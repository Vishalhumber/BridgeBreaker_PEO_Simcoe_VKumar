import csv
import time
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import messagebox

import matplotlib.pyplot as plt
import matplotlib.animation as animation
import pandas as pd
import serial
import serial.tools.list_ports
import keyboard


# ---------------- USER SETTINGS ----------------

# Calibration: Newtons produced by 1 volt from the load cell / force sensor.
# Example: if 1 V equals 50 N, set this to 50.
NEWTONS_PER_VOLT = 100
# Time between saved force readings, in seconds
# 0.100 seconds = 100 milliseconds = 10 readings per second
LOG_INTERVAL_SECONDS = 0.100

# Voltage offset at zero load, in volts.
# If the sensor outputs 0.05 V with no load, set ZERO_OFFSET_VOLTS = 0.05.
ZERO_OFFSET_VOLTS = 0.0

# Which analog channel is connected to the force sensor:
# 0 = analog channel 0
# 1 = analog channel 1
FORCE_CHANNEL = 0

# Mark a bridge break after voltage drops this much from its observed peak.
BREAK_VOLTAGE_DROP_PERCENT = 90
# Require multiple consecutive low readings to avoid marking a brief noise spike.
BREAK_CONFIRMATION_SAMPLES = 3

# -----------------------------------------------


slist = [0x0000, 0x0001, 0x0709, 0x000A]
analog_ranges = [10]

rate_ranges = (
    50000, 20000, 10000, 5000, 2000,
    1000, 500, 200, 100, 50, 20, 10
)

range_table = []
ser = serial.Serial()
acquiring = False


def discovery():
    available_ports = list(serial.tools.list_ports.comports())
    hooked_port = ""

    for port in available_ports:
        if "VID:PID=0683" in port.hwid:
            hooked_port = port.device
            break

    if hooked_port:
        print(f"Found DATAQ device on {hooked_port}")
        ser.timeout = 0
        ser.port = hooked_port
        ser.baudrate = 115200
        ser.open()
        return True

    print("Please connect the DATAQ Instruments device.")
    input("Press ENTER to try again...")
    return False


def send_cmd(command):
    ser.write((command + "\r").encode())
    time.sleep(0.1)

    if not acquiring:
        while ser.in_waiting > 0:
            response = ser.readline().decode(errors="ignore").strip()
            if response:
                print(response)
                break


def configure_scan_list():
    range_table.clear()

    for position, item in enumerate(slist):
        send_cmd(f"slist {position} {item}")

        function = item & 0x0F

        if function < 8:
            range_table.append(analog_ranges[item >> 8])
        elif function == 8:
            range_table.append(0)
        elif function == 9:
            range_table.append(rate_ranges[(item >> 8) - 1])
        else:
            range_table.append(0)


def collect_participant_name():
    root = tk.Tk()
    root.title("Bridge Building Competition")
    root.resizable(False, False)

    frame = tk.Frame(root, padx=24, pady=20)
    frame.pack(fill="both", expand=True)

    tk.Label(
        frame,
        text="Bridge Building Competition",
        font=("TkDefaultFont", 16, "bold"),
    ).pack(pady=(0, 12))
    tk.Label(frame, text="Enter your name to check in for the test:").pack(anchor="w")

    name_entry = tk.Entry(frame, width=36)
    name_entry.pack(fill="x", pady=(6, 4))

    error_label = tk.Label(frame, text="", fg="red")
    error_label.pack(anchor="w")

    participant = {"name": ""}

    def submit_name():
        name = name_entry.get().strip()
        if not name:
            error_label.config(text="Please enter your name.")
            name_entry.focus_set()
            return

        participant["name"] = name
        messagebox.showinfo(
            "Ready for test",
            f"Thank you, {name}. You are ready for your test. Please wait for the operator.",
            parent=root,
        )
        root.destroy()

    tk.Button(
        frame,
        text="Ready for test",
        command=submit_name,
        padx=12,
        pady=6,
    ).pack(pady=(10, 0))

    root.after(100, name_entry.focus_set)
    root.mainloop()

    return participant["name"]


while not discovery():
    pass

send_cmd("stop")
send_cmd("encode 0")
send_cmd("ps 0")
configure_scan_list()

# Approximately 10 samples per second per scan-list element
send_cmd("dec 512")
send_cmd("srate 11718")

# Find the position of the selected force channel
try:
    force_index = slist.index(FORCE_CHANNEL)
except ValueError:
    raise ValueError("FORCE_CHANNEL must be 0 or 1 for this configuration.")

# Check participants in only after the force sensor is ready.
participant_name = collect_participant_name()
if not participant_name:
    send_cmd("stop")
    ser.close()
    raise SystemExit("Participant check-in was cancelled; no test was started.")

safe_participant_name = "".join(
    character if character.isalnum() or character in "-_" else "_"
    for character in participant_name
).strip("_") or "participant"
test_folder = Path(
    f"{safe_participant_name}_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S_%f')}"
)
test_folder.mkdir()
CSV_FILENAME = test_folder / f"{safe_participant_name}.csv"

# Prepare CSV logging
csv_file = open(CSV_FILENAME, "w", newline="", encoding="utf-8")
csv_writer = csv.writer(csv_file)
csv_writer.writerow([
    "Participant_Name",
    "Time_s",
    "Voltage_V",
    "Force_N",
    "Break_Event",
    "Peak_Load_Before_Break_N",
])

# Data for plotting
times = []
voltages = []
forces = []
break_events = []
peak_load_before_break_values = []

start_time = None
peak_voltage = None
low_voltage_samples = 0
break_detected = False
peak_load_before_break = None

# Create live graph
plt.ion()
fig, ax = plt.subplots(figsize=(20, 5))
line, = ax.plot([], [], color="tab:blue", linewidth=2)
ax.set_xlabel("Time (s)")
ax.set_ylabel("Force (N)")
ax.set_title("Force vs. Time")
ax.grid(True)

print(f"\n=== BRIDGE BUILDING TEST: {participant_name} ===")
print("Press G to start, S to stop, Q to quit.")
print(f"Saving data to: {CSV_FILENAME}\n")


def update_graph():
    line.set_data(times, forces)

    if len(times) > 0:
        current_force = forces[-1]
        peak_force = max(forces) if forces else 0.0
        average_force = sum(forces) / len(forces) if forces else 0.0

        ax.set_title(
            f"Force vs. Time - {participant_name}"
            + (" - BRIDGE BREAK DETECTED" if break_detected else ""),
            fontsize=14,
            fontweight="bold",
        )
        ax.set_xlabel("Time (s)", fontsize=11)
        ax.set_ylabel("Force (N)", fontsize=11)
        ax.grid(True, linestyle="--", alpha=0.6)

        if len(times) > 1:
            ax.set_xlim(min(times), max(times))
            y_min = min(forces)
            y_max = max(forces)
            pad = max(1.0, abs(y_min) * 0.1, abs(y_max) * 0.1)
            ax.set_ylim(y_min - pad, y_max + pad)

        for text_obj in ax.texts:
            text_obj.remove()

        ax.text(
            0.02, 0.98,
            f"Latest: {current_force:.2f} N\nPeak: {peak_force:.2f} N\nAvg: {average_force:.2f} N",
            transform=ax.transAxes,
            va="top",
            fontsize=9,
            bbox=dict(boxstyle="round,pad=0.35", facecolor="white", edgecolor="0.7", alpha=0.85)
        )

        if break_detected:
            break_index = break_events.index(True)
            ax.text(
                0.98, 0.98,
                f"BRIDGE BREAK DETECTED\n"
                f"Time: {times[break_index]:.3f} s\n"
                f"Voltage: {voltages[break_index]:.4f} V\n"
                f"Peak load before break: {peak_load_before_break:.2f} N",
                transform=ax.transAxes,
                ha="right",
                va="top",
                color="darkred",
                fontsize=11,
                fontweight="bold",
                bbox=dict(
                    boxstyle="round,pad=0.4",
                    facecolor="mistyrose",
                    edgecolor="darkred",
                    alpha=0.95,
                ),
            )

    fig.canvas.draw()
    fig.canvas.flush_events()


def print_status():
    if not times:
        status = "WAITING FOR DATA" if acquiring else "IDLE"
        current_force = 0.0
        peak_force = 0.0
        average_force = 0.0
        elapsed_time = 0.0
    else:
        status = (
            "BREAK DETECTED"
            if break_detected
            else "ACQUIRING" if acquiring else "READY"
        )
        current_force = forces[-1]
        peak_force = max(forces)
        average_force = sum(forces) / len(forces)
        elapsed_time = times[-1] if times else 0.0

    print(
        f"\rStatus: {status:<16} | Time: {elapsed_time:7.2f}s | "
        f"Current: {current_force:7.2f} N | Peak: {peak_force:7.2f} N | "
        f"Average: {average_force:7.2f} N | File: {CSV_FILENAME}",
        end="",
        flush=True,
    )


print_status()


while True:
    if keyboard.is_pressed("g") or keyboard.is_pressed("G"):
        if not acquiring:
            acquiring = True
            start_time = time.perf_counter()
            send_cmd("start")
            print("Acquisition started.")
            print_status()

    elif keyboard.is_pressed("s") or keyboard.is_pressed("S"):
        if acquiring:
            send_cmd("stop")
            time.sleep(1)
            ser.reset_input_buffer()
            acquiring = False
            print("Acquisition stopped.")
            print_status()

    elif keyboard.is_pressed("q") or keyboard.is_pressed("Q"):
        send_cmd("stop")
        time.sleep(0.5)
        ser.reset_input_buffer()
        break

    if acquiring and ser.in_waiting >= 2 * len(slist):
        for i in range(len(slist)):
            function = slist[i] & 0x0F
            raw = ser.read(2)

            if function < 8:
                voltage = (
                    range_table[i]
                    * int.from_bytes(raw, byteorder="little", signed=True)
                    / 32768
                )
            else:
                # Skip non-analog channels for force logging
                continue

            if i == force_index:
                elapsed_time = time.perf_counter() - start_time
                force = (voltage - ZERO_OFFSET_VOLTS) * NEWTONS_PER_VOLT
                is_break_event = False

                if not break_detected:
                    if peak_voltage is None or voltage > peak_voltage:
                        peak_voltage = voltage
                        low_voltage_samples = 0
                    elif peak_voltage > ZERO_OFFSET_VOLTS:
                        break_threshold = ZERO_OFFSET_VOLTS + (
                            (peak_voltage - ZERO_OFFSET_VOLTS)
                            * (1 - BREAK_VOLTAGE_DROP_PERCENT / 100)
                        )
                        if voltage <= break_threshold + 1e-12:
                            low_voltage_samples += 1
                        else:
                            low_voltage_samples = 0

                        if low_voltage_samples >= BREAK_CONFIRMATION_SAMPLES:
                            break_detected = True
                            is_break_event = True
                            peak_load_before_break = max(forces + [force])

                times.append(elapsed_time)
                voltages.append(voltage)
                forces.append(force)
                break_events.append(is_break_event)
                peak_load_before_break_values.append(peak_load_before_break)

                csv_writer.writerow([
                    participant_name,
                    f"{elapsed_time:.6f}",
                    f"{voltage:.6f}",
                    f"{force:.3f}",
                    "BREAK DETECTED" if is_break_event else "",
                    (
                        f"{peak_load_before_break:.3f}"
                        if peak_load_before_break is not None
                        else ""
                    ),
                ])
                csv_file.flush()

                if is_break_event:
                    print(
                        f"\nBridge break detected at {elapsed_time:.3f}s "
                        f"({voltage:.4f} V, {force:.2f} N). "
                        f"Peak load before break: {peak_load_before_break:.2f} N. "
                        "Continuing to log."
                    )

                update_graph()
                print_status()

# Stop acquisition and close everything cleanly
send_cmd("stop")
time.sleep(0.5)
ser.reset_input_buffer()
ser.close()
csv_file.close()

# Save a final CSV copy using pandas as well
df = pd.DataFrame({
    "Participant_Name": [participant_name] * len(times),
    "Time_s": times,
    "Voltage_V": voltages,
    "Force_N": forces,
    "Break_Event": [
        "BREAK DETECTED" if event else ""
        for event in break_events
    ],
    "Peak_Load_Before_Break_N": peak_load_before_break_values,
})
df.to_csv(CSV_FILENAME, index=False)

# Save a static graph after logging ends
plt.ioff()
fig, ax = plt.subplots(figsize=(10, 5))
ax.plot(times, forces, color="#1f77b4", linewidth=2)
ax.set_xlabel("Time (s)", fontsize=11)
ax.set_ylabel("Force (N)", fontsize=11)
ax.set_title(
    f"Force vs. Time - {participant_name}",
    fontsize=14,
    fontweight="bold",
)
ax.grid(True, linestyle="--", alpha=0.6)

if break_detected:
    break_index = break_events.index(True)
    ax.axvline(
        times[break_index],
        color="tab:red",
        linestyle="--",
        linewidth=2,
        label="BREAK DETECTED",
    )
    ax.text(
        0.98, 0.98,
        f"BREAK DETECTED\n"
        f"Time: {times[break_index]:.3f} s\n"
        f"Voltage: {voltages[break_index]:.4f} V\n"
        f"Force at detection: {forces[break_index]:.2f} N\n"
        f"Peak load before break: {peak_load_before_break:.2f} N",
        transform=ax.transAxes,
        ha="right",
        va="top",
        color="darkred",
        fontsize=11,
        fontweight="bold",
        bbox=dict(
            boxstyle="round,pad=0.4",
            facecolor="mistyrose",
            edgecolor="darkred",
            alpha=0.95,
        ),
    )
    ax.legend()

if forces:
    peak_force = max(forces)
    average_force = sum(forces) / len(forces)
    ax.text(
        0.02, 0.98,
        f"Peak: {peak_force:.2f} N\nAverage: {average_force:.2f} N",
        transform=ax.transAxes,
        va="top",
        fontsize=10,
        bbox=dict(boxstyle="round,pad=0.35", facecolor="white", edgecolor="0.7", alpha=0.9)
    )

graph_filename = CSV_FILENAME.with_suffix(".png")
plt.savefig(graph_filename, dpi=200, bbox_inches="tight")

print("\n")
print("=== DATA COLLECTION COMPLETE ===")
print(f"Duration: {max(times) if times else 0.0:.2f} s")
print(f"Samples logged: {len(times)}")
print(f"Peak force: {max(forces) if forces else 0.0:.3f} N")
print(f"Average force: {sum(forces) / len(forces) if forces else 0.0:.3f} N")
if break_detected:
    break_index = break_events.index(True)
    print(f"Break detected at: {times[break_index]:.3f} s")
    print(f"Highest load before break: {peak_load_before_break:.3f} N")
else:
    print("Bridge break was not detected.")
print(f"Test folder: {test_folder}")
print(f"CSV saved to: {CSV_FILENAME}")
print(f"Graph saved to: {graph_filename}")
plt.show()
import csv
import time
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox

import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.widgets import Button
import pandas as pd
import serial
import serial.tools.list_ports
import keyboard


# ---------------- USER SETTINGS ----------------

# Calibration: Newtons produced by 1 volt from the load cell / force sensor.
# Example: if 1 V equals 50 N, set this to 50.
NEWTONS_PER_VOLT = 224
# Time between saved force readings, in seconds
# 0.100 seconds = 100 milliseconds = 10 readings per second
LOG_INTERVAL_SECONDS = 0.0001

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
elapsed_time_offset = 0.0
peak_voltage = None
low_voltage_samples = 0
break_detected = False
peak_load_before_break = None

# Create live graph
plt.ion()
fig, ax = plt.subplots(figsize=(20, 5))
fig.subplots_adjust(bottom=0.22)
line, = ax.plot([], [], color="tab:blue", linewidth=2, label=participant_name)
ax.set_xlabel("Time (s)")
ax.set_ylabel("Force (N)")
ax.set_title("Force vs. Time")
ax.grid(True)

comparison_datasets = []
quit_requested = False

print(f"\n=== BRIDGE BUILDING TEST: {participant_name} ===")
print("Use the graph buttons or press G to start, S to stop, Q to quit.")
print(f"Saving data to: {CSV_FILENAME}\n")


def update_graph():
    line.set_data(times, forces)

    plot_times = list(times)
    plot_forces = list(forces)
    for dataset in comparison_datasets:
        plot_times.extend(dataset["times"])
        plot_forces.extend(dataset["forces"])

    if plot_times:
        x_min = min(0.0, min(plot_times))
        x_max = max(plot_times)
        if x_min == x_max:
            x_max = x_min + 1.0
        ax.set_xlim(x_min, x_max)

        y_min = min(plot_forces)
        y_max = max(plot_forces)
        pad = max(1.0, abs(y_min) * 0.1, abs(y_max) * 0.1)
        ax.set_ylim(y_min - pad, y_max + pad)

    if comparison_datasets:
        ax.legend(loc="best", fontsize=8)
    elif ax.get_legend():
        ax.get_legend().remove()

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


def refresh_acquisition_buttons():
    start_button.label.set_text("Start (G)")
    stop_button.label.set_text("Stop (S)")
    start_button.ax.set_facecolor("0.85" if acquiring else "0.95")
    stop_button.ax.set_facecolor("0.95" if acquiring else "0.85")
    fig.canvas.draw_idle()


def start_acquisition(event=None):
    global acquiring, start_time, elapsed_time_offset

    if acquiring:
        return

    acquiring = True
    elapsed_time_offset = times[-1] if times else 0.0
    start_time = time.perf_counter()
    send_cmd("start")
    refresh_acquisition_buttons()
    print("\nAcquisition started.")
    print_status()


def stop_acquisition(event=None):
    global acquiring

    if not acquiring:
        return

    send_cmd("stop")
    time.sleep(1)
    ser.reset_input_buffer()
    acquiring = False
    refresh_acquisition_buttons()
    print("\nAcquisition stopped.")
    print_status()


def compare_participant_data(event=None):
    root = tk.Tk()
    root.withdraw()
    try:
        filenames = filedialog.askopenfilenames(
            parent=root,
            title="Select participant test CSV files",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not filenames:
            return

        existing_paths = {dataset["path"] for dataset in comparison_datasets}
        new_datasets = []
        for filename in filenames:
            csv_path = Path(filename).resolve()
            if csv_path in existing_paths:
                continue

            frame = pd.read_csv(csv_path)
            required_columns = {"Participant_Name", "Time_s", "Force_N"}
            missing_columns = required_columns.difference(frame.columns)
            if missing_columns:
                raise ValueError(
                    f"{csv_path.name} is missing required columns: "
                    f"{', '.join(sorted(missing_columns))}."
                )

            numeric_data = frame[["Time_s", "Force_N"]].apply(
                pd.to_numeric, errors="coerce"
            )
            if numeric_data.empty or numeric_data.isna().any().any():
                raise ValueError(
                    f"{csv_path.name} has no complete numeric time/force data."
                )

            names = frame["Participant_Name"].dropna().astype(str)
            participant = names.iloc[0] if not names.empty else csv_path.stem
            new_datasets.append({
                "path": csv_path,
                "participant": participant,
                "times": numeric_data["Time_s"].tolist(),
                "forces": numeric_data["Force_N"].tolist(),
            })
            existing_paths.add(csv_path)

        for dataset in new_datasets:
            (dataset["line"],) = ax.plot(
                dataset["times"],
                dataset["forces"],
                linewidth=1.5,
                alpha=0.8,
                label=dataset["participant"],
            )
            comparison_datasets.append(dataset)

        update_graph()
    except (OSError, pd.errors.ParserError, UnicodeDecodeError, ValueError) as error:
        messagebox.showerror(
            "Unable to compare participant data",
            str(error),
            parent=root,
        )
    finally:
        root.destroy()


def clear_comparisons(event=None):
    for dataset in comparison_datasets:
        dataset["line"].remove()
    comparison_datasets.clear()
    update_graph()


def quit_application(event=None):
    global quit_requested

    stop_acquisition()
    quit_requested = True


button_specs = (
    (0.08, 0.12, "Start (G)", start_acquisition),
    (0.22, 0.12, "Stop (S)", stop_acquisition),
    (0.36, 0.18, "Compare CSVs", compare_participant_data),
    (0.56, 0.18, "Clear Comparisons", clear_comparisons),
    (0.76, 0.14, "Quit (Q)", quit_application),
)
buttons = []
for left, width, label, callback in button_specs:
    button_ax = fig.add_axes([left, 0.06, width, 0.09])
    buttons.append(Button(button_ax, label))
    buttons[-1].on_clicked(callback)
start_button, stop_button = buttons[:2]
refresh_acquisition_buttons()


def print_status():
    if not times:
        status = "ACQUIRING" if acquiring else "IDLE"
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
        f"\rStatus: {status:<14} | Time: {elapsed_time:7.2f}s | "
        f"Current: {current_force:7.2f} N | Peak: {peak_force:7.2f} N | "
        f"Average: {average_force:7.2f} N | File: {CSV_FILENAME}",
        end="",
        flush=True,
    )


print_status()


while not quit_requested and plt.fignum_exists(fig.number):
    if keyboard.is_pressed("g") or keyboard.is_pressed("G"):
        start_acquisition()

    elif keyboard.is_pressed("s") or keyboard.is_pressed("S"):
        stop_acquisition()

    elif keyboard.is_pressed("q") or keyboard.is_pressed("Q"):
        quit_application()
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
                elapsed_time = (
                    elapsed_time_offset
                    + time.perf_counter()
                    - start_time
                )
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

    plt.pause(0.01)

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
ax.plot(
    times,
    forces,
    color="#1f77b4",
    linewidth=2,
    label=participant_name,
)
for dataset in comparison_datasets:
    ax.plot(
        dataset["times"],
        dataset["forces"],
        linewidth=1.5,
        alpha=0.8,
        label=dataset["participant"],
    )
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

if comparison_datasets:
    ax.legend(loc="best", fontsize=8)

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
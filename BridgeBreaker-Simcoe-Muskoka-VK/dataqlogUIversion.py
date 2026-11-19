import csv
import math
import time
from datetime import datetime
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import matplotlib
matplotlib.use("TkAgg")

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import pandas as pd
import serial
import serial.tools.list_ports


# ---------------- USER SETTINGS ----------------

NEWTONS_PER_VOLT = 224
ZERO_OFFSET_VOLTS = 0.0
FORCE_CHANNEL = 0

BREAK_VOLTAGE_DROP_PERCENT = 90
BREAK_CONFIRMATION_SAMPLES = 3

# -----------------------------------------------


slist = [0x0000, 0x0001, 0x0709, 0x000A]
analog_ranges = [10]

rate_ranges = (
    50000, 20000, 10000, 5000, 2000,
    1000, 500, 200, 100, 50, 20, 10
)

ser = serial.Serial()
acquiring = False
participant_name = ""
test_folder = None
CSV_FILENAME = None
csv_file = None
csv_writer = None

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

comparison_datasets = []


def load_participant_results(results_directory, excluded_path=None):
    results = {}
    errors = []
    excluded_path = excluded_path.resolve() if excluded_path else None

    for csv_path in results_directory.glob("*/*.csv"):
        if excluded_path and csv_path.resolve() == excluded_path:
            continue

        try:
            with csv_path.open("r", newline="", encoding="utf-8-sig") as data_file:
                reader = csv.DictReader(data_file)
                if not {"Participant_Name", "Force_N"}.issubset(reader.fieldnames or []):
                    continue

                participant = ""
                peak_force = None
                for row in reader:
                    participant = participant or (row.get("Participant_Name") or "").strip()
                    try:
                        force = float(row.get("Force_N", ""))
                    except (TypeError, ValueError):
                        continue

                    if math.isfinite(force):
                        peak_force = force if peak_force is None else max(peak_force, force)

                if participant and peak_force is not None:
                    results[participant] = max(
                        results.get(participant, peak_force),
                        peak_force,
                    )
        except (OSError, UnicodeDecodeError, csv.Error) as error:
            errors.append(f"{csv_path}: {error}")

    return results, errors


class BridgeTestApp(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("Bridge Building Competition")
        self.geometry("1450x800")
        self.minsize(1180, 680)

        self.device_connected = False
        self.device_port = ""
        self.live_participant_results = {}

        self._build_ui()
        self._create_plot()
        self.refresh_participant_results()

        self.after(500, self.check_device_connection)
        self.after(20, self.read_sensor_data)
        self.protocol("WM_DELETE_WINDOW", self.quit_application)

    # ------------------------------------------------------------
    # User interface
    # ------------------------------------------------------------

    def _build_ui(self):
        main = ttk.Frame(self, padding=10)
        main.pack(fill="both", expand=True)

        title = ttk.Label(
            main,
            text="Bridge Building Competition",
            font=("Segoe UI", 18, "bold"),
        )
        title.pack(pady=(0, 8))

        content = ttk.Frame(main)
        content.pack(fill="both", expand=True)

        controls = ttk.Frame(content)
        controls.pack(side="left", fill="both", expand=True)
        self.controls_frame = controls

        sidebar = ttk.LabelFrame(content, text="Competition Leaderboard", padding=8)
        sidebar.pack(side="right", fill="y", padx=(10, 0))
        sidebar.pack_propagate(False)
        sidebar.configure(width=310)

        self.participant_count_label = ttk.Label(sidebar, text="Participants: 0")
        self.participant_count_label.pack(anchor="w", pady=(0, 5))

        self.winner_label = ttk.Label(
            sidebar,
            text="Winner: —",
            font=("Segoe UI", 11, "bold"),
            wraplength=280,
        )
        self.winner_label.pack(anchor="w", pady=(0, 8))

        self.participant_table = ttk.Treeview(
            sidebar,
            columns=("rank", "participant", "peak"),
            show="headings",
            height=20,
        )
        self.participant_table.heading("rank", text="#")
        self.participant_table.heading("participant", text="Participant")
        self.participant_table.heading("peak", text="Peak (N)")
        self.participant_table.column("rank", width=28, anchor="center", stretch=False)
        self.participant_table.column("participant", width=145, anchor="w")
        self.participant_table.column("peak", width=82, anchor="e", stretch=False)
        self.participant_table.tag_configure("winner", foreground="#087a34")
        self.participant_table.pack(fill="both", expand=True)

        ttk.Button(
            sidebar,
            text="Refresh Results",
            command=self.refresh_participant_results,
        ).pack(fill="x", pady=(8, 0))

        connection_frame = ttk.LabelFrame(controls, text="Device Status", padding=10)
        connection_frame.pack(fill="x", pady=(0, 10))

        self.connection_label = ttk.Label(
            connection_frame,
            text="Checking for DATAQ device...",
            font=("Segoe UI", 12, "bold"),
        )
        self.connection_label.pack(side="left")

        self.port_label = ttk.Label(connection_frame, text="")
        self.port_label.pack(side="left", padx=(15, 0))

        ttk.Button(
            connection_frame,
            text="Check Connection",
            command=self.check_device_connection,
        ).pack(side="right")

        setup_frame = ttk.LabelFrame(controls, text="Participant Check-In", padding=10)
        setup_frame.pack(fill="x", pady=(0, 10))

        ttk.Label(setup_frame, text="Participant name:").pack(side="left")

        self.name_entry = ttk.Entry(setup_frame, width=35)
        self.name_entry.pack(side="left", padx=8)
        self.name_entry.focus_set()

        self.check_in_button = ttk.Button(
            setup_frame,
            text="Check In",
            command=self.collect_participant_name,
        )
        self.check_in_button.pack(side="left")

        self.participant_label = ttk.Label(
            setup_frame,
            text="No participant checked in.",
            font=("Segoe UI", 10, "bold"),
        )
        self.participant_label.pack(side="left", padx=15)

        control_frame = ttk.LabelFrame(controls, text="Test Controls", padding=10)
        control_frame.pack(fill="x", pady=(0, 10))

        self.start_button = ttk.Button(
            control_frame,
            text="Start Test (G)",
            command=self.start_acquisition,
            state="disabled",
        )
        self.start_button.pack(side="left", padx=(0, 8))

        self.stop_button = ttk.Button(
            control_frame,
            text="Stop Test (S)",
            command=self.stop_acquisition,
            state="disabled",
        )
        self.stop_button.pack(side="left", padx=(0, 8))

        ttk.Button(
            control_frame,
            text="Compare CSVs",
            command=self.compare_participant_data,
        ).pack(side="left", padx=(0, 8))

        ttk.Button(
            control_frame,
            text="Clear Comparisons",
            command=self.clear_comparisons,
        ).pack(side="left", padx=(0, 8))

        ttk.Button(
            control_frame,
            text="Quit",
            command=self.quit_application,
        ).pack(side="right")

        self.bind("<Key-g>", lambda event: self.start_acquisition())
        self.bind("<Key-G>", lambda event: self.start_acquisition())
        self.bind("<Key-s>", lambda event: self.stop_acquisition())
        self.bind("<Key-S>", lambda event: self.stop_acquisition())
        self.bind("<Escape>", lambda event: self.quit_application())

        status_frame = ttk.LabelFrame(controls, text="Live Test Status", padding=10)
        status_frame.pack(fill="x", pady=(0, 10))

        self.status_label = ttk.Label(
            status_frame,
            text="Status: READY",
            font=("Segoe UI", 12, "bold"),
        )
        self.status_label.pack(side="left")

        self.stats_label = ttk.Label(
            status_frame,
            text="Time: 0.00 s | Current: 0.00 N | Peak: 0.00 N | Average: 0.00 N",
            font=("Consolas", 11),
        )
        self.stats_label.pack(side="right")

        self.file_label = ttk.Label(
            controls,
            text="No data file created yet.",
            foreground="#555555",
        )
        self.file_label.pack(fill="x", pady=(0, 5))

    def _create_plot(self):
        plot_frame = ttk.LabelFrame(self.controls_frame, text="Force vs. Time", padding=8)
        plot_frame.pack(fill="both", expand=True, pady=(0, 10))

        self.figure = Figure(figsize=(8, 4.5), dpi=100)
        self.axes = self.figure.add_subplot(111)

        self.axes.set_xlabel("Time (s)")
        self.axes.set_ylabel("Force (N)")
        self.axes.set_title("Force vs. Time")
        self.axes.grid(True, linestyle="--", alpha=0.6)

        self.force_line, = self.axes.plot([], [], color="tab:blue", linewidth=2)

        self.canvas = FigureCanvasTkAgg(self.figure, master=plot_frame)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

    # ------------------------------------------------------------
    # DATAQ device connection
    # ------------------------------------------------------------

    def find_dataq_port(self):
        for port in serial.tools.list_ports.comports():
            if "VID:PID=0683" in port.hwid:
                return port.device
        return ""

    def check_device_connection(self):
        port_name = self.find_dataq_port()

        if port_name:
            if not ser.is_open or self.device_port != port_name:
                try:
                    if ser.is_open:
                        ser.close()

                    ser.timeout = 0
                    ser.port = port_name
                    ser.baudrate = 115200
                    ser.open()

                    self.device_port = port_name
                    self.device_connected = True

                    self.configure_device()

                    self.connection_label.config(
                        text="DEVICE CONNECTED",
                        foreground="green",
                    )
                    self.port_label.config(text=f"Port: {port_name}")

                    self.start_button.config(state="normal")
                    self.stop_button.config(state="disabled")

                except serial.SerialException as error:
                    self.device_connected = False
                    self.connection_label.config(
                        text="CONNECTION ERROR",
                        foreground="red",
                    )
                    self.port_label.config(text=str(error))
                    self.start_button.config(state="disabled")
                    self.stop_button.config(state="disabled")
            else:
                self.connection_label.config(
                    text="DEVICE CONNECTED",
                    foreground="green",
                )
                self.port_label.config(text=f"Port: {self.device_port}")
        else:
            if ser.is_open:
                try:
                    ser.close()
                except Exception:
                    pass

            self.device_connected = False
            self.device_port = ""
            self.connection_label.config(
                text="DEVICE NOT CONNECTED",
                foreground="red",
            )
            self.port_label.config(text="Connect the DATAQ device and click Check Connection.")
            self.start_button.config(state="disabled")
            self.stop_button.config(state="disabled")

        self.after(2000, self.check_device_connection)

    def send_cmd(self, command):
        if not ser.is_open:
            return

        ser.write((command + "\r").encode())
        time.sleep(0.05)

        if not acquiring and ser.in_waiting > 0:
            response = ser.readline().decode(errors="ignore").strip()
            if response:
                print(response)

    def configure_device(self):
        self.send_cmd("stop")
        self.send_cmd("encode 0")
        self.send_cmd("ps 0")

        for position, item in enumerate(slist):
            self.send_cmd(f"slist {position} {item}")

        self.send_cmd("dec 512")
        self.send_cmd("srate 11718")

    # ------------------------------------------------------------
    # Participant check-in and file setup
    # ------------------------------------------------------------

    def collect_participant_name(self):
        name = self.name_entry.get().strip()

        if not name:
            messagebox.showwarning(
                "Name required",
                "Please enter the participant's name before starting.",
                parent=self,
            )
            self.name_entry.focus_set()
            return

        global participant_name, test_folder, CSV_FILENAME
        global csv_file, csv_writer

        participant_name = name

        safe_name = "".join(
            character if character.isalnum() or character in "-_" else "_"
            for character in participant_name
        ).strip("_") or "participant"

        test_folder = Path(
            f"{safe_name}_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S_%f')}"
        )
        test_folder.mkdir()

        CSV_FILENAME = test_folder / f"{safe_name}.csv"

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

        self.participant_label.config(text=f"Checked in: {participant_name}")
        self.file_label.config(text=f"Saving data to: {CSV_FILENAME}")

        messagebox.showinfo(
            "Ready for test",
            f"Thank you, {participant_name}.\n\nYou are ready for your test. Please wait for the operator.",
            parent=self,
        )

    # ------------------------------------------------------------
    # Acquisition controls
    # ------------------------------------------------------------

    def start_acquisition(self):
        global acquiring, start_time, elapsed_time_offset

        if acquiring:
            return

        if not self.device_connected:
            messagebox.showerror(
                "Device not connected",
                "Please connect the DATAQ device before starting the test.",
                parent=self,
            )
            return

        if not participant_name:
            messagebox.showwarning(
                "Participant required",
                "Please enter a participant name and click Check In first.",
                parent=self,
            )
            self.name_entry.focus_set()
            return

        acquiring = True
        elapsed_time_offset = times[-1] if times else 0.0
        start_time = time.perf_counter()

        self.send_cmd("start")

        self.start_button.config(state="disabled")
        self.stop_button.config(state="normal")
        self.update_status()

    def stop_acquisition(self):
        global acquiring

        if not acquiring:
            return

        self.send_cmd("stop")
        time.sleep(0.5)

        if ser.is_open:
            ser.reset_input_buffer()

        acquiring = False

        self.start_button.config(state="normal")
        self.stop_button.config(state="disabled")
        self.update_status()

    # ------------------------------------------------------------
    # Sensor reading, CSV logging, and break detection
    # ------------------------------------------------------------

    def read_sensor_data(self):
        global start_time, elapsed_time_offset
        global peak_voltage, low_voltage_samples
        global break_detected, peak_load_before_break

        if acquiring and ser.is_open and ser.in_waiting >= 2 * len(slist):
            for i, item in enumerate(slist):
                function = item & 0x0F
                raw = ser.read(2)

                if function >= 8:
                    continue

                voltage = (
                    analog_ranges[item >> 8]
                    * int.from_bytes(raw, byteorder="little", signed=True)
                    / 32768
                )

                if i != FORCE_CHANNEL:
                    continue

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

                if csv_writer:
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
                    messagebox.showwarning(
                        "Bridge break detected",
                        (
                            f"Bridge break detected at {elapsed_time:.3f} s.\n\n"
                            f"Voltage: {voltage:.4f} V\n"
                            f"Force: {force:.2f} N\n"
                            f"Peak load before break: {peak_load_before_break:.2f} N"
                        ),
                        parent=self,
                    )

                self.update_plot()
                self.update_status()

        self.after(20, self.read_sensor_data)

    # ------------------------------------------------------------
    # Graph and status updates
    # ------------------------------------------------------------

    def update_plot(self):
        self.force_line.set_data(times, forces)

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

            self.axes.set_xlim(x_min, x_max)

            y_min = min(plot_forces)
            y_max = max(plot_forces)
            pad = max(1.0, abs(y_min) * 0.1, abs(y_max) * 0.1)

            self.axes.set_ylim(y_min - pad, y_max + pad)

        title = f"Force vs. Time - {participant_name or 'No participant'}"

        if break_detected:
            title += " - BRIDGE BREAK DETECTED"

        self.axes.set_title(title, fontweight="bold")

        self.figure.canvas.draw_idle()

    def update_status(self):
        if not forces:
            current_force = 0.0
            peak_force = 0.0
            average_force = 0.0
            elapsed_time = 0.0
        else:
            current_force = forces[-1]
            peak_force = max(forces)
            average_force = sum(forces) / len(forces)
            elapsed_time = times[-1]

        if break_detected:
            status = "BREAK DETECTED"
            colour = "red"
        elif acquiring:
            status = "ACQUIRING"
            colour = "green"
        else:
            status = "READY"
            colour = "#0066cc"

        self.status_label.config(text=f"Status: {status}", foreground=colour)

        self.stats_label.config(
            text=(
                f"Time: {elapsed_time:7.2f} s | "
                f"Current: {current_force:7.2f} N | "
                f"Peak: {peak_force:7.2f} N | "
                f"Average: {average_force:7.2f} N"
            )
        )

    # ------------------------------------------------------------
    # CSV comparison
    # ------------------------------------------------------------

    def compare_participant_data(self):
        filenames = filedialog.askopenfilenames(
            parent=self,
            title="Select participant test CSV files",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )

        if not filenames:
            return

        existing_paths = {dataset["path"] for dataset in comparison_datasets}

        for filename in filenames:
            csv_path = Path(filename).resolve()

            if csv_path in existing_paths:
                continue

            try:
                frame = pd.read_csv(csv_path)

                required_columns = {"Participant_Name", "Time_s", "Force_N"}
                missing = required_columns.difference(frame.columns)

                if missing:
                    raise ValueError(
                        f"{csv_path.name} is missing: {', '.join(sorted(missing))}"
                    )

                numeric_data = frame[["Time_s", "Force_N"]].apply(
                    pd.to_numeric, errors="coerce"
                )

                names = frame["Participant_Name"].dropna().astype(str)
                participant = names.iloc[0] if not names.empty else csv_path.stem

                line, = self.axes.plot(
                    numeric_data["Time_s"],
                    numeric_data["Force_N"],
                    linewidth=1.5,
                    alpha=0.8,
                    label=participant,
                )

                comparison_datasets.append({
                    "path": csv_path,
                    "participant": participant,
                    "times": numeric_data["Time_s"].tolist(),
                    "forces": numeric_data["Force_N"].tolist(),
                    "line": line,
                })

                existing_paths.add(csv_path)

            except (OSError, pd.errors.ParserError, UnicodeDecodeError, ValueError) as error:
                messagebox.showerror(
                    "Unable to compare participant data",
                    str(error),
                    parent=self,
                )

        if comparison_datasets:
            self.axes.legend(loc="best", fontsize=8)

        self.figure.canvas.draw_idle()

    def clear_comparisons(self):
        for dataset in comparison_datasets:
            dataset["line"].remove()

        comparison_datasets.clear()

        if self.axes.get_legend():
            self.axes.get_legend().remove()

        self.figure.canvas.draw_idle()

    # ------------------------------------------------------------
    # Save final graph and close app
    # ------------------------------------------------------------

    def save_final_graph(self):
        if not forces or CSV_FILENAME is None:
            return

        final_figure = Figure(figsize=(10, 5), dpi=150)
        final_axes = final_figure.add_subplot(111)

        final_axes.plot(
            times,
            forces,
            color="#1f77b4",
            linewidth=2,
            label=participant_name,
        )

        for dataset in comparison_datasets:
            final_axes.plot(
                dataset["times"],
                dataset["forces"],
                linewidth=1.5,
                alpha=0.8,
                label=dataset["participant"],
            )

        final_axes.set_xlabel("Time (s)")
        final_axes.set_ylabel("Force (N)")
        final_axes.set_title(f"Force vs. Time - {participant_name}", fontweight="bold")
        final_axes.grid(True, linestyle="--", alpha=0.6)

        if break_detected:
            break_index = break_events.index(True)

            final_axes.axvline(
                times[break_index],
                color="tab:red",
                linestyle="--",
                linewidth=2,
                label="BREAK DETECTED",
            )

            final_axes.text(
                0.98, 0.98,
                (
                    f"BREAK DETECTED\n"
                    f"Time: {times[break_index]:.3f} s\n"
                    f"Voltage: {voltages[break_index]:.4f} V\n"
                    f"Force at detection: {forces[break_index]:.2f} N\n"
                    f"Peak load before break: {peak_load_before_break:.2f} N"
                ),
                transform=final_axes.transAxes,
                ha="right",
                va="top",
                color="darkred",
                fontsize=9,
                fontweight="bold",
                bbox=dict(
                    boxstyle="round,pad=0.4",
                    facecolor="mistyrose",
                    edgecolor="darkred",
                    alpha=0.95,
                ),
            )

        if forces:
            final_axes.text(
                0.02, 0.98,
                f"Peak: {max(forces):.2f} N\nAverage: {sum(forces) / len(forces):.2f} N",
                transform=final_axes.transAxes,
                va="top",
                fontsize=9,
                bbox=dict(
                    boxstyle="round,pad=0.35",
                    facecolor="white",
                    edgecolor="0.7",
                    alpha=0.9,
                ),
            )

        if comparison_datasets:
            final_axes.legend(loc="best", fontsize=8)

        graph_filename = CSV_FILENAME.with_suffix(".png")
        final_figure.savefig(graph_filename, dpi=200, bbox_inches="tight")

        return graph_filename

    def quit_application(self):
        global csv_file

        if acquiring:
            self.stop_acquisition()

        if csv_file is not None:
            csv_file.close()
            csv_file = None

        graph_filename = self.save_final_graph()

        if ser.is_open:
            self.send_cmd("stop")
            time.sleep(0.3)
            ser.reset_input_buffer()
            ser.close()

        if graph_filename:
            messagebox.showinfo(
                "Test complete",
                (
                    f"CSV saved to:\n{CSV_FILENAME}\n\n"
                    f"Graph saved to:\n{graph_filename}"
                ),
                parent=self,
            )

        self.destroy()


if __name__ == "__main__":
    app = BridgeTestApp()
    app.mainloop()
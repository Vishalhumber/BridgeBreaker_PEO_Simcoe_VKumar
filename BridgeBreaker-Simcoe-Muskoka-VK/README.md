# Bridge Breaker — Simcoe Muskoka

Python data-logging software for bridge-building tests. The app reads a force-sensor voltage through a DATAQ Instruments DI-4718-series data acquisition device, converts the voltage to force, displays a live force-versus-time graph, and saves each test's measurements and graph.

> **Measurement note:** The force conversion depends on the load cell, wiring, amplifier, and calibration. The calibration constants in the two application files differ. Verify the setup and calibrate the sensor before relying on any reported force or bridge-break result.

## Project photos

Add photos of the physical test equipment to `docs/images/`, then replace the examples below with the corresponding filenames. Please avoid including participant personal information in photos.

### Complete bridge-breaking test setup

<!-- Add a photo, for example: ![Complete bridge-breaking test setup](docs/images/bridge-breaker-setup.jpg) -->

### DATAQ device and sensor wiring

<!-- Add a photo, for example: ![DATAQ DI-4718 device and sensor wiring](docs/images/dataq-di-4718-wiring.jpg) -->

### Bridge immediately before and after breaking

<!-- Add photos, for example: ![Bridge before testing](docs/images/bridge-before-test.jpg) -->
<!-- Add photos, for example: ![Bridge after breaking](docs/images/bridge-after-break.jpg) -->

## What the app does

- Connects to a DATAQ device through its COM port in Universal mode.
- Prompts for a participant name before the test.
- Shows a live force-versus-time plot and current, peak, and average force.
- Marks a break event when the selected voltage signal falls by the configured percentage for the configured number of consecutive samples.
- Saves a CSV file and a PNG graph in a timestamped folder for each run.

The break marker is an automated signal-based estimate. Review the saved data and the physical test when interpreting a result.

## Hardware and software

- DATAQ Instruments DI-4718-series acquisition device (confirm the exact model and interface from the label on your unit).
- Load cell or force sensor with the appropriate signal conditioning and wiring.
- Windows PC with a working DATAQ USB serial driver.
- Python 3 and the packages listed in `requirements-win7.txt`.

The project includes `dataqlogapp.py` and a Windows 7-oriented variant, `dataqlogapp_win7.py`. The supplied Windows setup scripts create an isolated environment using **64-bit Python 3.8.10** and install the pinned packages.

## Setup on Windows 7

1. Install 64-bit Python 3.8.10 and ensure the Python Launcher (`py`) can find it.
2. Connect/install the DATAQ device and verify that Windows recognizes it.
3. Run `setup_win7.bat`. It creates `%LOCALAPPDATA%\BridgeBreaker-Simcoe-Muskoka-VK-venv` and installs the pinned dependencies.
4. Connect the sensor and DATAQ device.
5. Run `run_win7.bat` from the project folder.
6. Enter the participant name when prompted. The app waits for the operator to start acquisition.

For other Windows versions, use an appropriate Python environment and install the dependencies from `requirements-win7.txt`, then run `dataqlogapp.py`. The Win7 scripts explicitly require Python 3.8.10 x64.

## Running a test

1. Secure the bridge and force sensor in the test fixture. Check the wiring and ensure the sensor output is within the DAQ input range.
2. Start the application and enter the participant name.
3. Press **G** to start recording.
4. Apply the test load while monitoring the live graph.
5. Press **S** to stop acquisition, then **Q** to quit and finalize the run.

The CSV is written while acquisition is running; the final graph is generated when the app exits after **Q**. Use **S** to stop acquisition normally before quitting.

## Calibration and settings

The user settings are near the top of each Python application file:

- `NEWTONS_PER_VOLT`: force conversion factor (N/V). Determine it from the actual load cell/conditioning system; do not assume the checked-in values are correct for your rig.
- `ZERO_OFFSET_VOLTS`: sensor voltage at zero load.
- `FORCE_CHANNEL`: analog channel connected to the force sensor.
- `BREAK_VOLTAGE_DROP_PERCENT` and `BREAK_CONFIRMATION_SAMPLES`: threshold and consecutive-reading count used to flag a break.

The current `NEWTONS_PER_VOLT` values are `-224` in `dataqlogapp.py` and `100` in `dataqlogapp_win7.py`. Confirm the correct sign and scale experimentally before collecting reportable measurements. Do not edit the scan list or acquisition commands unless you have checked them against the manual for the exact device variant.

## Test output

Each run creates a timestamped directory in the project folder, named from the sanitized participant name and test time. Once the app exits, it contains:

- `<participant>.csv` — one row per force reading, with participant name, elapsed time, voltage, calculated force, break-event marker, and peak load before break.
- `<participant>.png` — a static force-versus-time graph, with a break marker and summary values when available.

Keep the CSV and graph together with the corresponding bridge/test photos so results can be traced to the test setup.

## DATAQ DI-4718 documentation

DATAQ's documentation index lists a hardware manual for the **DI-4718B Series**. Use the manufacturer's documentation and confirm that it applies to the exact model/interface printed on your device; if the label says **DI-4718U** and the series manual does not match, contact DATAQ support before changing hardware configuration.

- [DI-4718B Series hardware manual (PDF)](https://www.dataq.com/resources/pdfs/manuals/di-4718b-daq-manual.pdf)
- [DATAQ hardware and software manuals index](https://www.dataq.com/resources/pdfs/index.htm)
- [DATAQ DI-47xx firmware/support page](https://www.dataq.com/support/firmware/)
- [DATAQ technical support](https://www.dataq.com/support/tech_support.htm)

The manual is linked from DATAQ's website rather than copied into this repository. Follow the manufacturer's safety, wiring, input-range, and installation instructions for your device.

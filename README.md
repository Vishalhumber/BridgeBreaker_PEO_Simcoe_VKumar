# Bridge Breaker Competition

**Bridge Breaker — PEO Simcoe-Muskoka**  
**Author:** Vishal Kumar  
**Institution:** Humber College

## Overview

This repository contains the **Bridge Breaker** project developed for the Professional Engineers Ontario (PEO) Simcoe-Muskoka Bridge Breaker Competition.

The project includes a Python-based data-logging application used to measure and record force during bridge-testing activities. It reads force-sensor voltage through a DATAQ Instruments DI-4718-series data-acquisition device, converts the voltage to force, displays a live force-versus-time graph, identifies a possible break event, and saves the test data and graph for later review.

## Objectives

- Design and test a bridge structure for the competition requirements
- Measure applied force using a load cell or force sensor
- Record force readings over time during each test
- Identify the approximate point at which the bridge breaks
- Save force-versus-time results for comparison between participants and tests

## Technologies Used

- **Python 3** — Core programming language for the data-logging application
- **Python GUI and plotting libraries** — Used for the application interface and live force-versus-time graph
- **PyInstaller** — Used to package the Python application as a standalone Windows executable
- **Microsoft Windows** — Target operating system for the application and DATAQ device driver
- **CSV file format** — Used to store time, voltage, calculated force, break-event markers, and peak-load data
- **PNG image format** — Used to save force-versus-time graphs for each test

## DATAQ Instruments

The application uses a **DATAQ Instruments DI-4718-series data-acquisition (DAQ) device** to collect voltage signals from the force sensor.

### How the DATAQ device is used

1. The load cell or force sensor is connected to the DATAQ device through the appropriate wiring and signal-conditioning setup.
2. The DATAQ device is connected to a Windows computer through its USB serial interface.
3. The application connects to the DATAQ device through a selected COM port in Universal mode.
4. The device continuously samples the analog voltage signal from the force sensor.
5. The application converts the measured voltage into force using the configured calibration factor and zero-offset value.
6. The live force readings, peak force, and average force are displayed during the test.
7. The application detects a possible break when the voltage signal drops by the configured percentage for the required number of consecutive samples.
8. Each test is saved in a timestamped folder containing a CSV data file and a PNG force-versus-time graph.

## Measurement and Calibration

The force calculation depends on the load cell, wiring, amplifier or signal conditioner, and calibration settings.

The application uses the following key settings:

- `NEWTONS_PER_VOLT` — Conversion factor from sensor voltage to force in newtons
- `ZERO_OFFSET_VOLTS` — Sensor voltage measured at zero load
- `FORCE_CHANNEL` — Analog input channel connected to the force sensor
- `BREAK_VOLTAGE_DROP_PERCENT` — Voltage-drop threshold used to identify a possible break
- `BREAK_CONFIRMATION_SAMPLES` — Number of consecutive samples required to confirm the break event

The calibration values must be verified for the specific load cell and test setup before using force results for formal reporting.

## Repository Contents

- `BridgeBreaker-Simcoe-Muskoka-VK/` — Main application folder
- `BridgeBreakerCompetition.py` — Python source code for the main application
- `dataqlogapp.py` — DATAQ data-logging application
- `dataqlogUIversion.py` — User-interface version of the data-logging application
- `BridgeBreakerCompetition.exe` — Standalone Windows executable
- `Bridge_Breaker_User_Manual.docx` — Complete user manual
- Test-result folders — CSV files, PNG graphs, and supporting test records

## Running the Application

1. Install the DATAQ USB serial driver on the Windows computer.
2. Connect the load cell and DATAQ DI-4718-series device.
3. Run `BridgeBreakerCompetition.exe`, or run the Python application using an appropriate Python environment.
4. Enter the participant name when prompted.
5. Start data acquisition and apply the test load to the bridge.
6. Monitor the live force-versus-time graph.
7. Stop the test when complete.
8. Review the saved CSV file and PNG graph in the timestamped test folder.

## Test Output

Each completed test creates a timestamped folder containing:

- A CSV file with participant name, elapsed time, voltage, calculated force, break-event marker, and peak load before break
- A PNG force-versus-time graph with the break marker and summary values, where available

## Author

**Vishal Kumar**  
Humber College

## Acknowledgements

This project was completed for the PEO Simcoe-Muskoka Bridge Breaker Competition.
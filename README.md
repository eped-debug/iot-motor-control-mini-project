# IoT Motor Control with Light Sensor

Mini project for an Internet of Things (IoT) course. The system controls a DC motor according to ambient-light readings, schedules, keypad/UART input, and a Firebase-hosted web dashboard.

## Features

- Control and monitor the motor from a web page through Firebase Realtime Database.
- Control the device from a keypad and UART terminal.
- Configure motor speed.
- Set and display a target light-intensity range.
- Automatically apply the configured motor speed when the sensor reading is inside the target range.
- Configure two independent start/stop schedules.
- Preserve control and device-status data in Firebase across restarts.

## Project structure

| Path | Purpose |
| --- | --- |
| `boot.py` | Connects the MicroPython device to Wi-Fi (kept local; create it from `boot.example.py`). |
| `Sender.py` | Sends control commands and sensor data to Firebase. |
| `Reciever.py` | Reads hardware inputs and controls the DC motor. |
| `public/` | Firebase Hosting web dashboard. |
| `database.rules.json` | Firebase Realtime Database rules. |

## Hardware

- MicroPython-compatible controller (for example, ESP32)
- DC motor and motor driver
- Light sensor
- Matrix keypad
- UART connection between the controllers

## Setup

1. Copy `boot.example.py` to `boot.py` on the MicroPython device, then enter your Wi-Fi network name and password. Do not commit `boot.py`.
2. Update the Firebase Realtime Database URL in `Sender.py` and `public/index.html` if you use a different Firebase project.
3. Deploy `boot.py`, `Sender.py`, and `Reciever.py` to the appropriate MicroPython devices.
4. Install web dependencies and deploy Firebase Hosting:

   ```bash
   npm install
   firebase deploy
   ```

## Keypad/UART menu

| Function | Operation |
| --- | --- |
| 1 | Set time |
| 2 | Set motor speed |
| 3 | Show current light intensity |
| 4 | Timer off |
| 5 | Timer on |
| 6 | Set target light-intensity range |
| 7 | Show target light-intensity range |
| 8 | Set schedule 1 start time |
| 9 | Set schedule 1 stop time |
| 10 | Show schedule 1 |
| 11 | Set schedule 2 start time |
| 12 | Set schedule 2 stop time |
| 13 | Show schedule 2 |

## Security note

This repository excludes Wi-Fi credentials through `.gitignore`. Before deploying a public Firebase project, review `database.rules.json` and restrict access appropriately.

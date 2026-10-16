# ShowMeTheConnection

<img width="309" height="57" alt="image" src="https://github.com/user-attachments/assets/742d28ee-1c02-4e7f-af74-366cd1841a66" />

A lightweight Windows notification area utility for monitoring connection and battery details from supported devices. It runs without a main window. Built-in integrations support the Razer Barracuda X 2.4 GHz receiver, ATK X1 V2 with its 8K dongle, and KZZI K75 Lite with its 2.4 GHz receiver.

## Currently supported devices

- Razer Barracuda X 2.4G
- ATK X1 V2 8K dongle
- KZZI K75 Lite 2.4 GHz receiver (only connection status)

## Run from source

Requires Python 3.12 or newer on Windows 10/11.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python run_tray.py
```

The tray menu has informational status entries, **Drivers monitored**, **Devices shown on icon**, **Refresh Now**, **Start with Windows**, and **Exit**. Use **Drivers monitored** to enable or disable tracking for each supported device. Disabled drivers are not polled and disappear from the status rows, but remain in **Drivers monitored** so they can be re-enabled. The selection is saved in the user settings. A one-shot hardware check prints the current state:

```powershell
python run_tray.py --once
```

For development diagnostics, use `python run_tray.py --debug`. This enables detailed logging; `python run_tray.py --once --debug` is useful for console-based HID troubleshooting.

## Build an executable

Install dependencies as above, then run:

```powershell
./build.ps1
```

The standalone one-file executable is written to `dist/ShowMeTheConnection.exe`; it bundles Python and HIDAPI, so users do not need Python. One-file packaging is convenient to distribute but has a short extraction step at startup and can trigger stricter antivirus scrutiny than a one-directory build. For a visible console during development, use `./build.ps1 -Console`.

Pushing to the `release` branch runs the Windows build and tests, then publishes a GitHub Release with the executable attached. Tags start at `v0.1.0` and increment the patch number on each successful release. The workflow needs repository Actions enabled and permission to write repository contents; its workflow token is granted that permission in the workflow file.

## Startup and exit

Choose **Start with Windows** in the tray menu to add or remove a per-user `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` entry. The preference is stored in `%APPDATA%\ShowMeTheConnection\settings.json`. Existing settings from `%APPDATA%\BarracudaTray` are read during migration. Right-click the icon and choose **Exit** to stop polling and close HID handles.

## Behavior and limitations

The app checks device connection about every four seconds and refreshes battery and charging about every 60 seconds. The Barracuda X integration uses only the documented PA reads for registers `20`, `21`, and `2A`, plus the verified Remote Mode toggle. The KZZI integration follows the read-only identity, online, and power requests identified in the bundled KZZI driver. Battery details are cleared after a confirmed disconnect. Transient communication failures keep the last known status visible while the monitor retries. Low battery notifications are omitted to keep dependencies and notification behavior simple.

For multiple devices, hovering over the tray icon shows the selected device names and battery percentages. The right-click menu shows a percentage in each device's row. **Devices shown on icon** chooses which enabled devices appear in the icon and tooltip, while **Drivers monitored** controls which devices are tracked.

## Adding another device

Device integrations live under `src/drivers/`. Put each model's VID/PID, interface, usage page, usage, and protocol/register details in its driver. The shared `src/hid_device.py` module only matches a driver's `HidDeviceMatch` and manages the generic HID handle. Implement the `DeviceDriver` contract (`key`, `display_name`, `read_connection()`, `read_details()`, and `close()`), then import the driver and add its factory to `_DRIVER_FACTORIES` in `src/registry.py`. `read_details()` may return `None` for battery or charging when a device does not report that value. The monitor keeps failures and polling timers independent per device; the tray creates a status submenu for each registered driver.

The `src` directory is the source root and contains the shared app modules plus `drivers/`. Launch the app through `run_tray.py`; monitoring, status presentation, and tray lifecycle remain device-agnostic.

The python scripts in the scripts folder are mainly for detecting devices. They are not used by the main project; they record how I capture HID interfaces.

For example, `scripts/detect_atk_hid.py` was used to detect the HID interface for ATK X1 V2 and can be a reference when adding devices or trying HID interfaces.

The KZZI K75 Lite took more investigation: I captured USB traffic with Wireshark and used IDA 9.4 with the REA MCP to reverse the official driver. Its read-only receiver identity now matches the K75 Lite profile, and the tray app includes support for it.

## Tests

The protocol and monitoring tests use mocked reports and devices and need no headset:

```powershell
$env:PYTHONPATH = 'src'
python -m unittest discover -s tests -v
```

## Troubleshooting

- Confirm Device Manager sees the original Razer receiver and that no other program is holding its HID interface open.
- The app does not replace drivers or require administrator privileges. Run `python run_tray.py --once --debug` to see discovery and protocol diagnostics.
- If Windows cannot open the handle, unplug and reconnect the receiver, close software that may be using it, and retry.
- A connected receiver can still report the headset as disconnected when the headset is powered off.

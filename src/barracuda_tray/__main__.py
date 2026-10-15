"""Application entry point."""

from __future__ import annotations

import argparse
import ctypes
import logging
import sys

from .hid_device import DeviceUnavailable, HeadsetDevice
from .monitor import Monitor


def main() -> int:
    parser = argparse.ArgumentParser(description="Razer Barracuda X 2.4 GHz tray battery monitor")
    parser.add_argument("--debug", action="store_true", help="enable diagnostic logging")
    parser.add_argument("--once", action="store_true", help="query once and print status")
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if args.once:
        device = HeadsetDevice()
        try:
            connected = device.read_connection()
            print("Razer Barracuda X 2.4")
            print(f"Connection: {'Connected' if connected else 'Disconnected'}")
            if connected:
                battery, charging = device.read_details()
                print(f"Battery: {battery}%")
                print(f"Charging: {'Yes' if charging else 'No'}")
            return 0
        except (DeviceUnavailable, OSError, TimeoutError, ValueError) as exc:
            print(f"Unable to read headset: {exc}")
            return 1
        finally:
            device.close()

    mutex = None
    kernel32 = None
    if sys.platform == "win32":
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.CreateMutexW.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p)
        kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
        mutex = kernel32.CreateMutexW(None, False, "Local\\RazerBarracudaTray.Monitor")
        if not mutex:
            logging.error("Could not create the single-instance mutex")
            return 1
        if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
            kernel32.CloseHandle(mutex)
            return 0
    from .tray import TrayApp
    app = TrayApp()
    if args.debug:
        # pystray's Windows backend may otherwise hide a console inherited at launch.
        logging.debug("Starting tray monitor")
    try:
        app.run()
    finally:
        if mutex:
            kernel32.CloseHandle(mutex)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

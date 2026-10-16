"""Application entry point."""

from __future__ import annotations

import argparse
import ctypes
import logging
import sys

import config
from monitor import ConnectionState, Monitor


def main() -> int:
    parser = argparse.ArgumentParser(description="ShowMeTheConnection device status tray monitor")
    parser.add_argument("--debug", action="store_true", help="enable diagnostic logging")
    parser.add_argument("--once", action="store_true", help="query once and print status")
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if args.once:
        settings = config.load_settings()
        monitor = Monitor(disabled_drivers=settings.get("disabled_drivers", []))
        try:
            monitor.poll_once(force_details=True)
            states = monitor.states
            for index, state in enumerate(states):
                if index:
                    print()
                print(state.device_name)
                print(f"Connection: {state.connection.value}")
                if state.battery is not None:
                    print(f"Battery: {state.battery}%")
                if state.charging is not None:
                    print(f"Charging: {'Yes' if state.charging else 'No'}")
            return 1 if any(state.connection in (ConnectionState.UNKNOWN, ConnectionState.RECEIVER_UNAVAILABLE)
                            for state in states) else 0
        finally:
            for driver in monitor.drivers:
                driver.close()

    mutex = None
    kernel32 = None
    if sys.platform == "win32":
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.CreateMutexW.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p)
        kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
        mutex = kernel32.CreateMutexW(None, False, "Local\\ShowMeTheConnection.Monitor")
        if not mutex:
            logging.error("Could not create the single-instance mutex")
            return 1
        if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
            kernel32.CloseHandle(mutex)
            return 0
    from tray import TrayApp
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

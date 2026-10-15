"""Hardware identity and verified PA protocol for Barracuda X 2.4."""

from __future__ import annotations

import logging
import threading
import time

from ..hid_device import HidDevice, HidDeviceMatch
from ..protocol import make_read_command, make_remote_mode, parse_register_response

log = logging.getLogger(__name__)

# Receiver identity belongs to this integration, not the shared HID transport.
RAZER_BARRACUDA_X_MATCH = HidDeviceMatch(
    vendor_id=0x1532,
    product_id=0x0550,
    interface_number=3,
    usage_page=0xFF00,
    usage=0x0001,
    display_name="Razer Barracuda X 2.4",
)

# Only these verified read-only registers are queried by this driver.
REG_CONNECTION = 0x20
REG_BATTERY = 0x21
REG_CHARGING = 0x2A


class BarracudaXDriver:
    key = "razer-barracuda-x-24"
    display_name = RAZER_BARRACUDA_X_MATCH.display_name

    def __init__(self, hid_device: HidDevice | None = None, sleeper=time.sleep):
        self.hid = hid_device or HidDevice(RAZER_BARRACUDA_X_MATCH)
        self._sleeper = sleeper
        self._lock = threading.RLock()

    def _read_register(self, register: int) -> int:
        with self._lock:
            try:
                self.hid.write(make_remote_mode(True))
                # The verified remote-mode acknowledgement is often absent.
                try:
                    self.hid.read(64, 15)
                except OSError:
                    log.debug("Remote mode acknowledgement unavailable", exc_info=True)
                self._sleeper(0.005)
                self.hid.write(make_read_command(register))
                self._sleeper(0.005)
                deadline = time.monotonic() + 0.25
                while time.monotonic() < deadline:
                    report = self.hid.read(64, 50)
                    if not report:
                        self._sleeper(0.005)
                        continue
                    try:
                        value = parse_register_response(report, register)
                    except ValueError:
                        log.debug("Ignoring unrelated HID report for 0x%02X", register)
                        continue
                    self._validate_value(register, value)
                    return value
                raise TimeoutError(f"Timed out reading register 0x{register:02X}")
            finally:
                if self.hid.is_open:
                    try:
                        self.hid.write(make_remote_mode(False))
                    except OSError:
                        log.debug("Could not restore local mode", exc_info=True)

    @staticmethod
    def _validate_value(register: int, value: int) -> None:
        if register in (REG_CONNECTION, REG_CHARGING) and value not in (0, 1):
            raise ValueError(f"Invalid value for register 0x{register:02X}")
        if register == REG_BATTERY and not 0 <= value <= 100:
            raise ValueError("Invalid battery percentage")

    def read_connection(self) -> bool:
        return bool(self._read_register(REG_CONNECTION))

    def read_details(self) -> tuple[int, bool]:
        return self._read_register(REG_BATTERY), bool(self._read_register(REG_CHARGING))

    def close(self) -> None:
        self.hid.close()

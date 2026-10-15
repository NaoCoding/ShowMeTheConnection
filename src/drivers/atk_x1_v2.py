"""Read-only HID support for the ATK X1 Ultimate V2 with its 8K dongle."""

from __future__ import annotations

import threading

from hid_device import HidDevice, HidDeviceMatch

ATK_X1_V2_MATCH = HidDeviceMatch(
    vendor_id=0x373B,
    product_id=0x11D9,
    interface_number=1,
    usage_page=0xFF02,
    usage=0x0002,
    display_name="ATK X1 V2 (8K dongle)",
)

REPORT_ID = 0x08
REPORT_SIZE = 17
CMD_GET_BATTERY = 0x04


class ATKX1V2Driver:
    """Read battery telemetry from the ATK X1 8K dongle's config collection.

    The battery command is read-only. This dongle only answers it while the
    mouse is awake, so a valid reply is also the best available connection
    check. Its secondary flag is documented as wired state, not charging, so
    this driver leaves charging unknown.
    """

    key = "atk-x1-v2"
    display_name = ATK_X1_V2_MATCH.display_name

    def __init__(self, hid_device: HidDevice | None = None):
        self.hid = hid_device or HidDevice(ATK_X1_V2_MATCH)
        self._lock = threading.RLock()
        self._last_battery: int | None = None

    @staticmethod
    def _battery_request() -> bytes:
        report = bytearray(REPORT_SIZE)
        report[0] = REPORT_ID
        report[1] = CMD_GET_BATTERY
        report[16] = (0x55 - (sum(report[:16]) & 0xFF)) & 0xFF
        return bytes(report)

    def _read_battery(self) -> int:
        with self._lock:
            self.hid.open()
            written = self.hid.write(self._battery_request())
            if written < REPORT_SIZE:
                raise OSError(f"Short ATK HID write ({written} of {REPORT_SIZE} bytes)")

            deadline_reads = 8
            for _ in range(deadline_reads):
                report = self.hid.read(REPORT_SIZE, 50)
                if not report:
                    continue
                raw = bytes(report)
                if len(raw) < REPORT_SIZE or raw[0] != REPORT_ID or raw[1] != CMD_GET_BATTERY:
                    continue
                checksum = (0x55 - (sum(raw[:16]) & 0xFF)) & 0xFF
                if raw[16] != checksum:
                    raise ValueError("Invalid ATK battery report checksum")
                battery = raw[6]
                if not 0 <= battery <= 100:
                    raise ValueError(f"Invalid ATK battery percentage: {battery}")
                self._last_battery = battery
                return battery

            raise TimeoutError("Timed out reading ATK battery; the mouse may be asleep")

    def read_connection(self) -> bool:
        self._read_battery()
        return True

    def read_details(self) -> tuple[int | None, bool | None]:
        battery = self._last_battery
        if battery is None:
            battery = self._read_battery()
        return battery, None

    def close(self) -> None:
        self.hid.close()
        self._last_battery = None

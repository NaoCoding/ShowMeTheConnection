"""Read-only support for the KZZI K75 Lite 2.4 GHz receiver."""

from __future__ import annotations

import logging
import threading
import time

from hid_device import HidDevice, HidDeviceMatch

log = logging.getLogger(__name__)

KZZI_K75_LITE_MATCH = HidDeviceMatch(
    vendor_id=0x3554,
    product_id=0xFA09,
    interface_number=1,
    usage_page=0xFF02,
    usage=0x0002,
    display_name="KZZI K75 Lite (2.4 GHz)",
)

REPORT_ID = 0x13
REPORT_SIZE = 20
CMD_GET_ONLINE = 0x07
CMD_GET_POWER = 0x4A
CMD_GET_IDENTITY = 0x05
K75_LITE_IDENTITY = bytes((0x03, 0x00, 0x00, 0x00, 0x01, 0x44))


class KZZIK75LiteDriver:
    """Poll the receiver's identity, wireless-link status, and power report.

    The packet layout and commands are taken from KZZI's bundled DeviceDriver
    code. Identity is checked against the K75 Lite profile before reporting a
    connection, so other products using this receiver VID/PID are not claimed.
    """

    key = "kzzi-k75-lite"
    display_name = KZZI_K75_LITE_MATCH.display_name

    def __init__(self, hid_device: HidDevice | None = None, sleeper=time.sleep):
        self.hid = hid_device or HidDevice(KZZI_K75_LITE_MATCH)
        self._sleeper = sleeper
        self._lock = threading.RLock()
        self._identity_matches: bool | None = None
        self._last_details: tuple[int | None, bool | None] | None = None

    @staticmethod
    def _request(command: int, subcommand: int = 0) -> bytes:
        report = bytearray(REPORT_SIZE)
        report[0] = REPORT_ID
        report[1] = command
        report[2] = 0x01
        report[4] = subcommand
        report[19] = sum(report[:19]) & 0xFF
        return bytes(report)

    def _command(self, command: int, subcommand: int, size: int) -> bytes:
        """Send one 3632-family request and collect its response packets."""
        request = self._request(command, subcommand)
        for attempt in range(3):
            with self._lock:
                self.hid.open()
                written = self.hid.write(request)
                if written < REPORT_SIZE:
                    raise OSError(f"Short KZZI HID write ({written} of {REPORT_SIZE} bytes)")

                deadline = time.monotonic() + 0.35
                packet_count: int | None = None
                packets: dict[int, bytes] = {}
                while time.monotonic() < deadline:
                    timeout_ms = max(1, min(100, int((deadline - time.monotonic()) * 1000)))
                    report = self.hid.read(REPORT_SIZE, timeout_ms)
                    if not report:
                        continue
                    raw = bytes(report)
                    if len(raw) < REPORT_SIZE or raw[0] != REPORT_ID:
                        continue
                    if raw[1] & 0x7F != command:
                        continue
                    if raw[1] & 0x80:
                        log.debug("KZZI receiver rejected command 0x%02X", command)
                        break

                    count = raw[2] & 0x7F
                    index = raw[3]
                    data_length = raw[4] & 0x0F
                    if not count or index >= count or data_length > 14:
                        continue
                    if packet_count is not None and count != packet_count:
                        continue
                    packet_count = count
                    packets.setdefault(index, raw[5:5 + data_length])
                    if len(packets) == packet_count:
                        payload = b"".join(packets[i] for i in range(packet_count))
                        if len(payload) < size:
                            raise ValueError(
                                f"Truncated KZZI response for command 0x{command:02X}"
                            )
                        return payload[:size]
            if attempt < 2:
                self._sleeper(0.01)
        raise TimeoutError(f"Timed out reading KZZI command 0x{command:02X}")

    def _matches_k75_lite(self) -> bool:
        if self._identity_matches is None:
            identity = self._command(CMD_GET_IDENTITY, 0x06, len(K75_LITE_IDENTITY))
            self._identity_matches = identity == K75_LITE_IDENTITY
            if not self._identity_matches:
                log.debug("KZZI receiver identity did not match the K75 Lite profile")
        return self._identity_matches

    def read_connection(self) -> bool:
        if not self._matches_k75_lite():
            return False
        online = self._command(CMD_GET_ONLINE, 0x00, 1)[0]
        # The bundled driver treats zero as offline and any nonzero value as
        # online; it does not constrain this status byte to a Boolean value.
        return online != 0

    def read_details(self) -> tuple[int | None, bool | None]:
        try:
            power = self._command(CMD_GET_POWER, 0x00, 2)
        except TimeoutError:
            log.debug("KZZI receiver did not answer the power query")
            return self._last_details or (None, None)

        log.debug("KZZI power payload: %s", power.hex(" "))
        battery = power[0] if power[0] <= 100 else None
        charging = bool(power[1]) if power[1] in (0, 1) else None
        if battery is None or charging is None:
            log.debug("KZZI power values are outside the known range: %s", tuple(power))
        self._last_details = (battery, charging)
        return self._last_details

    def close(self) -> None:
        self.hid.close()
        self._identity_matches = None
        self._last_details = None

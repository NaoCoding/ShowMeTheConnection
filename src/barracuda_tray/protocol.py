"""Verified Razer PA protocol commands and response parsing."""

from __future__ import annotations

REPORT_SIZE = 64
REPORT_ID = 0x02
REG_CONNECTION = 0x20
REG_BATTERY = 0x21
REG_CHARGING = 0x2A
READABLE_REGISTERS = {REG_CONNECTION, REG_BATTERY, REG_CHARGING}


class ProtocolError(ValueError):
    """A HID response was malformed or did not contain a live value."""


def make_read_command(register: int) -> bytes:
    if register not in READABLE_REGISTERS:
        raise ValueError(f"Unsupported read-only register: 0x{register:02X}")
    packet = bytearray(REPORT_SIZE)
    packet[0:3] = bytes((REPORT_ID, 0x80, 0x08))
    packet[5:7] = b"PA"
    packet[7] = 0x08
    packet[9] = 0x03
    packet[10] = register
    return bytes(packet)


def make_remote_mode(enabled: bool) -> bytes:
    packet = bytearray(REPORT_SIZE)
    packet[0:3] = bytes((REPORT_ID, 0x80, 0x07))
    packet[5:7] = b"PA"
    packet[7] = 0x0E
    packet[9] = 0x02
    packet[10] = 0xE1
    packet[11] = int(enabled)
    return bytes(packet)


def parse_register_response(report: bytes | bytearray, register: int) -> int:
    """Find and validate the requested live PA register subframe."""
    if register not in READABLE_REGISTERS:
        raise ValueError(f"Unsupported read-only register: 0x{register:02X}")
    data = bytes(report)
    if len(data) < 16:
        raise ProtocolError("Truncated HID report")
    if data[0] != REPORT_ID or data[1] != 0x0E or data[2:4] != b"PI" or data[4] != 0x08:
        raise ProtocolError("Invalid PA response header")

    # The headset has been observed to use markers 00, 01, and 02.
    for offset in range(9, len(data) - 6):
        marker, length, reserved, found_register, major, minor, value = data[offset:offset + 7]
        if marker not in (0x00, 0x01, 0x02) or length != 0x04 or reserved != 0:
            continue
        if found_register != register:
            continue
        if major != 0x01:
            raise ProtocolError(f"Stale or unsupported response version: {major}.{minor}")
        if register == REG_CONNECTION and value not in (0, 1):
            raise ProtocolError("Invalid connection status")
        if register == REG_BATTERY and not 0 <= value <= 100:
            raise ProtocolError("Invalid battery percentage")
        if register == REG_CHARGING and value not in (0, 1):
            raise ProtocolError("Invalid charging status")
        return value
    raise ProtocolError(f"Response did not contain register 0x{register:02X}")

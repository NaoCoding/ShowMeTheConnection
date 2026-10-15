"""Enumerate ATK HID interfaces and optionally query read-only mouse telemetry.

The telemetry probe uses the publicly documented BitMouse commands for
battery, charging, receiver link state, and mouse identity. It does not change
mouse settings or pairing state.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Any


ATK_VENDOR_IDS = (0x373B, 0x3554)
BITMOUSE_USAGE_PAGE = 0xFF05
BITMOUSE_USAGE = 0x0001
X1_CONFIG_USAGE_PAGE = 0xFF02
X1_CONFIG_USAGE = 0x0002
REPORT_ID = 0x08
REPORT_BODY_SIZE = 63
PACKET_CLASS = 0x72
PARAM_LENGTHS = {0x07: 2, 0x0F: 2, 0x81: 3, 0x89: 8, 0x4A: 8}


def _hex(value: int | None, width: int = 4) -> str:
    return "unknown" if value is None else f"0x{value:0{width}X}"


def _packet(command: int, target: int, payload: bytes = b"") -> bytes:
    packet = bytearray(REPORT_BODY_SIZE)
    packet[1] = PACKET_CLASS
    packet[2] = PARAM_LENGTHS[command]
    packet[3] = 0
    packet[4] = target
    packet[5] = command
    packet[6] = len(payload)
    packet[7:7 + len(payload)] = payload
    packet[0] = sum(packet[1:]) & 0xFF
    return bytes(packet)


def _normalize_report(report: list[int] | bytes, command: int) -> bytes | None:
    """Return the 63-byte packet body from hidapi's report representation."""
    raw = bytes(report)
    # hidapi may include the nonzero report ID in the returned buffer. Some
    # backends also expose the body without it, so accept both forms.
    candidates = [raw, raw[1:], raw[2:]]
    for candidate in candidates:
        if len(candidate) < REPORT_BODY_SIZE:
            continue
        body = candidate[:REPORT_BODY_SIZE]
        if body[1] == PACKET_CLASS and body[5] == command:
            if body[0] == (sum(body[1:]) & 0xFF):
                return body
    return None


def _exchange(handle: Any, command: int, target: int, payload: bytes = b"") -> bytes:
    request = _packet(command, target, payload)
    last_reports: list[bytes] = []
    for attempt in range(3):
        # hidapi expects the report ID as the first byte of an output report.
        written = handle.write(bytes((REPORT_ID,)) + request)
        if written < REPORT_BODY_SIZE:
            raise OSError(f"short HID write ({written} bytes)")
        deadline = time.monotonic() + 0.5
        while time.monotonic() < deadline:
            report = handle.read(REPORT_BODY_SIZE + 1, 100)
            if not report:
                continue
            last_reports.append(bytes(report))
            reply = _normalize_report(report, command)
            if reply is not None:
                if reply[2] == 0xFF:
                    raise ValueError(f"device returned error for command 0x{command:02X}")
                return reply
        if attempt < 2:
            time.sleep(0.05)
    last = "; ".join(report.hex(" ") for report in last_reports[-3:]) or "no reports"
    raise TimeoutError(f"no valid reply for command 0x{command:02X}; recent reports: {last}")


def _data(reply: bytes) -> bytes:
    length = min(reply[6], REPORT_BODY_SIZE - 7)
    return reply[7:7 + length]


def _query(handle: Any, command: int, target: int, label: str) -> bytes | None:
    try:
        reply = _exchange(handle, command, target)
    except (OSError, TimeoutError, ValueError) as exc:
        print(f"    {label}: unavailable ({exc})")
        return None
    value = _data(reply)
    print(f"    {label}: {value.hex(' ') if value else '(empty)'}  [report: {reply.hex(' ')}]")
    return value


def _probe(handle: Any) -> None:
    print("  Read-only BitMouse telemetry probe:")
    # A receiver answers 0x81 with its mouse link state. If this command is
    # unsupported, try the same telemetry commands against a directly wired
    # mouse (target 0).
    linked = _query(handle, 0x81, 0, "receiver link (0x81)")
    if linked is not None:
        target = 1
        print(f"    receiver reports mouse connected: {bool(linked and linked[0])}")
        _query(handle, 0x89, target, "mouse identity (0x89)")
    else:
        target = 0
        _query(handle, 0x4A, target, "device identity (0x4A)")

    battery = _query(handle, 0x07, target, "battery percent (0x07)")
    if battery and 0 <= battery[0] <= 100:
        print(f"    decoded battery: {battery[0]}%")
    charging = _query(handle, 0x0F, target, "charging state (0x0F)")
    if charging:
        print(f"    decoded charging: {bool(charging[0])}")


def _x1_battery_probe(handle: Any) -> None:
    """Query battery on the X1 8K dongle's 17-byte configuration report."""
    packet = bytearray(17)
    packet[0] = REPORT_ID
    packet[1] = 0x04  # Read battery; unlike EEPROM commands, this is read-only.
    packet[16] = (0x55 - sum(packet[:16])) & 0xFF
    print("  Read-only X1 battery query (configuration command 0x04):")
    for attempt in range(3):
        try:
            written = handle.write(packet)
            if written < len(packet):
                raise OSError(f"short HID write ({written} of {len(packet)} bytes)")
            response = handle.read(17, 500)
        except OSError as exc:
            print(f"    query failed: {exc}")
            return
        if not response:
            if attempt < 2:
                continue
            print("    no reply (mouse may be asleep, or another app has the interface open)")
            return
        report = bytes(response)
        print(f"    raw reply: {report.hex(' ')}")
        if len(report) < 8:
            print("    reply is too short to decode battery data")
            return
        if report[0] == REPORT_ID and report[1] == 0x04:
            print(f"    decoded battery: {report[6]}%")
            print(f"    decoded wired/charging flag: {report[7]}")
            expected_checksum = (0x55 - sum(report[:16])) & 0xFF if len(report) >= 17 else None
            if expected_checksum is not None:
                print(f"    reply checksum: {'ok' if report[16] == expected_checksum else 'mismatch'}")
            return
        print("    reply did not echo the battery command")
        return


def _describe(info: dict[str, Any]) -> None:
    print(f"  VID:PID: {_hex(info.get('vendor_id'))}:{_hex(info.get('product_id') or 0)}")
    print(f"  product: {info.get('product_string') or '(not reported)'}")
    print(f"  manufacturer: {info.get('manufacturer_string') or '(not reported)'}")
    print(f"  interface: {info.get('interface_number', 'unknown')}")
    print(f"  usage page / usage: {_hex(info.get('usage_page'))} / {_hex(info.get('usage'))}")
    path = info.get("path")
    print(f"  path: {os.fsdecode(path) if path is not None else '(not reported)'}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Find ATK/VXE HID interfaces and query read-only X1 V2 telemetry."
    )
    parser.add_argument("--vid", type=lambda value: int(value, 0), help="limit to a vendor ID, e.g. 0x373B")
    parser.add_argument("--pid", type=lambda value: int(value, 0), help="limit to a product ID, e.g. 0x11D9")
    parser.add_argument("--path", help="probe only this HID path (copy it from the listing)")
    parser.add_argument("--list-only", action="store_true", help="enumerate interfaces without opening any")
    args = parser.parse_args()

    try:
        import hid
    except ImportError:
        print("hidapi is missing. Install project dependencies with: python -m pip install -r requirements.txt", file=sys.stderr)
        return 2

    vids = [args.vid] if args.vid is not None else list(ATK_VENDOR_IDS)
    matches: list[dict[str, Any]] = []
    for vid in vids:
        matches.extend(hid.enumerate(vid, args.pid if args.pid is not None else 0))
    if args.path is not None:
        matches = [item for item in matches if os.fsdecode(item.get("path", b"")) == args.path]

    if not matches:
        print("No matching ATK/VXE HID interfaces found.")
        print("Check the USB receiver/cable, or pass --vid and --pid to select another device.")
        return 1

    print(f"Found {len(matches)} matching HID interface(s):")
    for index, info in enumerate(matches, 1):
        print(f"\n[{index}]")
        _describe(info)
        if args.list_only:
            continue
        if (info.get("vendor_id"), info.get("product_id")) == (0x373B, 0x11D9) and (
            info.get("usage_page"), info.get("usage")
        ) == (X1_CONFIG_USAGE_PAGE, X1_CONFIG_USAGE):
            device = hid.device()
            try:
                device.open_path(info["path"])
                _x1_battery_probe(device)
            except Exception as exc:
                print(f"  could not probe interface: {type(exc).__name__}: {exc}")
            finally:
                device.close()
            continue
        if info.get("usage_page") != BITMOUSE_USAGE_PAGE or info.get("usage") != BITMOUSE_USAGE:
            print("  skipped: not the documented BitMouse control collection (FF05/0001)")
            continue
        device = hid.device()
        try:
            device.open_path(info["path"])
            _probe(device)
        except Exception as exc:
            print(f"  could not probe interface: {type(exc).__name__}: {exc}")
        finally:
            device.close()
    print("\nIf the device is in use by ATK HUB or another tool, close that app and try again.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""HID discovery and serialized request/response communication."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

from .protocol import (
    REG_BATTERY, REG_CHARGING, REG_CONNECTION, make_read_command,
    make_remote_mode, parse_register_response,
)

log = logging.getLogger(__name__)
VID, PID, INTERFACE, USAGE_PAGE, USAGE = 0x1532, 0x0550, 3, 0xFF00, 0x0001


class DeviceUnavailable(OSError):
    """The expected receiver could not be found or contacted."""


@dataclass(frozen=True)
class HeadsetStatus:
    connected: bool
    battery: int | None = None
    charging: bool | None = None


def find_device(hid_module):
    for info in hid_module.enumerate(VID, PID):
        if all((info.get("vendor_id") == VID,
                info.get("product_id") == PID,
                info.get("interface_number") == INTERFACE,
                info.get("usage_page") == USAGE_PAGE,
                info.get("usage") == USAGE)):
            return info
    return None


class HeadsetDevice:
    """One handle with a lock so callers cannot overlap protocol exchanges."""

    def __init__(self, hid_module=None, sleeper=time.sleep):
        self._hid = hid_module
        self._sleeper = sleeper
        self._handle = None
        self._lock = threading.RLock()

    def _module(self):
        if self._hid is None:
            try:
                import hid
            except ImportError as exc:
                raise DeviceUnavailable("Install hidapi to access the receiver") from exc
            self._hid = hid
        return self._hid

    def open(self) -> None:
        with self._lock:
            if self._handle is not None:
                return
            info = find_device(self._module())
            if info is None:
                raise DeviceUnavailable("Razer Barracuda X receiver unavailable")
            handle = self._module().device()
            try:
                handle.open_path(info["path"])
                self._handle = handle
            except Exception:
                try:
                    handle.close()
                except Exception:
                    pass
                raise

    def _exchange(self, register: int) -> int:
        self.open()
        handle = self._handle
        handle.write(make_remote_mode(True))
        # Remote mode acknowledgement is optional; consume it when promptly available.
        try:
            handle.read(64, 15)
        except OSError:
            log.debug("Remote mode acknowledgement unavailable", exc_info=True)
        self._sleeper(0.005)
        handle.write(make_read_command(register))
        self._sleeper(0.005)
        deadline = time.monotonic() + 0.25
        while time.monotonic() < deadline:
            try:
                report = handle.read(64, 50)
            except OSError:
                raise
            if not report:
                self._sleeper(0.005)
                continue
            try:
                return parse_register_response(report, register)
            except ValueError:
                # Ignore stale/unrelated reports, but continue briefly for a live reply.
                log.debug("Ignoring unrelated HID report for 0x%02X", register)
        raise TimeoutError(f"Timed out reading register 0x{register:02X}")

    def read_register(self, register: int) -> int:
        with self._lock:
            try:
                return self._exchange(register)
            finally:
                if self._handle is not None:
                    try:
                        self._handle.write(make_remote_mode(False))
                    except OSError:
                        log.debug("Could not restore local mode", exc_info=True)

    def read_connection(self) -> bool:
        return bool(self.read_register(REG_CONNECTION))

    def read_details(self) -> tuple[int, bool]:
        return self.read_register(REG_BATTERY), bool(self.read_register(REG_CHARGING))

    def close(self) -> None:
        with self._lock:
            handle, self._handle = self._handle, None
            if handle is not None:
                try:
                    handle.close()
                except OSError:
                    log.debug("Error closing HID handle", exc_info=True)

"""Generic HID discovery and handle lifecycle; device protocols belong in drivers."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

log = logging.getLogger(__name__)


class DeviceUnavailable(OSError):
    """A matching HID interface could not be found or opened."""


@dataclass(frozen=True)
class HidDeviceMatch:
    """HID collection identity supplied by a device-specific driver."""

    vendor_id: int
    product_id: int
    interface_number: int
    usage_page: int
    usage: int
    display_name: str


def find_device(hid_module, match: HidDeviceMatch):
    """Return the exact HID collection requested by a driver."""
    for info in hid_module.enumerate(match.vendor_id, match.product_id):
        if (info.get("vendor_id") == match.vendor_id
                and info.get("product_id") == match.product_id
                and info.get("interface_number") == match.interface_number
                and info.get("usage_page") == match.usage_page
                and info.get("usage") == match.usage):
            return info
    return None


class HidDevice:
    """Owns one generic HID handle. It has no knowledge of reports or registers."""

    def __init__(self, match: HidDeviceMatch, hid_module=None):
        self.match = match
        self._hid = hid_module
        self._handle = None
        self._lock = threading.RLock()

    @property
    def is_open(self) -> bool:
        return self._handle is not None

    def _module(self):
        if self._hid is None:
            try:
                import hid
            except ImportError as exc:
                raise DeviceUnavailable("Install hidapi to access the selected device") from exc
            self._hid = hid
        return self._hid

    def open(self) -> None:
        with self._lock:
            if self._handle is not None:
                return
            module = self._module()
            info = find_device(module, self.match)
            if info is None:
                raise DeviceUnavailable(f"{self.match.display_name} receiver unavailable")
            handle = module.device()
            try:
                handle.open_path(info["path"])
                self._handle = handle
            except Exception:
                try:
                    handle.close()
                except Exception:
                    pass
                raise

    def write(self, report: bytes) -> int:
        with self._lock:
            self.open()
            return self._handle.write(report)

    def read(self, size: int, timeout_ms: int):
        with self._lock:
            self.open()
            return self._handle.read(size, timeout_ms)

    def close(self) -> None:
        with self._lock:
            handle, self._handle = self._handle, None
            if handle is not None:
                try:
                    handle.close()
                except OSError:
                    log.debug("Error closing HID handle", exc_info=True)

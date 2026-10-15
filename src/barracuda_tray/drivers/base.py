"""Contract implemented by each supported headset/device integration."""

from __future__ import annotations

from typing import Protocol


class DeviceDriver(Protocol):
    key: str
    display_name: str

    def read_connection(self) -> bool: ...
    def read_details(self) -> tuple[int | None, bool | None]: ...
    def close(self) -> None: ...

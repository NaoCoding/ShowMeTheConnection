"""Registry for device integrations; add new driver factories here."""

from __future__ import annotations

from collections.abc import Callable

from drivers.atk_x1_v2 import ATKX1V2Driver
from drivers.barracuda_x import BarracudaXDriver
from drivers.base import DeviceDriver
from drivers.kzzi_k75_lite import KZZIK75LiteDriver

DriverFactory = Callable[[], DeviceDriver]
_DRIVER_FACTORIES: list[DriverFactory] = [BarracudaXDriver, ATKX1V2Driver, KZZIK75LiteDriver]


def register_driver(factory: DriverFactory) -> None:
    """Register another supported device driver once during app startup."""
    if factory not in _DRIVER_FACTORIES:
        _DRIVER_FACTORIES.append(factory)


def create_drivers() -> list[DeviceDriver]:
    """Create an independent monitor instance for each registered device type."""
    return [factory() for factory in _DRIVER_FACTORIES]

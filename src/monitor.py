"""Background poller that publishes immutable headset snapshots."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable

from drivers.base import DeviceDriver
from hid_device import DeviceUnavailable
from registry import create_drivers

log = logging.getLogger(__name__)


class _InjectedDeviceDriver:
    """Adapter for the original monitor(device=...) test/integration API."""

    key = "injected-device"
    display_name = "Injected device"

    def __init__(self, device):
        self.device = device

    def read_connection(self):
        return self.device.read_connection()

    def read_details(self):
        return self.device.read_details()

    def close(self):
        self.device.close()


class ConnectionState(str, Enum):
    UNKNOWN = "Unknown"
    CONNECTED = "Connected"
    DISCONNECTED = "Disconnected"
    RECEIVER_UNAVAILABLE = "Receiver unavailable"


@dataclass(frozen=True)
class MonitorState:
    connection: ConnectionState = ConnectionState.UNKNOWN
    battery: int | None = None
    charging: bool | None = None
    updated_at: float | None = None
    device_key: str = "unknown-device"
    device_name: str = "Unknown device"


class Monitor:
    def __init__(self, device=None, on_change: Callable[[tuple[MonitorState, ...]], None] | None = None,
                 connection_interval: float = 4.0, battery_interval: float = 60.0,
                 drivers: list[DeviceDriver] | None = None):
        if drivers is not None:
            self.drivers = list(drivers)
        elif device is not None:
            # Keep the original constructor useful for tests and small integrations.
            self.drivers = [_InjectedDeviceDriver(device)]
        else:
            self.drivers = create_drivers()
        keys = [driver.key for driver in self.drivers]
        if len(keys) != len(set(keys)):
            raise ValueError("Each registered device driver must have a unique key")
        self._states = {driver.key: MonitorState(device_key=driver.key, device_name=driver.display_name)
                        for driver in self.drivers}
        self.on_change = on_change or (lambda _state: None)
        self.connection_interval = connection_interval
        self.battery_interval = battery_interval
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._refresh = threading.Event()
        self._thread: threading.Thread | None = None
        self._failures = {driver.key: 0 for driver in self.drivers}
        self._last_battery = {driver.key: 0.0 for driver in self.drivers}

    @property
    def state(self) -> MonitorState:
        with self._lock:
            return next(iter(self._states.values()), MonitorState())

    @property
    def states(self) -> tuple[MonitorState, ...]:
        with self._lock:
            return tuple(self._states[driver.key] for driver in self.drivers)

    def _publish(self, driver: DeviceDriver, state: MonitorState) -> None:
        with self._lock:
            self._states[driver.key] = state
            states = tuple(self._states[item.key] for item in self.drivers)
        self.on_change(states)

    def refresh_now(self) -> None:
        self._refresh.set()

    def poll_once(self, force_details: bool = False) -> MonitorState:
        for driver in self.drivers:
            previous = self._states[driver.key]
            try:
                connected = driver.read_connection()
                self._failures[driver.key] = 0
                if not connected:
                    state = MonitorState(ConnectionState.DISCONNECTED, updated_at=time.time(),
                                         device_key=driver.key, device_name=driver.display_name)
                    self._last_battery[driver.key] = 0
                else:
                    battery, charging = previous.battery, previous.charging
                    if force_details or previous.connection != ConnectionState.CONNECTED or time.monotonic() - self._last_battery[driver.key] >= self.battery_interval:
                        battery, charging = driver.read_details()
                        self._last_battery[driver.key] = time.monotonic()
                    state = MonitorState(ConnectionState.CONNECTED, battery, charging, time.time(), driver.key, driver.display_name)
                self._publish(driver, state)
            except DeviceUnavailable:
                driver.close()
                self._last_battery[driver.key] = 0
                self._publish(driver, MonitorState(ConnectionState.RECEIVER_UNAVAILABLE, updated_at=time.time(),
                                                  device_key=driver.key, device_name=driver.display_name))
            except (OSError, TimeoutError, ValueError) as exc:
                self._failures[driver.key] += 1
                failures = self._failures[driver.key]
                log.debug("%s poll failed (%d): %s", driver.display_name, failures, exc)
                if failures >= 2:
                    driver.close()
                    # Keep the last successful snapshot visible while the device is
                    # temporarily unreadable. Publishing UNKNOWN here discards the
                    # useful connection and battery values and makes the tray flicker.
        return self.state

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="BarracudaMonitor", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        first = True
        while not self._stop.is_set():
            self._refresh.clear()
            self.poll_once(force_details=first)
            first = False
            self._refresh.wait(self.connection_interval)
        for driver in self.drivers:
            driver.close()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        self._refresh.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout)
        if not self._thread or not self._thread.is_alive():
            for driver in self.drivers:
                driver.close()

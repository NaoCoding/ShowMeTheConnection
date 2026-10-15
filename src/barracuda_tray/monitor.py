"""Background poller that publishes immutable headset snapshots."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable

from .hid_device import DeviceUnavailable, HeadsetDevice

log = logging.getLogger(__name__)


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


class Monitor:
    def __init__(self, device: HeadsetDevice | None = None, on_change: Callable[[MonitorState], None] | None = None,
                 connection_interval: float = 4.0, battery_interval: float = 30.0):
        self.device = device or HeadsetDevice()
        self.on_change = on_change or (lambda _state: None)
        self.connection_interval = connection_interval
        self.battery_interval = battery_interval
        self._state = MonitorState()
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._refresh = threading.Event()
        self._thread: threading.Thread | None = None
        self._failures = 0
        self._last_battery = 0.0

    @property
    def state(self) -> MonitorState:
        with self._lock:
            return self._state

    def _publish(self, state: MonitorState) -> None:
        with self._lock:
            self._state = state
        self.on_change(state)

    def refresh_now(self) -> None:
        self._refresh.set()

    def poll_once(self, force_details: bool = False) -> MonitorState:
        try:
            connected = self.device.read_connection()
            self._failures = 0
            if not connected:
                self._publish(MonitorState(ConnectionState.DISCONNECTED, updated_at=time.time()))
                self._last_battery = 0
            else:
                previous = self.state
                battery, charging = previous.battery, previous.charging
                if force_details or previous.connection != ConnectionState.CONNECTED or time.monotonic() - self._last_battery >= self.battery_interval:
                    battery, charging = self.device.read_details()
                    self._last_battery = time.monotonic()
                self._publish(MonitorState(ConnectionState.CONNECTED, battery, charging, time.time()))
        except DeviceUnavailable:
            self.device.close()
            self._publish(MonitorState(ConnectionState.RECEIVER_UNAVAILABLE, updated_at=time.time()))
            self._last_battery = 0
        except (OSError, TimeoutError, ValueError) as exc:
            self._failures += 1
            log.debug("Headset poll failed (%d): %s", self._failures, exc)
            if self._failures >= 2:
                self._publish(MonitorState(ConnectionState.UNKNOWN, updated_at=time.time()))
                self.device.close()
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
        self.device.close()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        self._refresh.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout)
        if not self._thread or not self._thread.is_alive():
            self.device.close()

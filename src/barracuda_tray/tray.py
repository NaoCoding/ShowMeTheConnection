"""pystray front end; all HID work remains on the monitor thread."""

from __future__ import annotations

import logging
import threading

import pystray
from pystray import MenuItem

from . import config
from .icons import make_icon
from .monitor import ConnectionState, Monitor, MonitorState

log = logging.getLogger(__name__)


class TrayApp:
    def __init__(self, monitor: Monitor | None = None):
        self.settings = config.load_settings()
        self.monitor = monitor or Monitor(on_change=self._state_changed)
        self.monitor.on_change = self._state_changed
        self._lock = threading.RLock()
        self._states = self.monitor.states
        self._state = self._states[0] if self._states else self.monitor.state
        self._stopping = False
        self.icon = pystray.Icon("BarracudaTray", make_icon(self._state), "Razer Barracuda X - Unknown", self._menu())

    def _menu(self):
        items = []
        for state in self._states:
            key = state.device_key
            items.append(MenuItem(
                state.device_name,
                pystray.Menu(
                    MenuItem(lambda _item, device_key=key: self._device_status(device_key),
                             lambda _icon, _item: None, enabled=False),
                    MenuItem(lambda _item, device_key=key: self._device_battery(device_key),
                             lambda _icon, _item: None, enabled=False),
                    MenuItem(lambda _item, device_key=key: self._device_charging(device_key),
                             lambda _icon, _item: None, enabled=False),
                ),
            ))
        items.extend((
            pystray.Menu.SEPARATOR,
            MenuItem("Refresh Now", lambda _icon, _item: self.monitor.refresh_now()),
            MenuItem("Start with Windows", self._toggle_startup, checked=lambda _item: self.settings["start_with_windows"]),
            pystray.Menu.SEPARATOR,
            MenuItem("Exit", self._exit),
        ))
        return pystray.Menu(*items)

    def _get_state(self, key):
        return next((state for state in self._states if state.device_key == key), None)

    def _device_status(self, key):
        state = self._get_state(key)
        return f"Status: {state.connection.value}" if state else "Status: Unknown"

    def _device_battery(self, key):
        state = self._get_state(key)
        return f"Battery: {state.battery}%" if state and state.battery is not None else "Battery: —"

    def _device_charging(self, key):
        state = self._get_state(key)
        value = "Yes" if state and state.charging else "No" if state and state.charging is not None else "Unknown"
        return f"Charging: {value}"

    def _status_label(self):
        return f"Status: {self._state.connection.value}"

    def _battery_label(self):
        return f"Battery: {self._state.battery}%" if self._state.battery is not None else "Battery: —"

    def _charging_label(self):
        value = "Yes" if self._state.charging else "No" if self._state.charging is not None else "Unknown"
        return f"Charging: {value}"

    def _state_changed(self, states: tuple[MonitorState, ...]):
        with self._lock:
            self._states = tuple(states)
            connected = next((state for state in states if state.connection == ConnectionState.CONNECTED), None)
            state = connected or (states[0] if states else MonitorState())
            self._state = state
            connection = state.connection
            if connection == ConnectionState.CONNECTED:
                battery = f"{state.battery}%" if state.battery is not None else "—%"
                if state.charging:
                    tooltip = f"{state.device_name} - Charging - {battery}"
                else:
                    tooltip = f"{state.device_name} - Connected - Battery: {battery}"
            elif connection == ConnectionState.DISCONNECTED:
                tooltip = f"{state.device_name} - Disconnected"
            elif connection == ConnectionState.RECEIVER_UNAVAILABLE:
                tooltip = f"{state.device_name} - Receiver unavailable"
            else:
                tooltip = f"{state.device_name} - Status unknown"
            if len(states) > 1:
                online_count = sum(item.connection == ConnectionState.CONNECTED for item in states)
                tooltip = f"{online_count} of {len(states)} monitored devices connected"
            try:
                self.icon.icon = make_icon(state)
                self.icon.title = tooltip[:127]
                self.icon.update_menu()
            except (AttributeError, RuntimeError):
                log.debug("Tray icon is not running yet")

    def _toggle_startup(self, _icon=None, _item=None):
        try:
            enabled = not self.settings["start_with_windows"]
            config.set_startup(enabled)
            self.settings["start_with_windows"] = enabled
            config.save_settings(self.settings)
            self.icon.update_menu()
        except OSError as exc:
            log.warning("Could not update startup setting: %s", exc)

    def _exit(self, _icon=None, _item=None):
        if self._stopping:
            return
        self._stopping = True
        self.monitor.stop()
        self.icon.stop()

    def run(self):
        self.monitor.start()
        try:
            self.icon.run()
        finally:
            self.monitor.stop()

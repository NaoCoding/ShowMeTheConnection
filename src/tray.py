"""pystray front end; all HID work remains on the monitor thread."""

from __future__ import annotations

import logging
import threading

import pystray
from pystray import MenuItem

import config
from icons import make_icon
from monitor import ConnectionState, Monitor, MonitorState

log = logging.getLogger(__name__)


class TrayApp:
    def __init__(self, monitor: Monitor | None = None):
        self.settings = config.load_settings()
        self.monitor = monitor or Monitor(on_change=self._state_changed,
                                          disabled_drivers=self.settings.get("disabled_drivers", []))
        # Apply saved choices before the tray has initialized its locks and icon.
        self.monitor.on_change = lambda _states: None
        for state in self.monitor.states:
            self.monitor.set_driver_enabled(state.device_key,
                                            state.device_key not in self.settings.get("disabled_drivers", []))
        self.monitor.on_change = self._state_changed
        self._lock = threading.RLock()
        self._states = self.monitor.states
        self._state = self._states[0] if self._states else self.monitor.state
        saved_icon_devices = self.settings.get("icon_devices")
        self._icon_devices = (set(saved_icon_devices) if saved_icon_devices is not None
                              else {state.device_key for state in self._states})
        self._stopping = False
        visible_states = self._visible_states()
        self.icon = pystray.Icon("ShowMeTheConnection", make_icon(visible_states),
                                 self._tray_summary(visible_states), self._menu())

    def _menu(self):
        items = []
        for state in self._states:
            key = state.device_key
            if not self.monitor.is_driver_enabled(key):
                continue
            items.append(MenuItem(
                lambda _item, device_key=key: self._device_summary(device_key),
                pystray.Menu(
                    MenuItem(lambda _item, device_key=key: self._device_status(device_key),
                             lambda _icon, _item: None, enabled=False),
                    MenuItem(lambda _item, device_key=key: self._device_battery(device_key),
                             lambda _icon, _item: None, enabled=False),
                    MenuItem(lambda _item, device_key=key: self._device_charging(device_key),
                             lambda _icon, _item: None, enabled=False),
                ),
            ))
        visibility_items = []
        for state in self._states:
            key = state.device_key

            def toggle_action(device_key):
                return lambda _icon, _item: self._toggle_icon_device(device_key)

            visibility_items.append(MenuItem(
                state.device_name,
                toggle_action(key),
                checked=lambda _item, device_key=key: device_key in self._icon_devices,
            ))
        visibility_menu = pystray.Menu(*visibility_items)
        driver_items = []

        def toggle_driver_action(device_key):
            return lambda _icon, _item: self._toggle_driver(device_key)

        for state in self._states:
            key = state.device_key
            driver_items.append(MenuItem(
                state.device_name,
                toggle_driver_action(key),
                checked=lambda _item, device_key=key: self.monitor.is_driver_enabled(device_key),
            ))
        driver_menu = pystray.Menu(*driver_items)
        items.extend((
            MenuItem("Drivers monitored", driver_menu),
            MenuItem("Devices shown on icon", visibility_menu),
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

    def _device_summary(self, key):
        state = self._get_state(key)
        if state is None:
            return "Unknown device"
        if state.battery is not None:
            return f"{state.device_name} — {state.battery}%"
        return f"{state.device_name} — {state.connection.value}"

    def _visible_states(self):
        return tuple(state for state in self._states if state.device_key in self._icon_devices)

    def _tray_summary(self, states):
        if not states:
            return "No devices selected on tray icon"
        summaries = []
        for state in states:
            if state.connection == ConnectionState.DISABLED:
                summary = f"{state.device_name}: monitoring disabled"
            elif state.battery is not None:
                summary = f"{state.device_name}: {state.battery}%"
                if state.charging:
                    summary += " charging"
            elif state.connection == ConnectionState.RECEIVER_UNAVAILABLE:
                summary = f"{state.device_name}: receiver unavailable"
            elif state.connection == ConnectionState.DISCONNECTED:
                summary = f"{state.device_name}: disconnected"
            elif state.connection == ConnectionState.UNKNOWN:
                summary = f"{state.device_name}: searching"
            else:
                summary = f"{state.device_name}: battery pending"
            summaries.append(summary)
        return " | ".join(summaries) or "ShowMeTheConnection - Starting"

    def _refresh_icon(self):
        states = self._visible_states()
        try:
            self.icon.icon = make_icon(states)
            self.icon.title = self._tray_summary(states)[:127]
            self.icon.menu = self._menu()
        except (AttributeError, RuntimeError):
            log.debug("Tray icon is not running yet")

    def _toggle_icon_device(self, key):
        with self._lock:
            if key in self._icon_devices:
                self._icon_devices.remove(key)
            else:
                self._icon_devices.add(key)
            previous = self.settings.get("icon_devices")
            self.settings["icon_devices"] = sorted(self._icon_devices)
            try:
                config.save_settings(self.settings)
            except OSError as exc:
                if previous is None:
                    self._icon_devices = {state.device_key for state in self._states}
                    self.settings["icon_devices"] = None
                else:
                    self._icon_devices = set(previous)
                    self.settings["icon_devices"] = previous
                log.warning("Could not save tray icon device selection: %s", exc)
            self._refresh_icon()

    def _toggle_driver(self, key):
        with self._lock:
            previous = list(self.settings.get("disabled_drivers", []))
            disabled = set(previous)
            if self.monitor.is_driver_enabled(key):
                disabled.add(key)
            else:
                disabled.discard(key)
            self.settings["disabled_drivers"] = sorted(disabled)
            self.monitor.set_driver_enabled(key, key not in disabled)
            try:
                config.save_settings(self.settings)
            except OSError as exc:
                self.settings["disabled_drivers"] = previous
                self.monitor.set_driver_enabled(key, key not in previous)
                log.warning("Could not save monitored driver selection: %s", exc)
            self._refresh_icon()

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
            self._refresh_icon()

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

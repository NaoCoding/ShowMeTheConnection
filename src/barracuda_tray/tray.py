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
        self._state = self.monitor.state
        self._stopping = False
        self.icon = pystray.Icon("BarracudaTray", make_icon(self._state), "Razer Barracuda X - Unknown", self._menu())

    def _menu(self):
        return pystray.Menu(
            MenuItem("Razer Barracuda X", lambda _icon, _item: None, enabled=False),
            MenuItem(lambda _item: self._status_label(), lambda _icon, _item: None, enabled=False),
            MenuItem(lambda _item: self._battery_label(), lambda _icon, _item: None, enabled=False),
            MenuItem(lambda _item: self._charging_label(), lambda _icon, _item: None, enabled=False),
            pystray.Menu.SEPARATOR,
            MenuItem("Refresh Now", lambda _icon, _item: self.monitor.refresh_now()),
            MenuItem("Start with Windows", self._toggle_startup, checked=lambda _item: self.settings["start_with_windows"]),
            pystray.Menu.SEPARATOR,
            MenuItem("Exit", self._exit),
        )

    def _status_label(self):
        return f"Status: {self._state.connection.value}"

    def _battery_label(self):
        return f"Battery: {self._state.battery}%" if self._state.battery is not None else "Battery: —"

    def _charging_label(self):
        value = "Yes" if self._state.charging else "No" if self._state.charging is not None else "Unknown"
        return f"Charging: {value}"

    def _state_changed(self, state: MonitorState):
        with self._lock:
            self._state = state
            connection = state.connection
            if connection == ConnectionState.CONNECTED:
                battery = f"{state.battery}%" if state.battery is not None else "—%"
                if state.charging:
                    tooltip = f"Razer Barracuda X - Charging - {battery}"
                else:
                    tooltip = f"Razer Barracuda X - Connected - Battery: {battery}"
            elif connection == ConnectionState.DISCONNECTED:
                tooltip = "Razer Barracuda X - Disconnected"
            elif connection == ConnectionState.RECEIVER_UNAVAILABLE:
                tooltip = "Razer Barracuda X - Receiver unavailable"
            else:
                tooltip = "Razer Barracuda X - Status unknown"
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

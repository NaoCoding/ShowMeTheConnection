"""Small user settings file and optional Windows startup registration."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

APP_NAME = "ShowMeTheConnection"


def config_path() -> Path:
    root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    return root / APP_NAME / "settings.json"


def load_settings() -> dict:
    try:
        path = config_path()
        if not path.exists():
            legacy = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "BarracudaTray" / "settings.json"
            path = legacy
        data = json.loads(path.read_text(encoding="utf-8"))
        icon_devices = data.get("icon_devices")
        if icon_devices is not None:
            icon_devices = [key for key in icon_devices if isinstance(key, str)] if isinstance(icon_devices, list) else []
        disabled_drivers = data.get("disabled_drivers", [])
        disabled_drivers = ([key for key in disabled_drivers if isinstance(key, str)]
                            if isinstance(disabled_drivers, list) else [])
        return {"start_with_windows": bool(data.get("start_with_windows", False)),
                "low_battery_threshold": max(0, min(100, int(data.get("low_battery_threshold", 20)))),
                "icon_devices": icon_devices, "disabled_drivers": disabled_drivers}
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {"start_with_windows": False, "low_battery_threshold": 20, "icon_devices": None,
                "disabled_drivers": []}


def save_settings(settings: dict) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2), encoding="utf-8")


def set_startup(enabled: bool) -> None:
    if sys.platform != "win32":
        raise OSError("Windows startup integration is only available on Windows")
    import winreg
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
        # Remove the previous product value to avoid launching both old and new builds.
        for value_name in ("BarracudaTray", "ShowMeTheConnection"):
            try:
                winreg.DeleteValue(key, value_name)
            except FileNotFoundError:
                pass
        if enabled:
            if getattr(sys, "frozen", False):
                command = f'"{sys.executable}"'
            else:
                entry = Path(__file__).resolve().parents[2] / "run_tray.py"
                command = f'"{sys.executable}" "{entry}"'
            winreg.SetValueEx(key, "ShowMeTheConnection", 0, winreg.REG_SZ, command)

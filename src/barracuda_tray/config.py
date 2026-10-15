"""Small user settings file and optional Windows startup registration."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

APP_NAME = "Razer Barracuda X Tray"


def config_path() -> Path:
    root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    return root / "BarracudaTray" / "settings.json"


def load_settings() -> dict:
    try:
        data = json.loads(config_path().read_text(encoding="utf-8"))
        return {"start_with_windows": bool(data.get("start_with_windows", False)),
                "low_battery_threshold": max(0, min(100, int(data.get("low_battery_threshold", 20))))}
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {"start_with_windows": False, "low_battery_threshold": 20}


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
        if enabled:
            if getattr(sys, "frozen", False):
                command = f'"{sys.executable}"'
            else:
                entry = Path(__file__).resolve().parents[2] / "run_tray.py"
                command = f'"{sys.executable}" "{entry}"'
            winreg.SetValueEx(key, "BarracudaTray", 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, "BarracudaTray")
            except FileNotFoundError:
                pass

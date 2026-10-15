"""Source checkout launcher and PyInstaller entry point."""

from pathlib import Path
import sys

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from barracuda_tray.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())

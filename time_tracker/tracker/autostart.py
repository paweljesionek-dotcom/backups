"""Autostart bez terminala: rejestr HKCU\\...\\Run (Windows) albo LaunchAgent (macOS)."""
import os
import subprocess
import sys
from pathlib import Path

from . import config as C

NAME = "TimeTracker"
PLIST = Path.home() / "Library/LaunchAgents/pl.wemake.timetracker.plist"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _command():
    """Zwraca listę argumentów uruchamiającą aplikację (instalator albo Python z kodu)."""
    if getattr(sys, "frozen", False):
        return [sys.executable]
    exe = sys.executable
    if sys.platform == "win32":
        exe = str(Path(exe).with_name("pythonw.exe"))
    return [exe, "-m", "tracker", "app"]


def enabled():
    if sys.platform == "win32":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
                winreg.QueryValueEx(k, NAME)
            return True
        except OSError:
            return False
    if sys.platform == "darwin":
        return PLIST.exists()
    return False


def set_enabled(on):
    cmd = _command()
    if sys.platform == "win32":
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if on:
                winreg.SetValueEx(k, NAME, 0, winreg.REG_SZ, " ".join(f'"{c}"' for c in cmd))
            else:
                try:
                    winreg.DeleteValue(k, NAME)
                except OSError:
                    pass
    elif sys.platform == "darwin":
        if on:
            args = "".join(f"<string>{c}</string>" for c in cmd)
            PLIST.parent.mkdir(parents=True, exist_ok=True)
            PLIST.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>pl.wemake.timetracker</string>
<key>ProgramArguments</key><array>{args}</array>
<key>RunAtLoad</key><true/>
<key>StandardErrorPath</key><string>{C.HOME}/agent.log</string>
</dict></plist>""")
        else:
            PLIST.unlink(missing_ok=True)

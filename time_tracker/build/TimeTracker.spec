# PyInstaller: pyinstaller build/TimeTracker.spec   (Windows: dist/TimeTracker/, macOS: dist/TimeTracker.app)
import sys
from pathlib import Path

root = Path(SPECPATH).parent
hidden = ["tracker.platforms.windows", "tracker.platforms.macos", "pystray._win32", "pystray._darwin"]

a = Analysis([str(root / "launcher.py")], pathex=[str(root)], hiddenimports=hidden,
             excludes=["tkinter", "unittest.mock"])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="TimeTracker",
          console=False, disable_windowed_traceback=True)
coll = COLLECT(exe, a.binaries, a.datas, name="TimeTracker")

if sys.platform == "darwin":
    app = BUNDLE(coll, name="TimeTracker.app", bundle_identifier="pl.wemake.timetracker",
                 info_plist={
                     "LSUIElement": True,  # tylko ikona w pasku menu, bez ikony w Docku
                     "CFBundleName": "TimeTracker",
                     "NSAppleEventsUsageDescription": "Tracker czasu odczytuje aktywne okno i adres karty przeglądarki, aby przypisać czas do projektu.",
                 })

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

from . import config as C
from .db import DB
from .util import day_of, fmt_dur, now_ts


def _local_post(cfg, path):
    req = urllib.request.Request(f"http://127.0.0.1:{cfg['local_port']}{path}", b"{}",
                                 {"X-TT-Token": cfg["local_token"], "Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=5).read()


def install_autostart():
    py = sys.executable
    if sys.platform == "win32":
        startup = Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/Startup"
        pyw = Path(py).with_name("pythonw.exe")
        vbs = startup / "timetracker.vbs"
        vbs.write_text(f'Set s = CreateObject("WScript.Shell")\r\ns.CurrentDirectory = "{Path(__file__).resolve().parent.parent}"\r\n'
                       f's.Run """{pyw}"" -m tracker run", 0, False\r\n')
        print("Autostart zapisany:", vbs)
    elif sys.platform == "darwin":
        plist = Path.home() / "Library/LaunchAgents/pl.wemake.timetracker.plist"
        plist.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>pl.wemake.timetracker</string>
<key>ProgramArguments</key><array><string>{py}</string><string>-m</string><string>tracker</string><string>run</string></array>
<key>WorkingDirectory</key><string>{Path(__file__).resolve().parent.parent}</string>
<key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
<key>StandardErrorPath</key><string>{C.HOME}/agent.log</string>
</dict></plist>""")
        os.system(f'launchctl unload "{plist}" 2>/dev/null; launchctl load "{plist}"')
        print("Autostart zapisany:", plist)
    else:
        print("Autostart: tylko Windows i macOS")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="tracker")
    ap.add_argument("cmd", choices=["run", "serve", "pause", "resume", "status", "today", "install-autostart"])
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args(argv)
    cfg = C.load()

    if a.cmd == "install-autostart":
        return install_autostart()
    if a.cmd in ("pause", "resume"):
        _local_post(cfg, "/" + a.cmd)
        return print("Agent:", "wstrzymany" if a.cmd == "pause" else "wznowiony")
    if a.cmd == "status":
        r = urllib.request.urlopen(f"http://127.0.0.1:{cfg['local_port']}/status", timeout=5).read()
        return print(r.decode())

    db = DB(C.db_path())
    if a.cmd == "run":
        from .agent import Agent
        from .platforms import get_provider
        print(f"Agent '{cfg['device_name']}' działa. Dane: {C.db_path()}", flush=True)
        Agent(cfg, db, get_provider()).run()
    elif a.cmd == "serve":
        from .server import make_server
        srv = make_server(cfg, db, a.host, a.port)
        print(f"Panel: http://{a.host}:{a.port}", flush=True)
        srv.serve_forever()
    elif a.cmd == "today":
        from . import builder
        db.sync_projects(cfg["projects"])
        day = day_of(now_ts())
        builder.build_day(db, cfg, day)
        t = builder.totals(db, cfg, day)
        for p in t["projects"]:
            print(f"{p['code']:<12} {p['brand']:<10} {fmt_dur(p['seconds'])}")
        print(f"poza pracą: {fmt_dur(t['unproductive'])}, nieprzypisane: {fmt_dur(t['unknown'])}")


if __name__ == "__main__":
    main()

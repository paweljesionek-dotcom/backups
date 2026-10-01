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


def main(argv=None):
    ap = argparse.ArgumentParser(prog="tracker")
    ap.add_argument("cmd", nargs="?", default="app",
                    choices=["app", "run", "serve", "pause", "resume", "status", "today", "install-autostart"])
    ap.add_argument("--no-tray", action="store_true")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args(argv)
    C.ensure_config()
    cfg = C.load()

    if a.cmd == "install-autostart":
        from . import autostart
        autostart.set_enabled(True)
        return print("Autostart włączony")
    if a.cmd in ("pause", "resume"):
        _local_post(cfg, "/" + a.cmd)
        return print("Agent:", "wstrzymany" if a.cmd == "pause" else "wznowiony")
    if a.cmd == "status":
        r = urllib.request.urlopen(f"http://127.0.0.1:{cfg['local_port']}/status", timeout=5).read()
        return print(r.decode())

    db = DB(C.db_path())
    if a.cmd == "app":
        from .app import run_app
        return run_app(cfg, db, open_panel=not a.no_browser, tray=not a.no_tray)
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

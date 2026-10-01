"""Serwer + panel web. Lokalnie czyta wspólną bazę agenta; w chmurze przyjmuje dane od agentów (/api/ingest)."""
import base64
import hmac
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import ai, builder, exporter, matcher
from .panel_html import PAGE
from .util import day_bounds, day_of, hhmm, now_ts, parse_hhmm


def make_server(cfg, db, host="127.0.0.1", port=8765):
    db.sync_projects(cfg.get("projects", []))

    def blocks_view(day):
        out = []
        for b in builder.day_blocks(db, day):
            b["suggest"] = matcher.suggest_rule(b) if b["type"] in ("unknown", "project", "general") else None
            b["from"], b["to"] = hhmm(b["start"]), hhmm(b["end"])
            out.append(b)
        return out

    def day_payload(day):
        builder.build_day(db, cfg, day)
        d = db.one("SELECT approved_at FROM days WHERE day=?", (day,))
        return {"date": day, "approved": bool(d and d["approved_at"]), "blocks": blocks_view(day),
                "totals": builder.totals(db, cfg, day), "review": builder.review_queue(db, cfg, day),
                "projects": db.projects(), "entries": db.q("SELECT * FROM time_entries WHERE day=?", (day,)),
                "export_url_set": bool(cfg["export"]["url"]), "review_below": cfg["review_below"]}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, data, ctype="application/json"):
            raw = data if isinstance(data, bytes) else (data if isinstance(data, str) else json.dumps(data)).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype + "; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _auth_panel(self):
            pw = cfg["panel_password"]
            if not pw:
                return True
            h = self.headers.get("Authorization", "")
            if h.startswith("Basic "):
                try:
                    given = base64.b64decode(h[6:]).decode().split(":", 1)[1]
                    if hmac.compare_digest(given, pw):
                        return True
                except Exception:
                    pass
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="tracker"')
            self.send_header("Content-Length", "0")
            self.end_headers()
            return False

        def do_GET(self):
            u = urlparse(self.path)
            if u.path == "/healthz":
                return self._send(200, {"ok": True})
            if not self._auth_panel():
                return
            q = parse_qs(u.query)
            day = (q.get("date") or [day_of(now_ts())])[0]
            if u.path == "/":
                return self._send(200, PAGE, "text/html")
            if u.path == "/api/day":
                return self._send(200, day_payload(day))
            if u.path == "/api/export.csv":
                to = (q.get("to") or [day])[0]
                return self._send(200, exporter.entries_csv(db, day, to), "text/csv")
            self._send(404, {"error": "not found"})

        def do_POST(self):
            u = urlparse(self.path)
            n = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                return self._send(400, {"error": "bad json"})
            if u.path == "/api/ingest":
                return self._ingest(body)
            if not self._auth_panel():
                return
            try:
                self._send(200, self._act(u.path, body))
            except PermissionError as e:
                self._send(409, {"error": str(e)})
            except KeyError:
                self._send(404, {"error": "not found"})

        def _act(self, path, b):
            day = b.get("date")
            if path == "/api/assign":
                builder.assign(db, cfg, b["id"], b.get("project"), b.get("type"), b.get("rule"))
            elif path == "/api/manual":
                builder.add_manual(db, day, parse_hhmm(day, b["from"]), parse_hhmm(day, b["to"]),
                                   b.get("project"), b.get("type"), b.get("note", ""))
            elif path == "/api/delete":
                builder.delete_manual(db, b["id"])
            elif path == "/api/approve":
                exporter.approve_day(db, cfg, day)
            elif path == "/api/reopen":
                exporter.reopen_day(db, day)
            elif path == "/api/push":
                ok, msg = exporter.push_day(db, cfg, day)
                return {"ok": ok, "message": msg}
            elif path == "/api/classify":
                return {"classified": ai.classify_unknown(db, cfg, day)}
            else:
                raise KeyError(path)
            return {"ok": True}

        def _ingest(self, body):
            tok = self.headers.get("Authorization", "").removeprefix("Bearer ")
            dev = body.get("device", "")
            expected = cfg["ingest_tokens"].get(dev)
            if not expected or not hmac.compare_digest(tok, expected):
                return self._send(403, {"error": "forbidden"})
            db.x("INSERT INTO devices(name,os,last_seen) VALUES(?,?,?) ON CONFLICT(name) DO UPDATE SET "
                 "os=excluded.os,last_seen=excluded.last_seen", (dev, body.get("os", ""), now_ts()))
            for e in body.get("events", []):
                db.upsert_raw({"device": dev, "start": int(e["start"]), "end": int(e["end"]),
                               "app": e.get("app", ""), "title": e.get("title", ""), "path": e.get("path", ""),
                               "url": e.get("url", ""), "domain": e.get("domain", ""),
                               "private": int(e.get("private", 0)), "idle_s": int(e.get("idle_s", 0)),
                               "synced": 1})
            self._send(200, {"ok": True, "n": len(body.get("events", []))})

    srv = ThreadingHTTPServer((host, port), H)
    threading.Thread(target=_maintenance, args=(cfg, db), daemon=True).start()
    return srv


def _maintenance(cfg, db):
    """Co 15 min: AI dla niejasnych bloków dzisiaj; raz na jakiś czas czyszczenie starych surowych zdarzeń."""
    while True:
        try:
            ai.classify_unknown(db, cfg, day_of(now_ts()))
            cutoff = now_ts() - cfg["raw_retention_days"] * 86400
            db.x("DELETE FROM raw_events WHERE end<?", (cutoff,))
        except Exception as e:
            print("maintenance error:", e, flush=True)
        time.sleep(900)

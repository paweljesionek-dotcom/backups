"""Agent w tle: co kilka sekund zapisuje okno z fokusem, odrzuca bezczynność i buforuje w SQLite."""
import json
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import matcher
from .util import domain_of, extract_path_and_file, now_ts


class Agent:
    def __init__(self, cfg, db, provider, clock=time.time):
        self.cfg, self.db, self.provider, self.clock = cfg, db, provider, clock
        self.paused = False
        self.tab = None            # ostatnie dane z rozszerzenia: {ts, url, title, audible, incognito}
        self.cur = None            # otwarty zdarzenie: {key, start}
        self.lock = threading.Lock()

    # --- dane z rozszerzenia przeglądarki ---
    def set_tab(self, data):
        with self.lock:
            self.tab = {**data, "ts": self.clock()}

    def _fresh_tab(self):
        with self.lock:
            t = self.tab
        return t if t and self.clock() - t["ts"] <= max(15, self.cfg["sample_seconds"] * 3) else None

    def _is_browser(self, app):
        a = (app or "").lower()
        return any(b in a for b in self.cfg["browsers"])

    def _keepalive(self, snap, tab):
        a, t = (snap["app"] or "").lower(), snap["title"] or ""
        if any(m in a for m in self.cfg["meeting_apps"]):
            return True
        if any(p.lower() in t.lower() for p in self.cfg["meeting_title_patterns"]):
            return True
        return bool(tab and tab.get("audible"))

    def _close(self):
        self.cur = None

    def tick(self):
        """Jedna próbka. Zwraca zapisane zdarzenie albo None."""
        if self.paused:
            self._close()
            return None
        now = int(self.clock())
        snap = self.provider.foreground()
        if not snap or snap.get("incognito"):
            self._close()
            return None
        tab = self._fresh_tab() if self._is_browser(snap["app"]) else None
        if tab and tab.get("incognito"):
            self._close()
            return None
        idle = self.provider.idle_seconds()
        if idle >= self.cfg["idle_seconds"] and not self._keepalive(snap, tab):
            self._close()
            return None

        title = snap["title"] or ""
        url = (tab or {}).get("url") or snap.get("url") or ""
        if tab and tab.get("title"):
            title = tab["title"]
        domain = domain_of(url)
        path, fname = extract_path_and_file(title, snap.get("doc_path", ""))
        private = matcher.is_private(self.cfg, snap["app"], title, domain)
        if private:  # zapisujemy tylko czas i typ, bez tytułów i adresów
            ev = {"app": "[prywatne]", "title": "", "path": "", "url": "", "domain": "", "private": 1}
        else:
            ev = {"app": snap["app"], "title": title, "path": path, "url": url, "domain": domain, "private": 0}

        key = (ev["app"], ev["title"], ev["path"], ev["url"])
        step = self.cfg["sample_seconds"]
        cur = self.cur
        if cur and cur["key"] == key and now - cur["last"] <= step * 3:
            cur["last"] = now
            row = {"device": self.cfg["device_name"], "start": cur["start"], "end": now + step,
                   "idle_s": idle, **ev}
        else:
            if cur:  # domykamy poprzedni, żeby się nie nakładały
                self.db.x("UPDATE raw_events SET end=MIN(end,?), synced=0 WHERE device=? AND start=?",
                          (now, self.cfg["device_name"], cur["start"]))
            self.cur = {"key": key, "start": now, "last": now}
            row = {"device": self.cfg["device_name"], "start": now, "end": now + step, "idle_s": idle, **ev}
        self.db.upsert_raw(row)
        return row

    # --- synchronizacja z serwerem w chmurze ---
    def sync_once(self):
        url, tok = self.cfg["server_url"], self.cfg["device_token"]
        if not url:
            return 0
        rows = self.db.q("SELECT * FROM raw_events WHERE device=? AND synced=0 ORDER BY start LIMIT 500",
                         (self.cfg["device_name"],))
        if not rows:
            return 0
        body = json.dumps({"device": self.cfg["device_name"], "os": getattr(self.provider, "os_name", ""),
                           "events": rows}).encode()
        req = urllib.request.Request(url.rstrip("/") + "/api/ingest", body,
                                     {"Authorization": "Bearer " + tok, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                ok = r.status < 300
        except (urllib.error.URLError, OSError):
            return 0  # offline: zostaje w buforze, spróbujemy za minutę
        if ok:
            ids = [r["id"] for r in rows]
            # zaznacz jako wysłane tylko, jeśli nie zmieniły się w międzyczasie
            for r in rows:
                self.db.x("UPDATE raw_events SET synced=1 WHERE id=? AND end=?", (r["id"], r["end"]))
            return len(ids)
        return 0

    def run(self):
        threading.Thread(target=self._sync_loop, daemon=True).start()
        threading.Thread(target=self._local_server, daemon=True).start()
        while True:
            try:
                self.tick()
            except Exception as e:  # agent nie może paść przez pojedynczy błąd próbki
                print("tick error:", e, flush=True)
            time.sleep(self.cfg["sample_seconds"])

    def _sync_loop(self):
        while True:
            try:
                self.sync_once()
            except Exception as e:
                print("sync error:", e, flush=True)
            time.sleep(60)

    def _local_server(self):
        agent = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _ok(self, obj=None):
                data = json.dumps(obj or {"ok": True}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                if self.path == "/status":
                    self._ok({"paused": agent.paused, "device": agent.cfg["device_name"]})
                else:
                    self.send_error(404)

            def do_POST(self):
                if self.headers.get("X-TT-Token") != agent.cfg["local_token"]:
                    return self.send_error(403)
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}")
                if self.path == "/tab":
                    agent.set_tab(body)
                elif self.path == "/pause":
                    agent.paused = True
                elif self.path == "/resume":
                    agent.paused = False
                else:
                    return self.send_error(404)
                self._ok()

        ThreadingHTTPServer(("127.0.0.1", self.cfg["local_port"]), H).serve_forever()

import json
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tracker import builder, config as C, exporter
from tracker.agent import Agent
from tracker.db import DB
from tracker.platforms.fake import FakeProvider
from tracker.util import day_bounds, extract_path_and_file

DAY = "2026-10-01"
T0 = day_bounds(DAY)[0] + 9 * 3600  # 09:00 czasu warszawskiego

CFG_OVERRIDE = {
    "device_name": "PC",
    "projects": [
        {"code": "WM-024", "name": "Nowak", "brand": "we.make", "keywords": ["Nowak"], "paths": []},
        {"code": "10D-KOW", "name": "Kowalski", "brand": "10design", "keywords": [], "paths": ["10design/Klienci/Kowalski"]},
    ],
}


def mkcfg(**kw):
    cfg = C._merge(C.DEFAULTS, {**CFG_OVERRIDE, **kw})
    return cfg


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


def run_script(cfg, db, script, device="PC", step=5, offset=0):
    cfg = {**cfg, "device_name": device}
    clock = Clock(T0 + offset)
    prov = FakeProvider(script)
    ag = Agent(cfg, db, prov, clock)
    for _ in script:
        ag.tick()
        prov.advance()
        clock.t += step
    return ag


def app(name, title, **kw):
    return {"app": name, "title": title, "doc_path": kw.get("doc", ""), "url": kw.get("url", ""), "incognito": False}


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dbs = []
        self.db = self.open_db("t.db")
        self.cfg = mkcfg()
        self.db.sync_projects(self.cfg["projects"])

    def open_db(self, name):
        db = DB(Path(self.tmp.name) / name)
        self.dbs.append(db)
        return db

    def tearDown(self):
        for db in self.dbs:  # Windows nie pozwala skasować otwartego pliku bazy
            db.close()
        self.tmp.cleanup()

    def totals(self):
        builder.build_day(self.db, self.cfg, DAY)
        return builder.totals(self.db, self.cfg, DAY)

    def test_rule_by_filename_and_idle_excluded(self):
        script = [(0, app("ArchiCAD", "Nowak_rzut_v3.pln - ArchiCAD"))] * 24 + [(600, app("ArchiCAD", "Nowak_rzut_v3.pln"))] * 20
        run_script(self.cfg, self.db, script)
        t = self.totals()
        self.assertEqual([p["code"] for p in t["projects"]], ["WM-024"])
        self.assertAlmostEqual(t["projects"][0]["seconds"], 120, delta=6)  # 24 próbki * 5 s, idle nie liczy się

    def test_meeting_counts_while_idle(self):
        script = [(900, app("Zoom", "Zoom Meeting Nowak"))] * 12
        run_script(self.cfg, self.db, script)
        self.assertGreater(self.totals()["projects"][0]["seconds"], 50)

    def test_private_is_not_stored_and_not_exported(self):
        run_script(self.cfg, self.db, [(0, app("chrome", "Logowanie do banku PKO"))] * 12)
        ev = self.db.q("SELECT * FROM raw_events")[0]
        self.assertEqual((ev["title"], ev["url"], ev["private"]), ("", "", 1))
        t = self.totals()
        self.assertGreater(t["private"], 0)
        self.assertEqual(t["projects"], [])

    def test_incognito_ignored(self):
        s = app("chrome", "Nowak")
        s["incognito"] = True
        run_script(self.cfg, self.db, [(0, s)] * 10)
        self.assertEqual(self.db.q("SELECT * FROM raw_events"), [])

    def test_two_devices_do_not_double_count(self):
        win = [(0, app("ArchiCAD", "Nowak.pln"))] * 24             # PC: ręce na klawiaturze
        mac = [(150, app("Safari", "Nowak mood"))] * 24             # Mac: ten sam czas, 150 s bezczynności
        run_script(self.cfg, self.db, win, "PC")
        run_script(self.cfg, self.db, mac, "MacBook")
        t = self.totals()
        self.assertAlmostEqual(t["projects"][0]["seconds"], 120, delta=6)  # 120 s, a nie 240
        self.assertEqual({b["device"] for b in builder.day_blocks(self.db, DAY)}, {"PC"})

    def test_session_inheritance_and_unproductive_not_inherited(self):
        long = [(0, app("ArchiCAD", "Nowak.pln"))] * 60
        short = [(0, app("chrome", "Płytki łazienkowe - sklep", url="https://plytki.pl/lazienka"))] * 6
        yt = [(0, app("chrome", "Film", url="https://www.youtube.com/watch?v=1"))] * 6
        run_script(self.cfg, self.db, long + short + long + yt + long)
        self.totals()
        blocks = builder.day_blocks(self.db, DAY)
        shop = [b for b in blocks if "Płytki" in b["title"]][0]
        self.assertEqual((shop["project"], shop["source"]), ("WM-024", "session"))
        doc = [b for b in builder.day_blocks(self.db, DAY)]
        film = [b for b in blocks if "Film" in b["title"]][0]
        self.assertEqual((film["type"], film["project"]), ("unproductive", None))

    def test_named_document_is_not_inherited(self):
        long = [(0, app("ArchiCAD", "Nowak.pln"))] * 60
        other = [(0, app("Photoshop", "Kowalski_wizka.psd"))] * 12
        run_script(self.cfg, self.db, long + other)
        self.totals()
        b = [x for x in builder.day_blocks(self.db, DAY) if "Kowalski" in x["title"]][0]
        self.assertEqual((b["type"], b["project"]), ("unknown", None))

    def test_correction_creates_rule_and_locks(self):
        run_script(self.cfg, self.db, [(0, app("Photoshop", "Kowalski_wizka_v2.psd - Photoshop"))] * 20)
        self.totals()
        b = builder.day_blocks(self.db, DAY)[0]
        self.assertEqual(b["type"], "unknown")
        builder.assign(self.db, self.cfg, b["id"], "10D-KOW", None, {"field": "title", "pattern": "Kowalski_wizka"})
        b2 = builder.day_blocks(self.db, DAY)[0]
        self.assertEqual((b2["project"], b2["locked"]), ("10D-KOW", 1))
        # nowy plik z tej samej reguły trafia sam
        run_script(self.cfg, self.db, [(0, app("Photoshop", "Kowalski_wizka_v3.psd"))] * 20, offset=3600)
        self.totals()
        self.assertTrue(any(x["project"] == "10D-KOW" and x["source"] == "rule" for x in builder.day_blocks(self.db, DAY)))

    def test_approve_rounding_and_exclusions(self):
        run_script(self.cfg, self.db, [(0, app("ArchiCAD", "Nowak.pln"))] * 150)  # 12,5 min
        run_script(self.cfg, self.db, [(0, app("chrome", "x", url="https://facebook.com"))] * 40, offset=3600)
        exporter.approve_day(self.db, self.cfg, DAY)
        e = self.db.q("SELECT * FROM time_entries")
        self.assertEqual(len(e), 1)
        self.assertEqual((e[0]["project"], e[0]["seconds"]), ("WM-024", 900))  # zaokrąglone do 15 min
        csv = exporter.entries_csv(self.db, DAY)
        self.assertIn("WM-024", csv)
        self.assertNotIn("facebook", csv)
        with self.assertRaises(PermissionError):
            builder.assign(self.db, self.cfg, builder.day_blocks(self.db, DAY)[0]["id"], "WM-024", None)

    def test_push_to_program_is_idempotent_payload(self):
        got = []

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def do_POST(s):
                got.append((s.headers.get("Authorization"), json.loads(s.rfile.read(int(s.headers["Content-Length"])))))
                s.send_response(200); s.send_header("Content-Length", "0"); s.end_headers()

        srv = HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.cfg["export"].update(url=f"http://127.0.0.1:{srv.server_port}/api/time", token="sekret")
        run_script(self.cfg, self.db, [(0, app("ArchiCAD", "Nowak.pln"))] * 200)
        ok, _ = exporter.push_day(self.db, self.cfg, DAY)
        self.assertFalse(ok)  # niezatwierdzony dzień nie wychodzi
        exporter.approve_day(self.db, self.cfg, DAY)
        ok, msg = exporter.push_day(self.db, self.cfg, DAY)
        srv.shutdown()
        self.assertTrue(ok, msg)
        self.assertEqual(got[0][0], "Bearer sekret")
        self.assertEqual(got[0][1]["entries"][0]["external_id"], f"{DAY}:WM-024")

    def test_ingest_and_sync_dedupe(self):
        from tracker.server import make_server
        scfg = mkcfg(ingest_tokens={"MacBook": "tok"})
        sdb = self.open_db("server.db")
        srv = make_server(scfg, sdb, "127.0.0.1", 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        acfg = mkcfg(server_url=f"http://127.0.0.1:{srv.server_port}", device_token="tok", device_name="MacBook")
        ag = run_script(acfg, self.db, [(0, app("Safari", "Nowak"))] * 10, "MacBook")
        ag.cfg = acfg
        self.assertGreater(ag.sync_once(), 0)
        self.assertEqual(ag.sync_once(), 0)  # nic do wysłania
        ag.cfg = {**acfg, "device_token": "zly"}
        self.db.x("UPDATE raw_events SET synced=0")
        self.assertEqual(ag.sync_once(), 0)  # zły token odrzucony, dane zostają w buforze
        self.assertEqual(len(sdb.q("SELECT * FROM raw_events")), 1)
        srv.shutdown()

    def test_extract_path_and_file(self):
        self.assertEqual(extract_path_and_file("C:\\Klienci\\Nowak\\rzut.pln - ArchiCAD"),
                         ("C:\\Klienci\\Nowak\\rzut.pln - ArchiCAD", "rzut.pln - ArchiCAD"))
        self.assertEqual(extract_path_and_file("WM-024_rzut_v3.pln - ArchiCAD")[1], "WM-024_rzut_v3.pln")
        self.assertEqual(extract_path_and_file("x", "/Users/p/10design/a.psd"), ("/Users/p/10design/a.psd", "a.psd"))


if __name__ == "__main__":
    unittest.main()

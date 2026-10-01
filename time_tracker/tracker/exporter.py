"""Zatwierdzanie dnia i eksport. Obecnie tylko CSV (do importu w programie we.make).
Kolejne cele (np. API aplikacji) dopisuje się jako nowy adapter z funkcją export(entries)."""
import csv
import io
import os

from . import builder
from .util import fmt_dur, hhmm, now_ts


def _describe(blocks, limit=3):
    seen, out = set(), []
    for b in sorted(blocks, key=lambda b: b["start"] - b["end"]):  # najdłuższe najpierw
        label = ""
        if b["path"]:
            label = b["path"].replace("\\", "/").split("/")[-1]
        elif b["title"]:
            label = b["title"].split(" - ")[0].split(" – ")[0].strip()
        elif b["domain"]:
            label = b["domain"]
        label = label[:60]
        if label and label.lower() not in seen:
            seen.add(label.lower())
            out.append(label)
        if len(out) >= limit:
            break
    return ", ".join(out)


def _round(seconds, minutes):
    step = minutes * 60
    return int((seconds + step / 2) // step * step) if step > 1 else int(seconds)


def build_entries(db, cfg, day):
    """Wpisy do eksportu: tylko typy 'project' i 'general'; nieproduktywne i prywatne nigdy."""
    brands = set(cfg.get("export_brands") or [])
    projects = {p["code"]: p for p in db.projects()}
    gp = cfg.get("general_project") or ""
    groups = {}
    for b in builder.day_blocks(db, day):
        if b["type"] not in ("project", "general"):
            continue
        code = b["project"] or gp
        if brands and code and projects.get(code, {}).get("brand") not in brands:
            continue
        groups.setdefault(code, []).append(b)
    entries = []
    for code, blocks in groups.items():
        if cfg["entry_mode"] == "blocks":
            parts = [(f"{code}:{b['id']}", [b]) for b in blocks]
        else:
            parts = [(code or "(ogólne)", blocks)]
        for key, bl in parts:
            sec = _round(sum(b["end"] - b["start"] for b in bl), cfg["round_minutes"])
            if sec <= 0:
                continue
            entries.append({"day": day, "key": key, "project": code or None, "seconds": sec,
                            "start": min(b["start"] for b in bl),
                            "description": _describe(bl) or ("Praca ogólna" if not code else "")})
    return sorted(entries, key=lambda e: e["start"])


def approve_day(db, cfg, day):
    builder.build_day(db, cfg, day)
    with db.lock:
        db.conn.execute("UPDATE activity_blocks SET locked=1 WHERE day=?", (day,))
        db.conn.execute("DELETE FROM time_entries WHERE day=? AND status='pending'", (day,))
        for e in build_entries(db, cfg, day):
            db.conn.execute(
                "INSERT OR REPLACE INTO time_entries(day,key,project,seconds,start,description,status) VALUES(?,?,?,?,?,?, 'approved')",
                (e["day"], e["key"], e["project"], e["seconds"], e["start"], e["description"]))
        db.conn.execute("INSERT OR REPLACE INTO days(day,approved_at) VALUES(?,?)", (day, now_ts()))
        db.conn.commit()


def reopen_day(db, day):
    with db.lock:
        db.conn.execute("UPDATE days SET approved_at=NULL WHERE day=?", (day,))
        db.conn.execute("DELETE FROM time_entries WHERE day=?", (day,))
        db.conn.execute("UPDATE activity_blocks SET locked=0 WHERE day=? AND source!='manual'", (day,))
        db.conn.commit()


def entries_csv(db, day_from, day_to=None):
    day_to = day_to or day_from
    rows = db.q("SELECT e.*, p.name AS pname, p.brand, p.client FROM time_entries e "
                "LEFT JOIN projects p ON p.code=e.project WHERE e.day>=? AND e.day<=? ORDER BY e.day, e.start",
                (day_from, day_to))
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    w.writerow(["data", "marka", "klient", "kod_projektu", "projekt", "start", "godziny", "minuty", "opis"])
    for r in rows:
        w.writerow([r["day"], r["brand"] or "", r["client"] or "", r["project"] or "", r["pname"] or "",
                    hhmm(r["start"]), f"{r['seconds'] / 3600:.2f}".replace(".", ","), r["seconds"] // 60,
                    r["description"]])
        db.x("UPDATE time_entries SET status='exported', exported_at=? WHERE id=?", (now_ts(), r["id"]))
    return "﻿" + buf.getvalue()  # BOM, żeby Excel poprawnie czytał polskie znaki


def payload(db, day):
    """JSON wysyłany do programu we.make. external_id jest stały (dzień + klucz wpisu),
    więc ponowny eksport powinien aktualizować wpis, a nie dodawać nowy."""
    rows = db.q("SELECT e.*, p.name AS pname, p.brand, p.client FROM time_entries e "
                "LEFT JOIN projects p ON p.code=e.project WHERE e.day=? ORDER BY e.start", (day,))
    return {"source": "auto-tracker", "date": day, "entries": [
        {"external_id": f"{r['day']}:{r['key']}", "date": r["day"], "start_ts": r["start"],
         "seconds": r["seconds"], "minutes": r["seconds"] // 60, "project_code": r["project"],
         "project_name": r["pname"], "brand": r["brand"], "client": r["client"],
         "description": r["description"]} for r in rows]}


def push_day(db, cfg, day):
    """Wysyła zatwierdzony dzień POST-em do programu. Zwraca (ok, komunikat)."""
    import json
    import urllib.error
    import urllib.request
    ex = cfg["export"]
    if not ex["url"]:
        return False, "Brak export.url w konfiguracji (użyj eksportu CSV albo uzupełnij adres programu)"
    if not db.one("SELECT 1 AS x FROM days WHERE day=? AND approved_at IS NOT NULL", (day,)):
        return False, "Dzień nie jest zatwierdzony"
    body = payload(db, day)
    if not body["entries"]:
        return True, "Brak wpisów do wysłania"
    headers = {"Content-Type": "application/json"}
    if ex["token"]:
        headers[ex["auth_header"]] = ex["auth_prefix"] + ex["token"]
    req = urllib.request.Request(ex["url"], json.dumps(body).encode("utf-8"), headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            if r.status >= 300:
                return False, f"Program odpowiedział HTTP {r.status}"
    except urllib.error.HTTPError as e:
        return False, f"Program odpowiedział HTTP {e.code}: {e.read()[:200].decode('utf-8', 'replace')}"
    except (urllib.error.URLError, OSError) as e:
        return False, f"Nie można połączyć z programem: {e}"
    db.x("UPDATE time_entries SET status='exported', exported_at=? WHERE day=?", (now_ts(), day))
    return True, f"Wysłano {len(body['entries'])} wpisów"

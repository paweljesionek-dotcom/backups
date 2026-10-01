"""Składanie dnia: raw_events (wszystkie urządzenia) -> activity_blocks."""
from . import matcher
from .util import day_bounds, now_ts


def _segments(events, lo, hi):
    """Ucinamy czas do doby i rozwiązujemy nakładanie się urządzeń:
    w każdym odcinku wygrywa urządzenie z mniejszą bezczynnością (to, przy którym były ręce)."""
    evs = [e for e in events if e["end"] > lo and e["start"] < hi]
    cuts = sorted({max(lo, e["start"]) for e in evs} | {min(hi, e["end"]) for e in evs})
    segs = []
    for a, b in zip(cuts, cuts[1:]):
        active = [e for e in evs if e["start"] <= a and e["end"] >= b]
        if not active:
            continue
        w = min(active, key=lambda e: (e["idle_s"], e["device"]))
        if segs and segs[-1]["ev"] is w and segs[-1]["end"] == a:
            segs[-1]["end"] = b
        else:
            segs.append({"ev": w, "start": a, "end": b})
    return segs


def _subtract(segs, locked):
    out = []
    for s in segs:
        parts = [(s["start"], s["end"])]
        for l in locked:
            nxt = []
            for a, b in parts:
                if l["end"] <= a or l["start"] >= b:
                    nxt.append((a, b))
                    continue
                if a < l["start"]:
                    nxt.append((a, l["start"]))
                if l["end"] < b:
                    nxt.append((l["end"], b))
            parts = nxt
        out += [{"ev": s["ev"], "start": a, "end": b} for a, b in parts if b > a]
    return out


def build_day(db, cfg, day, merge_gap=30):
    if db.one("SELECT 1 AS x FROM days WHERE day=? AND approved_at IS NOT NULL", (day,)):
        return
    lo, hi = day_bounds(day)
    with db.lock:
        locked = db.q("SELECT start,end FROM activity_blocks WHERE day=? AND locked=1", (day,))
        events = db.q("SELECT * FROM raw_events WHERE end>? AND start<?", (lo, hi))
        segs = _subtract(_segments(events, lo, hi), locked)
        segs.sort(key=lambda s: s["start"])

        blocks = []
        for s in segs:
            e = s["ev"]
            cur = blocks[-1] if blocks else None
            same = cur and all(cur[k] == (e[k] or "") for k in ("device", "app", "title", "path", "url")) \
                and s["start"] - cur["end"] <= merge_gap
            if same:
                cur["end"] = s["end"]
            else:
                blocks.append({"day": day, "start": s["start"], "end": s["end"], "device": e["device"],
                               "app": e["app"] or "", "title": e["title"] or "", "path": e["path"] or "",
                               "url": e["url"] or "", "domain": e["domain"] or "",
                               "private": e["private"], "locked": 0, "note": ""})
        blocks = [b for b in blocks if b["end"] - b["start"] >= cfg["min_block_seconds"]]

        projects = db.projects()
        rules = db.rules(cfg.get("rules", []))
        cache = {r["key"]: r for r in db.q("SELECT * FROM ai_cache")}
        for b in blocks:
            b.update(matcher.classify(b, cfg, projects, rules, cache))
        matcher.inherit_session(blocks, cfg)

        db.conn.execute("DELETE FROM activity_blocks WHERE day=? AND locked=0", (day,))
        for b in blocks:
            db.conn.execute(
                """INSERT INTO activity_blocks(day,start,end,device,app,title,path,url,domain,type,
                   project,confidence,source,reason,locked,note)
                   VALUES(:day,:start,:end,:device,:app,:title,:path,:url,:domain,:type,:project,
                   :confidence,:source,:reason,0,'')""", b)
        db.conn.commit()


def day_blocks(db, day):
    return db.q("SELECT * FROM activity_blocks WHERE day=? ORDER BY start", (day,))


def totals(db, cfg, day):
    projects = {p["code"]: p for p in db.projects()}
    per, brands = {}, {}
    other = {"general": 0, "unproductive": 0, "private": 0, "unknown": 0}
    for b in day_blocks(db, day):
        d = b["end"] - b["start"]
        if b["type"] in ("project", "general") and b["project"]:
            per[b["project"]] = per.get(b["project"], 0) + d
            brand = projects.get(b["project"], {}).get("brand") or "—"
            brands[brand] = brands.get(brand, 0) + d
        elif b["type"] in other:
            other[b["type"]] += d
    return {"projects": [{"code": c, "name": projects.get(c, {}).get("name", c),
                          "brand": projects.get(c, {}).get("brand", ""), "seconds": s}
                         for c, s in sorted(per.items(), key=lambda x: -x[1])],
            "brands": brands, **other}


def review_queue(db, cfg, day):
    return [b["id"] for b in day_blocks(db, day)
            if b["type"] not in ("private", "unproductive") and not b["locked"]
            and b["confidence"] < cfg["review_below"]]


def assign(db, cfg, block_id, project, type_, rule=None):
    b = db.one("SELECT * FROM activity_blocks WHERE id=?", (block_id,))
    if not b:
        raise KeyError(block_id)
    if db.one("SELECT 1 AS x FROM days WHERE day=? AND approved_at IS NOT NULL", (b["day"],)):
        raise PermissionError("dzień zatwierdzony")
    type_ = type_ or ("project" if project else "general")
    db.x("UPDATE activity_blocks SET project=?, type=?, confidence=100, source='manual', locked=1, reason='ręcznie' WHERE id=?",
         (project or None, type_, block_id))
    if rule and rule.get("pattern"):
        db.x("INSERT INTO rules(field,pattern,project,type,priority,from_correction) VALUES(?,?,?,?,60,1)",
             (rule["field"], rule["pattern"], project or None, type_))
        build_day(db, cfg, b["day"])


def add_manual(db, day, start, end, project, type_, note):
    return db.x("""INSERT INTO activity_blocks(day,start,end,device,app,title,type,project,confidence,source,
                   reason,locked,note) VALUES(?,?,?,?,?,?,?,?,100,'manual','dopisane ręcznie',1,?)""",
                (day, start, end, "ręcznie", "", note or "Czas dopisany ręcznie", type_ or "project",
                 project or None, note))


def delete_manual(db, block_id):
    db.x("DELETE FROM activity_blocks WHERE id=? AND device='ręcznie'", (block_id,))

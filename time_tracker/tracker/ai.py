"""Opcjonalne dopasowanie AI dla bloków bez reguły. Używa Claude API (urllib, bez zależności).
Do modelu nie trafiają bloki prywatne ani treść dokumentów: tylko aplikacja, tytuł, plik, domena."""
import json
import urllib.error
import urllib.request

from .matcher import ctx_key


def _call(cfg, prompt):
    key = cfg["ai"]["api_key"]
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        json.dumps({"model": cfg["ai"]["model"], "max_tokens": 4000,
                    "messages": [{"role": "user", "content": prompt}]}).encode(),
        {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.load(r)
    return "".join(c.get("text", "") for c in data["content"] if c["type"] == "text")


def classify_unknown(db, cfg, day, call=_call):
    """Klasyfikuje unikalne konteksty bloków 'unknown' i zapisuje do ai_cache. Zwraca liczbę wpisów."""
    if not cfg["ai"]["enabled"] or not cfg["ai"]["api_key"]:
        return 0
    blocks = db.q("SELECT * FROM activity_blocks WHERE day=? AND type='unknown' AND locked=0 ORDER BY start", (day,))
    uniq = {}
    for b in blocks:
        uniq.setdefault(ctx_key(b), b)
    if not uniq:
        return 0
    projects = [{"code": p["code"], "name": p["name"], "brand": p["brand"], "keywords": p["keywords"]}
                for p in db.projects()]
    examples = [{"app": r["app"], "title": r["title"], "domain": r["domain"], "project": r["project"],
                 "type": r["type"]} for r in db.q(
        "SELECT * FROM activity_blocks WHERE source='manual' AND device!='ręcznie' ORDER BY id DESC LIMIT 20")]
    items = [{"id": k, "app": b["app"], "title": b["title"][:150], "file": b["path"].replace("\\", "/").split("/")[-1],
              "domain": b["domain"]} for k, b in uniq.items()]
    prompt = (
        "Przypisujesz aktywność z komputera do projektów pracowni projektowej. Typy: project (podaj kod), "
        "general (praca ogólna: administracja, marketing, oferty, nauka narzędzi), unproductive, unknown.\n"
        f"Projekty: {json.dumps(projects, ensure_ascii=False)}\n"
        f"Poprawki użytkownika (przykłady): {json.dumps(examples, ensure_ascii=False)}\n"
        f"Aktywności: {json.dumps(items, ensure_ascii=False)}\n"
        'Zwróć wyłącznie JSON: [{"id":"...","type":"project|general|unproductive|unknown","project":"kod lub null",'
        '"confidence":0-100,"reason":"krótko"}]')
    try:
        text = call(cfg, prompt)
        res = json.loads(text[text.index("["): text.rindex("]") + 1])
    except (urllib.error.URLError, OSError, ValueError, KeyError):
        return 0
    codes = {p["code"] for p in projects}
    n = 0
    for r in res:
        if r.get("id") not in uniq or r.get("type") not in ("project", "general", "unproductive", "unknown"):
            continue
        proj = r.get("project") if r.get("project") in codes else None
        if r["type"] == "project" and not proj:
            continue
        db.x("INSERT OR REPLACE INTO ai_cache(key,project,type,confidence,reason) VALUES(?,?,?,?,?)",
             (r["id"], proj, r["type"], max(0, min(100, int(r.get("confidence", 50)))),
              str(r.get("reason", ""))[:200]))
        n += 1
    return n

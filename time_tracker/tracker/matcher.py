"""Dopasowanie bloku do projektu: reguły -> sygnały projektu -> lista 'niepro' -> AI (cache) -> kontekst sesji."""
import hashlib
import re

from .util import extract_path_and_file

FIELDS = ("app", "title", "path", "url", "domain")


def ctx_key(b):
    s = "|".join(str(b.get(k) or "") for k in ("app", "title", "path", "url"))
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def _hit(pattern, text):
    if not text:
        return False
    try:
        return re.search(pattern, text) is not None
    except re.error:
        return pattern.lower() in text.lower()


def is_private(cfg, app, title, domain):
    p = cfg["private"]
    if any(a.lower() in (app or "").lower() for a in p["apps"]):
        return True
    if domain and any(domain == d or domain.endswith("." + d) for d in p["domains"]):
        return True
    return any(_hit(pat, title) for pat in p["title_patterns"])


def _domain_in(domain, lst):
    return bool(domain) and any(domain == d or domain.endswith("." + d) for d in lst)


def classify(b, cfg, projects, rules, ai_cache):
    """Zwraca dict(type, project, confidence, source, reason)."""
    if b.get("private"):
        return dict(type="private", project=None, confidence=100, source="rule", reason="lista prywatnych")

    for r in rules:  # 1. reguły jawne (priorytet malejąco)
        if r.get("field") in FIELDS and _hit(r["pattern"], b.get(r["field"])):
            t = r.get("type") or ("project" if r.get("project") else "general")
            return dict(type=t, project=r.get("project"), confidence=95,
                        source="rule", reason=f'reguła {r["field"]}~{r["pattern"]}')

    hay = " ".join(str(b.get(k) or "") for k in ("title", "path", "url")).lower()
    best = None  # 2. sygnały z katalogu projektów
    for p in projects:
        score, why = 0, ""
        if p["code"] and p["code"].lower() in hay:
            score, why = 92, f'kod {p["code"]}'
        for folder in p["paths"]:
            if folder and folder.lower().replace("\\", "/") in (b.get("path") or "").lower().replace("\\", "/"):
                score, why = max(score, 92), f"folder {folder}"
        for kw in p["keywords"]:
            if kw and kw.lower() in hay and score < 85:
                score, why = 85, f"słowo kluczowe '{kw}'"
        if score and (best is None or score > best[0]):
            best = (score, p["code"], why)
    if best:
        return dict(type="project", project=best[1], confidence=best[0], source="rule", reason=best[2])

    app_l = (b.get("app") or "").lower()  # 3. domyślnie nieproduktywne
    if _domain_in(b.get("domain"), cfg["unproductive"]["domains"]) or any(
            a.lower() in app_l for a in cfg["unproductive"]["apps"]):
        return dict(type="unproductive", project=None, confidence=85, source="rule", reason="lista nieproduktywnych")

    hit = ai_cache.get(ctx_key(b))  # 4. wynik AI z cache
    if hit:
        return dict(type=hit["type"], project=hit["project"], confidence=hit["confidence"],
                    source="ai", reason=hit["reason"])
    return dict(type="unknown", project=None, confidence=0, source="none", reason="brak dopasowania")


def inherit_session(blocks, cfg):
    """Krótkie, słabo dopasowane bloki dziedziczą projekt z otoczenia. Nigdy nie dla nieprod./prywatnych."""
    limit = cfg["session_inherit_seconds"]
    below = cfg["review_below"]
    strong = lambda x: x and x["project"] and x["confidence"] >= below and x["type"] == "project"
    for i, b in enumerate(blocks):
        if b["type"] in ("private", "unproductive") or b["locked"]:
            continue
        if b["confidence"] >= below or (b["end"] - b["start"]) > limit:
            continue
        if any(extract_path_and_file(b.get("title"), b.get("path"))):
            continue  # dokument z własną nazwą nie jest "wtrąceniem": niech sprawdzi człowiek
        prev = next((x for x in reversed(blocks[:i]) if strong(x)), None)
        nxt = next((x for x in blocks[i + 1:] if strong(x)), None)
        near = lambda x, gap: x and gap <= limit
        ok_prev = prev and near(prev, b["start"] - prev["end"])
        ok_next = nxt and near(nxt, nxt["start"] - b["end"])
        proj = None
        if ok_prev and ok_next and prev["project"] == nxt["project"]:
            proj = prev["project"]
        elif ok_prev and not nxt:
            proj = prev["project"]
        if proj:
            b.update(type="project", project=proj, confidence=60, source="session",
                     reason="kontekst sesji (otoczenie tego samego projektu)")
    return blocks


def suggest_rule(b):
    """Propozycja reguły po ręcznej poprawce."""
    if b.get("path"):
        folder = re.split(r"[\\/]", b["path"])
        if len(folder) > 1:
            return {"field": "path", "pattern": re.escape("/".join(folder[:-1]).replace("\\", "/")).replace("/", "[\\\\/]")}
    fname = ""
    m = re.search(r'([^\\/:*?"<>|\[\]]+?)\.[A-Za-z0-9]{2,5}\b', b.get("title") or "")
    if m:
        fname = re.sub(r"[ _-]*v?\d+$", "", m.group(1).strip(" -–—"), flags=re.I)
    if fname and len(fname) >= 4:
        return {"field": "title", "pattern": re.escape(fname)}
    if b.get("url"):
        d = b.get("domain", "")
        seg = [s for s in re.sub(r"^[a-z]+://[^/]+", "", b["url"]).split("/") if s][:2]
        return {"field": "url", "pattern": re.escape(d + ("/" + "/".join(seg) if seg else ""))}
    return {"field": "title", "pattern": re.escape((b.get("title") or "")[:40])}

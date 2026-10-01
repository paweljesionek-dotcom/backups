import json
import os
from pathlib import Path

HOME = Path(os.environ.get("TT_HOME", Path.home() / ".timetracker"))

DEFAULTS = {
    "device_name": "",
    "sample_seconds": 5,
    "idle_seconds": 180,
    "review_below": 80,
    "min_block_seconds": 5,
    "session_inherit_seconds": 300,
    "entry_mode": "daily",            # daily | blocks
    "round_minutes": 15,
    "general_project": "",
    "export": {"url": "", "token": "", "auth_header": "Authorization", "auth_prefix": "Bearer "},
    "export_brands": [],              # puste = wszystkie marki; np. ["we.make"]
    "server_url": "",                 # puste = tryb lokalny
    "device_token": "",
    "ingest_tokens": {},              # serwer: {"MacBook": "token", "PC biuro": "token"}
    "panel_password": "",
    "local_port": 47800,
    "panel_port": 8765,
    "local_token": "zmien-mnie",
    "raw_retention_days": 90,
    "ai": {"enabled": False, "model": "claude-haiku-4-5-20251001", "api_key": ""},
    "meeting_apps": ["zoom", "teams", "webex", "slack huddle"],
    "meeting_title_patterns": ["Meet -", "Google Meet", "Zoom Meeting"],
    "browsers": ["chrome", "msedge", "edge", "brave", "arc", "safari", "firefox", "opera", "vivaldi"],
    "unproductive": {
        "domains": ["facebook.com", "instagram.com", "youtube.com", "tiktok.com", "x.com",
                    "twitter.com", "reddit.com", "onet.pl", "wp.pl", "interia.pl", "allegro.pl"],
        "apps": ["steam", "spotify"],
    },
    "private": {
        "domains": [],
        "apps": ["1password", "keepass", "bitwarden"],
        "title_patterns": ["(?i)bank", "(?i)logowanie do banku"],
    },
    "projects": [],
    "rules": [],
}


def _merge(base, extra):
    out = dict(base)
    for k, v in extra.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def config_path():
    return Path(os.environ.get("TT_CONFIG", HOME / "config.json"))


def load(path=None):
    p = Path(path) if path else config_path()
    cfg = dict(DEFAULTS)
    if p.exists():
        cfg = _merge(DEFAULTS, json.loads(p.read_text(encoding="utf-8")))
    if not cfg["device_name"]:
        import socket
        cfg["device_name"] = socket.gethostname()
    return cfg


def db_path():
    HOME.mkdir(parents=True, exist_ok=True)
    return Path(os.environ.get("TT_DB", HOME / "tracker.db"))


STARTER = {
    "projects": [
        {"code": "WM-001", "name": "Przykładowy projekt we.make", "brand": "we.make", "client": "Klient",
         "keywords": ["NazwaKlienta"], "paths": []},
        {"code": "10D-001", "name": "Przykładowy projekt 10design", "brand": "10design", "client": "Klient",
         "keywords": [], "paths": []},
    ],
    "rules": [],
}


def ensure_config():
    """Pierwsze uruchomienie: tworzy config.json, który potem edytujesz w panelu (Ustawienia)."""
    p = config_path()
    if not p.exists():
        import socket
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"device_name": socket.gethostname(), **STARTER}, indent=2, ensure_ascii=False),
                     encoding="utf-8")
    return p

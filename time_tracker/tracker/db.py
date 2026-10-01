import json
import sqlite3
import threading

SCHEMA = """
CREATE TABLE IF NOT EXISTS devices(
  name TEXT PRIMARY KEY, os TEXT, last_seen INTEGER);
CREATE TABLE IF NOT EXISTS raw_events(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  device TEXT NOT NULL, start INTEGER NOT NULL, end INTEGER NOT NULL,
  app TEXT, title TEXT, path TEXT, url TEXT, domain TEXT,
  private INTEGER DEFAULT 0, idle_s INTEGER DEFAULT 0, synced INTEGER DEFAULT 0,
  UNIQUE(device, start));
CREATE TABLE IF NOT EXISTS activity_blocks(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  day TEXT NOT NULL, start INTEGER NOT NULL, end INTEGER NOT NULL,
  device TEXT, app TEXT, title TEXT, path TEXT, url TEXT, domain TEXT,
  type TEXT NOT NULL, project TEXT, confidence INTEGER DEFAULT 0,
  source TEXT, reason TEXT, locked INTEGER DEFAULT 0, note TEXT);
CREATE INDEX IF NOT EXISTS ix_blocks_day ON activity_blocks(day);
CREATE TABLE IF NOT EXISTS projects(
  code TEXT PRIMARY KEY, name TEXT, brand TEXT, client TEXT,
  keywords TEXT DEFAULT '[]', paths TEXT DEFAULT '[]',
  active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS rules(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  field TEXT NOT NULL, pattern TEXT NOT NULL, project TEXT, type TEXT,
  priority INTEGER DEFAULT 50, from_correction INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS ai_cache(
  key TEXT PRIMARY KEY, project TEXT, type TEXT, confidence INTEGER, reason TEXT);
CREATE TABLE IF NOT EXISTS days(day TEXT PRIMARY KEY, approved_at INTEGER);
CREATE TABLE IF NOT EXISTS time_entries(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  day TEXT NOT NULL, key TEXT NOT NULL, project TEXT, seconds INTEGER,
  start INTEGER, description TEXT, status TEXT DEFAULT 'pending',
  exported_at INTEGER, UNIQUE(day, key));
"""


class DB:
    def __init__(self, path):
        self.conn = sqlite3.connect(str(path), check_same_thread=False, timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.conn.executescript(SCHEMA)
            self.conn.commit()

    def q(self, sql, args=()):
        with self.lock:
            return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    def one(self, sql, args=()):
        rows = self.q(sql, args)
        return rows[0] if rows else None

    def x(self, sql, args=()):
        with self.lock:
            cur = self.conn.execute(sql, args)
            self.conn.commit()
            return cur.lastrowid

    # --- projekty z konfiguracji ---
    def sync_projects(self, projects):
        with self.lock:
            codes = [p["code"] for p in projects]
            self.conn.execute("UPDATE projects SET active=0")
            if codes:
                self.conn.execute("UPDATE projects SET active=1 WHERE code IN (%s)" % ",".join("?" * len(codes)), codes)
            for p in projects:
                self.conn.execute(
                    """INSERT INTO projects(code,name,brand,client,keywords,paths)
                       VALUES(?,?,?,?,?,?)
                       ON CONFLICT(code) DO UPDATE SET name=excluded.name, brand=excluded.brand,
                         client=excluded.client, keywords=excluded.keywords, paths=excluded.paths, active=1""",
                    (p["code"], p.get("name", p["code"]), p.get("brand", ""), p.get("client", ""),
                     json.dumps(p.get("keywords", []), ensure_ascii=False),
                     json.dumps(p.get("paths", []), ensure_ascii=False)))
            self.conn.commit()

    def projects(self):
        out = self.q("SELECT * FROM projects WHERE active=1 ORDER BY brand, code")
        for p in out:
            p["keywords"] = json.loads(p["keywords"] or "[]")
            p["paths"] = json.loads(p["paths"] or "[]")
        return out

    def rules(self, cfg_rules=()):
        rows = self.q("SELECT field,pattern,project,type,priority FROM rules")
        return sorted(list(cfg_rules) + rows, key=lambda r: -int(r.get("priority", 50)))

    def upsert_raw(self, ev):
        self.x(
            """INSERT INTO raw_events(device,start,end,app,title,path,url,domain,private,idle_s,synced)
               VALUES(:device,:start,:end,:app,:title,:path,:url,:domain,:private,:idle_s,:synced)
               ON CONFLICT(device,start) DO UPDATE SET end=excluded.end, idle_s=excluded.idle_s,
                 synced=excluded.synced""",
            {"private": 0, "idle_s": 0, "synced": 0, "path": "", "url": "", "domain": "", **ev})

"""Local SQLite state: which (file, revision) pairs are already backed up."""

import sqlite3
from contextlib import closing
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS backed_up_versions (
    file_id TEXT NOT NULL,
    revision_id TEXT NOT NULL,
    notion_page_id TEXT NOT NULL,
    file_name TEXT NOT NULL,
    backed_up_at TIMESTAMP NOT NULL,
    PRIMARY KEY (file_id, revision_id)
);
"""


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL;")
    with closing(conn.cursor()) as cur:
        cur.execute(SCHEMA)
    conn.commit()
    return conn


def is_backed_up(conn: sqlite3.Connection, file_id: str, revision_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM backed_up_versions WHERE file_id = ? AND revision_id = ?",
        (file_id, revision_id),
    ).fetchone()
    return row is not None


def record_backup(
    conn: sqlite3.Connection,
    file_id: str,
    revision_id: str,
    notion_page_id: str,
    file_name: str,
    backed_up_at: str = "",
) -> None:
    backed_up_at = backed_up_at or datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT OR REPLACE INTO backed_up_versions "
        "(file_id, revision_id, notion_page_id, file_name, backed_up_at) VALUES (?, ?, ?, ?, ?)",
        (file_id, revision_id, notion_page_id, file_name, backed_up_at),
    )
    conn.commit()


def forget_page(conn: sqlite3.Connection, notion_page_id: str) -> None:
    """Drop local rows for a page once it has been archived in Notion (retention)."""
    conn.execute("DELETE FROM backed_up_versions WHERE notion_page_id = ?", (notion_page_id,))
    conn.commit()

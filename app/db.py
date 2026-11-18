import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  platform TEXT NOT NULL CHECK (platform IN ('linkedin','instagram')),
  content TEXT NOT NULL,
  media_urls TEXT NOT NULL DEFAULT '[]',
  media_type TEXT NOT NULL DEFAULT 'none' CHECK (media_type IN ('none','image','carousel','video')),
  scheduled_at TEXT,
  status TEXT NOT NULL DEFAULT 'draft'
    CHECK (status IN ('draft','scheduled','publishing','published','failed')),
  attempts INTEGER NOT NULL DEFAULT 0,
  error TEXT,
  external_id TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_posts_due ON posts(status, scheduled_at);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    with connect() as c:
        c.executescript(SCHEMA)


def row_to_dict(r: sqlite3.Row) -> dict:
    d = dict(r)
    d["media_urls"] = json.loads(d["media_urls"])
    return d

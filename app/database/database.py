"""
SQLite persistence (PRD 5.7). Raw sqlite3, no ORM, single table.
"""
import sqlite3
from datetime import datetime, timezone

from app.config import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT,
    source TEXT NOT NULL,
    title TEXT,
    author TEXT,
    original_text TEXT NOT NULL,
    summary TEXT NOT NULL,
    created_at TEXT NOT NULL,
    merged_from TEXT
);
"""


def init_db() -> None:
    with sqlite3.connect(config.db_path) as conn:
        conn.execute(_SCHEMA)


def save_summary(content: dict, summary_text: str) -> int:
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(config.db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO summaries (url, source, title, author, original_text, summary, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                content.get("url"),
                content["source"],
                content.get("title"),
                content.get("author"),
                content["text"],
                summary_text,
                now,
            ),
        )
        return cursor.lastrowid

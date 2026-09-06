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


def get_recent(limit: int = 10) -> list[dict]:
    with sqlite3.connect(config.db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, title, summary FROM summaries ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_by_id(row_id: int) -> dict | None:
    with sqlite3.connect(config.db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM summaries WHERE id = ?", (row_id,)).fetchone()
    return dict(row) if row else None


def update_merged_summary(existing_id: int, summary_text: str, merged_id: int) -> None:
    """Absorb `merged_id` into `existing_id` (PRD 5.5 step 4): replace the
    existing row's summary, bump created_at, and record the merged-in id."""
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(config.db_path) as conn:
        row = conn.execute(
            "SELECT merged_from FROM summaries WHERE id = ?", (existing_id,)
        ).fetchone()
        existing_merged_from = row[0] if row else None
        merged_ids = existing_merged_from.split(",") if existing_merged_from else []
        merged_ids.append(str(merged_id))
        conn.execute(
            "UPDATE summaries SET summary = ?, created_at = ?, merged_from = ? WHERE id = ?",
            (summary_text, now, ",".join(merged_ids), existing_id),
        )

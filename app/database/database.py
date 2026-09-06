"""
SQLite persistence (PRD 5.7). Raw sqlite3, no ORM, single table.

PRD V2 multi-user revision: every row belongs to one Telegram user_id, and
every read/write is scoped to the caller's own user_id — passed explicitly
into every function rather than inferred, so it's never possible to
accidentally query across users. get_by_id in particular double-checks
user_id in its WHERE clause (not just id) specifically so one user can
never view, merge, undo, or delete another user's row even if they guessed
or somehow learned its numeric id.
"""
import sqlite3
from datetime import datetime, timezone

from app.config import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    url TEXT,
    source TEXT NOT NULL,
    title TEXT,
    author TEXT,
    original_text TEXT NOT NULL,
    summary TEXT NOT NULL,
    created_at TEXT NOT NULL,
    merged_from TEXT,
    previous_summary TEXT
);
"""

# Per-user Gemini API keys (PRD V2 multi-user cost revision). Stored in
# plain SQLite, same as everything else in this project — no encryption at
# rest. Reasonable for a small allowlist of people the owner knows, worth
# knowing if the allowlist ever grows past that.
_USER_SETTINGS_SCHEMA = """
CREATE TABLE IF NOT EXISTS user_settings (
    user_id INTEGER PRIMARY KEY,
    gemini_api_key TEXT
);
"""


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row[1] == column for row in rows)


def init_db() -> None:
    with sqlite3.connect(config.db_path) as conn:
        conn.execute(_SCHEMA)
        conn.execute(_USER_SETTINGS_SCHEMA)
        # CREATE TABLE IF NOT EXISTS doesn't add columns to an already-existing
        # table — migrate databases created before these columns existed.
        if not _column_exists(conn, "summaries", "previous_summary"):
            conn.execute("ALTER TABLE summaries ADD COLUMN previous_summary TEXT")
        if not _column_exists(conn, "summaries", "user_id"):
            conn.execute("ALTER TABLE summaries ADD COLUMN user_id INTEGER")
            # Pre-existing rows predate multi-user support and belong to
            # whoever was the sole authorized user — by convention, the
            # first id in AUTHORIZED_USER_IDS after upgrading.
            if config.authorized_user_ids:
                conn.execute(
                    "UPDATE summaries SET user_id = ? WHERE user_id IS NULL",
                    (config.authorized_user_ids[0],),
                )


def save_summary(content: dict, summary_text: str, user_id: int) -> int:
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(config.db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO summaries (user_id, url, source, title, author, original_text, summary, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
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


def get_recent(user_id: int, limit: int = 10) -> list[dict]:
    with sqlite3.connect(config.db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, title, summary FROM summaries WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def get_by_id(row_id: int, user_id: int) -> dict | None:
    with sqlite3.connect(config.db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM summaries WHERE id = ? AND user_id = ?", (row_id, user_id)
        ).fetchone()
    return dict(row) if row else None


def list_items(user_id: int, limit: int = 10) -> list[dict]:
    with sqlite3.connect(config.db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, title, original_text, created_at FROM summaries "
            "WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def search_items(user_id: int, keyword: str, limit: int = 10) -> tuple[list[dict], int]:
    """Case-insensitive substring search across title, summary, and
    original_text, scoped to one user. Returns (matches limited to
    `limit`, total match count)."""
    pattern = f"%{keyword}%"
    condition = "user_id = ? AND (title LIKE ? OR summary LIKE ? OR original_text LIKE ?)"
    params = (user_id, pattern, pattern, pattern)
    with sqlite3.connect(config.db_path) as conn:
        conn.row_factory = sqlite3.Row
        total = conn.execute(
            f"SELECT COUNT(*) AS c FROM summaries WHERE {condition}", params
        ).fetchone()["c"]
        rows = conn.execute(
            f"SELECT id, title, original_text, created_at FROM summaries "
            f"WHERE {condition} ORDER BY id DESC LIMIT ?",
            params + (limit,),
        ).fetchall()
    return [dict(row) for row in rows], total


def update_merged_summary(existing_id: int, summary_text: str, merged_id: int, user_id: int) -> None:
    """Absorb `merged_id` into `existing_id` (PRD 5.5 step 4): replace the
    existing row's summary, bump created_at, and record the merged-in id.
    The pre-merge summary is snapshotted into `previous_summary` so a single
    /undo can restore it (PRD V2 2.3) — one level, not a full history stack.
    Both ids must already be confirmed to belong to `user_id` by the caller
    (via get_by_id) — this only re-checks on the UPDATE itself as a second
    line of defense."""
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(config.db_path) as conn:
        row = conn.execute(
            "SELECT summary, merged_from FROM summaries WHERE id = ? AND user_id = ?",
            (existing_id, user_id),
        ).fetchone()
        previous_summary = row[0] if row else None
        existing_merged_from = row[1] if row else None
        merged_ids = existing_merged_from.split(",") if existing_merged_from else []
        merged_ids.append(str(merged_id))
        conn.execute(
            """
            UPDATE summaries
            SET summary = ?, created_at = ?, merged_from = ?, previous_summary = ?
            WHERE id = ? AND user_id = ?
            """,
            (summary_text, now, ",".join(merged_ids), previous_summary, existing_id, user_id),
        )


def delete_item(row_id: int, user_id: int) -> bool:
    with sqlite3.connect(config.db_path) as conn:
        cursor = conn.execute(
            "DELETE FROM summaries WHERE id = ? AND user_id = ?", (row_id, user_id)
        )
        return cursor.rowcount > 0


def undo_merge(row_id: int, previous_summary: str, user_id: int) -> None:
    """Revert a merged entry back to its pre-merge summary. `previous_summary`
    is left in place afterward (no history stack) — calling this again just
    reapplies the same pre-merge state rather than stepping further back."""
    with sqlite3.connect(config.db_path) as conn:
        conn.execute(
            "UPDATE summaries SET summary = ?, merged_from = NULL WHERE id = ? AND user_id = ?",
            (previous_summary, row_id, user_id),
        )


def get_user_api_key(user_id: int) -> str | None:
    with sqlite3.connect(config.db_path) as conn:
        row = conn.execute(
            "SELECT gemini_api_key FROM user_settings WHERE user_id = ?", (user_id,)
        ).fetchone()
    return row[0] if row and row[0] else None


def set_user_api_key(user_id: int, api_key: str) -> None:
    with sqlite3.connect(config.db_path) as conn:
        conn.execute(
            "INSERT INTO user_settings (user_id, gemini_api_key) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET gemini_api_key = excluded.gemini_api_key",
            (user_id, api_key),
        )


def resolve_gemini_api_key(user_id: int) -> str | None:
    """A personal key (set via /setkey) always wins. Otherwise, only the
    first id in AUTHORIZED_USER_IDS (the original owner) falls back to the
    shared .env key — every other invited user must set their own, which is
    the entire point: nobody but the owner can ever consume the owner's key."""
    personal_key = get_user_api_key(user_id)
    if personal_key:
        return personal_key
    if config.authorized_user_ids and user_id == config.authorized_user_ids[0]:
        return config.gemini_api_key or None
    return None

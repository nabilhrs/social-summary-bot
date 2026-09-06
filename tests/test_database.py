import sqlite3

import pytest

from app.database import database


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = str(tmp_path / "test.db")
    monkeypatch.setattr(database.config, "db_path", path)
    database.init_db()
    return path


def test_init_db_creates_table(db_path):
    with sqlite3.connect(db_path) as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='summaries'"
        ).fetchall()
    assert tables


def test_save_summary_persists_fields(db_path):
    content = {
        "title": "A Title",
        "author": "Jane Doe",
        "source": "web",
        "url": "https://example.com/a",
        "text": "original body",
    }
    row_id = database.save_summary(content, "TL;DR: summary text")

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM summaries WHERE id = ?", (row_id,)).fetchone()

    assert row["url"] == "https://example.com/a"
    assert row["source"] == "web"
    assert row["title"] == "A Title"
    assert row["author"] == "Jane Doe"
    assert row["original_text"] == "original body"
    assert row["summary"] == "TL;DR: summary text"
    assert row["created_at"]
    assert row["merged_from"] is None


def test_save_summary_handles_pasted_text_nulls(db_path):
    content = {
        "title": None,
        "author": None,
        "source": "pasted_text",
        "url": None,
        "text": "pasted body",
    }
    row_id = database.save_summary(content, "TL;DR: summary text")

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM summaries WHERE id = ?", (row_id,)).fetchone()

    assert row["url"] is None
    assert row["title"] is None
    assert row["author"] is None

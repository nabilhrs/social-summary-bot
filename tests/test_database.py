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


def _make_content(title, text):
    return {"title": title, "author": None, "source": "pasted_text", "url": None, "text": text}


def test_get_recent_returns_newest_first(db_path):
    first_id = database.save_summary(_make_content("First", "a"), "TL;DR: first")
    second_id = database.save_summary(_make_content("Second", "b"), "TL;DR: second")

    recent = database.get_recent(limit=10)

    assert [item["id"] for item in recent] == [second_id, first_id]
    assert recent[0] == {"id": second_id, "title": "Second", "summary": "TL;DR: second"}


def test_get_recent_respects_limit(db_path):
    for i in range(5):
        database.save_summary(_make_content(f"Item {i}", "x"), "TL;DR: x")

    assert len(database.get_recent(limit=2)) == 2


def test_get_by_id_returns_full_row(db_path):
    row_id = database.save_summary(_make_content("Title", "full body"), "TL;DR: summary")

    row = database.get_by_id(row_id)

    assert row["title"] == "Title"
    assert row["original_text"] == "full body"


def test_get_by_id_missing_returns_none(db_path):
    assert database.get_by_id(999) is None


def test_update_merged_summary_replaces_summary_and_records_merged_id(db_path):
    old_id = database.save_summary(_make_content("Old", "old body"), "TL;DR: old")
    new_id = database.save_summary(_make_content("New", "new body"), "TL;DR: new")

    database.update_merged_summary(old_id, "TL;DR: merged", new_id)

    row = database.get_by_id(old_id)
    assert row["summary"] == "TL;DR: merged"
    assert row["merged_from"] == str(new_id)


def test_update_merged_summary_appends_to_existing_merged_from(db_path):
    old_id = database.save_summary(_make_content("Old", "old body"), "TL;DR: old")
    second_id = database.save_summary(_make_content("Second", "b"), "TL;DR: b")
    third_id = database.save_summary(_make_content("Third", "c"), "TL;DR: c")

    database.update_merged_summary(old_id, "TL;DR: merged once", second_id)
    database.update_merged_summary(old_id, "TL;DR: merged twice", third_id)

    row = database.get_by_id(old_id)
    assert row["merged_from"] == f"{second_id},{third_id}"

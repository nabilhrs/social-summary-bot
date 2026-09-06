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


def test_list_items_returns_newest_first(db_path):
    first_id = database.save_summary(_make_content("First", "a"), "TL;DR: first")
    second_id = database.save_summary(_make_content("Second", "b"), "TL;DR: second")

    items = database.list_items(limit=10)

    assert [item["id"] for item in items] == [second_id, first_id]
    assert items[0]["title"] == "Second"
    assert items[0]["original_text"] == "b"
    assert items[0]["created_at"]


def test_list_items_respects_limit(db_path):
    for i in range(5):
        database.save_summary(_make_content(f"Item {i}", "x"), "TL;DR: x")

    assert len(database.list_items(limit=2)) == 2


def test_list_items_empty_db(db_path):
    assert database.list_items(limit=10) == []


def test_search_items_matches_title(db_path):
    match_id = database.save_summary(_make_content("Job interview tips", "x"), "TL;DR: x")
    database.save_summary(_make_content("Nasi lemak recipe", "y"), "TL;DR: y")

    matches, total = database.search_items("interview")

    assert total == 1
    assert [item["id"] for item in matches] == [match_id]


def test_search_items_matches_summary_and_original_text(db_path):
    by_summary = database.save_summary(_make_content("A", "unrelated body"), "TL;DR: mentions STAR method")
    by_text = database.save_summary(_make_content("B", "talks about STAR method here"), "TL;DR: unrelated")
    database.save_summary(_make_content("C", "nothing relevant"), "TL;DR: nothing relevant")

    matches, total = database.search_items("STAR")

    assert total == 2
    assert {item["id"] for item in matches} == {by_summary, by_text}


def test_search_items_is_case_insensitive(db_path):
    match_id = database.save_summary(_make_content("Interview Tips", "x"), "TL;DR: x")

    matches, total = database.search_items("interview")

    assert total == 1
    assert matches[0]["id"] == match_id


def test_search_items_no_match(db_path):
    database.save_summary(_make_content("Something", "x"), "TL;DR: x")

    matches, total = database.search_items("nonexistent-keyword")

    assert matches == []
    assert total == 0


def test_search_items_respects_limit_but_reports_total(db_path):
    for i in range(5):
        database.save_summary(_make_content(f"Interview note {i}", "x"), "TL;DR: x")

    matches, total = database.search_items("interview", limit=2)

    assert len(matches) == 2
    assert total == 5


def test_init_db_migrates_existing_table_missing_previous_summary(tmp_path, monkeypatch):
    path = str(tmp_path / "legacy.db")
    monkeypatch.setattr(database.config, "db_path", path)

    # Simulate a pre-migration database (no previous_summary column).
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT,
                source TEXT NOT NULL,
                title TEXT,
                author TEXT,
                original_text TEXT NOT NULL,
                summary TEXT NOT NULL,
                created_at TEXT NOT NULL,
                merged_from TEXT
            )
            """
        )

    database.init_db()

    with sqlite3.connect(path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(summaries)").fetchall()}
    assert "previous_summary" in columns


def test_init_db_is_idempotent_with_previous_summary_already_present(db_path):
    # Column already exists (fixture already ran init_db once) — running again
    # must not raise "duplicate column name".
    database.init_db()


def test_update_merged_summary_snapshots_previous_summary(db_path):
    old_id = database.save_summary(_make_content("Old", "old body"), "TL;DR: old")
    new_id = database.save_summary(_make_content("New", "new body"), "TL;DR: new")

    database.update_merged_summary(old_id, "TL;DR: merged", new_id)

    row = database.get_by_id(old_id)
    assert row["previous_summary"] == "TL;DR: old"


def test_delete_item_removes_row_and_returns_true(db_path):
    row_id = database.save_summary(_make_content("Title", "body"), "TL;DR: x")

    assert database.delete_item(row_id) is True
    assert database.get_by_id(row_id) is None


def test_delete_item_missing_id_returns_false(db_path):
    assert database.delete_item(999) is False


def test_undo_merge_restores_summary_and_clears_merged_from(db_path):
    old_id = database.save_summary(_make_content("Old", "old body"), "TL;DR: old")
    new_id = database.save_summary(_make_content("New", "new body"), "TL;DR: new")
    database.update_merged_summary(old_id, "TL;DR: merged", new_id)

    row = database.get_by_id(old_id)
    database.undo_merge(old_id, row["previous_summary"])

    reverted = database.get_by_id(old_id)
    assert reverted["summary"] == "TL;DR: old"
    assert reverted["merged_from"] is None


def test_undo_merge_is_repeatable(db_path):
    old_id = database.save_summary(_make_content("Old", "old body"), "TL;DR: old")
    new_id = database.save_summary(_make_content("New", "new body"), "TL;DR: new")
    database.update_merged_summary(old_id, "TL;DR: merged", new_id)
    row = database.get_by_id(old_id)

    database.undo_merge(old_id, row["previous_summary"])
    database.undo_merge(old_id, row["previous_summary"])

    reverted = database.get_by_id(old_id)
    assert reverted["summary"] == "TL;DR: old"

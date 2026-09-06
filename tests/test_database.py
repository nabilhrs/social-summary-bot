import sqlite3

import pytest

from app.database import database

USER = 111
OTHER_USER = 222


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = str(tmp_path / "test.db")
    monkeypatch.setattr(database.config, "db_path", path)
    database.init_db()
    return path


def _make_content(title, text):
    return {"title": title, "author": None, "source": "pasted_text", "url": None, "text": text}


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
    row_id = database.save_summary(content, "TL;DR: summary text", USER)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM summaries WHERE id = ?", (row_id,)).fetchone()

    assert row["user_id"] == USER
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
    row_id = database.save_summary(content, "TL;DR: summary text", USER)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM summaries WHERE id = ?", (row_id,)).fetchone()

    assert row["url"] is None
    assert row["title"] is None
    assert row["author"] is None


def test_get_recent_returns_newest_first(db_path):
    first_id = database.save_summary(_make_content("First", "a"), "TL;DR: first", USER)
    second_id = database.save_summary(_make_content("Second", "b"), "TL;DR: second", USER)

    recent = database.get_recent(USER, limit=10)

    assert [item["id"] for item in recent] == [second_id, first_id]
    assert recent[0] == {"id": second_id, "title": "Second", "summary": "TL;DR: second"}


def test_get_recent_respects_limit(db_path):
    for i in range(5):
        database.save_summary(_make_content(f"Item {i}", "x"), "TL;DR: x", USER)

    assert len(database.get_recent(USER, limit=2)) == 2


def test_get_recent_excludes_other_users_items(db_path):
    database.save_summary(_make_content("Mine", "a"), "TL;DR: mine", USER)
    database.save_summary(_make_content("Theirs", "b"), "TL;DR: theirs", OTHER_USER)

    recent = database.get_recent(USER, limit=10)

    assert [item["title"] for item in recent] == ["Mine"]


def test_get_by_id_returns_full_row(db_path):
    row_id = database.save_summary(_make_content("Title", "full body"), "TL;DR: summary", USER)

    row = database.get_by_id(row_id, USER)

    assert row["title"] == "Title"
    assert row["original_text"] == "full body"


def test_get_by_id_missing_returns_none(db_path):
    assert database.get_by_id(999, USER) is None


def test_get_by_id_wrong_user_returns_none(db_path):
    row_id = database.save_summary(_make_content("Title", "body"), "TL;DR: x", USER)

    assert database.get_by_id(row_id, OTHER_USER) is None


def test_update_merged_summary_replaces_summary_and_records_merged_id(db_path):
    old_id = database.save_summary(_make_content("Old", "old body"), "TL;DR: old", USER)
    new_id = database.save_summary(_make_content("New", "new body"), "TL;DR: new", USER)

    database.update_merged_summary(old_id, "TL;DR: merged", new_id, USER)

    row = database.get_by_id(old_id, USER)
    assert row["summary"] == "TL;DR: merged"
    assert row["merged_from"] == str(new_id)


def test_update_merged_summary_appends_to_existing_merged_from(db_path):
    old_id = database.save_summary(_make_content("Old", "old body"), "TL;DR: old", USER)
    second_id = database.save_summary(_make_content("Second", "b"), "TL;DR: b", USER)
    third_id = database.save_summary(_make_content("Third", "c"), "TL;DR: c", USER)

    database.update_merged_summary(old_id, "TL;DR: merged once", second_id, USER)
    database.update_merged_summary(old_id, "TL;DR: merged twice", third_id, USER)

    row = database.get_by_id(old_id, USER)
    assert row["merged_from"] == f"{second_id},{third_id}"


def test_update_merged_summary_does_not_touch_another_users_row(db_path):
    other_id = database.save_summary(_make_content("Theirs", "body"), "TL;DR: theirs", OTHER_USER)

    # Attempting to "merge into" someone else's row as the wrong user must be a no-op.
    database.update_merged_summary(other_id, "TL;DR: hijacked", other_id, USER)

    row = database.get_by_id(other_id, OTHER_USER)
    assert row["summary"] == "TL;DR: theirs"


def test_list_items_returns_newest_first(db_path):
    first_id = database.save_summary(_make_content("First", "a"), "TL;DR: first", USER)
    second_id = database.save_summary(_make_content("Second", "b"), "TL;DR: second", USER)

    items = database.list_items(USER, limit=10)

    assert [item["id"] for item in items] == [second_id, first_id]
    assert items[0]["title"] == "Second"
    assert items[0]["original_text"] == "b"
    assert items[0]["created_at"]


def test_list_items_respects_limit(db_path):
    for i in range(5):
        database.save_summary(_make_content(f"Item {i}", "x"), "TL;DR: x", USER)

    assert len(database.list_items(USER, limit=2)) == 2


def test_list_items_empty_db(db_path):
    assert database.list_items(USER, limit=10) == []


def test_list_items_excludes_other_users_items(db_path):
    database.save_summary(_make_content("Mine", "a"), "TL;DR: mine", USER)
    database.save_summary(_make_content("Theirs", "b"), "TL;DR: theirs", OTHER_USER)

    items = database.list_items(USER, limit=10)

    assert [item["title"] for item in items] == ["Mine"]


def test_search_items_matches_title(db_path):
    match_id = database.save_summary(_make_content("Job interview tips", "x"), "TL;DR: x", USER)
    database.save_summary(_make_content("Nasi lemak recipe", "y"), "TL;DR: y", USER)

    matches, total = database.search_items(USER, "interview")

    assert total == 1
    assert [item["id"] for item in matches] == [match_id]


def test_search_items_matches_summary_and_original_text(db_path):
    by_summary = database.save_summary(_make_content("A", "unrelated body"), "TL;DR: mentions STAR method", USER)
    by_text = database.save_summary(_make_content("B", "talks about STAR method here"), "TL;DR: unrelated", USER)
    database.save_summary(_make_content("C", "nothing relevant"), "TL;DR: nothing relevant", USER)

    matches, total = database.search_items(USER, "STAR")

    assert total == 2
    assert {item["id"] for item in matches} == {by_summary, by_text}


def test_search_items_is_case_insensitive(db_path):
    match_id = database.save_summary(_make_content("Interview Tips", "x"), "TL;DR: x", USER)

    matches, total = database.search_items(USER, "interview")

    assert total == 1
    assert matches[0]["id"] == match_id


def test_search_items_no_match(db_path):
    database.save_summary(_make_content("Something", "x"), "TL;DR: x", USER)

    matches, total = database.search_items(USER, "nonexistent-keyword")

    assert matches == []
    assert total == 0


def test_search_items_respects_limit_but_reports_total(db_path):
    for i in range(5):
        database.save_summary(_make_content(f"Interview note {i}", "x"), "TL;DR: x", USER)

    matches, total = database.search_items(USER, "interview", limit=2)

    assert len(matches) == 2
    assert total == 5


def test_search_items_excludes_other_users_items(db_path):
    database.save_summary(_make_content("Interview tips", "x"), "TL;DR: x", USER)
    database.save_summary(_make_content("Interview notes", "y"), "TL;DR: y", OTHER_USER)

    matches, total = database.search_items(USER, "interview")

    assert total == 1


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


def test_init_db_migrates_and_backfills_user_id(tmp_path, monkeypatch):
    path = str(tmp_path / "legacy.db")
    monkeypatch.setattr(database.config, "db_path", path)
    monkeypatch.setattr(database.config, "authorized_user_ids", [USER, OTHER_USER])

    # Simulate a pre-multi-user database: no user_id column, one existing row.
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
                merged_from TEXT,
                previous_summary TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO summaries (source, original_text, summary, created_at) "
            "VALUES ('pasted_text', 'legacy body', 'TL;DR: legacy', '2026-01-01T00:00:00+00:00')"
        )

    database.init_db()

    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        columns = {row[1] for row in conn.execute("PRAGMA table_info(summaries)").fetchall()}
        row = conn.execute("SELECT * FROM summaries").fetchone()

    assert "user_id" in columns
    # First id in AUTHORIZED_USER_IDS owns any pre-existing, unowned rows.
    assert row["user_id"] == USER


def test_update_merged_summary_snapshots_previous_summary(db_path):
    old_id = database.save_summary(_make_content("Old", "old body"), "TL;DR: old", USER)
    new_id = database.save_summary(_make_content("New", "new body"), "TL;DR: new", USER)

    database.update_merged_summary(old_id, "TL;DR: merged", new_id, USER)

    row = database.get_by_id(old_id, USER)
    assert row["previous_summary"] == "TL;DR: old"


def test_delete_item_removes_row_and_returns_true(db_path):
    row_id = database.save_summary(_make_content("Title", "body"), "TL;DR: x", USER)

    assert database.delete_item(row_id, USER) is True
    assert database.get_by_id(row_id, USER) is None


def test_delete_item_missing_id_returns_false(db_path):
    assert database.delete_item(999, USER) is False


def test_delete_item_wrong_user_returns_false_and_does_not_delete(db_path):
    row_id = database.save_summary(_make_content("Title", "body"), "TL;DR: x", OTHER_USER)

    assert database.delete_item(row_id, USER) is False
    assert database.get_by_id(row_id, OTHER_USER) is not None


def test_undo_merge_restores_summary_and_clears_merged_from(db_path):
    old_id = database.save_summary(_make_content("Old", "old body"), "TL;DR: old", USER)
    new_id = database.save_summary(_make_content("New", "new body"), "TL;DR: new", USER)
    database.update_merged_summary(old_id, "TL;DR: merged", new_id, USER)

    row = database.get_by_id(old_id, USER)
    database.undo_merge(old_id, row["previous_summary"], USER)

    reverted = database.get_by_id(old_id, USER)
    assert reverted["summary"] == "TL;DR: old"
    assert reverted["merged_from"] is None


def test_undo_merge_is_repeatable(db_path):
    old_id = database.save_summary(_make_content("Old", "old body"), "TL;DR: old", USER)
    new_id = database.save_summary(_make_content("New", "new body"), "TL;DR: new", USER)
    database.update_merged_summary(old_id, "TL;DR: merged", new_id, USER)
    row = database.get_by_id(old_id, USER)

    database.undo_merge(old_id, row["previous_summary"], USER)
    database.undo_merge(old_id, row["previous_summary"], USER)

    reverted = database.get_by_id(old_id, USER)
    assert reverted["summary"] == "TL;DR: old"


def test_undo_merge_does_not_touch_another_users_row(db_path):
    other_id = database.save_summary(_make_content("Theirs", "body"), "TL;DR: theirs", OTHER_USER)

    database.undo_merge(other_id, "TL;DR: hijacked", USER)

    row = database.get_by_id(other_id, OTHER_USER)
    assert row["summary"] == "TL;DR: theirs"


def test_get_user_api_key_missing_returns_none(db_path):
    assert database.get_user_api_key(USER) is None


def test_set_and_get_user_api_key(db_path):
    database.set_user_api_key(USER, "my-secret-key")

    assert database.get_user_api_key(USER) == "my-secret-key"


def test_set_user_api_key_overwrites_existing(db_path):
    database.set_user_api_key(USER, "old-key")
    database.set_user_api_key(USER, "new-key")

    assert database.get_user_api_key(USER) == "new-key"


def test_set_user_api_key_is_scoped_per_user(db_path):
    database.set_user_api_key(USER, "users-key")
    database.set_user_api_key(OTHER_USER, "other-users-key")

    assert database.get_user_api_key(USER) == "users-key"
    assert database.get_user_api_key(OTHER_USER) == "other-users-key"


def test_resolve_gemini_api_key_prefers_personal_key(db_path, monkeypatch):
    monkeypatch.setattr(database.config, "authorized_user_ids", [USER])
    monkeypatch.setattr(database.config, "gemini_api_key", "owner-env-key")
    database.set_user_api_key(USER, "users-own-key")

    assert database.resolve_gemini_api_key(USER) == "users-own-key"


def test_resolve_gemini_api_key_owner_falls_back_to_env_key(db_path, monkeypatch):
    monkeypatch.setattr(database.config, "authorized_user_ids", [USER, OTHER_USER])
    monkeypatch.setattr(database.config, "gemini_api_key", "owner-env-key")

    assert database.resolve_gemini_api_key(USER) == "owner-env-key"


def test_resolve_gemini_api_key_non_owner_without_key_returns_none(db_path, monkeypatch):
    monkeypatch.setattr(database.config, "authorized_user_ids", [USER, OTHER_USER])
    monkeypatch.setattr(database.config, "gemini_api_key", "owner-env-key")

    assert database.resolve_gemini_api_key(OTHER_USER) is None


def test_resolve_gemini_api_key_non_owner_with_personal_key(db_path, monkeypatch):
    monkeypatch.setattr(database.config, "authorized_user_ids", [USER, OTHER_USER])
    monkeypatch.setattr(database.config, "gemini_api_key", "owner-env-key")
    database.set_user_api_key(OTHER_USER, "other-users-own-key")

    assert database.resolve_gemini_api_key(OTHER_USER) == "other-users-own-key"

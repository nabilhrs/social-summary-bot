import asyncio
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.bot import review
from app.bot.actions import build_item_actions_keyboard, keyboard_for_item
from app.bot.browse import ARCHIVED, build_menu, render_menu, render_page
from app.bot.formatting import format_full_item
from app.bot.review import (
    age_text,
    build_archived,
    build_question,
    build_revealed,
    handle_review_callback,
    handle_unarchive_callback,
    pick_note,
)
from app.database import database

USER = 111
NOW = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)


def _save(title, days_old, category=None):
    content = {"title": title, "author": None, "source": "pasted_text", "url": None, "text": "x"}
    item_id = database.save_summary(content, f"SUMMARY: about {title}", USER, category)
    created = (NOW - timedelta(days=days_old)).isoformat()
    with sqlite3.connect(database.config.db_path) as conn:
        conn.execute("UPDATE summaries SET created_at = ? WHERE id = ?", (created, item_id))
    return item_id


@pytest.mark.parametrize(
    "days, expected",
    [(0, "0 days ago"), (1, "1 day ago"), (9, "9 days ago"), (21, "3 weeks ago"), (90, "3 months ago"), (800, "2 years ago")],
)
def test_age_text(days, expected):
    assert age_text((NOW - timedelta(days=days)).isoformat(), NOW) == expected


def test_only_week_old_unarchived_notes_come_up():
    database.init_db()
    _save("Fresh", 2)
    archived = _save("Archived", 30)
    database.set_archived(archived, USER, True)
    old = _save("Old", 30)
    for _ in range(10):
        assert pick_note(USER, NOW)["id"] == old
    assert pick_note(USER, NOW, exclude_id=old) is None


def test_kept_notes_rest_for_a_month_and_unreviewed_come_first():
    kept = _save("Kept", 60)
    fresh = _save("Never reviewed", 60)
    database.mark_reviewed(kept, USER, (NOW - timedelta(days=40)).isoformat())
    for _ in range(10):
        assert pick_note(USER, NOW)["id"] == fresh  # unreviewed beats a long-ago review
    database.mark_reviewed(fresh, USER, (NOW - timedelta(days=2)).isoformat())
    assert pick_note(USER, NOW)["id"] == kept
    database.mark_reviewed(kept, USER, NOW.isoformat())
    assert pick_note(USER, NOW) is None


def test_question_hides_the_summary_until_revealed():
    item = database.get_by_id(_save("Kopi <spots>", 21, "Food"), USER)
    text, markup = build_question(item, NOW)
    assert "Do you remember this one?" in text
    assert "Kopi &lt;spots&gt;" in text and "📂 Food · saved 3 weeks ago" in text
    assert "about Kopi" not in text
    assert [b.callback_data for b in markup.inline_keyboard[0]] == [f"rev:show:{item['id']}", f"rev:skip:{item['id']}"]

    text, markup = build_revealed(item, NOW)
    assert "about Kopi" in text and "Still useful?" in text
    data = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert data == [f"rev:keep:{item['id']}", f"rev:arch:{item['id']}", f"rev:next:{item['id']}"]


def test_archived_notes_leave_list_but_not_search():
    keep = _save("Keep me", 30, "Food")
    gone = _save("Archive me", 30, "Food")
    database.set_archived(gone, USER, True)

    assert database.count_items(USER) == 1
    assert database.count_items(USER, category="Food") == 1
    assert database.count_items(USER, archived=True) == 1
    assert [i["id"] for i in database.list_page(USER, 0, 10, archived=True)] == [gone]
    assert database.get_categories(USER, include_archived=False) == [("Food", 1)]
    assert database.get_categories(USER) == [("Food", 2)]
    assert database.search_items(USER, "Archive me")[1] == 1
    assert database.get_random_item_before(USER, NOW.isoformat())["id"] == keep

    text, markup = asyncio.run(render_menu(USER))
    assert "📦 Archived (1)" in [b.text for row in markup.inline_keyboard for b in row]
    text, _ = asyncio.run(render_page(USER, 0, ARCHIVED, None))
    assert text.startswith("📦 Archived — 1 note(s)") and f"#{gone}" in text


def test_menu_still_shows_when_everything_is_archived():
    database.set_archived(_save("Only", 30), USER, True)
    text, markup = asyncio.run(render_menu(USER))
    assert markup is not None and "📦 Archived (1)" in str(markup.inline_keyboard)


def test_menu_without_archived_has_no_archive_button():
    _, markup = build_menu(3, [], 0)
    assert "Archived" not in str(markup.inline_keyboard)


def test_archived_note_gets_unarchive_button_and_label():
    item = database.get_by_id(_save("A", 30), USER)
    assert "unarch:" not in str(keyboard_for_item(item).inline_keyboard)
    database.set_archived(item["id"], USER, True)
    item = database.get_by_id(item["id"], USER)
    assert keyboard_for_item(item).inline_keyboard[0][0].callback_data == f"unarch:{item['id']}"
    assert "📦 Archived" in format_full_item(item)
    assert build_item_actions_keyboard(1) is not None


class _Query:
    def __init__(self, data):
        self.data = data
        self.edits = []
        self.answers = []
        self.message = SimpleNamespace(replies=[])

        async def reply_text(text, parse_mode=None, reply_markup=None):
            self.message.replies.append((text, reply_markup))

        self.message.reply_text = reply_text

    async def answer(self, text=None):
        self.answers.append(text)

    async def edit_message_text(self, text, parse_mode=None, reply_markup=None):
        self.edits.append((text, reply_markup))

    async def edit_message_reply_markup(self, reply_markup=None):
        self.edits.append((None, reply_markup))


@pytest.fixture
def tap(monkeypatch):
    monkeypatch.setattr(review.config, "is_authorized", lambda user_id: user_id == USER)

    def run(handler, data):
        query = _Query(data)
        asyncio.run(handler(SimpleNamespace(effective_user=SimpleNamespace(id=USER), callback_query=query), None))
        return query

    return run


def test_keep_archive_undo_flow(tap):
    item_id = _save("Flow", 30)

    revealed = tap(handle_review_callback, f"rev:show:{item_id}")
    assert "SUMMARY" not in revealed.edits[0][0] and "about Flow" in revealed.edits[0][0]

    kept = tap(handle_review_callback, f"rev:keep:{item_id}")
    assert kept.edits[0][0].startswith(f"👍 Kept #{item_id}")
    assert database.get_by_id(item_id, USER)["reviewed_at"] is not None

    archived = tap(handle_review_callback, f"rev:arch:{item_id}")
    assert archived.edits[0][0].startswith(f"📦 Archived #{item_id}")
    assert database.get_by_id(item_id, USER)["archived"] == 1

    tap(handle_review_callback, f"rev:undo:{item_id}")
    assert database.get_by_id(item_id, USER)["archived"] == 0


def test_skip_replaces_the_card_and_next_sends_a_new_one(tap):
    first, second = _save("One", 30), _save("Two", 30)
    skipped = tap(handle_review_callback, f"rev:skip:{first}")
    assert f"#{second} — Two" in skipped.edits[0][0]

    following = tap(handle_review_callback, f"rev:next:{second}")
    assert following.edits == [] and f"#{first} — One" in following.message.replies[0][0]

    database.set_archived(first, USER, True)
    empty = tap(handle_review_callback, f"rev:skip:{second}")
    assert empty.edits[0][0] == review.NOTHING_TO_REVIEW_TEXT


def test_unarchive_button(tap):
    item_id = _save("Back", 30)
    database.set_archived(item_id, USER, True)
    query = tap(handle_unarchive_callback, f"unarch:{item_id}")
    assert database.get_by_id(item_id, USER)["archived"] == 0
    assert query.answers == ["📤 Back in /list"]
    assert "unarch:" not in str(query.edits[0][1].inline_keyboard)


def test_review_is_registered():
    import main

    patterns = [
        h.pattern.pattern
        for handlers in main.build_app().handlers.values()
        for h in handlers
        if getattr(h, "callback", None) in (handle_review_callback, handle_unarchive_callback)
    ]
    for data in ("rev:show:1", "rev:skip:1", "rev:keep:1", "rev:arch:1", "rev:undo:1", "rev:next:1", "unarch:5"):
        assert any(re.match(p, data) for p in patterns)
    list_pattern = next(
        h.pattern.pattern
        for handlers in main.build_app().handlers.values()
        for h in handlers
        if getattr(getattr(h, "pattern", None), "pattern", "").startswith("^(lm|")
    )
    assert re.match(list_pattern, f"lp:0:{ARCHIVED}")
    assert "review" in [c.command for c in main._BOT_COMMANDS]

import asyncio
from types import SimpleNamespace

import pytest

from app.bot.actions import (
    NEW_CATEGORY_PROMPT,
    RENAME_PROMPT,
    apply_reply_edit,
    build_category_picker,
    build_item_actions_keyboard,
    parse_reply_prompt,
)
from app.database import database

USER = 111


def _buttons(markup):
    return [button for row in markup.inline_keyboard for button in row]


def test_item_actions_keyboard_callback_data():
    data = [button.callback_data for button in _buttons(build_item_actions_keyboard(12))]
    assert data == ["act:rename:12", "act:cat:12", "delconfirm:12"]


def test_category_picker_marks_current_and_offers_new():
    buttons = _buttons(build_category_picker(5, ["Career", "Food & Drink"], current="Career"))
    assert [b.text for b in buttons] == ["✅ Career", "Food & Drink", "➕ New category"]
    assert [b.callback_data for b in buttons] == ["setcat:5:Career", "setcat:5:Food & Drink", "act:newcat:5"]


def test_category_picker_data_fits_telegram_limit():
    long_name = "x" * 40  # clean_category caps names at 40 bytes
    button = _buttons(build_category_picker(9_999_999, [long_name], None))[0]
    assert len(button.callback_data.encode("utf-8")) <= 64


def test_parse_reply_prompt():
    assert parse_reply_prompt(RENAME_PROMPT.format(id=7)) == ("rename", 7)
    assert parse_reply_prompt(NEW_CATEGORY_PROMPT.format(id=3)) == ("category", 3)
    assert parse_reply_prompt("📂 Pick a category for #3:") is None
    assert parse_reply_prompt(None) is None


class _FakeMessage:
    def __init__(self, text, reply_to=None):
        self.text = text
        self.reply_to_message = reply_to
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append(text)


def _prompt(text, is_bot=True):
    return SimpleNamespace(text=text, from_user=SimpleNamespace(is_bot=is_bot))


@pytest.fixture
def item_id(tmp_path, monkeypatch):
    monkeypatch.setattr(database.config, "db_path", str(tmp_path / "t.db"))
    database.init_db()
    content = {"title": "Old", "author": None, "source": "pasted_text", "url": None, "text": "x"}
    database.save_summary(content, "s", USER, category="Food")
    return database.save_summary(content, "s", USER, category="Career")


def test_reply_to_rename_prompt_renames(item_id):
    message = _FakeMessage("  Better   title ", _prompt(RENAME_PROMPT.format(id=item_id)))
    assert asyncio.run(apply_reply_edit(message, USER)) is True
    assert database.get_by_id(item_id, USER)["title"] == "Better title"
    assert message.replies == [f"✏️ Renamed #{item_id} to: Better title"]


def test_reply_to_new_category_prompt_reuses_existing_spelling(item_id):
    message = _FakeMessage("food", _prompt(NEW_CATEGORY_PROMPT.format(id=item_id)))
    assert asyncio.run(apply_reply_edit(message, USER)) is True
    assert database.get_by_id(item_id, USER)["category"] == "Food"


def test_reply_for_another_users_item_changes_nothing(item_id):
    message = _FakeMessage("Hijack", _prompt(RENAME_PROMPT.format(id=item_id)))
    assert asyncio.run(apply_reply_edit(message, 999)) is True
    assert database.get_by_id(item_id, USER)["title"] == "Old"
    assert message.replies == [f"Couldn't find #{item_id} anymore."]


def test_plain_messages_and_replies_to_other_text_are_not_edits(item_id):
    assert asyncio.run(apply_reply_edit(_FakeMessage("hello"), USER)) is False
    assert asyncio.run(apply_reply_edit(_FakeMessage("hi", _prompt("some summary")), USER)) is False
    not_bot = _prompt(RENAME_PROMPT.format(id=item_id), is_bot=False)
    assert asyncio.run(apply_reply_edit(_FakeMessage("hi", not_bot), USER)) is False

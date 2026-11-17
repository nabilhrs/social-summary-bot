import asyncio
from types import SimpleNamespace

import pytest

from app.bot import categories as cat
from app.database import database

USER = 111


def _buttons(markup):
    return [b for row in markup.inline_keyboard for b in row]


def test_menu_buttons_carry_the_category_name():
    text, markup = cat.build_menu([("Career", 9), ("Pets & Animals", 2)])
    assert text == cat.MENU_TEXT
    assert [(b.text, b.callback_data) for b in _buttons(markup)] == [
        ("Career (9)", "catpick:Career"),
        ("Pets & Animals (2)", "catpick:Pets & Animals"),
    ]


def test_options_text_round_trips_the_category_name():
    text, markup = cat.build_options("Food & Drink", 12)
    assert cat.category_in(text, cat._OPTIONS_RE) == "Food & Drink"
    assert [b.callback_data for b in _buttons(markup)] == ["catopt:rename", "catopt:merge", "catopt:list", "catmenu"]


def test_merge_picker_excludes_itself_and_round_trips_the_source():
    text, markup = cat.build_merge_picker("Pets", 3, [("Pets", 3), ("Pets & Animals", 5), ("Career", 9)])
    assert cat.category_in(text, cat._MERGE_RE) == "Pets"
    assert [b.callback_data for b in _buttons(markup)] == ["catto:Pets & Animals", "catto:Career", "catpick:Pets"]


def test_button_data_fits_telegram_limit_for_the_longest_names():
    longest = "x" * 40  # clean_category caps names at 40 bytes
    _, markup = cat.build_menu([(longest, 1)])
    _, picker = cat.build_merge_picker("y", 1, [("y", 1), (longest, 1)])
    for button in _buttons(markup) + _buttons(picker):
        assert len(button.callback_data.encode("utf-8")) <= 64


def test_rename_prompt_round_trips():
    assert cat.category_in(cat.RENAME_PROMPT.format(name="Pets"), cat._RENAME_PROMPT_RE) == "Pets"


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(database.config, "db_path", str(tmp_path / "c.db"))
    database.init_db()
    content = {"title": "T", "author": None, "source": "pasted_text", "url": None, "text": "x"}
    for category in ["Pets", "Pets", "Pets & Animals", "Career"]:
        database.save_summary(content, "s", USER, category=category)
    database.save_summary(content, "s", 999, category="Pets")


def test_rename_category_moves_only_the_users_items(db):
    assert database.rename_category(USER, "Pets", "Pets & Animals") == 2
    assert dict(database.get_categories(USER)) == {"Pets & Animals": 3, "Career": 1}
    assert dict(database.get_categories(999)) == {"Pets": 1}


class _Message(SimpleNamespace):
    async def reply_text(self, text, **kwargs):
        self.replies.append(text)


def _reply(text, prompt):
    return _Message(text=text, replies=[], reply_to_message=SimpleNamespace(text=prompt, from_user=SimpleNamespace(is_bot=True)))


def test_reply_renames_a_category(db):
    message = _reply("  animals ", cat.RENAME_PROMPT.format(name="Pets"))
    assert asyncio.run(cat.apply_category_rename(message, USER)) is True
    assert message.replies == ["✏️ Renamed Pets to Animals (2 note(s))."]
    assert "Animals" in dict(database.get_categories(USER))


def test_renaming_to_an_existing_name_merges(db):
    message = _reply("pets & animals", cat.RENAME_PROMPT.format(name="Pets"))
    asyncio.run(cat.apply_category_rename(message, USER))
    assert message.replies == ["🔀 Moved 2 note(s) from Pets into Pets & Animals."]
    assert dict(database.get_categories(USER)) == {"Pets & Animals": 3, "Career": 1}


def test_other_replies_are_not_category_renames(db):
    message = _Message(text="hi", replies=[], reply_to_message=None)
    assert asyncio.run(cat.apply_category_rename(message, USER)) is False

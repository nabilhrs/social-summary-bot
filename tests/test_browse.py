import asyncio

import pytest

from app.bot import browse
from app.bot.browse import (
    ALL,
    CATEGORY,
    MENU_CALLBACK,
    PAGE_SIZE,
    UNCATEGORIZED,
    build_menu,
    build_page,
    decode_page,
    encode_page,
)
from app.database import database

USER = 111


def _buttons(markup):
    return [button for row in markup.inline_keyboard for button in row]


def _item(item_id, title="T"):
    return {"id": item_id, "title": title, "original_text": "x", "created_at": "2026-10-01T00:00:00"}


@pytest.mark.parametrize(
    "page, scope, category",
    [(0, ALL, None), (3, UNCATEGORIZED, None), (1, CATEGORY, "Food & Drink"), (0, CATEGORY, "a:b:c")],
)
def test_encode_decode_round_trip(page, scope, category):
    data = encode_page(page, scope, category)
    assert decode_page(data) == (page, scope, category)
    assert len(data.encode("utf-8")) <= 64


def test_menu_has_all_button_categories_and_uncategorized():
    text, markup = build_menu(12, [("Career", 9), ("Food", 2)], uncategorized=1)
    assert "12" in text
    labels = [button.text for button in _buttons(markup)]
    assert labels == ["🕒 All, newest first (12)", "📂 Career (9)", "📂 Food (2)", "❔ Uncategorized (1)"]


def test_menu_omits_uncategorized_when_none():
    _, markup = build_menu(2, [("Career", 2)], uncategorized=0)
    assert not any("Uncategorized" in button.text for button in _buttons(markup))


def test_first_page_has_next_but_no_prev():
    items = [_item(i) for i in range(PAGE_SIZE)]
    text, markup = build_page(items, 0, 25, CATEGORY, "Career")
    assert "page 1/3" in text
    nav = [button.text for button in markup.inline_keyboard[-1]]
    assert nav == ["📚 Categories", "Next ▶"]
    assert markup.inline_keyboard[-1][1].callback_data == encode_page(1, CATEGORY, "Career")


def test_last_page_has_prev_but_no_next():
    _, markup = build_page([_item(1)], 2, 25, ALL, None)
    nav = [button.text for button in markup.inline_keyboard[-1]]
    assert nav == ["◀ Prev", "📚 Categories"]
    assert markup.inline_keyboard[-1][1].callback_data == MENU_CALLBACK


def test_page_lists_items_with_delete_buttons():
    text, markup = build_page([_item(5, "Ice cream review"), _item(4, "Nasi lemak")], 0, 2, ALL, None)
    assert "#5 — Ice cream review (2026-10-01)" in text
    assert [b.callback_data for b in _buttons(markup) if b.text.startswith("🗑")] == ["delconfirm:5", "delconfirm:4"]


def test_empty_page_says_so():
    text, _ = build_page([], 0, 0, CATEGORY, "Gone")
    assert "Nothing here anymore." in text


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(database.config, "db_path", str(tmp_path / "t.db"))
    database.init_db()
    content = {"title": None, "author": None, "source": "pasted_text", "url": None, "text": "x"}
    for i in range(23):
        content["title"] = f"Note {i}"
        database.save_summary(content, "s", USER, category="Food" if i % 2 else "Career")


def test_render_page_clamps_out_of_range_page(db):
    text, _ = asyncio.run(browse.render_page(USER, 99, CATEGORY, "Food"))
    assert "11 note(s), page 2/2" in text


def test_render_menu_counts(db):
    text, markup = asyncio.run(browse.render_menu(USER))
    assert "(23)" in text
    assert "📂 Career (12)" in [button.text for button in _buttons(markup)]

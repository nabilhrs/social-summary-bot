import asyncio
import re
from types import SimpleNamespace

import pytest

from app.ai import summarizer
from app.ai.prompts import build_summary_prompt
from app.ai.summarizer import _extract_tags, parse_todos, summarize
from app.bot import todos as todo_module
from app.bot.formatting import format_saved_summary
from app.bot.todos import MAX_SHOWN, build_todo_list, handle_todo_callback, todo_command
from app.database import database

USER = 111


def _save(text="x", title="Pasta"):
    content = {"title": title, "author": None, "source": "pasted_text", "url": None, "text": text}
    return database.save_summary(content, "SUMMARY: s", USER)


@pytest.mark.parametrize(
    "value, expected",
    [
        ("Try the kopi at Kedai A | buy a cast-iron pan", ["Try the kopi at Kedai A", "Buy a cast-iron pan"]),
        ("NONE", []),
        ("none.", []),
        ("", []),
        (None, []),
        ("Read Atomic Habits | read atomic habits", ["Read Atomic Habits"]),
        ("a | b | c | d", ["A", "B", "C"]),
        ("- \"Book a table\" |  tiada ", ["Book a table"]),
    ],
)
def test_parse_todos(value, expected):
    assert parse_todos(value) == expected


def test_todo_tag_is_read_from_the_trailing_block():
    text, tags = _extract_tags("SUMMARY: hi\nTITLE: T\nTODO: Try X | Buy Y\nCATEGORY: Food")
    assert text == "SUMMARY: hi"
    assert tags["TODO"] == "Try X | Buy Y"


def test_summary_prompt_asks_for_todos():
    prompt = build_summary_prompt({"title": None, "text": "hello there"})
    assert "TODO:" in prompt and "NONE" in prompt


def test_summarize_returns_todos(monkeypatch):
    monkeypatch.setattr(
        summarizer, "generate_text", lambda *_a, **_k: "SUMMARY: ok\nTITLE: Cafe\nCATEGORY: Food\nTODO: Try the cafe"
    )
    result = asyncio.run(summarize({"title": None, "text": "a cafe"}, [], "key", []))
    assert result.todos == ["Try the cafe"]
    assert result.text == "SUMMARY: ok"


def test_saved_reply_lists_added_todos():
    text = format_saved_summary(7, "T", None, "SUMMARY: s", todos=["Try <this>"])
    assert "☑️ Added to /todo:" in text and "• Try &lt;this&gt;" in text
    assert "/todo" not in format_saved_summary(None, "T", None, "SUMMARY: s", todos=["x"])


def test_todo_storage():
    item = _save()
    first, second = database.add_todos(USER, item, ["Try A", "Buy B"])
    database.add_todos(USER, None, ["Call mum"])
    database.add_todos(222, None, ["Someone else's"])

    open_todos = database.list_open_todos(USER)
    assert [t["text"] for t in open_todos] == ["Try A", "Buy B", "Call mum"]
    assert open_todos[0]["item_title"] == "Pasta"

    assert database.set_todo_done(first, USER, True)
    assert [t["text"] for t in database.list_open_todos(USER)] == ["Buy B", "Call mum"]
    assert not database.set_todo_done(first, 222, False)  # not theirs
    database.set_todo_done(first, USER, False)
    assert len(database.list_open_todos(USER)) == 3


def test_resummarizing_replaces_only_unticked_todos():
    item = _save()
    done, _ = database.add_todos(USER, item, ["Old done", "Old open"])
    database.set_todo_done(done, USER, True)
    database.replace_open_todos(USER, item, ["New one"])
    assert [t["text"] for t in database.list_open_todos(USER)] == ["New one"]
    assert database.get_todo(done, USER)["done_at"] is not None


def test_deleting_a_note_deletes_its_todos():
    item = _save()
    database.add_todos(USER, item, ["Try A"])
    database.add_todos(USER, None, ["Mine"])
    assert database.delete_item(item, USER)
    assert [t["text"] for t in database.list_open_todos(USER)] == ["Mine"]


def test_todo_list_text_and_buttons():
    rows = [
        {"id": 4, "item_id": 12, "text": "Try the nasi lemak", "item_title": "Food"},
        {"id": 5, "item_id": None, "text": "x" * 80, "item_title": None},
    ]
    text, markup = build_todo_list(rows)
    assert "☑️ To-do (2)" in text
    assert "1. Try the nasi lemak — from #12" in text
    assert "2. " + "x" * 80 in text and "from #" not in text.splitlines()[-3]
    data = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert data == ["todo:done:4", "todo:done:5"]
    assert len(markup.inline_keyboard[1][0].text) < 50


def test_todo_list_caps_buttons_and_offers_undo():
    rows = [{"id": i, "item_id": None, "text": f"t{i}"} for i in range(MAX_SHOWN + 3)]
    text, markup = build_todo_list(rows, "✅ Done: z", undo_id=99)
    assert text.startswith("✅ Done: z")
    assert "…and 3 more" in text
    assert markup.inline_keyboard[0][0].callback_data == "todo:undo:99"
    assert len(markup.inline_keyboard) == MAX_SHOWN + 1


def test_empty_list():
    text, markup = build_todo_list([])
    assert "Nothing on your to-do list" in text and markup is None
    text, markup = build_todo_list([], "✅ Done: z", undo_id=3)
    assert "That's everything" in text and markup.inline_keyboard[0][0].callback_data == "todo:undo:3"


class _Message:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text, reply_markup=None):
        self.replies.append((text, reply_markup))


class _Query:
    def __init__(self, data):
        self.data = data
        self.answers = []
        self.edits = []

    async def answer(self, text=None):
        self.answers.append(text)

    async def edit_message_text(self, text, reply_markup=None):
        self.edits.append((text, reply_markup))


@pytest.fixture
def authorized(monkeypatch):
    monkeypatch.setattr(todo_module.config, "is_authorized", lambda user_id: user_id == USER)


def test_todo_command_adds_and_lists(authorized):
    message = _Message()
    update = SimpleNamespace(effective_user=SimpleNamespace(id=USER), message=message)
    asyncio.run(todo_command(update, SimpleNamespace(args=["buy", "batteries", "|", "call", "mum"])))
    text, _ = message.replies[0]
    assert text.startswith("➕ Added: Buy batteries; Call mum")
    assert [t["text"] for t in database.list_open_todos(USER)] == ["Buy batteries", "Call mum"]

    asyncio.run(todo_command(update, SimpleNamespace(args=["check", "tyres"])))
    assert database.list_open_todos(USER)[-1]["text"] == "Check tyres"

    asyncio.run(todo_command(update, SimpleNamespace(args=["none"])))
    assert message.replies[-1][0] == "That to-do is empty — nothing added."


def test_tick_then_undo(authorized):
    (todo_id,) = database.add_todos(USER, None, ["Buy batteries"])
    update = lambda data: SimpleNamespace(effective_user=SimpleNamespace(id=USER), callback_query=_Query(data))

    tick = update(f"todo:done:{todo_id}")
    asyncio.run(handle_todo_callback(tick, None))
    assert database.list_open_todos(USER) == []
    text, markup = tick.callback_query.edits[0]
    assert "✅ Done: Buy batteries" in text
    assert markup.inline_keyboard[0][0].callback_data == f"todo:undo:{todo_id}"

    undo = update(f"todo:undo:{todo_id}")
    asyncio.run(handle_todo_callback(undo, None))
    assert [t["id"] for t in database.list_open_todos(USER)] == [todo_id]


def test_todo_button_pattern():
    import main

    pattern = next(
        h.pattern.pattern
        for handlers in main.build_app().handlers.values()
        for h in handlers
        if getattr(h, "callback", None) is handle_todo_callback
    )
    assert re.match(pattern, "todo:done:12") and re.match(pattern, "todo:undo:3")
    assert "todo" in [c.command for c in main._BOT_COMMANDS]

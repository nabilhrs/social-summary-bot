import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from app.bot import reminders as rem
from app.database import database

KL = ZoneInfo("Asia/Kuala_Lumpur")
USER = 111
WED_3PM = datetime(2026, 11, 18, 15, 0, tzinfo=KL)  # a Wednesday


@pytest.mark.parametrize(
    "code, now, expected",
    [
        ("tn", WED_3PM, datetime(2026, 11, 18, 20, 0, tzinfo=KL)),
        ("tn", datetime(2026, 11, 18, 19, 50, tzinfo=KL), datetime(2026, 11, 19, 20, 0, tzinfo=KL)),  # too close: tomorrow
        ("tm", WED_3PM, datetime(2026, 11, 19, 9, 0, tzinfo=KL)),
        ("wk", WED_3PM, datetime(2026, 11, 21, 9, 0, tzinfo=KL)),  # Saturday
        ("wk", datetime(2026, 11, 21, 8, 0, tzinfo=KL), datetime(2026, 11, 21, 9, 0, tzinfo=KL)),  # Saturday morning
        ("wk", datetime(2026, 11, 21, 10, 0, tzinfo=KL), datetime(2026, 11, 28, 9, 0, tzinfo=KL)),  # after 9 on Saturday
        ("nw", WED_3PM, datetime(2026, 11, 23, 9, 0, tzinfo=KL)),  # Monday
        ("nw", datetime(2026, 11, 23, 8, 0, tzinfo=KL), datetime(2026, 11, 23, 9, 0, tzinfo=KL)),
        ("mo", WED_3PM, datetime(2026, 12, 18, 9, 0, tzinfo=KL)),
    ],
)
def test_remind_time(code, now, expected):
    assert rem.remind_time(code, now) == expected


def test_unknown_choice_raises():
    with pytest.raises(ValueError):
        rem.remind_time("xx", WED_3PM)


def test_format_when():
    assert rem.format_when(datetime(2026, 11, 21, 9, 0, tzinfo=KL)) == "Sat 21 Nov, 9:00am"
    assert rem.format_when(datetime(2026, 11, 18, 20, 0, tzinfo=KL)) == "Wed 18 Nov, 8:00pm"
    assert rem.format_when(datetime(2026, 11, 18, 12, 5, tzinfo=KL)) == "Wed 18 Nov, 12:05pm"


def test_picker_offers_every_choice():
    data = [b.callback_data for row in rem.build_picker(41).inline_keyboard for b in row]
    assert data == ["remind:41:tn", "remind:41:tm", "remind:41:wk", "remind:41:nw", "remind:41:mo", "act:remindat:41"]


def test_reminders_list_text_and_cancel_buttons():
    rows = [{"id": 5, "item_id": 41, "remind_at": "2026-11-21T01:00:00+00:00", "title": "Pasta", "original_text": "x"}]
    text, markup = rem.build_reminders_list(rows, KL)
    assert "• Sat 21 Nov, 9:00am — #41 Pasta" in text
    assert markup.inline_keyboard[0][0].callback_data == "remcancel:5"
    assert rem.build_reminders_list([], KL)[1] is None


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(database.config, "db_path", str(tmp_path / "rem.db"))
    database.init_db()
    content = {"title": "Pasta", "author": None, "source": "pasted_text", "url": None, "text": "x"}
    return database.save_summary(content, "SUMMARY: cook it", USER)


def test_reminder_storage_lists_only_live_items_for_the_user(db):
    database.add_reminder(USER, db, "2026-11-21T01:00:00+00:00")
    database.add_reminder(USER, 9999, "2026-11-20T01:00:00+00:00")  # item no longer exists
    database.add_reminder(222, db, "2026-11-19T01:00:00+00:00")  # someone else's
    assert [r["item_id"] for r in database.list_reminders(USER)] == [db]
    assert len(database.get_due_reminders("2026-11-30")) == 3
    assert database.get_due_reminders("2026-11-01") == []


class _FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, parse_mode, reply_markup):
        self.sent.append((chat_id, text, reply_markup))


def test_due_reminders_are_sent_once_and_cleared(db):
    database.add_reminder(USER, db, "2026-11-21T01:00:00+00:00")
    database.add_reminder(USER, 9999, "2026-11-21T01:00:00+00:00")  # deleted item: dropped silently
    database.add_reminder(USER, db, "2026-12-25T01:00:00+00:00")  # not due yet
    bot = _FakeBot()

    sent = asyncio.run(rem.send_due_reminders(bot, "2026-11-22T00:00:00+00:00", lambda item: f"kb-{item['id']}"))

    assert sent == 1
    chat_id, text, markup = bot.sent[0]
    assert chat_id == USER and text.startswith("⏰ <b>Reminder</b>") and "Pasta" in text and markup == f"kb-{db}"
    assert [r["remind_at"][:10] for r in database.get_due_reminders("2099")] == ["2026-12-25"]


from types import SimpleNamespace  # noqa: E402


class _Message(SimpleNamespace):
    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs.get("reply_markup")))


def _frozen_now(monkeypatch, now=datetime(2026, 11, 18, 15, 0, tzinfo=KL)):
    monkeypatch.setattr(rem, "_local_now", lambda: now)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("remind me tomorrow 7am dentist", "tomorrow 7am dentist"),
        ("Remind me, in 2 hours call mum", "in 2 hours call mum"),
        ("ingatkan saya esok pukul 8 pagi temujanji", "esok pukul 8 pagi temujanji"),
        ("Ingatkan aku 2 jam lagi angkat kain", "2 jam lagi angkat kain"),
        ("Ingatkan diri anda untuk minum air", None),
        ("a note about reminders", None),
    ],
)
def test_natural_reminder_request(text, expected):
    assert rem.natural_reminder_request(text) == expected


def test_text_reminder_is_saved_and_confirmed_with_a_cancel_button(db, monkeypatch):
    _frozen_now(monkeypatch)
    message = _Message(replies=[])
    asyncio.run(rem.create_text_reminder(message, USER, "tomorrow 7am dentist appointment"))

    text, markup = message.replies[0]
    assert text == "⏰ Got it. I'll remind you: dentist appointment\n🗓 Thu 19 Nov, 7:00am"
    [reminder] = database.list_reminders(USER)
    assert (reminder["item_id"], reminder["text"]) == (None, "dentist appointment")
    assert reminder["remind_at"] == "2026-11-18T23:00:00+00:00"
    assert markup.inline_keyboard[0][0].callback_data == f"remcancel:{reminder['id']}".replace("remcancel", "remundo")


@pytest.mark.parametrize(
    "request_text, starts_with",
    [
        ("buy milk", "I couldn't find a time in that."),
        ("today 7am gym", "That time (Wed 18 Nov, 7:00am) has already passed."),
        ("tomorrow 7am", "What should I remind you about?"),
        ("", "Tell me when and what"),
    ],
)
def test_text_reminder_problems_are_explained_and_nothing_is_saved(db, monkeypatch, request_text, starts_with):
    _frozen_now(monkeypatch)
    message = _Message(replies=[])
    asyncio.run(rem.create_text_reminder(message, USER, request_text))
    assert message.replies[0][0].startswith(starts_with)
    assert database.list_reminders(USER) == []


def test_other_time_reply_sets_a_note_reminder(db, monkeypatch):
    _frozen_now(monkeypatch)
    message = _Message(replies=[], text="esok pukul 3 petang")
    asyncio.run(rem.apply_other_time(message, USER, db))
    [reminder] = database.list_reminders(USER)
    assert (reminder["item_id"], reminder["remind_at"]) == (db, "2026-11-19T07:00:00+00:00")
    assert message.replies[0][0] == f"⏰ I'll remind you about #{db} — Pasta on Thu 19 Nov, 3:00pm."


def test_other_time_prompt_round_trips():
    assert rem.other_time_prompt_id(rem.OTHER_TIME_PROMPT.format(id=41) + "\n\nFor example: ...") == 41
    assert rem.other_time_prompt_id("something else") is None


def test_text_reminders_are_listed_and_sent(db):
    database.add_reminder(USER, None, "2026-11-21T01:00:00+00:00", "renew road tax <today>")
    text, _ = rem.build_reminders_list(database.list_reminders(USER), KL)
    assert "• Sat 21 Nov, 9:00am — renew road tax <today>" in text

    bot = _FakeBot()
    assert asyncio.run(rem.send_due_reminders(bot, "2026-11-22", lambda item: None)) == 1
    assert bot.sent[0][1] == "⏰ <b>Reminder:</b> renew road tax &lt;today&gt;"
    assert database.list_reminders(USER) == []


def test_old_reminders_table_is_migrated(tmp_path, monkeypatch):
    import sqlite3

    path = str(tmp_path / "old.db")
    monkeypatch.setattr(database.config, "db_path", path)
    database.init_db()
    with sqlite3.connect(path) as conn:
        conn.execute("DROP TABLE reminders")
        conn.execute(
            "CREATE TABLE reminders (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, "
            "item_id INTEGER NOT NULL, remind_at TEXT NOT NULL, created_at TEXT NOT NULL)"
        )
        conn.execute("INSERT INTO reminders (user_id, item_id, remind_at, created_at) VALUES (1, 5, '2026-12-01', 'x')")

    database.init_db()

    with sqlite3.connect(path) as conn:
        columns = {row[1]: row for row in conn.execute("PRAGMA table_info(reminders)")}
        rows = conn.execute("SELECT user_id, item_id, text, remind_at FROM reminders").fetchall()
    assert "text" in columns and columns["item_id"][3] == 0  # item_id no longer NOT NULL
    assert rows == [(1, 5, None, "2026-12-01")]
    database.add_reminder(1, None, "2026-12-02", "plain reminder")

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
    assert data == ["remind:41:tn", "remind:41:tm", "remind:41:wk", "remind:41:nw", "remind:41:mo"]


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

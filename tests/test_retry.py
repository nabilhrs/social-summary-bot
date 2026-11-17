import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.ai.gemini import INVALID_KEY, QUOTA_DAILY, QUOTA_RATE, UNAVAILABLE, GeminiError
from app.bot import handlers
from app.bot.retry import (
    MAX_ATTEMPTS,
    RETRY_GAVE_UP_TEXT,
    ChatTarget,
    describe_wait,
    next_attempt_at,
    next_quota_reset,
)
from app.database import database

NOW = datetime(2026, 11, 17, 6, 0, tzinfo=timezone.utc)  # 22:00 the day before in Los Angeles
USER = 111


def test_backoff_grows_and_then_stays_at_an_hour():
    gaps = [(next_attempt_at(UNAVAILABLE, n, NOW) - NOW).total_seconds() / 60 for n in range(1, 8)]
    assert gaps == [2, 5, 15, 30, 60, 60, 60]


def test_rate_limit_retries_in_two_minutes():
    assert next_attempt_at(QUOTA_RATE, 3, NOW) - NOW == timedelta(minutes=2)


def test_daily_quota_waits_for_the_pacific_midnight_reset():
    reset = next_quota_reset(NOW)
    assert reset == datetime(2026, 11, 17, 8, 0, tzinfo=timezone.utc)  # midnight PST
    assert next_attempt_at(QUOTA_DAILY, 1, NOW) == reset + timedelta(minutes=5)


def test_describe_wait():
    assert describe_wait(NOW + timedelta(minutes=2), NOW) == "in about 2 minutes"
    assert describe_wait(NOW + timedelta(minutes=1), NOW) == "in about 1 minute"
    assert describe_wait(NOW + timedelta(hours=7), NOW) == "in about 7 hours, after it resets"


class _FakeBot:
    def __init__(self):
        self.sent, self.actions = [], []

    async def send_message(self, chat_id, text, **kwargs):
        self.sent.append((chat_id, text, kwargs))

    async def send_chat_action(self, chat_id, action):
        self.actions.append((chat_id, action))


def test_chat_target_replies_quoting_the_original_message():
    bot = _FakeBot()
    target = ChatTarget(bot, 42, 7)
    asyncio.run(target.reply_text("done", parse_mode="HTML"))
    asyncio.run(target.chat.send_action("typing"))
    chat_id, text, kwargs = bot.sent[0]
    assert (chat_id, text, kwargs["parse_mode"]) == (42, "done", "HTML")
    assert kwargs["reply_parameters"].message_id == 7
    assert kwargs["reply_parameters"].allow_sending_without_reply is True
    assert bot.actions == [(42, "typing")]


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(database.config, "db_path", str(tmp_path / "r.db"))
    database.init_db()


class _Message(SimpleNamespace):
    async def reply_text(self, text, **kwargs):
        self.replies.append(text)


def _message():
    return _Message(chat_id=42, message_id=7, replies=[])


def _jobs():
    return database.get_due_jobs("9999")


def test_busy_gemini_saves_a_job_and_tells_the_user(db):
    message = _message()
    finished = asyncio.run(handlers.gemini_failure(message, USER, GeminiError(UNAVAILABLE), "text", {"text": "hi"}, None))
    assert finished is False
    [job] = _jobs()
    assert (job["user_id"], job["chat_id"], job["message_id"], job["kind"], job["attempts"]) == (USER, 42, 7, "text", 1)
    assert json.loads(job["payload"]) == {"text": "hi"}
    assert message.replies[0].startswith("⏳ Gemini is busy right now")


def test_daily_quota_message_mentions_the_quota(db):
    message = _message()
    asyncio.run(handlers.gemini_failure(message, USER, GeminiError(QUOTA_DAILY), "text", {"text": "hi"}, None))
    assert message.replies[0].startswith("⏳ Today's free Gemini quota is used up")


def test_non_retryable_errors_are_reported_not_saved(db):
    message = _message()
    finished = asyncio.run(handlers.gemini_failure(message, USER, GeminiError(INVALID_KEY), "text", {"text": "hi"}, None))
    assert finished is True
    assert _jobs() == []
    assert "rejected the API key" in message.replies[0]


def test_retry_reschedules_quietly_then_gives_up(db):
    database.add_pending_job(USER, 42, 7, "text", '{"text": "hi"}', "2000-01-01")
    job = _jobs()[0]
    message = _message()

    assert asyncio.run(handlers.gemini_failure(message, USER, GeminiError(UNAVAILABLE), "text", {}, job)) is False
    assert _jobs()[0]["attempts"] == 2 and message.replies == []

    job = {**job, "attempts": MAX_ATTEMPTS}
    assert asyncio.run(handlers.gemini_failure(message, USER, GeminiError(UNAVAILABLE), "text", {}, job)) is True
    assert message.replies == [RETRY_GAVE_UP_TEXT]


def test_run_job_deletes_the_job_when_the_retry_succeeds(db, monkeypatch):
    database.add_pending_job(USER, 42, 7, "text", '{"text": "hello"}', "2000-01-01")
    seen = {}

    async def fake_process(target, user_id, text, job):
        seen["args"] = (target.chat_id, target.message_id, user_id, text, job["id"])
        return True

    monkeypatch.setattr(handlers, "_process_input", fake_process)
    asyncio.run(handlers.run_job(_FakeBot(), _jobs()[0]))
    assert seen["args"][:4] == (42, 7, USER, "hello")
    assert _jobs() == []


def test_run_job_keeps_a_deferred_job(db, monkeypatch):
    database.add_pending_job(USER, 42, 7, "files", '{"files": [], "caption": null}', "2000-01-01")

    async def deferred(*args):
        return False

    monkeypatch.setattr(handlers, "process_files", deferred)
    asyncio.run(handlers.run_job(_FakeBot(), _jobs()[0]))
    assert len(_jobs()) == 1


def test_process_input_defers_when_summarizing_is_busy(db, monkeypatch):
    async def busy_summarize(*args):
        raise GeminiError(UNAVAILABLE)

    monkeypatch.setattr(handlers, "summarize", busy_summarize)
    monkeypatch.setattr(handlers, "resolve_gemini_api_key", lambda user_id: "key")

    class _Chat:
        async def send_action(self, action):
            pass

    message = _Message(chat_id=42, message_id=7, replies=[], chat=_Chat())
    finished = asyncio.run(handlers._process_input(message, USER, "a pasted note worth keeping"))
    assert finished is False
    assert json.loads(_jobs()[0]["payload"]) == {"text": "a pasted note worth keeping"}


def test_end_to_end_busy_then_background_retry_posts_the_summary(db, monkeypatch):
    from app.ai.summarizer import Summary

    calls = {"n": 0}

    async def flaky_summarize(content, recent, api_key, categories):
        calls["n"] += 1
        if calls["n"] == 1:
            raise GeminiError(UNAVAILABLE)
        return Summary(text="SUMMARY: kept and summarized later", title="Later Note", category="Misc")

    monkeypatch.setattr(handlers, "summarize", flaky_summarize)
    monkeypatch.setattr(handlers, "resolve_gemini_api_key", lambda user_id: "key")

    class _Chat:
        async def send_action(self, action):
            pass

    message = _Message(chat_id=42, message_id=7, replies=[], chat=_Chat())
    assert asyncio.run(handlers._process_input(message, USER, "remember to renew the passport in March")) is False

    bot = _FakeBot()
    asyncio.run(handlers.run_job(bot, _jobs()[0]))

    assert _jobs() == []
    chat_id, text, kwargs = bot.sent[0]
    assert chat_id == 42 and "Later Note" in text and "kept and summarized later" in text
    assert kwargs["parse_mode"] == "HTML" and kwargs["reply_markup"] is not None
    assert kwargs["reply_parameters"].message_id == 7
    assert bot.actions == [(42, "typing")]
    assert database.get_all_items(USER)[0]["original_text"] == "remember to renew the passport in March"

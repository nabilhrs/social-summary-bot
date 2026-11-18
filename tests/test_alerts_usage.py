import asyncio
import logging
import sys

import pytest

from app.ai import gemini
from app.ai.gemini import MODELS, QUOTA_WARNING_MARGIN, generate_text, quota_day
from app.bot import alerts
from app.bot.alerts import AlertHandler, format_alert
from app.bot.commands import build_usage_text
from app.database import database


def _record(name="app.bot.handlers", level=logging.ERROR, msg="Failed to save %s", with_exc=True):
    exc_info = None
    if with_exc:
        try:
            raise RuntimeError("database is locked")
        except RuntimeError:
            exc_info = sys.exc_info()
    return logging.LogRecord(name, level, __file__, 1, msg, ("summary",), exc_info)


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_alerts_only_for_app_crashes():
    handler = AlertHandler()
    assert handler.should_alert(_record()) is True
    assert handler.should_alert(_record(msg="other %s")) is True
    assert handler.should_alert(_record(msg="no crash %s", with_exc=False)) is False
    assert handler.should_alert(_record(msg="warn %s", level=logging.WARNING)) is False
    assert handler.should_alert(_record(name="telegram.ext.Updater", msg="network %s")) is False
    assert handler.should_alert(_record(name="__main__", msg="Unhandled exception while handling %s")) is True
    assert handler.should_alert(_record(name="app.bot.alerts", msg="self %s")) is False


def test_same_error_is_muted_for_an_hour():
    clock = _Clock()
    handler = AlertHandler(clock=clock)
    assert handler.should_alert(_record()) is True
    clock.now += 60
    assert handler.should_alert(_record()) is False
    clock.now += 3600
    assert handler.should_alert(_record()) is True


def test_alert_text_says_where_what_and_why():
    text = format_alert(_record())
    assert "Where: app.bot.handlers" in text
    assert "What: Failed to save summary" in text
    assert "Error: RuntimeError: database is locked" in text
    assert "journalctl" in text


class _FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text):
        self.sent.append((chat_id, text))


def test_notify_is_a_no_op_until_configured(monkeypatch):
    monkeypatch.setattr(alerts, "_bot", None)
    alerts.notify("hello")  # must not raise


def test_notify_sends_to_the_owner(monkeypatch):
    bot = _FakeBot()

    async def scenario():
        monkeypatch.setattr(alerts, "_bot", None)
        alerts.configure(bot, 42, asyncio.get_running_loop())
        alerts.notify("hello")
        await asyncio.sleep(0.01)

    asyncio.run(scenario())
    monkeypatch.setattr(alerts, "_bot", None)
    assert bot.sent == [(42, "hello")]


class _Response:
    def __init__(self, text):
        self.text = text


class _ScriptedClient:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.models = self

    def generate_content(self, model, contents, config=None):
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return _Response(outcome)


@pytest.fixture
def scripted(monkeypatch):
    monkeypatch.setattr(gemini.time, "sleep", lambda _s: None)

    def install(outcomes):
        client = _ScriptedClient(outcomes)
        monkeypatch.setattr(gemini.genai, "Client", lambda **_kwargs: client)

    return install


def _daily_429():
    from google.genai import errors

    return errors.ClientError(429, {"error": {"code": 429, "message": "quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier", "status": "X"}})


def test_successful_requests_are_counted_per_model(scripted):
    scripted(["one", "two"])
    generate_text("key", "a")
    generate_text("key", "b")
    assert database.get_gemini_usage(quota_day()) == {MODELS[0]: 2}


def test_running_out_records_the_count_as_the_learned_limit(scripted):
    scripted(["one", "two", _daily_429(), "from lite"])
    generate_text("key", "a")
    generate_text("key", "b")
    generate_text("key", "c")  # main model out of quota; served by the first fallback
    assert database.get_learned_limits() == {MODELS[0]: 2}
    assert database.get_gemini_usage(quota_day()) == {MODELS[0]: 2, MODELS[1]: 1}


def test_heads_up_fires_once_when_near_the_learned_limit(scripted, monkeypatch):
    warnings = []
    monkeypatch.setattr(alerts, "notify", warnings.append)
    database.record_quota_ran_out("2026-01-01", MODELS[0])  # creates the row
    with database.sqlite3.connect(database.config.db_path) as conn:
        conn.execute("UPDATE gemini_usage SET ran_out_at = 6 WHERE day = '2026-01-01'")

    scripted(["ok"] * 5)
    for _ in range(5):
        generate_text("key", "x")

    assert len(warnings) == 1
    assert f"has used {6 - QUOTA_WARNING_MARGIN} of about 6" in warnings[0]


def test_ran_out_at_is_kept_from_the_first_time_only(scripted):
    day = quota_day()
    database.record_gemini_request(day, MODELS[0])
    database.record_quota_ran_out(day, MODELS[0])
    database.record_gemini_request(day, MODELS[0])
    database.record_quota_ran_out(day, MODELS[0])
    assert database.get_learned_limits() == {MODELS[0]: 1}


def test_usage_text():
    text = build_usage_text({MODELS[0]: 14, MODELS[1]: 3}, {MODELS[0]: 20}, pending=2, hours_to_reset=7)
    assert "resets in about 7 h" in text
    assert f"• {MODELS[0]}: 14 of about 20" in text
    assert f"• {MODELS[1]}: 3" in text and f"• {MODELS[2]}: 0" in text
    assert "2 save(s) waiting" in text
    assert "learn each model's daily limit" not in text
    assert "learn each model's daily limit" in build_usage_text({}, {}, 0, 7)


def test_describe_update():
    from types import SimpleNamespace

    import main
    from telegram import Update

    class _U(Update):
        def __init__(self, callback=None, text=None, caption=None):
            object.__setattr__(self, "_cq", callback)
            object.__setattr__(self, "_msg", SimpleNamespace(text=text, caption=caption) if (text or caption or callback is None) else None)

        @property
        def callback_query(self):
            return self._cq

        @property
        def effective_message(self):
            return self._msg

    assert main.describe_update(_U(callback=SimpleNamespace(data="star:4"))) == "a button tap (star:4)"
    assert main.describe_update(_U(text="/list career")) == "the command /list"
    assert main.describe_update(_U(text="hello")) == "a message"
    assert main.describe_update(_U(caption=None, text=None)) == "a file or photo"
    assert main.describe_update(None) == "a background task"


def test_polling_connection_blips_do_not_alert(caplog):
    from types import SimpleNamespace

    import main
    from telegram.error import NetworkError, TimedOut

    handler = AlertHandler()
    for error in (NetworkError("httpx.ReadError: "), TimedOut()):
        caplog.clear()
        with caplog.at_level(logging.DEBUG):
            asyncio.run(main.log_error(None, SimpleNamespace(error=error)))
        assert not any(handler.should_alert(record) for record in caplog.records)
        assert any(record.levelno == logging.WARNING for record in caplog.records)

    caplog.clear()
    try:
        raise RuntimeError("real bug")
    except RuntimeError as exc:
        crash = exc
    with caplog.at_level(logging.DEBUG):
        asyncio.run(main.log_error(None, SimpleNamespace(error=crash)))
    # Imported in tests, the logger is "main" rather than "__main__", so check the record itself.
    assert any(record.levelno == logging.ERROR and record.exc_info for record in caplog.records)

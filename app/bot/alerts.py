"""
Telegram messages to the owner (the first id in AUTHORIZED_USER_IDS) when
something breaks, plus notify() for one-off heads-ups like the quota warning.

Only real crashes are forwarded: ERROR records that carry exception info,
from this app's own loggers. Handled situations (Gemini busy and retried
later, a bad link) log without exception info and stay quiet. The same
error is muted for an hour after it's sent.
"""
import asyncio
import logging
import time

logger = logging.getLogger(__name__)

_MUTE_SECONDS = 60 * 60
_APP_LOGGERS = ("app.", "__main__")
_MAX_DETAIL_CHARS = 300

_bot = None
_chat_id: int | None = None
_loop: asyncio.AbstractEventLoop | None = None


def configure(bot, chat_id: int, loop: asyncio.AbstractEventLoop) -> None:
    global _bot, _chat_id, _loop
    _bot, _chat_id, _loop = bot, chat_id, loop


def notify(text: str) -> None:
    """Sends `text` to the owner. Safe to call from worker threads; does
    nothing until configure() has run (e.g. in tests)."""
    if _bot is None or _loop is None or _loop.is_closed():
        return
    _loop.call_soon_threadsafe(lambda: asyncio.ensure_future(_send(text)))


async def _send(text: str) -> None:
    try:
        await _bot.send_message(chat_id=_chat_id, text=text)
    except Exception as exc:  # never log with exc_info here: that would alert about the alert
        logger.warning("Couldn't send an alert: %s", exc)


def format_alert(record: logging.LogRecord) -> str:
    exc_type, exc_value, _tb = record.exc_info
    error = f"{exc_type.__name__}: {exc_value}" if exc_type else "unknown error"
    message = record.getMessage()
    return (
        "⚠️ Something broke (repeats are muted for an hour)\n"
        f"Where: {record.name}\n"
        f"What: {message[:_MAX_DETAIL_CHARS]}\n"
        f"Error: {error[:_MAX_DETAIL_CHARS]}\n\n"
        "Details: journalctl -u social-summary-bot -n 100"
    )


class AlertHandler(logging.Handler):
    def __init__(self, mute_seconds: float = _MUTE_SECONDS, clock=time.monotonic):
        super().__init__(level=logging.ERROR)
        self._mute_seconds, self._clock = mute_seconds, clock
        self._last_sent: dict[tuple, float] = {}

    def should_alert(self, record: logging.LogRecord) -> bool:
        if record.levelno < logging.ERROR or not record.exc_info or record.exc_info[0] is None:
            return False
        if record.name == __name__ or not record.name.startswith(_APP_LOGGERS):
            return False
        key = (record.name, record.msg, record.exc_info[0].__name__)
        now = self._clock()
        last = self._last_sent.get(key)
        if last is not None and now - last < self._mute_seconds:
            return False
        self._last_sent[key] = now
        return True

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if self.should_alert(record):
                notify(format_alert(record))
        except Exception:
            self.handleError(record)

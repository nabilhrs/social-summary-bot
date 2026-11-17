"""
Trying again later when Gemini is busy or out of quota, instead of asking
the user to resend. The work is saved in the pending_jobs table (so a
restart doesn't lose it) and retry_loop() re-runs it when it's due.

Retries use growing gaps; a used-up daily quota waits for Google's reset
at midnight Pacific time instead.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from telegram import ReplyParameters

from app.ai.gemini import QUOTA_DAILY, QUOTA_RATE, UNAVAILABLE
from app.database.database import get_due_jobs

logger = logging.getLogger(__name__)

RETRYABLE = (UNAVAILABLE, QUOTA_RATE, QUOTA_DAILY)
MAX_ATTEMPTS = 6  # the first try plus five retries, about two hours of busy Gemini
_BACKOFF_MINUTES = (2, 5, 15, 30, 60)
_RATE_LIMIT_MINUTES = 2
_QUOTA_RESET_TZ = ZoneInfo("America/Los_Angeles")
_AFTER_RESET = timedelta(minutes=5)
_POLL_SECONDS = 30

RETRY_SCHEDULED_TEXT = "⏳ Gemini is busy right now, so I've kept this and will try again {when}. No need to send it again."
QUOTA_SCHEDULED_TEXT = "⏳ Today's free Gemini quota is used up. I've kept this and will summarize it {when}."
RETRY_GAVE_UP_TEXT = (
    "I kept trying for a couple of hours, but Gemini stayed unavailable, so I've "
    "stopped retrying this one. Please send it again later."
)


def next_quota_reset(now: datetime) -> datetime:
    local = now.astimezone(_QUOTA_RESET_TZ)
    midnight = (local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight.astimezone(timezone.utc)


def next_attempt_at(kind: str, attempts: int, now: datetime) -> datetime:
    """When to try again after `attempts` failed tries."""
    if kind == QUOTA_DAILY:
        return next_quota_reset(now) + _AFTER_RESET
    if kind == QUOTA_RATE:
        return now + timedelta(minutes=_RATE_LIMIT_MINUTES)
    return now + timedelta(minutes=_BACKOFF_MINUTES[min(attempts, len(_BACKOFF_MINUTES)) - 1])


def describe_wait(when: datetime, now: datetime) -> str:
    minutes = max(1, round((when - now).total_seconds() / 60))
    if minutes < 90:
        return f"in about {minutes} minute{'s' if minutes != 1 else ''}"
    return f"in about {round(minutes / 60)} hours, after it resets"


class _Chat:
    def __init__(self, bot, chat_id: int):
        self._bot, self.id = bot, chat_id

    async def send_action(self, action) -> None:
        await self._bot.send_chat_action(chat_id=self.id, action=action)


class ChatTarget:
    """Stands in for the original Message during a background retry:
    replies go to the same chat, quoting the original message if it still exists."""

    def __init__(self, bot, chat_id: int, message_id: int | None):
        self._bot = bot
        self.chat_id, self.message_id = chat_id, message_id
        self.chat = _Chat(bot, chat_id)

    def get_bot(self):
        return self._bot

    async def reply_text(self, text: str, **kwargs):
        if self.message_id is not None:
            kwargs.setdefault(
                "reply_parameters", ReplyParameters(message_id=self.message_id, allow_sending_without_reply=True)
            )
        return await self._bot.send_message(chat_id=self.chat_id, text=text, **kwargs)


async def retry_loop(run_job, poll_seconds: float = _POLL_SECONDS) -> None:
    """Runs due jobs one at a time, forever. `run_job(job)` does the work."""
    while True:
        try:
            jobs = await asyncio.to_thread(get_due_jobs, datetime.now(timezone.utc).isoformat())
            for job in jobs:
                try:
                    await run_job(job)
                except Exception:
                    logger.exception("Retrying pending job %s crashed", job["id"])
        except Exception:
            logger.exception("Checking for pending jobs failed")
        await asyncio.sleep(poll_seconds)

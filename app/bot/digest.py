"""
Weekly digest: what was saved in the last 7 days, grouped by category, plus
one older note to revisit. Sent Sundays at 09:00 in config.timezone, and on
demand with /digest. Uses no Gemini calls.
"""
import asyncio
import html
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from telegram import Bot
from telegram.constants import ParseMode

from app.bot.browse import display_title
from app.bot.formatting import render_summary_html
from app.config import config
from app.database.database import get_items_since, get_random_item_before

logger = logging.getLogger(__name__)

DIGEST_WEEKDAY = 6  # Sunday (Monday is 0)
DIGEST_HOUR = 9
_THROWBACK_MIN_AGE_DAYS = 30
_THROWBACK_SUMMARY_CHARS = 700
_MAX_LISTED_ITEMS = 40


def next_run(now: datetime) -> datetime:
    """Next Sunday 09:00 strictly after `now` (timezone-aware)."""
    candidate = now.replace(hour=DIGEST_HOUR, minute=0, second=0, microsecond=0)
    candidate += timedelta(days=(DIGEST_WEEKDAY - now.weekday()) % 7)
    if candidate <= now:
        candidate += timedelta(days=7)
    return candidate


def build_digest(week_items: list[dict], throwback: dict | None) -> str | None:
    """Telegram HTML, or None when there's nothing worth sending."""
    if not week_items and throwback is None:
        return None

    lines = []
    if week_items:
        lines.append(f"🗓️ <b>Your week in notes</b> — {len(week_items)} saved")
        groups: dict[str, list[dict]] = {}
        for item in week_items[:_MAX_LISTED_ITEMS]:
            groups.setdefault(item.get("category") or "Uncategorized", []).append(item)
        for category, items in sorted(groups.items(), key=lambda pair: -len(pair[1])):
            lines += ["", f"📂 <b>{html.escape(category, quote=False)}</b>"]
            lines += [f"• #{item['id']} {html.escape(display_title(item), quote=False)}" for item in items]
        if len(week_items) > _MAX_LISTED_ITEMS:
            lines.append(f"…and {len(week_items) - _MAX_LISTED_ITEMS} more")
    else:
        lines.append("🗓️ <b>No new notes this week.</b>")

    if throwback is not None:
        summary = throwback["summary"]
        if len(summary) > _THROWBACK_SUMMARY_CHARS:
            summary = summary[:_THROWBACK_SUMMARY_CHARS].rsplit("\n", 1)[0] + "\n…"
        title = html.escape(display_title(throwback), quote=False)
        lines += [
            "",
            "🔁 <b>From your archive</b>",
            f"<b>#{throwback['id']} — {title}</b> ({throwback['created_at'][:10]})",
            render_summary_html(summary),
            f"<i>/view {throwback['id']} for the full note</i>",
        ]
    return "\n".join(lines)


def collect_digest(user_id: int, now: datetime) -> str | None:
    week_ago = (now - timedelta(days=7)).astimezone(ZoneInfo("UTC")).isoformat()
    week_items = get_items_since(user_id, week_ago)
    old_cutoff = (now - timedelta(days=_THROWBACK_MIN_AGE_DAYS)).astimezone(ZoneInfo("UTC")).isoformat()
    throwback = get_random_item_before(user_id, old_cutoff) or get_random_item_before(user_id, week_ago)
    return build_digest(week_items, throwback)


async def send_digest(bot: Bot, user_id: int) -> bool:
    text = await asyncio.to_thread(collect_digest, user_id, datetime.now(ZoneInfo(config.timezone)))
    if text is None:
        return False
    await bot.send_message(chat_id=user_id, text=text, parse_mode=ParseMode.HTML)
    return True


async def digest_loop(bot: Bot) -> None:
    tz = ZoneInfo(config.timezone)
    while True:
        now = datetime.now(tz)
        wait = (next_run(now) - now).total_seconds()
        logger.info("Next weekly digest in %.1f hours", wait / 3600)
        await asyncio.sleep(wait)
        for user_id in config.authorized_user_ids:
            try:
                await send_digest(bot, user_id)
            except Exception:
                logger.exception("Weekly digest for user %s failed", user_id)

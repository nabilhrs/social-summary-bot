"""
⏰ Remind me: bring a saved note back at a chosen time. Times are picked
from buttons (no date typing to misread) in config.timezone, stored in the
reminders table so they survive restarts, and sent by reminder_loop().
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from app.bot.browse import display_title
from app.bot.formatting import format_full_item
from app.config import config
from app.database.database import (
    add_reminder,
    delete_reminder,
    get_by_id,
    get_due_reminders,
    list_reminders,
)

logger = logging.getLogger(__name__)

CHOICES = (
    ("tn", "Tonight 8pm"),
    ("tm", "Tomorrow 9am"),
    ("wk", "Saturday 9am"),
    ("nw", "Monday 9am"),
    ("mo", "In a month"),
)
_EVENING_HOUR, _MORNING_HOUR = 20, 9
_POLL_SECONDS = 60


def remind_time(code: str, now: datetime) -> datetime:
    """`now` is timezone-aware in the user's timezone; the result is too."""
    def at(day: datetime, hour: int) -> datetime:
        return day.replace(hour=hour, minute=0, second=0, microsecond=0)

    if code == "tn":
        tonight = at(now, _EVENING_HOUR)
        return tonight if now < tonight - timedelta(minutes=15) else tonight + timedelta(days=1)
    if code == "tm":
        return at(now + timedelta(days=1), _MORNING_HOUR)
    if code in ("wk", "nw"):
        weekday = 5 if code == "wk" else 0  # Saturday / Monday
        candidate = at(now + timedelta(days=(weekday - now.weekday()) % 7), _MORNING_HOUR)
        return candidate if candidate > now else candidate + timedelta(days=7)
    if code == "mo":
        return at(now + timedelta(days=30), _MORNING_HOUR)
    raise ValueError(f"unknown reminder choice {code!r}")


def format_when(when: datetime) -> str:
    hour = when.hour % 12 or 12
    return f"{when:%a} {when.day} {when:%b}, {hour}:{when.minute:02d}{'am' if when.hour < 12 else 'pm'}"


def build_picker(item_id: int) -> InlineKeyboardMarkup:
    buttons = [InlineKeyboardButton(label, callback_data=f"remind:{item_id}:{code}") for code, label in CHOICES]
    return InlineKeyboardMarkup([buttons[i : i + 2] for i in range(0, len(buttons), 2)])


def _local_now() -> datetime:
    return datetime.now(ZoneInfo(config.timezone))


async def handle_remind_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = update.effective_user.id if update.effective_user else None
    if query is None or query.data is None:
        return
    await query.answer()
    if user_id is None or not config.is_authorized(user_id):
        return

    _, id_str, code = query.data.split(":")
    item = await asyncio.to_thread(get_by_id, int(id_str), user_id)
    if item is None:
        await query.edit_message_text(f"Couldn't find #{id_str} anymore.")
        return
    when = remind_time(code, _local_now())
    await asyncio.to_thread(add_reminder, user_id, item["id"], when.astimezone(timezone.utc).isoformat())
    await query.edit_message_text(
        f"⏰ I'll remind you about #{item['id']} — {display_title(item)} on {format_when(when)}.\n"
        "See or cancel reminders with /reminders."
    )


def build_reminders_list(reminders: list[dict], tz: ZoneInfo):
    if not reminders:
        return "No reminders set. Tap ⏰ Remind me under any summary to add one.", None
    lines = ["⏰ Upcoming reminders:"]
    buttons = []
    for reminder in reminders:
        when = format_when(datetime.fromisoformat(reminder["remind_at"]).astimezone(tz))
        lines.append(f"• {when} — #{reminder['item_id']} {display_title(reminder)}")
        buttons.append(InlineKeyboardButton(f"✖ #{reminder['item_id']}, {when}", callback_data=f"remcancel:{reminder['id']}"))
    lines.append("\nTap one below to cancel it.")
    return "\n".join(lines), InlineKeyboardMarkup([[button] for button in buttons])


async def reminders_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id if update.effective_user else None
    if user_id is None or not config.is_authorized(user_id):
        await update.message.reply_text("Sorry, this bot is private.")
        return
    reminders = await asyncio.to_thread(list_reminders, user_id)
    text, markup = build_reminders_list(reminders, ZoneInfo(config.timezone))
    await update.message.reply_text(text, reply_markup=markup)


async def handle_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = update.effective_user.id if update.effective_user else None
    if query is None or query.data is None:
        return
    await query.answer()
    if user_id is None or not config.is_authorized(user_id):
        return
    await asyncio.to_thread(delete_reminder, int(query.data.split(":")[1]), user_id)
    reminders = await asyncio.to_thread(list_reminders, user_id)
    text, markup = build_reminders_list(reminders, ZoneInfo(config.timezone))
    await query.edit_message_text(text, reply_markup=markup)


async def send_due_reminders(bot: Bot, now_iso: str, keyboard_for) -> int:
    """Sends and clears every due reminder; returns how many were sent.
    `keyboard_for(item)` builds the buttons under the reminded note."""
    sent = 0
    for reminder in await asyncio.to_thread(get_due_reminders, now_iso):
        item = await asyncio.to_thread(get_by_id, reminder["item_id"], reminder["user_id"])
        if item is not None:
            try:
                await bot.send_message(
                    chat_id=reminder["user_id"],
                    text="⏰ <b>Reminder</b>: you wanted to look at this again.\n\n" + format_full_item(item),
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboard_for(item),
                )
                sent += 1
            except Exception:
                logger.exception("Sending reminder %s failed", reminder["id"])
        await asyncio.to_thread(delete_reminder, reminder["id"])
    return sent


async def reminder_loop(bot: Bot, keyboard_for) -> None:
    while True:
        try:
            await send_due_reminders(bot, datetime.now(timezone.utc).isoformat(), keyboard_for)
        except Exception:
            logger.exception("Checking reminders failed")
        await asyncio.sleep(_POLL_SECONDS)

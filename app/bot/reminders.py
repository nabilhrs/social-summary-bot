"""
Reminders, in config.timezone, stored in the reminders table so they
survive restarts, and sent by reminder_loop():

- ⏰ Remind me under a saved note: preset times from buttons, or
  "🕐 Other time…" typed in words.
- /remind <when> <what> (or a message starting "remind me" / "ingatkan
  saya"): a plain reminder with no note, e.g. "tomorrow 7am dentist" or
  "esok pukul 8 pagi temujanji doktor". Times are read by timeparse.py.
"""
import asyncio
import html
import logging
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from app.bot.browse import display_title
from app.bot.formatting import format_full_item
from app.bot.timeparse import parse_reminder
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
    buttons.append(InlineKeyboardButton("🕐 Other time…", callback_data=f"act:remindat:{item_id}"))
    return InlineKeyboardMarkup([buttons[i : i + 2] for i in range(0, len(buttons), 2)])


OTHER_TIME_PROMPT = "🕐 Reply with when to remind you about #{id}"
_OTHER_TIME_PROMPT_RE = re.compile(r"^🕐 Reply with when to remind you about #(\d+)")
_NATURAL_PREFIX_RE = re.compile(r"^\s*(remind me|ingatkan saya|ingatkan aku)\b[\s,:]*(.*)$", re.IGNORECASE | re.DOTALL)

REMIND_USAGE = (
    "Tell me when and what, in English or Malay. For example:\n"
    "/remind tomorrow 7am dentist appointment\n"
    "/remind in 2 hours call mum\n"
    "/remind fri 3pm submit the report\n"
    "/remind 25/11 9:30am renew road tax\n"
    "/remind esok pukul 8 pagi temujanji doktor\n"
    "/remind 2 jam lagi angkat kain\n\n"
    "You can also just send a message starting with \"remind me\" or \"ingatkan saya\"."
)
NO_TIME_TEXT = "I couldn't find a time in that.\n\n" + REMIND_USAGE
PAST_TIME_TEXT = "That time ({when}) has already passed. Try a later time."
NO_TEXT_TEXT = "What should I remind you about? e.g. /remind tomorrow 7am dentist appointment"


def other_time_prompt_id(prompt_text: str | None) -> int | None:
    match = _OTHER_TIME_PROMPT_RE.match(prompt_text or "")
    return int(match.group(1)) if match else None


def natural_reminder_request(text: str) -> str | None:
    """What follows "remind me" / "ingatkan saya" at the start of a message, or None."""
    match = _NATURAL_PREFIX_RE.match(text)
    return match.group(2).strip() if match else None


def build_cancel_button(reminder_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"remundo:{reminder_id}")]])


async def create_text_reminder(message: Message, user_id: int, request: str) -> None:
    """/remind and "remind me ..." messages: read the time, save, confirm."""
    if not request.strip():
        await message.reply_text(REMIND_USAGE)
        return
    now = _local_now()
    parsed = parse_reminder(request, now)
    if parsed is None:
        await message.reply_text(NO_TIME_TEXT)
        return
    if parsed.when <= now:
        await message.reply_text(PAST_TIME_TEXT.format(when=format_when(parsed.when)))
        return
    if not parsed.text:
        await message.reply_text(NO_TEXT_TEXT)
        return
    reminder_id = await asyncio.to_thread(
        add_reminder, user_id, None, parsed.when.astimezone(timezone.utc).isoformat(), parsed.text
    )
    await message.reply_text(
        f"⏰ Got it. I'll remind you: {parsed.text}\n🗓 {format_when(parsed.when)}",
        reply_markup=build_cancel_button(reminder_id),
    )


async def remind_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id if update.effective_user else None
    if user_id is None or not config.is_authorized(user_id):
        await update.message.reply_text("Sorry, this bot is private.")
        return
    await create_text_reminder(update.message, user_id, " ".join(context.args))


async def apply_other_time(message: Message, user_id: int, item_id: int) -> None:
    """A reply to the 🕐 Other time… prompt under a saved note."""
    now = _local_now()
    parsed = parse_reminder(message.text or "", now)
    if parsed is None:
        await message.reply_text("I couldn't find a time in that. Try e.g. \"tomorrow 8am\" or \"esok pukul 3 petang\".")
        return
    if parsed.when <= now:
        await message.reply_text(PAST_TIME_TEXT.format(when=format_when(parsed.when)))
        return
    item = await asyncio.to_thread(get_by_id, item_id, user_id)
    if item is None:
        await message.reply_text(f"Couldn't find #{item_id} anymore.")
        return
    reminder_id = await asyncio.to_thread(add_reminder, user_id, item_id, parsed.when.astimezone(timezone.utc).isoformat())
    await message.reply_text(
        f"⏰ I'll remind you about #{item_id} — {display_title(item)} on {format_when(parsed.when)}.",
        reply_markup=build_cancel_button(reminder_id),
    )


async def handle_undo_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """❌ Cancel on a reminder confirmation."""
    query = update.callback_query
    user_id = update.effective_user.id if update.effective_user else None
    if query is None or query.data is None:
        return
    await query.answer()
    if user_id is None or not config.is_authorized(user_id):
        return
    cancelled = await asyncio.to_thread(delete_reminder, int(query.data.split(":")[1]), user_id)
    await query.edit_message_text("❌ Reminder cancelled." if cancelled else "That reminder was already sent or cancelled.")


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
        if reminder.get("item_id") is None:
            label = reminder["text"]
        else:
            label = f"#{reminder['item_id']} {display_title(reminder)}"
        lines.append(f"• {when} — {label}")
        short = label if len(label) <= 24 else label[:23] + "…"
        buttons.append(InlineKeyboardButton(f"✖ {short}, {when}", callback_data=f"remcancel:{reminder['id']}"))
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
        if reminder["item_id"] is None:
            text, markup = f"⏰ <b>Reminder:</b> {html.escape(reminder['text'] or '', quote=False)}", None
        else:
            item = await asyncio.to_thread(get_by_id, reminder["item_id"], reminder["user_id"])
            if item is None:
                text = None
            else:
                text = "⏰ <b>Reminder</b>: you wanted to look at this again.\n\n" + format_full_item(item)
                markup = keyboard_for(item)
        if text is not None:
            try:
                await bot.send_message(chat_id=reminder["user_id"], text=text, parse_mode=ParseMode.HTML, reply_markup=markup)
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

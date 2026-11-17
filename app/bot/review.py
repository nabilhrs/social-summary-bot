"""
/review: one older note at a time. It shows only the title first ("do you
remember this one?"), then the summary on Reveal, then asks whether it's
still useful. Kept notes come back after KEEP_FOR_DAYS; archived ones leave
/list and /review but stay searchable. No Gemini requests.

Buttons (stateless, memory.md #5): rev:<action>:<id>, where action is
show / skip / keep / arch / undo / next. unarch:<id> is the Unarchive
button under an archived note's summary.
"""
import asyncio
import html
from datetime import datetime, timedelta, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from app.bot.actions import keyboard_for_item
from app.bot.browse import display_title
from app.bot.formatting import render_summary_html
from app.config import config
from app.database.database import get_by_id, get_review_candidate, mark_reviewed, set_archived

MIN_AGE_DAYS = 7
KEEP_FOR_DAYS = 30
_MAX_SUMMARY_CHARS = 2500
NOTHING_TO_REVIEW_TEXT = (
    "🧠 Nothing to review right now. Notes show up here once they're a week "
    "old, and ones you keep come back after a month."
)


def _escape(value) -> str:
    return html.escape(str(value), quote=False)


def age_text(created_iso: str, now: datetime) -> str:
    days = max(0, (now - datetime.fromisoformat(created_iso)).days)
    if days < 14:
        return f"{days} day{'s' if days != 1 else ''} ago"
    if days < 60:
        return f"{days // 7} weeks ago"
    if days < 730:
        return f"{days // 30} months ago"
    return f"{days // 365} years ago"


def _header(item: dict, now: datetime) -> list[str]:
    details = f"saved {age_text(item['created_at'], now)}"
    if item.get("category"):
        details = f"📂 {_escape(item['category'])} · {details}"
    return [f"<b>#{item['id']} — {_escape(display_title(item))}</b>", details]


def _button(text: str, action: str, item_id: int = 0) -> InlineKeyboardButton:
    return InlineKeyboardButton(text, callback_data=f"rev:{action}:{item_id}")


def build_question(item: dict, now: datetime):
    text = "\n".join(
        ["🧠 <b>Do you remember this one?</b>", ""]
        + _header(item, now)
        + ["", "<i>Think about what it said, then tap Reveal.</i>"]
    )
    markup = InlineKeyboardMarkup([[_button("👀 Reveal", "show", item["id"]), _button("⏭ Skip", "skip", item["id"])]])
    return text, markup


def build_revealed(item: dict, now: datetime):
    summary = item["summary"]
    if len(summary) > _MAX_SUMMARY_CHARS:
        summary = summary[:_MAX_SUMMARY_CHARS].rsplit("\n", 1)[0] + "\n…"
    lines = ["🧠 " + _header(item, now)[0], _header(item, now)[1], "", render_summary_html(summary)]
    if item.get("user_note"):
        lines += ["", f"<b>📝 Your note:</b> {_escape(item['user_note'])}"]
    lines += ["", f"<b>Still useful?</b> <i>/view {item['id']} for the full note</i>"]
    markup = InlineKeyboardMarkup(
        [
            [_button("👍 Still useful", "keep", item["id"]), _button("📦 Archive", "arch", item["id"])],
            [_button("🧠 Next note", "next", item["id"])],
        ]
    )
    return "\n".join(lines), markup


def build_kept(item: dict):
    text = (
        f"👍 Kept #{item['id']} — {_escape(display_title(item))}. "
        f"I'll bring it up again in about {KEEP_FOR_DAYS} days."
    )
    return text, InlineKeyboardMarkup([[_button("🧠 Next note", "next", item["id"])]])


def build_archived(item: dict):
    text = (
        f"📦 Archived #{item['id']} — {_escape(display_title(item))}.\n\n"
        "It's out of /list and /review now, but /search and /ask still find it, "
        "and it's under /list → 📦 Archived."
    )
    markup = InlineKeyboardMarkup(
        [[_button("↩️ Undo", "undo", item["id"]), _button("🧠 Next note", "next", item["id"])]]
    )
    return text, markup


def pick_note(user_id: int, now: datetime, exclude_id: int | None = None) -> dict | None:
    saved_before = (now - timedelta(days=MIN_AGE_DAYS)).isoformat()
    reviewed_before = (now - timedelta(days=KEEP_FOR_DAYS)).isoformat()
    return get_review_candidate(user_id, saved_before, reviewed_before, exclude_id)


def _authorized(update: Update) -> int | None:
    user_id = update.effective_user.id if update.effective_user else None
    return user_id if user_id is not None and config.is_authorized(user_id) else None


async def review_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = _authorized(update)
    if user_id is None:
        await update.message.reply_text("Sorry, this bot is private.")
        return
    now = datetime.now(timezone.utc)
    item = await asyncio.to_thread(pick_note, user_id, now)
    if item is None:
        await update.message.reply_text(NOTHING_TO_REVIEW_TEXT)
        return
    text, markup = build_question(item, now)
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)


async def _edit(query, text: str, markup) -> None:
    try:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
    except BadRequest as exc:
        if "not modified" not in str(exc).lower():
            raise


async def handle_review_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return
    await query.answer()
    user_id = _authorized(update)
    if user_id is None:
        return

    _, action, id_str = query.data.split(":")
    item_id = int(id_str)
    now = datetime.now(timezone.utc)

    if action in ("skip", "next"):
        item = await asyncio.to_thread(pick_note, user_id, now, item_id)
        if item is None:
            text, markup = NOTHING_TO_REVIEW_TEXT, None
        else:
            text, markup = build_question(item, now)
        if action == "skip":
            await _edit(query, text, markup)  # a skipped card is replaced in place
        else:
            await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
        return

    item = await asyncio.to_thread(get_by_id, item_id, user_id)
    if item is None:
        await _edit(query, f"#{item_id} isn't there anymore.", InlineKeyboardMarkup([[_button("🧠 Next note", "next", item_id)]]))
        return

    if action == "show":
        await _edit(query, *build_revealed(item, now))
    elif action == "keep":
        await asyncio.to_thread(mark_reviewed, item_id, user_id, now.isoformat())
        await _edit(query, *build_kept(item))
    elif action == "arch":
        await asyncio.to_thread(set_archived, item_id, user_id, True)
        await asyncio.to_thread(mark_reviewed, item_id, user_id, now.isoformat())
        await _edit(query, *build_archived(item))
    elif action == "undo":
        await asyncio.to_thread(set_archived, item_id, user_id, False)
        await _edit(query, *build_revealed(item, now))


async def handle_unarchive_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """The Unarchive button under an archived note's summary."""
    query = update.callback_query
    if query is None or query.data is None:
        return
    user_id = _authorized(update)
    if user_id is None:
        await query.answer()
        return
    item_id = int(query.data.split(":")[1])
    if not await asyncio.to_thread(set_archived, item_id, user_id, False):
        await query.answer(f"Couldn't find #{item_id} anymore.")
        return
    await query.answer("📤 Back in /list")
    item = await asyncio.to_thread(get_by_id, item_id, user_id)
    await query.edit_message_reply_markup(reply_markup=keyboard_for_item(item))

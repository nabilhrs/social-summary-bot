"""
Handler for plain (non-command) messages, plus Combine Mode's merge callback.

Full pipeline (PRD 5.1-5.5, 5.7, 5.9): detect URL vs plain text -> extract if
URL -> normalize -> summarize (flagging related saved items) -> reply -> save
-> optionally offer to merge with a related item.
"""
import asyncio
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.config import config
from app.extractors.base import (
    looks_like_url,
    detect_unsupported_platform,
    normalize_pasted_text,
    normalize_web_article,
)
from app.extractors.webpage import fetch_and_extract
from app.ai.summarizer import summarize, merge_summaries
from app.database.database import (
    save_summary,
    get_recent,
    get_by_id,
    update_merged_summary,
    delete_item,
)

logger = logging.getLogger(__name__)

# PRD 5.9 — fixed error responses for each failure path.
UNAUTHORIZED_TEXT = "Sorry, this bot is private."
INVALID_INPUT_TEXT = "That doesn't look like a link or usable text."
EXTRACTION_FAILED_TEXT = (
    "I couldn't extract this article automatically. Please paste the text here and I'll summarize it."
)
UNSUPPORTED_PLATFORM_TEXT = (
    "{platform} doesn't allow me to pull post content automatically. "
    "Please paste the text here and I'll summarize it."
)
SUMMARY_FAILED_TEXT = "Something went wrong while generating the summary. Please try again."

# PRD 5.5 — how many recent saved items to check new content against.
_RECENT_HISTORY_LIMIT = 10


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.message

    if message is None or message.text is None:
        return

    if user is None or not config.is_authorized(user.id):
        await message.reply_text(UNAUTHORIZED_TEXT)
        return

    raw_text = message.text.strip()
    if not raw_text:
        await message.reply_text(INVALID_INPUT_TEXT)
        return

    if looks_like_url(raw_text):
        platform = detect_unsupported_platform(raw_text)
        if platform is not None:
            await message.reply_text(UNSUPPORTED_PLATFORM_TEXT.format(platform=platform))
            return

        extracted = await fetch_and_extract(raw_text)
        if extracted is None:
            await message.reply_text(EXTRACTION_FAILED_TEXT)
            return
        content = normalize_web_article(raw_text, extracted)
    else:
        content = normalize_pasted_text(raw_text)

    recent_items = await asyncio.to_thread(get_recent, _RECENT_HISTORY_LIMIT)

    summary = await summarize(content, recent_items)
    if summary is None:
        await message.reply_text(SUMMARY_FAILED_TEXT)
        return

    await message.reply_text(summary.text)

    try:
        new_id = await asyncio.to_thread(save_summary, content, summary.text)
    except Exception:
        logger.exception("Failed to save summary to database")
        return

    match = next((item for item in recent_items if item["id"] == summary.related_id), None)
    if match is None:
        return

    # Merge decision is encoded directly in callback_data (merge:<yes|no>:<existing_id>:<new_id>)
    # rather than kept in memory — that state must survive a bot restart, and must not depend on
    # which process instance handles the eventual button click.
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Yes, merge", callback_data=f"merge:yes:{match['id']}:{new_id}"),
                InlineKeyboardButton("No, keep separate", callback_data=f"merge:no:{match['id']}:{new_id}"),
            ]
        ]
    )
    title = match["title"] or "Untitled"
    await message.reply_text(
        f"This looks related to #{match['id']} — {title}. Want me to merge these into one summary?",
        reply_markup=keyboard,
    )


async def handle_merge_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user

    if query is None or query.data is None:
        return
    await query.answer()

    if user is None or not config.is_authorized(user.id):
        await query.edit_message_text(UNAUTHORIZED_TEXT)
        return

    _, decision, existing_id_str, new_id_str = query.data.split(":")
    existing_id, new_id = int(existing_id_str), int(new_id_str)

    if decision == "no":
        await query.edit_message_text("Kept as a separate entry.")
        return

    old_row = await asyncio.to_thread(get_by_id, existing_id)
    new_row = await asyncio.to_thread(get_by_id, new_id)
    if old_row is None or new_row is None:
        await query.edit_message_text("Couldn't find one of those entries anymore — nothing merged.")
        return

    merged = await merge_summaries(
        old_row["original_text"], new_row["original_text"], old_row["title"], new_row["title"]
    )
    if merged is None:
        await query.edit_message_text(SUMMARY_FAILED_TEXT)
        return

    try:
        await asyncio.to_thread(update_merged_summary, old_row["id"], merged.text, new_row["id"])
    except Exception:
        logger.exception("Failed to save merged summary to database")
        await query.edit_message_text(SUMMARY_FAILED_TEXT)
        return

    await query.edit_message_text(f"Merged into #{old_row['id']}:\n\n{merged.text}")


async def handle_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user

    if query is None or query.data is None:
        return
    await query.answer()

    if user is None or not config.is_authorized(user.id):
        await query.edit_message_text(UNAUTHORIZED_TEXT)
        return

    _, decision, id_str = query.data.split(":")
    item_id = int(id_str)

    if decision == "no":
        await query.edit_message_text("Cancelled — nothing deleted.")
        return

    deleted = await asyncio.to_thread(delete_item, item_id)
    if not deleted:
        await query.edit_message_text(f"Couldn't find #{item_id} anymore — nothing deleted.")
        return

    await query.edit_message_text(f"Deleted #{item_id}.")

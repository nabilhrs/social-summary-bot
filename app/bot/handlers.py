"""
Handler for plain (non-command) messages, plus Combine Mode's merge callback.

Full pipeline (PRD 5.1-5.5, 5.7, 5.9): detect URL vs plain text -> extract if
URL -> normalize -> summarize (flagging related saved items) -> reply -> save
-> optionally offer to merge with a related item.
"""
import asyncio
import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from app.config import config
from app.extractors.base import (
    looks_like_url,
    detect_unsupported_platform,
    is_threads_url,
    is_tiktok_url,
    normalize_pasted_text,
    normalize_web_article,
    normalize_threads_post,
    normalize_tiktok_video,
)
from app.extractors.webpage import fetch_and_extract
from app.extractors.threads import fetch_and_extract as fetch_threads_post
from app.extractors.tiktok import fetch_and_extract as fetch_tiktok_video
from app.ai.gemini import INVALID_KEY, QUOTA_DAILY, QUOTA_RATE, UNAVAILABLE, GeminiError
from app.ai.related import pick_candidates
from app.ai.summarizer import summarize, merge_summaries
from app.database.database import (
    save_summary,
    get_recent,
    get_by_id,
    update_merged_summary,
    delete_item,
    resolve_gemini_api_key,
)
from app.bot.formatting import format_full_item, build_merge_keyboard, render_summary_html

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
GEMINI_ERROR_TEXTS = {
    QUOTA_DAILY: (
        "Your Gemini API key has used up today's free quota on every model I can "
        "fall back to. It resets at midnight Pacific time — send this again after that."
    ),
    QUOTA_RATE: "Gemini's per-minute rate limit was hit. Wait a minute and send this again.",
    INVALID_KEY: (
        "Gemini rejected the API key. Update GEMINI_API_KEY in the server's .env "
        "(then restart the bot), or send /setkey <new-key>."
    ),
    UNAVAILABLE: (
        "Gemini is overloaded or unreachable right now — I retried and tried backup "
        "models too. Try again in a few minutes."
    ),
}
NO_API_KEY_TEXT = (
    "You need your own Gemini API key before I can generate summaries for you. "
    "Get a free one at https://aistudio.google.com/apikey, then send /setkey <your-key>."
)
TIKTOK_PROCESSING_TEXT = "🎥 Downloading and analyzing this TikTok video — this may take a moment..."
THREADS_LIMITATION_NOTE = (
    "ℹ️ Threads posts can be part of a longer thread (including Threads' own "
    "native \"1/9\"-style numbering, which isn't visible to a plain link fetch). "
    "I can only read the post you linked, not any replies — paste the rest too "
    "if you want the full picture."
)

# PRD 5.5 — recent saved items always checked against new content; older
# keyword-matched items are added on top (see app/ai/related.py).
_RECENT_HISTORY_LIMIT = 10


def _gemini_error_text(exc: GeminiError) -> str:
    return GEMINI_ERROR_TEXTS.get(exc.kind, SUMMARY_FAILED_TEXT)


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

    # Resolved before any extraction work — no point downloading a TikTok
    # video (the slowest, most expensive path) only to fail at the
    # summarize step for lack of a key.
    api_key = await asyncio.to_thread(resolve_gemini_api_key, user.id)
    if api_key is None:
        await message.reply_text(NO_API_KEY_TEXT)
        return

    is_threads_content = False

    if looks_like_url(raw_text):
        platform = detect_unsupported_platform(raw_text)
        if platform is not None:
            await message.reply_text(UNSUPPORTED_PLATFORM_TEXT.format(platform=platform))
            return

        if is_tiktok_url(raw_text):
            await message.reply_text(TIKTOK_PROCESSING_TEXT)
            try:
                extracted = await fetch_tiktok_video(raw_text, api_key)
            except GeminiError as exc:
                await message.reply_text(_gemini_error_text(exc))
                return
            if extracted is None:
                await message.reply_text(EXTRACTION_FAILED_TEXT)
                return
            content = normalize_tiktok_video(raw_text, extracted)
        elif is_threads_url(raw_text):
            extracted = await fetch_threads_post(raw_text)
            if extracted is None:
                await message.reply_text(EXTRACTION_FAILED_TEXT)
                return
            is_threads_content = True
            content = normalize_threads_post(raw_text, extracted)
        else:
            extracted = await fetch_and_extract(raw_text)
            if extracted is None:
                await message.reply_text(EXTRACTION_FAILED_TEXT)
                return
            content = normalize_web_article(raw_text, extracted)
    else:
        content = normalize_pasted_text(raw_text)

    all_items = await asyncio.to_thread(get_recent, user.id, None)
    recent_items = pick_candidates(content["text"], all_items, recent_limit=_RECENT_HISTORY_LIMIT)

    try:
        summary = await summarize(content, recent_items, api_key)
    except GeminiError as exc:
        await message.reply_text(_gemini_error_text(exc))
        return

    await message.reply_text(render_summary_html(summary.text), parse_mode=ParseMode.HTML)
    if is_threads_content:
        await message.reply_text(THREADS_LIMITATION_NOTE)

    try:
        new_id = await asyncio.to_thread(save_summary, content, summary.text, user.id)
    except Exception:
        logger.exception("Failed to save summary to database")
        return

    match = next((item for item in recent_items if item["id"] == summary.related_id), None)
    if match is None:
        return

    # Merge decision is encoded directly in callback_data (merge:<yes|no|view>:<existing_id>:<new_id>)
    # rather than kept in memory — that state must survive a bot restart, and must not depend on
    # which process instance handles the eventual button click.
    title = match["title"] or "Untitled"
    await message.reply_text(
        f"This looks related to #{match['id']} — {title}. Want me to merge these into one summary?",
        reply_markup=build_merge_keyboard(match["id"], new_id),
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

    if decision == "view":
        # Sends a new message rather than editing the suggestion, so the
        # original Yes/No/View buttons stay intact for a decision afterward —
        # viewing is optional and shouldn't consume the prompt (see PRD V2
        # discussion: "not compulsory, just an added option").
        old_row = await asyncio.to_thread(get_by_id, existing_id, user.id)
        if old_row is None:
            await query.message.reply_text(f"Couldn't find #{existing_id} anymore.")
            return
        await query.message.reply_text(format_full_item(old_row), parse_mode=ParseMode.HTML)
        return

    if decision == "no":
        await query.edit_message_text("Kept as a separate entry.")
        return

    api_key = await asyncio.to_thread(resolve_gemini_api_key, user.id)
    if api_key is None:
        await query.edit_message_text(NO_API_KEY_TEXT)
        return

    old_row = await asyncio.to_thread(get_by_id, existing_id, user.id)
    new_row = await asyncio.to_thread(get_by_id, new_id, user.id)
    if old_row is None or new_row is None:
        await query.edit_message_text("Couldn't find one of those entries anymore — nothing merged.")
        return

    try:
        merged = await merge_summaries(
            old_row["original_text"], new_row["original_text"], old_row["title"], new_row["title"], api_key
        )
    except GeminiError as exc:
        # Sent as a new message so the merge buttons stay usable for a retry.
        await query.message.reply_text(_gemini_error_text(exc))
        return

    try:
        await asyncio.to_thread(update_merged_summary, old_row["id"], merged.text, new_row["id"], user.id)
    except Exception:
        logger.exception("Failed to save merged summary to database")
        await query.edit_message_text(SUMMARY_FAILED_TEXT)
        return

    await query.edit_message_text(
        f"<b>Merged into #{old_row['id']}:</b>\n\n{render_summary_html(merged.text)}",
        parse_mode=ParseMode.HTML,
    )


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

    deleted = await asyncio.to_thread(delete_item, item_id, user.id)
    if not deleted:
        await query.edit_message_text(f"Couldn't find #{item_id} anymore — nothing deleted.")
        return

    await query.edit_message_text(f"Deleted #{item_id}.")

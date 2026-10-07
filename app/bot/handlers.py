"""
Handler for plain (non-command) messages, plus Combine Mode's merge callback.

Full pipeline (PRD 5.1-5.5, 5.7, 5.9): detect URL vs plain text -> extract if
URL -> normalize -> summarize (flagging related saved items) -> reply -> save
-> optionally offer to merge with a related item.
"""
import asyncio
import logging

from telegram import Message, Update
from telegram.constants import ChatAction, ParseMode
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
from app.extractors.media import (
    AUDIO,
    IMAGE,
    MAX_DOWNLOAD_BYTES,
    PDF,
    TEXT,
    VIDEO,
    MediaInfo,
    build_text as build_media_text,
    classify_document,
    extract_text,
)
from app.ai.gemini import GeminiError
from app.ai.related import pick_candidates
from app.ai.summarizer import summarize, merge_summaries
from app.database.database import (
    save_summary,
    get_categories,
    get_recent,
    get_by_id,
    update_merged_summary,
    delete_item,
    resolve_gemini_api_key,
)
from app.bot.formatting import (
    NO_API_KEY_TEXT,
    SUMMARY_FAILED_TEXT,
    build_merge_keyboard,
    format_full_item,
    format_saved_summary,
    gemini_error_text,
    render_summary_html,
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
TIKTOK_PROCESSING_TEXT = "🎥 Downloading and analyzing this TikTok video — this may take a moment..."
MEDIA_PROCESSING_TEXTS = {
    IMAGE: "🖼️ Reading your image...",
    AUDIO: "🎙️ Transcribing your audio — this may take a moment...",
    VIDEO: "🎥 Watching your video — this may take a moment...",
    PDF: "📄 Reading your PDF — this may take a moment...",
    TEXT: "📄 Reading your file...",
}
UNSUPPORTED_FILE_TEXT = (
    "I can't read this file type. I can summarize PDFs, plain-text files, "
    "images, audio, and video."
)
FILE_TOO_LARGE_TEXT = "That file is over 20 MB — Telegram doesn't let bots download files that big."
MEDIA_DOWNLOAD_FAILED_TEXT = "I couldn't download that file from Telegram. Please try sending it again."
MEDIA_EMPTY_TEXT = "I couldn't find anything to summarize in that file."
UNSUPPORTED_MESSAGE_TEXT = (
    "I can't summarize this kind of message. Send me text, a link, a photo or "
    "screenshot, a voice note, audio, a video, or a PDF/text file."
)
THREADS_LIMITATION_NOTE = (
    "ℹ️ Threads posts can be part of a longer thread (including Threads' own "
    "native \"1/9\"-style numbering, which isn't visible to a plain link fetch). "
    "I can only read the post you linked, not any replies — paste the rest too "
    "if you want the full picture."
)

# PRD 5.5 — recent saved items always checked against new content; older
# keyword-matched items are added on top (see app/ai/related.py).
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
                await message.reply_text(gemini_error_text(exc))
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

    await _summarize_and_save(message, user.id, api_key, content)
    if is_threads_content:
        await message.reply_text(THREADS_LIMITATION_NOTE)


async def _summarize_and_save(message: Message, user_id: int, api_key: str, content: dict) -> None:
    """Shared tail of every input path: summarize, save, reply, and offer a
    merge if Gemini flagged a related saved item."""
    all_items = await asyncio.to_thread(get_recent, user_id, None)
    recent_items = pick_candidates(content["text"], all_items, recent_limit=_RECENT_HISTORY_LIMIT)

    categories = [name for name, _count in await asyncio.to_thread(get_categories, user_id)]

    await message.chat.send_action(ChatAction.TYPING)
    try:
        summary = await summarize(content, recent_items, api_key, categories)
    except GeminiError as exc:
        await message.reply_text(gemini_error_text(exc))
        return

    # Web articles keep their real headline; everything else gets the generated title.
    if not (content["source"] == "web" and content.get("title")):
        content = {**content, "title": summary.title or content.get("title")}

    try:
        new_id = await asyncio.to_thread(save_summary, content, summary.text, user_id, summary.category)
    except Exception:
        logger.exception("Failed to save summary to database")
        new_id = None

    await message.reply_text(
        format_saved_summary(new_id, content.get("title"), summary.category, summary.text),
        parse_mode=ParseMode.HTML,
    )
    if new_id is None:
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


def _media_info(message: Message):
    """(Telegram file object, MediaInfo) for a supported media message, or
    (None, None) if it's a document type this bot can't read."""
    if message.photo:
        photo = message.photo[-1]  # largest resolution
        return photo, MediaInfo(IMAGE, "photo", "image/jpeg", photo.file_size)
    if message.voice:
        voice = message.voice
        return voice, MediaInfo(AUDIO, "voice", voice.mime_type or "audio/ogg", voice.file_size)
    if message.audio:
        audio = message.audio
        name = audio.title or audio.file_name
        return audio, MediaInfo(AUDIO, "audio", audio.mime_type or "audio/mpeg", audio.file_size, name)
    if message.video:
        video = message.video
        return video, MediaInfo(VIDEO, "video", video.mime_type or "video/mp4", video.file_size, video.file_name)
    if message.video_note:
        note = message.video_note
        return note, MediaInfo(VIDEO, "video", "video/mp4", note.file_size)
    if message.document:
        document = message.document
        kind = classify_document(document.mime_type)
        if kind is None:
            return None, None
        source = {PDF: "pdf", TEXT: "document"}.get(kind, kind)
        return document, MediaInfo(kind, source, document.mime_type, document.file_size, document.file_name)
    return None, None


async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.message
    if message is None:
        return
    if user is None or not config.is_authorized(user.id):
        await message.reply_text(UNAUTHORIZED_TEXT)
        return

    file_obj, info = _media_info(message)
    if info is None:
        await message.reply_text(UNSUPPORTED_FILE_TEXT)
        return
    if info.file_size and info.file_size > MAX_DOWNLOAD_BYTES:
        await message.reply_text(FILE_TOO_LARGE_TEXT)
        return

    api_key = await asyncio.to_thread(resolve_gemini_api_key, user.id)
    if api_key is None:
        await message.reply_text(NO_API_KEY_TEXT)
        return

    await message.reply_text(MEDIA_PROCESSING_TEXTS[info.kind])
    try:
        telegram_file = await file_obj.get_file()
        data = bytes(await telegram_file.download_as_bytearray())
    except Exception:
        logger.exception("Failed to download %s from Telegram", info.source)
        await message.reply_text(MEDIA_DOWNLOAD_FAILED_TEXT)
        return

    try:
        extracted = await asyncio.to_thread(extract_text, api_key, data, info)
    except GeminiError as exc:
        await message.reply_text(gemini_error_text(exc))
        return
    if not extracted:
        await message.reply_text(MEDIA_EMPTY_TEXT)
        return

    content = {
        "title": info.file_name,
        "author": None,
        "source": info.source,
        "url": None,
        "text": build_media_text(extracted, message.caption),
    }
    await _summarize_and_save(message, user.id, api_key, content)


async def handle_unsupported(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if update.message is None or user is None or not config.is_authorized(user.id):
        return
    await update.message.reply_text(UNSUPPORTED_MESSAGE_TEXT)


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
        await query.message.reply_text(gemini_error_text(exc))
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

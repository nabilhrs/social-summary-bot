"""
Handler for plain (non-command) messages, plus Combine Mode's merge callback.

Full pipeline (PRD 5.1-5.5, 5.7, 5.9): detect URL vs plain text -> extract if
URL -> normalize -> summarize (flagging related saved items) -> reply -> save
-> optionally offer to merge with a related item.
"""
import asyncio
import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import ContextTypes

from app.config import config
from app.extractors.base import (
    VIDEO_PLATFORM_NAMES,
    link_key,
    looks_like_url,
    detect_unsupported_platform,
    is_threads_url,
    normalize_pasted_text,
    normalize_web_article,
    normalize_threads_post,
    normalize_video_post,
    normalize_youtube_video,
    video_platform,
    youtube_video_id,
)
from app.extractors.webpage import fetch_and_extract
from app.extractors.threads import fetch_and_extract as fetch_threads_post
from app.extractors.video_link import NO_VIDEO, VideoUnavailable, fetch_and_extract as fetch_video_link
from app.extractors.youtube import fetch_and_extract as fetch_youtube_video
from app.extractors.media import (
    ALBUM_PROMPT,
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
from app.ai.gemini import FAILED, QUOTA_DAILY, TEXT_ITEM, UNAVAILABLE, GeminiError, describe_many
from app.ai.related import pick_candidates
from app.ai.summarizer import summarize, merge_summaries
from app.bot.browse import display_title
from app.bot.retry import (
    MAX_ATTEMPTS,
    QUOTA_SCHEDULED_TEXT,
    RETRY_GAVE_UP_TEXT,
    RETRY_SCHEDULED_TEXT,
    RETRYABLE,
    ChatTarget,
    describe_wait,
    next_attempt_at,
)
from app.database.database import (
    add_pending_job,
    delete_job,
    reschedule_job,
    save_summary,
    get_categories,
    get_recent,
    get_saved_links,
    get_by_id,
    update_merged_summary,
    delete_item,
    resolve_gemini_api_key,
)
from app.bot.actions import apply_reply_edit, build_item_actions_keyboard
from app.bot.categories import apply_category_rename
from app.bot.formatting import (
    NO_API_KEY_TEXT,
    SUMMARY_FAILED_TEXT,
    TRANSCRIBED_SOURCES,
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
YOUTUBE_PROCESSING_TEXT = "▶️ Watching this YouTube video — longer videos take a while..."
YOUTUBE_FAILED_TEXT = (
    "I couldn't watch that YouTube video. It may be private, age-restricted, "
    "or too long. Send me a link to a different video, or paste the key points."
)
VIDEO_PROCESSING_TEXT ="🎥 Downloading this {platform} post — videos take a moment..."
VIDEO_FAILED_TEXT = (
    "I couldn't download that {platform} post. You can send me the video file itself, "
    "or a screenshot, and I'll summarize that instead."
)
NO_VIDEO_TEXT = (
    "I couldn't find a video or photos in that {platform} post. Send me a "
    "screenshot and I'll read it instead."
)
LOGIN_REQUIRED_TEXT = (
    "{platform} wouldn't show me that post without logging in. It may be private or a "
    "story, or {platform} may be limiting requests from my server. Send me the video "
    "file or a screenshot instead."
)
MEDIA_PROCESSING_TEXTS = {
    IMAGE: "🖼️ Reading your image...",
    AUDIO: "🎙️ Transcribing your audio — this may take a moment...",
    VIDEO: "🎥 Watching your video — this may take a moment...",
    PDF: "📄 Reading your PDF — this may take a moment...",
    TEXT: "📄 Reading your file...",
}
ALBUM_PROCESSING_TEXT = "📎 Reading your {count} files together{note} — this may take a moment..."
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

    if await apply_reply_edit(message, user.id) or await apply_category_rename(message, user.id):
        return

    # Checked before anything costs a Gemini request.
    if looks_like_url(raw_text):
        saved = await asyncio.to_thread(find_saved_link, user.id, raw_text)
        if saved is not None:
            await message.reply_text(already_saved_text(saved), reply_markup=build_duplicate_keyboard(saved["id"]))
            return

    await _process_input(message, user.id, raw_text)


def find_saved_link(user_id: int, url: str) -> dict | None:
    key = link_key(url)
    return next((item for item in get_saved_links(user_id) if link_key(item["url"]) == key), None)


def already_saved_text(item: dict) -> str:
    return f"📌 Already saved as #{item['id']} — {display_title(item)} ({item['created_at'][:10]})."


def build_duplicate_keyboard(item_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton(f"👀 View #{item_id}", callback_data=f"dup:view:{item_id}"),
            InlineKeyboardButton("🔄 Save again", callback_data=f"dup:again:{item_id}"),
        ]]
    )


async def handle_duplicate_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Buttons on an "Already saved" reply. "Save again" re-reads the link
    stored on the existing item, so no state is kept between messages."""
    query = update.callback_query
    user = update.effective_user
    if query is None or query.data is None:
        return
    await query.answer()
    if user is None or not config.is_authorized(user.id):
        return

    _, action, id_str = query.data.split(":")
    item = await asyncio.to_thread(get_by_id, int(id_str), user.id)
    if item is None or not item.get("url"):
        await query.message.reply_text(f"Couldn't find #{id_str} anymore.")
        return
    if action == "view":
        await query.message.reply_text(
            format_full_item(item),
            parse_mode=ParseMode.HTML,
            reply_markup=build_item_actions_keyboard(item["id"], item["source"], bool(item.get("starred"))),
        )
        return
    await query.edit_message_reply_markup(reply_markup=None)
    await _process_input(query.message, user.id, item["url"])


async def _process_input(message, user_id: int, raw_text: str, job: dict | None = None) -> bool:
    """Extract (for links), summarize and save. `message` is what replies go
    to. Returns False if it was put off for a later retry (see retry.py),
    True once it's finished, successfully or not. `job` is set when this is
    a background retry; progress messages are skipped then."""
    # Resolved before any extraction work — no point downloading a video
    # (the slowest, most expensive path) only to fail at the
    # summarize step for lack of a key.
    api_key = await asyncio.to_thread(resolve_gemini_api_key, user_id)
    if api_key is None:
        await message.reply_text(NO_API_KEY_TEXT)
        return True

    async def progress(text: str) -> None:
        if job is None:
            await message.reply_text(text)

    try:
        is_threads_content = False
        if looks_like_url(raw_text):
            platform = detect_unsupported_platform(raw_text)
            if platform is not None:
                await message.reply_text(UNSUPPORTED_PLATFORM_TEXT.format(platform=platform))
                return True

            video_source = video_platform(raw_text)
            youtube_id = youtube_video_id(raw_text)
            if youtube_id is not None:
                await progress(YOUTUBE_PROCESSING_TEXT)
                try:
                    extracted = await fetch_youtube_video(youtube_id, api_key)
                except GeminiError as exc:
                    if exc.kind != FAILED:
                        raise
                    await message.reply_text(YOUTUBE_FAILED_TEXT)
                    return True
                content = normalize_youtube_video(raw_text, extracted)
            elif video_source is not None:
                name = VIDEO_PLATFORM_NAMES[video_source]
                await progress(VIDEO_PROCESSING_TEXT.format(platform=name))
                try:
                    extracted = await fetch_video_link(raw_text, api_key)
                except VideoUnavailable as exc:
                    text = NO_VIDEO_TEXT if exc.reason == NO_VIDEO else LOGIN_REQUIRED_TEXT
                    await message.reply_text(text.format(platform=name))
                    return True
                if extracted is None:
                    await message.reply_text(VIDEO_FAILED_TEXT.format(platform=name))
                    return True
                content = normalize_video_post(raw_text, extracted, video_source)
            elif is_threads_url(raw_text):
                extracted = await fetch_threads_post(raw_text)
                if extracted is None:
                    await message.reply_text(EXTRACTION_FAILED_TEXT)
                    return True
                is_threads_content = True
                content = normalize_threads_post(raw_text, extracted)
            else:
                extracted = await fetch_and_extract(raw_text)
                if extracted is None:
                    await message.reply_text(EXTRACTION_FAILED_TEXT)
                    return True
                content = normalize_web_article(raw_text, extracted)
        else:
            content = normalize_pasted_text(raw_text)

        await _summarize_and_save(message, user_id, api_key, content)
    except GeminiError as exc:
        return await gemini_failure(message, user_id, exc, "text", {"text": raw_text}, job)
    if is_threads_content:
        await message.reply_text(THREADS_LIMITATION_NOTE)
    return True


async def gemini_failure(message, user_id: int, exc: GeminiError, kind: str, payload: dict, job: dict | None) -> bool:
    """A busy or rate-limited Gemini puts the work off for a retry instead
    of failing (False); anything else is reported and ends it (True)."""
    if exc.kind not in RETRYABLE:
        await message.reply_text(gemini_error_text(exc))
        return True
    attempts = job["attempts"] + 1 if job else 1
    if attempts > MAX_ATTEMPTS:
        await message.reply_text(RETRY_GAVE_UP_TEXT)
        return True
    now = datetime.now(timezone.utc)
    when = next_attempt_at(exc.kind, attempts, now)
    if job is not None:
        await asyncio.to_thread(reschedule_job, job["id"], attempts, when.isoformat())
        return False
    await asyncio.to_thread(
        add_pending_job, user_id, message.chat_id, message.message_id, kind, json.dumps(payload), when.isoformat()
    )
    template = QUOTA_SCHEDULED_TEXT if exc.kind == QUOTA_DAILY else RETRY_SCHEDULED_TEXT
    await message.reply_text(template.format(when=describe_wait(when, now)))
    return False


async def run_job(bot, job: dict) -> None:
    """One background retry of a saved pending job (see retry.py)."""
    target = ChatTarget(bot, job["chat_id"], job["message_id"])
    payload = json.loads(job["payload"])
    try:
        if job["kind"] == "text":
            finished = await _process_input(target, job["user_id"], payload["text"], job)
        else:
            finished = await process_files(target, job["user_id"], payload["files"], payload.get("caption"), job)
    except Exception:
        logger.exception("Pending job %s failed unexpectedly", job["id"])
        finished = job["attempts"] + 1 > MAX_ATTEMPTS
        if not finished:
            when = next_attempt_at(UNAVAILABLE, job["attempts"] + 1, datetime.now(timezone.utc))
            await asyncio.to_thread(reschedule_job, job["id"], job["attempts"] + 1, when.isoformat())
    if finished:
        await asyncio.to_thread(delete_job, job["id"])


async def _summarize_and_save(message, user_id: int, api_key: str, content: dict) -> None:
    """Shared tail of every input path: summarize, save, reply, and offer a
    merge if Gemini flagged a related saved item. Raises GeminiError; the
    caller decides whether to retry later."""
    all_items = await asyncio.to_thread(get_recent, user_id, None)
    recent_items = pick_candidates(content["text"], all_items, recent_limit=_RECENT_HISTORY_LIMIT)

    categories = [name for name, _count in await asyncio.to_thread(get_categories, user_id)]

    await message.chat.send_action(ChatAction.TYPING)
    summary = await summarize(content, recent_items, api_key, categories)

    # Web articles and YouTube videos keep their real title; everything else gets the generated one.
    if not (content["source"] in ("web", "youtube") and content.get("title")):
        content = {**content, "title": summary.title or content.get("title")}

    try:
        new_id = await asyncio.to_thread(save_summary, content, summary.text, user_id, summary.category)
    except Exception:
        logger.exception("Failed to save summary to database")
        new_id = None

    transcript = content["text"] if content["source"] in TRANSCRIBED_SOURCES else None
    await message.reply_text(
        format_saved_summary(new_id, content.get("title"), summary.category, summary.text, transcript),
        parse_mode=ParseMode.HTML,
        reply_markup=build_item_actions_keyboard(new_id, content["source"]) if new_id else None,
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
    if message.media_group_id:
        queue_album_item(message, user.id, file_obj, info)
        return
    if info is None:
        await message.reply_text(UNSUPPORTED_FILE_TEXT)
        return
    if info.file_size and info.file_size > MAX_DOWNLOAD_BYTES:
        await message.reply_text(FILE_TOO_LARGE_TEXT)
        return
    await process_files(message, user.id, [file_ref(file_obj, info)], message.caption)


def file_ref(file_obj, info: MediaInfo) -> dict:
    """What's needed to download and read a Telegram file again later; a
    plain dict so it can be saved with a pending job."""
    return {"file_id": file_obj.file_id, **asdict(info)}


async def process_files(
    message, user_id: int, refs: list[dict], caption: str | None, job: dict | None = None, skipped: int = 0
) -> bool:
    """Read one file, or several sent together, summarize and save. Returns
    False if put off for a retry, True once finished (see _process_input)."""
    api_key = await asyncio.to_thread(resolve_gemini_api_key, user_id)
    if api_key is None:
        await message.reply_text(NO_API_KEY_TEXT)
        return True
    infos = [MediaInfo(**{k: v for k, v in ref.items() if k != "file_id"}) for ref in refs]
    if job is None:
        if len(refs) == 1:
            await message.reply_text(MEDIA_PROCESSING_TEXTS[infos[0].kind])
        else:
            note = f" (skipping {skipped} I can't read)" if skipped else ""
            await message.reply_text(ALBUM_PROCESSING_TEXT.format(count=len(refs), note=note))

    try:
        bot = message.get_bot()
        files = [bytes(await (await bot.get_file(ref["file_id"])).download_as_bytearray()) for ref in refs]
    except Exception:
        logger.exception("Failed to download %d file(s) from Telegram", len(refs))
        await message.reply_text(MEDIA_DOWNLOAD_FAILED_TEXT)
        return True

    try:
        if len(refs) == 1:
            extracted = await asyncio.to_thread(extract_text, api_key, files[0], infos[0])
        else:
            items = [
                (data.decode("utf-8", errors="replace"), TEXT_ITEM) if info.kind == TEXT else (data, info.mime_type)
                for data, info in zip(files, infos)
            ]
            extracted = await asyncio.to_thread(describe_many, api_key, items, ALBUM_PROMPT, 90, 150)
        if not extracted:
            await message.reply_text(MEDIA_EMPTY_TEXT)
            return True
        single = len(refs) == 1
        content = {
            "title": infos[0].file_name if single else None,
            "author": None,
            "source": infos[0].source if single else "album",
            "url": None,
            "text": build_media_text(extracted, caption),
        }
        await _summarize_and_save(message, user_id, api_key, content)
    except GeminiError as exc:
        return await gemini_failure(message, user_id, exc, "files", {"files": refs, "caption": caption}, job)
    return True


# Telegram delivers an album (several files sent together) as separate
# messages sharing a media_group_id, with no "last one" marker. They're
# collected here until _ALBUM_WAIT_SECONDS pass with no new item, then read
# as one note. This is the one place state is held in memory between
# updates (see docs/memory.md #5): it only lasts seconds, and if the bot
# restarts mid-album, that album just needs resending.
_ALBUM_WAIT_SECONDS = 1.5
_albums: dict[str, list] = {}
_album_timers: dict[str, asyncio.Task] = {}


def queue_album_item(message: Message, user_id: int, file_obj, info) -> None:
    group_id = message.media_group_id
    _albums.setdefault(group_id, []).append((message, file_obj, info))
    timer = _album_timers.pop(group_id, None)
    if timer is not None:
        timer.cancel()
    _album_timers[group_id] = asyncio.create_task(_flush_album_later(group_id, user_id))


async def _flush_album_later(group_id: str, user_id: int) -> None:
    await asyncio.sleep(_ALBUM_WAIT_SECONDS)
    _album_timers.pop(group_id, None)
    parts = sorted(_albums.pop(group_id, []), key=lambda part: part[0].message_id)
    if parts:
        await process_album(parts, user_id)


async def process_album(parts: list, user_id: int) -> None:
    reply_to = parts[0][0]
    try:
        usable = [p for p in parts if p[2] is not None and not (p[2].file_size and p[2].file_size > MAX_DOWNLOAD_BYTES)]
        if not usable:
            await reply_to.reply_text(UNSUPPORTED_FILE_TEXT)
            return
        caption = next((m.caption for m, _, _ in parts if m.caption), None)
        refs = [file_ref(file_obj, info) for _m, file_obj, info in usable]
        await process_files(reply_to, user_id, refs, caption, skipped=len(parts) - len(usable))
    except Exception:
        logger.exception("Processing an album of %d file(s) failed", len(parts))
        await reply_to.reply_text(MEDIA_DOWNLOAD_FAILED_TEXT)


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

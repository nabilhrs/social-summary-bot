"""
Buttons under each saved summary (and /view): rename, change category, add a
note, delete, and for voice notes and audio, edit the transcript.

Rename, note, "new category" and transcript edits need typed text, so the bot sends a ForceReply
prompt containing the item id; the user's reply quotes that prompt, and
apply_reply_edit() reads the id back from it. Nothing is kept in memory
(see docs/memory.md #5).
"""
import asyncio
import html
import re

from telegram import ForceReply, InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import ContextTypes

from app.ai.gemini import GeminiError
from app.ai.summarizer import clean_category, clean_title, summarize
from app.bot.formatting import (
    NO_API_KEY_TEXT,
    TRANSCRIBED_SOURCES,
    format_saved_summary,
    gemini_error_text,
)
from app.config import config
from app.database.database import (
    append_note,
    get_by_id,
    get_categories,
    replace_text,
    resolve_gemini_api_key,
    update_fields,
)

RENAME_PROMPT = "✏️ Reply with a new title for #{id}"
NEW_CATEGORY_PROMPT = "📂 Reply with a new category name for #{id}"
NOTE_PROMPT = "📝 Reply with a note to add to #{id}"
TRANSCRIPT_PROMPT = "🎙 Reply with the corrected transcript for #{id}"
_RENAME_PROMPT_RE = re.compile(r"^✏️ Reply with a new title for #(\d+)")
_NEW_CATEGORY_PROMPT_RE = re.compile(r"^📂 Reply with a new category name for #(\d+)")
_NOTE_PROMPT_RE = re.compile(r"^📝 Reply with a note to add to #(\d+)")
_TRANSCRIPT_PROMPT_RE = re.compile(r"^🎙 Reply with the corrected transcript for #(\d+)")
# Telegram messages max out at 4096 characters, both the prompt that shows
# the transcript and the user's corrected reply.
MAX_EDITABLE_TRANSCRIPT = 3500


def build_item_actions_keyboard(item_id: int, source: str | None = None) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("✏️ Rename", callback_data=f"act:rename:{item_id}"),
            InlineKeyboardButton("📂 Category", callback_data=f"act:cat:{item_id}"),
        ],
        [
            InlineKeyboardButton("📝 Note", callback_data=f"act:note:{item_id}"),
            InlineKeyboardButton("🗑 Delete", callback_data=f"delconfirm:{item_id}"),
        ],
    ]
    if source in TRANSCRIBED_SOURCES:
        rows.insert(0, [InlineKeyboardButton("🎙 Edit transcript", callback_data=f"act:transcript:{item_id}")])
    return InlineKeyboardMarkup(rows)


def build_category_picker(item_id: int, categories: list[str], current: str | None) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(("✅ " if name == current else "") + name, callback_data=f"setcat:{item_id}:{name}")
        for name in categories
    ]
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    rows.append([InlineKeyboardButton("➕ New category", callback_data=f"act:newcat:{item_id}")])
    return InlineKeyboardMarkup(rows)


async def handle_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = update.effective_user.id if update.effective_user else None
    if query is None or query.data is None:
        return
    await query.answer()
    if user_id is None or not config.is_authorized(user_id):
        return

    _, action, id_str = query.data.split(":")
    item_id = int(id_str)
    item = await asyncio.to_thread(get_by_id, item_id, user_id)
    if item is None:
        await query.message.reply_text(f"Couldn't find #{item_id} anymore.")
        return

    if action == "rename":
        await query.message.reply_text(
            RENAME_PROMPT.format(id=item_id),
            reply_markup=ForceReply(input_field_placeholder="New title"),
        )
    elif action == "note":
        await query.message.reply_text(
            NOTE_PROMPT.format(id=item_id),
            reply_markup=ForceReply(input_field_placeholder="Your note"),
        )
    elif action == "transcript":
        text = item["original_text"]
        if len(text) > MAX_EDITABLE_TRANSCRIPT:
            await query.message.reply_text(
                f"#{item_id}'s transcript is too long to edit in a Telegram message "
                f"(over {MAX_EDITABLE_TRANSCRIPT:,} characters)."
            )
            return
        await query.message.reply_text(
            f"{TRANSCRIPT_PROMPT.format(id=item_id)}\n\n"
            "Tap the text below to copy it, fix what I misheard, and send it back as a reply to this message.\n\n"
            f"<pre>{html.escape(text, quote=False)}</pre>",
            parse_mode=ParseMode.HTML,
            reply_markup=ForceReply(input_field_placeholder="Corrected transcript"),
        )
    elif action == "newcat":
        await query.message.reply_text(
            NEW_CATEGORY_PROMPT.format(id=item_id),
            reply_markup=ForceReply(input_field_placeholder="New category"),
        )
    elif action == "cat":
        categories = [name for name, _count in await asyncio.to_thread(get_categories, user_id)]
        await query.message.reply_text(
            f"📂 Pick a category for #{item_id}:",
            reply_markup=build_category_picker(item_id, categories, item.get("category")),
        )


async def handle_setcat_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = update.effective_user.id if update.effective_user else None
    if query is None or query.data is None:
        return
    await query.answer()
    if user_id is None or not config.is_authorized(user_id):
        return

    _, id_str, category = query.data.split(":", 2)
    item_id = int(id_str)
    if not await asyncio.to_thread(update_fields, item_id, user_id, category=category):
        await query.edit_message_text(f"Couldn't find #{item_id} anymore.")
        return
    await query.edit_message_text(f"📂 Moved #{item_id} to {category}.")


def parse_reply_prompt(prompt_text: str | None) -> tuple[str, int] | None:
    """("rename" | "category" | "note" | "transcript", item id) if
    `prompt_text` is one of our prompts."""
    prompts = (
        ("rename", _RENAME_PROMPT_RE),
        ("category", _NEW_CATEGORY_PROMPT_RE),
        ("note", _NOTE_PROMPT_RE),
        ("transcript", _TRANSCRIPT_PROMPT_RE),
    )
    for kind, pattern in prompts:
        match = pattern.match(prompt_text or "")
        if match:
            return kind, int(match.group(1))
    return None


async def apply_reply_edit(message: Message, user_id: int) -> bool:
    """If `message` answers a rename/new-category prompt, apply it and return
    True; otherwise return False so it's handled as normal content."""
    replied = message.reply_to_message
    if replied is None or replied.from_user is None or not replied.from_user.is_bot:
        return False
    parsed = parse_reply_prompt(replied.text)
    if parsed is None:
        return False

    kind, item_id = parsed
    if kind == "transcript":
        await _apply_transcript_edit(message, user_id, item_id)
        return True
    if kind == "rename":
        title = clean_title(message.text)
        if title is None:
            await message.reply_text("That title is empty — nothing changed.")
            return True
        updated = await asyncio.to_thread(update_fields, item_id, user_id, title=title)
        reply = f"✏️ Renamed #{item_id} to: {title}"
    elif kind == "note":
        note = (message.text or "").strip()
        if not note:
            await message.reply_text("That note is empty — nothing changed.")
            return True
        updated = await asyncio.to_thread(append_note, item_id, user_id, note)
        reply = f"📝 Added your note to #{item_id}."
    else:
        existing = [name for name, _count in await asyncio.to_thread(get_categories, user_id)]
        category = clean_category(message.text, existing)
        if category is None:
            await message.reply_text("That category name is empty — nothing changed.")
            return True
        updated = await asyncio.to_thread(update_fields, item_id, user_id, category=category)
        reply = f"📂 Moved #{item_id} to {category}."

    await message.reply_text(reply if updated else f"Couldn't find #{item_id} anymore.")
    return True


async def _apply_transcript_edit(message: Message, user_id: int, item_id: int) -> None:
    """Saves the corrected transcript, then rewrites the summary and title
    from it. The transcript is saved even if Gemini then fails."""
    new_text = (message.text or "").strip()
    if not new_text:
        await message.reply_text("That transcript is empty — nothing changed.")
        return
    item = await asyncio.to_thread(get_by_id, item_id, user_id)
    if item is None:
        await message.reply_text(f"Couldn't find #{item_id} anymore.")
        return
    await asyncio.to_thread(replace_text, item_id, user_id, new_text, item["summary"], None)

    api_key = await asyncio.to_thread(resolve_gemini_api_key, user_id)
    if api_key is None:
        await message.reply_text(f"Saved the corrected transcript for #{item_id}. {NO_API_KEY_TEXT}")
        return
    categories = [name for name, _count in await asyncio.to_thread(get_categories, user_id)]
    content = {"title": None, "author": item.get("author"), "source": item["source"], "url": item.get("url"), "text": new_text}
    await message.chat.send_action(ChatAction.TYPING)
    try:
        summary = await summarize(content, [], api_key, categories)
    except GeminiError as exc:
        await message.reply_text(
            f"Saved the corrected transcript for #{item_id}, but couldn't rewrite the summary. {gemini_error_text(exc)}"
        )
        return

    title = summary.title or item.get("title")
    await asyncio.to_thread(replace_text, item_id, user_id, new_text, summary.text, title)
    await message.reply_text(
        "✅ Transcript updated and summary rewritten.\n\n"
        + format_saved_summary(item_id, title, item.get("category"), summary.text, new_text),
        parse_mode=ParseMode.HTML,
        reply_markup=build_item_actions_keyboard(item_id, item["source"]),
    )

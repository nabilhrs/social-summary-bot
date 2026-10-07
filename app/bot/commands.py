"""
Slash-command handlers (PRD 5.6, PRD V2 2.2).

/summarize is intentionally not implemented — auto-detection in
app/bot/handlers.py covers both URL and pasted text without a command.
"""
import asyncio
from datetime import datetime, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction, ParseMode
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from app.ai.gemini import QUOTA_DAILY, QUOTA_RATE, UNAVAILABLE, GeminiError, generate_text
from app.ai.summarizer import answer_question, clean_category, clean_title
from app.config import config
from app.database.database import (
    append_note,
    get_all_items,
    get_categories,
    update_fields,
    search_items,
    get_by_id,
    undo_merge,
    set_user_api_key,
    resolve_gemini_api_key,
)
from app.bot.actions import build_item_actions_keyboard
from app.bot.browse import CATEGORY, MENU_CALLBACK, decode_page, format_item_line, render_menu, render_page
from app.bot.export import build_json, build_markdown
from app.bot.formatting import (
    NO_API_KEY_TEXT,
    build_delete_keyboard,
    build_list_delete_keyboard,
    build_merge_keyboard,
    format_full_item,
    gemini_error_text,
    render_summary_html,
)

WELCOME_TEXT = (
    "👋 Hey! I'm your personal content summarizer.\n\n"
    "Send me a link (articles, Threads posts, TikTok videos), paste text, or "
    "send a photo, screenshot, voice note, video, or PDF — I'll send back a "
    "summary and save it. If something looks related to an earlier save, I'll "
    "offer to merge them.\n\n"
    "Later, use /ask to ask questions about everything you've saved.\n\n"
    "Type /help to see everything I can do."
)

HELP_TEXT = (
    "*What I can do*\n\n"
    "• Send a URL — articles, Threads posts, or TikTok videos — and I'll "
    "extract and summarize it. TikTok videos take longer since I actually "
    "download and watch them.\n"
    "• Send pasted text — I'll summarize it directly.\n"
    "• Send a photo or screenshot, voice note, audio, video, or a PDF/text "
    "file — I'll transcribe or read it first, then summarize. A caption is "
    "kept as context.\n"
    "• Short notes get a quick 1-3 sentence summary; longer content gets "
    "the full TL;DR / KEY POINTS / TAKEAWAY structure.\n"
    "• If something looks related to an earlier save, I'll offer to merge "
    "them into one summary — you can also trigger this yourself with "
    "/merge.\n\n"
    "*Commands*\n"
    "`/start` — show the welcome message\n"
    "`/help` — show this message\n"
    "`/list [n]` — show your last n saved items (default 10, max 50)\n"
    "`/search <keyword>` — search your saved items\n"
    "`/ask <question>` — ask a question; I answer from your saved notes and cite them\n"
    "`/view <id>` — show the full summary for a saved item\n"
    "`/merge <keep_id> <absorb_id>` — merge two saved items into one (asks for confirmation)\n"
    "`/delete <id>` — delete a saved item (asks for confirmation)\n"
    "`/undo <id>` — revert a merged item back to its pre-merge summary\n"
    "`/export` — download all your notes (readable Markdown + full JSON backup)\n"
    "`/setkey <api_key>` — set your own Gemini API key (required unless you're the bot's owner)\n"
)

_SEARCH_LIMIT = 10
_MAX_REPLY_CHARS = 3500  # safety margin under Telegram's 4096-char message limit
_VIEW_HINT = "\nUse /view <id> to read the full summary."
# Above this many items, a delete button per row would be an unreadable wall
# of buttons — large result sets fall back to typing /delete <id> instead.
_MAX_ITEMS_FOR_DELETE_BUTTONS = 20


def _delete_keyboard_for(items: list[dict]) -> InlineKeyboardMarkup | None:
    if not items or len(items) > _MAX_ITEMS_FOR_DELETE_BUTTONS:
        return None
    return build_list_delete_keyboard(items)


def _format_item_list(items: list[dict], header: str) -> str:
    lines = [header] + [format_item_line(item) for item in items]
    text = "\n".join(lines)
    budget = _MAX_REPLY_CHARS - len(_VIEW_HINT)
    if len(text) > budget:
        text = text[:budget].rsplit("\n", 1)[0]
        text += "\n… (truncated — try a narrower /search)"
    return text + _VIEW_HINT


def _parse_id_arg(args: list[str]) -> int | None:
    if not args:
        return None
    try:
        return int(args[0])
    except ValueError:
        return None


def _parse_two_id_args(args: list[str]) -> tuple[int, int] | None:
    if len(args) < 2:
        return None
    try:
        return int(args[0]), int(args[1])
    except ValueError:
        return None


def _quick_action_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📚 Browse my notes", callback_data="quick:list")],
            [InlineKeyboardButton("❓ Help", callback_data="quick:help")],
        ]
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id if update.effective_user else None
    if user_id is None or not config.is_authorized(user_id):
        await update.message.reply_text("Sorry, this bot is private.")
        return
    await update.message.reply_text(WELCOME_TEXT, reply_markup=_quick_action_keyboard())


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id if update.effective_user else None
    if user_id is None or not config.is_authorized(user_id):
        await update.message.reply_text("Sorry, this bot is private.")
        return
    await update.message.reply_text(HELP_TEXT, parse_mode="Markdown", reply_markup=_quick_action_keyboard())


async def handle_quick_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Buttons for commands that need no extra input (see PRD V2 2.4 discussion
    on making commands clickable) — /search, /view, /delete, /undo all need an
    id/keyword a button can't supply, so only /list and /help get one here."""
    query = update.callback_query
    user_id = update.effective_user.id if update.effective_user else None

    if query is None or query.data is None:
        return
    await query.answer()

    if user_id is None or not config.is_authorized(user_id):
        await query.message.reply_text("Sorry, this bot is private.")
        return

    _, action = query.data.split(":", 1)
    if action == "list":
        text, markup = await render_menu(user_id)
        await query.message.reply_text(text, reply_markup=markup)
    elif action == "help":
        await query.message.reply_text(HELP_TEXT, parse_mode="Markdown", reply_markup=_quick_action_keyboard())


async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/list opens the category menu; /list <category> jumps straight into one."""
    user_id = update.effective_user.id if update.effective_user else None
    if user_id is None or not config.is_authorized(user_id):
        await update.message.reply_text("Sorry, this bot is private.")
        return

    if context.args:
        wanted = " ".join(context.args).casefold()
        categories = [name for name, _count in await asyncio.to_thread(get_categories, user_id)]
        match = next((name for name in categories if name.casefold() == wanted), None)
        if match is not None:
            text, markup = await render_page(user_id, 0, CATEGORY, match)
            await update.message.reply_text(text, reply_markup=markup)
            return
        await update.message.reply_text(f"No category called \"{' '.join(context.args)}\" — here are yours:")

    text, markup = await render_menu(user_id)
    await update.message.reply_text(text, reply_markup=markup)


async def handle_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Category menu and Prev/Next taps — edits the same message in place."""
    query = update.callback_query
    user_id = update.effective_user.id if update.effective_user else None
    if query is None or query.data is None:
        return
    await query.answer()
    if user_id is None or not config.is_authorized(user_id):
        return

    if query.data == MENU_CALLBACK:
        text, markup = await render_menu(user_id)
    else:
        text, markup = await render_page(user_id, *decode_page(query.data))
    try:
        await query.edit_message_text(text, reply_markup=markup)
    except BadRequest as exc:
        if "not modified" not in str(exc).lower():
            raise


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id if update.effective_user else None
    if user_id is None or not config.is_authorized(user_id):
        await update.message.reply_text("Sorry, this bot is private.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /search <keyword>")
        return

    keyword = " ".join(context.args)
    items, total = search_items(user_id, keyword, limit=_SEARCH_LIMIT)
    if not items:
        await update.message.reply_text(f"No matches found for \"{keyword}\".")
        return

    header = f"Found {total} match(es) for \"{keyword}\""
    header += ":" if total <= len(items) else f" (showing first {len(items)}):"
    await update.message.reply_text(_format_item_list(items, header), reply_markup=_delete_keyboard_for(items))


async def ask_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id if update.effective_user else None
    if user_id is None or not config.is_authorized(user_id):
        await update.message.reply_text("Sorry, this bot is private.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /ask <question about your saved notes>")
        return

    api_key = await asyncio.to_thread(resolve_gemini_api_key, user_id)
    if api_key is None:
        await update.message.reply_text(NO_API_KEY_TEXT)
        return

    items = await asyncio.to_thread(get_all_items, user_id)
    if not items:
        await update.message.reply_text("You haven't saved anything yet.")
        return

    await update.effective_chat.send_action(ChatAction.TYPING)
    try:
        answer = await answer_question(" ".join(context.args), items, api_key)
    except GeminiError as exc:
        await update.message.reply_text(gemini_error_text(exc))
        return

    rendered = render_summary_html(answer)
    if len(rendered) > _MAX_REPLY_CHARS:
        rendered = render_summary_html(answer[:_MAX_REPLY_CHARS].rsplit("\n", 1)[0] + "\n…")
    await update.message.reply_text(rendered, parse_mode=ParseMode.HTML)


def _id_and_rest(args: list[str]) -> tuple[int, str] | None:
    """Parses '<id> <free text...>' command arguments."""
    if len(args) < 2:
        return None
    try:
        return int(args[0].lstrip("#")), " ".join(args[1:]).strip()
    except ValueError:
        return None


async def rename_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id if update.effective_user else None
    if user_id is None or not config.is_authorized(user_id):
        await update.message.reply_text("Sorry, this bot is private.")
        return

    parsed = _id_and_rest(context.args)
    title = clean_title(parsed[1]) if parsed else None
    if title is None:
        await update.message.reply_text("Usage: /rename <id> <new title>")
        return

    item_id = parsed[0]
    if not await asyncio.to_thread(update_fields, item_id, user_id, title=title):
        await update.message.reply_text(f"No saved item found with id #{item_id}.")
        return
    await update.message.reply_text(f"✏️ Renamed #{item_id} to: {title}")


async def move_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id if update.effective_user else None
    if user_id is None or not config.is_authorized(user_id):
        await update.message.reply_text("Sorry, this bot is private.")
        return

    parsed = _id_and_rest(context.args)
    existing = [name for name, _count in await asyncio.to_thread(get_categories, user_id)]
    category = clean_category(parsed[1], existing) if parsed else None
    if category is None:
        await update.message.reply_text("Usage: /move <id> <category>")
        return

    item_id = parsed[0]
    if not await asyncio.to_thread(update_fields, item_id, user_id, category=category):
        await update.message.reply_text(f"No saved item found with id #{item_id}.")
        return
    is_new = category not in existing
    await update.message.reply_text(
        f"📂 Moved #{item_id} to {category}" + (" (new category)." if is_new else ".")
    )


async def note_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id if update.effective_user else None
    if user_id is None or not config.is_authorized(user_id):
        await update.message.reply_text("Sorry, this bot is private.")
        return

    parsed = _id_and_rest(context.args)
    if parsed is None or not parsed[1]:
        await update.message.reply_text("Usage: /note <id> <your note>  (or /note <id> clear)")
        return

    item_id, note = parsed
    if note.casefold() == "clear":
        updated = await asyncio.to_thread(update_fields, item_id, user_id, user_note=None)
        reply = f"🧹 Cleared your note on #{item_id}."
    else:
        updated = await asyncio.to_thread(append_note, item_id, user_id, note)
        reply = f"📝 Added your note to #{item_id}."
    await update.message.reply_text(reply if updated else f"No saved item found with id #{item_id}.")


async def export_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id if update.effective_user else None
    if user_id is None or not config.is_authorized(user_id):
        await update.message.reply_text("Sorry, this bot is private.")
        return

    items = await asyncio.to_thread(get_all_items, user_id)
    if not items:
        await update.message.reply_text("You haven't saved anything yet.")
        return

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    await update.message.reply_document(
        document=build_markdown(items, today),
        filename=f"notes-{today}.md",
        caption=f"{len(items)} saved item(s), readable copy.",
    )
    await update.message.reply_document(
        document=build_json(items),
        filename=f"notes-backup-{today}.json",
        caption="Complete backup (every field) — keep this one safe.",
    )


async def view_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id if update.effective_user else None
    if user_id is None or not config.is_authorized(user_id):
        await update.message.reply_text("Sorry, this bot is private.")
        return

    item_id = _parse_id_arg(context.args)
    if item_id is None:
        await update.message.reply_text("Usage: /view <id>")
        return

    item = get_by_id(item_id, user_id)
    if item is None:
        await update.message.reply_text(f"No saved item found with id #{item_id}.")
        return

    await update.message.reply_text(
        format_full_item(item), parse_mode=ParseMode.HTML, reply_markup=build_item_actions_keyboard(item_id)
    )


async def merge_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id if update.effective_user else None
    if user_id is None or not config.is_authorized(user_id):
        await update.message.reply_text("Sorry, this bot is private.")
        return

    ids = _parse_two_id_args(context.args)
    if ids is None:
        await update.message.reply_text("Usage: /merge <keep_id> <absorb_id>")
        return

    keep_id, absorb_id = ids
    if keep_id == absorb_id:
        await update.message.reply_text("Can't merge an item with itself.")
        return

    keep_item = get_by_id(keep_id, user_id)
    absorb_item = get_by_id(absorb_id, user_id)
    if keep_item is None or absorb_item is None:
        missing_id = keep_id if keep_item is None else absorb_id
        await update.message.reply_text(f"No saved item found with id #{missing_id}.")
        return

    # Reuses the exact same confirm/decline/view-first flow as an automatic
    # Combine Mode suggestion (handle_merge_callback in app/bot/handlers.py)
    # — a manually requested merge and an auto-suggested one work identically
    # once the two ids are known.
    keep_title = keep_item["title"] or "Untitled"
    absorb_title = absorb_item["title"] or "Untitled"
    await update.message.reply_text(
        f"Merge #{absorb_id} — {absorb_title} into #{keep_id} — {keep_title}? "
        f"#{keep_id} will keep its id and absorb #{absorb_id}'s content into one summary.",
        reply_markup=build_merge_keyboard(keep_id, absorb_id),
    )


async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id if update.effective_user else None
    if user_id is None or not config.is_authorized(user_id):
        await update.message.reply_text("Sorry, this bot is private.")
        return

    item_id = _parse_id_arg(context.args)
    if item_id is None:
        await update.message.reply_text("Usage: /delete <id>")
        return

    item = get_by_id(item_id, user_id)
    if item is None:
        await update.message.reply_text(f"No saved item found with id #{item_id}.")
        return

    title = item["title"] or "Untitled"
    await update.message.reply_text(
        f"Delete #{item_id} — {title}? This can't be undone.",
        reply_markup=build_delete_keyboard(item_id),
    )


async def handle_delete_request_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Triggered by a per-item 🗑 button on /list or /search results —
    equivalent to typing /delete <id> directly, just one tap instead of
    retyping the id. Sends the same confirmation prompt as /delete."""
    query = update.callback_query
    user_id = update.effective_user.id if update.effective_user else None

    if query is None or query.data is None:
        return
    await query.answer()

    if user_id is None or not config.is_authorized(user_id):
        await query.message.reply_text("Sorry, this bot is private.")
        return

    _, id_str = query.data.split(":")
    item_id = int(id_str)

    item = get_by_id(item_id, user_id)
    if item is None:
        await query.message.reply_text(f"Couldn't find #{item_id} anymore.")
        return

    title = item["title"] or "Untitled"
    await query.message.reply_text(
        f"Delete #{item_id} — {title}? This can't be undone.",
        reply_markup=build_delete_keyboard(item_id),
    )


async def undo_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id if update.effective_user else None
    if user_id is None or not config.is_authorized(user_id):
        await update.message.reply_text("Sorry, this bot is private.")
        return

    item_id = _parse_id_arg(context.args)
    if item_id is None:
        await update.message.reply_text("Usage: /undo <id>")
        return

    item = get_by_id(item_id, user_id)
    if item is None:
        await update.message.reply_text(f"No saved item found with id #{item_id}.")
        return

    if item.get("previous_summary") is None:
        await update.message.reply_text(f"#{item_id} has no merge to undo.")
        return

    undo_merge(item_id, item["previous_summary"], user_id)
    await update.message.reply_text(f"Reverted #{item_id} to its pre-merge summary.")


def _validate_gemini_key(api_key: str) -> bool:
    """A tiny live call against the key itself — so a typo or expired key
    fails immediately with a clear message, not on the user's next summary.
    Quota or overload errors mean Gemini accepted the key, so they count as valid."""
    try:
        generate_text(api_key, "Say OK.")
    except GeminiError as exc:
        return exc.kind in (QUOTA_DAILY, QUOTA_RATE, UNAVAILABLE)
    return True


async def setkey_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id if update.effective_user else None
    if user_id is None or not config.is_authorized(user_id):
        await update.message.reply_text("Sorry, this bot is private.")
        return

    if not context.args:
        await update.message.reply_text(
            "Usage: /setkey <your-gemini-api-key>\n"
            "Get a free one at https://aistudio.google.com/apikey"
        )
        return

    api_key = context.args[0].strip()

    # Best-effort: remove the message containing the raw key from chat
    # history so it doesn't linger visibly. Send replies via effective_chat
    # from here on rather than message.reply_text, since the original
    # message this would reply to may no longer exist.
    try:
        await update.message.delete()
    except Exception:
        pass

    is_valid = await asyncio.to_thread(_validate_gemini_key, api_key)
    if not is_valid:
        await update.effective_chat.send_message(
            "That doesn't look like a working Gemini API key — double-check it and try again."
        )
        return

    set_user_api_key(user_id, api_key)
    await update.effective_chat.send_message(
        "✅ Your Gemini API key is set. Your summaries now run on your own key."
    )

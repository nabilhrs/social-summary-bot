"""
Slash-command handlers (PRD 5.6, PRD V2 2.2).

/summarize is intentionally not implemented — auto-detection in
app/bot/handlers.py covers both URL and pasted text without a command.
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.config import config
from app.database.database import list_items, search_items, get_by_id, undo_merge
from app.bot.formatting import format_full_item, build_merge_keyboard, build_delete_keyboard, build_list_delete_keyboard

WELCOME_TEXT = (
    "👋 Hey! I'm your personal content summarizer.\n\n"
    "Send me a URL — articles, Threads posts, or TikTok videos (I watch the "
    "video itself, not just the caption) — or paste text directly, and I'll "
    "send back a summary and save it for later. If something looks related "
    "to an earlier save, I'll offer to merge them into one.\n\n"
    "Type /help to see everything I can do."
)

HELP_TEXT = (
    "*What I can do*\n\n"
    "• Send a URL — articles, Threads posts, or TikTok videos — and I'll "
    "extract and summarize it. TikTok videos take longer since I actually "
    "download and watch them.\n"
    "• Send pasted text — I'll summarize it directly.\n"
    "• Short notes get a quick 1-3 sentence summary; longer content gets "
    "the full TL;DR / KEY POINTS / TAKEAWAY structure.\n"
    "• If something looks related to an earlier save, I'll offer to merge "
    "them into one summary — you can also trigger this yourself with "
    "/merge.\n\n"
    "*Commands*\n"
    "/start — show the welcome message\n"
    "/help — show this message\n"
    "/list [n] — show your last n saved items (default 10, max 50)\n"
    "/search <keyword> — search your saved items\n"
    "/view <id> — show the full summary for a saved item\n"
    "/merge <keep_id> <absorb_id> — merge two saved items into one (asks for confirmation)\n"
    "/delete <id> — delete a saved item (asks for confirmation)\n"
    "/undo <id> — revert a merged item back to its pre-merge summary\n"
)

_DEFAULT_LIST_LIMIT = 10
_MAX_LIST_LIMIT = 50
_MAX_REPLY_CHARS = 3500  # safety margin under Telegram's 4096-char message limit
_VIEW_HINT = "\nUse /view <id> to read the full summary."
# Above this many items, a delete button per row would be an unreadable wall
# of buttons — large /list counts fall back to typing /delete <id> instead.
_MAX_ITEMS_FOR_DELETE_BUTTONS = 20


def _delete_keyboard_for(items: list[dict]) -> InlineKeyboardMarkup | None:
    if not items or len(items) > _MAX_ITEMS_FOR_DELETE_BUTTONS:
        return None
    return build_list_delete_keyboard(items)


def _display_title(item: dict) -> str:
    if item.get("title"):
        return item["title"]
    preview = item["original_text"].strip().splitlines()[0].strip()
    return (preview[:60] + "…") if len(preview) > 60 else preview


def _format_item_line(item: dict) -> str:
    date = item["created_at"][:10]
    return f"#{item['id']} — {_display_title(item)} ({date})"


def _format_item_list(items: list[dict], header: str) -> str:
    lines = [header] + [_format_item_line(item) for item in items]
    text = "\n".join(lines)
    budget = _MAX_REPLY_CHARS - len(_VIEW_HINT)
    if len(text) > budget:
        text = text[:budget].rsplit("\n", 1)[0]
        text += "\n… (truncated — try a smaller /list count or a narrower /search)"
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
            [InlineKeyboardButton("📋 Show recent items", callback_data="quick:list")],
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
        items = list_items(_DEFAULT_LIST_LIMIT)
        if not items:
            await query.message.reply_text("You haven't saved anything yet.")
            return
        await query.message.reply_text(
            _format_item_list(items, f"Last {len(items)} saved item(s):"),
            reply_markup=_delete_keyboard_for(items),
        )
    elif action == "help":
        await query.message.reply_text(HELP_TEXT, parse_mode="Markdown", reply_markup=_quick_action_keyboard())


async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id if update.effective_user else None
    if user_id is None or not config.is_authorized(user_id):
        await update.message.reply_text("Sorry, this bot is private.")
        return

    limit = _DEFAULT_LIST_LIMIT
    if context.args:
        try:
            limit = int(context.args[0])
        except ValueError:
            pass
    limit = max(1, min(limit, _MAX_LIST_LIMIT))

    items = list_items(limit)
    if not items:
        await update.message.reply_text("You haven't saved anything yet.")
        return

    await update.message.reply_text(
        _format_item_list(items, f"Last {len(items)} saved item(s):"),
        reply_markup=_delete_keyboard_for(items),
    )


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id if update.effective_user else None
    if user_id is None or not config.is_authorized(user_id):
        await update.message.reply_text("Sorry, this bot is private.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /search <keyword>")
        return

    keyword = " ".join(context.args)
    items, total = search_items(keyword, limit=_DEFAULT_LIST_LIMIT)
    if not items:
        await update.message.reply_text(f"No matches found for \"{keyword}\".")
        return

    header = f"Found {total} match(es) for \"{keyword}\""
    header += ":" if total <= len(items) else f" (showing first {len(items)}):"
    await update.message.reply_text(_format_item_list(items, header), reply_markup=_delete_keyboard_for(items))


async def view_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id if update.effective_user else None
    if user_id is None or not config.is_authorized(user_id):
        await update.message.reply_text("Sorry, this bot is private.")
        return

    item_id = _parse_id_arg(context.args)
    if item_id is None:
        await update.message.reply_text("Usage: /view <id>")
        return

    item = get_by_id(item_id)
    if item is None:
        await update.message.reply_text(f"No saved item found with id #{item_id}.")
        return

    await update.message.reply_text(format_full_item(item))


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

    keep_item = get_by_id(keep_id)
    absorb_item = get_by_id(absorb_id)
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

    item = get_by_id(item_id)
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

    item = get_by_id(item_id)
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

    item = get_by_id(item_id)
    if item is None:
        await update.message.reply_text(f"No saved item found with id #{item_id}.")
        return

    if item.get("previous_summary") is None:
        await update.message.reply_text(f"#{item_id} has no merge to undo.")
        return

    undo_merge(item_id, item["previous_summary"])
    await update.message.reply_text(f"Reverted #{item_id} to its pre-merge summary.")

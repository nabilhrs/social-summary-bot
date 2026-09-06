"""
Slash-command handlers (PRD 5.6, PRD V2 2.2).

/summarize is intentionally not implemented — auto-detection in
app/bot/handlers.py covers both URL and pasted text without a command.
"""
from telegram import Update
from telegram.ext import ContextTypes

from app.config import config
from app.database.database import list_items, search_items

WELCOME_TEXT = (
    "👋 Hey! I'm your personal content summarizer.\n\n"
    "Send me a web article URL or paste some text, and I'll send back a "
    "structured summary and save it for later.\n\n"
    "Type /help to see what I can do."
)

HELP_TEXT = (
    "*What I can do*\n\n"
    "• Send me a URL — I'll fetch the article and summarize it.\n"
    "• Send me pasted text — I'll summarize it directly.\n\n"
    "*Commands*\n"
    "/start — show the welcome message\n"
    "/help — show this message\n"
    "/list [n] — show your last n saved items (default 10, max 50)\n"
    "/search <keyword> — search your saved items\n"
)

_DEFAULT_LIST_LIMIT = 10
_MAX_LIST_LIMIT = 50
_MAX_REPLY_CHARS = 3500  # safety margin under Telegram's 4096-char message limit


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
    if len(text) > _MAX_REPLY_CHARS:
        text = text[:_MAX_REPLY_CHARS].rsplit("\n", 1)[0]
        text += "\n… (truncated — try a smaller /list count or a narrower /search)"
    return text


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id if update.effective_user else None
    if user_id is None or not config.is_authorized(user_id):
        await update.message.reply_text("Sorry, this bot is private.")
        return
    await update.message.reply_text(WELCOME_TEXT)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id if update.effective_user else None
    if user_id is None or not config.is_authorized(user_id):
        await update.message.reply_text("Sorry, this bot is private.")
        return
    await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")


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

    await update.message.reply_text(_format_item_list(items, f"Last {len(items)} saved item(s):"))


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
    await update.message.reply_text(_format_item_list(items, header))

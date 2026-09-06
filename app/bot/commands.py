"""
Slash-command handlers (PRD 5.6).

/summarize is intentionally not implemented yet — it lands in a later build
step once the summarizer + extractor pipeline exists (see build order,
PRD section 8). For now the bot only understands /start and /help; any other
plain message is routed through app/bot/handlers.py.
"""
from telegram import Update
from telegram.ext import ContextTypes

from app.config import config

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
)


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

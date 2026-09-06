"""
Entry point. Wires up the Telegram Application and starts polling.

Run with: python main.py
Requires TELEGRAM_BOT_TOKEN and AUTHORIZED_USER_IDS in .env (see .env.example).
"""
import logging

from telegram import BotCommand
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from app.config import config
from app.bot.commands import (
    start,
    help_command,
    list_command,
    search_command,
    view_command,
    merge_command,
    delete_command,
    undo_command,
    setkey_command,
    handle_quick_action_callback,
    handle_delete_request_callback,
)
from app.bot.handlers import handle_message, handle_merge_callback, handle_delete_callback
from app.database.database import init_db

# Registered with Telegram via set_my_commands so clients show a tappable "/"
# command menu (tapping one inserts and sends it) instead of requiring the
# user to remember and type commands from scratch.
_BOT_COMMANDS = [
    BotCommand("start", "Show the welcome message"),
    BotCommand("help", "Show what I can do"),
    BotCommand("list", "Show your last saved items"),
    BotCommand("search", "Search your saved items"),
    BotCommand("view", "Show the full summary for a saved item"),
    BotCommand("merge", "Merge two saved items into one"),
    BotCommand("delete", "Delete a saved item"),
    BotCommand("undo", "Revert a merged item to its pre-merge summary"),
    BotCommand("setkey", "Set your own Gemini API key"),
]

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
# Quiet down the very chatty HTTP client logger.
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


async def log_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Unhandled exception while processing update: %s", update, exc_info=context.error)


async def _post_init(app: Application) -> None:
    await app.bot.set_my_commands(_BOT_COMMANDS)


def build_app() -> Application:
    app = Application.builder().token(config.telegram_bot_token).post_init(_post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("list", list_command))
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CommandHandler("view", view_command))
    app.add_handler(CommandHandler("merge", merge_command))
    app.add_handler(CommandHandler("delete", delete_command))
    app.add_handler(CommandHandler("undo", undo_command))
    app.add_handler(CommandHandler("setkey", setkey_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_merge_callback, pattern=r"^merge:(yes|no|view):\d+:\d+$"))
    app.add_handler(CallbackQueryHandler(handle_delete_callback, pattern=r"^delete:(yes|no):\d+$"))
    app.add_handler(CallbackQueryHandler(handle_delete_request_callback, pattern=r"^delconfirm:\d+$"))
    app.add_handler(CallbackQueryHandler(handle_quick_action_callback, pattern=r"^quick:(list|help)$"))
    app.add_error_handler(log_error)

    return app


def main() -> None:
    init_db()
    app = build_app()
    logger.info("Bot starting — polling for updates...")
    app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()

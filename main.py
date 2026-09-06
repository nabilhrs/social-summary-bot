"""
Entry point. Wires up the Telegram Application and starts polling.

Run with: python main.py
Requires TELEGRAM_BOT_TOKEN and AUTHORIZED_USER_ID in .env (see .env.example).
"""
import logging

from telegram.ext import Application, CommandHandler, MessageHandler, filters

from app.config import config
from app.bot.commands import start, help_command
from app.bot.handlers import handle_message
from app.database.database import init_db

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
# Quiet down the very chatty HTTP client logger.
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def build_app() -> Application:
    app = Application.builder().token(config.telegram_bot_token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    return app


def main() -> None:
    init_db()
    app = build_app()
    logger.info("Bot starting — polling for updates...")
    app.run_polling(allowed_updates=["message"])


if __name__ == "__main__":
    main()

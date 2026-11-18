"""
Entry point. Wires up the Telegram Application and starts polling.

Run with: python main.py
Requires TELEGRAM_BOT_TOKEN and AUTHORIZED_USER_IDS in .env (see .env.example).
"""
import asyncio
import logging
import os

from telegram import BotCommand, Update
from telegram.error import NetworkError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from app.bot.actions import (
    handle_action_callback,
    keyboard_for_item,
    handle_setcat_callback,
    handle_star_callback,
)
from app.bot.reminders import (
    handle_cancel_callback,
    handle_remind_callback,
    handle_undo_callback,
    remind_command,
    reminder_loop,
    reminders_command,
)
from app.bot import alerts
from app.bot.background import backfill_loop
from app.bot.categories import categories_command, handle_category_callback
from app.bot.digest import digest_loop
from app.bot.retry import retry_loop
from app.bot.review import handle_review_callback, handle_unarchive_callback, review_command
from app.bot.todos import handle_todo_callback, todo_command
from app.config import config
from app.bot.commands import (
    start,
    help_command,
    list_command,
    search_command,
    ask_command,
    view_command,
    merge_command,
    delete_command,
    undo_command,
    export_command,
    rename_command,
    move_command,
    note_command,
    digest_command,
    starred_command,
    usage_command,
    setkey_command,
    handle_quick_action_callback,
    handle_list_callback,
    handle_delete_request_callback,
)
from app.bot.handlers import (
    handle_delete_callback,
    handle_duplicate_callback,
    handle_media,
    handle_merge_callback,
    handle_message,
    handle_unsupported,
    run_job,
)
from app.database.database import init_db

# Registered with Telegram via set_my_commands so clients show a tappable "/"
# command menu (tapping one inserts and sends it) instead of requiring the
# user to remember and type commands from scratch.
_BOT_COMMANDS = [
    BotCommand("start", "Show the welcome message"),
    BotCommand("help", "Show what I can do"),
    BotCommand("list", "Browse your notes by category"),
    BotCommand("starred", "Show your starred notes"),
    BotCommand("categories", "Rename or merge your categories"),
    BotCommand("search", "Search your saved items"),
    BotCommand("ask", "Ask a question about your saved notes"),
    BotCommand("view", "Show the full summary for a saved item"),
    BotCommand("merge", "Merge two saved items into one"),
    BotCommand("delete", "Delete a saved item"),
    BotCommand("undo", "Revert a merged item to its pre-merge summary"),
    BotCommand("export", "Download all your notes as files"),
    BotCommand("usage", "Today's Gemini usage"),
    BotCommand("rename", "Rename a saved item"),
    BotCommand("move", "Move a saved item to another category"),
    BotCommand("note", "Add your own note to a saved item"),
    BotCommand("digest", "Show your weekly digest now"),
    BotCommand("remind", "Set a reminder, e.g. tomorrow 7am dentist"),
    BotCommand("reminders", "See or cancel your reminders"),
    BotCommand("todo", "Your to-do list, or add one: /todo buy milk"),
    BotCommand("review", "Revisit an older note: keep it or archive it"),
    BotCommand("setkey", "Set your own Gemini API key"),
]

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
# Quiet down the very chatty HTTP client logger.
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def describe_update(update: object) -> str:
    """Short and readable for the owner alert; the full update goes to the debug log."""
    if isinstance(update, Update):
        if update.callback_query is not None:
            return f"a button tap ({update.callback_query.data})"
        message = update.effective_message
        if message is not None:
            text = message.text or message.caption or ""
            if text.startswith("/"):
                return f"the command {text.split()[0]}"
            return "a message" if text else "a file or photo"
    return "a background task" if update is None else "an update"


async def log_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update is None and isinstance(context.error, NetworkError):
        # A dropped connection while waiting for new messages (getUpdates).
        # The library reconnects by itself, so this is logged without
        # exception info and doesn't alert the owner (docs/memory.md #12).
        logger.warning("Telegram connection blip while polling, reconnecting: %r", context.error)
        return
    logger.debug("Update that failed: %s", update)
    logger.error("Unhandled exception while handling %s", describe_update(update), exc_info=context.error)


async def _post_init(app: Application) -> None:
    await app.bot.set_my_commands(_BOT_COMMANDS)
    alerts.configure(app.bot, config.authorized_user_ids[0], asyncio.get_running_loop())
    alert_handler = alerts.AlertHandler()
    logging.getLogger().addHandler(alert_handler)
    app.bot_data["alert_handler"] = alert_handler
    # Plain asyncio tasks, cancelled in _post_stop: Application.create_task
    # warns when called before the app is running and leaves them pending at exit.
    app.bot_data["background_tasks"] = [
        asyncio.create_task(backfill_loop(), name="backfill"),
        asyncio.create_task(digest_loop(app.bot), name="digest"),
        asyncio.create_task(retry_loop(lambda job: run_job(app.bot, job)), name="retry"),
        asyncio.create_task(reminder_loop(app.bot, _note_keyboard), name="reminders"),
    ]


def _note_keyboard(item: dict):
    return keyboard_for_item(item)


async def _post_stop(app: Application) -> None:
    tasks = app.bot_data.get("background_tasks", [])
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    if "alert_handler" in app.bot_data:
        logging.getLogger().removeHandler(app.bot_data.pop("alert_handler"))


def build_app() -> Application:
    app = (
        Application.builder()
        .token(config.telegram_bot_token)
        .post_init(_post_init)
        .post_stop(_post_stop)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("list", list_command))
    app.add_handler(CommandHandler("starred", starred_command))
    app.add_handler(CommandHandler("categories", categories_command))
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CommandHandler("ask", ask_command))
    app.add_handler(CommandHandler("view", view_command))
    app.add_handler(CommandHandler("merge", merge_command))
    app.add_handler(CommandHandler("delete", delete_command))
    app.add_handler(CommandHandler("undo", undo_command))
    app.add_handler(CommandHandler("export", export_command))
    app.add_handler(CommandHandler("rename", rename_command))
    app.add_handler(CommandHandler("move", move_command))
    app.add_handler(CommandHandler("note", note_command))
    app.add_handler(CommandHandler("digest", digest_command))
    app.add_handler(CommandHandler("reminders", reminders_command))
    app.add_handler(CommandHandler("remind", remind_command))
    app.add_handler(CommandHandler("todo", todo_command))
    app.add_handler(CommandHandler("review", review_command))
    app.add_handler(CommandHandler("usage", usage_command))
    app.add_handler(CommandHandler("setkey", setkey_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(
        MessageHandler(
            filters.PHOTO
            | filters.VOICE
            | filters.AUDIO
            | filters.VIDEO
            | filters.VIDEO_NOTE
            | filters.Document.ALL,
            handle_media,
        )
    )
    # Anything else (stickers, locations, polls...) gets a clear reply instead of silence.
    app.add_handler(MessageHandler(~filters.COMMAND, handle_unsupported))
    app.add_handler(CallbackQueryHandler(handle_merge_callback, pattern=r"^merge:(yes|no|view):\d+:\d+$"))
    app.add_handler(CallbackQueryHandler(handle_delete_callback, pattern=r"^delete:(yes|no):\d+$"))
    app.add_handler(CallbackQueryHandler(handle_delete_request_callback, pattern=r"^delconfirm:\d+$"))
    app.add_handler(CallbackQueryHandler(handle_quick_action_callback, pattern=r"^quick:(list|help)$"))
    app.add_handler(CallbackQueryHandler(handle_list_callback, pattern=r"^(lm|lp:\d+:[auscx].*)$"))
    app.add_handler(CallbackQueryHandler(handle_star_callback, pattern=r"^star:\d+$"))
    app.add_handler(
        CallbackQueryHandler(handle_category_callback, pattern=r"^(catmenu|catpick:.+|catopt:(rename|merge|list)|catto:.+)$")
    )
    app.add_handler(CallbackQueryHandler(handle_duplicate_callback, pattern=r"^dup:(view|again):\d+$"))
    app.add_handler(
        CallbackQueryHandler(handle_action_callback, pattern=r"^act:(rename|cat|newcat|note|transcript|remind|remindat):\d+$")
    )
    app.add_handler(CallbackQueryHandler(handle_undo_callback, pattern=r"^remundo:\d+$"))
    app.add_handler(CallbackQueryHandler(handle_remind_callback, pattern=r"^remind:\d+:(tn|tm|wk|nw|mo)$"))
    app.add_handler(CallbackQueryHandler(handle_cancel_callback, pattern=r"^remcancel:\d+$"))
    app.add_handler(CallbackQueryHandler(handle_setcat_callback, pattern=r"^setcat:\d+:.+$"))
    app.add_handler(CallbackQueryHandler(handle_todo_callback, pattern=r"^todo:(done|undo):\d+$"))
    app.add_handler(CallbackQueryHandler(handle_review_callback, pattern=r"^rev:(show|skip|keep|arch|undo|next):\d+$"))
    app.add_handler(CallbackQueryHandler(handle_unarchive_callback, pattern=r"^unarch:\d+$"))
    app.add_error_handler(log_error)

    return app


def main() -> None:
    init_db()
    app = build_app()
    logger.info("Database: %s", os.path.abspath(config.db_path))
    logger.info("Bot starting — polling for updates...")
    app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()

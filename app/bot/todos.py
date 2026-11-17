"""
/todo: a checklist of things to do, gathered from notes as they're saved
(the summary request also lists action items, so this costs no extra
Gemini quota) or added by hand with /todo <text>.

Buttons: todo:done:<id> ticks one off, todo:undo:<id> brings it back.
"""
import asyncio

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from app.ai.summarizer import parse_todos
from app.config import config
from app.database.database import add_todos, get_todo, list_open_todos, set_todo_done

# Telegram allows up to 100 buttons; past this many the list stops being useful.
MAX_SHOWN = 20
_BUTTON_CHARS = 40
EMPTY_TEXT = (
    "☑️ Nothing on your to-do list.\n\n"
    "When a note suggests something to do (a place to try, a thing to buy), "
    "I add it here. You can also add one yourself: /todo buy batteries"
)


def _short(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def build_todo_list(todos: list[dict], notice: str | None = None, undo_id: int | None = None):
    """(text, keyboard) for the open to-dos, oldest first."""
    rows = []
    if undo_id is not None:
        rows.append([InlineKeyboardButton("↩️ Undo", callback_data=f"todo:undo:{undo_id}")])
    if not todos:
        text = EMPTY_TEXT if notice is None else f"{notice}\n\n☑️ That's everything on your list."
        return text, InlineKeyboardMarkup(rows) if rows else None

    shown = todos[:MAX_SHOWN]
    lines = [f"☑️ To-do ({len(todos)})", ""]
    if notice:
        lines = [notice, ""] + lines
    for number, todo in enumerate(shown, start=1):
        source = f" — from #{todo['item_id']}" if todo["item_id"] else ""
        lines.append(f"{number}. {todo['text']}{source}")
    if len(todos) > len(shown):
        lines.append(f"…and {len(todos) - len(shown)} more. Tick some off to see them.")
    lines += ["", "Tap one when it's done."]
    rows += [
        [InlineKeyboardButton(f"✅ {number}. {_short(todo['text'], _BUTTON_CHARS)}", callback_data=f"todo:done:{todo['id']}")]
        for number, todo in enumerate(shown, start=1)
    ]
    return "\n".join(lines), InlineKeyboardMarkup(rows)


async def todo_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id if update.effective_user else None
    if user_id is None or not config.is_authorized(user_id):
        await update.message.reply_text("Sorry, this bot is private.")
        return

    notice = None
    typed = " ".join(context.args or []).strip()
    if typed:
        # Same cleanup as Gemini's to-dos; " | " adds up to 3 at once.
        texts = parse_todos(typed)
        if not texts:
            await update.message.reply_text("That to-do is empty — nothing added.")
            return
        await asyncio.to_thread(add_todos, user_id, None, texts)
        notice = "➕ Added: " + "; ".join(texts)

    todos = await asyncio.to_thread(list_open_todos, user_id)
    text, markup = build_todo_list(todos, notice)
    await update.message.reply_text(text, reply_markup=markup)


async def handle_todo_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = update.effective_user.id if update.effective_user else None
    if query is None or query.data is None:
        return
    if user_id is None or not config.is_authorized(user_id):
        await query.answer()
        return

    _, action, id_str = query.data.split(":")
    todo_id = int(id_str)
    todo = await asyncio.to_thread(get_todo, todo_id, user_id)
    if todo is None:
        await query.answer("That to-do is gone.")
    else:
        await asyncio.to_thread(set_todo_done, todo_id, user_id, action == "done")
        await query.answer("✅ Done" if action == "done" else "↩️ Back on the list")

    todos = await asyncio.to_thread(list_open_todos, user_id)
    if todo is not None and action == "done":
        text, markup = build_todo_list(todos, f"✅ Done: {todo['text']}", undo_id=todo_id)
    else:
        text, markup = build_todo_list(todos)
    try:
        await query.edit_message_text(text, reply_markup=markup)
    except BadRequest as exc:
        # A double tap re-renders the same list, which Telegram rejects.
        if "not modified" not in str(exc).lower():
            raise

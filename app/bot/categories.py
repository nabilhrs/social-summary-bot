"""
/categories: rename or merge categories.

Category names travel in button data, which Telegram caps at 64 bytes, so
a merge (two names) can't fit in one button. Buttons carry at most one
name; the other is read back from the text of the message the button is
attached to. Nothing is kept in memory (see docs/memory.md #5).
"""
import asyncio
import re

from telegram import ForceReply, InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from app.ai.summarizer import clean_category
from app.bot.browse import CATEGORY, render_page
from app.config import config
from app.database.database import get_categories, rename_category

MENU_TEXT = "📂 Your categories. Tap one to rename it or merge it into another:"
_OPTIONS_RE = re.compile(r"^📂 (.+) — \d+ note")
_MERGE_RE = re.compile(r"^🔀 Merge (.+) into which category\?")
RENAME_PROMPT = "✏️ Reply with a new name for the category {name}"
_RENAME_PROMPT_RE = re.compile(r"^✏️ Reply with a new name for the category (.+)$", re.MULTILINE)


def build_menu(categories: list[tuple[str, int]]):
    buttons = [InlineKeyboardButton(f"{name} ({count})", callback_data=f"catpick:{name}") for name, count in categories]
    return MENU_TEXT, InlineKeyboardMarkup([buttons[i : i + 2] for i in range(0, len(buttons), 2)])


def build_options(name: str, count: int):
    text = f"📂 {name} — {count} note(s)\nWhat would you like to do?"
    return text, InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✏️ Rename", callback_data="catopt:rename"),
                InlineKeyboardButton("🔀 Merge into…", callback_data="catopt:merge"),
            ],
            [
                InlineKeyboardButton("📋 Show notes", callback_data="catopt:list"),
                InlineKeyboardButton("◀ Back", callback_data="catmenu"),
            ],
        ]
    )


def build_merge_picker(name: str, count: int, categories: list[tuple[str, int]]):
    text = f"🔀 Merge {name} into which category?\nIts {count} note(s) will move there."
    others = [InlineKeyboardButton(other, callback_data=f"catto:{other}") for other, _ in categories if other != name]
    rows = [others[i : i + 2] for i in range(0, len(others), 2)]
    rows.append([InlineKeyboardButton("◀ Back", callback_data=f"catpick:{name}")])
    return text, InlineKeyboardMarkup(rows)


def category_in(text: str | None, pattern: re.Pattern) -> str | None:
    match = pattern.match(text or "")
    return match.group(1) if match else None


def describe_move(old: str, new: str, moved: int, existing: list[str]) -> str:
    if new in existing:
        return f"🔀 Moved {moved} note(s) from {old} into {new}."
    return f"✏️ Renamed {old} to {new} ({moved} note(s))."


async def _categories(user_id: int) -> list[tuple[str, int]]:
    return await asyncio.to_thread(get_categories, user_id)


async def categories_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id if update.effective_user else None
    if user_id is None or not config.is_authorized(user_id):
        await update.message.reply_text("Sorry, this bot is private.")
        return
    categories = await _categories(user_id)
    if not categories:
        await update.message.reply_text("You don't have any categories yet. Save something first.")
        return
    text, markup = build_menu(categories)
    await update.message.reply_text(text, reply_markup=markup)


async def _edit(query, text: str, markup=None) -> None:
    try:
        await query.edit_message_text(text, reply_markup=markup)
    except BadRequest as exc:
        if "not modified" not in str(exc).lower():
            raise


async def handle_category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = update.effective_user.id if update.effective_user else None
    if query is None or query.data is None:
        return
    await query.answer()
    if user_id is None or not config.is_authorized(user_id):
        return

    data = query.data
    categories = await _categories(user_id)
    names = [name for name, _ in categories]
    counts = dict(categories)

    if data == "catmenu":
        await _edit(query, *build_menu(categories))
        return
    if data.startswith("catpick:"):
        name = data.split(":", 1)[1]
        if name not in counts:
            await _edit(query, f"There's no category called {name} anymore.", build_menu(categories)[1])
            return
        await _edit(query, *build_options(name, counts[name]))
        return
    if data.startswith("catto:"):
        source = category_in(query.message.text, _MERGE_RE)
        target = data.split(":", 1)[1]
        if source not in counts or target not in counts:
            await _edit(query, "One of those categories doesn't exist anymore.", build_menu(categories)[1])
            return
        moved = await asyncio.to_thread(rename_category, user_id, source, target)
        await _edit(query, describe_move(source, target, moved, names))
        return

    name = category_in(query.message.text, _OPTIONS_RE)
    if name not in counts:
        await _edit(query, "That category doesn't exist anymore.", build_menu(categories)[1])
        return
    action = data.split(":", 1)[1]
    if action == "rename":
        await query.message.reply_text(
            RENAME_PROMPT.format(name=name), reply_markup=ForceReply(input_field_placeholder="New category name")
        )
    elif action == "merge":
        if len(categories) < 2:
            await query.message.reply_text("There's no other category to merge it into.")
            return
        await _edit(query, *build_merge_picker(name, counts[name], categories))
    elif action == "list":
        text, markup = await render_page(user_id, 0, CATEGORY, name)
        await query.message.reply_text(text, reply_markup=markup)


async def apply_category_rename(message: Message, user_id: int) -> bool:
    """If `message` answers a category rename prompt, apply it and return True."""
    replied = message.reply_to_message
    if replied is None or replied.from_user is None or not replied.from_user.is_bot:
        return False
    old = category_in(replied.text, _RENAME_PROMPT_RE)
    if old is None:
        return False

    names = [name for name, _ in await _categories(user_id)]
    if old not in names:
        await message.reply_text(f"There's no category called {old} anymore.")
        return True
    new = clean_category(message.text, [n for n in names if n != old])
    if new is None:
        await message.reply_text("That name is empty — nothing changed.")
        return True
    if new == old:
        await message.reply_text("That's the same name — nothing changed.")
        return True
    moved = await asyncio.to_thread(rename_category, user_id, old, new)
    await message.reply_text(describe_move(old, new, moved, names))
    return True

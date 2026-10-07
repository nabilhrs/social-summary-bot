"""
/list browsing: a category menu, then pages of items with Prev/Next buttons.

Button data is stateless (memory.md #5): lm = back to the menu,
lp:<page>:<scope> = a page, where scope is "a" (all), "u" (uncategorized),
or "c<category name>".
"""
import asyncio

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.database.database import count_items, get_categories, list_page

PAGE_SIZE = 10
MENU_CALLBACK = "lm"
ALL, UNCATEGORIZED, CATEGORY = "a", "u", "c"


def encode_page(page: int, scope: str, category: str | None = None) -> str:
    return f"lp:{page}:{scope}{category or ''}"


def decode_page(data: str) -> tuple[int, str, str | None]:
    _, page, rest = data.split(":", 2)
    scope, category = rest[0], rest[1:] or None
    return int(page), scope, category


def display_title(item: dict) -> str:
    if item.get("title"):
        return item["title"]
    preview = item["original_text"].strip().splitlines()[0].strip()
    return (preview[:60] + "…") if len(preview) > 60 else preview


def format_item_line(item: dict) -> str:
    return f"#{item['id']} — {display_title(item)} ({item['created_at'][:10]})"


def build_menu(total: int, categories: list[tuple[str, int]], uncategorized: int):
    text = f"📚 Your saved notes ({total}). Pick a category:"
    buttons = [InlineKeyboardButton(f"🕒 All, newest first ({total})", callback_data=encode_page(0, ALL))]
    category_buttons = [
        InlineKeyboardButton(f"📂 {name} ({count})", callback_data=encode_page(0, CATEGORY, name))
        for name, count in categories
    ]
    if uncategorized:
        category_buttons.append(
            InlineKeyboardButton(f"❔ Uncategorized ({uncategorized})", callback_data=encode_page(0, UNCATEGORIZED))
        )
    rows = [buttons] + [category_buttons[i : i + 2] for i in range(0, len(category_buttons), 2)]
    return text, InlineKeyboardMarkup(rows)


def _scope_label(scope: str, category: str | None) -> str:
    if scope == CATEGORY:
        return f"📂 {category}"
    if scope == UNCATEGORIZED:
        return "❔ Uncategorized"
    return "🕒 All notes"


def build_page(items: list[dict], page: int, total: int, scope: str, category: str | None):
    pages = max(1, -(-total // PAGE_SIZE))
    header = f"{_scope_label(scope, category)} — {total} note(s), page {page + 1}/{pages}"
    if not items:
        text = f"{header}\n\nNothing here anymore."
    else:
        text = "\n".join([header, ""] + [format_item_line(item) for item in items])
        text += "\n\nUse /view <id> to read one, or 🗑 to delete."

    delete_buttons = [
        InlineKeyboardButton(f"🗑 #{item['id']}", callback_data=f"delconfirm:{item['id']}") for item in items
    ]
    rows = [delete_buttons[i : i + 5] for i in range(0, len(delete_buttons), 5)]

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀ Prev", callback_data=encode_page(page - 1, scope, category)))
    nav.append(InlineKeyboardButton("📚 Categories", callback_data=MENU_CALLBACK))
    if page + 1 < pages:
        nav.append(InlineKeyboardButton("Next ▶", callback_data=encode_page(page + 1, scope, category)))
    rows.append(nav)
    return text, InlineKeyboardMarkup(rows)


async def render_menu(user_id: int):
    total = await asyncio.to_thread(count_items, user_id)
    if total == 0:
        return "You haven't saved anything yet.", None
    categories = await asyncio.to_thread(get_categories, user_id)
    uncategorized = await asyncio.to_thread(count_items, user_id, None, True)
    return build_menu(total, categories, uncategorized)


async def render_page(user_id: int, page: int, scope: str, category: str | None):
    filters = {"category": category} if scope == CATEGORY else {"uncategorized": scope == UNCATEGORIZED}
    total = await asyncio.to_thread(lambda: count_items(user_id, **filters))
    pages = max(1, -(-total // PAGE_SIZE))
    page = min(max(page, 0), pages - 1)
    items = await asyncio.to_thread(lambda: list_page(user_id, page * PAGE_SIZE, PAGE_SIZE, **filters))
    return build_page(items, page, total, scope, category)

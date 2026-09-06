"""
Shared display formatting — used by both app/bot/commands.py (slash
commands) and app/bot/handlers.py (the plain-message handler and its
callback handlers), so the two don't duplicate presentation logic.
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def build_merge_keyboard(existing_id: int, new_id: int) -> InlineKeyboardMarkup:
    """Yes/No/View-first buttons for a merge decision. Used both for
    Combine Mode's automatic suggestion (app/bot/handlers.py) and for a
    manually-requested /merge (app/bot/commands.py) — the confirmation flow
    is identical either way, handled by handle_merge_callback."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Yes, merge", callback_data=f"merge:yes:{existing_id}:{new_id}"),
                InlineKeyboardButton("No, keep separate", callback_data=f"merge:no:{existing_id}:{new_id}"),
            ],
            [
                InlineKeyboardButton(
                    f"👀 View #{existing_id} first", callback_data=f"merge:view:{existing_id}:{new_id}"
                ),
            ],
        ]
    )


def build_delete_keyboard(item_id: int) -> InlineKeyboardMarkup:
    """Yes/No buttons for a delete confirmation (callback_data:
    delete:<yes|no>:<id>, handled by handle_delete_callback). Used by
    /delete directly and by the per-item delete buttons attached to
    /list and /search results (see build_list_delete_keyboard)."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Yes, delete", callback_data=f"delete:yes:{item_id}"),
                InlineKeyboardButton("No, cancel", callback_data=f"delete:no:{item_id}"),
            ]
        ]
    )


def build_list_delete_keyboard(items: list[dict]) -> InlineKeyboardMarkup:
    """One small button per listed item (callback_data: delconfirm:<id>,
    handled by handle_delete_request_callback), so a /list or /search
    result can be deleted without retyping its id into /delete. Chunked
    into rows of 5 to keep the keyboard readable."""
    buttons = [InlineKeyboardButton(f"🗑 #{item['id']}", callback_data=f"delconfirm:{item['id']}") for item in items]
    rows = [buttons[i : i + 5] for i in range(0, len(buttons), 5)]
    return InlineKeyboardMarkup(rows)


def format_full_item(item: dict) -> str:
    lines = [f"#{item['id']} — {item['title'] or 'Untitled'}"]
    lines.append(f"Saved: {item['created_at'][:10]} · Source: {item['source']}")
    if item.get("url"):
        lines.append(f"URL: {item['url']}")
    if item.get("merged_from"):
        merged_ids = "#" + item["merged_from"].replace(",", ", #")
        lines.append(f"Merged from: {merged_ids}")
    lines.append("")
    lines.append(item["summary"])
    return "\n".join(lines)

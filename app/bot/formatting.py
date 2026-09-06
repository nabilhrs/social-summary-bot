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

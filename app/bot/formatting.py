"""
Shared display formatting — used by both app/bot/commands.py (slash
commands) and app/bot/handlers.py (the plain-message handler and its
callback handlers), so the two don't duplicate presentation logic.
"""
import html
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# Summaries are stored as plain text and rendered as Telegram HTML only at
# send time. Everything is escaped first, so content can never break
# Telegram's parser (see docs/memory.md #7).
_SUMMARY_LABEL_RE = re.compile(r"^\s*\**SUMMARY\**\s*:\s*\**\s*", re.IGNORECASE)
_MARKDOWN_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_SECTION_LABEL_RE = re.compile(r"^(TL;DR|KEY POINTS|TAKEAWAY)\s*:", re.MULTILINE)
_SECTION_GAP_RE = re.compile(r"\n+(?=<b>(?:KEY POINTS|TAKEAWAY):</b>)")
_BULLET_RE = re.compile(r"^[ \t]*[-*•][ \t]+", re.MULTILINE)


def render_summary_html(text: str) -> str:
    text = _SUMMARY_LABEL_RE.sub("", text.strip(), count=1)
    rendered = html.escape(text, quote=False)
    rendered = _MARKDOWN_BOLD_RE.sub(r"<b>\1</b>", rendered)
    rendered = _SECTION_LABEL_RE.sub(r"<b>\1:</b>", rendered)
    rendered = _SECTION_GAP_RE.sub("\n\n", rendered)
    return _BULLET_RE.sub("• ", rendered)


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
    """Telegram HTML — send with parse_mode=HTML."""
    escape = lambda value: html.escape(str(value), quote=False)  # noqa: E731
    lines = [f"<b>#{item['id']} — {escape(item['title'] or 'Untitled')}</b>"]
    lines.append(f"Saved: {item['created_at'][:10]} · Source: {escape(item['source'])}")
    if item.get("url"):
        lines.append(f"URL: {escape(item['url'])}")
    if item.get("merged_from"):
        merged_ids = "#" + item["merged_from"].replace(",", ", #")
        lines.append(f"Merged from: {escape(merged_ids)}")
    lines.append("")
    lines.append(render_summary_html(item["summary"]))
    return "\n".join(lines)

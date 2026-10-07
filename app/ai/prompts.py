"""
Prompt templates for the AI summarizer (PRD 5.4, 5.5, PRD V2 2.4).
"""

# PRD V2 2.4 — below this word count, content is treated as a short informal
# note (a tip, a quick thought) rather than an article, and gets a compact
# 1-3 sentence summary instead of the full TL;DR/KEY POINTS/TAKEAWAY structure.
_SHORT_CONTENT_WORD_THRESHOLD = 80

_RELATED_ID_INSTRUCTION = (
    "RELATED_ID: <the bare number id (no # symbol) of a previously saved "
    "item below that is about the same general subject as the new content "
    "— they don't need to cover the same specific event, just clearly be "
    "about the same topic (e.g. two different tips about job interviews "
    "should match, but a job-interview tip and a coffee-shop review should "
    "not) — or NONE if none share a subject with the new content>"
)

_TITLE_INSTRUCTION = (
    "TITLE: <a short, specific title for the new content, 3-8 words, in the "
    "same language as the content, no quotes>"
)

_CATEGORY_RULES = (
    "Reuse one of the existing categories whenever it reasonably fits — only "
    "create a new one if none do. A new category must be a broad, reusable "
    "topic of 1-3 words in English Title Case (e.g. Career, Food & Drink, "
    "Tech, Personal Finance, Health), never something specific to one item."
)


def _format_categories(existing_categories: list[str]) -> str:
    return ", ".join(existing_categories) if existing_categories else "(none yet)"


def _category_instruction(existing_categories: list[str]) -> str:
    return (
        f"CATEGORY: <one broad category for the new content. Existing "
        f"categories: {_format_categories(existing_categories)}. {_CATEGORY_RULES}>"
    )


_FULL_STRUCTURE = (
    "TL;DR: <1-2 sentence summary>\n"
    "KEY POINTS:\n"
    "- <bullet point>\n"
    "- <bullet point>\n"
    "(3-6 bullets total)\n"
    "TAKEAWAY: <1 sentence>"
)

_COMPACT_STRUCTURE = (
    "SUMMARY: <a compact summary, no headers. If the note makes one point, "
    "write 1-2 tight sentences as a single paragraph. If it clearly lists "
    "several distinct points or tips, use a short bullet list instead — "
    "pick whichever reads more naturally for this specific note, don't "
    "force one style>"
)


def _is_short_content(text: str) -> bool:
    return len(text.split()) < _SHORT_CONTENT_WORD_THRESHOLD


def _format_recent_items(recent_items: list[dict]) -> str:
    if not recent_items:
        return "(none saved yet)"
    return "\n\n".join(
        f"#{item['id']} — {item.get('title') or 'Untitled'}\n{item['summary']}"
        for item in recent_items
    )


def build_summary_prompt(
    content: dict, recent_items: list[dict] | None = None, existing_categories: list[str] | None = None
) -> str:
    header_lines = [f"Title: {content.get('title') or 'Untitled'}"]
    if content.get("author"):
        header_lines.append(f"Author: {content['author']}")

    if _is_short_content(content["text"]):
        intro = (
            "Summarize the new content below. This is a short, informal note "
            "(not an article) — keep the summary just as short."
        )
        structure = _COMPACT_STRUCTURE
    else:
        intro = "Summarize the new content below."
        structure = _FULL_STRUCTURE

    return (
        f"{intro} Reply with exactly this structure and nothing else — no "
        f"preamble, no extra commentary:\n\n"
        f"{structure}\n"
        f"{_RELATED_ID_INSTRUCTION}\n"
        f"{_TITLE_INSTRUCTION}\n"
        f"{_category_instruction(existing_categories or [])}\n\n"
        f"{chr(10).join(header_lines)}\n\n"
        "New content:\n"
        f"{content['text']}\n\n"
        "Previously saved items:\n"
        f"{_format_recent_items(recent_items or [])}"
    )


def build_organize_prompt(items: list[dict], existing_categories: list[str]) -> str:
    """One-time backfill: a title and category for each already-saved item.
    Items that already have a title keep it."""
    listing = "\n\n".join(
        f"id {item['id']}" + (f" (keep title: {item['title']})" if item.get("title") else "")
        + f"\n{item['summary']}"
        for item in items
    )
    return (
        "For each saved item below, give a short specific title (3-8 words, same "
        "language as the item, no quotes) and one broad category. Existing "
        f"categories: {_format_categories(existing_categories)}. {_CATEGORY_RULES} "
        "Items in this batch should share categories where they fit together. "
        "Where an item says 'keep title', return that title unchanged.\n\n"
        "Reply with only a JSON array, no other text, like:\n"
        '[{"id": 1, "title": "...", "category": "..."}]\n\n'
        f"Items:\n{listing}"
    )


def build_ask_prompt(question: str, items: list[dict], detailed_items: list[dict]) -> str:
    """`items` get their summaries included; `detailed_items` (the best
    keyword matches) also get their full original text, already truncated."""
    summaries = "\n\n".join(
        f"#{item['id']} ({item['created_at'][:10]}) — {item.get('title') or 'Untitled'}\n{item['summary']}"
        + (f"\nUser's own note: {item['user_note']}" if item.get("user_note") else "")
        for item in items
    )
    details = "\n\n".join(
        f"--- Full text of #{item['id']} ---\n{item['original_text']}" for item in detailed_items
    )
    return (
        "You are answering a question using only the user's own saved notes "
        "below. Rules:\n"
        "- Use only information in the notes. If they don't contain the answer, "
        "say so plainly — never fill gaps with outside knowledge.\n"
        "- Cite the note ids you used inline, like (#12).\n"
        "- Answer in the same language as the question.\n"
        "- Be concise. Use a short bullet list (\"- \") only if listing several things.\n"
        "- Plain text only: no headings and no Markdown except **bold** for emphasis.\n\n"
        f"Question: {question}\n\n"
        f"Saved note summaries (newest first):\n{summaries}\n\n"
        f"Full text of the notes most likely to be relevant:\n{details or '(none)'}"
    )


def build_merge_prompt(
    old_text: str, new_text: str, old_title: str | None, new_title: str | None
) -> str:
    if _is_short_content(old_text) and _is_short_content(new_text):
        merge_instruction = (
            "Merge them into ONE summary that combines the information without "
            "duplication. Both sources are short informal notes — keep the "
            "merged summary just as short."
        )
        structure = _COMPACT_STRUCTURE
    else:
        merge_instruction = (
            "Merge them into ONE summary that combines the information without "
            "duplication."
        )
        structure = _FULL_STRUCTURE

    return (
        f"The two sources below cover the same topic. {merge_instruction} "
        f"Reply with exactly this structure and nothing else — no preamble, "
        f"no extra commentary:\n\n"
        f"{structure}\n\n"
        f"--- Source: {old_title or 'Untitled'} ---\n"
        f"{old_text}\n\n"
        f"--- Source: {new_title or 'Untitled'} ---\n"
        f"{new_text}"
    )

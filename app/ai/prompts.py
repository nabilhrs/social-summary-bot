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

_FULL_STRUCTURE = (
    "TL;DR: <1-2 sentence summary>\n"
    "KEY POINTS:\n"
    "- <bullet point>\n"
    "- <bullet point>\n"
    "(3-6 bullets total)\n"
    "TAKEAWAY: <1 sentence>"
)

_COMPACT_STRUCTURE = "SUMMARY: <1-3 sentence summary, a single tight paragraph — no headers, no bullet points>"


def _is_short_content(text: str) -> bool:
    return len(text.split()) < _SHORT_CONTENT_WORD_THRESHOLD


def _format_recent_items(recent_items: list[dict]) -> str:
    if not recent_items:
        return "(none saved yet)"
    return "\n\n".join(
        f"#{item['id']} — {item.get('title') or 'Untitled'}\n{item['summary']}"
        for item in recent_items
    )


def build_summary_prompt(content: dict, recent_items: list[dict] | None = None) -> str:
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
        f"{_RELATED_ID_INSTRUCTION}\n\n"
        f"{chr(10).join(header_lines)}\n\n"
        "New content:\n"
        f"{content['text']}\n\n"
        "Previously saved items:\n"
        f"{_format_recent_items(recent_items or [])}"
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

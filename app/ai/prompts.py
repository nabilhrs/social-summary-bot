"""
Prompt templates for the AI summarizer (PRD 5.4, 5.5).
"""


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

    return (
        "Summarize the new content below. Reply with exactly this structure "
        "and nothing else — no preamble, no extra commentary:\n\n"
        "TL;DR: <1-2 sentence summary>\n"
        "KEY POINTS:\n"
        "- <bullet point>\n"
        "- <bullet point>\n"
        "(3-6 bullets total)\n"
        "TAKEAWAY: <1 sentence>\n"
        "RELATED_ID: <the bare number id (no # symbol) of a previously saved "
        "item below that is about the same general subject as the new content "
        "— they don't need to cover the same specific event, just clearly be "
        "about the same topic (e.g. two different tips about job interviews "
        "should match, but a job-interview tip and a coffee-shop review should "
        "not) — or NONE if none share a subject with the new content>\n\n"
        f"{chr(10).join(header_lines)}\n\n"
        "New content:\n"
        f"{content['text']}\n\n"
        "Previously saved items:\n"
        f"{_format_recent_items(recent_items or [])}"
    )


def build_merge_prompt(
    old_text: str, new_text: str, old_title: str | None, new_title: str | None
) -> str:
    return (
        "The two sources below cover the same topic. Merge them into ONE summary "
        "that combines the information without duplication. Reply with exactly "
        "this structure and nothing else — no preamble, no extra commentary:\n\n"
        "TL;DR: <1-2 sentence summary>\n"
        "KEY POINTS:\n"
        "- <bullet point>\n"
        "- <bullet point>\n"
        "(3-6 bullets total)\n"
        "TAKEAWAY: <1 sentence>\n\n"
        f"--- Source: {old_title or 'Untitled'} ---\n"
        f"{old_text}\n\n"
        f"--- Source: {new_title or 'Untitled'} ---\n"
        f"{new_text}"
    )

"""
Prompt template for the AI summarizer (PRD 5.4).
"""


def build_summary_prompt(content: dict) -> str:
    header_lines = [f"Title: {content.get('title') or 'Untitled'}"]
    if content.get("author"):
        header_lines.append(f"Author: {content['author']}")

    return (
        "Summarize the following content. Reply with exactly this structure "
        "and nothing else — no preamble, no extra commentary:\n\n"
        "TL;DR: <1-2 sentence summary>\n"
        "KEY POINTS:\n"
        "- <bullet point>\n"
        "- <bullet point>\n"
        "(3-6 bullets total)\n"
        "TAKEAWAY: <1 sentence>\n\n"
        f"{chr(10).join(header_lines)}\n\n"
        "Content:\n"
        f"{content['text']}"
    )

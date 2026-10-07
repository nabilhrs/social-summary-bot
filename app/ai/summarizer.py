"""
AI summarization (PRD 5.4) and Combine Mode's related-item flagging + merge (5.5).

On API failure, raises app.ai.gemini.GeminiError — its `kind` lets the
caller tell the user *why* (quota, bad key, Gemini overloaded) instead of a
generic error. Retries and model fallback live in app/ai/gemini.py.
"""
import asyncio
import logging
import re
from dataclasses import dataclass

from app.ai.gemini import FAILED, GeminiError, generate_text
from app.ai.prompts import build_ask_prompt, build_summary_prompt, build_merge_prompt
from app.ai.related import rank_by_shared_keywords

logger = logging.getLogger(__name__)

_ASK_DETAILED_ITEMS = 5
_ASK_DETAIL_CHARS = 8000
_ASK_SUMMARY_CHAR_BUDGET = 200_000
_ASK_TIMEOUT_SECONDS = 60

_RELATED_ID_RE = re.compile(r"RELATED_ID\s*:\s*\**\s*#?\s*(NONE|\d+)", re.IGNORECASE)


@dataclass
class Summary:
    text: str
    related_id: int | None = None


def _extract_related_id(text: str) -> tuple[str, int | None]:
    """Pull the RELATED_ID line out of a raw model response, returning the
    cleaned display text and the id it flagged (or None)."""
    match = _RELATED_ID_RE.search(text)
    if not match:
        return text.strip(), None

    related_id = None if match.group(1).upper() == "NONE" else int(match.group(1))
    cleaned = "\n".join(
        line for line in text.splitlines() if not _RELATED_ID_RE.search(line)
    ).strip()
    return cleaned, related_id


async def summarize(content: dict, recent_items: list[dict] | None, api_key: str) -> Summary:
    prompt = build_summary_prompt(content, recent_items)
    text = await asyncio.to_thread(generate_text, api_key, prompt)

    clean_text, related_id = _extract_related_id(text)
    if not clean_text:
        logger.warning("Gemini summary was empty after stripping RELATED_ID line")
        raise GeminiError(FAILED)

    return Summary(text=clean_text, related_id=related_id)


def select_ask_context(question: str, items: list[dict]) -> tuple[list[dict], list[dict]]:
    """`items` newest-first. Returns (items whose summaries fit the budget,
    best keyword matches with their original text truncated)."""
    budgeted, used = [], 0
    for item in items:
        used += len(item["summary"]) + 100
        if used > _ASK_SUMMARY_CHAR_BUDGET:
            break
        budgeted.append(item)

    matches = rank_by_shared_keywords(
        question,
        items,
        item_text=lambda item: f"{item.get('title') or ''} {item['summary']} {item['original_text']}",
    )
    detailed = [
        {**item, "original_text": item["original_text"][:_ASK_DETAIL_CHARS]}
        for item in matches[:_ASK_DETAILED_ITEMS]
    ]
    return budgeted, detailed


async def answer_question(question: str, items: list[dict], api_key: str) -> str:
    budgeted, detailed = select_ask_context(question, items)
    prompt = build_ask_prompt(question, budgeted, detailed)
    return await asyncio.to_thread(generate_text, api_key, prompt, _ASK_TIMEOUT_SECONDS)


async def merge_summaries(
    old_text: str, new_text: str, old_title: str | None, new_title: str | None, api_key: str
) -> Summary:
    prompt = build_merge_prompt(old_text, new_text, old_title, new_title)
    text = await asyncio.to_thread(generate_text, api_key, prompt)
    return Summary(text=text)

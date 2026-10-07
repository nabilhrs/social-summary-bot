"""
AI summarization (PRD 5.4) and Combine Mode's related-item flagging + merge (5.5).

On API failure, raises app.ai.gemini.GeminiError — its `kind` lets the
caller tell the user *why* (quota, bad key, Gemini overloaded) instead of a
generic error. Retries and model fallback live in app/ai/gemini.py.
"""
import asyncio
import json
import logging
import re
from dataclasses import dataclass

from app.ai.gemini import FAILED, GeminiError, generate_text
from app.ai.prompts import build_ask_prompt, build_merge_prompt, build_organize_prompt, build_summary_prompt
from app.ai.related import rank_by_shared_keywords

logger = logging.getLogger(__name__)

_ASK_DETAILED_ITEMS = 5
_ASK_DETAIL_CHARS = 8000
_ASK_SUMMARY_CHAR_BUDGET = 200_000
_ASK_TIMEOUT_SECONDS = 60

_TAG_LINE_RE = re.compile(
    r"^[\s*_#>-]*(RELATED_ID|TITLE|CATEGORY)[\s*_]*:[\s*_]*(.*?)[\s*_]*$", re.IGNORECASE
)
_RELATED_ID_VALUE_RE = re.compile(r"#?\s*(\d+)")
_MAX_TITLE_CHARS = 80
_MAX_CATEGORY_CHARS = 30
_ORGANIZE_BATCH_SIZE = 40


@dataclass
class Summary:
    text: str
    related_id: int | None = None
    title: str | None = None
    category: str | None = None


def _extract_tags(text: str) -> tuple[str, dict[str, str]]:
    """Split a raw model response into display text and the tag lines
    (RELATED_ID / TITLE / CATEGORY) at its end. Only the trailing block is
    read, so a summary bullet like "- Title: The Godfather" stays content.
    The first occurrence of each tag wins."""
    lines = text.splitlines()
    tags: dict[str, str] = {}
    cut = len(lines)
    for index in range(len(lines) - 1, -1, -1):
        line = lines[index]
        if not line.strip() or set(line.strip()) <= set("-*_="):
            cut = index
            continue
        match = _TAG_LINE_RE.match(line)
        if not match:
            break
        tags[match.group(1).upper()] = match.group(2).strip()  # walking backwards: earliest wins
        cut = index
    return "\n".join(lines[:cut]).strip(), tags


def _parse_related_id(value: str | None) -> int | None:
    match = _RELATED_ID_VALUE_RE.match(value or "")
    return int(match.group(1)) if match else None


def clean_title(value: str | None) -> str | None:
    title = " ".join((value or "").split()).strip("\"'“”‘’<>[]")
    return title[:_MAX_TITLE_CHARS].strip() or None


def clean_category(value: str | None, existing: list[str]) -> str | None:
    """Normalizes a category name, reusing an existing category's exact
    spelling when it matches case-insensitively."""
    name = " ".join((value or "").split()).strip("\"'“”‘’<>[].")
    name = name[:_MAX_CATEGORY_CHARS].strip()
    if not name:
        return None
    for existing_name in existing:
        if existing_name.casefold() == name.casefold():
            return existing_name
    return name[0].upper() + name[1:]


async def summarize(
    content: dict,
    recent_items: list[dict] | None,
    api_key: str,
    existing_categories: list[str] | None = None,
) -> Summary:
    existing_categories = existing_categories or []
    prompt = build_summary_prompt(content, recent_items, existing_categories)
    text = await asyncio.to_thread(generate_text, api_key, prompt)

    clean_text, tags = _extract_tags(text)
    if not clean_text:
        logger.warning("Gemini summary was empty after stripping tag lines")
        raise GeminiError(FAILED)

    return Summary(
        text=clean_text,
        related_id=_parse_related_id(tags.get("RELATED_ID")),
        title=clean_title(tags.get("TITLE")),
        category=clean_category(tags.get("CATEGORY"), existing_categories),
    )


def _parse_json_array(text: str) -> list:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rsplit("```", 1)[0]
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1:
        raise ValueError("no JSON array in response")
    return json.loads(text[start : end + 1])


async def organize_items(
    items: list[dict], existing_categories: list[str], api_key: str
) -> dict[int, tuple[str | None, str | None]]:
    """Titles and categories for already-saved items, in batches.
    Returns {id: (title, category)}; items Gemini skipped are left out."""
    categories = list(existing_categories)
    results: dict[int, tuple[str | None, str | None]] = {}
    for start in range(0, len(items), _ORGANIZE_BATCH_SIZE):
        batch = items[start : start + _ORGANIZE_BATCH_SIZE]
        text = await asyncio.to_thread(generate_text, api_key, build_organize_prompt(batch, categories))
        try:
            rows = _parse_json_array(text)
        except (ValueError, json.JSONDecodeError):
            logger.error("Couldn't parse organize response: %s", text[:500])
            raise GeminiError(FAILED)

        valid_ids = {item["id"] for item in batch}
        for row in rows:
            if not isinstance(row, dict) or row.get("id") not in valid_ids:
                continue
            category = clean_category(row.get("category"), categories)
            if category and category not in categories:
                categories.append(category)
            results[row["id"]] = (clean_title(row.get("title")), category)
    return results


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

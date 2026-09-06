"""
AI summarization (PRD 5.4) and Combine Mode's related-item flagging + merge (5.5).

On any API failure, returns None so the caller can show the fixed error message
from PRD 5.9 rather than leaking exception details to the user.
"""
import asyncio
import logging
import re
from dataclasses import dataclass

from google import genai

from app.config import config
from app.ai.prompts import build_summary_prompt, build_merge_prompt

logger = logging.getLogger(__name__)

_MODEL = "gemini-3.6-flash"
_TIMEOUT_SECONDS = 30
_RELATED_ID_RE = re.compile(r"RELATED_ID\s*:\s*\**\s*#?\s*(NONE|\d+)", re.IGNORECASE)

_client = genai.Client(api_key=config.gemini_api_key)


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


async def _generate(prompt: str) -> str | None:
    try:
        response = await asyncio.wait_for(
            asyncio.to_thread(
                _client.models.generate_content,
                model=_MODEL,
                contents=prompt,
            ),
            timeout=_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.error("Gemini API call timed out after %ss", _TIMEOUT_SECONDS)
        return None
    except Exception:
        logger.exception("Gemini API call failed")
        return None

    text = (response.text or "").strip()
    if not text:
        logger.warning("Gemini returned an empty response")
        return None
    return text


async def summarize(content: dict, recent_items: list[dict] | None = None) -> Summary | None:
    prompt = build_summary_prompt(content, recent_items)
    text = await _generate(prompt)
    if text is None:
        return None

    clean_text, related_id = _extract_related_id(text)
    if not clean_text:
        logger.warning("Gemini summary was empty after stripping RELATED_ID line")
        return None

    return Summary(text=clean_text, related_id=related_id)


async def merge_summaries(
    old_text: str, new_text: str, old_title: str | None, new_title: str | None
) -> Summary | None:
    prompt = build_merge_prompt(old_text, new_text, old_title, new_title)
    text = await _generate(prompt)
    if text is None:
        return None
    return Summary(text=text)

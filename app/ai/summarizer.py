"""
AI summarization (PRD 5.4). Single entry point: summarize(content) -> Summary | None.

On any API failure, returns None so the caller can show the fixed error message
from PRD 5.9 rather than leaking exception details to the user.
"""
import asyncio
import logging
from dataclasses import dataclass

from google import genai

from app.config import config
from app.ai.prompts import build_summary_prompt

logger = logging.getLogger(__name__)

_MODEL = "gemini-3.6-flash"

_client = genai.Client(api_key=config.gemini_api_key)


@dataclass
class Summary:
    text: str


async def summarize(content: dict) -> Summary | None:
    prompt = build_summary_prompt(content)
    try:
        response = await asyncio.to_thread(
            _client.models.generate_content,
            model=_MODEL,
            contents=prompt,
        )
    except Exception:
        logger.exception("Gemini API call failed")
        return None

    text = (response.text or "").strip()
    if not text:
        logger.warning("Gemini returned an empty summary")
        return None

    return Summary(text=text)

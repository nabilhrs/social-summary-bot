"""
YouTube videos (including Shorts and live replays). Gemini watches public
YouTube videos straight from the link, so nothing is downloaded. The title
and channel come from YouTube's public oEmbed endpoint (what link previews
use), which is optional: the summary works without it.
"""
import asyncio
import logging

import httpx
from google.genai import types

from app.ai.gemini import generate_text

logger = logging.getLogger(__name__)

_OEMBED_URL = "https://www.youtube.com/oembed"
_OEMBED_TIMEOUT = 10.0
_DESCRIBE_TIMEOUT_SECONDS = 120
_DESCRIBE_DEADLINE_SECONDS = 200

YOUTUBE_PROMPT = (
    "Describe what this video covers, in order and in detail: the main topics, "
    "key points, any steps or instructions, and notable facts, names or numbers. "
    "Say who is speaking if it's clear. Plain text, no headings."
)


def canonical_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


async def _oembed(video_id: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=_OEMBED_TIMEOUT) as client:
            response = await client.get(_OEMBED_URL, params={"url": canonical_url(video_id), "format": "json"})
            response.raise_for_status()
            data = response.json()
        return {"title": data.get("title"), "author": data.get("author_name")}
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("YouTube oEmbed failed for %s: %s", video_id, exc)
        return {}


async def fetch_and_extract(video_id: str, api_key: str) -> dict:
    """{"title", "author", "text"}. Raises GeminiError if Gemini couldn't
    watch it (a private, age-restricted or very long video fails as FAILED)."""
    meta = await _oembed(video_id)
    video = types.Part(file_data=types.FileData(file_uri=canonical_url(video_id)))
    # Low media resolution cuts video tokens to about a third; plenty for summarizing.
    config = types.GenerateContentConfig(media_resolution=types.MediaResolution.MEDIA_RESOLUTION_LOW)
    text = await asyncio.to_thread(
        generate_text,
        api_key,
        [video, YOUTUBE_PROMPT],
        _DESCRIBE_TIMEOUT_SECONDS,
        _DESCRIBE_DEADLINE_SECONDS,
        config,
    )
    return {"title": meta.get("title"), "author": meta.get("author"), "text": text}

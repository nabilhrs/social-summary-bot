"""
TikTok video extraction (PRD V2 TikTok revision).

Downloads the video via yt-dlp and asks Gemini to describe its actual
content (visuals + speech) — the caption alone is often minimal or
missing, and the point is to summarize the video itself, not just
whatever text the poster typed.

TikTok's terms restrict automated downloading, so this extractor 
is meant for personal use only (see the README). yt-dlp's curl-cffi 
"impersonation" extra is required: without it, TikTok answers with a 
JS challenge page instead of the video.

PRD V2 per-user key revision: takes the caller's own resolved Gemini API
key rather than a fixed client — video calls are the most expensive kind,
which is exactly why per-user keys exist.
"""
import asyncio
import logging
import os
import tempfile

import yt_dlp

from app.ai.gemini import GeminiError, describe_file
from app.extractors.media import PROMPTS, VIDEO

logger = logging.getLogger(__name__)

_OVERALL_TIMEOUT_SECONDS = 240
_DESCRIBE_TIMEOUT_SECONDS = 60
_DESCRIBE_DEADLINE_SECONDS = 100
_MAX_FILESIZE_BYTES = 200 * 1024 * 1024


def _build_text(description: str, caption: str | None) -> str:
    if caption:
        return f"{description}\n\nCaption: {caption}"
    return description


def _download_and_describe(url: str, api_key: str) -> dict | None:
    """Runs in a worker thread — yt-dlp and the genai SDK's file upload are
    both synchronous. Downloads the video to a temp dir and has Gemini
    describe it (describe_file deletes the upload; the temp dir cleans up
    the local copy)."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        opts = {
            "quiet": True,
            "no_warnings": True,
            "outtmpl": os.path.join(tmp_dir, "%(id)s.%(ext)s"),
            "format": "mp4/best",
            "max_filesize": _MAX_FILESIZE_BYTES,
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
        except Exception:
            logger.exception("yt-dlp failed for %s", url)
            return None

        files = os.listdir(tmp_dir)
        if not files:
            logger.warning("yt-dlp reported success but no file was written for %s", url)
            return None
        file_path = os.path.join(tmp_dir, files[0])

        try:
            description = describe_file(
                api_key,
                file_path,
                PROMPTS[VIDEO],
                timeout_seconds=_DESCRIBE_TIMEOUT_SECONDS,
                deadline_seconds=_DESCRIBE_DEADLINE_SECONDS,
            )
        except GeminiError:
            raise
        except Exception:
            logger.exception("Gemini video description failed for %s", url)
            return None

    author = info.get("uploader") or info.get("creator")
    caption = (info.get("description") or "").strip() or None
    return {"author": author, "text": _build_text(description, caption)}


async def fetch_and_extract(url: str, api_key: str) -> dict | None:
    """Returns None if the video couldn't be downloaded or processed;
    raises GeminiError if Gemini itself refused (quota, bad key, overload)."""
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_download_and_describe, url, api_key),
            timeout=_OVERALL_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.error("TikTok video processing timed out after %ss for %s", _OVERALL_TIMEOUT_SECONDS, url)
        return None

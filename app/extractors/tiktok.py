"""
TikTok video extraction (PRD V2 TikTok revision).

Downloads the video via yt-dlp and asks Gemini to describe its actual
content (visuals + speech) — the caption alone is often minimal or
missing, and the point is to summarize the video itself, not just
whatever text the poster typed.

Unlike Threads' Open Graph approach (a universally-sanctioned mechanism
every site supports for link previews), downloading a TikTok video isn't
something TikTok's terms permit. Built at the user's explicit, informed
request after that tradeoff was stated plainly (see summarizer_bot_prd_v2.md)
— they weighed it against having to manually paste captions and chose this
anyway. yt-dlp needs its curl-cffi "impersonation" extra to get past
TikTok's bot-challenge at all: verified live before writing this that a
plain fetch, and even yt-dlp without impersonation, gets blocked with a JS
challenge page (TikTok pushes back on automated access harder than any
other platform this bot talks to).

PRD V2 per-user key revision: takes the caller's own resolved Gemini API
key rather than a fixed client — video calls are the most expensive kind,
which is exactly why per-user keys exist.
"""
import asyncio
import logging
import os
import tempfile
import time

import yt_dlp
from google import genai

logger = logging.getLogger(__name__)

_MODEL = "gemini-3.6-flash"
_OVERALL_TIMEOUT_SECONDS = 120
_MAX_FILESIZE_BYTES = 200 * 1024 * 1024
_MAX_UPLOAD_POLL_SECONDS = 60

_DESCRIBE_PROMPT = (
    "Describe what actually happens in this video — visuals, actions, and "
    "any spoken or sung content — in enough detail for someone who hasn't "
    "watched it to understand what it's about."
)


def _build_text(description: str, caption: str | None) -> str:
    if caption:
        return f"{description}\n\nCaption: {caption}"
    return description


def _download_and_describe(url: str, api_key: str) -> dict | None:
    """Runs in a worker thread — yt-dlp and the genai SDK's file upload are
    both synchronous. Downloads the video to a temp dir, uploads it to
    Gemini, asks for a description, then cleans up both the temp file and
    the uploaded copy before returning, regardless of outcome."""
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

        uploaded = None
        try:
            client = genai.Client(api_key=api_key)
            uploaded = client.files.upload(file=file_path)
            waited = 0
            while uploaded.state.name == "PROCESSING" and waited < _MAX_UPLOAD_POLL_SECONDS:
                time.sleep(1)
                waited += 1
                uploaded = client.files.get(name=uploaded.name)

            if uploaded.state.name != "ACTIVE":
                logger.warning("Uploaded video never became active (state=%s) for %s", uploaded.state, url)
                return None

            response = client.models.generate_content(
                model=_MODEL,
                contents=[uploaded, _DESCRIBE_PROMPT],
            )
            description = (response.text or "").strip()
            if not description:
                logger.warning("Gemini returned an empty video description for %s", url)
                return None
        except Exception:
            logger.exception("Gemini video description failed for %s", url)
            return None
        finally:
            if uploaded is not None:
                try:
                    client.files.delete(name=uploaded.name)
                except Exception:
                    logger.warning("Failed to clean up uploaded Gemini file for %s", url)

    author = info.get("uploader") or info.get("creator")
    caption = (info.get("description") or "").strip() or None
    return {"author": author, "text": _build_text(description, caption)}


async def fetch_and_extract(url: str, api_key: str) -> dict | None:
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_download_and_describe, url, api_key),
            timeout=_OVERALL_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.error("TikTok video processing timed out after %ss for %s", _OVERALL_TIMEOUT_SECONDS, url)
        return None

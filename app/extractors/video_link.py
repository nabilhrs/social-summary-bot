"""
Video links (TikTok, Instagram Reels and video posts): download the video
with yt-dlp and have Gemini describe what's actually shown and said. The
caption alone is often minimal or missing.

TikTok's and Instagram's terms restrict automated downloading, so this is
meant for personal use only (see the README). yt-dlp's curl-cffi
"impersonation" extra is required: without it, TikTok answers with a JS
challenge page instead of the video. Instagram serves public reels without
a login, but often refuses requests from cloud servers or after many
anonymous requests; those failures are reported as LOGIN_REQUIRED.
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

NO_VIDEO = "no_video"
LOGIN_REQUIRED = "login_required"
_LOGIN_MARKERS = ("--cookies", "registered users", "log in", "login", "rate-limit", "empty media response")


class VideoUnavailable(Exception):
    """yt-dlp couldn't get a video for a reason worth telling the user."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def classify_download_error(message: str) -> str | None:
    lowered = message.lower()
    if "there is no video in this post" in lowered:
        return NO_VIDEO
    if any(marker in lowered for marker in _LOGIN_MARKERS):
        return LOGIN_REQUIRED
    return None


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
            # An Instagram carousel is a playlist; only its first video is summarized.
            "playlist_items": "1",
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
        except yt_dlp.utils.DownloadError as exc:
            reason = classify_download_error(str(exc))
            logger.warning("yt-dlp couldn't fetch %s (%s): %s", url, reason, exc)
            if reason:
                raise VideoUnavailable(reason) from exc
            return None
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

    entry = (info.get("entries") or [info])[0] or info
    author = info.get("uploader") or entry.get("uploader") or entry.get("creator") or entry.get("channel")
    caption = (info.get("description") or entry.get("description") or "").strip() or None
    return {"author": author, "text": _build_text(description, caption)}


async def fetch_and_extract(url: str, api_key: str) -> dict | None:
    """Returns None if the video couldn't be downloaded or processed. Raises
    VideoUnavailable for a post with no video or one behind a login, and
    GeminiError if Gemini itself refused (quota, bad key, overload)."""
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_download_and_describe, url, api_key),
            timeout=_OVERALL_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.error("Video processing timed out after %ss for %s", _OVERALL_TIMEOUT_SECONDS, url)
        return None

"""
TikTok and Instagram links: videos are downloaded with yt-dlp and Gemini
describes what's actually shown and said; photo posts (one photo or a
carousel) have their images read by Gemini in one request. The caption is
added to either. The caption alone is often minimal or missing.

TikTok's and Instagram's terms restrict automated downloading, so this is
meant for personal use only (see the README). yt-dlp's curl-cffi
"impersonation" extra is required: without it, TikTok answers with a JS
challenge page instead of the video. Instagram serves public posts without
a login, but often refuses requests from cloud servers or after many
anonymous requests; those failures are reported as LOGIN_REQUIRED.
"""
import asyncio
import logging
import os
import tempfile

import httpx
import yt_dlp
from google.genai import types

from app.ai.gemini import GeminiError, describe_file, generate_text
from app.extractors.media import PROMPTS, VIDEO

logger = logging.getLogger(__name__)

_OVERALL_TIMEOUT_SECONDS = 240
_DESCRIBE_TIMEOUT_SECONDS = 60
_DESCRIBE_DEADLINE_SECONDS = 100
_MAX_FILESIZE_BYTES = 200 * 1024 * 1024
_MAX_IMAGES = 10
_IMAGE_DOWNLOAD_TIMEOUT = 20.0

NO_VIDEO = "no_video"
LOGIN_REQUIRED = "login_required"
_LOGIN_MARKERS = ("--cookies", "registered users", "log in", "login", "rate-limit", "empty media response")

POST_IMAGES_PROMPT = (
    "These are the images from one social media post, in order. Transcribe all "
    "text visible in them exactly, image by image. Then describe what they show, "
    "in enough detail for someone who hasn't seen the post to understand it."
)


class VideoUnavailable(Exception):
    """yt-dlp couldn't get the post for a reason worth telling the user."""

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


def _has_video(item: dict) -> bool:
    return any(f.get("vcodec") not in (None, "none") for f in item.get("formats") or [])


def _best_image_url(item: dict) -> str | None:
    # yt-dlp lists thumbnails worst to best; for Instagram the last is the uncropped original.
    thumbnails = item.get("thumbnails") or []
    return thumbnails[-1].get("url") if thumbnails else item.get("thumbnail")


def classify_post(info: dict) -> tuple[str, list[str]]:
    """("video", []) if the post starts with a video, ("images", urls) for a
    photo post or carousel (photos only, at most _MAX_IMAGES), or ("none", [])."""
    items = [item for item in (info.get("entries") or [info]) if item]
    if not items:
        return "none", []
    if _has_video(items[0]):
        return "video", []
    urls = [url for url in (_best_image_url(item) for item in items if not _has_video(item)) if url]
    return ("images", urls[:_MAX_IMAGES]) if urls else ("none", [])


def _build_text(description: str, caption: str | None) -> str:
    if caption:
        return f"{description}\n\nCaption: {caption}"
    return description


def _probe(url: str) -> dict:
    """Post metadata without downloading, and without failing on photo posts."""
    opts = {"quiet": True, "no_warnings": True, "ignore_no_formats_error": True, "skip_download": True}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as exc:
        reason = classify_download_error(str(exc))
        logger.warning("yt-dlp couldn't read %s (%s): %s", url, reason, exc)
        if reason:
            raise VideoUnavailable(reason) from exc
        raise


def _describe_video(url: str, api_key: str) -> str | None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        opts = {
            "quiet": True,
            "no_warnings": True,
            "outtmpl": os.path.join(tmp_dir, "%(id)s.%(ext)s"),
            "format": "mp4/best",
            "max_filesize": _MAX_FILESIZE_BYTES,
            # A carousel is a playlist; only its first video is summarized.
            "playlist_items": "1",
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.extract_info(url, download=True)
        except yt_dlp.utils.DownloadError as exc:
            reason = classify_download_error(str(exc))
            logger.warning("yt-dlp couldn't download %s (%s): %s", url, reason, exc)
            if reason:
                raise VideoUnavailable(reason) from exc
            return None

        files = os.listdir(tmp_dir)
        if not files:
            logger.warning("yt-dlp reported success but no file was written for %s", url)
            return None
        return describe_file(
            api_key,
            os.path.join(tmp_dir, files[0]),
            PROMPTS[VIDEO],
            timeout_seconds=_DESCRIBE_TIMEOUT_SECONDS,
            deadline_seconds=_DESCRIBE_DEADLINE_SECONDS,
        )


def _describe_images(urls: list[str], api_key: str) -> str | None:
    parts = []
    with httpx.Client(timeout=_IMAGE_DOWNLOAD_TIMEOUT, follow_redirects=True) as client:
        for url in urls:
            response = client.get(url)
            response.raise_for_status()
            mime_type = response.headers.get("content-type", "").split(";")[0]
            if not mime_type.startswith("image/"):
                mime_type = "image/jpeg"
            parts.append(types.Part.from_bytes(data=response.content, mime_type=mime_type))
    return generate_text(
        api_key,
        [*parts, POST_IMAGES_PROMPT],
        timeout_seconds=_DESCRIBE_TIMEOUT_SECONDS,
        deadline_seconds=_DESCRIBE_DEADLINE_SECONDS,
    )


def _download_and_describe(url: str, api_key: str) -> dict | None:
    """Runs in a worker thread — yt-dlp, httpx here and the genai SDK calls
    are all synchronous."""
    try:
        info = _probe(url)
        kind, image_urls = classify_post(info)
        if kind == "none":
            raise VideoUnavailable(NO_VIDEO)
        description = _describe_video(url, api_key) if kind == "video" else _describe_images(image_urls, api_key)
    except (GeminiError, VideoUnavailable):
        raise
    except Exception:
        logger.exception("Couldn't process %s", url)
        return None
    if not description:
        return None

    entry = (info.get("entries") or [info])[0] or info
    author = info.get("uploader") or entry.get("uploader") or entry.get("creator") or entry.get("channel")
    caption = (info.get("description") or entry.get("description") or "").strip() or None
    return {"author": author, "text": _build_text(description, caption)}


async def fetch_and_extract(url: str, api_key: str) -> dict | None:
    """Returns None if the post couldn't be downloaded or processed. Raises
    VideoUnavailable for a post with nothing to read or one behind a login,
    and GeminiError if Gemini itself refused (quota, bad key, overload)."""
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_download_and_describe, url, api_key),
            timeout=_OVERALL_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.error("Processing timed out after %ss for %s", _OVERALL_TIMEOUT_SECONDS, url)
        return None

"""
TikTok and Instagram links: every photo and video in the post (a single
reel, a photo post, or a carousel mixing both) is downloaded and Gemini
reads them together in one request, in order: what's shown, said and
written. The caption is added; on its own it's often minimal or missing.

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

from app.ai.gemini import GeminiError, describe_many
from app.extractors.media import PROMPTS, VIDEO

logger = logging.getLogger(__name__)

_OVERALL_TIMEOUT_SECONDS = 300
_DESCRIBE_TIMEOUT_SECONDS = 90
_DESCRIBE_DEADLINE_SECONDS = 150
_MAX_FILESIZE_BYTES = 200 * 1024 * 1024
_MAX_ITEMS = 10
_MAX_VIDEO_SECONDS = 180
_ASSUMED_VIDEO_SECONDS = 30  # when yt-dlp doesn't report a duration
_IMAGE_DOWNLOAD_TIMEOUT = 20.0

NO_VIDEO = "no_video"
LOGIN_REQUIRED = "login_required"
_LOGIN_MARKERS = ("--cookies", "registered users", "log in", "login", "rate-limit", "empty media response")

POST_IMAGES_PROMPT = (
    "These are the images from one social media post, in order. Transcribe all "
    "text visible in them exactly, image by image. Then describe what they show, "
    "in enough detail for someone who hasn't seen the post to understand it."
)
POST_ITEMS_PROMPT = (
    "These are the photos and videos from one social media post, in order. Go "
    "through them one by one: transcribe any visible text exactly, describe what's "
    "shown, and include any spoken or sung content. Then say in a sentence or two "
    "what the post as a whole is about."
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


def plan_post(info: dict) -> list[tuple[str, int, str | None]]:
    """Every photo and video in the post, in order, as (kind, playlist index
    starting at 1, image url or None). At most _MAX_ITEMS items, and videos
    stop being added once they'd take the total past _MAX_VIDEO_SECONDS
    (the first video is always kept)."""
    items = [item for item in (info.get("entries") or [info]) if item]
    plan, video_seconds = [], 0.0
    for index, item in enumerate(items[:_MAX_ITEMS], start=1):
        if _has_video(item):
            duration = item.get("duration") or _ASSUMED_VIDEO_SECONDS
            if video_seconds and video_seconds + duration > _MAX_VIDEO_SECONDS:
                continue
            video_seconds += duration
            plan.append(("video", index, None))
        else:
            url = _best_image_url(item)
            if url:
                plan.append(("image", index, url))
    return plan


def prompt_for(plan: list[tuple[str, int, str | None]]) -> str:
    kinds = {kind for kind, _, _ in plan}
    if kinds == {"video"} and len(plan) == 1:
        return PROMPTS[VIDEO]
    if kinds == {"image"}:
        return POST_IMAGES_PROMPT
    return POST_ITEMS_PROMPT


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


def _download_videos(url: str, indexes: list[int], tmp_dir: str) -> dict[int, str]:
    """{playlist index: file path} for the given videos. A single-video post
    has no playlist index; its file comes back under index 1."""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "outtmpl": os.path.join(tmp_dir, "%(playlist_index|1)s.%(ext)s"),
        "format": "mp4/best",
        "max_filesize": _MAX_FILESIZE_BYTES,
        "playlist_items": ",".join(map(str, indexes)),
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.extract_info(url, download=True)
    except yt_dlp.utils.DownloadError as exc:
        reason = classify_download_error(str(exc))
        logger.warning("yt-dlp couldn't download %s (%s): %s", url, reason, exc)
        if reason:
            raise VideoUnavailable(reason) from exc
        raise
    files = {}
    for name in os.listdir(tmp_dir):
        stem = os.path.splitext(name)[0]
        if stem.isdigit():
            files[int(stem)] = os.path.join(tmp_dir, name)
    return files


def _download_image(client: httpx.Client, url: str) -> tuple[bytes, str]:
    response = client.get(url)
    response.raise_for_status()
    mime_type = response.headers.get("content-type", "").split(";")[0]
    return response.content, mime_type if mime_type.startswith("image/") else "image/jpeg"


def _describe_post(url: str, plan: list[tuple[str, int, str | None]], api_key: str) -> str | None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        video_indexes = [index for kind, index, _ in plan if kind == "video"]
        videos = _download_videos(url, video_indexes, tmp_dir) if video_indexes else {}
        items = []
        with httpx.Client(timeout=_IMAGE_DOWNLOAD_TIMEOUT, follow_redirects=True) as client:
            for kind, index, image_url in plan:
                if kind == "image":
                    items.append(_download_image(client, image_url))
                elif index in videos:
                    items.append((videos[index], "video/mp4"))
                else:
                    logger.warning("Video %d of %s wasn't downloaded; skipping it", index, url)
        if not items:
            return None
        return describe_many(api_key, items, prompt_for(plan), _DESCRIBE_TIMEOUT_SECONDS, _DESCRIBE_DEADLINE_SECONDS)


def _download_and_describe(url: str, api_key: str) -> dict | None:
    """Runs in a worker thread — yt-dlp, httpx here and the genai SDK calls
    are all synchronous."""
    try:
        info = _probe(url)
        plan = plan_post(info)
        if not plan:
            raise VideoUnavailable(NO_VIDEO)
        description = _describe_post(url, plan, api_key)
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

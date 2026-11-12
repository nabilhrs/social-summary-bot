"""
Shared helpers for turning raw input into the normalized content object (PRD 5.1, 5.3).
"""
import re
from urllib.parse import parse_qsl, urlencode, urlparse


def looks_like_url(text: str) -> bool:
    text = text.strip()
    if " " in text or "\n" in text:
        return False
    parsed = urlparse(text)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


# PRD V2 2.1 — platforms with no way to get post content without violating
# their terms or scraping a private API. Detected up front so we skip a
# doomed fetch and give an honest, platform-specific fallback instead of a
# generic one. Currently empty: Threads (Open Graph tags), TikTok and
# Instagram (yt-dlp video download, personal use only — see the README) got real
# extraction instead. Kept as an extensibility point for a future platform
# that turns out to have no viable path at all.
_UNSUPPORTED_PLATFORM_DOMAINS: dict[str, str] = {}

_THREADS_DOMAINS = ("threads.net", "threads.com")
# Video platforms handled by app/extractors/video_link.py, keyed by source name.
_VIDEO_PLATFORM_DOMAINS = {
    "tiktok": ("tiktok.com",),
    "instagram": ("instagram.com", "instagr.am"),
}
VIDEO_PLATFORM_NAMES = {"tiktok": "TikTok", "instagram": "Instagram"}


def _matches(hostname: str, domains: tuple[str, ...]) -> bool:
    return any(hostname == domain or hostname.endswith(f".{domain}") for domain in domains)


def detect_unsupported_platform(url: str) -> str | None:
    hostname = (urlparse(url).hostname or "").lower()
    for domain, platform in _UNSUPPORTED_PLATFORM_DOMAINS.items():
        if hostname == domain or hostname.endswith(f".{domain}"):
            return platform
    return None


def is_threads_url(url: str) -> bool:
    return _matches((urlparse(url).hostname or "").lower(), _THREADS_DOMAINS)


_YOUTUBE_HOSTS = ("youtube.com", "youtu.be", "youtube-nocookie.com")
_YOUTUBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def youtube_video_id(url: str) -> str | None:
    """The 11-character video id for watch, youtu.be, Shorts, live and embed links."""
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if not _matches(hostname, _YOUTUBE_HOSTS):
        return None
    parts = [p for p in parsed.path.split("/") if p]
    if hostname.endswith("youtu.be"):
        candidate = parts[0] if parts else ""
    elif parts[:1] == ["watch"]:
        candidate = dict(parse_qsl(parsed.query)).get("v", "")
    elif len(parts) >= 2 and parts[0] in ("shorts", "live", "embed", "v"):
        candidate = parts[1]
    else:
        return None
    return candidate if _YOUTUBE_ID_RE.match(candidate) else None


# Query parameters that only track where a link was shared from.
_TRACKING_PARAMS = {
    "si", "igsh", "igshid", "fbclid", "gclid", "ref", "ref_src", "mc_cid", "mc_eid", "feature",
    "is_from_webapp", "sender_device", "sender_web_id", "share_app_id", "_r", "_t", "t", "pp",
}


def link_key(url: str) -> str:
    """A canonical form of a link, so the same page shared twice (with a
    different tracking suffix, www./m. prefix or trailing slash) matches."""
    video_id = youtube_video_id(url)
    if video_id:
        return f"youtube:{video_id}"
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    for prefix in ("www.", "m."):
        if host.startswith(prefix):
            host = host[len(prefix):]
    query = sorted(
        (k, v) for k, v in parse_qsl(parsed.query) if k not in _TRACKING_PARAMS and not k.startswith("utm_")
    )
    path = parsed.path.rstrip("/")
    return f"{host}{path}" + (f"?{urlencode(query)}" if query else "")


def normalize_youtube_video(url: str, extracted: dict) -> dict:
    return {
        "title": extracted.get("title"),
        "author": extracted.get("author"),
        "source": "youtube",
        "url": url,
        "text": extracted["text"],
    }


def video_platform(url: str) -> str | None:
    """"tiktok" or "instagram" for a link to one of those platforms, else None."""
    hostname = (urlparse(url).hostname or "").lower()
    for platform, domains in _VIDEO_PLATFORM_DOMAINS.items():
        if _matches(hostname, domains):
            return platform
    return None


def normalize_pasted_text(text: str) -> dict:
    return {
        "title": None,
        "author": None,
        "source": "pasted_text",
        "url": None,
        "text": text.strip(),
    }


def normalize_web_article(url: str, extracted: dict) -> dict:
    return {
        "title": extracted.get("title"),
        "author": extracted.get("author"),
        "source": "web",
        "url": url,
        "text": extracted["text"],
    }


def normalize_threads_post(url: str, extracted: dict) -> dict:
    return {
        "title": None,
        "author": extracted.get("author"),
        "source": "threads",
        "url": url,
        "text": extracted["text"],
    }


def normalize_video_post(url: str, extracted: dict, platform: str) -> dict:
    return {
        "title": None,
        "author": extracted.get("author"),
        "source": platform,
        "url": url,
        "text": extracted["text"],
    }

"""
Shared helpers for turning raw input into the normalized content object (PRD 5.1, 5.3).
"""
from urllib.parse import urlparse


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

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
# generic one. Currently empty: Threads (Open Graph tags) and TikTok (yt-dlp
# video download, personal use only — see the README) both got real
# extraction instead. Kept as an extensibility point for a future platform
# that turns out to have no viable path at all.
_UNSUPPORTED_PLATFORM_DOMAINS: dict[str, str] = {}

_THREADS_DOMAINS = ("threads.net", "threads.com")
_TIKTOK_DOMAINS = ("tiktok.com",)


def detect_unsupported_platform(url: str) -> str | None:
    hostname = (urlparse(url).hostname or "").lower()
    for domain, platform in _UNSUPPORTED_PLATFORM_DOMAINS.items():
        if hostname == domain or hostname.endswith(f".{domain}"):
            return platform
    return None


def is_threads_url(url: str) -> bool:
    hostname = (urlparse(url).hostname or "").lower()
    return any(hostname == domain or hostname.endswith(f".{domain}") for domain in _THREADS_DOMAINS)


def is_tiktok_url(url: str) -> bool:
    hostname = (urlparse(url).hostname or "").lower()
    return any(hostname == domain or hostname.endswith(f".{domain}") for domain in _TIKTOK_DOMAINS)


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


def normalize_tiktok_video(url: str, extracted: dict) -> dict:
    return {
        "title": None,
        "author": extracted.get("author"),
        "source": "tiktok",
        "url": url,
        "text": extracted["text"],
    }

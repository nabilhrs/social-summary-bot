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
# generic one. Threads was here too until PRD V2 2.1's revision found that
# its Open Graph meta tags (a universal, ToS-clean web standard, unlike the
# oEmbed API) carry the full caption — see app/extractors/threads.py.
_UNSUPPORTED_PLATFORM_DOMAINS = {
    "tiktok.com": "TikTok",
}

_THREADS_DOMAINS = ("threads.net", "threads.com")


def detect_unsupported_platform(url: str) -> str | None:
    hostname = (urlparse(url).hostname or "").lower()
    for domain, platform in _UNSUPPORTED_PLATFORM_DOMAINS.items():
        if hostname == domain or hostname.endswith(f".{domain}"):
            return platform
    return None


def is_threads_url(url: str) -> bool:
    hostname = (urlparse(url).hostname or "").lower()
    return any(hostname == domain or hostname.endswith(f".{domain}") for domain in _THREADS_DOMAINS)


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

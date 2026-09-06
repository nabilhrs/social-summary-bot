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


# PRD V2 2.1 — platforms whose terms don't allow extracting post content
# (Threads' oEmbed terms restrict use to rendering an embed; TikTok has no
# public API for this at all). Detected up front so we skip a doomed fetch
# and give an honest, platform-specific fallback instead of a generic one.
_UNSUPPORTED_PLATFORM_DOMAINS = {
    "threads.net": "Threads",
    "threads.com": "Threads",
    "tiktok.com": "TikTok",
}


def detect_unsupported_platform(url: str) -> str | None:
    hostname = (urlparse(url).hostname or "").lower()
    for domain, platform in _UNSUPPORTED_PLATFORM_DOMAINS.items():
        if hostname == domain or hostname.endswith(f".{domain}"):
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

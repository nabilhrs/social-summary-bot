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

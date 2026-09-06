"""
Threads post extraction via Open Graph meta tags (PRD V2 2.1 revision).

Reading a page's own Open Graph meta tags via a normal HTTP fetch is the
same universal mechanism every link-preview feature on the web already
uses (Slack, iMessage, Discord, ...) — unlike the oEmbed API, whose terms
restrict use to rendering an embed, there's no equivalent restriction on
reading a page's own standard meta tags. Verified live: a post permalink's
raw, un-rendered HTML contains the full caption in og:description.

This only gets the linked post's own caption — Threads hydrates replies,
images, and video entirely via client-side JS after the page loads, so a
plain fetch never sees them. A multi-part thread ("(1/4)", "part 2 of 5")
is detected so the caller can warn the user rather than silently
summarizing one part as if it were the whole thing.
"""
import html as html_module
import logging
import re

import httpx

logger = logging.getLogger(__name__)

_TIMEOUT = 15.0
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; SocialSummaryBot/1.0)"}

_OG_DESCRIPTION_RE = re.compile(r'<meta[^>]+property="og:description"[^>]+content="([^"]*)"', re.IGNORECASE)
_OG_TITLE_RE = re.compile(r'<meta[^>]+property="og:title"[^>]+content="([^"]*)"', re.IGNORECASE)
_AUTHOR_FROM_TITLE_RE = re.compile(r"^(.*?)\s*\(@")

_THREAD_PART_RE = re.compile(
    r"(?:\(\s*\d{1,2}\s*/\s*\d{1,2}\s*\)|\b\d{1,2}\s*/\s*\d{1,2}\b|\bpart\s+\d{1,2}\s+of\s+\d{1,2}\b)",
    re.IGNORECASE,
)


def _extract_og_field(body: str, pattern: re.Pattern) -> str | None:
    match = pattern.search(body)
    if not match:
        return None
    return html_module.unescape(match.group(1)).strip() or None


def _extract_author(og_title: str | None) -> str | None:
    if not og_title:
        return None
    match = _AUTHOR_FROM_TITLE_RE.match(og_title)
    return match.group(1).strip() if match else None


def looks_like_partial_thread(text: str) -> bool:
    return bool(_THREAD_PART_RE.search(text))


async def fetch_and_extract(url: str) -> dict | None:
    try:
        async with httpx.AsyncClient(
            timeout=_TIMEOUT, follow_redirects=True, headers=_HEADERS
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("Fetch failed for %s: %s", url, exc)
        return None

    text = _extract_og_field(response.text, _OG_DESCRIPTION_RE)
    if not text:
        logger.warning("No og:description found for %s", url)
        return None

    author = _extract_author(_extract_og_field(response.text, _OG_TITLE_RE))

    return {
        "author": author,
        "text": text,
        "is_partial_thread": looks_like_partial_thread(text),
    }

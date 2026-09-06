"""
Threads post extraction via Open Graph meta tags (PRD V2 2.1 revision).

Reading a page's own Open Graph meta tags via a normal HTTP fetch is the
same universal mechanism every link-preview feature on the web already
uses (Slack, iMessage, Discord, ...) — unlike the oEmbed API, whose terms
restrict use to rendering an embed, there's no equivalent restriction on
reading a page's own standard meta tags. Verified live: a post permalink's
raw, un-rendered HTML contains the full caption in og:description.

This only gets the linked post's own caption. Threads hydrates everything
else — replies, images, video, and its own native multi-part "1/9"-style
thread badge — entirely via client-side JS/API calls that a plain fetch
never sees. An earlier version of this module tried to detect a multi-part
post by regex-matching numbering typed into the caption text (e.g. "(1/4)"),
but live testing showed Threads' native thread badge isn't part of the
caption at all — it's UI chrome computed client-side, with no equivalent
signal anywhere in the raw HTML (confirmed: no per-post reply/thread
metadata survives an unauthenticated fetch, only generic app config that
happens to share substrings like "reply_count"). Regex detection therefore
missed the common case and gave false confidence. The caller now discloses
the limitation unconditionally for every Threads extraction instead of
trying to detect it — see PARTIAL_THREAD_NOTE in app/bot/handlers.py.
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

    return {"author": author, "text": text}

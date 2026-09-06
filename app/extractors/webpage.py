"""
Web article extraction (PRD 5.2).

Fetch page HTML via httpx, extract main content via trafilatura. Any failure
(paywalled, JS-rendered, 404, timeout, no extractable content) returns None
so the caller can fall back to asking the user to paste the text instead.
"""
import json
import logging

import httpx
import trafilatura

logger = logging.getLogger(__name__)

_TIMEOUT = 15.0
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; SocialSummaryBot/1.0)"}
_MIN_TEXT_LENGTH = 50


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

    extracted_json = trafilatura.extract(
        response.text,
        output_format="json",
        with_metadata=True,
        include_comments=False,
        url=url,
    )
    if not extracted_json:
        logger.warning("Extraction failed for %s", url)
        return None

    data = json.loads(extracted_json)
    text = (data.get("text") or "").strip()
    if len(text) < _MIN_TEXT_LENGTH:
        logger.warning("Extracted text too short for %s (%d chars)", url, len(text))
        return None

    return {"title": data.get("title"), "author": data.get("author"), "text": text}

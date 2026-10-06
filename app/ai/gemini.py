"""
Every Gemini text-generation call in the bot goes through generate_text(),
which retries transient failures and falls back to lighter models.

Free-tier quota is counted per model, so falling back when the primary
model is exhausted (429) or overloaded (503 "high demand", seen live) keeps
the bot working instead of failing on the first error. A retired model
(404) also falls through to the next one instead of breaking the bot.
"""
import logging
import time

import httpx
from google import genai
from google.genai import errors, types

logger = logging.getLogger(__name__)

MODELS = ("gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite")

_ATTEMPTS_PER_MODEL = 2
_RETRY_DELAY_SECONDS = 2
_TRANSIENT_STATUS_CODES = {500, 502, 503, 504}

QUOTA_DAILY = "quota_daily"
QUOTA_RATE = "quota_rate"
INVALID_KEY = "invalid_key"
UNAVAILABLE = "unavailable"
FAILED = "failed"


class GeminiError(Exception):
    def __init__(self, kind: str):
        super().__init__(kind)
        self.kind = kind


def _is_invalid_key(exc: errors.APIError) -> bool:
    return exc.code in (401, 403) or (exc.code == 400 and "API key not valid" in str(exc))


def _pause_before_retry(attempt: int) -> None:
    if attempt + 1 < _ATTEMPTS_PER_MODEL:
        time.sleep(_RETRY_DELAY_SECONDS)


def _final_kind(failures: list[str]) -> str:
    if failures and all(kind in (QUOTA_DAILY, QUOTA_RATE) for kind in failures):
        return QUOTA_DAILY if QUOTA_DAILY in failures else QUOTA_RATE
    if UNAVAILABLE in failures:
        return UNAVAILABLE
    return FAILED


def generate_text(
    api_key: str, contents, timeout_seconds: float = 30, deadline_seconds: float = 90
) -> str:
    """Blocking — call via asyncio.to_thread. Returns the response text, or
    raises GeminiError whose `kind` says why every model failed."""
    client = genai.Client(
        api_key=api_key, http_options=types.HttpOptions(timeout=int(timeout_seconds * 1000))
    )
    started = time.monotonic()
    failures: list[str] = []

    for model in MODELS:
        for attempt in range(_ATTEMPTS_PER_MODEL):
            if time.monotonic() - started > deadline_seconds:
                logger.error("Gemini deadline of %ss exceeded", deadline_seconds)
                raise GeminiError(_final_kind(failures + [UNAVAILABLE]))
            try:
                response = client.models.generate_content(model=model, contents=contents)
            except errors.APIError as exc:
                if _is_invalid_key(exc):
                    logger.error("Gemini rejected the API key: %s", exc)
                    raise GeminiError(INVALID_KEY) from exc
                if exc.code == 429:
                    kind = QUOTA_DAILY if "PerDay" in str(exc) else QUOTA_RATE
                    logger.warning("%s quota exhausted (%s), trying next model", model, kind)
                    failures.append(kind)
                    break
                if exc.code == 404:
                    logger.error("%s not found (retired?), trying next model", model)
                    failures.append(FAILED)
                    break
                if exc.code in _TRANSIENT_STATUS_CODES:
                    logger.warning("%s returned %s (attempt %d)", model, exc.code, attempt + 1)
                    failures.append(UNAVAILABLE)
                    _pause_before_retry(attempt)
                    continue
                logger.exception("%s failed with a non-retryable error", model)
                raise GeminiError(FAILED) from exc
            except httpx.TransportError as exc:
                logger.warning("%s network error/timeout (attempt %d): %s", model, attempt + 1, exc)
                failures.append(UNAVAILABLE)
                _pause_before_retry(attempt)
                continue

            text = (response.text or "").strip()
            if text:
                if model != MODELS[0]:
                    logger.info("Served by fallback model %s", model)
                return text
            logger.warning("%s returned an empty response, trying next model", model)
            failures.append(FAILED)
            break

    raise GeminiError(_final_kind(failures))

"""
Every Gemini text-generation call in the bot goes through generate_text(),
which retries transient failures and falls back to lighter models.

Free-tier quota is counted per model, so falling back when the primary
model is exhausted (429) or overloaded (503 "high demand", seen live) keeps
the bot working instead of failing on the first error. A retired model
(404) also falls through to the next one instead of breaking the bot.
"""
import io
import logging
import time

import httpx
from google import genai
from google.genai import errors, types

logger = logging.getLogger(__name__)

MODELS = ("gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite")

_MAX_UPLOAD_POLL_SECONDS = 120
_ATTEMPTS_PER_MODEL = 2
_RETRY_DELAY_SECONDS = 2
# Fast "busy" answers are worth one retry on the same model. A 504 or a
# timeout only arrives after the full wait (often ~90 s, seen live), so
# retrying that model would use up the deadline before any fallback runs.
_FAST_BUSY_CODES = {500, 502, 503}
_SLOW_BUSY_CODES = {504}
# If every model was busy, pause and go round once more while time remains.
_ROUNDS = 2
_ROUND_PAUSE_SECONDS = 20
_MIN_ATTEMPT_SECONDS = 15

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


def _pause_before_retry(attempt: int, attempts: int) -> None:
    if attempt + 1 < attempts:
        time.sleep(_RETRY_DELAY_SECONDS)


def _final_kind(failures: list[str]) -> str:
    if failures and all(kind in (QUOTA_DAILY, QUOTA_RATE) for kind in failures):
        return QUOTA_DAILY if QUOTA_DAILY in failures else QUOTA_RATE
    if UNAVAILABLE in failures:
        return UNAVAILABLE
    return FAILED


def generate_text(
    api_key: str,
    contents,
    timeout_seconds: float = 30,
    deadline_seconds: float = 120,
    config: types.GenerateContentConfig | None = None,
) -> str:
    """Blocking — call via asyncio.to_thread. Returns the response text, or
    raises GeminiError whose `kind` says why every model failed."""
    client = genai.Client(
        api_key=api_key, http_options=types.HttpOptions(timeout=int(timeout_seconds * 1000))
    )
    started = time.monotonic()
    failures: list[str] = []
    # Out of quota, retired or empty: not worth another round.
    done_with: set[str] = set()

    for round_index in range(_ROUNDS):
        if round_index:
            elapsed = time.monotonic() - started
            if UNAVAILABLE not in failures or elapsed + _ROUND_PAUSE_SECONDS + _MIN_ATTEMPT_SECONDS > deadline_seconds:
                break
            logger.warning("Every Gemini model was busy; trying again in %ss", _ROUND_PAUSE_SECONDS)
            time.sleep(_ROUND_PAUSE_SECONDS)
        attempts = _ATTEMPTS_PER_MODEL if round_index == 0 else 1
        for model in MODELS:
            if model in done_with:
                continue
            for attempt in range(attempts):
                if time.monotonic() - started > deadline_seconds:
                    logger.error("Gemini deadline of %ss exceeded", deadline_seconds)
                    raise GeminiError(_final_kind(failures + [UNAVAILABLE]))
                try:
                    response = client.models.generate_content(model=model, contents=contents, config=config)
                except errors.APIError as exc:
                    if _is_invalid_key(exc):
                        logger.error("Gemini rejected the API key: %s", exc)
                        raise GeminiError(INVALID_KEY) from exc
                    if exc.code == 429:
                        kind = QUOTA_DAILY if "PerDay" in str(exc) else QUOTA_RATE
                        logger.warning("%s quota exhausted (%s), trying next model", model, kind)
                        failures.append(kind)
                        done_with.add(model)
                        break
                    if exc.code == 404:
                        logger.error("%s not found (retired?), trying next model", model)
                        failures.append(FAILED)
                        done_with.add(model)
                        break
                    if exc.code in _FAST_BUSY_CODES:
                        logger.warning("%s returned %s (attempt %d)", model, exc.code, attempt + 1)
                        failures.append(UNAVAILABLE)
                        _pause_before_retry(attempt, attempts)
                        continue
                    if exc.code in _SLOW_BUSY_CODES:
                        logger.warning("%s returned %s; moving to the next model", model, exc.code)
                        failures.append(UNAVAILABLE)
                        break
                    logger.exception("%s failed with a non-retryable error", model)
                    raise GeminiError(FAILED) from exc
                except httpx.TimeoutException as exc:
                    logger.warning("%s timed out; moving to the next model: %s", model, exc)
                    failures.append(UNAVAILABLE)
                    break
                except httpx.TransportError as exc:
                    logger.warning("%s network error (attempt %d): %s", model, attempt + 1, exc)
                    failures.append(UNAVAILABLE)
                    _pause_before_retry(attempt, attempts)
                    continue

                text = (response.text or "").strip()
                if text:
                    if model != MODELS[0]:
                        logger.info("Served by fallback model %s", model)
                    return text
                logger.warning("%s returned an empty response, trying next model", model)
                failures.append(FAILED)
                done_with.add(model)
                break

    raise GeminiError(_final_kind(failures))


TEXT_ITEM = "text/plain"
# Images up to this size travel inside the request; anything bigger, and all
# video, audio and PDFs, go through the Files API.
_MAX_INLINE_IMAGE_BYTES = 4 * 1024 * 1024


def _upload(client, data, mime_type: str | None):
    try:
        return client.files.upload(file=data, config=types.UploadFileConfig(mime_type=mime_type))
    except errors.APIError as exc:
        logger.error("Gemini file upload failed: %s", exc)
        if _is_invalid_key(exc):
            raise GeminiError(INVALID_KEY) from exc
        raise GeminiError(QUOTA_RATE if exc.code == 429 else UNAVAILABLE) from exc
    except httpx.TransportError as exc:
        logger.error("Gemini file upload network error: %s", exc)
        raise GeminiError(UNAVAILABLE) from exc


def _wait_until_active(client, uploaded):
    waited = 0
    while uploaded.state.name == "PROCESSING" and waited < _MAX_UPLOAD_POLL_SECONDS:
        time.sleep(1)
        waited += 1
        uploaded = client.files.get(name=uploaded.name)
    if uploaded.state.name != "ACTIVE":
        logger.error("Uploaded file never became active (state=%s)", uploaded.state)
        raise GeminiError(FAILED)
    return uploaded


def describe_many(
    api_key: str,
    items: list[tuple],
    prompt: str,
    timeout_seconds: float = 60,
    deadline_seconds: float = 100,
) -> str:
    """Blocking. Asks `prompt` about several items in one request, in order.
    Each item is (data, mime_type): data is bytes, a file path or a binary
    stream, or a string with mime_type TEXT_ITEM. Uploads are always deleted
    afterward. Raises GeminiError on failure."""
    client = genai.Client(api_key=api_key)
    uploads, contents = [], []
    try:
        for data, mime_type in items:
            if mime_type == TEXT_ITEM:
                contents.append(data)
            elif isinstance(data, bytes) and (mime_type or "").startswith("image/") and len(data) <= _MAX_INLINE_IMAGE_BYTES:
                contents.append(types.Part.from_bytes(data=data, mime_type=mime_type))
            else:
                uploaded = _upload(client, io.BytesIO(data) if isinstance(data, bytes) else data, mime_type)
                uploads.append(uploaded)
                contents.append(uploaded)
        contents = [_wait_until_active(client, c) if c in uploads else c for c in contents]
        return generate_text(api_key, [*contents, prompt], timeout_seconds, deadline_seconds)
    finally:
        for uploaded in uploads:
            try:
                client.files.delete(name=uploaded.name)
            except Exception:
                logger.warning("Failed to delete uploaded Gemini file %s", uploaded.name)


def describe_file(
    api_key: str,
    file,
    prompt: str,
    mime_type: str | None = None,
    timeout_seconds: float = 60,
    deadline_seconds: float = 100,
) -> str:
    """Blocking. One file (path or binary stream) through the Files API; see describe_many."""
    return describe_many(api_key, [(file, mime_type)], prompt, timeout_seconds, deadline_seconds)

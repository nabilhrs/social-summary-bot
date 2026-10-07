"""
Files sent directly in Telegram — photos, voice notes, audio, video, PDFs and
plain-text documents — turned into text that the normal summarize pipeline
can use. The extracted text is what gets saved as original_text, so /search
and /ask can find a voice note or screenshot by what it said.
"""
import io
from dataclasses import dataclass

from app.ai.gemini import describe_file

# Telegram's Bot API only lets bots download files up to 20 MB.
MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024

IMAGE, AUDIO, VIDEO, PDF, TEXT = "image", "audio", "video", "pdf", "text"

PROMPTS = {
    IMAGE: (
        "Transcribe all text visible in this image exactly, in reading order. "
        "Then briefly describe anything else needed to understand it (what kind "
        "of image it is, charts, products, people, context). If there's no text, "
        "just describe the image."
    ),
    AUDIO: (
        "Transcribe the speech in this audio verbatim, in its original language. "
        "If there's no speech, describe what the audio contains."
    ),
    VIDEO: (
        "Describe what actually happens in this video — visuals, actions, and "
        "any spoken or sung content — in enough detail for someone who hasn't "
        "watched it to understand what it's about."
    ),
    PDF: (
        "Extract the full text of this document in reading order, keeping "
        "headings and lists. Skip page numbers and repeated headers/footers."
    ),
}

_EXTRACT_TIMEOUT_SECONDS = 90
_EXTRACT_DEADLINE_SECONDS = 150


@dataclass
class MediaInfo:
    kind: str
    source: str
    mime_type: str
    file_size: int | None
    file_name: str | None = None


def classify_document(mime_type: str | None) -> str | None:
    mime_type = (mime_type or "").lower()
    if mime_type == "application/pdf":
        return PDF
    if mime_type.startswith("text/"):
        return TEXT
    for prefix, kind in (("image/", IMAGE), ("audio/", AUDIO), ("video/", VIDEO)):
        if mime_type.startswith(prefix):
            return kind
    return None


def extract_text(api_key: str, data: bytes, info: MediaInfo) -> str:
    """Blocking — call via asyncio.to_thread. Raises GeminiError."""
    if info.kind == TEXT:
        return data.decode("utf-8", errors="replace").strip()
    return describe_file(
        api_key,
        io.BytesIO(data),
        PROMPTS[info.kind],
        mime_type=info.mime_type,
        timeout_seconds=_EXTRACT_TIMEOUT_SECONDS,
        deadline_seconds=_EXTRACT_DEADLINE_SECONDS,
    )


def build_text(extracted: str, caption: str | None) -> str:
    if caption:
        return f"Note from the sender: {caption.strip()}\n\n{extracted}"
    return extracted

from types import SimpleNamespace

import pytest

from app.bot.handlers import _media_info
from app.extractors.media import (
    AUDIO,
    IMAGE,
    PDF,
    TEXT,
    VIDEO,
    MediaInfo,
    build_text,
    classify_document,
    extract_text,
)


@pytest.mark.parametrize(
    "mime_type, expected",
    [
        ("application/pdf", PDF),
        ("text/plain", TEXT),
        ("text/markdown", TEXT),
        ("image/png", IMAGE),
        ("audio/mpeg", AUDIO),
        ("video/quicktime", VIDEO),
        ("APPLICATION/PDF", PDF),
        ("application/zip", None),
        ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", None),
        (None, None),
    ],
)
def test_classify_document(mime_type, expected):
    assert classify_document(mime_type) == expected


def test_build_text_puts_caption_first():
    assert build_text("transcript", "  save this recipe ") == "Note from the sender: save this recipe\n\ntranscript"


def test_build_text_without_caption():
    assert build_text("transcript", None) == "transcript"


def test_extract_text_decodes_text_files_without_gemini():
    info = MediaInfo(TEXT, "document", "text/plain", 10)
    assert extract_text("unused-key", "  héllo\n".encode("utf-8"), info) == "héllo"


def _message(**media):
    fields = dict(photo=None, voice=None, audio=None, video=None, video_note=None, document=None)
    fields.update(media)
    return SimpleNamespace(**fields)


def test_media_info_uses_largest_photo():
    small = SimpleNamespace(file_size=100)
    large = SimpleNamespace(file_size=900)
    file_obj, info = _media_info(_message(photo=[small, large]))
    assert file_obj is large
    assert (info.kind, info.source, info.mime_type) == (IMAGE, "photo", "image/jpeg")


def test_media_info_voice_note():
    voice = SimpleNamespace(mime_type="audio/ogg", file_size=5000)
    _, info = _media_info(_message(voice=voice))
    assert (info.kind, info.source, info.mime_type) == (AUDIO, "voice", "audio/ogg")


def test_media_info_pdf_document_keeps_file_name():
    document = SimpleNamespace(mime_type="application/pdf", file_size=1000, file_name="report.pdf")
    _, info = _media_info(_message(document=document))
    assert (info.kind, info.source, info.file_name) == (PDF, "pdf", "report.pdf")


def test_media_info_unsupported_document():
    document = SimpleNamespace(mime_type="application/zip", file_size=1000, file_name="a.zip")
    assert _media_info(_message(document=document)) == (None, None)

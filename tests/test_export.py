import json

from app.bot.export import build_json, build_markdown

ITEM = {
    "id": 3,
    "user_id": 111,
    "created_at": "2026-10-01T08:00:00+00:00",
    "source": "web",
    "url": "https://example.com/a",
    "title": "Café review",
    "author": "Ana",
    "summary": "TL;DR: good coffee.",
    "original_text": "Long original text.",
    "merged_from": "1,2",
    "previous_summary": "TL;DR: older.",
}


def test_build_json_round_trips_every_field_except_user_id():
    rows = json.loads(build_json([ITEM]).decode("utf-8"))
    assert rows == [{key: value for key, value in ITEM.items() if key != "user_id"}]


def test_build_json_keeps_non_ascii_readable():
    assert "Café" in build_json([ITEM]).decode("utf-8")


def test_build_markdown_includes_metadata_summary_and_original():
    text = build_markdown([ITEM], "2026-10-07").decode("utf-8")
    assert text.startswith("# Saved notes — exported 2026-10-07")
    assert "1 item(s)" in text
    assert "## #3 — Café review" in text
    assert "_2026-10-01 · web · Ana_" in text
    assert "<https://example.com/a>" in text
    assert "Merged from: #1, #2" in text
    assert "TL;DR: good coffee." in text
    assert "Long original text." in text


def test_build_markdown_handles_untitled_minimal_item():
    item = {**ITEM, "title": None, "author": None, "url": None, "merged_from": None}
    text = build_markdown([item], "2026-10-07").decode("utf-8")
    assert "## #3 — Untitled" in text
    assert "_2026-10-01 · web_" in text
    assert "Merged from" not in text

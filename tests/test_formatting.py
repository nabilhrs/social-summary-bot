from app.bot.formatting import format_full_item


def test_format_full_item_basic():
    item = {
        "id": 3,
        "title": "My Title",
        "source": "web",
        "url": "https://example.com/a",
        "created_at": "2026-09-06T12:00:00+00:00",
        "merged_from": None,
        "summary": "TL;DR: something.",
    }
    text = format_full_item(item)
    assert text.startswith("#3 — My Title\n")
    assert "Saved: 2026-09-06 · Source: web" in text
    assert "URL: https://example.com/a" in text
    assert "Merged from" not in text
    assert text.endswith("TL;DR: something.")


def test_format_full_item_untitled_no_url():
    item = {
        "id": 1,
        "title": None,
        "source": "pasted_text",
        "url": None,
        "created_at": "2026-09-06T12:00:00+00:00",
        "merged_from": None,
        "summary": "TL;DR: something.",
    }
    text = format_full_item(item)
    assert text.startswith("#1 — Untitled\n")
    assert "URL:" not in text


def test_format_full_item_shows_merged_from():
    item = {
        "id": 1,
        "title": "Title",
        "source": "pasted_text",
        "url": None,
        "created_at": "2026-09-06T12:00:00+00:00",
        "merged_from": "2,3",
        "summary": "TL;DR: merged.",
    }
    text = format_full_item(item)
    assert "Merged from: #2, #3" in text

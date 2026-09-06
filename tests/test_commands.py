from app.bot.commands import _display_title, _format_item_line, _format_item_list


def test_display_title_uses_title_when_present():
    item = {"title": "My Article", "original_text": "irrelevant body"}
    assert _display_title(item) == "My Article"


def test_display_title_falls_back_to_first_line_of_text():
    item = {"title": None, "original_text": "First line here.\nSecond line."}
    assert _display_title(item) == "First line here."


def test_display_title_truncates_long_preview():
    long_line = "x" * 100
    item = {"title": None, "original_text": long_line}
    result = _display_title(item)
    assert result.endswith("…")
    assert len(result) == 61  # 60 chars + ellipsis


def test_format_item_line_includes_id_title_and_date():
    item = {"id": 5, "title": "Some Title", "original_text": "x", "created_at": "2026-09-06T12:00:00+00:00"}
    line = _format_item_line(item)
    assert line == "#5 — Some Title (2026-09-06)"


def test_format_item_list_includes_header_and_all_items():
    items = [
        {"id": 2, "title": "Second", "original_text": "x", "created_at": "2026-09-06T00:00:00+00:00"},
        {"id": 1, "title": "First", "original_text": "x", "created_at": "2026-09-05T00:00:00+00:00"},
    ]
    text = _format_item_list(items, "Header:")
    assert text.startswith("Header:\n")
    assert "#2 — Second (2026-09-06)" in text
    assert "#1 — First (2026-09-05)" in text


def test_format_item_list_truncates_when_too_long():
    items = [
        {"id": i, "title": f"Item {i}" * 20, "original_text": "x", "created_at": "2026-09-06T00:00:00+00:00"}
        for i in range(200)
    ]
    text = _format_item_list(items, "Header:")
    assert len(text) < 3700
    assert "truncated" in text

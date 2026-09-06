from app.ai.prompts import build_summary_prompt, build_merge_prompt

_LONG_TEXT = " ".join(["word"] * 100)  # 100 words, over the 80-word short-content threshold
_SHORT_TEXT = "Quick tip: always research the company first."  # well under 80 words


def test_prompt_includes_title_and_content():
    content = {"title": "My Article", "author": None, "text": _LONG_TEXT}
    prompt = build_summary_prompt(content)
    assert "My Article" in prompt
    assert _LONG_TEXT in prompt
    assert "TL;DR" in prompt
    assert "KEY POINTS" in prompt
    assert "TAKEAWAY" in prompt


def test_prompt_includes_author_when_present():
    content = {"title": "My Article", "author": "Jane Doe", "text": _LONG_TEXT}
    prompt = build_summary_prompt(content)
    assert "Author: Jane Doe" in prompt


def test_prompt_omits_author_line_when_missing():
    content = {"title": "My Article", "author": None, "text": _LONG_TEXT}
    prompt = build_summary_prompt(content)
    assert "Author:" not in prompt


def test_prompt_falls_back_to_untitled():
    content = {"title": None, "author": None, "text": _LONG_TEXT}
    prompt = build_summary_prompt(content)
    assert "Title: Untitled" in prompt


def test_prompt_asks_for_related_id():
    content = {"title": "My Article", "author": None, "text": _LONG_TEXT}
    prompt = build_summary_prompt(content)
    assert "RELATED_ID" in prompt
    assert "(none saved yet)" in prompt


def test_prompt_lists_recent_items():
    content = {"title": "My Article", "author": None, "text": _LONG_TEXT}
    recent_items = [
        {"id": 5, "title": "Old Article", "summary": "TL;DR: old stuff"},
        {"id": 3, "title": None, "summary": "TL;DR: other stuff"},
    ]
    prompt = build_summary_prompt(content, recent_items)
    assert "#5 — Old Article" in prompt
    assert "TL;DR: old stuff" in prompt
    assert "#3 — Untitled" in prompt


def test_merge_prompt_includes_both_sources():
    prompt = build_merge_prompt(_LONG_TEXT, _LONG_TEXT, "Old Title", "New Title")
    assert "Old Title" in prompt
    assert "New Title" in prompt
    assert prompt.count(_LONG_TEXT) == 2
    assert "TL;DR" in prompt


# PRD V2 2.4 — short informal notes get a compact format instead of the full
# TL;DR/KEY POINTS/TAKEAWAY structure.


def test_prompt_uses_compact_format_for_short_content():
    content = {"title": "A tip", "author": None, "text": _SHORT_TEXT}
    prompt = build_summary_prompt(content)
    assert "SUMMARY:" in prompt
    assert "TL;DR" not in prompt
    assert "KEY POINTS" not in prompt
    assert "informal note" in prompt


def test_prompt_uses_full_format_for_long_content():
    content = {"title": "An article", "author": None, "text": _LONG_TEXT}
    prompt = build_summary_prompt(content)
    assert "TL;DR" in prompt
    assert "SUMMARY:" not in prompt


def test_prompt_short_content_still_asks_for_related_id():
    content = {"title": "A tip", "author": None, "text": _SHORT_TEXT}
    prompt = build_summary_prompt(content)
    assert "RELATED_ID" in prompt


def test_merge_prompt_uses_compact_format_when_both_sources_short():
    prompt = build_merge_prompt(_SHORT_TEXT, _SHORT_TEXT, "Old", "New")
    assert "SUMMARY:" in prompt
    assert "TL;DR" not in prompt


def test_merge_prompt_uses_full_format_when_either_source_is_long():
    prompt = build_merge_prompt(_SHORT_TEXT, _LONG_TEXT, "Old", "New")
    assert "TL;DR" in prompt
    assert "SUMMARY:" not in prompt

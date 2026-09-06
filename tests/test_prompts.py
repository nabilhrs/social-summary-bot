from app.ai.prompts import build_summary_prompt, build_merge_prompt


def test_prompt_includes_title_and_content():
    content = {"title": "My Article", "author": None, "text": "Some article body."}
    prompt = build_summary_prompt(content)
    assert "My Article" in prompt
    assert "Some article body." in prompt
    assert "TL;DR" in prompt
    assert "KEY POINTS" in prompt
    assert "TAKEAWAY" in prompt


def test_prompt_includes_author_when_present():
    content = {"title": "My Article", "author": "Jane Doe", "text": "body"}
    prompt = build_summary_prompt(content)
    assert "Author: Jane Doe" in prompt


def test_prompt_omits_author_line_when_missing():
    content = {"title": "My Article", "author": None, "text": "body"}
    prompt = build_summary_prompt(content)
    assert "Author:" not in prompt


def test_prompt_falls_back_to_untitled():
    content = {"title": None, "author": None, "text": "body"}
    prompt = build_summary_prompt(content)
    assert "Title: Untitled" in prompt


def test_prompt_asks_for_related_id():
    content = {"title": "My Article", "author": None, "text": "body"}
    prompt = build_summary_prompt(content)
    assert "RELATED_ID" in prompt
    assert "(none saved yet)" in prompt


def test_prompt_lists_recent_items():
    content = {"title": "My Article", "author": None, "text": "body"}
    recent_items = [
        {"id": 5, "title": "Old Article", "summary": "TL;DR: old stuff"},
        {"id": 3, "title": None, "summary": "TL;DR: other stuff"},
    ]
    prompt = build_summary_prompt(content, recent_items)
    assert "#5 — Old Article" in prompt
    assert "TL;DR: old stuff" in prompt
    assert "#3 — Untitled" in prompt


def test_merge_prompt_includes_both_sources():
    prompt = build_merge_prompt("old body", "new body", "Old Title", "New Title")
    assert "Old Title" in prompt
    assert "old body" in prompt
    assert "New Title" in prompt
    assert "new body" in prompt
    assert "TL;DR" in prompt

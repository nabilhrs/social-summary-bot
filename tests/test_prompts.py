from app.ai.prompts import build_summary_prompt


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

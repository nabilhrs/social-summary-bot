from app.ai import summarizer
from app.ai.prompts import build_ask_prompt
from app.ai.summarizer import (
    _extract_tags,
    _parse_json_array,
    _parse_related_id,
    clean_category,
    clean_title,
    select_ask_context,
)


def _note(item_id, summary, original_text="", title=None):
    return {
        "id": item_id,
        "title": title,
        "summary": summary,
        "original_text": original_text,
        "created_at": "2026-10-01T00:00:00+00:00",
    }


def test_select_ask_context_includes_all_summaries_within_budget():
    items = [_note(i, f"summary {i}") for i in range(3, 0, -1)]
    budgeted, _ = select_ask_context("anything", items)
    assert [item["id"] for item in budgeted] == [3, 2, 1]


def test_select_ask_context_drops_oldest_summaries_over_budget(monkeypatch):
    monkeypatch.setattr(summarizer, "_ASK_SUMMARY_CHAR_BUDGET", 300)  # 150 per item
    items = [_note(i, "x" * 50) for i in range(5, 0, -1)]
    budgeted, _ = select_ask_context("anything", items)
    assert [item["id"] for item in budgeted] == [5, 4]


def test_select_ask_context_details_best_keyword_matches_from_original_text():
    items = [
        _note(3, "Cooking", "Boil pasta for ten minutes"),
        _note(2, "Career", "Behavioral interview answers should follow STAR structure"),
        _note(1, "Gardening", "Water tomatoes"),
    ]
    _, detailed = select_ask_context("how should I structure behavioral interview answers?", items)
    assert [item["id"] for item in detailed] == [2]


def test_select_ask_context_truncates_detailed_original_text(monkeypatch):
    monkeypatch.setattr(summarizer, "_ASK_DETAIL_CHARS", 10)
    items = [_note(1, "interview tips", "interview " * 50)]
    _, detailed = select_ask_context("interview", items)
    assert len(detailed[0]["original_text"]) == 10
    assert len(items[0]["original_text"]) == 500


def test_build_ask_prompt_contains_question_ids_and_details():
    items = [_note(4, "STAR method summary", title="Interview tips")]
    detailed = [{**items[0], "original_text": "full original text here"}]
    prompt = build_ask_prompt("What is STAR?", items, detailed)
    assert "Question: What is STAR?" in prompt
    assert "#4 (2026-10-01) — Interview tips" in prompt
    assert "--- Full text of #4 ---\nfull original text here" in prompt
    assert "(#12)" in prompt


def test_build_ask_prompt_without_detailed_items():
    prompt = build_ask_prompt("q", [_note(1, "s")], [])
    assert "Full text of the notes most likely to be relevant:\n(none)" in prompt


FULL_RESPONSE = (
    "TL;DR: something.\nKEY POINTS:\n- a\nTAKEAWAY: b\n"
    "RELATED_ID: 7\nTITLE: STAR Method Interview Tips\nCATEGORY: Career"
)


def test_extract_tags_splits_display_text_and_tags():
    cleaned, tags = _extract_tags(FULL_RESPONSE)
    assert cleaned == "TL;DR: something.\nKEY POINTS:\n- a\nTAKEAWAY: b"
    assert tags == {"RELATED_ID": "7", "TITLE": "STAR Method Interview Tips", "CATEGORY": "Career"}


def test_extract_tags_tolerates_markdown_and_case():
    cleaned, tags = _extract_tags("SUMMARY: hi\n**related_id:** #12\n**Title:** *My Note*\n- Category: Food")
    assert cleaned == "SUMMARY: hi"
    assert tags == {"RELATED_ID": "#12", "TITLE": "My Note", "CATEGORY": "Food"}


def test_extract_tags_without_tags_returns_text_unchanged():
    text = "TL;DR: something.\nKEY POINTS:\n- a\nTAKEAWAY: b"
    assert _extract_tags(text) == (text, {})


def test_extract_tags_first_occurrence_wins():
    _, tags = _extract_tags("x\nTITLE: First\nTITLE: Second")
    assert tags["TITLE"] == "First"


def test_extract_tags_leaves_tag_like_lines_inside_content():
    text = "KEY POINTS:\n- Title: The Godfather\n- Category: drama\nTAKEAWAY: watch it\n\nRELATED_ID: NONE\nTITLE: Film Notes"
    cleaned, tags = _extract_tags(text)
    assert "- Title: The Godfather" in cleaned
    assert "- Category: drama" in cleaned
    assert tags == {"RELATED_ID": "NONE", "TITLE": "Film Notes"}


def test_extract_tags_skips_separator_lines_in_trailing_block():
    cleaned, tags = _extract_tags("SUMMARY: hi\n---\nRELATED_ID: 3\n\nCATEGORY: Food")
    assert cleaned == "SUMMARY: hi"
    assert tags == {"RELATED_ID": "3", "CATEGORY": "Food"}


def test_parse_related_id():
    assert _parse_related_id("7") == 7
    assert _parse_related_id("#1") == 1
    assert _parse_related_id("NONE") is None
    assert _parse_related_id(None) is None


def test_clean_title_strips_quotes_and_whitespace_and_caps_length():
    assert clean_title('  "Interview   Tips"  ') == "Interview Tips"
    assert clean_title("") is None
    assert clean_title(None) is None
    assert len(clean_title("word " * 40)) <= 80


def test_clean_category_reuses_existing_spelling():
    assert clean_category("career", ["Career", "Food"]) == "Career"
    assert clean_category("FOOD & DRINK", ["Food & Drink"]) == "Food & Drink"


def test_clean_category_new_name_is_capitalized_and_trimmed():
    assert clean_category(" personal finance. ", []) == "Personal finance"
    assert clean_category("<Travel>", []) == "Travel"
    assert clean_category("   ", []) is None
    assert len(clean_category("x" * 100, [])) == 30


def test_parse_json_array_handles_code_fences_and_preamble():
    assert _parse_json_array('```json\n[{"id": 1}]\n```') == [{"id": 1}]
    assert _parse_json_array('Here you go: [{"id": 2}] done') == [{"id": 2}]

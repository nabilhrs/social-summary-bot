from app.ai import summarizer
from app.ai.prompts import build_ask_prompt
from app.ai.summarizer import _extract_related_id, select_ask_context


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


def test_extract_related_id_none():
    text = "TL;DR: something.\nKEY POINTS:\n- a\nTAKEAWAY: b\nRELATED_ID: NONE"
    cleaned, related_id = _extract_related_id(text)
    assert related_id is None
    assert "RELATED_ID" not in cleaned
    assert "TAKEAWAY: b" in cleaned


def test_extract_related_id_with_match():
    text = "TL;DR: something.\nKEY POINTS:\n- a\nTAKEAWAY: b\nRELATED_ID: 7"
    cleaned, related_id = _extract_related_id(text)
    assert related_id == 7
    assert "RELATED_ID" not in cleaned


def test_extract_related_id_case_insensitive_and_markdown():
    text = "TL;DR: something.\n**related_id:** 12"
    cleaned, related_id = _extract_related_id(text)
    assert related_id == 12
    assert "related_id" not in cleaned.lower()


def test_extract_related_id_with_hash_prefix():
    text = "TL;DR: something.\nRELATED_ID: #1"
    cleaned, related_id = _extract_related_id(text)
    assert related_id == 1
    assert "RELATED_ID" not in cleaned


def test_extract_related_id_missing_line():
    text = "TL;DR: something.\nKEY POINTS:\n- a\nTAKEAWAY: b"
    cleaned, related_id = _extract_related_id(text)
    assert related_id is None
    assert cleaned == text

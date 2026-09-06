from app.ai.summarizer import _extract_related_id


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

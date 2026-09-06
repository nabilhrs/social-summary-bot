from app.extractors.tiktok import _build_text


def test_build_text_with_caption():
    result = _build_text("A person dances in a kitchen.", "check this out!!")
    assert result == "A person dances in a kitchen.\n\nCaption: check this out!!"


def test_build_text_without_caption():
    result = _build_text("A person dances in a kitchen.", None)
    assert result == "A person dances in a kitchen."


def test_build_text_empty_caption_treated_as_none():
    result = _build_text("A person dances in a kitchen.", "")
    assert result == "A person dances in a kitchen."

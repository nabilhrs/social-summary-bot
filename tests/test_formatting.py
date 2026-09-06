from app.bot.formatting import format_full_item, build_merge_keyboard


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


def test_build_merge_keyboard_has_three_buttons_with_correct_callback_data():
    keyboard = build_merge_keyboard(existing_id=1, new_id=5)
    buttons = [button for row in keyboard.inline_keyboard for button in row]

    assert len(buttons) == 3
    callback_data = {button.callback_data for button in buttons}
    assert callback_data == {"merge:yes:1:5", "merge:no:1:5", "merge:view:1:5"}


def test_build_merge_keyboard_view_button_mentions_existing_id():
    keyboard = build_merge_keyboard(existing_id=7, new_id=9)
    view_button = next(
        button for row in keyboard.inline_keyboard for button in row if button.callback_data == "merge:view:7:9"
    )
    assert "#7" in view_button.text

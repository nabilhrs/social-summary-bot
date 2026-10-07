from app.bot.formatting import (
    build_delete_keyboard,
    build_list_delete_keyboard,
    build_merge_keyboard,
    format_full_item,
    render_summary_html,
)


def test_render_full_structure_bolds_labels_and_converts_bullets():
    text = "TL;DR: Short.\nKEY POINTS:\n- one\n- two\nTAKEAWAY: Do it."
    assert render_summary_html(text) == (
        "<b>TL;DR:</b> Short.\n\n<b>KEY POINTS:</b>\n• one\n• two\n\n<b>TAKEAWAY:</b> Do it."
    )


def test_render_strips_compact_summary_label():
    assert render_summary_html("SUMMARY: Just one point.") == "Just one point."
    assert render_summary_html("**SUMMARY:** Bolded label.") == "Bolded label."


def test_render_escapes_html_in_content():
    rendered = render_summary_html("SUMMARY: use <b>tags</b> & a < b")
    assert rendered == "use &lt;b&gt;tags&lt;/b&gt; &amp; a &lt; b"


def test_render_converts_markdown_bold_without_double_bolding_labels():
    rendered = render_summary_html("**TL;DR:** The **key** idea.")
    assert rendered == "<b>TL;DR:</b> The <b>key</b> idea."


def test_render_leaves_lone_asterisks_alone():
    assert render_summary_html("SUMMARY: 5 * 3 = 15") == "5 * 3 = 15"
    assert render_summary_html("SUMMARY: a*b and c*d") == "a*b and c*d"


def test_render_converts_single_asterisk_italics():
    rendered = render_summary_html("- Read the *job description* and **prepare**")
    assert rendered == "• Read the <i>job description</i> and <b>prepare</b>"


def test_render_star_bullets_are_not_italicized():
    assert render_summary_html("* one\n* two") == "• one\n• two"


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
    assert text.startswith("<b>#3 — My Title</b>\n")
    assert "Saved: 2026-09-06 · Source: web" in text
    assert "URL: https://example.com/a" in text
    assert "Merged from" not in text
    assert text.endswith("<b>TL;DR:</b> something.")


def test_format_full_item_escapes_title_and_url():
    item = {
        "id": 4,
        "title": "Q&A <live>",
        "source": "web",
        "url": "https://example.com/?a=1&b=2",
        "created_at": "2026-09-06T12:00:00+00:00",
        "merged_from": None,
        "summary": "SUMMARY: ok",
    }
    text = format_full_item(item)
    assert "Q&amp;A &lt;live&gt;" in text
    assert "a=1&amp;b=2" in text


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
    assert text.startswith("<b>#1 — Untitled</b>\n")
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


def test_build_delete_keyboard_has_yes_no_buttons():
    keyboard = build_delete_keyboard(item_id=5)
    buttons = [button for row in keyboard.inline_keyboard for button in row]

    assert len(buttons) == 2
    callback_data = {button.callback_data for button in buttons}
    assert callback_data == {"delete:yes:5", "delete:no:5"}


def test_build_list_delete_keyboard_one_button_per_item():
    items = [{"id": 1}, {"id": 2}, {"id": 3}]
    keyboard = build_list_delete_keyboard(items)
    buttons = [button for row in keyboard.inline_keyboard for button in row]

    callback_data = {button.callback_data for button in buttons}
    assert callback_data == {"delconfirm:1", "delconfirm:2", "delconfirm:3"}


def test_build_list_delete_keyboard_chunks_into_rows_of_five():
    items = [{"id": i} for i in range(1, 8)]  # 7 items
    keyboard = build_list_delete_keyboard(items)

    assert len(keyboard.inline_keyboard) == 2
    assert len(keyboard.inline_keyboard[0]) == 5
    assert len(keyboard.inline_keyboard[1]) == 2


def test_build_list_delete_keyboard_empty_items():
    keyboard = build_list_delete_keyboard([])
    assert len(keyboard.inline_keyboard) == 0

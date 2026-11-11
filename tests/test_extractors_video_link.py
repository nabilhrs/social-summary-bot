from app.extractors.video_link import LOGIN_REQUIRED, NO_VIDEO, _build_text, classify_download_error


def test_build_text_with_caption():
    result = _build_text("A person dances in a kitchen.", "check this out!!")
    assert result == "A person dances in a kitchen.\n\nCaption: check this out!!"


def test_build_text_without_caption():
    result = _build_text("A person dances in a kitchen.", None)
    assert result == "A person dances in a kitchen."


def test_build_text_empty_caption_treated_as_none():
    result = _build_text("A person dances in a kitchen.", "")
    assert result == "A person dances in a kitchen."


def test_classify_photo_only_instagram_post():
    assert classify_download_error("ERROR: [Instagram] abc: There is no video in this post") == NO_VIDEO


def test_classify_instagram_login_walls():
    messages = [
        "ERROR: [Instagram] abc: This content is only available for registered users who follow this account. Use --cookies-from-browser",
        "ERROR: [Instagram] abc: The webpage request was redirected to the login page. You have exceeded the rate-limit for accessing posts anonymously",
        "ERROR: [Instagram] abc: Instagram sent an empty media response. Check if this post is accessible in your browser without being logged-in.",
    ]
    assert [classify_download_error(m) for m in messages] == [LOGIN_REQUIRED] * len(messages)


def test_classify_other_errors_as_unknown():
    assert classify_download_error("ERROR: Unable to download webpage: HTTP Error 404") is None

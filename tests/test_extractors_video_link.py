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


def _video(**extra):
    return {"formats": [{"vcodec": "h264"}], "thumbnails": [{"url": "v-thumb"}], **extra}


def _photo(name, **extra):
    return {"formats": [], "thumbnails": [{"url": f"{name}-small"}, {"url": f"{name}-original"}], **extra}


def test_classify_single_photo_post_uses_best_thumbnail():
    from app.extractors.video_link import classify_post

    assert classify_post(_photo("a")) == ("images", ["a-original"])


def test_classify_photo_carousel_keeps_order_and_skips_videos():
    from app.extractors.video_link import classify_post

    info = {"_type": "playlist", "entries": [_photo("a"), _video(), _photo("b")]}
    assert classify_post(info) == ("images", ["a-original", "b-original"])


def test_classify_post_starting_with_video_is_a_video():
    from app.extractors.video_link import classify_post

    assert classify_post(_video()) == ("video", [])
    assert classify_post({"entries": [_video(), _photo("a")]}) == ("video", [])


def test_classify_caps_images_and_handles_empty_posts():
    from app.extractors.video_link import _MAX_IMAGES, classify_post

    many = {"entries": [_photo(str(i)) for i in range(_MAX_IMAGES + 5)]}
    assert len(classify_post(many)[1]) == _MAX_IMAGES
    assert classify_post({"formats": [], "thumbnails": []}) == ("none", [])
    assert classify_post({"entries": []}) == ("none", [])


def test_classify_falls_back_to_single_thumbnail_field():
    from app.extractors.video_link import classify_post

    assert classify_post({"formats": [], "thumbnail": "only"}) == ("images", ["only"])

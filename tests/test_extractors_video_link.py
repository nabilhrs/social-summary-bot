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


from app.extractors import video_link  # noqa: E402
from app.extractors.video_link import POST_IMAGES_PROMPT, POST_ITEMS_PROMPT, plan_post, prompt_for  # noqa: E402


def _video(duration=20, **extra):
    return {"formats": [{"vcodec": "h264"}], "thumbnails": [{"url": "v-thumb"}], "duration": duration, **extra}


def _photo(name, **extra):
    return {"formats": [], "thumbnails": [{"url": f"{name}-small"}, {"url": f"{name}-original"}], **extra}


def test_single_video_post():
    assert plan_post(_video()) == [("video", 1, None)]


def test_single_photo_uses_best_thumbnail():
    assert plan_post(_photo("a")) == [("image", 1, "a-original")]


def test_mixed_carousel_keeps_every_item_in_order():
    info = {"_type": "playlist", "entries": [_photo("a"), _video(), _photo("b"), _video()]}
    assert plan_post(info) == [("image", 1, "a-original"), ("video", 2, None), ("image", 3, "b-original"), ("video", 4, None)]


def test_all_video_carousel_keeps_every_video():
    assert plan_post({"entries": [_video(), _video(), _video()]}) == [("video", 1, None), ("video", 2, None), ("video", 3, None)]


def test_videos_stop_at_the_total_length_cap_but_photos_continue(monkeypatch):
    monkeypatch.setattr(video_link, "_MAX_VIDEO_SECONDS", 100)
    info = {"entries": [_video(60), _video(60), _photo("a"), _video(30)]}
    assert plan_post(info) == [("video", 1, None), ("image", 3, "a-original"), ("video", 4, None)]


def test_first_video_is_kept_even_if_longer_than_the_cap(monkeypatch):
    monkeypatch.setattr(video_link, "_MAX_VIDEO_SECONDS", 100)
    assert plan_post({"entries": [_video(500), _video(10)]}) == [("video", 1, None)]


def test_items_are_capped():
    info = {"entries": [_photo(str(i)) for i in range(video_link._MAX_ITEMS + 5)]}
    assert len(plan_post(info)) == video_link._MAX_ITEMS


def test_empty_posts_have_no_plan():
    assert plan_post({"formats": [], "thumbnails": []}) == []
    assert plan_post({"entries": []}) == []


def test_missing_duration_counts_as_assumed_length(monkeypatch):
    monkeypatch.setattr(video_link, "_MAX_VIDEO_SECONDS", 50)
    info = {"entries": [_video(None), _video(None)]}
    assert plan_post(info) == [("video", 1, None)]


def test_prompt_matches_the_post_shape():
    from app.extractors.media import PROMPTS, VIDEO

    assert prompt_for([("video", 1, None)]) == PROMPTS[VIDEO]
    assert prompt_for([("image", 1, "a"), ("image", 2, "b")]) == POST_IMAGES_PROMPT
    assert prompt_for([("video", 1, None), ("video", 2, None)]) == POST_ITEMS_PROMPT
    assert prompt_for([("image", 1, "a"), ("video", 2, None)]) == POST_ITEMS_PROMPT



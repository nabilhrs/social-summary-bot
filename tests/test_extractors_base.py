from app.extractors.base import (
    looks_like_url,
    detect_unsupported_platform,
    is_threads_url,
    normalize_pasted_text,
    normalize_web_article,
    normalize_threads_post,
    normalize_video_post,
    video_platform,
)


def test_looks_like_url_accepts_http_and_https():
    assert looks_like_url("https://example.com/article")
    assert looks_like_url("http://example.com")


def test_looks_like_url_rejects_plain_text():
    assert not looks_like_url("just some regular text")
    assert not looks_like_url("check this out: https://example.com")
    assert not looks_like_url("")


def test_looks_like_url_rejects_schemeless_or_bare_domain():
    assert not looks_like_url("example.com")
    assert not looks_like_url("www.example.com")


def test_normalize_pasted_text():
    content = normalize_pasted_text("  hello world  ")
    assert content == {
        "title": None,
        "author": None,
        "source": "pasted_text",
        "url": None,
        "text": "hello world",
    }


def test_normalize_web_article():
    extracted = {"title": "A Title", "author": "Jane Doe", "text": "body text"}
    content = normalize_web_article("https://example.com/a", extracted)
    assert content == {
        "title": "A Title",
        "author": "Jane Doe",
        "source": "web",
        "url": "https://example.com/a",
        "text": "body text",
    }


def test_normalize_web_article_missing_metadata():
    extracted = {"title": None, "author": None, "text": "body text"}
    content = normalize_web_article("https://example.com/a", extracted)
    assert content["title"] is None
    assert content["author"] is None


def test_detect_unsupported_platform_no_longer_flags_threads():
    # PRD V2 2.1 revision: Threads gets real extraction via Open Graph tags
    # now (app/extractors/threads.py), so it's no longer in the "can't
    # extract at all" bucket — only genuinely unsupported platforms are.
    assert detect_unsupported_platform("https://www.threads.net/@user/post/123") is None
    assert detect_unsupported_platform("https://threads.com/@user/post/123") is None


def test_detect_unsupported_platform_no_longer_flags_tiktok():
    # TikTok now gets real extraction via yt-dlp + Gemini video understanding
    # (app/extractors/video_link.py), so nothing is left in the unsupported list.
    assert detect_unsupported_platform("https://www.tiktok.com/@user/video/123") is None
    assert detect_unsupported_platform("https://vt.tiktok.com/abc123") is None


def test_detect_unsupported_platform_none_for_regular_sites():
    assert detect_unsupported_platform("https://example.com/article") is None
    assert detect_unsupported_platform("https://www.bbc.com/news/some-article") is None


def test_video_platform_matches_tiktok_domain_and_subdomains():
    assert video_platform("https://www.tiktok.com/@user/video/123") == "tiktok"
    assert video_platform("https://vt.tiktok.com/abc123") == "tiktok"
    assert video_platform("https://vm.tiktok.com/abc123") == "tiktok"
    assert video_platform("https://WWW.TIKTOK.COM/@user/video/123") == "tiktok"


def test_video_platform_matches_instagram_links():
    assert video_platform("https://www.instagram.com/reel/Chunk8-jurw/") == "instagram"
    assert video_platform("https://www.instagram.com/reels/Cop84x6u7CP/") == "instagram"
    assert video_platform("https://instagram.com/p/BQ0eAlwhDrw/?igsh=abc") == "instagram"
    assert video_platform("https://m.instagram.com/reel/x/") == "instagram"
    assert video_platform("https://instagr.am/p/x/") == "instagram"


def test_video_platform_rejects_lookalike_domains():
    # A domain that merely contains the real one as a substring (not a real
    # subdomain) must not match — e.g. a phishing/lookalike domain.
    assert video_platform("https://tiktok.com.evil.example/x") is None
    assert video_platform("https://nottiktok.com/x") is None
    assert video_platform("https://instagram.com.evil.example/reel/x") is None
    assert video_platform("https://fakeinstagram.com/reel/x") is None


def test_video_platform_rejects_other_sites():
    assert video_platform("https://example.com/article") is None
    assert video_platform("https://threads.com/@user/post/1") is None


def test_is_threads_url_matches_both_domains_and_subdomains():
    assert is_threads_url("https://www.threads.net/@user/post/123")
    assert is_threads_url("https://threads.com/@user/post/123")
    assert is_threads_url("https://WWW.THREADS.NET/@user/post/123")


def test_is_threads_url_rejects_other_sites():
    assert not is_threads_url("https://example.com/article")
    assert not is_threads_url("https://tiktok.com/@user/video/1")
    assert not is_threads_url("https://threads.com.evil.example/x")


def test_normalize_threads_post():
    extracted = {"author": "Jane Doe", "text": "post caption"}
    content = normalize_threads_post("https://www.threads.net/@jane/post/123", extracted)
    assert content == {
        "title": None,
        "author": "Jane Doe",
        "source": "threads",
        "url": "https://www.threads.net/@jane/post/123",
        "text": "post caption",
    }


def test_normalize_video_post_records_platform_as_source():
    extracted = {"author": "creator123", "text": "A video description."}
    content = normalize_video_post("https://www.instagram.com/reel/abc/", extracted, "instagram")
    assert content == {
        "title": None,
        "author": "creator123",
        "source": "instagram",
        "url": "https://www.instagram.com/reel/abc/",
        "text": "A video description.",
    }

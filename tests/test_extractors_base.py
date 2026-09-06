from app.extractors.base import looks_like_url, normalize_pasted_text, normalize_web_article


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

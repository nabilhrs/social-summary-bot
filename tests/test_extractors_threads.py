from app.extractors.threads import _extract_og_field, _extract_author, _OG_DESCRIPTION_RE, _OG_TITLE_RE


def _html_with_meta(description=None, title=None):
    tags = []
    if description is not None:
        tags.append(f'<meta property="og:description" content="{description}">')
    if title is not None:
        tags.append(f'<meta property="og:title" content="{title}">')
    return f"<html><head>{''.join(tags)}</head><body></body></html>"


def test_extract_og_field_finds_description():
    html = _html_with_meta(description="Hello world")
    assert _extract_og_field(html, _OG_DESCRIPTION_RE) == "Hello world"


def test_extract_og_field_unescapes_html_entities():
    html = _html_with_meta(description="It&#039;s a test &amp; more")
    assert _extract_og_field(html, _OG_DESCRIPTION_RE) == "It's a test & more"


def test_extract_og_field_missing_returns_none():
    html = "<html><head></head><body></body></html>"
    assert _extract_og_field(html, _OG_DESCRIPTION_RE) is None


def test_extract_og_field_empty_content_returns_none():
    html = _html_with_meta(description="")
    assert _extract_og_field(html, _OG_DESCRIPTION_RE) is None


def test_extract_author_from_og_title():
    assert _extract_author("Mark Zuckerberg (@zuck) on Threads") == "Mark Zuckerberg"


def test_extract_author_missing_title_returns_none():
    assert _extract_author(None) is None


def test_extract_author_unparseable_title_returns_none():
    assert _extract_author("Just a random title") is None



"""
Chooses which saved items Combine Mode shows Gemini as merge candidates.

The most recent items are always included. Older items only make the cut if
they share several keywords with the new content, so a related note saved
months ago can still be matched without sending the whole history.
"""
import re

_WORD_RE = re.compile(r"[^\W\d_]{4,}")
_MIN_SHARED_KEYWORDS = 2

# Common English and Malay filler words — 4+ letters, since shorter words are
# already ignored by _WORD_RE.
_STOPWORDS = frozenset(
    """
    about after also been before being could does doing from have having here
    into just like make more most much need only other over same should some
    such than that their them then there these they this those through very
    want what when where which while will with would your yours
    adalah akan atau bagi boleh dalam dari dengan juga kalau kami kepada kita
    lagi mereka nak oleh pada saja sahaja saya sebab supaya tapi tetapi tidak
    untuk yang
    """.split()
)


def _keywords(text: str) -> set[str]:
    return {word for word in _WORD_RE.findall(text.lower()) if word not in _STOPWORDS}


def _title_and_summary(item: dict) -> str:
    return f"{item.get('title') or ''} {item['summary']}"


def rank_by_shared_keywords(
    text: str, items: list[dict], min_shared: int = 1, item_text=_title_and_summary
) -> list[dict]:
    """Items sharing at least `min_shared` keywords with `text`, most shared
    first. Ties keep the input order."""
    text_keywords = _keywords(text)
    scored = []
    for item in items:
        shared = len(text_keywords & _keywords(item_text(item)))
        if shared >= min_shared:
            scored.append((shared, item))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in scored]


def pick_candidates(
    new_text: str, items: list[dict], recent_limit: int = 10, keyword_limit: int = 10
) -> list[dict]:
    """`items` must be newest-first, each with `title` and `summary`."""
    recent, older = items[:recent_limit], items[recent_limit:]
    matches = rank_by_shared_keywords(new_text, older, min_shared=_MIN_SHARED_KEYWORDS)
    return recent + matches[:keyword_limit]

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


def pick_candidates(
    new_text: str, items: list[dict], recent_limit: int = 10, keyword_limit: int = 10
) -> list[dict]:
    """`items` must be newest-first, each with `title` and `summary`."""
    recent, older = items[:recent_limit], items[recent_limit:]
    new_keywords = _keywords(new_text)

    scored = []
    for item in older:
        shared = len(new_keywords & _keywords(f"{item.get('title') or ''} {item['summary']}"))
        if shared >= _MIN_SHARED_KEYWORDS:
            scored.append((shared, item))
    # sort() is stable, so ties keep the newer item first.
    scored.sort(key=lambda pair: pair[0], reverse=True)

    return recent + [item for _, item in scored[:keyword_limit]]

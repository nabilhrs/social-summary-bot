"""
Reads a reminder time from plain English or Malay, e.g. "tomorrow 7am",
"esok pukul 3 petang", "in 2 hours", "fri 3pm", "25/11 9:30am",
"3 hari lagi". Rule-based on purpose: instant, no Gemini quota, and it
works when Gemini is busy.

parse_reminder() finds the time words at the start (or the end) of the
text and returns the time plus what's left over as the reminder text. Dates
are day-first (25/11 is 25 November). The caller always shows the exact
date back, so a misread is visible before it counts.
"""
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

_WEEKDAYS = {
    "mon": 0, "monday": 0, "isnin": 0,
    "tue": 1, "tues": 1, "tuesday": 1, "selasa": 1,
    "wed": 2, "wednesday": 2, "rabu": 2,
    "thu": 3, "thur": 3, "thurs": 3, "thursday": 3, "khamis": 3,
    "fri": 4, "friday": 4, "jumaat": 4, "jumat": 4,
    "sat": 5, "saturday": 5, "sabtu": 5,
    "sun": 6, "sunday": 6, "ahad": 6,
}
_MONTHS = {
    "jan": 1, "january": 1, "januari": 1,
    "feb": 2, "february": 2, "februari": 2,
    "mar": 3, "march": 3, "mac": 3,
    "apr": 4, "april": 4,
    "may": 5, "mei": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7, "julai": 7,
    "aug": 8, "august": 8, "ogos": 8, "ogo": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "okt": 10, "oktober": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12, "dis": 12, "disember": 12,
}
_DAY_OFFSETS = {
    "today": 0, "tdy": 0, "harini": 0,
    "tomorrow": 1, "tmr": 1, "tmrw": 1, "tomoro": 1, "esok": 1, "besok": 1, "esk": 1,
    "lusa": 2,
}
# Part of the day: (default hour if no time is given, whether a bare hour means pm)
_PARTS = {
    "morning": (9, False), "pagi": (9, False),
    "noon": (12, True), "tengahari": (12, True),
    "afternoon": (15, True), "petang": (16, True),
    "evening": (18, True),
    "night": (20, True), "malam": (20, True), "mlm": (20, True),
    "tonight": (20, True),
}
_UNITS = {
    "m": 1, "min": 1, "mins": 1, "minute": 1, "minutes": 1, "minit": 1,
    "h": 60, "hr": 60, "hrs": 60, "hour": 60, "hours": 60, "jam": 60,
    "d": 1440, "day": 1440, "days": 1440, "hari": 1440,
    "w": 10080, "wk": 10080, "week": 10080, "weeks": 10080, "minggu": 10080,
}
# Words that join time words but carry no meaning of their own.
_FILLERS = {
    "at", "on", "by", "in", "dalam", "pukul", "pkl", "jam", "pada", "this", "ini", "ni",
    "next", "depan", "the", "around", "about",
}
_LEADING_TEXT_FILLERS = {"to", "that", "untuk", "nak", "-", ":", "about", "pasal"}
_DEFAULT_HOUR = 9

_CLOCK_RE = re.compile(r"^(\d{1,2})(?:[:.](\d{2}))?(am|pm|a\.m\.|p\.m\.)?$")
_DATE_RE = re.compile(r"^(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?$")
_COMPACT_DURATION_RE = re.compile(r"^(\d+)(m|min|mins|h|hr|hrs|d|w)$")
_NUMBER_RE = re.compile(r"^\d+$")


@dataclass
class _State:
    day_offset: int | None = None
    weekday: int | None = None
    explicit_date: date | None = None
    hour: int | None = None
    minute: int = 0
    meridiem: str | None = None  # "am" / "pm"
    part: str | None = None
    delta_minutes: int = 0


def _match_at(tokens: list[str], i: int, state: _State) -> int:
    """How many tokens starting at i are a time expression (0 if none);
    records what they mean in `state`."""
    token = tokens[i]
    nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
    nxt2 = tokens[i + 2] if i + 2 < len(tokens) else ""

    # Relative durations: "in 2 hours", "dalam 30 minit", "lagi 2 jam", "2 jam lagi", "30min".
    if token in ("in", "dalam", "lagi") and _NUMBER_RE.match(nxt) and nxt2 in _UNITS:
        state.delta_minutes += int(nxt) * _UNITS[nxt2]
        return 3 + (1 if i + 3 < len(tokens) and tokens[i + 3] == "lagi" else 0)
    if _NUMBER_RE.match(token) and nxt in _UNITS and nxt2 == "lagi":
        state.delta_minutes += int(token) * _UNITS[nxt]
        return 3
    if token in ("in", "dalam", "lagi") and nxt in ("an", "a", "sejam", "sehari", "seminggu"):
        if nxt in ("sejam", "sehari", "seminggu"):
            state.delta_minutes += {"sejam": 60, "sehari": 1440, "seminggu": 10080}[nxt]
            return 2
        if nxt2 in _UNITS:
            state.delta_minutes += _UNITS[nxt2]
            return 3
    if token in ("sejam", "sehari", "seminggu") and nxt == "lagi":
        state.delta_minutes += {"sejam": 60, "sehari": 1440, "seminggu": 10080}[token]
        return 2
    if token == "setengah" and nxt == "jam":
        state.delta_minutes += 30
        return 2 + (1 if nxt2 == "lagi" else 0)
    compact = _COMPACT_DURATION_RE.match(token)
    if compact and (i > 0 and tokens[i - 1] in ("in", "dalam", "lagi") or nxt == "lagi"):
        state.delta_minutes += int(compact.group(1)) * _UNITS[compact.group(2)]
        return 1 + (1 if nxt == "lagi" else 0)

    # Days: "tomorrow", "esok", "hari ini", "day after tomorrow", "lusa".
    if token == "hari" and nxt in ("ini", "ni"):
        state.day_offset = 0
        return 2
    if token == "day" and nxt == "after" and nxt2 in ("tomorrow", "tmr", "tmrw"):
        state.day_offset = 2
        return 3
    if (token, nxt) in (("next", "week"), ("minggu", "depan")):
        state.day_offset = 7
        return 2
    if token in _DAY_OFFSETS:
        state.day_offset = _DAY_OFFSETS[token]
        return 1
    if token in _WEEKDAYS:
        state.weekday = _WEEKDAYS[token]
        return 1

    # Dates: "25/11", "25-11-2026", "25 nov", "nov 25".
    date_match = _DATE_RE.match(token)
    if date_match:
        state.explicit_date = _make_date(int(date_match.group(1)), int(date_match.group(2)), date_match.group(3))
        return 1 if state.explicit_date else 0
    if _NUMBER_RE.match(token) and nxt in _MONTHS and int(token) <= 31:
        state.explicit_date = _make_date(int(token), _MONTHS[nxt], None)
        return 2 if state.explicit_date else 0
    if token in _MONTHS and _NUMBER_RE.match(nxt) and int(nxt) <= 31:
        state.explicit_date = _make_date(int(nxt), _MONTHS[token], None)
        return 2 if state.explicit_date else 0

    # Parts of the day: "pagi", "tonight", "tengah hari", "petang".
    if token == "tengah" and nxt in ("hari", "malam"):
        if nxt == "hari":
            state.part = "noon"
        else:
            state.hour, state.minute, state.meridiem = 0, 0, "am"
        return 2
    if token in _PARTS:
        state.part = token
        if token == "tonight":
            state.day_offset = 0 if state.day_offset is None else state.day_offset
        # "malam ini" / "pagi ni" = tonight / this morning
        return 2 if nxt in ("ini", "ni") else 1
    if token in ("midnight",):
        state.hour, state.minute, state.meridiem = 0, 0, "am"
        return 1

    # Clock times: "7am", "7:30pm", "19:00", "7 pm", and a bare "8" only right
    # after "at"/"pukul"/a part of the day, or right before a part of the day.
    clock = _CLOCK_RE.match(token)
    previous = tokens[i - 1] if i > 0 else ""
    if clock and (clock.group(2) or clock.group(3) or int(clock.group(1)) > 12 or nxt in ("am", "pm")
                  or previous in ("at", "pukul", "pkl", "jam") or previous in _PARTS or nxt in _PARTS):
        hour, minute = int(clock.group(1)), int(clock.group(2) or 0)
        if hour > 23 or minute > 59:
            return 0
        meridiem = (clock.group(3) or "").replace(".", "") or (nxt if nxt in ("am", "pm") else None)
        state.hour, state.minute, state.meridiem = hour, minute, meridiem
        return 2 if nxt in ("am", "pm") and not clock.group(3) else 1

    if token in _FILLERS:
        return 1
    return 0


def _make_date(day: int, month: int, year: str | None) -> date | None:
    try:
        if year:
            year_number = int(year) + (2000 if len(year) == 2 else 0)
            return date(year_number, month, day)
        return date(1, month, day)  # year filled in later
    except ValueError:
        return None


def _consume(tokens: list[str], start: int) -> tuple[_State, int, int]:
    """(meaning, where matching stopped, end of the last non-filler match).
    Fillers after the last real time word belong to the reminder text."""
    state, i, meaningful_end = _State(), start, start
    while i < len(tokens):
        taken = _match_at(tokens, i, state)
        if taken == 0:
            break
        if not (taken == 1 and tokens[i] in _FILLERS):
            meaningful_end = i + taken
        i += taken
    return state, i, meaningful_end


def _meaningful(state: _State) -> bool:
    return any(
        (state.day_offset is not None, state.weekday is not None, state.explicit_date is not None,
         state.hour is not None, state.part is not None, state.delta_minutes)
    )


def _resolve(state: _State, now: datetime) -> datetime | None:
    if state.delta_minutes and state.hour is None and state.part is None:
        return now + timedelta(minutes=state.delta_minutes)

    day_given = state.day_offset is not None or state.weekday is not None or state.explicit_date is not None
    base = now + timedelta(minutes=state.delta_minutes) if state.delta_minutes else now
    if state.explicit_date is not None:
        target = state.explicit_date
        if target.year == 1:
            target = target.replace(year=now.year)
            if target < now.date():
                target = target.replace(year=now.year + 1)
        day = target
    elif state.day_offset is not None:
        day = (base + timedelta(days=state.day_offset)).date()
    elif state.weekday is not None:
        day = (now + timedelta(days=(state.weekday - now.weekday()) % 7)).date()
    else:
        day = base.date()

    part_hour, part_pm = _PARTS.get(state.part, (None, None)) if state.part else (None, None)
    if state.hour is None:
        hour, minute = (part_hour if part_hour is not None else _DEFAULT_HOUR), 0
    else:
        hour, minute = state.hour, state.minute
        if state.meridiem == "pm" and hour < 12:
            hour += 12
        elif state.meridiem == "am" and hour == 12:
            hour = 0
        elif state.meridiem is None and hour <= 12:
            if part_pm is not None:
                hour = hour + 12 if part_pm and hour < 12 else hour
            elif day_given:
                hour = hour + 12 if 1 <= hour <= 6 else hour
            else:
                # Just "at 8": whichever of 8am / 8pm comes next.
                morning = datetime.combine(day, datetime.min.time(), now.tzinfo).replace(hour=hour % 12)
                hour = hour % 12 if morning > now else hour % 12 + 12

    when = datetime.combine(day, datetime.min.time(), now.tzinfo).replace(hour=hour, minute=minute)
    if state.weekday is not None and when <= now:
        when += timedelta(days=7)
    if not day_given and not state.delta_minutes and when <= now:
        when += timedelta(days=1)
    return when


@dataclass
class ParsedReminder:
    when: datetime
    text: str


def _tokens(text: str) -> list[str]:
    return [t for t in re.split(r"[\s,]+", text.strip().lower()) if t]


def _clean_text(words: list[str], original: str) -> str:
    while words and words[0].lower() in _LEADING_TEXT_FILLERS:
        words = words[1:]
    while words and words[-1].lower() in _FILLERS | {"-", ":"}:
        words = words[:-1]
    return " ".join(words).strip()


def parse_reminder(text: str, now: datetime) -> ParsedReminder | None:
    """`now` is timezone-aware in the user's timezone. Returns None when no
    time could be read. The time may be in the past; callers should check."""
    lowered = _tokens(text)
    original_words = [w for w in re.split(r"[\s,]+", text.strip()) if w]
    if not lowered:
        return None

    state, _end, meaningful_end = _consume(lowered, 0)
    if meaningful_end > 0 and _meaningful(state):
        return ParsedReminder(_resolve(state, now), _clean_text(original_words[meaningful_end:], text))

    for start in range(1, len(lowered)):
        state, end, _meaningful_end = _consume(lowered, start)
        if end == len(lowered) and _meaningful(state):
            return ParsedReminder(_resolve(state, now), _clean_text(original_words[:start], text))
    return None

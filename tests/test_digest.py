from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.bot.digest import build_digest, collect_digest, next_run
from app.database import database

KL = ZoneInfo("Asia/Kuala_Lumpur")
USER = 111


@pytest.mark.parametrize(
    "now, expected",
    [
        (datetime(2026, 10, 7, 13, 0, tzinfo=KL), datetime(2026, 10, 11, 9, 0, tzinfo=KL)),  # Wed -> Sun
        (datetime(2026, 10, 11, 8, 59, tzinfo=KL), datetime(2026, 10, 11, 9, 0, tzinfo=KL)),  # Sun before 9
        (datetime(2026, 10, 11, 9, 0, tzinfo=KL), datetime(2026, 10, 18, 9, 0, tzinfo=KL)),  # exactly 9 -> next week
        (datetime(2026, 10, 11, 21, 0, tzinfo=KL), datetime(2026, 10, 18, 9, 0, tzinfo=KL)),  # Sun evening
    ],
)
def test_next_run(now, expected):
    assert next_run(now) == expected


def _item(item_id, title, category=None, summary="SUMMARY: s", created_at="2026-10-05T00:00:00+00:00"):
    return {
        "id": item_id,
        "title": title,
        "original_text": "x",
        "category": category,
        "summary": summary,
        "created_at": created_at,
    }


def test_build_digest_nothing_to_send():
    assert build_digest([], None) is None


def test_build_digest_groups_by_category_biggest_first():
    week = [_item(3, "Pasta tip", "Food"), _item(2, "STAR <method>", "Career"), _item(1, "Pitch", "Career")]
    text = build_digest(week, None)
    assert text.startswith("🗓️ <b>Your week in notes</b> — 3 saved")
    assert text.index("📂 <b>Career</b>") < text.index("📂 <b>Food</b>")
    assert "• #2 STAR &lt;method&gt;" in text


def test_build_digest_throwback_only_week():
    text = build_digest([], _item(9, "Old idea", summary="SUMMARY: still good"))
    assert "No new notes this week." in text
    assert "🔁 <b>From your archive</b>" in text
    assert "<b>#9 — Old idea</b> (2026-10-05)" in text
    assert "still good" in text
    assert "/view 9" in text


def test_build_digest_uncategorized_and_truncated_throwback():
    text = build_digest([_item(1, "Loose note")], _item(2, "Long", summary="line\n" * 500))
    assert "📂 <b>Uncategorized</b>" in text
    assert len(text) < 1500


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(database.config, "db_path", str(tmp_path / "t.db"))
    database.init_db()


def _save_at(title, when, category="Career"):
    content = {"title": title, "author": None, "source": "pasted_text", "url": None, "text": "x"}
    row_id = database.save_summary(content, "SUMMARY: s", USER, category=category)
    import sqlite3

    with sqlite3.connect(database.config.db_path) as conn:
        conn.execute("UPDATE summaries SET created_at = ? WHERE id = ?", (when.isoformat(), row_id))
    return row_id


def test_collect_digest_splits_this_week_from_archive(db):
    now = datetime(2026, 10, 11, 9, 0, tzinfo=KL)
    recent = _save_at("This week", (now - timedelta(days=2)).astimezone(timezone.utc))
    old = _save_at("Months ago", (now - timedelta(days=90)).astimezone(timezone.utc))

    text = collect_digest(USER, now)

    assert f"• #{recent} This week" in text
    assert f"<b>#{old} — Months ago</b>" in text


def test_collect_digest_empty_database(db):
    assert collect_digest(USER, datetime(2026, 10, 11, 9, 0, tzinfo=KL)) is None

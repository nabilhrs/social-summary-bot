import pytest

from app.bot.handlers import already_saved_text, build_duplicate_keyboard, find_saved_link
from app.database import database
from app.extractors.base import link_key, youtube_video_id

USER = 111


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=9hE5-98ZeCg",
        "https://youtube.com/watch?v=9hE5-98ZeCg&si=abc&t=42",
        "https://m.youtube.com/watch?feature=share&v=9hE5-98ZeCg",
        "https://youtu.be/9hE5-98ZeCg?si=xyz",
        "https://www.youtube.com/shorts/9hE5-98ZeCg",
        "https://www.youtube.com/live/9hE5-98ZeCg?feature=shared",
        "https://www.youtube-nocookie.com/embed/9hE5-98ZeCg",
    ],
)
def test_youtube_video_id_variants(url):
    assert youtube_video_id(url) == "9hE5-98ZeCg"


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/@GoogleDevelopers",
        "https://www.youtube.com/watch?v=short",
        "https://www.youtube.com/playlist?list=PL123",
        "https://notyoutube.com/watch?v=9hE5-98ZeCg",
        "https://example.com/watch?v=9hE5-98ZeCg",
    ],
)
def test_youtube_video_id_rejects_non_videos(url):
    assert youtube_video_id(url) is None


def test_link_key_ignores_tracking_and_cosmetic_differences():
    assert link_key("https://www.instagram.com/reel/abc/?igsh=xyz") == link_key("https://instagram.com/reel/abc")
    assert link_key("https://m.example.com/a/?utm_source=x&id=7") == link_key("https://example.com/a?id=7")
    assert link_key("https://youtu.be/9hE5-98ZeCg") == link_key("https://www.youtube.com/watch?v=9hE5-98ZeCg&si=1")


def test_link_key_keeps_meaningful_differences():
    assert link_key("https://example.com/a?id=7") != link_key("https://example.com/a?id=8")
    assert link_key("https://example.com/a") != link_key("https://example.com/b")


@pytest.fixture
def saved(tmp_path, monkeypatch):
    monkeypatch.setattr(database.config, "db_path", str(tmp_path / "d.db"))
    database.init_db()
    content = {"title": "Pasta Reel", "author": None, "source": "instagram",
               "url": "https://www.instagram.com/reel/C9pQx2Lm8nK/?igsh=abc", "text": "x"}
    return database.save_summary(content, "s", USER)


def test_same_link_with_different_tracking_is_found(saved):
    assert find_saved_link(USER, "https://instagram.com/reel/C9pQx2Lm8nK")["id"] == saved


def test_other_links_and_other_users_are_not_matched(saved):
    assert find_saved_link(USER, "https://instagram.com/reel/SomethingElse") is None
    assert find_saved_link(999, "https://instagram.com/reel/C9pQx2Lm8nK") is None


def test_already_saved_reply_and_buttons(saved):
    item = find_saved_link(USER, "https://instagram.com/reel/C9pQx2Lm8nK")
    assert already_saved_text(item).startswith(f"📌 Already saved as #{saved} — Pasta Reel (")
    data = [b.callback_data for row in build_duplicate_keyboard(saved).inline_keyboard for b in row]
    assert data == [f"dup:view:{saved}", f"dup:again:{saved}"]

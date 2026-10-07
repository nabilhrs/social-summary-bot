from app.config import Config


def _config(monkeypatch, **env):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("AUTHORIZED_USER_IDS", "1")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return Config()


def test_empty_db_path_falls_back_to_default(monkeypatch):
    assert _config(monkeypatch, DB_PATH="").db_path == "summarizer.db"


def test_db_path_override(monkeypatch):
    assert _config(monkeypatch, DB_PATH="/data/notes.db").db_path == "/data/notes.db"


def test_empty_timezone_falls_back_to_default(monkeypatch):
    assert _config(monkeypatch, TIMEZONE="").timezone == "Asia/Kuala_Lumpur"


def test_timezone_override(monkeypatch):
    assert _config(monkeypatch, TIMEZONE="Europe/London").timezone == "Europe/London"

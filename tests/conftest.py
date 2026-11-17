import pytest

from app.database import database


@pytest.fixture(autouse=True)
def _isolated_database(tmp_path, monkeypatch):
    """Every test gets its own empty database, so nothing (like Gemini usage
    counting) can ever write to the real summarizer.db. Tests that need a
    specific database still point db_path elsewhere themselves."""
    monkeypatch.setattr(database.config, "db_path", str(tmp_path / "isolated.db"))
    database.init_db()

"""
Central config loader.

Everything the bot needs at runtime is pulled from environment variables
(populated via `.env` locally). Keeping this in one place means every other
module just does `from app.config import config` instead of touching
os.environ / dotenv directly.
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    def __init__(self):
        self.telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")

        # PRD 5.8 — single authorized user, hardcoded via env, not a DB table.
        authorized_id = os.getenv("AUTHORIZED_USER_ID", "")
        self.authorized_user_id: int | None = (
            int(authorized_id) if authorized_id.strip() else None
        )

        self.db_path: str = os.getenv("DB_PATH", "summarizer.db")

        self._validate()

    def _validate(self):
        missing = []
        if not self.telegram_bot_token:
            missing.append("TELEGRAM_BOT_TOKEN")
        if self.authorized_user_id is None:
            missing.append("AUTHORIZED_USER_ID")
        if missing:
            raise RuntimeError(
                f"Missing required environment variable(s): {', '.join(missing)}. "
                f"Copy .env.example to .env and fill them in."
            )

    def is_authorized(self, user_id: int) -> bool:
        return user_id == self.authorized_user_id


config = Config()

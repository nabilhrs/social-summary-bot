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

        # PRD V2 multi-user revision — an ordered allowlist of Telegram user
        # ids, comma-separated, not a DB table (still a hardcoded gate, just
        # no longer limited to one person). Order matters once: on first run
        # after upgrading from single-user, the first id here is treated as
        # the owner of any pre-existing rows with no user_id yet (see
        # app/database/database.py's init_db migration).
        raw_ids = os.getenv("AUTHORIZED_USER_IDS", "")
        self.authorized_user_ids: list[int] = [
            int(uid.strip()) for uid in raw_ids.split(",") if uid.strip()
        ]

        self.db_path: str = os.getenv("DB_PATH", "summarizer.db")

        self._validate()

    def _validate(self):
        missing = []
        if not self.telegram_bot_token:
            missing.append("TELEGRAM_BOT_TOKEN")
        if not self.authorized_user_ids:
            missing.append("AUTHORIZED_USER_IDS")
        if missing:
            raise RuntimeError(
                f"Missing required environment variable(s): {', '.join(missing)}. "
                f"Copy .env.example to .env and fill them in."
            )

    def is_authorized(self, user_id: int) -> bool:
        return user_id in self.authorized_user_ids


config = Config()

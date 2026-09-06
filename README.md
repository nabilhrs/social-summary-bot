# Social Summary Bot

A personal Telegram bot that takes pasted text or a web article URL, generates
a structured AI summary via Gemini, and saves it to a local SQLite database.

See [summarizer_bot_prd_v1.md](summarizer_bot_prd_v1.md) for the full spec.

## Setup

1. Create a virtual environment (a 64-bit Python interpreter is required —
   `cryptography`, a transitive dependency, has no prebuilt wheels for 32-bit
   Windows and will fail to build from source):
   ```
   py -3.14 -m venv venv
   ```
2. Install dependencies:
   ```
   venv\Scripts\pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and fill in:
   - `TELEGRAM_BOT_TOKEN` — from [@BotFather](https://t.me/BotFather)
   - `AUTHORIZED_USER_ID` — your numeric Telegram user ID, from [@userinfobot](https://t.me/userinfobot)
   - `GEMINI_API_KEY` — from [Google AI Studio](https://aistudio.google.com/apikey)
4. Run the bot:
   ```
   venv\Scripts\python main.py
   ```

## Usage

Message the bot directly:
- **Paste text** — summarized as-is.
- **Send a URL** — the bot fetches and extracts the article, then summarizes it.

Every summary is saved to SQLite (`summarizer.db` by default, or `DB_PATH`).

## Tests

```
venv\Scripts\pytest
```

## Project structure

See section 7 of the PRD. Build order (section 8) is complete through
step 5 (error handling); Combine Mode (5.5) is not implemented — per the
PRD's own cut criterion, it's the first thing dropped under time pressure.

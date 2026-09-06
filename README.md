# Social Summary Bot

A Telegram bot that takes a URL — articles, Threads posts, TikTok videos —
or pasted text, generates an AI summary via Gemini, and saves it to a local
SQLite database. Related saves get offered a merge instead of piling up as
duplicates, and everything you save can be listed, searched, viewed,
merged, or deleted back from Telegram itself.

Multiple people can use the same bot — each person's saved items are
private to them, gated by a hardcoded allowlist (not open to the public
internet; see Setup).

See [summarizer_bot_prd_v1.md](summarizer_bot_prd_v1.md) for the original
spec and [summarizer_bot_prd_v2.md](summarizer_bot_prd_v2.md) for what's
been added since. [CHECKLIST.md](CHECKLIST.md) is the up-to-date status of
every feature. [memory.md](memory.md) logs bugs found through real use and
why they happened — worth a read before touching the extraction or
Combine Mode code.

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
   This includes `yt-dlp` with its browser-impersonation extra (needed to
   get past TikTok's bot-challenge), which pulls in a few extra packages —
   the install takes a little longer than a typical Python project.
3. Copy `.env.example` to `.env` and fill in:
   - `TELEGRAM_BOT_TOKEN` — from [@BotFather](https://t.me/BotFather)
   - `AUTHORIZED_USER_IDS` — comma-separated numeric Telegram user IDs allowed
     to use the bot (get an ID from [@userinfobot](https://t.me/userinfobot)).
     List yourself first — on first run after adding more people, any
     pre-existing saved items are assigned to whichever ID is listed first.
     Every listed user gets their own private saved items; no one sees
     anyone else's.
   - `GEMINI_API_KEY` — from [Google AI Studio](https://aistudio.google.com/apikey).
     Only used for the *first* id in `AUTHORIZED_USER_IDS` (the owner) — every
     other invited user must set their own key from inside the bot with
     `/setkey`, so no one but the owner can ever consume this key's cost.
4. Run the bot:
   ```
   venv\Scripts\python main.py
   ```

## Usage

Message the bot directly, or tap a command from Telegram's "/" menu:

- **Paste text** — summarized as-is. Short notes (under ~80 words) get a
  tight 1-3 sentence summary; longer content gets the full
  TL;DR / KEY POINTS / TAKEAWAY structure.
- **Send a URL** — the bot fetches and summarizes it:
  - Regular web articles are extracted with `trafilatura`.
  - **Threads** posts are read via their public Open Graph tags (the same
    mechanism every app uses for link previews) — this only captures the
    linked post's own caption, not replies, so the bot always notes that
    limitation.
  - **TikTok** videos are downloaded and actually watched — Gemini
    summarizes what's shown and said, not just the caption. This takes
    noticeably longer (expect 30s+); the bot sends a heads-up while it
    works.
- **Combine Mode** — if new content looks related to something already
  saved, the bot offers to merge them into one summary instead of leaving
  duplicates, with an optional "view first" button if you don't remember
  the older item. You can also trigger a merge yourself with `/merge`.

Every summary is saved to SQLite (`summarizer.db` by default, or `DB_PATH`),
scoped to the Telegram user who saved it — Combine Mode's related-item
check and every command below only ever see and act on your own items,
never another authorized user's. Commands for managing what's saved:

| Command | Does |
|---|---|
| `/list [n]` | Last `n` saved items (default 10, max 50), with a quick-delete button per item |
| `/search <keyword>` | Search saved items by keyword |
| `/view <id>` | Full summary for one item |
| `/merge <keep_id> <absorb_id>` | Merge two items into one (asks for confirmation) |
| `/delete <id>` | Delete an item (asks for confirmation) |
| `/undo <id>` | Revert a merged item to its pre-merge summary |
| `/setkey <api_key>` | Set your own Gemini API key (required for every invited user except the owner) |

Every authorized user besides the owner sees a prompt to run `/setkey` the
first time they try to summarize anything — `/setkey` validates the key
live before saving it, and deletes the message containing it from chat
history afterward. Keys are stored in plain SQLite, same as everything
else here — no encryption at rest, worth knowing if you invite people
beyond a small trusted group.

## Hosting

Running `python main.py` locally only keeps the bot online while your
machine does. See [DEPLOY.md](DEPLOY.md) to run it continuously on a
free-tier cloud VM (`deploy/setup.sh` + `deploy/social-summary-bot.service`
automate everything past account creation).

## Tests

```
venv\Scripts\pytest
```

Pure logic (parsing, formatting, database queries) is unit tested.
Network- and filesystem-dependent extraction (web/Threads/TikTok fetches,
Gemini calls) is verified live rather than mocked — see the commit history
and `memory.md` for what's been checked and how.

## Project structure

```
social-summary-bot/
├── app/
│   ├── bot/
│   │   ├── commands.py      # slash commands
│   │   ├── handlers.py      # plain-message pipeline + merge/delete callbacks
│   │   └── formatting.py    # shared display/keyboard builders
│   ├── extractors/
│   │   ├── base.py          # URL routing, normalization
│   │   ├── webpage.py       # generic articles (trafilatura)
│   │   ├── threads.py       # Threads posts (Open Graph tags)
│   │   └── tiktok.py        # TikTok videos (yt-dlp + Gemini video understanding)
│   ├── ai/
│   │   ├── summarizer.py
│   │   └── prompts.py
│   ├── database/
│   │   └── database.py
│   └── config.py
├── tests/
├── deploy/
│   ├── setup.sh                     # provisions a fresh Ubuntu VM
│   └── social-summary-bot.service   # systemd unit for always-on running
├── .env / .env.example
├── requirements.txt
└── main.py
```

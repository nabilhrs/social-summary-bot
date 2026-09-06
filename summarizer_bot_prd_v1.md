# PRD — Personal Content Summarizer Bot (V1)

**Status:** Finalized scope, ready for implementation
**Owner:** Nabil
**Last updated:** 2026-09-04

---

## 1. Problem Statement

Interesting content encountered while browsing (articles, posts, threads) gets bookmarked and forgotten. There's no lightweight way to capture it, get a useful summary, and keep it for later.

## 2. Goal (V1)

Build a Telegram bot that accepts either pasted text or a web article URL, produces a structured AI summary, and saves it locally — proving the core extractor → summarizer → storage architecture end to end.

**Non-goal for V1:** Threads or TikTok support. Both require unofficial/fragile access methods (see Appendix A) and are deliberately deferred to Phase 2.

## 3. Success Criteria

- User can send pasted text OR a web article URL to the bot and receive a structured summary within ~10–15 seconds for typical article length.
- Every summary is saved to SQLite with its source metadata.
- The bot never hard-fails silently — every error path returns a clear message to the user.
- Fully usable by one authorized user (you) via a hardcoded user ID check.

## 4. User Flow

```
User sends message to bot
        │
        ▼
Is it a URL or plain text?
        │
   ┌────┴────┐
   ▼         ▼
 URL       Plain text
   │         │
   ▼         │
Fetch page   │
Extract      │
article      │
content      │
   │         │
   └────┬────┘
        ▼
Normalized content object
        │
        ▼
AI Summarizer (OpenAI API)
        │
        ▼
Structured summary sent to user
        │
        ▼
Saved to SQLite
```

## 5. Functional Requirements

### 5.1 Input Handling
- Bot listens for any message from the authorized user.
- Detect whether the message is a URL (regex/urlparse check) or plain text.
- If URL: attempt to fetch and extract; if extraction fails, respond with a fallback message asking the user to paste the text instead.
- If plain text: use directly as content.

### 5.2 Content Extraction (Web Articles Only)
- Fetch page HTML via `httpx`.
- Extract main content using `trafilatura` (preferred) or `readability-lxml` as fallback.
- Extract: title, author (if available), body text.
- Handle failures gracefully (paywalled, JS-rendered, 404, timeout) — fall back to "please paste the text" message.

### 5.3 Normalization
Every piece of content, regardless of source, becomes:
```json
{
  "title": "...",
  "author": "...",
  "source": "web" | "pasted_text",
  "url": "..." ,
  "text": "..."
}
```

### 5.4 AI Summarization
- Single function: `summarize(content: dict) -> Summary`
- Fixed output structure for V1 (no mode switching yet):
  ```
  TL;DR: <1-2 sentences>
  KEY POINTS: <3-6 bullets>
  TAKEAWAY: <1 sentence>
  ```
- Model: Gemini API (specific model chosen at implementation time).
- On API failure: return "Something went wrong while generating the summary. Please try again."

### 5.5 Combine Mode (Stretch — not core V1)

**Goal:** when new content looks related to something already saved, suggest merging it into one accumulating summary for that topic instead of leaving fragmented, duplicate entries.

**Why this is a stretch, not core:** reliable topic similarity is what embeddings/vector search are built for (see section 13 of the original brainstorm / Appendix B below). Building that properly is real complexity — a Phase 2 item, not a weekend item.

**Lightweight approach for now (no embeddings, no vector DB):**
1. Before generating a fresh summary, pull the title + summary of the last ~10 saved items from SQLite.
2. Pass those alongside the new content in the same Gemini call, asking the model to judge whether the new content is closely related to any of them.
3. If the model flags a likely match, the bot replies with the new summary *and* a suggestion: "This looks related to #<id> — <title>. Want me to merge these into one summary?"
4. If the user confirms, the bot asks Gemini to produce a single merged summary from both original texts, replaces the old row's `summary` field (or appends), and updates `created_at`.
5. If the user declines or ignores it, save as a normal separate entry — no forced merging.

**Known limitations of this approach:** works fine at the scale of a personal bot with a few dozen items; accuracy will degrade as history grows past what fits comfortably in one prompt. That's the natural trigger point to revisit with real embeddings in Phase 2, not before.

**Cut criterion:** if V1 build time runs short, this is the first thing dropped. The bot is fully usable without it — items just save as independent entries.

### 5.6 Bot Commands (V1)
```
/start      — welcome + short usage instructions
/help       — usage instructions
/summarize <URL or nothing, then paste text next>
```
Auto-detection (no command needed) is a stretch goal, not required for V1 — decide at implementation time based on remaining time budget.

### 5.7 Storage
SQLite, single table, direct `sqlite3` (no ORM):

| Field | Type | Notes |
|---|---|---|
| id | INTEGER PK | autoincrement |
| url | TEXT | nullable (pasted text has none) |
| source | TEXT | "web" or "pasted_text" |
| title | TEXT | nullable |
| author | TEXT | nullable |
| original_text | TEXT | |
| summary | TEXT | |
| created_at | TEXT | ISO timestamp |
| merged_from | TEXT | nullable — comma-separated ids merged into this entry via Combine Mode |

### 5.8 Access Control
- Single authorized Telegram user ID, stored in `.env`.
- Any message from a different user ID gets a polite rejection, no processing.

### 5.9 Error Handling

| Case | Response |
|---|---|
| Invalid/unrecognized input | "That doesn't look like a link or usable text." |
| URL fetch/extraction fails | "I couldn't extract this article automatically. Please paste the text here and I'll summarize it." |
| AI API failure | "Something went wrong while generating the summary. Please try again." |
| Unauthorized user | Generic rejection, no details leaked |

## 6. Technical Stack

| Component | Choice |
|---|---|
| Bot interface | Telegram (`python-telegram-bot`) |
| Backend | Python |
| AI | Gemini API |
| Article extraction | `trafilatura` |
| HTTP | `httpx` |
| Database | SQLite, raw `sqlite3` |
| Config | `.env` (`python-dotenv`) |
| Testing | `pytest` |
| Version control | Git + GitHub |

## 7. Project Structure

```
social-summary-bot/
├── app/
│   ├── bot/
│   │   ├── handlers.py
│   │   └── commands.py
│   ├── extractors/
│   │   ├── base.py
│   │   └── webpage.py
│   ├── ai/
│   │   ├── summarizer.py
│   │   └── prompts.py
│   ├── database/
│   │   └── database.py
│   └── config.py
├── tests/
├── .env
├── .gitignore
├── requirements.txt
├── README.md
└── main.py
```

## 8. Build Order

1. Telegram bot skeleton — receive message, echo response
2. AI summarizer working on hardcoded/pasted text
3. Web article extractor wired into the same pipeline
4. SQLite persistence
5. Error handling pass across all failure paths
6. README + basic tests

## 9. Explicitly Out of Scope (V1)

- Threads and TikTok extraction
- `/search`, `/notes`, `/eli5`, `/technical`, `/action` modes
- Real embeddings/vector-based semantic search (Combine Mode uses a lightweight recent-history prompt instead — see 5.5)
- Tags, categories
- Web dashboard
- Multi-user support beyond one hardcoded ID

---

## Appendix A — Why Threads/TikTok Are Deferred

- **Threads:** Meta's official API only retrieves the *authenticated user's own* posts (`threads_basic` scope). The oEmbed endpoint can fetch a public post's embed HTML by URL, but Meta's terms explicitly prohibit using that data for anything beyond rendering an embed on a webpage — extraction/summarization use is disallowed. Any working approach would rely on unofficial scraping, which is fragile and ToS-risky.
- **TikTok:** No official API for arbitrary video/content retrieval by a personal bot. A working pipeline would need video download (e.g. `yt-dlp`) + Whisper transcription — a real day-plus of work and an ongoing maintenance burden as TikTok changes its defenses.

Both are strong Phase 2 candidates *once V1 is stable*, built as opportunistic extractors behind the same fallback message: "couldn't access automatically — paste the text/transcript instead."

## Appendix B — Combine Mode's Upgrade Path

V1's Combine Mode (5.5) uses a cheap trick: passing recent titles/summaries into the same LLM call rather than real similarity search. This works because a personal bot's history stays small. Once the saved-item count grows large enough that recent-history prompting gets unreliable or expensive, that's the signal to build the real version:

```
Saved Content → Summarization → Embeddings → Vector DB (pgvector) → Similarity Search
```

This is the same architecture already described in the original brainstorm's semantic search section, and Combine Mode becomes one more consumer of it — matches happen against the whole history, not just the last ~10 items.

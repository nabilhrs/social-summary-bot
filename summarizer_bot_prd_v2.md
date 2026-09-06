# PRD — Personal Content Summarizer Bot (V2)

**Status:** Draft, scoping in progress
**Owner:** Nabil
**Last updated:** 2026-09-06
**Supersedes:** `summarizer_bot_prd_v1.md` (V1 is complete and live — see `CHECKLIST.md`)

---

## 1. Where V1 landed

V1 shipped and is in daily use: paste text or a URL, get a structured
summary, it's saved to SQLite, and Combine Mode offers to merge related
saves. Five real bugs were found through live testing and fixed (see
`memory.md`). Full status is tracked in `CHECKLIST.md` — this document only
covers what's changing.

One thing V1's own design didn't anticipate: real usage turned out to be
**personal notes and tips** (job-interview advice, mixed Malay/English,
informal), not the "save a news article" scenario the original PRD's
examples assumed. That's shaped every decision below — V2 optimizes for
"my running personal knowledge base," not "my read-it-later article queue."

## 2. Goal (V2)

Turn the bot from **write-only** (you can save things, but the only way to
see what's saved is opening the `.db` file yourself) into a bot that
actually helps you use what you've saved — retrieve it, fix mistakes in it,
and extend capture to Threads/TikTok links where realistically possible.

## 3. Scope, in build order

Phased by value-to-effort, cheapest and highest-value first. Each phase is
independently shippable — nothing here depends on a later phase.

### Phase 2.1 — Platform-aware fallback for Threads / TikTok

**What this is *not*:** automated scraping of Threads or TikTok content.
V1's Appendix A already found that Meta's oEmbed terms explicitly prohibit
using post data for anything beyond rendering an embed — plugging that into
a summarizer would be a ToS violation, not just "fragile." TikTok has no
official API for this either; the only working approach is unofficial
scraping or `yt-dlp` + Whisper transcription, both fragile and a real
maintenance burden. Building either isn't the right trade-off for a
personal tool that breaks the platform's terms to do it.

**What this is:** a much better *fallback* than what exists today. Right
now, sending a Threads/TikTok link makes the bot attempt a generic
`httpx` fetch, which fails (or returns useless embed-wrapper HTML), and you
get the generic "I couldn't extract this" message. Instead:

- Detect Threads (`threads.net`, `threads.com`) and TikTok
  (`tiktok.com`, `vt.tiktok.com`) URLs by domain *before* attempting a
  generic fetch.
- Reply immediately with a platform-specific message, e.g.: *"Threads
  doesn't allow me to pull post content automatically — paste the post
  text here and I'll summarize it."*
- No wasted fetch attempt, no confusing error, and it's honest about *why*
  rather than implying it's a bug.

This is a small, safe, immediate win — it directly fixes the papercut of
today's generic failure message for the exact links you said you want to
send, without building something that breaks Meta's/TikTok's terms.

**If you still want real extraction later:** it's possible (unofficial
scraping libraries exist for both), but it should be a deliberate, separate
decision — not something bundled into a "make Threads work" ask — because
it carries real ToS and account-ban risk for personal accounts, and breaks
whenever the platform changes its defenses. Flagging this explicitly rather
than quietly deciding it for you.

### Phase 2.2 — Retrieval: `/list` and `/search`

The highest-value gap: you can save notes but never see them again inside
Telegram.

- `/list [n]` — shows the last `n` saved items (default 10, max 50), one
  line each: `#id · title-or-first-few-words · created_at date`.
- `/search <keyword>` — case-insensitive `LIKE` match across `title`,
  `summary`, and `original_text`; returns up to 10 matches in the same
  compact format as `/list`.
- Long results get truncated/paginated to stay under Telegram's 4096-char
  message limit (simple "showing 10 of 23, refine your search" note —
  no need for real pagination UI in V2).
- No schema changes — pure read queries against the existing table.

### Phase 2.3 — Manage entries: `/delete` and `/undo`

- `/delete <id>` — asks for confirmation via inline Yes/No (same pattern as
  the merge flow), then removes the row.
- `/undo <id>` — reverts a merged entry back to its pre-merge summary.
  Requires one schema addition: a nullable `previous_summary` column,
  populated with the old `summary` value at merge time (before
  overwriting). Single-level undo only (matches the rest of the app's
  "lightweight, no history stack" philosophy) — undoing twice in a row
  just restores the same pre-merge state again, it doesn't step further
  back.

### Phase 2.4 — Note-style output for short content

Right now every input gets the full `TL;DR / KEY POINTS / TAKEAWAY`
structure, which is the right call for articles but feels like overkill for
a 3-sentence tip. Proposal:

- If the input's word count is below a threshold (~80 words, tunable),
  use a compact prompt: a single short paragraph instead of the full
  three-part structure.
- Longer input (articles, or long pasted text) keeps today's format
  unchanged.
- This only touches the prompt/summarizer layer — no schema change, and
  Combine Mode's `RELATED_ID` mechanism works the same regardless of which
  format was used.

## 4. Explicitly Out of Scope (V2)

Carried over from V1 (still true), plus:
- Automated Threads/TikTok content extraction (see Phase 2.1 — a
  deliberate non-goal, not a deferral)
- Real embeddings/vector search — Combine Mode's recent-history approach
  is still working well at current volume
- Tags, categories, web dashboard, multi-user support

## 5. Open questions before implementation

- **Phase 2.4 threshold:** is ~80 words the right cutoff, or should it be
  based on something else (e.g. presence of paragraph breaks)? Can be
  tuned after seeing it in practice rather than getting it exactly right
  up front.
- **`/delete` and `/undo`:** any concern about accidentally deleting the
  wrong id? The confirmation button should cover this, but worth a
  real test before trusting it on real data (same lesson as the merge
  button bugs in `memory.md`).

## 6. Suggested build order

1. Phase 2.1 (platform-aware fallback) — smallest, no schema change, fixes
   an immediate papercut.
2. Phase 2.2 (`/list`, `/search`) — highest value, no schema change.
3. Phase 2.3 (`/delete`, `/undo`) — needs one schema addition.
4. Phase 2.4 (note-style output) — lowest urgency, purely a quality-of-life
   polish once the above are in daily use.

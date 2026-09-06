# PRD — Personal Content Summarizer Bot (V2)

**Status:** All four phases shipped, plus several user-requested additions
beyond the original scope (clickable commands, view-before-merge, manual
`/merge`, automatic paragraph/bullets, and a revised Threads approach —
see section 3 and `CHECKLIST.md` for full detail on each)
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

### Phase 2.1 — Real extraction for both Threads and TikTok

**Originally scoped as:** an honest fallback for *both* Threads and TikTok
— no extraction for either, just a fast, platform-specific "paste the text
yourself" reply instead of a doomed generic fetch. That shipped first.
TikTok video summarization was then discussed and explicitly deferred —
the user's own call when asked directly, not a technical dead end.

**Revised for Threads**, after live testing turned up a distinction the
original research missed: the "Meta prohibits this" finding was about the
**oEmbed API** specifically, whose terms restrict use to rendering an
embed. **Open Graph meta tags** (`og:title`, `og:description`) are a
different, universal web standard every site uses for link previews — the
same mechanism Slack, iMessage, and Discord use to show a preview when you
paste a link. Reading them via a normal HTTP fetch — exactly what this bot
already does for every other website — isn't the restricted mechanism at
all.

Verified live (via browser, on real public posts, before writing any
code): a Threads post permalink's raw, un-rendered HTML contains the full
caption in `og:description` — confirmed on a multi-paragraph post with an
emoji, no truncation. Also verified: **replies are not reachable this
way** — a root post's raw HTML has zero trace of its own replies' text or
ids, since Threads hydrates those entirely via client-side JS after the
page loads. Getting them would need a full headless browser or reverse-
engineering a private API — both rejected as disproportionate for what
they'd buy.

**What got built:** `app/extractors/threads.py` — reads `og:description`
(caption) and derives the author from `og:title`. A `source: "threads"`
value distinguishes these from regular web articles in `/view`.

**Correction after real-world use:** the first version tried to *detect*
a multi-part post by regex-matching numbering typed into the caption
(`(1/4)`, `part 2 of 5`). The user then hit a real post using Threads'
own **native** "1/9"-style thread badge — UI chrome computed client-side,
not text in the caption — which the regex structurally cannot see.
Investigated live: no per-post threading signal survives an
unauthenticated fetch anywhere in the raw HTML (a promising `reply_count`
match turned out to be generic app config, not real per-post data), so
detection isn't reliably achievable at all, native badge or manual
typing. Fix: removed detection entirely — the bot now unconditionally
discloses the "I can only read the linked post, not replies" limitation
on every Threads extraction, rather than gambling on catching the cases
that matter.

**Revisited: TikTok video summarization**, after the user reopened the
decision — pasting or typing a caption defeats the point of just pasting a
link, and a caption-only shortcut wouldn't actually summarize the *video*
(what's shown/said) at all, only whatever the poster happened to type.
Restated the tradeoff plainly one more time before building: unlike
Threads' Open Graph approach, this genuinely crosses TikTok's terms —
downloading video content isn't permitted, same category as `youtube-dl`.
The user weighed that against the caption-only alternative and chose to
proceed anyway.

Verified live before building: a plain fetch, and even `yt-dlp` without
its `curl-cffi` "impersonation" extra, gets blocked by TikTok's JS
bot-challenge outright — direct confirmation that TikTok resists
automated access harder than any other platform this bot touches.
Installing `yt-dlp[default,curl-cffi]` gets past it. Verified end-to-end
on a real public video: downloaded (2.2MB, 28s clip), uploaded to
Gemini's Files API, and asked to describe the actual content — the
response correctly described specific visuals (candles, a particular
necklace) and lip-synced lyrics that weren't in the caption at all,
confirming this is a real video summary, not a caption pass-through.

**What got built:** `app/extractors/tiktok.py` — downloads via yt-dlp,
uploads to Gemini, asks for a description, cleans up the temp file and
the uploaded Gemini copy in a `finally` block regardless of outcome.
Wrapped in a 120s overall timeout (video processing is much slower than
text) and a 200MB size cap. The resulting description feeds into the
*existing* summarize() pipeline unchanged — Combine Mode, the compact
short-content format, everything — since it's just plain text like every
other extractor produces, no changes needed to `app/ai/summarizer.py` or
`app/ai/prompts.py`. A "🎥 Downloading and analyzing..." message goes out
first, since silence during a 30-120s wait would look like the bot hung.

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

### Major revision — multi-user support (V1's "multi-user support beyond
one hardcoded ID" exclusion reversed)

The user asked to make the bot "publicly available to be used by anyone on
Telegram." Before writing any code, the real implications were laid out
plainly: the database had zero per-user data isolation (anyone let in
could see, search, merge, or delete *your* notes too), the owner's Gemini
API key pays for every request with no per-user cap (a public TikTok video
call is the most expensive kind), TikTok downloading at true public scale
is a materially different risk than one person's personal use, and the bot
only runs while the owner's own machine does — "public" doesn't mean
"always on" for free.

Scoped down deliberately after that: **a private allowlist of multiple
people, each with fully isolated data, no usage caps for now** — not
literally open to anyone on the internet. `AUTHORIZED_USER_IDS` (ordered,
comma-separated) replaces the single `AUTHORIZED_USER_ID`; a new `user_id`
column (backfilled via migration, owned by whichever id is listed first)
scopes every database function and every command/callback to the calling
user. Verified live with two distinct simulated users sharing one process
and database: each `/list` showed only that user's own item, and every
attempt by one user to `/view`, `/delete`, or `/merge` the *other* user's
real, existing item was correctly refused — the property this whole
change exists to guarantee.

**Consciously not built:** per-user rate limiting/usage caps, and hosting
beyond "runs on whoever starts `main.py`" — both explicitly accepted as
known gaps rather than silently ignored, since the user said not to worry
about cost right now.

## 4. Explicitly Out of Scope (V2)

Carried over from V1 (still true), plus:
- Full multi-part Threads thread stitching — not achievable without a
  headless browser or reverse-engineering a private API; the bot
  unconditionally discloses this limitation instead of guessing when it
  applies (see Phase 2.1 — detection was tried and abandoned as unreliable)
- Real embeddings/vector search — Combine Mode's recent-history approach
  is still working well at current volume
- Tags, categories, web dashboard
- Per-user rate limiting/usage caps, and dedicated hosting — both accepted
  as known gaps in the multi-user revision above, not oversights

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

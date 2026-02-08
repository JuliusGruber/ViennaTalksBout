# Implementation Plan: Mastodon (wien.rocks) Datasource

## Overview

Implement the first TalkBout datasource — a real-time ingestion pipeline that streams public posts from the **wien.rocks** Mastodon instance, extracts trending topics using Claude, and feeds them into the tag cloud.

**Why Mastodon first:** Easiest viable datasource to implement. True real-time push streaming (SSE), no polling needed. Free, mature Python library (Mastodon.py), and instance-based locality eliminates the need for geo-filtering logic.

---

## Architecture

```
wien.rocks SSE stream
        │
        ▼
┌─────────────────┐
│  Stream Client   │  Mastodon.py — persistent SSE connection
│  (Ingestion)     │  Reconnects automatically on failure
└────────┬────────┘
         │ raw posts (text, timestamp, language, id)
         ▼
┌─────────────────┐
│  Post Buffer     │  Collects posts over a configurable window
│                  │  (e.g. 5-15 min batches)
└────────┬────────┘
         │ batch of posts
         ▼
┌─────────────────┐
│  Topic Extractor │  Claude API — extracts trending topics
│  (LLM)          │  from batched post text
└────────┬────────┘
         │ topics with scores
         ▼
┌─────────────────┐
│  Topic Store     │  Persists current + historical topic state
│                  │  Powers the tag cloud + time slider
└─────────────────┘
```

---

## Implementation Phases

### Phase 1: OAuth Registration & Configuration

**Goal:** Obtain credentials to connect to the wien.rocks streaming API.

**Steps:**

1. Register an OAuth application on wien.rocks
   - Navigate to `https://wien.rocks/settings/applications/new`
   - App name: `TalkBout` (or similar descriptive name)
   - Scopes needed: `read` (specifically `read:statuses`)
   - Redirect URI: `urn:ietf:wg:oauth:2.0:oob` (for local dev)
2. Store credentials securely
   - Client ID, client secret, and access token
   - Use environment variables or a `.env` file (excluded from version control)
3. Verify access by calling `GET /api/v1/instance` on wien.rocks

**Deliverable:** Working OAuth token that can authenticate against wien.rocks API.

**Note:** Use the authorization code flow, not `client_credentials` — the latter may not work with streaming (see Mastodon GitHub issue #24116).

---

### Phase 2: Stream Client (Ingestion)

**Goal:** Establish a persistent SSE connection to the `public:local` stream on wien.rocks and receive posts in real time.

**Steps:**

1. Install dependencies
   - `Mastodon.py` (v2.1.4+) — handles SSE streaming, auth, and rate limits
2. Create a stream listener class
   - Extend `mastodon.StreamListener`
   - Implement `on_update(status)` — called for each new public post
   - Implement `on_abort(err)` — called on stream errors
3. Connect to the `public:local` stream
   - Use `mastodon.stream_public(listener, local=True, run_async=True, reconnect_async=True)`
   - `local=True` restricts to wien.rocks posts only (geographic proxy)
   - `reconnect_async=True` enables automatic reconnection on disconnects
4. Extract relevant fields from each status
   - `status['content']` — HTML content (strip tags to plain text)
   - `status['created_at']` — timestamp
   - `status['language']` — language code (expect mostly `de`)
   - `status['id']` — unique post ID (for deduplication)
   - `status['sensitive']` / `status['spoiler_text']` — content warning flags
5. Filter out unwanted posts
   - Skip reblogs (`status['reblog'] is not None`)
   - Skip posts with empty text content after HTML stripping
   - Optionally skip posts flagged as sensitive

**Key considerations:**
- **No catch-up on reconnect** — Mastodon SSE does not replay missed events. Accept data gaps during disconnects; this is acceptable for an MVP showing trending topics.
- **HTML stripping** — Post content is HTML. Use a library like `BeautifulSoup` or `html2text` to extract plain text.
- **Volume** — Expect ~10 posts/hour average, ~17/hour during European daytime (06:00-22:00 CET).

**Deliverable:** A running process that prints incoming wien.rocks posts to stdout in real time.

---

### Phase 3: Post Buffer

**Goal:** Batch incoming posts into time windows for efficient LLM processing.

**Steps:**

1. Implement an in-memory buffer that accumulates posts over a configurable time window
   - Default window: 10 minutes (tunable)
   - At ~10 posts/hour, a 10-min window yields ~1-3 posts per batch on average
2. On window expiry, emit the batch for topic extraction and start a new window
3. Handle edge cases
   - Empty batches (no posts in window) — skip LLM call
   - Very active periods — cap batch size if needed to control LLM costs
4. Include metadata with each batch
   - Window start/end timestamps
   - Post count
   - Source identifier (`mastodon:wien.rocks`)

**Design decision — batch window size:**
- Shorter windows (5 min) = more responsive topic updates, more LLM calls, higher cost
- Longer windows (15-30 min) = lower cost, but topics update sluggishly
- 10 minutes is a reasonable starting point; tune based on observed behavior

**Deliverable:** Buffering layer that groups posts into timed batches.

---

### Phase 4: Topic Extraction (LLM)

**Goal:** Use Claude to extract trending topics from batched posts.

**Steps:**

1. Design the extraction prompt
   - Input: batch of plain-text posts from wien.rocks
   - Output: structured list of topics with relevance scores
   - Instruct the LLM to extract specific, concrete topics (e.g. "U2 Stoerung", "Donauinselfest") not broad categories (e.g. "politics", "weather")
   - Handle German-language content — prompt should specify that input is primarily German
2. Call the Claude API
   - Use the Anthropic Python SDK
   - Model: choose based on cost/quality tradeoff (Haiku for cost efficiency, Sonnet for quality)
   - Structured output: request JSON with topic name, score, and optional category
3. Parse and validate the LLM response
   - Ensure response is valid JSON
   - Validate topic list is non-empty (unless the batch had no meaningful content)
   - Handle LLM errors/timeouts gracefully

**Example prompt structure:**

```
You are analyzing social media posts from Vienna, Austria (from the wien.rocks Mastodon instance).
Extract the specific topics people are discussing. Return concrete, specific topic terms
(e.g. "Donauinselfest", "U2 Stoerung") not broad categories.

Posts:
{batch_text}

Return JSON: [{"topic": "...", "score": 0.0-1.0, "count": N}, ...]
```

**Deliverable:** Function that takes a batch of posts and returns a list of extracted topics.

---

### Phase 5: Topic Store & State Management

**Goal:** Maintain current and historical topic state to power the tag cloud and time slider.

**Steps:**

1. Define the topic data model
   - Topic name (string)
   - Current score / weight (float) — drives tag size in the cloud
   - First seen timestamp
   - Last seen timestamp
   - Source (`mastodon:wien.rocks`)
   - Lifecycle state: `entering` | `growing` | `shrinking` | `disappeared`
2. Implement topic merging logic
   - When new topics arrive from the LLM, merge with existing topics
   - Matching topics: update score, refresh `last_seen`
   - New topics: add with `entering` state
   - Stale topics (not seen in recent batches): begin `shrinking`, eventually `disappeared`
3. Maintain a maximum of 20 active topics
   - When a new topic enters and 20 are already active, the lowest-scoring topic transitions to `shrinking`/`disappeared`
4. Persist hourly snapshots for the time slider
   - Store the topic set at each hour boundary
   - Storage: start with file-based (JSON) for MVP; migrate to a database later
5. Expose the current topic state for the frontend
   - API endpoint or in-memory state accessible to the web layer

**Deliverable:** Topic store that tracks the 20 active topics with lifecycle states and hourly history.

---

### Phase 6: Integration & End-to-End Pipeline

**Goal:** Wire all components together into a running pipeline.

**Steps:**

1. Create the main application entry point
   - Start the stream client
   - Connect it to the post buffer
   - Connect the buffer to the topic extractor
   - Connect the extractor to the topic store
2. Add configuration management
   - Instance URL (`https://wien.rocks`)
   - OAuth credentials (from environment)
   - Buffer window duration
   - LLM model selection
   - Topic retention settings
3. Add logging
   - Log stream connection/disconnection events
   - Log batch processing (post count, topics extracted)
   - Log errors and retries
4. Add basic health monitoring
   - Track time since last received post (detect stale connections)
   - Track LLM call success/failure rate

**Deliverable:** A single command (`python -m talkbout.ingest`) that starts the full Mastodon ingestion pipeline.

---

## Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Language | Python | Mastodon.py and Anthropic SDK are both Python-native |
| Streaming library | Mastodon.py 2.1.4 | Mature, handles SSE + auth + reconnection |
| HTML stripping | BeautifulSoup4 | Reliable, widely used |
| LLM | Claude (Haiku or Sonnet) | Project already uses Claude; Haiku for cost, Sonnet for quality |
| Storage (MVP) | File-based JSON | Simple, no infrastructure; migrate to DB later |
| Config | Environment variables + `.env` | Standard Python practice, 12-factor app |

## Dependencies

```
Mastodon.py>=2.1.4
anthropic>=0.40.0
beautifulsoup4>=4.12.0
python-dotenv>=1.0.0
```

## Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| wien.rocks goes down | No data ingestion | Log alerts; pipeline resumes automatically on reconnect; accept data gaps for MVP |
| OAuth token expires/revoked | Stream disconnects | Monitor connection health; document token refresh procedure |
| Low post volume (holidays/nights) | Sparse topics | Extend batch windows during low-activity periods; combine with Reddit source (Phase 2 datasource) |
| LLM extracts poor topics | Bad tag cloud quality | Iterate on prompt; add human review during early testing; tune score thresholds |
| Mastodon.py SSE reconnect fails | Missed posts | Add watchdog that restarts the stream client after prolonged silence |

## Out of Scope (for this plan)

- Reddit datasource (separate implementation plan)
- Frontend tag cloud rendering
- Deployment / hosting infrastructure
- User-facing API design
- Multi-region support

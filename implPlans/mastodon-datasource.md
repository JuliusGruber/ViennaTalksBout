# Implementation Plan: Mastodon (wien.rocks) Datasource

## Overview

Implement the first ViennaTalksBout datasource — a real-time ingestion pipeline that streams public posts from the **wien.rocks** Mastodon instance, extracts trending topics using Claude, and feeds them into the tag cloud.

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
   - App name: `ViennaTalksBout` (or similar descriptive name)
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

**Deliverable:** A single command (`python -m viennatalksbout.ingest`) that starts the full Mastodon ingestion pipeline.

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

### Dev Dependencies

```
pytest>=8.0.0
pytest-cov>=5.0.0
pytest-asyncio>=0.23.0
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

---

## Plan Review: Inconsistencies & Missing Concepts

The following issues were identified during a review of this implementation plan against the product spec (`specs/product-idea.md`) and the datasource analysis (`research/datasource-implementation-analysis.md`).

### Inconsistencies

1. **No testing strategy.** The plan defines 6 implementation phases but none mention writing tests. Every component (stream client, post buffer, topic extractor, topic store, integration) needs automated tests. See the [Test Coverage Requirement](#test-coverage-requirement) section below.

2. **Thread safety not addressed.** Phase 2 uses `run_async=True` (spawns a background thread), and Phase 3 describes an in-memory buffer. The stream listener writes to the buffer from one thread while the timer reads and flushes it from another. The plan does not mention thread-safe access (locks, queues, or thread-safe data structures).

3. **Topic matching is undefined.** Phase 5 says "Matching topics: update score, refresh `last_seen`" but never defines what "matching" means. The LLM may return `"U2 Störung"` in one batch and `"U2 Stoerung"` or `"U-Bahn Störung"` in the next. Without normalization or fuzzy matching, these would be treated as separate topics, fragmenting the tag cloud.

4. **Lifecycle state transitions are incomplete.** Phase 5 defines four states (`entering`, `growing`, `shrinking`, `disappeared`) but does not specify transition rules:
   - When does `entering` become `growing`? After N batches? After a score threshold?
   - How many consecutive "not seen" batches before `shrinking` begins?
   - When does `shrinking` become `disappeared`? After a time threshold? When score reaches zero?

5. **"Active topics" definition is ambiguous.** Phase 5 says "Maintain a maximum of 20 active topics" but does not clarify whether `shrinking` topics count toward the 20. If they do, the visible cloud could be dominated by fading-out topics with few growing ones. If they don't, more than 20 topics might be visible simultaneously during transitions.

6. **Sensitive post handling is undecided.** Phase 2 says "Optionally skip posts flagged as sensitive" — this should be a definitive design decision, not left optional, since it affects the kind of content that reaches the tag cloud.

7. **The `public:local` stream may not require OAuth.** The Mastodon API documentation indicates that the `public` and `public:local` streaming endpoints are accessible without authentication. Phase 1 assumes OAuth is required for streaming, but it may only be needed for authenticated endpoints. This should be verified — if unauthenticated access works, Phase 1 simplifies significantly.

### Missing Concepts

8. **No Python package structure defined.** Phase 6 references `python -m viennatalksbout.ingest` but the plan never defines the package layout (module names, directory structure, `__init__.py` files). This is needed before any code is written.

9. **No datasource abstraction layer.** The datasource analysis (`datasource-implementation-analysis.md`) confirms Reddit as the second MVP source. The Mastodon implementation should define a common interface (e.g., `BaseDatasource` with `start()`, `stop()`, `on_batch()`) so that Reddit (and future sources) can plug in without refactoring the pipeline. This is absent from the plan.

10. **No error handling / retry strategy for the Claude API.** Phase 4 says "Handle LLM errors/timeouts gracefully" but does not describe what happens when a call fails. Should it retry? How many times? What happens to the batch — is it dropped, re-queued, or merged into the next window? API rate limits from Anthropic are also not mentioned.

11. **No input validation on Mastodon status objects.** Phase 2 lists fields to extract (`content`, `created_at`, `language`, `id`) but does not account for missing or malformed fields. Real-world SSE data can have `null` language codes, missing content, or unexpected structures.

12. **Frontend API contract not defined.** Phase 5 says "Expose the current topic state for the frontend — API endpoint or in-memory state accessible to the web layer." While the frontend itself is out of scope, the backend must define *how* it exposes data (REST endpoint? WebSocket? file polling?). Without this, the topic store has no defined consumer interface.

13. **No data retention / cleanup policy.** Phase 5 mentions persisting hourly snapshots as JSON files but does not specify how long they are kept. Without a cleanup policy, snapshot files accumulate indefinitely on disk.

14. **Missing `html.parser` or `lxml` dependency.** BeautifulSoup4 requires a parser backend. The dependencies list includes `beautifulsoup4` but not the parser. If using the built-in `html.parser`, this should be documented explicitly. If using `lxml`, it must be added to the dependency list.

15. **No graceful shutdown handling.** Phase 6 describes starting the pipeline but not stopping it. The plan should address signal handling (`SIGTERM`, `SIGINT`), flushing the current buffer before exit, and cleanly closing the SSE connection.

---

## Test Coverage Requirement

**All code must be covered by tests.** No phase is considered complete until its components have corresponding automated tests. This applies to every module, function, and class introduced in the implementation.

### Testing Principles

- **Unit tests** for all individual functions and classes (stream listener, buffer, topic extractor, topic store, merging logic)
- **Integration tests** for component interactions (stream → buffer → extractor → store pipeline)
- **Mock external dependencies** — Mastodon SSE stream, Claude API, and file I/O must be mocked in tests so the test suite runs without network access or API keys
- **Edge case coverage** — empty batches, malformed HTML, null fields, LLM returning invalid JSON, concurrent buffer access, etc.
- **Test framework:** `pytest` (add to dependencies)
- **Coverage target:** aim for ≥90% line coverage; all public functions must have at least one test

### Test Dependencies (add to dev dependencies)

```
pytest>=8.0.0
pytest-cov>=5.0.0
pytest-asyncio>=0.23.0  # if async patterns are used
```

---

## Implementation Checklist

Check off each item as it is completed. A phase is only done when all its items — including tests — are checked.

### Phase 1: OAuth Registration & Configuration ✓

- [x] Register OAuth application on wien.rocks (`read:statuses` scope)
- [x] Verify whether `public:local` stream actually requires OAuth (see review item 7)
- [x] Store credentials in `.env` file (add `.env` to `.gitignore`)
- [x] Verify access by calling `GET /api/v1/instance`
- [x] Document the OAuth flow steps (authorization code exchange, token storage)
- [x] Write tests: config loading, credential validation, `.env` parsing

### Phase 2: Stream Client (Ingestion) ✓

- [x] Define Python package structure (`viennatalksbout/` package, module layout)
- [x] Define a `BaseDatasource` abstract interface for future datasource reuse
- [x] Install `Mastodon.py` and `beautifulsoup4` (with explicit parser choice)
- [x] Implement `StreamListener` subclass with `on_update()` and `on_abort()`
- [x] Implement HTML-to-plain-text stripping
- [x] Implement post filtering (reblogs, empty content, sensitive — make a definitive decision)
- [x] Implement input validation for status fields (handle `null` language, missing content)
- [x] Write tests: listener callback handling, HTML stripping, post filtering, field validation
- [x] Write tests: mock SSE stream delivering sample statuses end-to-end

### Phase 3: Post Buffer ✓

- [x] Implement thread-safe in-memory buffer (use `queue.Queue` or `threading.Lock`)
- [x] Implement configurable time window with timer-based flush
- [x] Handle edge cases: empty batches (skip), oversized batches (cap)
- [x] Include batch metadata (window start/end, post count, source identifier)
- [x] Write tests: buffer accumulation, window expiry, empty window handling
- [x] Write tests: thread safety — concurrent writes and reads
- [x] Write tests: batch metadata correctness

### Phase 4: Topic Extraction (LLM) ✓

- [x] Design and document the extraction prompt (German-language handling, concrete topics)
- [x] Implement Claude API call using Anthropic Python SDK
- [x] Choose model (Haiku vs. Sonnet) and document the decision
- [x] Use structured output (tool use / JSON mode) instead of free-text JSON parsing
- [x] Implement response parsing and validation (valid JSON, non-empty topic list)
- [x] Implement error handling: retry logic (with backoff), behavior on repeated failures
- [x] Define what happens to a batch when the LLM call fails (drop / re-queue / merge)
- [x] Write tests: prompt construction with various batch inputs
- [x] Write tests: response parsing — valid JSON, malformed JSON, empty response
- [x] Write tests: retry logic and error handling (mock API failures, timeouts, rate limits)

### Phase 5: Topic Store & State Management ✓

- [x] Define topic data model (name, score, first_seen, last_seen, source, lifecycle state)
- [x] Implement topic matching strategy (define normalization / fuzzy matching approach)
- [x] Implement topic merging logic (new, updated, stale topics)
- [x] Define and implement lifecycle state transition rules with explicit thresholds
- [x] Clarify "active topics" definition — whether `shrinking` counts toward the 20 cap
- [x] Implement 20-topic cap with eviction of lowest-scoring topic
- [x] Implement hourly snapshot persistence (JSON files)
- [x] Implement snapshot retention / cleanup policy
- [x] Define the API contract for frontend consumption (REST, WebSocket, or other)
- [x] Write tests: topic merging — new topics, updated topics, stale topic decay
- [x] Write tests: lifecycle state transitions through all states
- [x] Write tests: 20-topic cap and eviction ordering
- [x] Write tests: snapshot persistence and loading
- [x] Write tests: snapshot cleanup policy

### Phase 6: Integration & End-to-End Pipeline ✓

- [x] Create main entry point (`python -m viennatalksbout.ingest`)
- [x] Wire all components: stream → buffer → extractor → store
- [x] Implement configuration management (instance URL, credentials, buffer window, model, retention)
- [x] Implement structured logging (use Python `logging` module, define log format)
- [x] Implement health monitoring (last post timestamp, LLM success/failure rate)
- [x] Implement graceful shutdown (signal handling, buffer flush, SSE disconnect)
- [x] Write integration tests: full pipeline with mocked Mastodon stream and mocked Claude API
- [x] Write tests: configuration loading and validation
- [x] Write tests: health monitoring thresholds and alerts
- [x] Write tests: graceful shutdown flushes buffer and closes connections
- [x] Verify ≥90% test coverage across all modules (`pytest --cov`)

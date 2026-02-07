# Datasource Implementation Analysis

> Which datasource (excluding X/Twitter) is the easiest to implement?

## Ranking: Easiest to Hardest

### 1. Bluesky Jetstream — Easiest ✦

| Factor | Detail |
|---|---|
| **Authentication** | None required — 4 public Jetstream instances |
| **Real-time** | Yes — lightweight JSON WebSocket stream |
| **Rate limits** | Most permissive: 3,000 req/5 min (PDS); Jetstream uses persistent connections, no per-request limits |
| **Cost** | Free |
| **Data format** | Clean JSON, ~850 MB/day for all posts (~56% smaller with zstd compression) |
| **Libraries needed** | Standard WebSocket client — no special SDK required |
| **Geo-filtering** | Not native; requires post-processing (keyword/LLM-based) |
| **Data integrity** | Jetstream data is not self-authenticating (no cryptographic signatures) — acceptable for read-only ingestion |

**Why it's easiest:** Zero authentication, no SDK dependency, persistent WebSocket avoids rate-limit concerns, well-documented lightweight JSON format. Connect to a public instance and start receiving posts immediately.

---

### 2. Mastodon — Easy

| Factor | Detail |
|---|---|
| **Authentication** | OAuth (straightforward) |
| **Real-time** | Yes — Streaming API (SSE/WebSocket), exempt from per-request rate limits |
| **Rate limits** | 300 req/5 min per user; streaming bypasses this |
| **Cost** | Free |
| **Libraries** | `Mastodon.py` — mature, auto rate-limit handling (`wait`/`pace`/`throw` modes) |
| **Geo advantage** | **vienna.social** instance provides pre-filtered local content |
| **Audience** | Smaller than other platforms |

**Why it's easy:** The `vienna.social` instance eliminates the need for geo-filtering entirely. `Mastodon.py` handles auth and rate limiting automatically. Streaming API provides real-time data via persistent connections.

---

### 3. Reddit — Moderate

| Factor | Detail |
|---|---|
| **Authentication** | OAuth client registration required (app approval process) |
| **Real-time** | Subreddit streaming via PRAW |
| **Rate limits** | 60 req/min (OAuth); PRAW auto-sleeps; some undocumented limits on certain actions |
| **Cost** | Free |
| **Libraries** | `PRAW` — well-maintained, handles auth and rate limiting |
| **Geo sources** | r/vienna, r/austria |
| **Risk** | Reddit has been tightening API access policies |

**Why it's moderate:** More involved OAuth setup and approval process. Tighter, occasionally unpredictable rate limits. PRAW smooths over complexity but the registration overhead is real.

---

### 4. News & Blogs (RSS) — Moderate

| Factor | Detail |
|---|---|
| **Authentication** | None |
| **Real-time** | No — polling only |
| **Rate limits** | Informal (polite polling intervals) |
| **Cost** | Free |
| **Targets** | derstandard.at, orf.at, krone.at, kurier.at |
| **Complexity** | RSS structures vary per site; content extraction requires per-source parsing; polling scheduler needed |

**Why it's moderate:** No auth needed, but no unified API either. Per-site feed parsing, variable RSS formats, and partial-content feeds requiring additional scraping add up.

---

### 5. Google Trends / Autocomplete — Moderate-to-Hard

| Factor | Detail |
|---|---|
| **Authentication** | API key or unofficial library |
| **Real-time** | No |
| **Data type** | Aggregate trends, not individual posts |
| **Stability** | Unofficial libraries (e.g., `pytrends`) break frequently when Google changes endpoints |

**Why it's harder:** Useful as a supplementary signal, but unreliable as a primary datasource. Official API is limited; unofficial libraries are fragile.

---

### 6. Local Forums (willhaben, Facebook groups, Nextdoor) — Hardest

| Factor | Detail |
|---|---|
| **Authentication** | Varies; often no public API |
| **Real-time** | No |
| **Implementation** | Web scraping required; no documented APIs |
| **Risk** | ToS violations; fragile to site changes; potential legal issues |

**Why it's hardest:** High engineering effort, high maintenance burden, significant legal/ToS risk. Last priority.

---

## Recommendation

**Start with Bluesky Jetstream:**
- Zero auth, zero API key, zero SDK dependency
- Connect a WebSocket to a public endpoint → receive JSON
- Add a Vienna-content filter (keyword or LLM-based) as a second step

**Follow with Mastodon (vienna.social):**
- Curated local content with minimal filtering
- Mature Python library handles everything

These two together provide a **real-time, free, low-complexity dual-source pipeline** with strong Vienna relevance — the fastest path to a working prototype.

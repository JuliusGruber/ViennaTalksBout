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
| **Geo-filtering** | **None** — no native geo support and no structural locality mechanism. Does not meet ViennaTalksBout's must-have geolocation filtering requirement |
| **Data integrity** | Jetstream data is not self-authenticating (no cryptographic signatures) — acceptable for read-only ingestion |

**Why it's technically simple:** Zero authentication, no SDK dependency, persistent WebSocket avoids rate-limit concerns, well-documented lightweight JSON format. Connect to a public instance and start receiving posts immediately.

**⚠ Blocker:** Despite being the simplest to implement, Bluesky lacks any geolocation filtering — a must-have requirement for ViennaTalksBout data sources. There is no native geo support and no structural locality mechanism (unlike subreddit- or instance-based filtering). This makes Bluesky unsuitable as a ViennaTalksBout data source until the community location schemas reach mainstream adoption.

---

### 2. Mastodon — Easy

| Factor | Detail |
|---|---|
| **Authentication** | OAuth (straightforward) |
| **Real-time** | Yes — Streaming API (SSE/WebSocket), exempt from per-request rate limits |
| **Rate limits** | 300 req/5 min per user; streaming bypasses this |
| **Cost** | Free |
| **Libraries** | `Mastodon.py` — mature, auto rate-limit handling (`wait`/`pace`/`throw` modes) |
| **Geo advantage** | **wien.rocks** instance provides pre-filtered local content |
| **Audience** | Smaller than other platforms |

**Why it's easy:** The `wien.rocks` instance eliminates the need for geo-filtering entirely. `Mastodon.py` handles auth and rate limiting automatically. Streaming API provides real-time data via persistent connections.

---

### 3. Reddit — Moderate

| Factor | Detail |
|---|---|
| **Authentication** | OAuth client registration required (app approval process) |
| **Real-time** | Subreddit streaming via PRAW |
| **Rate limits** | 60 req/min (OAuth); PRAW auto-sleeps; some undocumented limits on certain actions |
| **Cost** | Free |
| **Libraries** | `PRAW` — well-maintained, handles auth and rate limiting |
| **Geo sources** | r/wien (~204k members, primary), r/austria (~645k members, secondary). Note: r/vienna (~3.9k) is deprecated and migrating to r/wien |
| **Risk** | Reddit has been tightening API access policies |

**Why it's moderate:** More involved OAuth setup and approval process. Tighter, occasionally unpredictable rate limits (60-100 QPM). PRAW smooths over complexity but the registration overhead is real. PRAW streaming is polling-based (2-16 sec latency), not true push. See `research/reddit-research.md` for details.

---

### 4. News & Blogs (RSS) — Moderate

| Factor | Detail |
|---|---|
| **Authentication** | None |
| **Real-time** | No — polling only |
| **Rate limits** | Informal (polite polling intervals) |
| **Cost** | Free |
| **Targets** | orf.at (Vienna feed: `rss.orf.at/wien.xml`), vienna.at, krone.at, kurier.at, derstandard.at, heute.at, ots.at |
| **Geo-filtering** | **Good** — orf.at, krone.at, kurier.at have Vienna-specific feeds; vienna.at/heute.at are inherently Vienna-focused |
| **Complexity** | RSS structures vary per site (RDF 1.0 vs RSS 2.0); all feeds are summary-only; polling scheduler needed |

**Why it's moderate:** No auth needed, but no unified API either. Variable RSS formats (orf.at uses RDF 1.0 for national, RSS 2.0 for regional). All feeds provide summaries only — RSS summaries are likely sufficient for LLM topic extraction without full-article scraping. Estimated ~130-250 Vienna-relevant articles/day. See `research/austrian-news-rss.md` for detailed feed URLs, formats, and volume estimates.

---

### 5. Google Trends / Autocomplete — Moderate-to-Hard

| Factor | Detail |
|---|---|
| **Authentication** | Official API (closed alpha, unavailable); unofficial libraries or paid scraping services |
| **Real-time** | Trending Now refreshes ~every 10 min; Autocomplete is near-instantaneous |
| **Data type** | Aggregate trends, not individual posts |
| **Geo-filtering** | Austria-level (`AT`) for Trending Now; Vienna-level (`AT-9`) for Explore only. **Does not fully meet must-have** for real-time Vienna-specific trends |
| **Stability** | pytrends is **dead** (archived April 2025); trendspyg is v0.3.0 (early, fragile). Google deployed SearchGuard anti-bot (Jan 2025) |
| **Legal risk** | Google filed DMCA lawsuit against SerpApi (Dec 2025); ToS explicitly prohibits scraping |

**Why it's harder:** Official API is closed alpha (expected public late 2026/early 2027). Unofficial tools are fragile and face escalating anti-bot measures. Best suited as a future supplementary source, not MVP. See `research/google-trends-research.md` for details.

---

### 6. Local Forums & Community Platforms — Hardest

| Factor | Detail |
|---|---|
| **Authentication** | Varies; most have no public API |
| **Real-time** | No (except Telegram via Telethon) |
| **Implementation** | Web scraping required for most; Telegram has unofficial library access |
| **Risk** | Explicit ToS prohibitions on scraping; Austrian GDPR enforcement is strict (Dec 2025 Supreme Court ruling) |
| **Key platforms** | Jodel (hyperlocal, no API), derstandard.at comments (30k/day, no API), meinbezirk.at (643k users/mo, no API), Telegram Vienna groups (Telethon works, ToS prohibits) |
| **Not viable** | Nextdoor (not in Austria), Facebook Groups (API removed Apr 2024), Discord (tiny communities) |

**Why it's hardest:** High engineering effort, high maintenance burden, significant legal/ToS risk. The most relevant platform for Vienna (Jodel — hyperlocal anonymous app with GPS geofencing) has no API and explicitly prohibits scraping. Monitor Jodel for future API availability. See `research/local-forums-research.md` for details.

---

## Decision

**Mastodon (wien.rocks)** and **Reddit (r/wien + r/austria)** are the two data sources for the ViennaTalksBout MVP.

| Source | Geo-Filtering | Real-Time | Volume | Cost | Implementation |
|--------|--------------|-----------|--------|------|----------------|
| **Mastodon (wien.rocks)** | Instance-based locality | True SSE push, sub-second latency | ~248 posts/day | Free | Easy — Mastodon.py |
| **Reddit (r/wien + r/austria)** | Subreddit-based locality | Polling via PRAW, 2-16 sec latency | ~100-800 items/day | Free | Moderate — OAuth + PRAW |

Both meet the must-have geolocation filtering requirement through structural locality. Both are free, have mature Python libraries, and support real-time or near-real-time ingestion.

**News/RSS feeds** are a strong candidate for a third source post-MVP (Vienna-specific feeds from orf.at, krone.at, kurier.at, vienna.at; ~130-250 articles/day; no auth needed). See `research/austrian-news-rss.md`.

**Not selected for MVP:**
- **Bluesky** — no geolocation filtering at any level (see `research/bluesky-geolocation.md`)
- **Google Trends** — Austria-level only for real-time trends, fragile tooling (see `research/google-trends-research.md`)
- **Local forums** — no accessible APIs, high legal risk (see `research/local-forums-research.md`)

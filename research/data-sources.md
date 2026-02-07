# Data Sources Research

Research into potential data sources for TalkBout — a real-time tag cloud showing what Vienna is talking about.

## MVP Data Sources

### Social Media Platforms

| Platform | API | Real-Time Support | Notes |
|----------|-----|-------------------|-------|
| X (Twitter) | X API v2 | Filtered Stream endpoint | Geo-filtering for Vienna available; rate limits vary by access tier |
| Reddit | Reddit API | Subreddit streaming via PRAW | r/vienna, r/austria — useful for local discussion threads |
| Mastodon | Mastodon API | Streaming API built-in | vienna.social instance is a strong local source |
| Bluesky | Bluesky AT Protocol | Firehose / Jetstream | Growing user base; geo-filtering requires post-processing |

### Rate Limits by Platform

#### X (Twitter) API v2

Access depends on paid tier — rate limits are per 15-minute window unless noted otherwise.

| Tier | Price | Monthly Read Cap | Filtered Stream | Search | Notes |
|------|-------|-----------------|-----------------|--------|-------|
| Free | $0 | 0 (write-only) | ❌ | ❌ | Not usable for ingestion |
| Basic | $200/mo | 15,000 tweets | ❌ | Recent (7 days), 15 req/15 min | Insufficient for real-time |
| Pro | $5,000/mo | 1,000,000 tweets | ✅ 1,000 rules, 250 posts/sec | Full-archive, 1 req/sec | Minimum viable tier for TalkBout |
| Enterprise | Custom | Custom | ✅ | ✅ | Dedicated support |

Key endpoint limits (Pro tier):
- Tweets lookup: 5,000 req/15 min (per user), 3,500 req/15 min (per app)
- Filtered Stream rules: 50 req/15 min, max 1,000 rules, 1,024 char rule length
- Post creation: 100 req/15 min (per user)
- HTTP 429 returned when limits exceeded; resets after 15-minute window

Source: [X API Rate Limits](https://docs.x.com/x-api/fundamentals/rate-limits), [X API Pricing](https://twitterapi.io/blog/twitter-api-pricing-2025)

#### Reddit API

| Auth Type | Rate Limit | Window |
|-----------|-----------|--------|
| Unauthenticated | 10 req/min | Rolling |
| OAuth-authenticated | 60 req/min | 10-min rolling window |

- Limits are **per OAuth client** (each registered app gets its own quota)
- Recommended practical throughput: **50–55 req/min** to avoid accidental overages
- PRAW (Python Reddit API Wrapper) handles rate limiting automatically; default `ratelimit_seconds` is 5s — will sleep and retry if wait time is ≤ 5s, otherwise raises `RedditAPIException`
- Some actions (commenting, editing, banning) have additional undocumented rate limits

Source: [PRAW Rate Limits Docs](https://praw.readthedocs.io/en/stable/getting_started/ratelimits.html), [Reddit API Rate Limits Guide](https://painonsocial.com/blog/reddit-api-rate-limits-guide)

#### Mastodon API

| Limit Type | Rate Limit | Window |
|-----------|-----------|--------|
| Per-user (all endpoints) | 300 req / 5 min (~1 req/sec) | 5 min |
| Per-IP | 7,500 req / 5 min | 5 min |
| Media upload | 30 req / 30 min | 30 min |
| Account creation | 5 req / 30 min | 30 min |

- **Streaming API** (SSE/WebSocket) uses persistent connections and is **not subject to per-request rate limits** — ideal for real-time ingestion
- Limits can vary per instance (vienna.social may differ from defaults)
- Mastodon.py supports three rate-limit modes: `throw`, `wait` (default), and `pace`
- Limits refresh every 5 minutes

Source: [Mastodon Rate Limits Docs](https://docs.joinmastodon.org/api/rate-limits/)

#### Bluesky (AT Protocol)

| Limit Type | Rate Limit | Window |
|-----------|-----------|--------|
| Overall API requests (PDS) | 3,000 req / 5 min | Per IP |
| Session creation | 30 req / 5 min, 300/day | Per account |
| Content write ops | 5,000 points/hr, 35,000 points/day | Per account (CREATE=3pts, UPDATE=2pts, DELETE=1pt) |
| Relay stream events | 50/sec, 1,500/hr, 10,000/day | Per account |

**Firehose / Jetstream** (for real-time ingestion):
- Firehose: full binary stream of all network events; sustained **2,000+ events/sec** across network; ~232 GB/day at peak
- **Jetstream** (recommended): lightweight JSON alternative; ~850 MB/day for all posts; zstd compression reduces by ~56%; 4 official public instances available; **no authentication required**
- Jetstream data is **not self-authenticating** (no cryptographic signatures) — acceptable tradeoff for read-only ingestion
- Geo-filtering must be done post-processing (no native geo support)

Source: [Bluesky Rate Limits](https://docs.bsky.app/docs/advanced-guides/rate-limits), [Bluesky Firehose](https://docs.bsky.app/docs/advanced-guides/firehose), [Jetstream](https://github.com/bluesky-social/jetstream)

### Key Considerations (MVP)

- **Rate limits**: See detailed breakdown above — X requires Pro tier ($5k/mo) for filtered streaming; Reddit and Mastodon have moderate limits suitable for polling; Bluesky Jetstream is the most permissive for real-time use
- **Geo-filtering**: Not all platforms support native location filtering — may need LLM-based or heuristic filtering to isolate Vienna-related content
- **Language**: Posts will be in German and English; the LLM extraction step must handle both
- **Cost**: X API Pro tier ($5,000/mo) is the main cost driver; Reddit, Mastodon, and Bluesky APIs are free

## Future Data Sources

### News & Blogs

- **Austrian news sites**: derstandard.at, orf.at, krone.at, kurier.at
- **RSS feeds**: Many outlets offer RSS for headlines and articles
- **Approach**: Periodic polling or RSS ingestion rather than real-time streaming

### Local Forums & Community Platforms

- **willhaben.at**: Marketplace activity can reflect local trends
- **Vienna community forums**: Smaller niche forums and Facebook groups
- **Nextdoor**: Neighborhood-level discussions

### Search & Trend Data

- **Google Trends**: Regional interest data for Austria / Vienna
- **Google Autocomplete API**: Reflects what people are actively searching for

## Open Questions

- Which platform provides the best signal-to-noise ratio for Vienna-specific topics?
- What is the minimum viable ingestion rate to produce a meaningful tag cloud?
- How should we handle duplicate or cross-posted content across platforms?
- What is the licensing / terms-of-service status for each API regarding public display of derived data?

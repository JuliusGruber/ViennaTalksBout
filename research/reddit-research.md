# Reddit as a Data Source for ViennaTalksBout — In-Depth Research

Research date: 2026-02-07

---

## 1. Reddit API Access in 2026

### Background: The 2023 API Controversy

On April 18, 2023, Reddit announced it would begin charging for API access, which had been free since 2008. The pricing of $0.24 per 1,000 API calls (effective July 1, 2023) triggered a massive subreddit blackout protest and the shutdown of most major third-party clients (Apollo, Reddit is Fun, Sync).

### Current Pricing Structure (2025-2026)

The **$0.24 per 1,000 API calls** rate remains unchanged through 2026.

**Free Tier** — still exists with restrictions:
- **100 queries per minute (QPM)** for OAuth-authenticated clients (per OAuth client ID, averaged over 10-minute window)
- **10 req/min** for unauthenticated requests
- Restricted to **non-commercial use only**: personal projects, academic research, hobby work
- No commercial data usage; cannot resell data
- Limited access to historical data

**Commercial/Enterprise Access:**
- Starting at approximately **$12,000/year**
- Per-call rate of **$0.24 per 1,000 API calls** for commercial applications
- High-volume usage requires individual enterprise negotiations
- Volume discounts start at millions of requests monthly

**ViennaTalksBout classification question:** Reddit's terms define commercial as "mobile apps with ads, services with paywalls, or any monetized products." A free, open, non-monetized website likely qualifies for the free tier. However, Reddit's May 2024 Public Content Policy states that any company wanting to use data to "power, augment or enhance products for commercial purposes" needs a contract.

### Key Policy Documents

- [Reddit Data API Wiki](https://support.reddithelp.com/hc/en-us/articles/16160319875092-Reddit-Data-API-Wiki)
- [Responsible Builder Policy](https://support.reddithelp.com/hc/en-us/articles/42728983564564-Responsible-Builder-Policy)
- [Public Content Policy (May 2024)](https://support.reddithelp.com/hc/en-us/articles/26410290525844-Public-Content-Policy)

---

## 2. Geolocation / Geographic Filtering

### No Native Geo-Filtering

Reddit's API does not provide geographic filtering for posts. There are no geo-tags, no location parameters, and no way to query by user location. Reddit collects approximate location via IP for internal personalization, but this is **not exposed through the API**.

### Subreddit-Based Locality: The Primary Strategy

| Subreddit | Members | Description | Vienna Relevance |
|-----------|---------|-------------|-----------------|
| **r/wien** | ~204,000 | Main Vienna subreddit | **Direct** — Vienna-specific |
| **r/austria** | ~645,000 | Main Austria subreddit | **High** — national topics frequently include Vienna |
| **r/vienna** | ~3,900 | Legacy Vienna subreddit | **Deprecated** — migrating to r/wien ("Wir ziehen nach r/wien um!") |
| **r/aeiou** | ~7,500 | Austrian meme subreddit | **Low** — described as "legit dead" |

**Key finding:** r/wien (204k members) is the primary Vienna-focused subreddit. r/vienna is abandoned and redirecting to r/wien. r/austria is the most active Austrian subreddit and will contain significant Vienna-relevant content.

### Reliability of Subreddit-Based Locality

For ViennaTalksBout's use case (extracting trending topics), subreddit-based locality is sufficient. The topics discussed in r/wien are inherently Vienna-focused by community norms and moderation. If someone posts about "U2 Störung" in r/wien, the topic is Vienna-relevant regardless of the poster's physical location.

This meets ViennaTalksBout's must-have requirement for geolocation filtering through **structural locality**.

---

## 3. Real-Time Streaming

### Reddit Has NO Native Real-Time Streaming API

Reddit's public API is strictly REST/HTTP-based. There is no WebSocket, SSE, or push-based mechanism.

### PRAW Streaming Is Polling Under the Hood

PRAW's `SubredditStream` provides a streaming-like interface, but it is implemented as polling:

- Uses **exponential backoff with jitter** between polls when no new results are found
- Maximum polling delay: **~16 seconds** between requests when idle
- Returns up to **100 historical items** on first call
- Supports `skip_existing=True` and multi-subreddit monitoring: `reddit.subreddit("wien+austria").stream.comments()`

**Latency characteristics:**

| Scenario | Expected Latency |
|----------|-----------------|
| High-activity subreddit | 1-5 seconds |
| Low-activity subreddit | Up to ~16 seconds (max backoff) |
| Very high volume (r/all) | May **drop items** |

**Bottom line:** PRAW streaming is adequate for ViennaTalksBout. Expect 2-16 second latency, which is acceptable for a tag cloud that updates live but doesn't need sub-second freshness. However, this is less real-time than Mastodon's SSE streaming.

---

## 4. Data Volume Estimates

| Subreddit | Members | Posts/Day (est.) | Comments/Day (est.) | Activity |
|-----------|---------|-----------------|--------------------|-|
| **r/austria** | ~491,000-645,000 | ~10-50 | ~100-500 | High |
| **r/wien** | ~130,000-204,000 | ~3-15 | ~20-100 | High |
| **r/vienna** | ~3,900 | <1 | <1 | Nearly dead |

**Estimated combined daily volume for ViennaTalksBout:**

| Metric | Conservative | Moderate | Optimistic |
|--------|-------------|----------|-----------|
| Combined posts/day (r/wien + r/austria) | 15 | 40 | 80 |
| Combined comments/day | 100 | 400 | 800 |
| Total text items/day | 115 | 440 | 880 |

Reddit's value is in the quality and depth of discussion (longer comments, more context) rather than raw volume. Posts in r/wien and r/austria are primarily in **German**, with a significant minority in **English**.

---

## 5. API Rate Limits

| Auth Type | Rate Limit | Window |
|-----------|-----------|--------|
| **OAuth-authenticated** | 100 QPM (some sources say 60 QPM) | 10-minute rolling average |
| **Unauthenticated** | 10 req/min | Rolling |
| **No OAuth** | **Blocked entirely** | N/A |

**Rate limit response headers:** `X-Ratelimit-Used`, `X-Ratelimit-Remaining`, `X-Ratelimit-Reset`

**Practical budget for ViennaTalksBout (at 60 QPM conservative):**
- 4 streams (r/wien posts + comments, r/austria posts + comments): ~16 req/min
- Remaining budget: ~44 req/min for other operations

**User-Agent requirement:** `<platform>:<app ID>:<version> (by /u/<username>)` — default user-agents are "drastically limited."

---

## 6. Legal / ToS Considerations

### What is permitted:
- Accessing public subreddit data via API for non-commercial purposes
- Creating applications that aggregate and display trending content
- Displaying derived/aggregated insights (e.g., a tag cloud)

### What is restricted:
- Using Reddit content to **train AI models** without written consent
- Displaying content from **deleted** posts — must remove when deleted on Reddit
- Commercial use without a contract
- Circumventing rate limits

### ViennaTalksBout Risk Assessment

| Factor | Risk Level | Notes |
|--------|-----------|-------|
| Free tier eligibility | Medium | Likely qualifies if non-commercial, but definitions are ambiguous |
| Content reproduction | Low | Tag cloud shows derived topics, not verbatim content |
| GDPR compliance | Low | No personal data in final output |
| Policy change risk | **High** | Reddit has a track record of unilateral API policy changes |

---

## Summary Assessment

| Dimension | Rating | Notes |
|-----------|--------|-------|
| **Geo-filtering** | **Good** | r/wien provides direct Vienna content via structural locality |
| **Real-time** | Moderate | Polling-based only (2-16 sec latency) |
| **Volume** | Low-Moderate | ~100-800 text items/day from Vienna/Austria subreddits |
| **Content quality** | High | Longer, more detailed discussions; rich topic signal |
| **Cost** | Good | Free for non-commercial use |
| **API stability** | Low | History of unilateral API changes |
| **Implementation** | Moderate | OAuth required; PRAW simplifies polling |

**Decision:** Reddit is selected as one of the two MVP data sources. r/wien provides structural geographic filtering (must-have requirement met). Paired with Mastodon (wien.rocks) as the other source for a dual-source pipeline with complementary strengths — Reddit provides higher volume and deeper discussion threads, Mastodon provides true push streaming.

## Sources

- [Reddit Data API Wiki](https://support.reddithelp.com/hc/en-us/articles/16160319875092-Reddit-Data-API-Wiki)
- [Responsible Builder Policy](https://support.reddithelp.com/hc/en-us/articles/42728983564564-Responsible-Builder-Policy)
- [Public Content Policy](https://support.reddithelp.com/hc/en-us/articles/26410290525844-Public-Content-Policy)
- [PainOnSocial Pricing Guide](https://painonsocial.com/blog/how-much-does-reddit-api-cost)
- [PRAW SubredditStream Docs](https://praw.readthedocs.io/en/stable/code_overview/other/subredditstream.html)
- [PRAW Rate Limits](https://praw.readthedocs.io/en/stable/getting_started/ratelimits.html)
- [SubredditStats r/wien](https://subredditstats.com/r/wien)
- [SubredditStats r/austria](https://subredditstats.com/r/austria)

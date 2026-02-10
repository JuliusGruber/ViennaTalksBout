# Mastodon as a Data Source for ViennaTalksBout — In-Depth Research

Research date: 2026-02-07

---

## Critical Correction: vienna.social Does Not Exist

The instance `vienna.social` referenced in earlier project documents **does not exist**. Fetching `https://vienna.social/about` returns HTTP 503. The instance does not appear in any Fediverse directory. All project references have been corrected to **wien.rocks**.

---

## 1. Vienna-Related Mastodon Instances

### Active Austrian/Vienna Instances (verified live via API, February 2026)

| Instance | Focus | MAU | Avg Posts/Day | Registrations | Software |
|----------|-------|-----|---------------|---------------|----------|
| **wien.rocks** | Vienna | 424 | ~248 | Open, no approval | Mastodon 4.5.5 |
| **fedi.at** | Austria-wide | 167 | ~64 | Open, no approval | Mastodon 4.5.5 |
| **graz.social** | Graz/Styria | 235 | ~76 | Approval required | Mastodon 4.5.4 |
| **mastodon.wien** | Vienna | 51 | unknown | Approval required | Mastodon 4.5.6 |

**Combined totals**: ~877 monthly active users, ~389 posts/day across the three instances with available activity data.

### wien.rocks: The Primary Candidate

Operated by the **Fediverse Foundation** (Verein Fediverse Foundation), a nonprofit registered in Vienna.

- **424 monthly active users**
- **~248 posts/day** average (Nov 2025 - Jan 2026)
- Post character limit: **5,000** (higher than Mastodon default of 500)
- Primary language: **German (de)**
- Registrations: open, no approval required, minimum age 14

**Instance rules relevant to ViennaTalksBout:**
- Rule #4 bans "automated accounts, bots, or uncontextualized crossposting" — this governs user accounts on the instance, not external API consumers reading public data
- Corporate/business accounts are restricted

---

## 2. Geolocation / Geographic Filtering

### Mastodon Has No Native Geolocation Features

Mastodon does not support geo-tagging, location-based search, or geographic filtering. Multiple GitHub feature requests remain open and unimplemented (Issue #281 from 2016, Issue #8340, Issue #29002).

### Instance-Based Locality as Geographic Proxy

The `public:local` stream from wien.rocks contains exclusively posts from wien.rocks users — people who chose a Vienna-specific instance.

**Strengths:**
- High precision: every post in the local stream is from a wien.rocks user
- No false positives from non-Vienna users
- Instance rules enforce German or contextually relevant content

**Weaknesses:**
- **Coverage gap**: many Viennese users register on mastodon.social or other general instances
- Not all wien.rocks posts are about Vienna — users post on any topic
- Small volume: ~248 posts/day

**Reliability assessment:** Instance-based filtering provides a useful geographic proxy with low false-positive rate but high false-negative rate. For an MVP, it is workable. This meets ViennaTalksBout's must-have requirement for geolocation filtering through **structural locality**.

---

## 3. Real-Time Streaming

### Streaming API Architecture

Mastodon provides true real-time streaming via:
1. **Server-Sent Events (SSE)**: Long-lived HTTP with heartbeat keepalive
2. **WebSocket**: Multiplexed at `wss://<instance>/api/v1/streaming`

### Key Streams

| Stream | Description |
|--------|-------------|
| `public:local` | **Public posts from this server only** — the key stream for ViennaTalksBout |
| `public` | All public posts (federated) — too broad |
| `hashtag:local` | Local posts with a specific hashtag |

### Authentication Required (Since v4.2.0)

Anonymous streaming access was removed in Mastodon v4.2.0 (2023). All streaming connections require a valid OAuth access token. Note: `client_credentials` tokens may not work with streaming (GitHub #24116) — use authorization code flow.

### Latency

- Events are delivered via Redis pub/sub internally — **sub-second latency** for local posts
- No catch-up mechanism on reconnect — Mastodon.py's `reconnect_async` will auto-reconnect but missed events are lost

---

## 4. Data Volume Estimates

### wien.rocks Activity (Live Data, 2025-11-21 to 2026-02-06)

| Period | Posts/Day | Weekly Logins |
|--------|-----------|---------------|
| Jan 30 - Feb 6 2026 | 274 | 269 |
| Jan 23-30 2026 | 276 | 270 |
| Jan 9-16 2026 | 275-289 | 259-268 |
| Dec 19-26 2025 (holiday dip) | 209-215 | 234-249 |
| Nov 21-28 2025 | 242-246 | 238-261 |

**Average: ~248 posts/day, ~253 weekly logins**

At ~248 posts/day:
- ~10 posts/hour average
- ~17 posts/hour during active European daytime hours

This is **low but usable** volume. Mastodon posts tend to be longer and more substantive than tweets, potentially yielding more topics per post.

---

## 5. API Rate Limits

### REST API (Default Mastodon Configuration)

| Scope | Limit | Window |
|-------|-------|--------|
| Per account | 300 requests | 5 minutes |
| Per IP | 300 requests | 5 minutes |

### Streaming API

**No per-request rate limits.** Uses persistent connections. Connection limits are left to instance admin configuration.

---

## 6. Legal / ToS Considerations

### mastodon.social Terms (July 2025) — DO NOT Apply to wien.rocks

mastodon.social explicitly bans automated data collection and AI training. However, these terms apply **only to mastodon.social**, not to other instances. Each instance sets its own terms.

### wien.rocks Considerations

- Does not have explicit data usage terms beyond content moderation rules
- The Fediverse Foundation does not appear to have published data usage policies
- GDPR applies: ViennaTalksBout displays aggregated topics (not individual posts), which is likely covered by the **legitimate interest** basis

### Recommendations

1. Contact the Fediverse Foundation (admin@fediverse.foundation) to inform them about ViennaTalksBout
2. Never display individual posts or usernames — only aggregated topic terms
3. Register a proper OAuth application with a descriptive name

---

## 7. Mastodon.py Library

| Property | Detail |
|----------|--------|
| Version | 2.1.4 (September 23, 2025) |
| License | MIT |
| Python support | 3.7+ |
| API coverage | Feature-complete for Mastodon API v4.4.3 |
| PyPI downloads | ~18,858/week |
| Status | Production/Stable, actively maintained |

Key streaming methods:
- `stream_public(listener, local=True)` — stream local public timeline
- Rate limit handling: `wait` (default), `pace`, `throw` modes
- Auto-reconnect: `reconnect_async=True`
- **No WebSocket support** — SSE only (adequate for single instance)

---

## Summary Assessment

| Dimension | Rating | Notes |
|-----------|--------|-------|
| **Geo-filtering** | **Good** | wien.rocks local timeline provides instance-based structural locality |
| **Real-time** | **Excellent** | True SSE push streaming, sub-second latency |
| **Volume** | Low | ~248 posts/day (wien.rocks), ~389/day (all Austrian) |
| **Cost** | Free | No paid API tiers |
| **Implementation** | Easy | Mastodon.py handles everything; OAuth straightforward |
| **Legal risk** | Low | Aggregated display; contact Fediverse Foundation proactively |

**Decision:** Mastodon via wien.rocks is selected as one of the two MVP data sources. It provides true real-time streaming, strong geographic signal through instance-based locality, and zero cost. Paired with Reddit (r/wien + r/austria) as the second source to compensate for limited volume.

## Sources

- Instance API endpoints queried directly on 2026-02-07
- [Mastodon Streaming API Docs](https://docs.joinmastodon.org/methods/streaming/)
- [Mastodon Rate Limits](https://docs.joinmastodon.org/api/rate-limits/)
- [Mastodon.py Documentation](https://mastodonpy.readthedocs.io/en/stable/)
- [Mastodon.py on PyPI](https://pypi.org/project/Mastodon.py/)
- [JoinFediverse Wiki — Austria](https://joinfediverse.wiki/Austria_in_the_Fediverse)
- [Fediverse Foundation](https://fediverse.foundation/en/instanzen/)
- [GitHub Issue #281 — GeoTag](https://github.com/mastodon/mastodon/issues/281)

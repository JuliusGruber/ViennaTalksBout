# New Data Sources Research — User Posts for ViennaTalksBout

Research date: 2026-02-15

---

## Context

ViennaTalksBout surfaces what **regular people** are posting online about Vienna. The signal comes from user-generated posts, not media articles. This research evaluates all viable platforms beyond the currently implemented sources (Mastodon wien.rocks, RSS news feeds) and the already-researched Reddit (r/wien, r/austria).

### Must-Have Requirements

1. **User-generated posts** — authentic social media content, not news articles
2. **Geographic filtering for Vienna** — native, structural (instance/community-based), or reliably approximated
3. **Accessible API** — public or with reasonable registration; no scraping of ToS-prohibiting platforms
4. **Free or affordable** — no $5,000/month API tiers
5. **Legal compliance** — GDPR-safe, ToS-compliant

---

## Executive Summary: Ranked Candidates

| Rank | Source | Type | Vienna Volume | Feasibility | Priority |
|------|--------|------|---------------|-------------|----------|
| 1 | **Reddit (r/wien + r/austria)** | Social/Forum | ~100-800 items/day | Moderate | **Implement next** |
| 2 | **Additional Mastodon Instances** | Social | ~70-215 posts/day | Easy | **Quick win** |
| 3 | **Fediverse Hashtag Polling** | Social | Variable | Easy | **Quick win** |
| 4 | **Lemmy (feddit.org)** | Forum/Social | ~10-20 posts/day | Easy | **Low-effort add** |
| 5 | **Bluesky (DID-curated)** | Social | ~50-500 posts/day | Moderate | **Post-MVP** |
| 6 | **Nostr** | Social | <10 posts/day | Very Easy | **Trivial add** |
| 7 | **Jodel** | Social | Hundreds/day | Very Hard | **Watch list** |
| 8 | **Threads** | Social | Unknown | Hard | **Not recommended** |
| 9 | **TikTok** | Social | N/A | Blocked | **Not viable** |

---

## Tier 1 — High Priority (Implement Next)

### 1. Reddit (r/wien + r/austria) — Already Researched, Not Yet Implemented

See `research/reddit-research.md` for full details. Summary:

| Factor | Detail |
|--------|--------|
| **Geo-filtering** | Subreddit-based locality (r/wien = 204k members, r/austria = 645k) |
| **Volume** | ~100-800 text items/day (posts + comments) |
| **Real-time** | Polling via PRAW (2-16 sec latency) |
| **Authentication** | OAuth required |
| **Cost** | Free (non-commercial) |
| **Content quality** | High — longer, more detailed discussions; rich topic signal |
| **User posts?** | Yes — genuine user discussion, opinions, questions |
| **Implementation** | Moderate — PRAW library handles auth and rate limiting |
| **Risk** | Reddit has history of unilateral API policy changes |

**Status:** Research complete, implementation pending. This remains the strongest next data source.

---

### 2. Additional Austrian Mastodon Instances — New Finding

The Austrian Fediverse is larger than just wien.rocks. Multiple instances can be polled **without authentication** using the existing `MastodonPollingDatasource`.

#### Discovered Austrian Instances

| Instance | MAU | Focus | Vienna Relevance | Auth Needed |
|----------|-----|-------|-----------------|-------------|
| **wien.rocks** | 422 | Vienna | Direct | Already implemented |
| **fedi.at** | 166 | All Austria | Moderate | No (public timeline) |
| **mastodon.wien** | 52 | Vienna | Direct | No (public timeline) |
| **graz.social** | 235 | Graz region | Indirect | No (public timeline) |
| **tyrol.social** | 121 | Tyrol | Low | No (public timeline) |
| **social.uibk.ac.at** | 52 | Univ. of Innsbruck | Low | No (public timeline) |

**Total estimated Austrian Fediverse MAU: ~1,085** across all instances.

All are operated by known organizations:
- **Fediverse Foundation** (Vienna nonprofit): wien.rocks, fedi.at, tyrol.social
- **Verein graz.social**: Association for Ethical Digital Culture
- **permanizer.com**: mastodon.wien
- **University of Innsbruck**: social.uibk.ac.at (chose Mastodon over X and Bluesky as official platform)

#### Implementation

The existing `MastodonPollingDatasource` can be instantiated multiple times with different `instance_url` values and `access_token=None`:

```
GET https://fedi.at/api/v1/timelines/public?local=true
GET https://mastodon.wien/api/v1/timelines/public?local=true
```

Each instance automatically gets a distinct `source_id` (e.g., `"mastodon:fedi.at"`). No code changes needed — only configuration.

#### Priority Additions

| Priority | Instance | Rationale |
|----------|----------|-----------|
| **High** | fedi.at | All-Austria scope, 166 MAU, run by same org as wien.rocks |
| **High** | mastodon.wien | Vienna-specific, complements wien.rocks |
| **Medium** | graz.social | Largest Austrian instance by MAU, some Vienna topics |

**Estimated additional volume:** ~70-215 posts/day across fedi.at, mastodon.wien, and graz.social.

**Implementation effort:** Near zero — configuration only.

---

### 3. Fediverse Hashtag Polling — New Finding

In addition to local timelines, Mastodon's hashtag timeline API can find Vienna-related posts from **any user on any instance**, including large international ones:

```
GET https://{instance}/api/v1/timelines/tag/Wien
GET https://{instance}/api/v1/timelines/tag/Vienna
```

Supports multi-tag queries (`any[]`, `all[]`, `none[]`, up to 4 tags total), pagination via `min_id`/`max_id`, and `limit` (1-40 per request). No authentication required.

#### Strategy

Poll `#Wien` and `#Vienna` on:
1. **mastodon.social** — largest global instance, most federated reach
2. **wien.rocks** — local content
3. **fedi.at** — Austrian content

This catches Vienna discussion from users on non-Austrian instances worldwide — tourists, expats, people commenting on Vienna events, etc.

#### Mastodon Trends API (No Auth Required)

An additional discovery:

```
GET https://{instance}/api/v1/trends/tags        — trending hashtags
GET https://{instance}/api/v1/trends/statuses     — trending posts
GET https://{instance}/api/v1/trends/links         — trending links
```

Polling trends across multiple Austrian instances provides a "what's trending on the Austrian Fediverse" signal directly, without needing LLM extraction.

#### Implementation

Requires a new datasource variant that polls `/api/v1/timelines/tag/{hashtag}` instead of `/api/v1/timelines/public`. Needs deduplication logic since the same post could appear from multiple instance queries (same post `uri` = duplicate).

**Implementation effort:** ~0.5-1 day.

#### Limitation

There is no global unified hashtag index for the Fediverse. Each server returns only posts it has "seen" (from its own users, followed users, or relays). The **Fediscovery** project (fediscovery.org) is developing standardized cross-instance search under an EU NGI Search grant, but it is still in development.

---

## Tier 2 — Moderate Priority (Good Additions)

### 4. Lemmy (feddit.org, linz.city) — New Finding

Lemmy is a Fediverse Reddit alternative with real Austrian communities.

#### Austrian Lemmy Communities

| Community | Instance | Subscribers | MAU | Content Character |
|-----------|----------|-------------|-----|-------------------|
| **!dach@feddit.org** | feddit.org | 4,904 | 2,347 | Broad German-speaking discussion — highest volume |
| **!austria@feddit.org** | feddit.org | 508 | 74 | Mix of news and genuine user discussion |
| **!wien@feddit.org** | feddit.org | 93 | 10 | Mostly reshared news links |
| **!austria@linz.city** | linz.city | 1,184 | — | Austrian content |
| **!wien@linz.city** | linz.city | 364 | — | Vienna news links |

feddit.org is operated by the Austrian Fediverse Foundation (same org as wien.rocks).

#### User Posts vs. News Links — Critical Distinction

- **!wien communities** are mostly reshared news articles (ORF, vienna.at headlines). This overlaps with the existing RSS datasource and is NOT what we want.
- **!austria@feddit.org** has genuinely original user content: weekly "G'sudert wird!" venting threads, social media policy debates, genuine user opinions.
- **!dach@feddit.org** has the most volume and genuine discussion, but requires keyword filtering to extract Vienna-relevant content.

#### API Details

| Factor | Detail |
|--------|--------|
| **Authentication** | Not required for reading public posts |
| **Rate limits** | 999 req/600 sec (search), 999 req/60 sec (reads) — very generous |
| **Streaming** | None — polling only (WebSocket support was removed) |
| **Key endpoint** | `GET /api/v3/post/list?community_name={name}&sort=New&limit=50` |
| **API version** | v3 (widely deployed), v4 introduced with Lemmy 1.0 (Feb 2025) |
| **License consideration** | Lemmy server is AGPL-3.0, but using the REST API does NOT trigger AGPL. Use raw HTTP requests (not lemmy-js-client which is also AGPL) |

#### Implementation

Structurally identical to `MastodonPollingDatasource`: poll endpoint, track cursor, normalize to `Post` objects. The existing polling pattern is a near-perfect template.

| Factor | Rating |
|--------|--------|
| **Volume** | Low — ~10-20 relevant posts/day, ~3-5 genuinely user-generated |
| **Quality** | Good where genuine (user opinions, discussions) |
| **Effort** | ~1-2 days including tests |
| **Legal risk** | Low — public data, topic extraction, no AGPL concern with raw HTTP |

**Recommendation:** Worth implementing for its unique content type (community discussion, user opinions), but will not be a high-volume source. Focus on !austria and !dach with keyword filtering for Vienna relevance, not !wien (which is just reshared news).

---

### 5. Bluesky (DID-Curated Approach) — Updated Finding

The original research (see `research/bluesky-geolocation.md`) concluded Bluesky is blocked by lack of geo-filtering. This update explores a workaround.

#### What Has NOT Changed (Feb 2026)

- No native location features on posts or profiles
- No geographic search or discovery
- `community.lexicon.location.*` schemas still proof-of-concept only (Anchor, Smoke Signal)
- The main Bluesky app does not recognize any community location data
- No location-based labelers exist

#### German Language Volume on Bluesky

German is the **3rd most common language** on Bluesky (~11% of posts, after English ~56% and Japanese ~14%). At ~3.5M posts/day, that's ~385,000 German-language posts/day. Austria represents ~10% of the German-speaking population, suggesting ~1% of Bluesky posts could be Austrian.

#### Why Naive Language Filtering Is Too Expensive

Filtering all German-language posts and LLM-classifying for Vienna relevance:

| Approach | Daily API Calls | Monthly Cost |
|----------|----------------|--------------|
| One LLM call per German post | ~385,000 | ~$3,450/mo |
| Batched (20 per call) | ~19,250 | ~$1,200/mo |
| Keyword pre-filter + batch LLM | ~250-950 | ~$60-240/mo |

All are too expensive for the marginal value gained.

#### Viable Approach: DID-Based Filtering (Zero Classification Cost)

1. Scrape Austrian starter packs (~700+ known Austrian accounts)
2. Connect to Jetstream WebSocket with `wantedDids` filter (supports up to 10,000 DIDs)
3. Receive only posts from curated accounts (~50-500 posts/day)
4. Feed into existing pipeline — no classification needed

**Austrian Bluesky starter packs identified:**

| Pack | Accounts |
|------|----------|
| Österreichs Parteien und Politiker:innen | 134 |
| Churchies AT | 88 |
| Sozialdemokratie AT | 83 |
| NEOS | 52 |
| Kleine Zeitung Journalist:innen | 24 |
| Freie Journalist:innen in Österreich | — |
| ORF | — |
| DACH Illustrators | 147 |
| Migration Research DACH | 62 |

**Total estimated Austrian user base:** ~120-200K registered users (estimated from Germany's ~1.3-1.8M scaled by population ratio).

#### Assessment

| Factor | Detail |
|--------|--------|
| **Volume** | ~50-500 posts/day from curated accounts |
| **Content** | Skews toward journalists, politicians, institutions — less "regular people" |
| **Cost** | $0 (no auth, no LLM classification) |
| **Implementation** | New `BlueskyDatasource` using WebSocket + Jetstream |
| **Limitation** | Only captures known accounts; misses organic Vienna content from undiscovered users |
| **Effort** | ~2-3 days |

**Recommendation:** Post-MVP addition. The DID-curated approach is viable and free, but the content skews toward public figures rather than regular people posting about their daily life — which somewhat contradicts the product vision. Revisit if Bluesky adds native location features or Austrian DAU exceeds 50K.

---

## Tier 3 — Low Priority (Niche / Supplementary)

### 6. Nostr (Austrian Relay) — New Finding

Nostr is an open decentralized social protocol. Austria has its own relay at `wss://at.nostrworks.at`.

| Factor | Detail |
|--------|--------|
| **Authentication** | None — fully open protocol |
| **Real-time** | Yes — WebSocket with subscription filters |
| **Geo-filtering** | Austrian relay provides structural locality; hashtag filtering (#wien, #vienna) |
| **Cost** | Free |
| **Legal risk** | None — designed to be consumed by any client |
| **Volume** | Very low — single-digit Vienna-relevant posts per day |
| **Implementation** | ~0.5-1 day. Standard WebSocket client, filter by hashtags |

**Recommendation:** Trivially easy to add, zero legal risk, but negligible volume. Good as a "free" background source that requires almost no maintenance.

---

### 7. Jodel — WATCH LIST (Highest-Value Blocked Source)

Jodel is a hyperlocal anonymous social app with GPS geofencing (~10-20 km radius). Austria/Vienna is a core market. Content is text-based, opinion-rich, and inherently Vienna-specific.

| Factor | Detail |
|--------|--------|
| **Vienna volume** | Very high — hundreds to thousands of posts/day |
| **Content quality** | Excellent — anonymous opinions, complaints, local events, university life |
| **Geo-filtering** | Built-in GPS geofence |
| **User demographics** | 95% aged 18-26, ~70% students |
| **API** | No official API. Unofficial Python libraries exist but require frequently-rotated HMAC signing keys |
| **ToS** | **Explicitly prohibits** automation and data extraction. Takedown requests sent to API wrapper repos |
| **Legal risk** | **Very high** |

**Recommendation:** Most promising source for authentic Vienna user posts by far, but currently inaccessible without violating ToS. **Monitor for future official API.** Do not scrape.

---

## Tier 4 — Not Viable (Evaluated and Rejected)

### 8. Threads (Meta)

| Factor | Detail |
|--------|--------|
| **API** | Official, launched June 2024, free |
| **Geo-filtering** | **None** — no geographic filtering, no structural locality. Keyword proxy only |
| **Rate limits** | **500 searches per 7 days** — cripples polling frequency |
| **Streaming** | None — no public post stream |
| **Vienna volume** | Unknown, likely small German-language volume |
| **Fediverse federation** | Partial, opt-in. Cannot access Threads posts via Mastodon API |

**Why rejected:** The 500 queries/week limit makes real-time trending detection impossible. At best, you could search 3-4 keywords every 4-6 hours — producing a sparse, delayed signal. No structural locality means noisy keyword-based filtering. Not worth the Meta app review process.

### 9. TikTok

| Factor | Detail |
|--------|--------|
| **API** | Research API exists with video captions, comments, hashtags |
| **Geo-filtering** | Country-level only (`region_code: AT`), no city-level |
| **Austrian user base** | 2.33 million adults |
| **Data freshness** | **48-hour delay** — posts take 2 days to appear in API |
| **Access** | **Requires academic/non-profit affiliation** |
| **ToS** | **Prohibits public display of derived data** ("confidential information proprietary to TikTok") |
| **Cost** | Free if approved |

**Why rejected:** Three independent blockers: (1) 48-hour delay is incompatible with real-time trending, (2) requires academic affiliation for access, (3) ToS prohibits displaying aggregated trends publicly. Each alone would be fatal.

### 10. Other Rejected Platforms

| Platform | Status | Reason |
|----------|--------|--------|
| **X (Twitter)** | Evaluated | $5,000/month for Filtered Stream — too expensive |
| **Facebook Groups** | Dead | API fully removed by Meta in April 2024 |
| **Yik Yak** | Not available | US-college-campus-focused; no Vienna/EU presence |
| **BeReal** | Not feasible | No API, photo-based, certificate pinning blocks access |
| **Lemon8** | Not available | Not launched in Austria/EU |
| **Hive Social** | Dead | Security breach 2022, never recovered |
| **Cohost** | Shut down | Closed January 2025 |
| **Quora** | Not feasible | No API, sparse Vienna content, slow Q&A format |
| **Foursquare/Swarm** | Dying | City Guide shut down Dec 2024; check-ins have no topical text |
| **Strava** | Prohibited | ToS explicitly forbids third-party display and AI/ML use |
| **Nextdoor** | Not available | Not operating in Austria |
| **Discord** | Prohibited | Tiny Vienna communities (1,406 members); ToS prohibits data mining |
| **Telegram** | Risky | ToS explicitly prohibits scraping for datasets/AI |
| **Snap Map** | Poor fit | Visual content, no text; unofficial scrapers only |
| **Matrix/Element** | Wrong format | Chat fragments too noisy for topic extraction |
| **Gutefrage.net** | Low value | No API, slow Q&A format, minimal Vienna content |
| **derstandard.at comments** | Blocked | 30k comments/day but no public API; requires academic partnership |
| **meinbezirk.at Wien** | Blocked | 643k monthly users but no API or RSS |
| **willhaben.at** | Wrong type | Classified ads marketplace, not discussion content |
| **Diaspora** | Dead/incompatible | Declining usage; does not use ActivityPub |
| **Google Trends** | Not ready | Official API still in closed alpha; Austria-level only; fragile tooling |
| **Sag's Wien** | Niche | City issue reports (potholes, graffiti), not social conversation |

---

## Recommended Implementation Roadmap

### Phase 1 — Quick Wins (Days)

These require minimal to no code changes:

1. **Add fedi.at polling** — instantiate existing `MastodonPollingDatasource` with `instance_url=https://fedi.at`, no auth
2. **Add mastodon.wien polling** — same approach
3. **Add graz.social polling** — same approach

**Added volume:** ~70-215 posts/day. **Effort:** Configuration only.

### Phase 2 — Fediverse Expansion (1-2 Days)

4. **Hashtag timeline polling** — new datasource variant polling `#Wien` and `#Vienna` across mastodon.social, wien.rocks, fedi.at with deduplication
5. **Mastodon Trends API polling** — poll trending tags/posts across Austrian instances for supplementary signal

### Phase 3 — Reddit Integration (3-5 Days)

6. **Reddit datasource (r/wien + r/austria)** — implement `RedditDatasource` using PRAW with OAuth. Already fully researched in `research/reddit-research.md`. Highest volume non-Mastodon source.

### Phase 4 — Supplementary Sources (Post-MVP)

7. **Lemmy datasource** — poll feddit.org (!austria, !dach with Vienna keyword filtering). ~1-2 days.
8. **Nostr datasource** — WebSocket to `wss://at.nostrworks.at` with hashtag filtering. ~0.5-1 day.
9. **Bluesky DID-curated** — Jetstream WebSocket with curated Austrian DID list. ~2-3 days. Only if regular-people content is sufficient.

### Watch List (Monitor for Changes)

- **Jodel** — monitor for official API launch
- **Bluesky** — monitor for native location features or `community.lexicon.location` adoption
- **Google Trends** — monitor for public API launch (expected late 2026/early 2027)
- **derstandard.at** — explore academic data partnership
- **Fediscovery** — cross-instance Fediverse search/trends (in development under EU grant)

---

## Volume Comparison: All Viable Sources

| Source | Est. Vienna Posts/Day | Content Type | Real-Time | Status |
|--------|----------------------|--------------|-----------|--------|
| **Mastodon wien.rocks** | ~248 | Social posts | SSE streaming | Implemented |
| **RSS news feeds** | ~130-250 | News articles | Polling | Implemented |
| **Reddit r/wien + r/austria** | ~100-800 | Forum discussion | Polling (2-16s) | Researched |
| **Mastodon fedi.at** | ~15-50 | Social posts | Polling | New finding |
| **Mastodon mastodon.wien** | ~5-15 | Social posts | Polling | New finding |
| **Mastodon graz.social** | ~30-80 | Social posts | Polling | New finding |
| **Fediverse #Wien hashtag** | Variable | Social posts | Polling | New finding |
| **Lemmy feddit.org** | ~10-20 | Forum discussion | Polling | New finding |
| **Bluesky (DID-curated)** | ~50-500 | Social posts | WebSocket | New finding |
| **Nostr (Austrian relay)** | <10 | Social posts | WebSocket | New finding |

**With all sources implemented, estimated total Vienna-relevant user posts: ~500-2,000+ per day** (excluding RSS news, which the product vision de-emphasizes).

---

## Key Insight: The Fediverse Is ViennaTalksBout's Strongest Ecosystem

The Austrian Fediverse Foundation operates multiple platforms from Vienna:
- wien.rocks (Mastodon) — already integrated
- fedi.at (Mastodon) — easy add
- tyrol.social (Mastodon) — easy add
- feddit.org (Lemmy) — easy add
- instapix.org (Pixelfed) — future possibility

These all share the same operator, community norms, and GDPR-compliant approach. Expanding within this ecosystem is the lowest-risk, lowest-effort path to more Vienna user posts. Combined with Reddit as the major non-Fediverse addition, ViennaTalksBout can achieve meaningful post volume while staying true to the "user posts, not media articles" vision.

## Sources

### Threads
- [Threads API Documentation](https://developers.facebook.com/docs/threads)
- [Threads API Keyword Search](https://developers.facebook.com/docs/threads/keyword-search)
- [Meta Content Library](https://developers.facebook.com/docs/content-library-and-api/)

### Lemmy
- [Lemmy API Documentation](https://join-lemmy.org/docs/contributors/04-api.html)
- [feddit.org](https://feddit.org)
- [linz.city](https://linz.city)
- [Lemmy OpenAPI Spec (Unofficial)](https://mv-gh.github.io/lemmy_openapi_spec/)

### TikTok
- [TikTok Research API](https://developers.tiktok.com/products/research-api/)
- [TikTok Research API Terms](https://www.tiktok.com/legal/page/global/terms-of-service-research-api/en)

### Mastodon/Fediverse
- [Austria in the Fediverse — JoinFediverse Wiki](https://joinfediverse.wiki/Austria_in_the_Fediverse)
- [Fediverse Foundation](https://fediverse.foundation/en/instanzen/)
- [Mastodon Timelines API](https://docs.joinmastodon.org/methods/timelines/)
- [Mastodon Trends API](https://docs.joinmastodon.org/methods/trends/)
- [Mastodon Public Data Guide](https://docs.joinmastodon.org/client/public/)
- [University of Innsbruck Mastodon](https://www.uibk.ac.at/en/newsroom/2024/mastodon-for-all-university-employees/)
- [Fediscovery Project](https://www.fediscovery.org/)

### Bluesky
- [Bluesky Jetstream](https://github.com/bluesky-social/jetstream)
- [Bluesky Rate Limits](https://docs.bsky.app/docs/advanced-guides/rate-limits)
- [Anchor (Location Check-ins)](https://github.com/dropanchorapp/Anchor)
- [Smoke Signal Events](https://discourse.smokesignal.events/)

### Nostr
- [Nostr Protocol](https://github.com/nostr-protocol/nostr)
- [Austrian Relay (at.nostrworks.at)](https://at.nostrworks.at)
- [GeoRelays Project](https://github.com/permissionlesstech/georelays)

### Niche Platforms
- [Jodel](https://jodel.com)
- [Jodel API (JodelRaccoons)](https://github.com/JodelRaccoons/jodel_api)
- [Sag's Wien](https://www.wien.gv.at/sagswien/)
- [data.gv.at](https://www.data.gv.at)

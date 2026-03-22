# Datasource Candidates Research — March 2026

Research into additional user-generated content sources for ViennaTalksBout.
Criteria: Vienna structural locality, API availability, volume, legal viability.

## Already Working (3)

| Source | Vienna Specificity | Notes |
|---|---|---|
| Mastodon (wien.rocks) | High | Polling local timeline |
| RSS (ORF Wien, ORF News, vienna.at, OTS) | High-Medium | 4 Austrian news feeds |
| Lemmy (feddit.org austria/dach) | Medium | 2 communities |

## Implemented, Needs Credentials (1)

| Source | Vienna Specificity | Notes |
|---|---|---|
| Reddit (r/wien, r/austria) | High-Medium | Code ready, needs Reddit "script" app creds |

## Quick Wins — Config Only

### Mastodon (mastodon.wien, fedi.at)
- **Effort**: Config only — multi-instance already supported via `MASTODON_2_*` env vars
- **Vienna specificity**: High (mastodon.wien), Medium (fedi.at is Austrian)
- **Volume**: Lower than wien.rocks but adds signal
- **Action**: Run `python scripts/register_app.py --instance https://mastodon.wien` and `--instance https://fedi.at`

### Lemmy Multi-Instance
- **Effort**: Small refactor to support multiple Lemmy instances (like multi-Mastodon)
- **Best communities to add**:
  - feddit.de/c/austria (1,184 subscribers — largest Austrian Lemmy community)
  - lemmy.world/c/vienna (366 subscribers — largest Vienna-specific)
  - feddit.org/c/wien (95 subscribers)
- **Action**: Extend LemmyConfig to support multiple instances

## Worth Implementing — New Datasources

### 1. Wien.gv.at Petitions (petitionen.wien.gv.at)
- **Effort**: Easy — simple HTML table scraping, predictable structure, no auth
- **Vienna specificity**: 100% Vienna
- **Volume**: Low (dozens of active petitions) but each = verified civic concern
- **Legal**: Public government platform, low risk
- **Bonus**: Combine with openPetition.eu/at (269 Vienna petitions)

### 2. derstandard.at Forum Comments
- **Effort**: Medium-Hard — HTML scraping, anti-bot measures likely, nested comment threads
- **Vienna specificity**: Medium-High (national paper but heavy Vienna focus, articles filterable by Wien tag)
- **Volume**: Very high — up to 30,000 comments/day, 75M+ comments over a decade
- **Legal**: Scraping likely violates ToS. Academic "One Million Posts Corpus" exists on HuggingFace (CC BY-NC-SA 4.0) but covers 2015-2016 only
- **Note**: Extremely high signal for trending opinions among educated Austrian audience

### 3. Bluesky
- **Effort**: Medium — new datasource module, REST + AT Protocol
- **Vienna specificity**: Medium — keyword search for "wien"/"vienna" with language filter
- **Volume**: Growing — significant German-speaking adoption
- **API**: `app.bsky.feed.searchPosts` supports keyword search. Can also build feed generator for firehose filtering
- **Legal**: Open protocol, feed generators are encouraged use case
- **No geo-filtering** but keyword + language filtering is practical

### 4. Threads by Meta
- **Effort**: Medium — new datasource, requires Meta developer account + app review
- **Vienna specificity**: Medium — keyword search only, no geo or language filtering
- **Volume**: Unknown for Vienna specifically, high general DACH adoption
- **API**: REST with keyword search (`/keyword_search`), 2,200 queries/24h
- **Legal**: Standard Meta platform terms, attribution required

### 5. X/Twitter Vienna Trending
- **Effort**: Medium — well-documented API
- **Vienna specificity**: High — `GET trends/place` with Vienna WOEID gives city-level trending topics
- **Volume**: Medium-high for trending topics
- **Cost**: Free tier is write-only (useless). Basic tier $100/mo. Pay-per-use ~$0.01/tweet (launched Feb 2026)
- **Legal**: Strict ToS, prohibits redistribution
- **Note**: Direct trending-topics feed is a perfect fit, but cost is a concern

## Maybe Later

### Jodel
- **What**: Hyperlocal anonymous posting app, popular with Vienna students
- **Why defer**: No official API. Unofficial Python libraries exist but HMAC signing key rotates every few weeks. Explicitly violates ToS.
- **Vienna quality**: Very high (inherently hyperlocal, 10km radius)

### FragNebenan (fragnebenan.at)
- **What**: Austria's largest neighborhood social network (~60k users)
- **Why defer**: No public API, content behind login, would need authenticated scraping
- **Vienna quality**: Very high (Vienna-born, Grätzl-level granularity)

### Telegram Channels
- **What**: Public Vienna channels (news, events, community)
- **Why defer**: Requires manual curation of quality channels. Content quality inconsistent.
- **API**: Telegram Bot API allows reading public channel messages

### Matrix Rooms
- **What**: Public rooms about Vienna (tech community, etc.)
- **Why defer**: Chat-like content, often off-topic chatter rather than Vienna news/events
- **API**: Matrix Client-Server API, can search room directory

## Not Viable

| Source | Reason |
|---|---|
| **Discord** | No server discovery API, requires manual admin invitations, ToS prohibits scraping |
| **PeerTube** | Video titles/descriptions too sparse for topic extraction |
| **Nostr** | Minimal Vienna adoption, no discovery mechanism, hard implementation |
| **Twitch** | Stream titles too thin for meaningful topic extraction |
| **Pixelfed** | Image-focused, very low text volume for topic extraction. pixelfed.at is down |

## Implementation Priority

1. **Activate mastodon.wien + fedi.at** (config only)
2. **Enable Reddit** (needs user to create app at reddit.com/prefs/apps)
3. **Extend Lemmy to multi-instance** (small refactor)
4. **Wien.gv.at petitions** (easy, 100% Vienna civic signal)
5. **Bluesky keyword search** (medium, growing platform)
6. **derstandard.at comments** (high value but scraping complexity)
7. **Threads** (medium, Meta bureaucracy)
8. **X/Twitter trending** (good fit but $100+/mo)

# Bluesky Geolocation Filtering — Research Update (Feb 2026)

Investigation into whether Bluesky supports filtering data by geolocation, and what community-driven alternatives exist.

## Short Answer

**No.** As of February 2026, Bluesky has no native geolocation support. There are no location fields in the `app.bsky.feed.post` schema, no geo parameters in the search API, and no location-based filtering in Jetstream or the Firehose. Bluesky's official 2026 roadmap does not mention location features.

However, a **community-driven effort** funded by Bluesky is actively building standardized location schemas for the AT Protocol. These are not yet in production use.

## Official API — No Geo Support

### Post Schema (`app.bsky.feed.post`)

The standard post record contains:
- `text` — post content
- `createdAt` — timestamp
- `langs` — language tags
- `facets` — rich text (links, mentions, hashtags)
- `reply` — reply references
- `embed` — media/link embeds

**No latitude, longitude, place, or location fields exist.**

### Search API (`app.bsky.feed.searchPosts`)

The search endpoint supports:
- Text query matching
- Exact phrase matching
- Hashtag filtering
- Mention filtering
- Language filtering

**No geolocation, radius, bounding box, or place-based search parameters.**

### Jetstream / Firehose

- Jetstream supports server-side filtering by **collection NSID** and **DID** only
- No geographic or location-based filtering at the stream level
- The Firehose delivers everything with no filtering at all

### 2026 Roadmap

Bluesky's January 2026 roadmap focuses on:
- Discover feed improvements (topic tags)
- Real-time / live event features
- Basic features (drafts, longer videos, more photos per post)
- "Who to follow" improvements

**Location features are not mentioned.**

## Community Location Schemas (In Development)

### Overview

The most significant geolocation work is happening through the **Lexicon Community** initiative, funded by Bluesky's AT Protocol Community Fund.

- **Funding:** $15,000 initial donation from Peter Wang / Skyseed Fund (March 2025)
- **Timeline:** Originally scoped for 3 months from March 2025 announcement
- **Lead developers:** Nick Gerakines (Smoke Signal), Boris Mann (volunteer steward)
- **Catalyst:** Foursquare's release of their open-source Places dataset (100M+ global POIs)

### Schemas Under Development

All schemas use the `community.lexicon.location.*` namespace:

| Schema | Purpose |
|--------|---------|
| `community.lexicon.location.place` | Venue/place records linked to Foursquare OS Places identifiers |
| `community.lexicon.location.hthree` | H3 hexagonal geocell indexing for area-based tagging |
| Geo lat/long lexicon | Basic latitude/longitude coordinate data (strings for precision) |

### Planned Deliverables

1. Default venue and geo lexicons
2. Foursquare OS Places integration with lazy-loading
3. Hosted venue lookup endpoint and developer widget
4. Backend firehose, feeds, search support, and map visualization

### Adoption Status

- **Smoke Signal Events** (Nick Gerakines' app) is the first planned adopter
- **Anchor** — experimental macOS menubar app testing location-based check-ins
- No mainstream Bluesky client has adopted these schemas yet
- The schemas enable interoperability: any app using `community.lexicon.location.*` records would have posts visible across shared infrastructure

### Implications for ViennaTalksBout

These community schemas are **not yet usable** for ViennaTalksBout's purposes:
- They are still in development / early adoption
- Mainstream Bluesky users do not attach location data to posts
- Even once available, adoption would be opt-in — most posts would still lack location data
- The schemas are designed for check-in and venue-tagging use cases, not passive geo-filtering of all posts

## Third-Party Geo-Enrichment Options

### DigitalStakeout

- Offers geo-enrichment for Bluesky Firehose data
- Uses NLP to extract location references from post content
- Enables location-based feeds by analyzing text, not structured data
- Commercial product aimed at security/intelligence use cases

### Custom Feed Generators

- Bluesky's architecture allows anyone to build custom feed algorithms
- A feed generator could in theory implement keyword/NLP-based location filtering
- However, content-based location inference is unreliable and does not meet ViennaTalksBout's requirement for geolocation filtering as a must-have

## Comparison With Other Platforms

| Platform | Native Geo-Filtering | Notes |
|----------|---------------------|-------|
| X (Twitter) | Yes | Geo-tagged tweets + location search; requires Pro tier ($5k/mo) |
| Mastodon | Partial | Instance-based locality (e.g. wien.rocks); no per-post geo |
| Reddit | No | Subreddit-based locality (r/vienna); no geo coordinates |
| **Bluesky** | **No** | No location data at any level; no structural locality mechanism |

## Conclusion for ViennaTalksBout

**The absence of native geolocation filtering is a significant limitation for Bluesky as a ViennaTalksBout data source.** Geolocation filtering — whether native (API-level geo parameters) or structural (instance-based locality, topic-specific communities) — is a must-have requirement for ViennaTalksBout data sources. Bluesky offers neither.

The community location schemas are worth monitoring, but they will not provide meaningful coverage anytime soon. Even once available, adoption would be opt-in and limited to specific apps — most posts would still lack location data.

Bluesky remains a candidate only if and when the `community.lexicon.location.*` schemas reach mainstream adoption, which is not on any near-term horizon.

## Sources

- [Bluesky API — searchPosts](https://docs.bsky.app/docs/api/app-bsky-feed-search-posts)
- [Bluesky 2026 Roadmap — "What's Next at Bluesky"](https://bsky.social/about/blog/01-26-2026-whats-next-at-bluesky)
- [Location Data on AT Protocol — Community Fund Project](https://atprotocol.dev/location-data-on-at-protocol-the-second-community-fund-project/)
- [ATGeo Working Group — Place Object Discussion](https://discourse.lexicon.community/t/atgeo-wg-lets-look-at-an-example-place-object/82)
- [Lexicon Community Governance — GitHub](https://github.com/lexicon-community/governance)
- [Nick Gerakines — Smoke Signal Talk](https://atprotocommunity.leaflet.pub/3mcq4wmjyrc2w)
- [DigitalStakeout — Bluesky Firehose Integration](https://www.digitalstakeout.com/post/enhance-your-security-intelligence-with-digitalstakeout-s-new-bluesky-firehose-integration)
- [Add Location Field to Profile — GitHub Issue #883](https://github.com/bluesky-social/social-app/issues/883)

# Bluesky Data Delivery & Expected Volumes

Research into how Bluesky delivers data via Jetstream and what data volumes TalkBout should expect to handle.

## Two Delivery Mechanisms

Bluesky offers two real-time data streams. Both are WebSocket-based.

| | Firehose | Jetstream |
|---|---|---|
| **Protocol** | `com.atproto.sync.subscribeRepos` | Unofficial convenience layer |
| **Encoding** | CBOR + CAR (binary) | JSON |
| **Content** | Full repo MST updates with Merkle proofs + cryptographic signatures | Leaf-node records only, no signatures |
| **Filtering** | None — consumer receives everything | Server-side by collection NSID and/or DID |
| **Compression** | None | Optional zstd (~56% size reduction) |
| **Authentication to consume** | None | None |
| **Self-authenticating data** | Yes | No — acceptable for read-only ingestion |

**TalkBout should use Jetstream.** It's simpler, dramatically smaller, filterable, and the lack of cryptographic verification is irrelevant for our read-only trend extraction use case.

## Jetstream Connection

### WebSocket URL

```
wss://jetstream2.us-east.bsky.network/subscribe?wantedCollections=app.bsky.feed.post
```

Four official public instances are available:

| Instance | Region |
|---|---|
| `jetstream1.us-east.bsky.network` | US East |
| `jetstream2.us-east.bsky.network` | US East |
| `jetstream1.us-west.bsky.network` | US West |
| `jetstream2.us-west.bsky.network` | US West |

### Key Query Parameters

| Parameter | Description |
|---|---|
| `wantedCollections` | Array of collection NSIDs to receive (e.g. `app.bsky.feed.post`). Supports prefixes like `app.bsky.graph.*`. Max 100. Default: all. |
| `wantedDids` | Array of repo DIDs to filter by. Max 10,000. |
| `cursor` | Unix microseconds timestamp — resume from a point in time. Works across instances. |
| `compress` | `true` to enable zstd compression (requires custom dictionary for decoding). |
| `maxMessageSizeBytes` | Max payload size per message (0 = unlimited). |

### Dynamic Filtering

After connecting, a client can update filters by sending a text message:

```json
{
  "type": "options_update",
  "payload": {
    "wantedCollections": ["app.bsky.feed.post"],
    "wantedDids": [],
    "maxMessageSizeBytes": 0
  }
}
```

## Message Format

Jetstream delivers three event types. All subscribers receive Identity and Account events regardless of collection filters.

### 1. Commit Event (posts, likes, follows, etc.)

This is the primary event type. For TalkBout, we filter to `app.bsky.feed.post` commits.

```json
{
  "did": "did:plc:eygmaihciaxprqvxpfvl6flk",
  "time_us": 1725911162329308,
  "kind": "commit",
  "commit": {
    "rev": "3l3qo2vutsw2b",
    "operation": "create",
    "collection": "app.bsky.feed.post",
    "rkey": "3l3qo2vuowo2b",
    "record": {
      "$type": "app.bsky.feed.post",
      "text": "Enjoying a Melange at Café Central ☕",
      "createdAt": "2024-09-09T19:46:02.102Z",
      "langs": ["de"],
      "facets": [
        {
          "index": { "byteStart": 0, "byteEnd": 5 },
          "features": [
            { "$type": "app.bsky.richtext.facet#link", "uri": "https://example.com" }
          ]
        }
      ],
      "reply": {
        "root": { "uri": "at://did:plc:.../app.bsky.feed.post/...", "cid": "bafy..." },
        "parent": { "uri": "at://did:plc:.../app.bsky.feed.post/...", "cid": "bafy..." }
      },
      "embed": {
        "$type": "app.bsky.embed.images",
        "images": [{ "alt": "description", "image": { "...": "..." } }]
      }
    },
    "cid": "bafyreidwaivazkwu67xztlmuobx35hs2lnfh3kolmgfmucldvhd3sgzcqi"
  }
}
```

**Key fields for TalkBout:**

| Field | Use |
|---|---|
| `commit.operation` | `create` / `update` / `delete` — we primarily care about `create` |
| `commit.record.text` | The post content to extract topics from |
| `commit.record.langs` | Language tags — useful for filtering to `de` / `en` |
| `commit.record.createdAt` | Timestamp for the time slider feature |
| `did` | Author DID — can be resolved to a handle for profile context |
| `commit.record.reply` | Present if this is a reply — may want to weight differently |
| `commit.record.facets` | Rich-text annotations (links, mentions, hashtags) |

### 2. Identity Event

```json
{
  "did": "did:plc:abc123",
  "time_us": 1725911162329308,
  "kind": "identity",
  "identity": {
    "did": "did:plc:abc123",
    "handle": "user.bsky.social",
    "seq": 12345,
    "time": "2024-09-09T19:46:02Z"
  }
}
```

Useful for maintaining a DID→handle cache. Low volume — can be safely ignored or stored cheaply.

### 3. Account Event

```json
{
  "did": "did:plc:abc123",
  "time_us": 1725911162329308,
  "kind": "account",
  "account": {
    "active": true,
    "did": "did:plc:abc123",
    "seq": 12346,
    "time": "2024-09-09T19:46:02Z"
  }
}
```

Indicates account status changes (active, deactivated, taken down). Low volume — TalkBout can ignore these.

## Expected Data Volumes

### Network-Wide Baseline

| Metric | Value | Notes |
|---|---|---|
| Registered users | ~40 million | As of late 2025; growing at ~17k/day |
| Daily active users | ~1.5–4 million | Estimates vary; trending downward from Nov 2024 peak |
| Total posts created | ~850 million+ | All-time cumulative |
| Firehose event rate | ~300 events/sec (quiet) to 2,000+/sec (peak) | All event types combined |

### Bandwidth by Configuration

| Configuration | Daily Volume | Monthly Volume |
|---|---|---|
| Full Firehose (CBOR) | 24–232 GB/day | ~3.16 TB/mo (baseline) |
| Jetstream — all events, uncompressed | ~41 GB/day | ~400 GB/mo |
| Jetstream — all events, zstd compressed | ~18 GB/day | ~175 GB/mo |
| **Jetstream — posts only, uncompressed** | **~850 MB/day** | **~25.5 GB/mo** |
| **Jetstream — posts only, zstd compressed** | **~375 MB/day** | **~11.3 GB/mo** |

> **Note:** The ~850 MB/day figure is from September 2024. Bluesky has grown since then, so actual volumes may be 1.5–2x higher today. Plan for **~1–2 GB/day** for posts-only uncompressed.

### What TalkBout Will Actually Process

TalkBout does not need the full global post stream. After connecting with `wantedCollections=app.bsky.feed.post`, posts can be filtered by language. However, **Bluesky has no native geolocation filtering** — there is no way to isolate Vienna-relevant posts at the API level, and no structural locality mechanism (unlike subreddit- or instance-based filtering on other platforms). Estimated funnel:

| Stage | Events/Day (estimate) | Volume |
|---|---|---|
| All Bluesky posts | Millions | ~1–2 GB/day |
| German-language posts (`langs` contains `de`) | ~2–5% of total | ~20–100 MB/day |
| Vienna-relevant posts | No reliable filtering mechanism | Unknown |

The ingestion bandwidth is small, but **the lack of geolocation filtering is a fundamental limitation**. Language filtering alone is insufficient to isolate Vienna-relevant content from all German-language posts worldwide.

### Message Sizes

Individual Jetstream messages are small:

| Type | Typical Size (JSON) | With zstd |
|---|---|---|
| Post create (short text, no embed) | 400–600 bytes | ~200–270 bytes |
| Post create (with images/links) | 800–1,500 bytes | ~400–700 bytes |
| Like | ~350 bytes | ~150 bytes |
| Identity/Account | ~200 bytes | ~100 bytes |

## Implications for TalkBout Architecture

### Ingestion is Lightweight

- A single WebSocket connection to one Jetstream instance is sufficient
- No authentication, no API keys, no SDK dependencies
- A basic WebSocket client in any language can handle the stream
- At ~1–2 GB/day uncompressed (all posts), even a cheap VPS handles this easily
- With zstd compression, it drops to under 1 GB/day

### Filtering Strategy

1. **Server-side (Jetstream):** Filter to `app.bsky.feed.post` only — eliminates likes, follows, blocks, etc.
2. **Client-side pass 1:** Check `langs` field for `de` (German) or `en` (English) — cheap string check
3. **LLM pass:** Send posts to Claude for topic extraction

**Note:** This filtering pipeline lacks a geolocation filtering step. Bluesky has no native geo-filtering, and language filtering alone does not isolate Vienna-relevant content. See `research/bluesky-geolocation.md` for details on this limitation.

### Resilience

- Jetstream cursors are time-based (unix microseconds) — if disconnected, reconnect with cursor to resume
- Same cursor works across all 4 public instances — can fail over between them
- No state to maintain on the server side

### Limitations to Plan For

- **No geo-filtering:** Bluesky has no native location data and no structural locality mechanism (unlike subreddit- or instance-based approaches on other platforms). Community-driven `community.lexicon.location.*` schemas are in development but not yet in production or widely adopted. This is a fundamental limitation for TalkBout, which requires geolocation filtering as a must-have for any data source. See `research/bluesky-geolocation.md` for details.
- **Not self-authenticating:** Jetstream strips cryptographic proofs. Data could theoretically be tampered with by the Jetstream instance. Acceptable for TalkBout's use case.
- **Not formally part of AT Protocol:** Bluesky operates Jetstream as a convenience service. They plan to eventually fold its advantages into the core protocol firehose, which could mean API changes.
- **No SLA on public instances:** The 4 public instances are best-effort. For production reliability, consider running a private Jetstream instance (it's open source).

## Sources

- [Bluesky Jetstream GitHub](https://github.com/bluesky-social/jetstream)
- [Introducing Jetstream — Bluesky Blog](https://docs.bsky.app/blog/jetstream)
- [Jetstream: Shrinking the AT Proto Firehose by >99% — Jaz](https://jazco.dev/2024/09/24/jetstream/)
- [Bluesky Firehose Docs](https://docs.bsky.app/docs/advanced-guides/firehose)
- [Bluesky Posts Docs](https://docs.bsky.app/docs/advanced-guides/posts)
- [Bluesky Rate Limits](https://docs.bsky.app/docs/advanced-guides/rate-limits)
- [Relay Operational Updates — Bluesky Blog](https://docs.bsky.app/blog/relay-ops)
- [Bluesky Statistics (Backlinko)](https://backlinko.com/bluesky-statistics)

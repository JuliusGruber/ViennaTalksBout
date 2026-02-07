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

### Key Considerations (MVP)

- **Rate limits**: Each platform imposes API rate limits that affect ingestion volume
- **Geo-filtering**: Not all platforms support native location filtering — may need LLM-based or heuristic filtering to isolate Vienna-related content
- **Language**: Posts will be in German and English; the LLM extraction step must handle both
- **Cost**: X API paid tiers may be required for sufficient streaming volume

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

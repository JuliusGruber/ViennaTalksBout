# Austrian News Sites & RSS Feeds — Research

Research into Austrian news websites and their RSS feeds as data sources for ViennaTalksBout.

Research date: 2026-02-07

---

## 1. Major Austrian News Sites with RSS Feeds

### 1.1 orf.at — Austrian Broadcasting Corporation (ORF)

**Overview:** ORF is Austria's public service broadcaster and the dominant online news platform. orf.at is the most visited news website in Austria with approximately 128 million visits per month (2024). The ORF website reaches over 60% of Austrian internet users. ORF retains the highest trust level of any Austrian news brand at 63% (Reuters Digital News Report 2025).

**RSS availability:** Yes. Official RSS hub at `https://rss.orf.at/`. All feeds are free for non-commercial use.

**Feed URLs (confirmed):**

| Feed | URL | Description |
|------|-----|-------------|
| National news | `https://rss.orf.at/news.xml` | Main news feed |
| Sport | `https://rss.orf.at/sport.xml` | Sports |
| Science | `https://rss.orf.at/science.xml` | Science |
| Help | `https://rss.orf.at/help.xml` | Consumer/help |
| Debate | `https://rss.orf.at/debatten.xml` | Discussion/debate |
| OE3 | `https://rss.orf.at/oe3.xml` | Radio OE3 |
| FM4 | `https://rss.orf.at/fm4.xml` | Radio FM4 |
| Austria (regional) | `https://rss.orf.at/oesterreich.xml` | All regional news |
| **Wien (Vienna)** | **`https://rss.orf.at/wien.xml`** | **Vienna-specific regional news** |
| Niederosterreich | `https://rss.orf.at/noe.xml` | Lower Austria |
| Oberosterreich | `https://rss.orf.at/ooe.xml` | Upper Austria |
| Burgenland | `https://rss.orf.at/burgenland.xml` | Burgenland |
| Salzburg | `https://rss.orf.at/salzburg.xml` | Salzburg |
| Steiermark | `https://rss.orf.at/steiermark.xml` | Styria |
| Karnten | `https://rss.orf.at/kaernten.xml` | Carinthia |
| Tirol | `https://rss.orf.at/tirol.xml` | Tyrol |
| Vorarlberg | `https://rss.orf.at/vorarlberg.xml` | Vorarlberg |

**Feed format:** RDF 1.0 (RSS 1.0) for the main news feed (`news.xml`), RSS 2.0 for regional feeds (`wien.xml`). Uses `http://purl.org/rss/1.0/` namespace. Encoding: UTF-8.

**Items per feed:** 20 most recent articles per feed.

**Content depth:** Summary only. Descriptions are brief overviews, not full article text. Some items in the main feed lack descriptions entirely (title + metadata only).

**Fields per item:** `<title>`, `<link>`, `<guid>`, `<description>` (when present), `<category>`, `<pubDate>`, `<enclosure>` (images in regional feeds), `<dc:subject>`, `<dc:date>`, `<orfon:storyType>` (ticker vs. story).

**Update frequency:** Every 30 minutes (documented in feed metadata: hourly period, frequency of 2). ORF editorial team updates news more than 30 times a day.

**Vienna-specific feed:** Yes. `https://rss.orf.at/wien.xml` covers Vienna-only regional news from the wien.orf.at portal. Categories observed include Wirtschaft, Chronik, Verkehr, Kultur, Essen & Trinken.

**Paywall:** None. orf.at content is freely accessible, funded by the mandatory ORF household levy (EUR 15.30/month since January 2024). However, the 2024 ORF law amendment limits ORF to a maximum of **350 text articles per week** on its main news page, a concession to private media publishers.

**Source:** [ORF RSS Hub](https://rss.orf.at/), [ORF Corporate](https://der.orf.at/unternehmen/austrian-broadcasting-corporation/index.html)

---

### 1.2 derstandard.at — Der Standard

**Overview:** Austria's leading quality/broadsheet newspaper (center-left). Comparable online reach to krone.at, with approximately 5+ million unique users per quarter. Trust level among the highest alongside Die Presse (Reuters 2025). Up to 30,000 user-generated comments per day. 46,000 subscribers (24% digital, 2023 OAK data).

**RSS availability:** Yes. Official documentation at `https://about.derstandard.at/services/rss-feeds/`.

**Feed URLs (confirmed, 20 feeds total):**

| Feed | URL |
|------|-----|
| **Main (all news)** | `https://www.derstandard.at/rss` |
| International | `https://www.derstandard.at/rss/international` |
| Inland (domestic) | `https://www.derstandard.at/rss/inland` |
| Wirtschaft (economy) | `https://www.derstandard.at/rss/wirtschaft` |
| Web | `https://www.derstandard.at/rss/web` |
| Sport | `https://www.derstandard.at/rss/sport` |
| Panorama | `https://www.derstandard.at/rss/panorama` |
| Etat (media) | `https://www.derstandard.at/rss/etat` |
| Kultur (culture) | `https://www.derstandard.at/rss/kultur` |
| Wissenschaft (science) | `https://www.derstandard.at/rss/wissenschaft` |
| Gesundheit (health) | `https://www.derstandard.at/rss/gesundheit` |
| Lifestyle | `https://www.derstandard.at/rss/lifestyle` |
| Karriere (career) | `https://www.derstandard.at/rss/karriere` |
| Immobilien (real estate) | `https://www.derstandard.at/rss/immobilien` |
| Diskurs (discourse) | `https://www.derstandard.at/rss/diskurs` |
| dieStandard | `https://www.derstandard.at/rss/diestandard` |
| Live | `https://www.derstandard.at/rss/live` |
| Video | `https://www.derstandard.at/rss/video` |
| Podcast | `https://www.derstandard.at/rss/podcast` |
| Recht (law) | `https://www.derstandard.at/rss/recht` |

**Feed format:** RSS 2.0. Encoding: UTF-8. Language: `de-de`.

**Items per feed:** Approximately 60+ items in the main feed.

**Content depth:** Summary only. Description contains headline text plus a brief excerpt with embedded HTML image tags. Uses Media RSS (MRSS) extension for rich image metadata (150px and 800px thumbnails, photo credits).

**Fields per item:** `<guid>`, `<link>` (with RSS tracking parameter), `<title>`, `<description>`, `<pubDate>`, `<group>` (MRSS with `<content>` images), `<credit>`.

**Update frequency:** High — articles are timestamped throughout the day with frequent updates.

**Vienna-specific feed:** No dedicated Vienna feed. The "Inland" feed covers all of Austria. Der Standard is headquartered in Vienna and naturally covers Vienna events prominently, but there is no geographic filter. The "Panorama" section often contains Vienna-relevant local stories.

**Paywall:** Cookie/consent paywall model. Users can choose "continue reading with ads" (free with tracking) or subscribe (EUR ~12/month, ad-free). Most article content is accessible with the ad-supported option. The paywall is soft — RSS feed content and article text are generally accessible.

**RSS terms of use:** Free for personal use. Commercial restrictions apply:
- Must link directly to the original article (no redirects)
- Must attribute the source (e.g., "Artikel von derStandard.at" or use their logo)
- Text may not be altered
- Exclusive aggregation of derStandard.at teasers on an ad-selling website is prohibited
- Use exclusively for "private personal needs" — further reproduction beyond personal use is not permitted

**Source:** [Der Standard RSS Feeds](https://about.derstandard.at/services/rss-feeds/), [Der Standard Nutzungsbedingungen](https://about.derstandard.at/nutzungsbedingungen/)

---

### 1.3 krone.at — Kronen Zeitung

**Overview:** Austria's largest tabloid newspaper and most widely read daily, with 22.4% national reach (1.7 million readers). krone.at ranks as the #1 most visited news publisher website in Austria (SimilarWeb November 2024). Tabloid style: short articles (max ~1,600 characters), populist, covers politics, crime, entertainment, sports. Over 500,000 user comments per month. 523,000 subscribers (6% digital, 2023 OAK data).

**RSS availability:** Yes. Feeds served via API endpoint.

**Feed URLs (confirmed pattern):**

| Feed | URL |
|------|-----|
| **Main news** | `https://api.krone.at/v1/rss/rssfeed-nachrichten.html` |
| **Wien (Vienna)** | `https://api.krone.at/v1/rss/rssfeed-wien.html` (inferred from pattern) |
| Sport | `https://api.krone.at/v1/rss/rssfeed-sport.html` (inferred) |
| Digital | `https://api.krone.at/v1/rss/rssfeed-digital.html` (inferred) |
| Wirtschaft | `https://api.krone.at/v1/rss/rssfeed-wirtschaft.html` (inferred) |
| Oesterreich | `https://api.krone.at/v1/rss/rssfeed-oesterreich.html` (inferred) |
| Ausland | `https://api.krone.at/v1/rss/rssfeed-ausland.html` (inferred) |
| Tirol | `https://api.krone.at/v1/rss/rssfeed-tirol.html` (inferred) |
| Niederoesterreich | `https://api.krone.at/v1/rss/rssfeed-niederoesterreich.html` (inferred) |
| Kaernten | `https://api.krone.at/v1/rss/rssfeed-kaernten.html` (inferred) |

The confirmed main feed URL is `https://api.krone.at/v1/rss/rssfeed-nachrichten.html`. The section-specific URLs follow the pattern `rssfeed-{section}.html` and are inferred from FeedSpot directory listings. Over 45 category feeds are listed on FeedSpot.

**Feed format:** Likely RSS 2.0 (could not directly fetch to confirm). Encoding: UTF-8 (standard for Austrian news feeds).

**Items per feed:** Not confirmed — could not directly access the feed at research time. Typical for Austrian news feeds: 20-60 items.

**Content depth:** Likely summary only given krone.at's already short article format (max 1,600 characters). Full content extraction from the site would yield relatively short articles.

**Vienna-specific feed:** Likely yes — krone.at has regional sections including Wien, matching the `rssfeed-wien.html` pattern. krone.at has extensive regional coverage across all Austrian states.

**Paywall:** Planned metered paywall (announced as early as 2013). Current status: soft paywall or consent wall. Most content accessible with ad-supported reading.

**Source:** [FeedSpot Kronen Zeitung RSS](https://rss.feedspot.com/kronenzeitung_rss_feeds/), [Kronen Zeitung Wikipedia](https://en.wikipedia.org/wiki/Kronen_Zeitung)

---

### 1.4 kurier.at — Kurier

**Overview:** Major Austrian daily newspaper, based in Vienna. Quality journalism with in-depth analysis and investigative reporting. Part of the Mediaprint group alongside Kronen Zeitung. Announced 40 staff job cuts in 2024. Known for strong "Chronik" (local news/crime) section.

**RSS availability:** Yes.

**Feed URLs (confirmed and inferred):**

| Feed | URL |
|------|-----|
| **Main (all news)** | `https://kurier.at/xml/rss` |
| Main (alternate URL) | `https://kurier.at/xml/rssd` |
| Politik/Inland | `https://kurier.at/politik/inland/xml/rssd` |
| Chronik (local/crime) | `https://kurier.at/chronik/xml/rssd` |
| **Chronik Wien (Vienna local)** | `https://kurier.at/chronik/wien/xml/rssd` (inferred from pattern) |
| Sport | `https://kurier.at/sport/xml/rssd` (inferred) |
| Wirtschaft | `https://kurier.at/wirtschaft/xml/rssd` (inferred) |
| Kultur | `https://kurier.at/kultur/xml/rssd` (inferred) |
| Technologie | `https://kurier.at/technologie/xml/rssd` (inferred) |

The main feed URL `https://kurier.at/xml/rss` is confirmed from the GitHub news-crawler project. The `xml/rssd` variant is confirmed from rss-verzeichnis.de directory listings.

**Feed format:** RSS 2.0 (standard). Encoding: UTF-8.

**Content depth:** Summary/excerpt only. Descriptions contain truncated article summaries, not full text.

**Vienna-specific feed:** Likely yes. kurier.at has a "Chronik Wien" section at `kurier.at/chronik/wien` covering Vienna-specific local news and crime. The RSS feed URL `kurier.at/chronik/wien/xml/rssd` follows the observed pattern but needs verification.

**Paywall:** Soft paywall/consent model. Most content accessible with ads.

**Source:** [RSS Verzeichnis Kurier Chronik](https://www.rss-verzeichnis.de/nachrichten/regional/950-kurier-at-chronik), [GitHub news-crawler feeds](https://github.com/theSoenke/news-crawler/blob/master/data/feeds_de.txt)

---

### 1.5 diepresse.com — Die Presse

**Overview:** Conservative-liberal quality broadsheet, Vienna-based. Among the most trusted Austrian news brands alongside Der Standard (Reuters 2025). Nearly 60,000 subscribers (40%+ digital, 2023 OAK data).

**RSS availability:** Yes.

**Feed URLs:**

| Feed | URL |
|------|-----|
| Home (all news) | `https://www.diepresse.com/rss/home/` |
| Politik | `https://diepresse.com/rss/Politik` |
| Wirtschaft | `https://diepresse.com/rss/Wirtschaft` |
| Mein Geld | `https://diepresse.com/rss/MeinGeld` |
| EU | `https://diepresse.com/rss/EU` |
| Panorama | `https://diepresse.com/rss/Panorama` |
| Sport | `https://diepresse.com/rss/Sport` |
| Kultur | `https://diepresse.com/rss/Kultur` |
| Leben (lifestyle) | `https://diepresse.com/rss/Leben` |
| Tech | `https://diepresse.com/rss/Tech` |
| Science | `https://diepresse.com/rss/Science` |
| Bildung (education) | `https://diepresse.com/rss/Bildung` |
| Gesundheit (health) | `https://diepresse.com/rss/Gesundheit` |
| Recht (law) | `https://diepresse.com/rss/Recht` |
| Spectrum | `https://diepresse.com/rss/Spectrum` |
| Meinung (opinion) | `https://diepresse.com/rss/Meinung` |

Note: URLs sourced from third-party aggregations. Some may use `http://` vs. `https://` — verify current endpoints.

**Vienna-specific feed:** No dedicated Vienna feed. Die Presse is Vienna-based and covers Vienna prominently, but no geographic section feed exists.

**Paywall:** Hard paywall on many articles (premium content). Die Presse is one of the more aggressively paywalled Austrian outlets. RSS feeds likely contain only headlines/summaries for paywalled content.

**Source:** [RSS Agent Die Presse](https://www.rss-agent.at/newsfeed/diepresse-com/56.html), [GitHub news-feeds Austria](https://raw.githubusercontent.com/lemon3/news-feeds/main/dist/austria-news.csv)

---

### 1.6 vienna.at — Local Vienna News

**Overview:** Part of the Russmedia/austria.com network. Hyper-local focus on Vienna news. Covers crime, local politics, events, community stories.

**RSS availability:** Yes.

**Feed URLs:**

| Feed | URL |
|------|-----|
| Main (general) | `http://www.vienna.at/rss` |
| Wien news | `https://www.vienna.at/news/wien/feed` |

RSS guide page: `https://www.vienna.at/features/rssanleitung`

**Vienna-specific feed:** Inherently Vienna-focused. The entire site is dedicated to Vienna news and services.

**Feed terms:** Free for non-commercial purposes.

**Source:** [Vienna.at RSS Guide](https://www.vienna.at/features/rssanleitung), [GitHub news-crawler](https://github.com/theSoenke/news-crawler/blob/master/data/feeds_de.txt)

---

### 1.7 heute.at — Heute (Free Daily)

**Overview:** Austria's most successful free daily newspaper and #1 in Vienna specifically. Founded 2004 in Vienna, expanded to Lower Austria, Upper Austria, and Burgenland. Approximately 1 million readers daily. heute.at ranked #2 most visited news publisher website in Austria (SimilarWeb November 2024). Strong Vienna focus due to its origins as a Vienna free daily.

**RSS availability:** Uncertain. heute.at is listed on FeedSpot's Austrian news RSS directory, confirming a feed exists, but the exact URL is not publicly documented. Likely candidates based on common Austrian patterns:
- `https://www.heute.at/rss`
- `https://www.heute.at/feed`
- `https://www.heute.at/xml/rss`

**Vienna-specific:** Inherently Vienna-centric. The newspaper originated as a Vienna free daily and still has its strongest readership there.

**Paywall:** None (free daily model, ad-supported).

**Source:** [FeedSpot Austria News RSS](https://rss.feedspot.com/austria_news_rss_feeds/)

---

### 1.8 falter.at — Falter (Weekly)

**Overview:** Vienna-based weekly news magazine, published since 1977 (every Wednesday). Covers politics, culture, city life, nature. Strongly Vienna-focused. Circulation approximately 40,000. Significant social media following (116K Twitter followers, 92K Facebook followers).

**RSS availability:** Likely yes (listed on FeedSpot Vienna RSS feeds), but exact URL not confirmed. Likely candidate: `https://www.falter.at/rss` or similar.

**Vienna-specific:** Inherently Vienna-focused. Self-described as "die Wochenzeitung aus Wien" (the weekly newspaper from Vienna). Falter is one of the best sources for Vienna cultural life, local politics, and restaurant/event coverage.

**Update frequency:** Weekly (Wednesdays), with some online-only content between print editions.

**Paywall:** Partial — some investigative content is behind a paywall.

**Source:** [Falter Wikipedia](https://en.wikipedia.org/wiki/Falter)

---

### 1.9 Other Relevant Sources

#### APA-OTS (Austria Press Agency — Original Text Service)

| Detail | Value |
|--------|-------|
| RSS Feed URL | `https://www.ots.at/rss/index` |
| API | `http://api.ots.at` — allows embedding OTS press releases |
| Description | Austria's largest portal for multimedia press releases. ~900,000 visits/month |
| Content type | Press releases from government, companies, organizations |
| ViennaTalksBout value | High — press releases often break news before editorial coverage |

#### oe24.at

| Detail | Value |
|--------|-------|
| RSS Feed URL | `https://www.oe24.at/xml/rss` |
| Description | Tabloid online news outlet. Ranked #5 most visited news site in Austria |

#### Kleine Zeitung (kleinezeitung.at)

| Detail | Value |
|--------|-------|
| RSS Feed URL | `https://www.kleinezeitung.at/rss/hp_stmk` |
| Description | Major regional newspaper (Styria/Carinthia focus). #3 most visited news site in Austria |
| ViennaTalksBout value | Low for Vienna-specific content |

#### Salzburger Nachrichten (sn.at)

| Detail | Value |
|--------|-------|
| RSS Feed URL | `https://www.sn.at/xml/rss` |
| ViennaTalksBout value | Low for Vienna-specific content (Salzburg focus) |

#### futurezone.at

| Detail | Value |
|--------|-------|
| RSS Feed URL | `https://futurezone.at/xml/rss` |
| Description | IT/tech channel (formerly part of ORF, now part of kurier.at) |
| ViennaTalksBout value | Moderate — technology news with Austrian relevance |

#### meinbezirk.at (Regionalmedien Austria)

| Detail | Value |
|--------|-------|
| RSS Feed URL | Not available via standard RSS |
| Description | Hyper-local news platform covering all 23 Vienna districts. 2.2M unique users/month, 33.6% national reach |
| Access method | Proprietary newsfeed system, WhatsApp channels, no traditional RSS |
| ViennaTalksBout value | Very high for Vienna-specific content, but technically difficult to ingest |

#### wien.gv.at (City of Vienna)

| Detail | Value |
|--------|-------|
| RSS Feed URL | Event database RSS: `http://www.wien.gv.at/vadb/internet/AdvPrSrv.asp?Layout=rss-vadb_neu&Type=R&...` |
| Description | Official City of Vienna events database. Max 500 results per query |
| ViennaTalksBout value | Moderate — events represent what's happening in Vienna |

---

## 2. Geolocation / Geographic Filtering Capabilities

### Vienna-Specific Feeds Available

| Source | Vienna-Specific Feed? | Details |
|--------|-----------------------|---------|
| orf.at | **Yes** | `rss.orf.at/wien.xml` — dedicated Vienna regional feed from wien.orf.at |
| krone.at | **Likely yes** | `rssfeed-wien.html` pattern — krone.at has Wien regional section |
| kurier.at | **Likely yes** | `kurier.at/chronik/wien/xml/rssd` — Chronik Wien section |
| vienna.at | **Inherently** | Entire site is Vienna-focused |
| heute.at | **Inherently** | Originated as Vienna free daily, strongest Vienna focus |
| falter.at | **Inherently** | Self-described Vienna weekly |
| derstandard.at | **No** | No Vienna-specific feed; covers all of Austria |
| diepresse.com | **No** | No Vienna-specific feed; covers all of Austria |
| meinbezirk.at | **Yes** | District-level coverage of all 23 Vienna districts (no RSS though) |

### How Inherently Geo-Filtered Is Austrian News?

Austrian news is inherently concentrated on Vienna because:
- Vienna is the capital and largest city (2 million population, ~25% of Austria's 9 million)
- All major media headquarters are in Vienna
- National political coverage (Parliament, government ministries) is Vienna-based
- Cultural institutions (Staatsoper, Burgtheater, major museums) are Vienna-based
- Crime reporting in national outlets skews toward Vienna

**Estimate:** Even in national feeds without geographic filtering, approximately 30-50% of articles have significant Vienna relevance (direct mentions of Vienna, Vienna institutions, or Vienna-based events). This is based on the observation that Austrian national politics, culture, and crime coverage naturally centers on the capital.

### Filtering Strategies for Non-Vienna-Specific Feeds

For sources like derstandard.at and diepresse.com that lack Vienna-specific feeds:
1. **Keyword filtering:** Search for "Wien", "Vienna", Vienna district names (Leopoldstadt, Favoriten, etc.), Vienna landmarks, institutions
2. **Category filtering:** "Chronik" sections often focus on local/crime news, frequently Vienna
3. **Combined approach:** Keyword pre-filter on headlines and summaries

---

## 3. RSS Feed Technical Details Summary

| Source | Format | Encoding | Items per Feed | Content Depth | Vienna Feed? |
|--------|--------|----------|----------------|---------------|--------------|
| orf.at (news) | RDF 1.0 | UTF-8 | 20 | Summary (some items title-only) | Yes (`wien.xml`) |
| orf.at (wien) | RSS 2.0 | UTF-8 | 20 | Summary | Yes |
| derstandard.at | RSS 2.0 | UTF-8 | ~60+ | Summary + MRSS images | No |
| krone.at | RSS 2.0 (likely) | UTF-8 (likely) | Unknown | Summary (likely) | Likely (`rssfeed-wien.html`) |
| kurier.at | RSS 2.0 | UTF-8 | Unknown | Summary/excerpt | Likely (`chronik/wien`) |
| diepresse.com | RSS 2.0 (likely) | UTF-8 (likely) | Unknown | Summary (likely) | No |
| vienna.at | RSS (version unknown) | Unknown | Unknown | Unknown | Inherently |
| ots.at | RSS | Unknown | Unknown | Press release summaries | No (but filterable) |

### Key Technical Observations

- **All feeds provide summaries only, not full article text.** To get full article content, you must follow the link and extract text from the HTML page.
- **orf.at uses two different feed formats:** RDF 1.0 for the main national feed, RSS 2.0 for regional feeds. Feed parsers must handle both.
- **derstandard.at feeds are the richest:** ~60+ items with Media RSS extensions (images at multiple resolutions, photo credits).
- **orf.at feeds are the smallest:** Exactly 20 items per feed, with some items lacking descriptions entirely.
- **Categories/tags:** orf.at uses `<dc:subject>` and `<category>` tags (e.g., "Chronik", "Inland", "Ausland"). derstandard.at does not include per-item categories in the RSS (categories are implicit via separate feed URLs).

---

## 4. Data Volume Estimates

### Articles Per Day by Source (Estimated)

Exact per-source article counts are not publicly reported. These estimates are based on feed sizes, update frequencies, and known editorial constraints.

| Source | Estimated Articles/Day | Notes |
|--------|------------------------|-------|
| orf.at | ~50/day (max 350/week by law) | Legally capped at 350 text articles/week on main news page since 2024 |
| derstandard.at | ~80-120/day | High-frequency publisher; ~60+ items visible in feed at any time |
| krone.at | ~100-150/day | High-volume tabloid; short articles (max 1,600 chars each) |
| kurier.at | ~60-100/day | Quality newspaper with moderate output |
| diepresse.com | ~50-80/day | Quality broadsheet, moderate output |
| vienna.at | ~20-40/day | Local focus, smaller editorial team |
| heute.at | ~80-120/day | High-volume free daily |
| falter.at | ~5-15/day | Weekly publication, limited online-only content |
| ots.at | ~100-200/day | Press releases from all Austrian organizations |

**Total estimated daily output across all sources: ~550-950 articles/day**

### Vienna-Specific Volume

| Category | Estimated Articles/Day |
|----------|----------------------|
| Vienna-specific feeds (orf.at/wien, krone.at/wien, kurier.at/chronik/wien, vienna.at, heute.at) | ~80-150/day |
| Vienna-relevant articles from national feeds (filtered by keyword) | ~50-100/day additional |
| **Total Vienna-relevant articles** | **~130-250/day** |

### Comparison to Social Media Volume

For context, the ViennaTalksBout social media data sources generate:
- Bluesky Jetstream: ~2,000+ events/sec across the entire network (filtering to Vienna yields a small fraction)
- Mastodon wien.rocks: Smaller volume, but pre-filtered to Vienna
- Reddit r/vienna: ~20-50 posts/day + comments

News RSS feeds would contribute **supplementary signal** — fewer items but each item is editorially curated and highly relevant. News stories often **set the agenda** for social media discussion, making them a valuable leading indicator of trending topics.

---

## 5. Technical Considerations

### 5.1 Polling Frequency Recommendations

| Source | Recommended Poll Interval | Rationale |
|--------|--------------------------|-----------|
| orf.at | Every 10-15 minutes | Updates every 30 min per feed metadata; 10-15 min captures changes promptly |
| derstandard.at | Every 10-15 minutes | High-frequency publisher |
| krone.at | Every 10-15 minutes | High-volume tabloid |
| kurier.at | Every 15-20 minutes | Moderate output |
| diepresse.com | Every 15-20 minutes | Moderate output |
| vienna.at | Every 20-30 minutes | Lower volume |
| heute.at | Every 10-15 minutes | High volume |
| falter.at | Every 60 minutes | Weekly publication |
| ots.at | Every 15-20 minutes | Press releases come in bursts |

**Polling best practices:**
1. Send `If-None-Match` (ETag) and `If-Modified-Since` headers on every request — returns HTTP 304 if unchanged, saving bandwidth
2. Respect `Cache-Control` / `max-age` headers — do not poll before cache expires
3. Honor `Retry-After` on HTTP 429 or 503 responses
4. Set a descriptive `User-Agent` string (e.g., `ViennaTalksBout/1.0 +https://viennatalksbout.at`)
5. Support gzip/deflate compression via `Accept-Encoding`
6. Use adaptive polling — learn each feed's actual update pattern and adjust accordingly
7. Respect `<ttl>` values in RSS feeds if present
8. Consider RFC 3229 feed deltas (`A-IM: feed` header) for incremental updates

### 5.2 API Access Beyond RSS

| Source | API Availability |
|--------|-----------------|
| orf.at | RSS only. No public API |
| derstandard.at | RSS only. No public API. Static assets served from `at.staticfiles.at` and `b.staticfiles.at` |
| krone.at | RSS via `api.krone.at` — this is an API endpoint but no documented public API beyond RSS |
| kurier.at | RSS only. No public API |
| diepresse.com | RSS only. No public API |
| ots.at | **Yes** — `http://api.ots.at` allows programmatic access to press releases |
| vienna.at | RSS only |
| heute.at | Unknown |

### 5.3 Content Extraction Challenges

**RSS feeds contain summaries only.** To get full article text for topic extraction, additional steps are needed:

1. **HTML content extraction:** Follow the article link and parse the HTML page. Tools like `newspaper3k`, `readability`, `trafilatura`, or `beautifulsoup` can extract article body text from HTML.

2. **Paywalls by source:**

| Source | Paywall Type | Impact on Extraction |
|--------|-------------|---------------------|
| orf.at | None | Full content accessible |
| derstandard.at | Consent/cookie wall (soft) | Content accessible with ad-consent; may need to accept cookies |
| krone.at | Metered paywall (soft) | Most content accessible; may hit limits with heavy scraping |
| kurier.at | Soft paywall | Most content accessible |
| diepresse.com | Hard paywall (premium) | Many articles fully paywalled — RSS summary may be all that's available |
| vienna.at | None | Full content accessible |
| heute.at | None | Full content accessible |
| falter.at | Partial paywall | Investigative content paywalled |
| ots.at | None | Press releases are public |

3. **JavaScript rendering:** Most Austrian news sites serve article content in the initial HTML (server-side rendered) for SEO purposes. Full JavaScript rendering (headless browser) is generally **not required** for article text extraction. However, interactive elements, comment sections, and some dynamic content may require JS.

4. **Recommendation for ViennaTalksBout:** RSS summaries alone may be sufficient for topic extraction. The LLM can identify trending topics from headlines and short descriptions without needing full article text. This avoids the complexity and legal risk of full-page scraping. If deeper extraction is needed later, prioritize paywall-free sources (orf.at, vienna.at, heute.at, ots.at).

### 5.4 Character Encoding

All Austrian news RSS feeds use **UTF-8 encoding**, which natively supports German umlauts (a, o, u, ss) and all special characters. No special encoding handling is needed beyond ensuring the RSS parser and database support UTF-8.

German-specific characters to expect:
- Umlauts: A/a, O/o, U/u
- Eszett: ss
- Common in Austrian place names, political terms, and proper nouns

---

## 6. Legal / Terms of Service Considerations

### 6.1 EU Directive on Copyright in the Digital Single Market (DSM) — Article 15

Austria has fully transposed Article 15 of the EU DSM Directive into national copyright law (effective December 31, 2021). Key implications:

- **Press publishers' right (Leistungsschutzrecht):** Press publishers have the exclusive right to authorize or prohibit the reproduction and making available of their publications by "information society service providers"
- **Scope:** Online uses of press publications beyond "individual words and very short extracts" require publisher permission
- **Mere linking is exempt:** The directive explicitly allows linking to articles — linking alone does not constitute "making available to the public"
- **Mandatory collective management:** Austria requires all publishers to license these rights collectively through collecting societies (controversial — the European Commission has questioned this approach)
- **"Dominant service providers" carve-out:** The collective management obligation applies only to claims against "dominant service providers" — smaller aggregators may not be affected, but this is legally untested

### 6.2 Per-Source Terms

| Source | RSS Terms | Key Restrictions |
|--------|-----------|-----------------|
| orf.at | Free for non-commercial use | Contains the 20 most current articles; free for all internet users for non-commercial purposes |
| derstandard.at | Free for personal use with conditions | Must link directly to article; must attribute source; no text modification; no exclusive aggregation for ad-selling websites; "private personal needs" only |
| krone.at | Not publicly documented | No specific RSS terms found |
| kurier.at | Not publicly documented | No specific RSS terms found |
| diepresse.com | Not publicly documented | No specific RSS terms found |
| vienna.at | Free for non-commercial use | Available to readers for non-commercial purposes |
| ots.at | Press releases are public | API available; press releases intended for wide distribution |

### 6.3 Risk Assessment for ViennaTalksBout

**What ViennaTalksBout does with news content:**
- Ingests RSS feed summaries/headlines
- Extracts trending topic keywords/phrases using an LLM
- Displays topic names in a tag cloud (not article text or links)
- Does not republish, display, or redistribute article content

**Legal assessment:**
- **Low risk for topic extraction from RSS:** ViennaTalksBout extracts *topics* (e.g., "Donauinselfest", "U2 Storung"), not article text. This is transformative use — the output (a tag cloud of topic names) bears no resemblance to the input (news articles).
- **RSS feeds are public and intended for machine consumption:** RSS is specifically designed for automated reading by software. Using RSS for automated processing aligns with its intended purpose.
- **Article 15 likely does not apply:** ViennaTalksBout does not reproduce or make available press publications. It extracts abstract topic names. This is well below the threshold of "individual words and very short extracts."
- **Respect robots.txt and ToS regardless:** Even if legally permissible, respecting publisher preferences maintains good relationships and avoids complaints.
- **OTS press releases are safest:** Press releases from ots.at are explicitly intended for wide distribution and pose zero legal risk.
- **Avoid displaying article text or full headlines:** If ViennaTalksBout ever adds a drill-down feature showing source articles, that would enter riskier legal territory and would need to link directly to the source (as per derstandard.at's terms).

### 6.4 Practical Recommendations

1. Use RSS feeds as intended — poll at reasonable intervals with proper caching headers
2. Extract only topic keywords, not article text
3. Do not store or display full article content
4. Set a proper User-Agent identifying ViennaTalksBout
5. Respect robots.txt directives
6. If later adding source attribution/links, link directly to original articles per publisher terms
7. Prioritize paywall-free, explicitly public sources (orf.at, vienna.at, ots.at) to minimize any legal friction

---

## 7. Recommended Feed Set for ViennaTalksBout MVP

### Tier 1 — High Priority (Vienna-focused, free, confirmed feeds)

| Source | Feed URL | Rationale |
|--------|----------|-----------|
| orf.at Wien | `https://rss.orf.at/wien.xml` | Dedicated Vienna feed, public broadcaster, no paywall, highest trust |
| orf.at National | `https://rss.orf.at/news.xml` | National agenda-setting stories |
| vienna.at | `http://www.vienna.at/rss` | Inherently Vienna-focused |
| ots.at | `https://www.ots.at/rss/index` | Press releases, no legal restrictions, often break news first |

### Tier 2 — High Priority (national feeds, filtering needed)

| Source | Feed URL | Rationale |
|--------|----------|-----------|
| derstandard.at | `https://www.derstandard.at/rss` | Highest volume (~60+ items), quality journalism, needs keyword filtering |
| krone.at Wien | `https://api.krone.at/v1/rss/rssfeed-wien.html` | Vienna-specific from #1 tabloid (verify URL) |
| kurier.at Chronik | `https://kurier.at/chronik/xml/rssd` | Local news/crime section, high Vienna relevance |

### Tier 3 — Lower Priority

| Source | Feed URL | Rationale |
|--------|----------|-----------|
| diepresse.com | `https://www.diepresse.com/rss/home/` | Quality broadsheet; heavily paywalled |
| kurier.at Main | `https://kurier.at/xml/rss` | Broader national news |
| krone.at National | `https://api.krone.at/v1/rss/rssfeed-nachrichten.html` | High volume tabloid |
| heute.at | (URL needs discovery) | #1 in Vienna readership but RSS URL unconfirmed |
| falter.at | (URL needs discovery) | Best Vienna cultural coverage but weekly cadence |

### Estimated Total Ingestion

With Tier 1 + Tier 2 feeds, polling every 15 minutes:
- ~96 polls per feed per day
- ~7 feeds = ~672 feed requests per day
- With conditional HTTP requests (ETag/If-Modified-Since), most requests return HTTP 304 (no new content)
- Actual new articles to process: ~100-200/day across all feeds
- LLM processing cost: minimal (short summaries, simple topic extraction)

---

## Sources

- [ORF.at RSS Hub](https://rss.orf.at/)
- [ORF Corporate](https://der.orf.at/unternehmen/austrian-broadcasting-corporation/index.html)
- [Der Standard RSS Feeds](https://about.derstandard.at/services/rss-feeds/)
- [Der Standard Nutzungsbedingungen](https://about.derstandard.at/nutzungsbedingungen/)
- [FeedSpot Austria News RSS](https://rss.feedspot.com/austria_news_rss_feeds/)
- [FeedSpot Kronen Zeitung RSS](https://rss.feedspot.com/kronenzeitung_rss_feeds/)
- [RSS Verzeichnis Kurier](https://www.rss-verzeichnis.de/nachrichten/regional/950-kurier-at-chronik)
- [RSS Agent Die Presse](https://www.rss-agent.at/newsfeed/diepresse-com/56.html)
- [GitHub news-feeds Austria CSV](https://raw.githubusercontent.com/lemon3/news-feeds/main/dist/austria-news.csv)
- [GitHub news-crawler feeds_de.txt](https://github.com/theSoenke/news-crawler/blob/master/data/feeds_de.txt)
- [Vienna.at RSS Guide](https://www.vienna.at/features/rssanleitung)
- [Reuters Digital News Report 2025 — Austria](https://reutersinstitute.politics.ox.ac.uk/digital-news-report/2025/austria)
- [Austria Media Landscape](https://medialandscapes.org/country/austria/media/digital-media)
- [SimilarWeb Austria News & Media](https://www.similarweb.com/top-websites/austria/news-and-media/)
- [ORF Law Amendment — Public Media Alliance](https://www.publicmediaalliance.org/orf-law-amendment-sees-digital-focus/)
- [EU DSM Directive Article 15 — Wikipedia](https://en.wikipedia.org/wiki/Directive_on_Copyright_in_the_Digital_Single_Market)
- [Austria DSM Implementation — EDRi](https://edri.org/our-work/how-austria-wants-to-implement-upload-filters-and-ancillary-copyright/)
- [CCIA Comments on Austrian Copyright Act](https://ccianet.org/wp-content/uploads/2022/02/CCIA-Comments-on-the-compatibility-of-the-EU-Copyright-Directive-with-Austrias-Federal-Act-amending-the-Austrian-Copyright-Act-TRIS-notification.pdf)
- [Open RSS Developer Guide](https://openrss.org/guides/developers-guide-to-open-rss-feeds)
- [RSS Polling Best Practices — Kevin Cox](https://kevincox.ca/2022/05/06/rss-feed-best-practices/)
- [Feed Caching Best Practices — Ctrl Blog](https://www.ctrl.blog/entry/feed-caching.html)
- [Wien.gv.at Event RSS Feed](https://digitales.wien.gv.at/beschreibung-des-rss-feeds-fuer-die-wien-at-veranstaltungsdatenbank/)
- [Kronen Zeitung — Wikipedia](https://en.wikipedia.org/wiki/Kronen_Zeitung)
- [Falter — Wikipedia](https://en.wikipedia.org/wiki/Falter)

# Google Trends & Autocomplete as a Data Source for ViennaTalksBout — In-Depth Research

Research date: 2026-02-07

---

## 1. Google Trends API

### Official API (Closed Alpha)

Google announced an **official Google Trends API (alpha)** on July 24, 2025.

- **Status:** Closed alpha — very limited approved testers only
- **Public availability:** Expected late 2026 or early 2027
- **Authentication:** Google Cloud OAuth 2.0
- **Features:** Interest over time (stable scaling), top trends, related queries, region/subregion breakdowns using ISO 3166-2 codes (`AT` for Austria, `AT-9` for Vienna)
- **Data freshness:** Up to **2 days ago** — not truly real-time
- **Cannot be used by ViennaTalksBout today** without alpha access approval

### Unofficial Libraries

| Library | Status | Risk |
|---------|--------|------|
| **pytrends** | **Archived April 17, 2025** — dead, do not use | N/A |
| **trendspyg** | Active, v0.3.0 (early) | High — scrapes unofficial endpoints |
| **SerpApi** | Paid (~$50/mo+), managed | Google filed DMCA lawsuit against SerpApi Dec 2025 |
| **Glimpse** | Paid, enterprise | Lower risk but expensive |

### Real-Time Trending for Austria/Vienna

**Trending Now page** (replaced Daily Search Trends in August 2024):
- Austria (`geo=AT`) is confirmed as a supported country
- Refreshes every **~10 minutes**
- **City-level (Vienna-specific) Trending Now is likely not available** — sub-national regions only for ~40 of 125 countries, and Austria is probably not among them
- Google Trends Explore **does** support `AT-9` (Vienna) for interest-over-time queries — but this is not the same as "what's trending in Vienna"

---

## 2. Geolocation / Geographic Filtering

| Feature | Vienna-Level Filtering? |
|---------|------------------------|
| Trends Explore (interest over time) | Yes (`AT-9`) |
| Trends Explore (related queries) | Yes (`AT-9`) |
| Trending Now | Unlikely (AT country-level only) |
| Official API (alpha) | Theoretically yes (ISO 3166-2) |
| Google Autocomplete | Indirect (`gl=AT`, IP-based) |

**Bottom line:** Explore tool supports Vienna; Trending Now likely Austria-only. Given Vienna is ~23% of Austria's population and the dominant urban center, there is significant overlap with country-level data.

---

## 3. Google Autocomplete / Suggest

Unofficial endpoint: `https://suggestqueries.google.com/complete/search`

- **Parameters:** `q` (query), `client=firefox` (JSON output), `gl=at`, `hl=de`
- **Returns:** 10 suggestions by default, up to 50 with `results=N`
- **No city-level parameter** — uses IP geolocation for additional localization
- **Most "real-time" signal** — suggestions update within minutes of trending shifts
- **Unofficial, undocumented** — violates Google ToS

---

## 4. Reliability Concerns

- **pytrends is dead** (archived April 2025)
- Google deployed **SearchGuard** (JavaScript challenge) in January 2025 — blocks simple HTTP requests
- Google Trends endpoints have changed **multiple times per year**
- Rate limit: ~1,400 requests in 4 hours before triggering 429; blocks can last **16+ hours**
- Google filed **DMCA lawsuit against SerpApi** (December 19, 2025) — signaling willingness to pursue legal action against scrapers

---

## 5. Legal / ToS

Google's ToS **explicitly prohibit** automated scraping. The Google v. SerpApi lawsuit signals escalating enforcement. For ViennaTalksBout: low risk at small, non-commercial scale with respectful rate limiting; high technical risk due to endpoint instability.

---

## 6. Assessment for ViennaTalksBout

| Criterion | Google Trends | Google Autocomplete |
|-----------|--------------|-------------------|
| Vienna-specific data | Partial (Explore: yes; Trending: AT only) | Partial (`gl=at`, no city param) |
| Real-time freshness | ~10 min (Trending Now) | Near-instantaneous |
| Ease of access | Poor (alpha or fragile scrapers) | Good (simple HTTP GET) |
| Reliability | Poor (endpoints change frequently) | Moderate |
| Legal safety | Low-Moderate | Low-Moderate |
| Geo-filtering must-have | **Does not fully meet** — Austria-level only for real-time trends | **Does not fully meet** |

**Recommendation:** Both sources are best suited as **future/supplementary data sources**, not MVP sources. They provide country-level Austrian trending data but lack Vienna-specific granularity for real-time trends. The official API should be monitored for when it becomes publicly available (likely late 2026/early 2027).

## Sources

- [Google Trends API (Alpha) Announcement](https://developers.google.com/search/blog/2025/07/trends-api)
- [pytrends GitHub (Archived)](https://github.com/GeneralMills/pytrends)
- [trendspyg GitHub](https://github.com/flack0x/trendspyg)
- [Google Autocomplete Spec](https://www.fullstackoptimization.com/a/google-autocomplete-google-suggest-unofficial-full-specification)
- [Google v. SerpApi Lawsuit](https://blog.google/technology/safety-security/serpapi-lawsuit/)
- [Google Trends FAQ](https://support.google.com/trends/answer/4365533)

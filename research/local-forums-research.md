# Local Forums & Community Platforms — In-Depth Research for TalkBout

Research date: 2026-02-07

---

## 1. willhaben.at

- **No public API.** Internal API exists (`api.willhaben.at`) but is undocumented and closed.
- **Marketplace, not a forum.** 200,000 new classified ads/day, 20.8M monthly visits — but no discussion content, no comment sections, no community features. User interaction is strictly one-to-one buyer/seller chat.
- **Verdict:** Low value for TalkBout. Wrong content type (listings, not conversations).

---

## 2. Nextdoor

- **Not available in Austria.** Operates in 11 countries; Austria is not among them.
- **Verdict:** Completely unusable. Removed from future data sources list.

---

## 3. Jodel — Most Relevant Discovery

**Jodel** ([jodel.com](https://jodel.com)) is a hyperlocal, anonymous social app **active in Vienna/Austria**.

- Posts are **geofenced to ~10-20km radius** of user's physical location
- Completely anonymous — no profiles, no usernames
- Very popular among students and young adults (18-35)
- Available across Europe: Germany, Switzerland, Austria, Scandinavia, etc.

**API status:** No official public API. Unofficial libraries (`jodel_api` on PyPI) require frequent updates as signing keys change every few weeks. Active bot detection with IP bans.

**ToS:** **Explicitly prohibit** automation and data extraction.

**Verdict:** Content would be ideal for TalkBout (hyperlocal Vienna conversations), but **no public API, explicit ToS prohibition, extremely fragile unofficial tools, significant legal risk**. Monitor for future API availability.

---

## 4. Facebook Groups

- Facebook Groups API was **fully deprecated and removed** by Meta as of April 22, 2024 (Graph API v19).
- Relevant Vienna groups exist but are **completely inaccessible via API**.
- **Verdict:** Not viable since April 2024.

---

## 5. Telegram Groups

- Vienna groups exist: "Welcome to Vienna" (@welcome2vienna), "Vienna Wien Main Group", others
- **Telethon** library (MTProto API) can technically read public channel messages
- **ToS explicitly prohibit** scraping for datasets or AI products
- **Verdict:** Technically feasible via Telethon; moderate-to-high legal risk.

---

## 6. Discord Servers

- Small Vienna/Austria servers: "Austria" (5,724 members), "Vienna Cord" (1,406 members)
- Official API with bot capabilities available
- **ToS explicitly prohibit** scraping and data mining
- **Verdict:** Tiny communities, ToS prohibits data mining. Not viable.

---

## 7. derstandard.at Comments

- Up to **30,000 user-generated comments per day** — most active online news comment section in Austria
- Academic datasets exist: "A Decade of News Forum Interactions" (2025 paper, 75M+ comments)
- **No public API** for comments. Academic access requires collaboration with DerStandard.
- **Verdict:** Very high value but no API. Explore academic data partnership.

---

## 8. meinbezirk.at (Regionalmedien Austria)

- 2.2M unique monthly users nationally; 643,000 unique users for Wien section
- Hyper-local news covering all 23 Vienna districts
- Citizen journalism model ("Regionaut") with user-generated content
- No documented public API or standard RSS
- **Verdict:** High value for Vienna, technically difficult to ingest.

---

## 9. Austrian-Specific Social Platforms

**None exist.** 0% of top social apps in Austria are Austrian-made (42matters). Austrians use international platforms. Historical platforms (studiVZ, Lokalisten.at) are defunct.

---

## Geolocation Assessment

| Platform | Geographic Specificity | Mechanism |
|----------|----------------------|-----------|
| **Jodel** | Excellent (~10-20km geofence) | Built-in GPS |
| **Telegram (Vienna groups)** | Good | Self-selecting communities |
| **meinbezirk.at** | Excellent | Organized by Bezirk (district) |
| **derstandard.at** | Poor | National newspaper, no location tags |
| **willhaben.at** | Moderate | Listings have location data |

---

## Legal Environment (Austria/EU)

- **GDPR enforcement is strict** — December 2025 Austrian Supreme Court ruling against Meta (Max Schrems/noyb case) set binding EU precedent
- **Austrian copyright law** allows rights holders to opt out of text-and-data-mining via robots.txt or ToS
- Most platforms **explicitly prohibit** scraping in ToS

---

## Overall Recommendation

This category is **the hardest and riskiest** to implement, confirming the existing assessment. Prioritized summary:

| Priority | Source | Value | Feasibility | Risk | Action |
|----------|--------|-------|-------------|------|--------|
| 1 | **Jodel** | Very High | Very Low | Very High | Monitor for future API; do not scrape |
| 2 | **derstandard.at comments** | High | Low | High | Explore academic data partnership |
| 3 | **Telegram Vienna groups** | Medium | Moderate | Moderate-High | Only if ToS risk accepted |
| 4 | **meinbezirk.at Wien** | Medium | Low | High | Not recommended without partnership |
| 5 | **Discord Vienna servers** | Low | Moderate | High | Not worth the effort |
| 6 | **willhaben.at** | Very Low | Low | Moderate-High | Not recommended (wrong content type) |
| 7 | **Facebook Groups** | N/A | None | Very High | Not viable since April 2024 |
| 8 | **Nextdoor** | N/A | N/A | N/A | Not available in Austria |

**Key actionable findings:**
- **Nextdoor** removed from future data sources (not in Austria)
- **Jodel** added as a "watch" item — the single most relevant hyperlocal platform, but currently inaccessible
- None of these platforms meet TalkBout's must-have requirement for geolocation filtering via accessible APIs

## Sources

- [Jodel Terms of Use](https://jodel.com/en/terms-of-use/)
- [Telethon GitHub](https://github.com/LonamiWebs/Telethon)
- [Facebook Graph API v19 Changelog](https://developers.facebook.com/docs/graph-api/changelog/version19.0/)
- [Nextdoor Developer Portal](https://developer.nextdoor.com)
- [willhaben GitHub](https://github.com/willhaben)
- [meinbezirk.at](https://www.meinbezirk.at)

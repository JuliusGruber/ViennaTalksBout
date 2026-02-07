# TalkBout - Product Idea

## Vision

TalkBout is a real-time tag cloud that shows what topics people are posting, writing, and commenting about online — starting with Vienna. Anyone can open the web app and instantly see what the city is talking about right now.

## MVP Scope

### Core Feature: Live Tag Cloud

- A **tag cloud** displaying specific trending terms (e.g. "Donauinselfest", "U2 Störung", "Wiener Schnitzel") — not broad categories
- **Tag size** reflects the volume of posts and mentions — more activity means a bigger tag
- **Single color** design for the MVP
- Trending terms are **extracted by an LLM** (Claude) from raw social media data
- The tag cloud **updates live** in real time as new data streams in

### Time Slider

- A **draggable time slider** covering the hours of the current day
- As the user drags the slider, the tag cloud changes to reflect the activity at that point in time
- The tag cloud also updates live when the slider is at the current time

### Data Sources (MVP)

- **Social media platforms** — live streaming from APIs for real-time data ingestion

### Data Sources (Future)

- News sites and blogs
- Local forums and community platforms
- Google Trends and search data
- Other online activity sources

### Target Region

- **MVP: Vienna, Austria**
- Future: Users will be able to select a given region or town

### Target Audience

- **General public** — anyone curious about what's buzzing in Vienna

### Platform

- **Web app** (browser-based)

### Access

- **Open and anonymous** — no login or user accounts required. Visit the site and see the tag cloud immediately.

## Non-Goals (MVP)

- Clicking on tags to drill down into posts/comments
- Multiple color schemes or sentiment visualization
- User accounts or personalization
- Region/town selection (beyond Vienna)
- Mobile-native apps

# TalkBout - Product Idea

## Vision

TalkBout is a real-time tag cloud that shows what topics people are posting, writing, and commenting about online — starting with Vienna. Anyone can open the web app and instantly see what the city is talking about right now.

## MVP Scope

### Core Feature: Living Tag Cloud

- The tag cloud shows **exactly 20 topics** at any given time — specific trending terms (e.g. "Donauinselfest", "U2 Störung", "Wiener Schnitzel"), not broad categories
- Topics have a **lifecycle** — they morph over time:
  1. **Enter**: A new topic fades into the tag cloud when it starts gaining traction
  2. **Grow**: As more people post and comment about it, the tag grows in size
  3. **Shrink**: As Vienna moves on, the topic gradually shrinks
  4. **Disappear**: Once the conversation dies down, the topic fades out — making room for a new one
- This creates a **living, breathing visualization** where the 20 topics are constantly evolving as the city's conversation shifts
- **Single color** design for the MVP
- Topics are **extracted by an LLM** (Claude) from raw social media data
- The tag cloud **updates live** in real time as new data streams in

### Time Slider

- A **draggable time slider** covering the hours of the current day
- As the user drags the slider, the tag cloud **morphs** to reflect the activity at that point in time — topics enter, grow, shrink, and disappear using the same lifecycle animations as the live tag cloud
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

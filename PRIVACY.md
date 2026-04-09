# Privacy Policy

**Waveform** — Last updated: April 2026

Analytics are off by default. On first launch, Waveform asks if you want to help improve the app by sharing anonymous usage data. You can change this at any time in Settings.

---

## What we collect

If you opt in, Waveform sends anonymous usage events to PostHog. Every event is tied to a random UUID generated on your device at first launch. That ID is not linked to your Spotify account, your name, your email, or any device identifier.

The events we collect include:

- App lifecycle signals (app opened, session started, session abandoned)
- Event template selections (which template you picked, whether you entered a vibe description — not the text itself)
- Block operations (block added, removed, resized, reordered — using opaque internal IDs)
- Genre weight adjustments (genre tag name and slider value)
- AI generation signals (request sent, songs returned, latency in milliseconds)
- Song interaction signals (song previewed, kept, skipped, vetoed) — using opaque Spotify track URIs, not song titles or artist names
- Veto reason tags when provided (e.g., "too slow", "overplayed") — not free-text input
- Playlist export events (block count, track count, time from open)
- Error signals (Python exception class name only — never the error message or stack trace)

## What we do NOT collect

- Song titles or artist names
- Your Spotify username, email, display name, or any profile data
- The vibe text or event names you type
- Venue or location information
- Any content from your Gemini API calls beyond numeric counts and latencies
- Free-text input of any kind

Note on IP address: PostHog may capture your IP for approximate geo-bucketing (country/region). Waveform does not explicitly send your IP, but it is transmitted as part of normal HTTPS requests. We are evaluating IP masking for a future update.

## How to opt out

Open **Settings** in the app and turn off "Share anonymous usage data." All event capture stops immediately. No data from that session onward is sent. Previously collected events are retained per PostHog's retention policy (see below) but cannot be retroactively deleted because they carry no identifying information that would let us locate them.

## Data retention

PostHog retains event data for 1 year by default. After that it is automatically deleted.

## Contact

Questions about this policy: [privacy@waveform.app]

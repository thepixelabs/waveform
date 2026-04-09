# Waveform

**AI-powered event playlist designer for Spotify.**

Design the full soundtrack of any event — birthday, wedding, club night, rooftop bar, corporate dinner, house party, and more. Sketch a block schedule, dial in genre weights per block, and let Gemini AI generate every song. Then preview each track and curate with keep, skip, or veto. The playlist lands in your Spotify account with custom cover art.

## How it works

Waveform is a desktop app. The workflow has five steps:

1. **Pick a template** — choose from 10 built-in event types (Birthday, Wedding, Club Night, Rooftop Bar, Corporate Dinner, House Party, Funeral/Memorial, Road Trip, Workout, Focus Session). Each seeds a block schedule and default genre weights. Everything is editable.
2. **Build your schedule** — a horizontal timeline of named blocks. Drag to reorder, grab an edge to resize, click to add. Each block has an archetype (Arrival, Dance Floor, Singalong, Groove, Late Night, Sunrise, etc.) that drives its visual identity and default energy level.
3. **Set genre weights** — per-block sliders from a library of ~300 genre tags. Up to 6 active genres per block. Weights are relative nudges ("lean heavily into X, a bit of Y"), not quotas.
4. **Generate and curate** — Gemini streams songs into a card feed as they arrive. For each song: preview the 30-second Spotify clip, then hit Keep (`Space`), Skip (`S`), or Veto (`Backspace`).
5. **Export** — approved songs go to Spotify as a playlist with parametric cover art generated per block archetype.

### The veto feedback loop

When you veto a song, Waveform records it with optional context (too slow / wrong genre / overplayed / not the vibe / artist already used). Every subsequent generation call in the same session injects those vetoes into the prompt. The AI learns what you don't want in real time — without you touching any settings. Keeps also feed back as positive reinforcement.

## Quick start

Requires Python 3.11+.

```bash
git clone https://github.com/thepixelabs/waveform.git
cd waveform
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` with your credentials (see setup sections below), then run:

```bash
python -m waveform
```

First launch opens a browser for Spotify OAuth and prompts you to opt into anonymous analytics.

### Spotify setup

1. Go to [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard) and log in.
2. Click **Create App**.
3. Set the **Redirect URI** to `http://127.0.0.1:8888/callback/` — copy-paste exactly.
4. Under "Which API/SDKs are you planning to use?", check **Web API**.
5. Save, then open the app's **Settings** page to find your **Client ID** and **Client Secret**.

### Gemini setup

1. Go to [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey).
2. Create an API key. The free tier works for personal use.

### Fill in `.env`

```env
SPOTIFY_CLIENT_ID=your_client_id
SPOTIFY_CLIENT_SECRET=your_client_secret
SPOTIFY_REDIRECT_URI=http://127.0.0.1:8888/callback/
GOOGLE_GENERATIVE_AI_API_KEY=your_gemini_key
```

The `BIRTHDAY_NAME` and `REFERENCE_PLAYLIST_URL` fields in `.env.example` are legacy v1 options. In v2 you set these inside the app per session.

## Customization

**`waveform/prompts/master_prompt.md`** — the main AI instruction file. Describes the overall musical direction, preferred artists per block archetype, and hard rules ("no breakup songs"). Edit this to change what Gemini reaches for across all events.

**`waveform/prompts/veto_addendum.md`** — auto-updated by the veto loop during a session. You can inspect it but don't need to edit it by hand.

**Blocked artists** — `~/.waveform/blocked_artists.txt` is a hard veto list that overrides everything, including the AI's suggestions. One artist per line.

**Genre weights** — set in the app per block. Inherited from the event template by default; override per block as needed.

**Event templates** — select and modify in the app. Use "Save as template" to persist a custom configuration locally.

## Project structure

```
waveform/
├── app/
│   ├── main.py                 # entry point, boots the UI
│   ├── state.py                # observable app state store
│   ├── generation.py           # AI generation pipeline
│   └── export.py               # Spotify export logic
├── domain/
│   ├── event.py                # EventType, EventTemplate
│   ├── block.py                # Block, BlockArchetype
│   ├── session.py              # PlaylistSession, VetoContext
│   └── genre.py                # GenreWeight, GenreTagIndex
├── services/
│   ├── spotify_client.py       # auth, search, export, previews
│   ├── gemini_client.py        # generation, streaming, veto re-prompting
│   ├── cover_art.py            # parametric PIL cover art
│   ├── preview_audio.py        # pygame.mixer audio playback
│   ├── analytics.py            # PostHog wrapper
│   └── persistence.py          # settings.json, session history
├── ui/
│   ├── shell.py                # three-column app layout
│   ├── event_setup.py          # event template selection screen
│   ├── sidebar_schedule.py     # block list sidebar
│   ├── timeline_canvas.py      # drag-and-drop block timeline
│   ├── track_panel.py          # song preview and approve/skip/veto
│   ├── settings_screen.py      # app settings including analytics toggle
│   ├── export_dialog.py        # export confirmation and progress
│   ├── session_history.py      # past sessions browser
│   ├── analytics_consent.py    # first-launch consent modal
│   └── widgets/                # reusable UI components
├── prompts/
│   ├── master_prompt.md        # AI direction (user-editable)
│   └── veto_addendum.md        # session veto context (auto-managed)
├── assets/                     # fonts, icons, textures, palettes
└── tests/
```

Top-level files:

```
requirements.txt
.env.example
LICENSE
PRIVACY.md
DISTRIBUTION.md
```

## License

[Elastic License 2.0 (ELv2)](LICENSE) — free to use, fork, and contribute. Commercial use and hosted services require a separate agreement.

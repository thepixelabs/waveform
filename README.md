# Arc

**The invisible architect of your night.**

> **The Arc Manifesto**
> Bad music kills good parties. We believe every great event deserves an engineered soundtrack—a sequence of energy that moves with the crowd, from the first pour to the final sunrise. Arc isn't just a playlist generator; it's a safeguard for your night.

Design the full soundtrack of any event with the precision of a professional DJ and the intuition of Gemini AI.

**Powered by Spotify.**

---

## How it works

Arc is a desktop engine for engineered emotion. The process is a five-step orchestration:

1. **The Blueprint** — Choose from 10 built-in event templates (Birthday, Wedding, Club Night, etc.). Each seeds a proven block schedule and energy arc.
2. **Define the Frequency** — A horizontal timeline of named blocks. Drag, resize, and reorder the night. Each block has an archetype that drives its visual identity and sonic soul.
3. **Vibe Dialing** — Per-block genre sliders from a library of ~300 tags. Nudge the night—lean into 80s synth, pull back on heavy bass. You are the conductor.
4. **Intuitive Curation** — Gemini streams songs into a live feed. Preview the 30-second pulse, then Keep (`Space`), Skip (`S`), or Veto (`Backspace`).
5. **The Export** — Approved tracks land in Spotify with parametric cover art generated for each chapter of your night.

### The Feedback Loop

When you veto a song, Arc listens. It records the context—*too slow, wrong vibe, overplayed*—and injects that intelligence back into the next generation. The engine learns your crowd's taste in real-time.

## Quick start

Requires Python 3.11+.

```bash
git clone https://github.com/thepixelabs/arc.git
cd arc
```

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

---

*Built with [Gemini](https://ai.google.dev) + [Spotify API](https://developer.spotify.com) by [Pixelabs](https://github.com/thepixelabs)*

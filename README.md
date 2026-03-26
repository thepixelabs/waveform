# 🎂🎧🪩 BirthDJ

**AI-powered birthday party playlists that actually slap.**

Someone's birthday is coming up and you need 8+ hours of music that flows from "people arriving with wine" to "dancing on the couch" to "happy-crying to Bill Withers at 5 AM." BirthDJ handles it — tell it who the birthday person is, link a playlist that captures their taste, and let Gemini AI curate the whole night. The result lands in your Spotify, with custom cover art and everything.

## How it works

BirthDJ structures a party into chapters, each with its own mood:

🍷 **Arrival** → 🎤 **Singalongs** → 🪩 **Dance Floor** → 🌙 **Late Groove** → 🌅 **Sunrise**

You customize the schedule, the block types, and how many songs per hour. Then Gemini generates every song dynamically based on your prompt, your reference playlist, and your rules. No hardcoded song pools — every playlist is unique.

**Three ways to play:**
- **Full Night** — one big playlist, all blocks in order. Press play and forget.
- **Split Night** — separate playlists per vibe. Shuffle each, switch when the energy shifts.
- **Both** — get both at once, same songs.

## Quick start

```bash
git clone https://github.com/thepixelabs/birthdj.git
cd birthdj
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### Spotify setup

1. Go to [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard) and log in
2. Click **Create App**
3. Set the **Redirect URI** to `http://127.0.0.1:8888/callback/` (copy-paste exactly)
4. Check **Web API** under "Which API/SDKs are you planning to use?"
5. Save, then grab your **Client ID** and **Client Secret** from the app's Settings page

### Gemini setup

1. Go to [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)
2. Create an API key — the free tier works fine

### Fill in `.env`

```env
SPOTIFY_CLIENT_ID=your_client_id
SPOTIFY_CLIENT_SECRET=your_client_secret
GOOGLE_GENERATIVE_AI_API_KEY=your_gemini_key
BIRTHDAY_NAME=Sarah
REFERENCE_PLAYLIST_URL=https://open.spotify.com/playlist/...  # optional
```

Then run it:

```bash
python create_playlist.py
```

First launch opens a browser for Spotify login and auto-creates your config files from the included templates. After that, everything happens in the terminal.

## Customization

BirthDJ has three layers you can tweak, from most to least powerful:

**`master_prompt.md`** — The main instruction file. This is where you describe the party, list your favorite artists per block type, set rules like "no breakup songs", and define the overall music direction. It's the primary driver of what Gemini picks. Edit it to completely change the vibe.

**Reference playlist** — Link any Spotify playlist from the menu or `.env`. Gemini sees the actual songs and matches the taste — genre ratios, energy level, artist choices. The master prompt says *who* to pick, the reference playlist shows *what it should sound like*. They work together: the prompt sets direction, the playlist calibrates taste.

**Mood rules** — Quick one-off tweaks from the menu ("extra 80s", "more reggaeton"). These layer on top without touching your files.

On top of all that, `blocked_artists.txt` is a hard veto — any artist listed there is excluded no matter what.

Both `master_prompt.md` and `blocked_artists.txt` are gitignored. The repo ships `.example` templates that get auto-copied on first run.

## Project structure

```
birthdj/
├── create_playlist.py          # The whole app
├── master_prompt.md.example    # AI prompt template (customize → master_prompt.md)
├── blocked_artists.txt.example # Blocklist template (customize → blocked_artists.txt)
├── .env.example                # Credentials template (customize → .env)
├── requirements.txt            # Python dependencies
└── LICENSE                     # Elastic License 2.0
```

## Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## License

[Elastic License 2.0 (ELv2)](LICENSE) — free to use, fork, and contribute. Not for commercial use or hosted services.

---

*Built with [Gemini](https://ai.google.dev) + [Spotify API](https://developer.spotify.com) + love by [Pixelabs](https://github.com/thepixelabs)*

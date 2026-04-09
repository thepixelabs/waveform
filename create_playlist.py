#!/usr/bin/env python3
"""
Waveform v1 CLI — legacy entry point.

This file is kept as a working CLI shim for backward compatibility with v1 users.
The v2 package lives in waveform/ and is the active development path.

v2 entry point: python -m waveform.app.main
"""

import spotipy
from spotipy.oauth2 import SpotifyOAuth
import time
import os
import json
import random
import base64
import io
import re
import math

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass  # .env loading is optional if vars are set manually

try:
    from PIL import Image, ImageDraw, ImageFont

    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False

try:
    from google import genai

    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False

try:
    import questionary

    HAS_QUESTIONARY = True
except ImportError:
    HAS_QUESTIONARY = False

# ─────────────────────────────────────────────────────────────
# CONFIG (all from environment / .env)
# ─────────────────────────────────────────────────────────────

SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET", "")
SPOTIFY_REDIRECT_URI = os.environ.get(
    "SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback/"
)
GEMINI_API_KEY = os.environ.get("GOOGLE_GENERATIVE_AI_API_KEY", "")
BIRTHDAY_NAME = os.environ.get("BIRTHDAY_NAME", "Birthday")
REFERENCE_PLAYLIST_URL = os.environ.get("REFERENCE_PLAYLIST_URL", "")

SCOPE = "playlist-modify-private playlist-modify-public ugc-image-upload"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HISTORY_FILE = os.path.join(BASE_DIR, "song_history.json")
SETTINGS_FILE = os.path.join(BASE_DIR, "settings.json")
MASTER_PROMPT_FILE = os.path.join(BASE_DIR, "master_prompt.md")
BLOCKED_ARTISTS_FILE = os.path.join(BASE_DIR, "blocked_artists.txt")

# Auto-create user files from .example templates on first run
for _user_file in (MASTER_PROMPT_FILE, BLOCKED_ARTISTS_FILE):
    if not os.path.exists(_user_file):
        _example = _user_file + ".example"
        if os.path.exists(_example):
            import shutil
            shutil.copy2(_example, _user_file)

# Available Gemini models
GEMINI_MODELS = [
    "gemini-3.1-pro-preview",
    "gemini-3-pro-preview",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite-preview",
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
]
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"

DEFAULT_PLAYLIST_PREFIX = f"{BIRTHDAY_NAME} Birthday"

ORDER_SYMBOLS = ["①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨", "⑩"]

# Available block types that users can pick from when customizing
BLOCK_TYPES = {
    "chill": {
        "subtitle": "Wine & Chill",
        "emoji": "🍷",
        "description": "Warm, smooth, inviting vibes ✨🍷",
        "color_start": (120, 40, 90),
        "color_end": (60, 15, 50),
    },
    "singalong": {
        "subtitle": "Singalongs",
        "emoji": "🎤",
        "description": "Anthems everyone knows the words to 🔥🎤",
        "color_start": (220, 80, 40),
        "color_end": (160, 40, 20),
    },
    "dance": {
        "subtitle": "Dance Floor",
        "emoji": "🪩",
        "description": "Peak energy, full send, living room club 💃🪩",
        "color_start": (230, 30, 120),
        "color_end": (140, 10, 80),
    },
    "groove": {
        "subtitle": "Late Groove",
        "emoji": "🌙",
        "description": "Groovy afterparty, deep talks, rhythmic 🌙💜",
        "color_start": (30, 50, 160),
        "color_end": (15, 20, 90),
    },
    "sunrise": {
        "subtitle": "Sunrise",
        "emoji": "🌅",
        "description": "Wind down, peaceful, happy exhaustion 🌅🤍",
        "color_start": (50, 140, 140),
        "color_end": (20, 70, 80),
    },
}

DEFAULT_SCHEDULE = [
    {"start": "20:00", "end": "22:00", "type": "chill"},
    {"start": "22:00", "end": "00:00", "type": "singalong"},
    {"start": "00:00", "end": "02:00", "type": "dance"},
    {"start": "02:00", "end": "04:00", "type": "groove"},
    {"start": "04:00", "end": "05:00", "type": "sunrise"},
]

TRACKS_PER_HOUR = 16  # ~16 tracks per hour at ~3.5 min average

DEFAULT_SETTINGS = {
    "schedule": DEFAULT_SCHEDULE,
    "tracks_per_hour": TRACKS_PER_HOUR,
    "total_tracks": None,  # None = auto-calculate from schedule
    "psytrance_enabled": True,
    "psytrance_pct": 30,  # % of dance block that should be psytrance
    "reference_playlist_url": "",
    "mood_rules": "",
    "allow_repeats": False,  # if True, song history is ignored and songs can repeat
    "offer_split_after_full": True,  # ask to also create split playlists after Full Night
    "shuffle_within_blocks": True,  # shuffle song order within each block before adding
    "split_extra_pct": 0,  # extra % of songs per block in split/both modes (0 = same as full)
    "playlist_prefix": "",  # custom playlist name prefix (empty = "{BIRTHDAY_NAME} Birthday")
}


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────


def get_playlist_prefix(settings=None):
    """Get playlist name prefix from settings, falling back to default.

    Supports {name} template which gets replaced with BIRTHDAY_NAME from .env.
    """
    if settings:
        prefix = settings.get("playlist_prefix", "") or DEFAULT_PLAYLIST_PREFIX
    else:
        prefix = DEFAULT_PLAYLIST_PREFIX
    return prefix.replace("{name}", BIRTHDAY_NAME)


def parse_time(t):
    """Parse HH:MM to hours as float."""
    h, m = map(int, t.split(":"))
    return h + m / 60.0


def block_duration_hours(block):
    """Calculate duration in hours, handling midnight crossover."""
    start = parse_time(block["start"])
    end = parse_time(block["end"])
    if end <= start:
        end += 24
    return end - start


def build_blocks_from_schedule(settings):
    """Build block metadata + track counts from the schedule."""
    schedule = settings.get("schedule", DEFAULT_SCHEDULE)
    tph = settings.get("tracks_per_hour", TRACKS_PER_HOUR)
    blocks = []

    for i, sched in enumerate(schedule):
        btype = BLOCK_TYPES.get(sched["type"], BLOCK_TYPES["chill"])
        duration = block_duration_hours(sched)
        track_count = max(5, round(duration * tph))

        block_key = f"block_{i + 1}"
        label = f"{sched['start']} – {sched['end']}"
        order = ORDER_SYMBOLS[i] if i < len(ORDER_SYMBOLS) else f"({i + 1})"

        blocks.append(
            {
                "key": block_key,
                "type": sched["type"],
                "label": label,
                "subtitle": btype["subtitle"],
                "emoji": btype["emoji"],
                "order": order,
                "description": btype["description"],
                "color_start": btype["color_start"],
                "color_end": btype["color_end"],
                "track_count": track_count,
                "duration_hours": duration,
            }
        )

    return blocks


def extract_playlist_id(url_or_id):
    """Extract Spotify playlist ID from a URL or return as-is if already an ID."""
    if not url_or_id:
        return ""
    match = re.search(r"playlist[/:]([a-zA-Z0-9]+)", url_or_id)
    if match:
        return match.group(1)
    return url_or_id.strip()


# ─────────────────────────────────────────────────────────────
# PERSISTENCE
# ─────────────────────────────────────────────────────────────


def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_all_history():
    """Load the full history file (all playlist names)."""
    return load_json(HISTORY_FILE, {})


def save_all_history(all_history):
    """Save the full history file."""
    save_json(HISTORY_FILE, all_history)


def load_history(playlist_name=None):
    """Load history for a specific playlist name. Falls back to legacy format."""
    all_hist = load_all_history()
    # Migrate legacy format (flat {"used_songs": {...}})
    if "used_songs" in all_hist and not any(
        isinstance(v, dict) and "used_songs" in v for v in all_hist.values()
    ):
        legacy = {"used_songs": all_hist.pop("used_songs")}
        migrated_name = DEFAULT_PLAYLIST_PREFIX
        all_hist[migrated_name] = legacy
        save_all_history(all_hist)
    if playlist_name and playlist_name in all_hist:
        return all_hist[playlist_name]
    return {"used_songs": {}}


def save_history(history, playlist_name=None):
    """Save history for a specific playlist name."""
    if not playlist_name:
        playlist_name = DEFAULT_PLAYLIST_PREFIX
    all_hist = load_all_history()
    all_hist[playlist_name] = history
    save_all_history(all_hist)


def get_history_names():
    """Get all playlist names that have history."""
    all_hist = load_all_history()
    return [k for k in all_hist if isinstance(all_hist[k], dict) and all_hist[k].get("used_songs")]


def load_settings():
    saved = load_json(SETTINGS_FILE, None)
    if saved is None:
        settings = json.loads(json.dumps(DEFAULT_SETTINGS))
        # Seed reference URL from env if available
        if REFERENCE_PLAYLIST_URL:
            settings["reference_playlist_url"] = REFERENCE_PLAYLIST_URL
        return settings
    for k, v in DEFAULT_SETTINGS.items():
        if k not in saved:
            saved[k] = v
    return saved


def save_settings(settings):
    save_json(SETTINGS_FILE, settings)


def get_used_keys(history, block_key):
    return set(history.get("used_songs", {}).get(block_key, []))


def mark_used(history, block_key, songs, playlist_name=None):
    if "used_songs" not in history:
        history["used_songs"] = {}
    if block_key not in history["used_songs"]:
        history["used_songs"][block_key] = []
    for title, artist in songs:
        key = f"{title}||{artist}"
        if key not in history["used_songs"][block_key]:
            history["used_songs"][block_key].append(key)
    save_history(history, playlist_name)


def clear_history(playlist_name=None):
    """Clear history for a specific playlist or all history."""
    if playlist_name:
        all_hist = load_all_history()
        if playlist_name in all_hist:
            del all_hist[playlist_name]
            save_all_history(all_hist)
    else:
        if os.path.exists(HISTORY_FILE):
            os.remove(HISTORY_FILE)


# ─────────────────────────────────────────────────────────────
# REFERENCE PLAYLIST
# ─────────────────────────────────────────────────────────────

REFERENCE_CACHE_FILE = os.path.join(BASE_DIR, "reference_playlist.json")


def fetch_reference_playlist(sp, playlist_url):
    """Fetch all tracks from a reference playlist and cache them."""
    playlist_id = extract_playlist_id(playlist_url)
    if not playlist_id:
        return []

    # Check cache — keyed by playlist ID
    if os.path.exists(REFERENCE_CACHE_FILE):
        cached = load_json(REFERENCE_CACHE_FILE, None)
        if (
            cached
            and cached.get("playlist_id") == playlist_id
            and len(cached.get("tracks", [])) > 0
        ):
            print(f"  📋 Reference playlist loaded from cache ({len(cached['tracks'])} tracks).")
            return cached["tracks"]

    print("  📋 Fetching reference playlist from Spotify...")
    tracks = []
    try:
        results = sp.playlist_tracks(playlist_id)
        while results:
            for item in results["items"]:
                track = item.get("track")
                if track:
                    name = track.get("name", "")
                    artists = ", ".join(a["name"] for a in track.get("artists", []))
                    tracks.append({"title": name, "artist": artists})
            if results.get("next"):
                results = sp.next(results)
            else:
                break

        save_json(REFERENCE_CACHE_FILE, {"playlist_id": playlist_id, "tracks": tracks})
        print(f"  ✅ Loaded {len(tracks)} reference tracks.")
    except Exception as e:
        print(f"  ⚠️  Could not fetch reference playlist: {e}")

    return tracks


def format_reference_for_prompt(ref_tracks):
    """Format reference tracks as a concise string for Claude's prompt."""
    if not ref_tracks:
        return ""

    sample = ref_tracks[:80]
    lines = [f"- {t['title']} — {t['artist']}" for t in sample]
    remainder = len(ref_tracks) - len(sample)

    text = "\n\nREFERENCE PLAYLIST (match this taste, ratio of Hebrew/international, and energy):\n"
    text += "\n".join(lines)
    if remainder > 0:
        text += f"\n... and {remainder} more tracks in similar style."
    return text


# ─────────────────────────────────────────────────────────────
# CLAUDE AI — DYNAMIC SONG GENERATION
# ─────────────────────────────────────────────────────────────

TYPE_PROMPTS = {
    "chill": """The Arrival & Mingling.
Warm, inviting, slightly sophisticated. Mid-tempo R&B, light pop, smooth contemporary.
People arriving, catching up. Music present but not overpowering conversation.
Chill vibes, smooth grooves, feel-good atmosphere. Downtempo touches welcome if they fit the mellow BPM.""",
    "singalong": """Pre-Game & Singalongs.
Energy building noticeably. Recognizable anthems, upbeat pop, classic hits.
Songs everyone knows the words to — party starters, empowerment anthems, crowd favorites.
People singing along to choruses.""",
    "dance": """The Peak Dance Party.
HIGH ENERGY, high BPM. Full club/dance floor mode.
Massive dance hits, EDM, high-energy pop, reggaeton.
{psytrance_instruction}""",
    "groove": """Late Night Groove.
Peak has passed but party still going. Drop BPM slightly.
Deep house vibes, nostalgic hits, rhythmic but less aggressive.
Cool afterparty feel — dancing AND deep late-night conversations.
Atmospheric/melodic touches welcome (groovy, hypnotic — NOT hard dance).""",
    "sunrise": """The Wind Down.
Final hour. Chill, atmospheric, acoustic vibes, peaceful classics.
Exhausted but happy, winding down.
Feel-good and grateful vibes — songs about life being beautiful, friendship, good times.
Gentle ambient touches welcome if peaceful.""",
}


def get_block_prompt(block, settings):
    """Generate the prompt text for a block, injecting psytrance instructions for dance blocks."""
    btype = block["type"]
    template = TYPE_PROMPTS.get(btype, TYPE_PROMPTS["chill"])

    if btype == "dance" and settings.get("psytrance_enabled", True):
        psy_pct = settings.get("psytrance_pct", 30)
        psy_instruction = f"~{psy_pct}% of this block's tracks should be psytrance."
    elif btype == "dance":
        psy_instruction = "No psytrance in this block (disabled by user)."
    else:
        psy_instruction = ""

    return template.replace("{psytrance_instruction}", psy_instruction)


def load_master_prompt():
    """Load the master prompt from external .md file."""
    if os.path.exists(MASTER_PROMPT_FILE):
        with open(MASTER_PROMPT_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    return "Every song must actually exist on Spotify. Use real track names and correct artist names."


def load_blocked_artists():
    """Load the blocked artists list from blocked_artists.txt."""
    if os.path.exists(BLOCKED_ARTISTS_FILE):
        with open(BLOCKED_ARTISTS_FILE, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
    return []


def ask_gemini_for_all_blocks(blocks, history, settings, reference_text=""):
    """Use a single Gemini call to generate songs for ALL blocks at once.

    This is cheaper than per-block calls since the master prompt, reference playlist,
    blocked artists, and history are only sent once.
    """
    if not HAS_GEMINI:
        print("  ❌ google-generativeai package not installed. Run: pip install google-generativeai")
        return None

    if not GEMINI_API_KEY:
        print("  ❌ GOOGLE_GENERATIVE_AI_API_KEY not set in .env")
        return None

    mood_rules = settings.get("mood_rules", "")
    master_prompt = load_master_prompt()
    model_name = settings.get("gemini_model", DEFAULT_GEMINI_MODEL)

    # Build block descriptions
    blocks_desc = ""
    for block in blocks:
        block_desc = get_block_prompt(block, settings)
        blocks_desc += f'\n--- BLOCK "{block["key"]}" ---\n'
        blocks_desc += f'Label: {block["label"]} — "{block["subtitle"]}"\n'
        blocks_desc += f"Number of songs: exactly {block['track_count']}\n"
        blocks_desc += f"{block_desc}\n"

    # Collect all used songs across all blocks (skip if repeats allowed)
    all_exclude = set()
    if not settings.get("allow_repeats", False):
        for block in blocks:
            all_exclude.update(get_used_keys(history, block["key"]))
    exclude_text = ""
    if all_exclude:
        exclude_list = [k.replace("||", " — ") for k in list(all_exclude)[:300]]
        exclude_text = (
            "\n\nDo NOT include any of these songs (already used in previous playlists):\n"
            + "\n".join(f"- {s}" for s in exclude_list)
        )

    mood_text = ""
    if mood_rules:
        mood_text = f"\n\nADDITIONAL MOOD RULES FROM USER:\n{mood_rules}\n"

    blocked_artists = load_blocked_artists()
    blocked_text = ""
    if blocked_artists:
        blocked_list = "\n".join(f"- {a}" for a in blocked_artists)
        blocked_text = (
            "\n\nBLOCKED ARTISTS — DO NOT include ANY songs by these artists under any circumstances:\n"
            + blocked_list + "\n"
        )

    block_keys = [b["key"] for b in blocks]
    block_keys_str = ", ".join(f'"{k}"' for k in block_keys)

    prompt = f"""Generate a complete birthday party playlist across multiple time blocks in a SINGLE response.

The birthday person's name is {BIRTHDAY_NAME}.

TIME BLOCKS:
{blocks_desc}

{master_prompt}
{blocked_text}
{mood_text}
{reference_text}
{exclude_text}

Return ONLY a JSON object where each key is the block key and each value is an array of song objects.
The keys MUST be exactly: {block_keys_str}
Each song object has "title" and "artist" keys.
No markdown fences, no explanation — just the JSON object.

Example format:
{{{{"block_1": [{{"title": "Partition", "artist": "Beyoncé"}}], "block_2": [{{"title": "שקט בבקשה", "artist": "סטטיק ובן אל תבורי"}}]}}}}
Use Hebrew characters for Hebrew song titles and artist names where appropriate.
Do NOT repeat any song across blocks."""

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        total_tracks = sum(b["track_count"] for b in blocks)
        print(f"  🤖 Gemini ({model_name}) is curating {total_tracks} tracks across {len(blocks)} blocks...\n")

        # Enable thinking for models that support it (2.5-flash, 2.5-pro, 3.x)
        config = None
        thinking_supported = any(
            x in model_name for x in ("2.5-flash", "2.5-pro", "3-flash", "3-pro", "3.1")
        )
        if thinking_supported:
            from google.genai import types
            config = types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_budget=2048)
            )

        response = client.models.generate_content(
            model=model_name, contents=prompt, config=config
        )

        # Display thinking process if available
        response_text = ""
        for part in response.candidates[0].content.parts:
            is_thought = getattr(part, "thought", False)
            has_text = getattr(part, "text", None)
            if is_thought and has_text:
                print(f"  {DIM}💭 Gemini's thinking:{RESET}")
                for line in has_text.strip().split("\n"):
                    print(f"     {DIM}{line}{RESET}")
                print()
            elif has_text:
                response_text += has_text

        response_text = response_text.strip()

        if response_text.startswith("```"):
            lines = response_text.split("\n")
            response_text = "\n".join(lines[1:-1])

        data = json.loads(response_text)

        # Parse into per-block results
        results = {}
        for block in blocks:
            key = block["key"]
            block_tracks = data.get(key, [])
            songs = []
            for t in block_tracks:
                if isinstance(t, dict) and "title" in t and "artist" in t:
                    songs.append((t["title"], t["artist"]))
            results[key] = songs
            print(f"  ✅ {len(songs)} tracks curated for {block['subtitle']}")

        return results

    except json.JSONDecodeError as e:
        print(f"  ⚠️  Could not parse Gemini response: {e}")
        return None
    except Exception as e:
        print(f"  ⚠️  Gemini API error: {e}")
        return None


# ─────────────────────────────────────────────────────────────
# SPOTIFY
# ─────────────────────────────────────────────────────────────


def authenticate():
    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
        print("  ❌ SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET must be set in .env")
        return None

    auth_manager = SpotifyOAuth(
        scope=SCOPE,
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET,
        redirect_uri=SPOTIFY_REDIRECT_URI,
        open_browser=True,
    )
    return spotipy.Spotify(auth_manager=auth_manager)


def search_track(sp, title, artist):
    query = f"track:{title} artist:{artist}"
    try:
        results = sp.search(q=query, type="track", limit=5)
        if results["tracks"]["items"]:
            return results["tracks"]["items"][0]["uri"]
    except Exception:
        pass

    query = f"{title} {artist}"
    try:
        results = sp.search(q=query, type="track", limit=5)
        if results["tracks"]["items"]:
            return results["tracks"]["items"][0]["uri"]
    except Exception:
        pass
    return None


def generate_cover_image(
    text_line1, text_line2, color_start, color_end, emoji_chars="🎂🦄🎈🪩🎉💃✨🥳"
):
    if not HAS_PILLOW:
        return None

    W, H = 640, 640
    img = Image.new("RGBA", (W, H))
    draw = ImageDraw.Draw(img)

    # Gradient background
    for y in range(H):
        ratio = y / H
        r = int(color_start[0] + (color_end[0] - color_start[0]) * ratio)
        g = int(color_start[1] + (color_end[1] - color_start[1]) * ratio)
        b = int(color_start[2] + (color_end[2] - color_start[2]) * ratio)
        draw.line([(0, y), (W, y)], fill=(r, g, b, 255))

    # Light rays radiating from center-top
    ray_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ray_draw = ImageDraw.Draw(ray_layer)
    cx_ray, cy_ray = W // 2, -50
    for angle_deg in range(0, 360, 15):
        angle = math.radians(angle_deg)
        end_x = cx_ray + int(math.cos(angle) * 900)
        end_y = cy_ray + int(math.sin(angle) * 900)
        ray_draw.line(
            [(cx_ray, cy_ray), (end_x, end_y)],
            fill=(255, 255, 255, random.randint(6, 18)),
            width=random.randint(20, 50),
        )
    img = Image.alpha_composite(img, ray_layer)

    # Large soft bokeh circles (fewer, bigger, more prominent)
    for _ in range(8):
        cx = random.randint(-60, W + 60)
        cy = random.randint(-60, H + 60)
        radius = random.randint(80, 200)
        alpha = random.randint(15, 40)
        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        ball_color = (
            min(255, color_start[0] + random.randint(80, 180)),
            min(255, color_start[1] + random.randint(80, 180)),
            min(255, color_start[2] + random.randint(80, 180)),
            alpha,
        )
        overlay_draw.ellipse(
            [cx - radius, cy - radius, cx + radius, cy + radius], fill=ball_color
        )
        # Ring outline for depth
        ring_color = (*ball_color[:3], min(255, alpha + 20))
        overlay_draw.ellipse(
            [cx - radius, cy - radius, cx + radius, cy + radius],
            outline=ring_color, width=3,
        )
        img = Image.alpha_composite(img, overlay)

    # Confetti rectangles scattered around
    confetti_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    confetti_draw = ImageDraw.Draw(confetti_layer)
    for _ in range(30):
        rx = random.randint(0, W)
        ry = random.randint(0, H)
        rw = random.randint(4, 16)
        rh = random.randint(12, 40)
        ra = random.randint(40, 120)
        rot = random.randint(-45, 45)
        confetti_color = random.choice([
            (255, 200, 100, ra),  # gold
            (255, 120, 180, ra),  # pink
            (120, 220, 255, ra),  # sky blue
            (200, 140, 255, ra),  # lavender
            (255, 255, 255, ra),  # white
        ])
        # Draw rotated rectangle as a small image
        piece = Image.new("RGBA", (rw, rh), confetti_color)
        piece = piece.rotate(rot, expand=True, resample=Image.BICUBIC)
        confetti_layer.paste(piece, (rx, ry), piece)
    img = Image.alpha_composite(img, confetti_layer)

    # Sparkle stars (4-point star shapes instead of just dots)
    sparkle_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sparkle_draw = ImageDraw.Draw(sparkle_layer)
    for _ in range(25):
        sx = random.randint(0, W)
        sy = random.randint(0, H)
        sr = random.randint(6, 18)
        sa = random.randint(100, 240)
        # 4-point star: vertical + horizontal lines with glow
        sparkle_draw.line([(sx, sy - sr), (sx, sy + sr)], fill=(255, 255, 255, sa), width=2)
        sparkle_draw.line([(sx - sr, sy), (sx + sr, sy)], fill=(255, 255, 255, sa), width=2)
        # Small center dot
        sparkle_draw.ellipse(
            [sx - 2, sy - 2, sx + 2, sy + 2],
            fill=(255, 255, 255, min(255, sa + 30)),
        )
    img = Image.alpha_composite(img, sparkle_layer)

    # Diagonal decorative stripes (subtle)
    stripe_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    stripe_draw = ImageDraw.Draw(stripe_layer)
    for i in range(-H, W + H, 80):
        stripe_draw.line(
            [(i, 0), (i + H, H)],
            fill=(255, 255, 255, 10),
            width=30,
        )
    img = Image.alpha_composite(img, stripe_layer)

    # Dark overlay behind text for readability
    text_bg = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    text_bg_draw = ImageDraw.Draw(text_bg)
    text_bg_draw.rectangle([0, H // 2 - 120, W, H // 2 + 120], fill=(0, 0, 0, 100))
    img = Image.alpha_composite(img, text_bg)

    draw = ImageDraw.Draw(img)

    # Load fonts — bold for title, regular for subtitle
    def load_font(size, bold=False):
        paths = [
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
        for p in paths:
            try:
                return ImageFont.truetype(p, size)
            except (OSError, IOError):
                continue
        return ImageFont.load_default()

    font_title = load_font(90, bold=True)
    font_sub = load_font(56)

    # Auto-shrink title if it doesn't fit
    title_font = font_title
    for size in [90, 76, 64, 52]:
        test_font = load_font(size, bold=True)
        bbox = draw.textbbox((0, 0), text_line1, font=test_font)
        if bbox[2] - bbox[0] <= W - 60:
            title_font = test_font
            break

    # Draw title — centered, with strong shadow
    bbox1 = draw.textbbox((0, 0), text_line1, font=title_font)
    w1 = bbox1[2] - bbox1[0]
    h1 = bbox1[3] - bbox1[1]
    x1 = (W - w1) / 2
    y1 = H / 2 - h1 - 10
    # Shadow
    for offset in [(3, 3), (2, 2), (4, 4)]:
        draw.text((x1 + offset[0], y1 + offset[1]), text_line1, fill=(0, 0, 0, 160), font=title_font)
    draw.text((x1, y1), text_line1, fill=(255, 255, 255, 255), font=title_font)

    # Draw subtitle — centered below title
    bbox2 = draw.textbbox((0, 0), text_line2, font=font_sub)
    w2 = bbox2[2] - bbox2[0]
    x2 = (W - w2) / 2
    y2 = y1 + h1 + 16
    draw.text((x2 + 2, y2 + 2), text_line2, fill=(0, 0, 0, 120), font=font_sub)
    draw.text((x2, y2), text_line2, fill=(255, 230, 255, 255), font=font_sub)

    # Convert to RGB for JPEG
    final = img.convert("RGB")
    buf = io.BytesIO()
    final.save(buf, format="JPEG", quality=92)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def set_playlist_cover(sp, playlist_id, image_b64):
    if image_b64:
        try:
            sp.playlist_upload_cover_image(playlist_id, image_b64)
            print("  🖼️  Cover image set.")
        except Exception as e:
            print(f"  ⚠️  Could not set cover: {e}")


def add_tracks_to_playlist(sp, playlist_id, track_list):
    found_uris = []
    not_found = []

    for title, artist in track_list:
        uri = search_track(sp, title, artist)
        if uri:
            found_uris.append(uri)
            print(f"    ✓ {title} — {artist}")
        else:
            not_found.append((title, artist))
            print(f"    ✗ NOT FOUND: {title} — {artist}")
        time.sleep(0.05)

    for i in range(0, len(found_uris), 100):
        batch = found_uris[i : i + 100]
        sp.playlist_add_items(playlist_id, batch)
        if i + 100 < len(found_uris):
            time.sleep(0.3)

    return len(found_uris), not_found


# ─────────────────────────────────────────────────────────────
# MODE 1: Single Playlist
# ─────────────────────────────────────────────────────────────


def generate_all_songs(sp, settings, extra_for_split=False):
    """Common song generation: fetch reference, call Gemini once, return (blocks, all_songs, history).

    If extra_for_split is True and split_extra_pct > 0, requests more songs per block
    so split playlists have extra variety for shuffle mode.
    """
    playlist_name = get_playlist_prefix(settings)
    history = load_history(playlist_name)
    blocks = build_blocks_from_schedule(settings)

    # Apply extra track multiplier for split/both modes
    extra_pct = settings.get("split_extra_pct", 0)
    if extra_for_split and extra_pct > 0:
        for b in blocks:
            b["track_count"] = max(b["track_count"], round(b["track_count"] * (1 + extra_pct / 100)))

    ref_url = settings.get("reference_playlist_url", "")
    ref_tracks = fetch_reference_playlist(sp, ref_url) if ref_url else []
    ref_text = format_reference_for_prompt(ref_tracks)

    print()
    all_songs = ask_gemini_for_all_blocks(blocks, history, settings, ref_text)
    if not all_songs:
        print("  ❌ Could not generate songs. Check your .env configuration.")
        return blocks, None, history

    return blocks, all_songs, history


def create_full_from_songs(sp, blocks, all_songs, history, settings=None, action="create", existing=None):
    """Create a single Full Night playlist from already-generated songs."""
    existing = existing or {}
    user_id = sp.current_user()["id"]
    prefix = get_playlist_prefix(settings)
    name = f"{prefix} 🎂🦄 Full Night"
    flow = " → ".join(f"{b['emoji']} {b['subtitle']}" for b in blocks)
    desc = f"{BIRTHDAY_NAME}'s party playlist: {flow} 🎂"

    pid = prepare_playlist(sp, user_id, name, desc, action, existing)

    img = generate_cover_image(
        prefix, "Full Night", (180, 50, 140), (30, 20, 60)
    )
    set_playlist_cover(sp, pid, img)

    shuffle = settings.get("shuffle_within_blocks", True) if settings else True

    total_found = 0
    all_not_found = []
    for block in blocks:
        songs = all_songs.get(block["key"], [])
        if songs:
            if shuffle:
                songs = list(songs)
                random.shuffle(songs)
            print(f"\n  ── {block['emoji']} {block['subtitle']} ({block['label']}) ──")
            found, nf = add_tracks_to_playlist(sp, pid, songs)
            total_found += found
            all_not_found.extend(nf)
            if history:
                mark_used(history, block["key"], songs, prefix)

    print(f"\n  🎵 Added {total_found} tracks to Full Night playlist.")
    if all_not_found:
        print(f"  ⚠️  {len(all_not_found)} tracks not found.")
    return pid


def create_split_from_songs(sp, blocks, all_songs, history=None, settings=None, action="create", existing=None):
    """Create per-block playlists from already-generated songs (no extra Gemini call)."""
    existing = existing or {}
    user_id = sp.current_user()["id"]
    shuffle = settings.get("shuffle_within_blocks", True) if settings else True
    print()
    for block in blocks:
        songs = all_songs.get(block["key"], [])
        if not songs:
            continue

        if shuffle:
            songs = list(songs)
            random.shuffle(songs)

        name = (
            f"{get_playlist_prefix(settings)} {block['emoji']} {block['order']} {block['subtitle']}"
        )
        desc = block["description"]
        pid = prepare_playlist(sp, user_id, name, desc, action, existing)

        img = generate_cover_image(
            get_playlist_prefix(settings),
            block["subtitle"],
            block["color_start"],
            block["color_end"],
        )
        set_playlist_cover(sp, pid, img)

        found, nf = add_tracks_to_playlist(sp, pid, songs)
        if history:
            mark_used(history, block["key"], songs, get_playlist_prefix(settings))
        print(f"  ✅ {name} — {found} tracks")

    print("\n  🎉 Split playlists created (play each on shuffle).")


# ─────────────────────────────────────────────────────────────
# PLAYLIST DUPLICATE CHECK
# ─────────────────────────────────────────────────────────────


def find_existing_playlists(sp, names):
    """Search user's playlists for any matching the given names. Returns dict of name→playlist."""
    found = {}
    remaining = set(names)
    offset = 0
    while remaining:
        results = sp.current_user_playlists(limit=50, offset=offset)
        if not results["items"]:
            break
        for pl in results["items"]:
            if pl["name"] in remaining:
                found[pl["name"]] = pl
                remaining.discard(pl["name"])
        offset += 50
        if offset >= results["total"]:
            break
    return found


def check_existing_playlists(sp, playlist_names, settings):
    """Check if playlists already exist. Returns 'create'|'overwrite'|'append'|None (abort)."""
    existing = find_existing_playlists(sp, playlist_names)
    if not existing:
        return "create", {}

    print(f"\n  ⚠️  Found {len(existing)} existing playlist(s) with the same name:")
    for name in existing:
        print(f"      • {name}")
    print()

    choice = menu_select([
        "📝 Overwrite (clear existing tracks and replace)",
        "➕ Append (add new tracks to existing playlists)",
        "🆕 Create new (keep both, creates duplicates)",
        "🏷️  Change playlist name first",
    ], back_label="🚫 Cancel")

    if choice is None:
        return None, {}
    elif choice == 0:
        return "overwrite", existing
    elif choice == 1:
        return "append", existing
    elif choice == 2:
        return "create", {}
    elif choice == 3:
        print(f"    {DIM}Use {{name}} to insert the birthday name from .env (e.g., \"{{name}}'s Party\"){RESET}")
        val = input(f"    New playlist name prefix (current: '{get_playlist_prefix(settings)}'): ").strip()
        if val:
            settings["playlist_prefix"] = val
            save_settings(settings)
            print(f"  🏷️  Playlist name set to: {get_playlist_prefix(settings)}")
        return None, {}


def prepare_playlist(sp, user_id, name, desc, action, existing):
    """Create or reuse a playlist based on the action. Returns playlist id."""
    if action in ("overwrite", "append") and name in existing:
        pid = existing[name]["id"]
        if action == "overwrite":
            sp.playlist_replace_items(pid, [])
            print(f"  🔄 Cleared: {name}")
        else:
            print(f"  ➕ Appending to: {name}")
        return pid
    else:
        # Append date/time suffix if a duplicate already exists on Spotify
        if name in existing:
            from datetime import datetime
            suffix = datetime.now().strftime("%d.%m %H:%M")
            name = f"{name} ({suffix})"
        playlist = sp.user_playlist_create(
            user=user_id, name=name, public=False, description=desc
        )
        print(f"  ✅ Created: {name}")
        return playlist["id"]


# ─────────────────────────────────────────────────────────────
# PLAYLIST MODES
# ─────────────────────────────────────────────────────────────


def mode_single_playlist(sp, settings):
    prefix = get_playlist_prefix(settings)
    names = [f"{prefix} 🎂🦄 Full Night"]
    action, existing = check_existing_playlists(sp, names, settings)
    if action is None:
        return

    blocks, all_songs, history = generate_all_songs(sp, settings)
    if not all_songs:
        return

    create_full_from_songs(sp, blocks, all_songs, history, settings=settings, action=action, existing=existing)

    # Offer to also create split playlists
    if settings.get("offer_split_after_full", True):
        print()
        if menu_confirm("Also create split playlists per block (for shuffle)?"):
            create_split_from_songs(sp, blocks, all_songs, settings=settings)


def mode_split_playlists(sp, settings):
    prefix = get_playlist_prefix(settings)
    blocks_preview = build_blocks_from_schedule(settings)
    names = [f"{prefix} {b['emoji']} {b['order']} {b['subtitle']}" for b in blocks_preview]
    action, existing = check_existing_playlists(sp, names, settings)
    if action is None:
        return

    blocks, all_songs, history = generate_all_songs(sp, settings, extra_for_split=True)
    if not all_songs:
        return

    create_split_from_songs(sp, blocks, all_songs, history, settings=settings, action=action, existing=existing)

    # Offer to also create a single Full Night playlist
    print()
    if menu_confirm("Also create a single Full Night playlist (all blocks in order)?"):
        create_full_from_songs(sp, blocks, all_songs, history=None, settings=settings)


def mode_both(sp, settings):
    prefix = get_playlist_prefix(settings)
    blocks_preview = build_blocks_from_schedule(settings)
    names = [f"{prefix} 🎂🦄 Full Night"]
    names += [f"{prefix} {b['emoji']} {b['order']} {b['subtitle']}" for b in blocks_preview]
    action, existing = check_existing_playlists(sp, names, settings)
    if action is None:
        return

    blocks, all_songs, history = generate_all_songs(sp, settings)
    if not all_songs:
        return

    create_full_from_songs(sp, blocks, all_songs, history, settings=settings, action=action, existing=existing)
    create_split_from_songs(sp, blocks, all_songs, settings=settings, action=action, existing=existing)


# ─────────────────────────────────────────────────────────────
# TERMINAL STYLING
# ─────────────────────────────────────────────────────────────

BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
YELLOW = "\033[33m"
GREEN = "\033[32m"
MAGENTA = "\033[35m"
RESET = "\033[0m"


def styled_header(emoji, title):
    """Print a styled section header."""
    print(f"\n  {emoji} {BOLD}{CYAN}{title}{RESET}")
    print(f"  {DIM}{'━' * 40}{RESET}\n")


def styled_label(label, value=""):
    """Print a styled key-value label."""
    if value:
        print(f"    {DIM}{label}:{RESET} {value}")
    else:
        print(f"    {DIM}{label}{RESET}")


def styled_separator():
    """Print a visual separator between sections."""
    print()


# ─────────────────────────────────────────────────────────────
# MENU HELPERS
# ─────────────────────────────────────────────────────────────


def menu_select(options, back_label="🔙 Back", help_texts=None):
    """Show an interactive arrow-key menu. Returns the selected index or None for back/quit.

    Each item in `options` is a display string. A "back" option is appended automatically.
    Returns the 0-based index of the chosen option, or None if back was selected.

    If `help_texts` is provided (list of strings, same length as options), pressing 'i'
    shows the help text for the highlighted option, and 'h' shows all help in a scrollable popup.
    """
    items = list(options) + [back_label]
    if HAS_QUESTIONARY:
        hint = "↑↓ move, Enter select"
        if help_texts:
            hint += ", i info, h help"

        if help_texts and HAS_QUESTIONARY:
            print()
            result = _menu_select_with_help(items, help_texts, back_label)
        else:
            answer = questionary.select(
                "",
                choices=items,
                instruction=f"  {hint}",
                qmark="",
            ).ask()
            result = answer

        if result is None or result == back_label:
            return None
        return items.index(result)
    else:
        # Fallback to numbered input if questionary is not installed
        print()
        for i, opt in enumerate(items):
            print(f"    {i + 1}. {opt}")
        print()
        choice = input("  → ").strip()
        if not choice or choice == str(len(items)):
            return None
        if choice.isdigit() and 1 <= int(choice) <= len(options):
            return int(choice) - 1
        return None


def _menu_select_with_help(items, help_texts, back_label):
    """Arrow-key select menu with 'i' for inline info and 'h' for full help dialog.

    Uses prompt_toolkit directly for keybinding support.
    """
    try:
        from prompt_toolkit import Application
        from prompt_toolkit.layout import Layout, HSplit, Window, FormattedTextControl
        from prompt_toolkit.layout.containers import ConditionalContainer
        from prompt_toolkit.key_binding import KeyBindings
        from prompt_toolkit.formatted_text import HTML
        from prompt_toolkit.widgets import TextArea, Dialog, Label
        from prompt_toolkit.filters import Condition
    except ImportError:
        # Fall back to plain questionary if prompt_toolkit bits missing
        answer = questionary.select("", choices=items, instruction="", qmark="").ask()
        return answer

    # Pad help_texts to match items (back has no help)
    all_help = list(help_texts) + ["Go back to the previous menu."]

    selected = [0]
    info_visible = [False]
    help_visible = [False]
    result = [None]

    kb = KeyBindings()

    @kb.add("up")
    def _up(event):
        selected[0] = (selected[0] - 1) % len(items)
        info_visible[0] = False

    @kb.add("down")
    def _down(event):
        selected[0] = (selected[0] + 1) % len(items)
        info_visible[0] = False

    @kb.add("enter")
    def _enter(event):
        result[0] = items[selected[0]]
        event.app.exit()

    @kb.add("i")
    def _info(event):
        if not help_visible[0]:
            info_visible[0] = not info_visible[0]

    @kb.add("h")
    def _help(event):
        help_visible[0] = not help_visible[0]
        info_visible[0] = False

    @kb.add("escape")
    @kb.add("q")
    def _quit(event):
        if help_visible[0]:
            help_visible[0] = False
        else:
            result[0] = back_label
            event.app.exit()

    help_scroll = [0]

    @kb.add("pagedown")
    @kb.add("c-d")
    def _help_down(event):
        if help_visible[0]:
            help_scroll[0] = min(help_scroll[0] + 5, max(0, len(all_help) - 1))

    @kb.add("pageup")
    @kb.add("c-u")
    def _help_up(event):
        if help_visible[0]:
            help_scroll[0] = max(0, help_scroll[0] - 5)

    def get_menu_text():
        lines = []
        for i, item in enumerate(items):
            pointer = " ❯ " if i == selected[0] else "   "
            if i == selected[0]:
                lines.append(("bold", f"{pointer}{item}\n"))
            else:
                lines.append(("", f"{pointer}{item}\n"))
        return lines

    def get_info_text():
        if help_visible[0]:
            # Full help view
            lines = [("bold", " ── Settings Help ──\n\n")]
            for i, item in enumerate(items):
                if i < len(all_help):
                    lines.append(("bold", f" {item}\n"))
                    lines.append(("", f"   {all_help[i]}\n\n"))
            lines.append(("class:dim", " Press h or Esc to close"))
            return lines
        elif info_visible[0]:
            idx = selected[0]
            if idx < len(all_help):
                return [("class:dim", f" ℹ️  {all_help[idx]}")]
            return []
        return []

    menu_control = FormattedTextControl(get_menu_text)
    info_control = FormattedTextControl(get_info_text)

    layout = Layout(
        HSplit([
            Window(content=menu_control, dont_extend_height=True),
            Window(content=info_control, dont_extend_height=True),
        ])
    )

    app = Application(layout=layout, key_bindings=kb, full_screen=False)
    app.run()
    return result[0]


def menu_confirm(prompt="Are you sure?"):
    """Show a yes/no confirmation menu. Returns True if confirmed."""
    if HAS_QUESTIONARY:
        return questionary.confirm(f"  ⚠️  {prompt}").ask() or False
    else:
        choice = input(f"  ⚠️  {prompt} (y/n): ").strip().lower()
        return choice == "y"


# ─────────────────────────────────────────────────────────────
# MENUS
# ─────────────────────────────────────────────────────────────


def ensure_spotify(sp):
    """Authenticate with Spotify if not already connected. Returns sp."""
    if sp is not None:
        return sp
    print("\n  🔑 Authenticating with Spotify...")
    try:
        sp = authenticate()
        if sp:
            user = sp.current_user()
            print(f"  ✅ Logged in as: {user['display_name']}\n")
        return sp
    except Exception as e:
        print(f"  ❌ Auth failed: {e}")
        print("  💡 Try: rm .cache && python create_playlist.py\n")
        return None


def reference_playlist_menu(sp, settings):
    """Menu to set/update/view the reference playlist. Returns sp (may have been auto-created)."""
    ref_url = settings.get("reference_playlist_url", "")
    styled_header("🎧", "Reference Playlist")
    if ref_url:
        pid = extract_playlist_id(ref_url)
        styled_label("URL", ref_url)
        styled_label("ID", pid)
        if os.path.exists(REFERENCE_CACHE_FILE):
            cached = load_json(REFERENCE_CACHE_FILE, {})
            styled_label("Cached tracks", str(len(cached.get('tracks', []))))
    else:
        print(f"    {DIM}No reference playlist set.{RESET}")
    styled_separator()

    options = [
        "📋 Set / change reference playlist URL",
        "🔄 Re-fetch from Spotify (clear cache)",
        "🗑️  Remove reference playlist",
    ]
    choice = menu_select(options)
    if choice == 0:
        url = input("  Paste Spotify playlist URL: ").strip()
        if url:
            settings["reference_playlist_url"] = url
            save_settings(settings)
            if os.path.exists(REFERENCE_CACHE_FILE):
                os.remove(REFERENCE_CACHE_FILE)
            sp = ensure_spotify(sp)
            if sp:
                fetch_reference_playlist(sp, url)
            print("  ✅ Reference playlist saved.")
    elif choice == 1:
        if os.path.exists(REFERENCE_CACHE_FILE):
            os.remove(REFERENCE_CACHE_FILE)
        sp = ensure_spotify(sp)
        if sp and ref_url:
            fetch_reference_playlist(sp, ref_url)
            print("  ✅ Cache cleared & re-fetched.")
        elif not ref_url:
            print("  ❌ No reference playlist URL set.")
    elif choice == 2:
        settings["reference_playlist_url"] = ""
        save_settings(settings)
        if os.path.exists(REFERENCE_CACHE_FILE):
            os.remove(REFERENCE_CACHE_FILE)
        print("  ✅ Reference playlist removed.")
    return sp


def mood_rules_menu(settings):
    """Set custom mood rules that get injected into Gemini's prompt."""
    current = settings.get("mood_rules", "")
    styled_header("🎭", "Mood Rules")
    print(f"    {DIM}These rules guide Gemini when picking songs.{RESET}")
    print(f"    {DIM}Example: 'No heartbreak songs, she just went through a breakup'{RESET}")
    print(f"    {DIM}Example: 'Include lots of 80s music, she loves synthwave'{RESET}")
    styled_separator()
    if current:
        styled_label("Current rules", f'"{current}"')
    else:
        print(f"    {DIM}No custom rules set.{RESET}")
    styled_separator()

    options = [
        "✏️  Set new rules",
        "🗑️  Clear rules",
    ]
    choice = menu_select(options)
    if choice == 0:
        rules = input("  Enter mood rules: ").strip()
        if rules:
            settings["mood_rules"] = rules
            save_settings(settings)
            print("  ✅ Mood rules saved.")
    elif choice == 1:
        settings["mood_rules"] = ""
        save_settings(settings)
        print("  ✅ Rules cleared.")


def schedule_menu(settings):
    """Edit the party schedule — blocks, times, and types."""
    while True:
        blocks = build_blocks_from_schedule(settings)
        tph = settings.get("tracks_per_hour", TRACKS_PER_HOUR)
        total_tracks = sum(b["track_count"] for b in blocks)
        total_hours = sum(b["duration_hours"] for b in blocks)

        styled_header("🕐", "Party Schedule")
        for i, b in enumerate(blocks):
            print(
                f"    {b['order']} {b['emoji']} {BOLD}{b['label']:15s}{RESET}  {b['subtitle']:14s}  {DIM}~{b['track_count']} tracks ({b['duration_hours']:.1f}h){RESET}"
            )
        print(
            f"\n    {DIM}Total: ~{total_tracks} tracks over {total_hours:.1f} hours ({tph} tracks/hour){RESET}"
        )

        styled_separator()
        print(f"    {BOLD}Available block types:{RESET}")
        for key, bt in BLOCK_TYPES.items():
            print(f"      {bt['emoji']}  {key:12s} {DIM}— {bt['subtitle']}{RESET}")
        styled_separator()

        options = [
            "➕ Add a block",
            "➖ Remove a block",
            f"🔢 Change tracks per hour (currently {tph})",
            "🔄 Reset to default schedule",
        ]
        choice = menu_select(options)
        if choice == 0:
            start = input("    Start time (HH:MM, e.g. 22:00): ").strip()
            end = input("    End time (HH:MM, e.g. 00:00): ").strip()
            # Let user pick block type from a menu
            type_options = [
                f"{bt['emoji']}  {key} — {bt['subtitle']}"
                for key, bt in BLOCK_TYPES.items()
            ]
            type_keys = list(BLOCK_TYPES.keys())
            type_choice = menu_select(type_options)
            if type_choice is not None and ":" in start and ":" in end:
                btype = type_keys[type_choice]
                schedule = settings.get("schedule", [])
                schedule.append({"start": start, "end": end, "type": btype})

                def sort_key(s):
                    h = parse_time(s["start"])
                    return h if h >= 12 else h + 24

                schedule.sort(key=sort_key)
                settings["schedule"] = schedule
                save_settings(settings)
                print("  ✅ Block added.")
            else:
                print("  ❌ Invalid input.")
        elif choice == 1:
            schedule = settings.get("schedule", [])
            if len(schedule) <= 1:
                print("  ❌ Need at least one block.")
            else:
                block_options = [
                    f"{blocks[i]['order']} {blocks[i]['emoji']} {blocks[i]['label']} ({s['start']}–{s['end']})"
                    for i, s in enumerate(schedule)
                ]
                rm_choice = menu_select(block_options)
                if rm_choice is not None:
                    schedule.pop(rm_choice)
                    settings["schedule"] = schedule
                    save_settings(settings)
                    print("  ✅ Block removed.")
        elif choice == 2:
            # Interactive tracks-per-hour editor with live preview
            while True:
                current_tph = settings.get("tracks_per_hour", TRACKS_PER_HOUR)
                preview_blocks = build_blocks_from_schedule(settings)
                preview_total = sum(b["track_count"] for b in preview_blocks)
                preview_hours = sum(b["duration_hours"] for b in preview_blocks)

                styled_header("🔢", f"Tracks Per Hour: {current_tph}")
                for b in preview_blocks:
                    print(
                        f"      {b['order']} {b['emoji']} {b['label']:15s} {DIM}{b['subtitle']:14s}{RESET}  "
                        f"{BOLD}{b['track_count']:3d} tracks{RESET} {DIM}({b['duration_hours']:.1f}h){RESET}"
                    )
                print(f"\n      {DIM}Total: {preview_total} tracks over {preview_hours:.1f}h{RESET}")
                styled_separator()

                tph_options = [
                    f"⬆️  Increase to {current_tph + 1} tracks/hour",
                    f"⬇️  Decrease to {max(1, current_tph - 1)} tracks/hour",
                    "🔢 Type a number",
                ]
                tph_choice = menu_select(tph_options, back_label="✅ Done")
                if tph_choice == 0:
                    settings["tracks_per_hour"] = current_tph + 1
                    save_settings(settings)
                elif tph_choice == 1:
                    settings["tracks_per_hour"] = max(1, current_tph - 1)
                    save_settings(settings)
                elif tph_choice == 2:
                    val = input(f"    Tracks per hour: ").strip()
                    if val.isdigit() and int(val) > 0:
                        settings["tracks_per_hour"] = int(val)
                        save_settings(settings)
                else:
                    break
        elif choice == 3:
            settings["schedule"] = json.loads(json.dumps(DEFAULT_SCHEDULE))
            settings["tracks_per_hour"] = TRACKS_PER_HOUR
            save_settings(settings)
            print("  ✅ Schedule reset to default.")
        else:
            break


def gemini_model_menu(settings):
    """Menu to pick the Gemini model."""
    current = settings.get("gemini_model", DEFAULT_GEMINI_MODEL)
    styled_header("🧠", "Gemini Model Selection")
    styled_label("Current", f"{BOLD}{current}{RESET}")
    styled_separator()

    options = [
        f"{'▸ ' if model == current else '  '}{model}"
        for model in GEMINI_MODELS
    ]
    choice = menu_select(options)
    if choice is not None:
        selected = GEMINI_MODELS[choice]
        settings["gemini_model"] = selected
        save_settings(settings)
        print(f"  ✅ Model set to: {selected}")


def master_prompt_menu():
    """Menu to view/edit the master prompt file."""
    styled_header("🎤", "Master Prompt")
    styled_label("File", MASTER_PROMPT_FILE)
    styled_separator()

    current = load_master_prompt()
    lines = current.split("\n")
    preview = "\n".join(lines[:10])
    if len(lines) > 10:
        preview += f"\n  ... ({len(lines) - 10} more lines)"
    for line in preview.split("\n"):
        print(f"    {DIM}{line}{RESET}")
    styled_separator()

    options = [
        "✏️  Edit master prompt (opens in $EDITOR)",
        "📝 Replace with new text (paste here)",
        "👀 Show full prompt",
    ]
    choice = menu_select(options)
    if choice == 0:
        editor = os.environ.get("EDITOR", "nano")
        os.system(f'{editor} "{MASTER_PROMPT_FILE}"')
        print("  ✅ Master prompt updated.")
    elif choice == 1:
        print("  Type/paste your new master prompt. Enter a blank line when done:")
        new_lines = []
        while True:
            line = input()
            if line == "":
                break
            new_lines.append(line)
        if new_lines:
            with open(MASTER_PROMPT_FILE, "w", encoding="utf-8") as f:
                f.write("\n".join(new_lines) + "\n")
            print("  ✅ Master prompt saved.")
        else:
            print("  ❌ Empty input, not saved.")
    elif choice == 2:
        print()
        print(current)
        print()
        input("  Press Enter to go back...")


def settings_menu(settings):
    while True:
        psy_on = settings.get("psytrance_enabled", True)
        psy_pct = settings.get("psytrance_pct", 30)
        blocks = build_blocks_from_schedule(settings)

        styled_header("⚙️ ", "Settings")

        print(f"    {BOLD}Schedule{RESET}")
        for b in blocks:
            psy_str = f" {MAGENTA}(~{psy_pct}% psy){RESET}" if b["type"] == "dance" and psy_on else ""
            print(
                f"      {b['order']} {b['emoji']} {b['label']:15s} {DIM}{b['subtitle']:14s} ~{b['track_count']} tracks{RESET}{psy_str}"
            )

        styled_separator()
        print(f"    {BOLD}Status{RESET}")
        has_gemini = HAS_GEMINI and GEMINI_API_KEY
        model_name = settings.get("gemini_model", DEFAULT_GEMINI_MODEL)
        allow_repeats = settings.get("allow_repeats", False)
        offer_split = settings.get("offer_split_after_full", True)
        shuffle_on = settings.get("shuffle_within_blocks", True)
        psy_status = f"{GREEN}ON{RESET} — {psy_pct}%" if psy_on else f"{YELLOW}OFF{RESET}"
        print(f"      🍄 Psytrance {DIM}(dance only):{RESET} {psy_status}")
        repeat_status = f"{YELLOW}Allowed{RESET}" if allow_repeats else f"{GREEN}Blocked{RESET}"
        print(f"      🔄 Song repeats: {repeat_status}")
        shuffle_status = f"{GREEN}ON{RESET}" if shuffle_on else f"{YELLOW}OFF{RESET}"
        print(f"      🎲 Shuffle within blocks: {shuffle_status}")
        split_extra = settings.get("split_extra_pct", 0)
        split_extra_status = f"{GREEN}+{split_extra}%{RESET}" if split_extra > 0 else f"{DIM}OFF{RESET}"
        print(f"      🎰 Extra songs in split mode: {split_extra_status}")
        split_status = f"{GREEN}ON{RESET}" if offer_split else f"{YELLOW}OFF{RESET}"
        print(f"      🔗 Offer split after Full Night: {split_status}")
        current_prefix = get_playlist_prefix(settings)
        print(f"      🏷️  Playlist name: {CYAN}{current_prefix}{RESET}")
        ai_status = f"{GREEN}Ready{RESET} — {model_name}" if has_gemini else f"{YELLOW}Not configured{RESET}"
        print(f"      🧠 Gemini AI: {ai_status}")
        ref = settings.get("reference_playlist_url", "")
        print(f"      🎧 Reference: {GREEN + 'Set' + RESET if ref else DIM + 'None' + RESET}")
        mood = settings.get("mood_rules", "")
        print(f"      🎭 Mood rules: {GREEN + 'Set' + RESET if mood else DIM + 'None' + RESET}")
        print(f"      🎤 Master prompt: {DIM}{MASTER_PROMPT_FILE}{RESET}")
        styled_separator()

        options = [
            # Schedule
            "🕐 Edit party schedule (blocks, times, types)",
            # Music
            f"🍄 Toggle psytrance ({'ON → OFF' if psy_on else 'OFF → ON'})",
            f"🎛️  Set psytrance % (currently {psy_pct}%)",
            f"🔄 Toggle song repeats ({'allowed → blocked' if allow_repeats else 'blocked → allowed'})",
            f"🎲 Toggle shuffle within blocks ({'ON → OFF' if shuffle_on else 'OFF → ON'})",
            f"🎰 Set extra songs for split mode (currently +{split_extra}%)",
            f"🔗 Toggle split offer after Full Night ({'ON → OFF' if offer_split else 'OFF → ON'})",
            f"🏷️  Change playlist name (currently: {current_prefix})",
            # AI
            f"🧠 Choose Gemini model ({model_name})",
            "🎤 Edit master prompt",
            # History
            "🧹 Clear song history",
            # System
            "💥 Reset all to defaults",
        ]
        help_texts = [
            "Configure the party timeline: add/remove blocks, set start and end times, change block types (chill, dance, singalong, etc.), and adjust tracks per hour.",
            "When enabled, dance blocks will include psytrance tracks mixed with regular dance music. Other blocks may still include psychedelic-flavored songs at matching BPM.",
            "Controls what percentage of each dance block is psytrance vs. regular dance music. E.g., 30% means roughly 1 in 3 dance songs will be psytrance.",
            "When blocked (default), songs from previous runs are remembered and never repeated. When allowed, the AI can reuse any song — useful if you want fresh playlists without clearing history.",
            "Randomizes the order of songs within each block before adding them to Spotify. Prevents all songs by the same artist or genre from being grouped together.",
            "Request extra songs per block in Split and Both modes. E.g., +50% means a 20-song block gets 30 songs. More songs = more variety when shuffling each playlist.",
            "After creating a Full Night (single) playlist, automatically ask whether to also create separate per-block playlists from the same songs.",
            "Change the prefix used for all playlist names on Spotify. Useful so each run creates distinctly named playlists. Leave empty to use the default (birthday person's name + Birthday).",
            "Choose which Gemini model generates the playlist. Larger models (Pro) are more creative but slower and may cost more. Flash models are fast and free-tier friendly.",
            "Open master_prompt.md in your text editor. This file controls the overall music direction, party context, genre mix, and hard rules for the AI.",
            "Delete all remembered songs so the AI can pick them again. Useful when you want a completely fresh start.",
            "Reset all settings to factory defaults. This does NOT clear song history or your master prompt file.",
        ]
        choice = menu_select(options, help_texts=help_texts)
        if choice == 0:
            schedule_menu(settings)
        elif choice == 1:
            settings["psytrance_enabled"] = not psy_on
            save_settings(settings)
            print(
                f"  🍄 Psytrance {'enabled' if settings['psytrance_enabled'] else 'disabled'}."
            )
        elif choice == 2:
            val = input(
                f"    Psytrance % of dance block (current: {psy_pct}%): "
            ).strip()
            if val.isdigit() and 0 <= int(val) <= 100:
                settings["psytrance_pct"] = int(val)
                save_settings(settings)
                print("  ✅ Saved.")
        elif choice == 3:
            settings["allow_repeats"] = not allow_repeats
            save_settings(settings)
            if settings["allow_repeats"]:
                print("  🔄 Song repeats allowed — history will be ignored.")
            else:
                print("  🔄 Song repeats blocked — history will be used to avoid duplicates.")
        elif choice == 4:
            settings["shuffle_within_blocks"] = not shuffle_on
            save_settings(settings)
            print(f"  🎲 Shuffle {'enabled' if settings['shuffle_within_blocks'] else 'disabled'}.")
        elif choice == 5:
            val = input(
                f"    Extra songs % for split/both modes (current: {split_extra}%, 0 = off): "
            ).strip()
            if val.isdigit() and 0 <= int(val) <= 200:
                settings["split_extra_pct"] = int(val)
                save_settings(settings)
                if int(val) > 0:
                    print(f"  🎰 Split playlists will request +{val}% extra songs per block.")
                else:
                    print("  📈 Extra songs disabled — split uses same count as full.")
        elif choice == 6:
            settings["offer_split_after_full"] = not offer_split
            save_settings(settings)
            print(f"  🔗 Split offer {'enabled' if settings['offer_split_after_full'] else 'disabled'}.")
        elif choice == 7:
            print(f"    {DIM}Use {{name}} to insert the birthday name from .env (e.g., \"{{name}}'s Party\"){RESET}")
            val = input(f"    Playlist name prefix (empty = default '{DEFAULT_PLAYLIST_PREFIX}'): ").strip()
            settings["playlist_prefix"] = val
            save_settings(settings)
            print(f"  🏷️  Playlist name: {get_playlist_prefix(settings)}")
        elif choice == 8:
            gemini_model_menu(settings)
        elif choice == 9:
            master_prompt_menu()
        elif choice == 10:
            current_name = get_playlist_prefix(settings)
            if menu_confirm(f"Clear song history for \"{current_name}\"?"):
                clear_history(current_name)
                print(f"  🧹 History cleared for \"{current_name}\".")
        elif choice == 11:
            for k, v in DEFAULT_SETTINGS.items():
                settings[k] = json.loads(json.dumps(v))
            save_settings(settings)
            print("  ✅ Reset to defaults.")
        else:
            break


def _show_history_for(playlist_name, settings):
    """Display song history bars for a specific playlist name."""
    history = load_history(playlist_name)
    blocks = build_blocks_from_schedule(settings)

    total = 0
    counts = []
    for b in blocks:
        used = len(history.get("used_songs", {}).get(b["key"], []))
        total += used
        counts.append((b, used))
    max_used = max((c for _, c in counts), default=1) or 1
    bar_width = 20
    for b, used in counts:
        filled = round(used / max_used * bar_width) if used > 0 else 0
        bar = f"{CYAN}{'█' * filled}{RESET}{DIM}{'░' * (bar_width - filled)}{RESET}"
        print(f"    {b['emoji']} {b['subtitle']:14s}  {bar}  {used} songs")

    print(f"\n    {BOLD}Total songs remembered:{RESET} {total}")
    return total


def history_menu(settings):
    styled_header("📀", "Song History")

    names = get_history_names()
    current = get_playlist_prefix(settings)

    if not names:
        print(f"    {DIM}No song history yet.{RESET}")
        styled_separator()
        return

    # Show current playlist's history
    print(f"    {BOLD}Current: {current}{RESET}")
    if current in names:
        _show_history_for(current, settings)
    else:
        print(f"    {DIM}No history for this playlist name.{RESET}")

    if len(names) > 1:
        print(f"\n    {DIM}Other playlists with history: {', '.join(n for n in names if n != current)}{RESET}")

    print(f"    {DIM}Gemini will avoid remembered songs on next generation{RESET}")
    styled_separator()

    options = [f"🧹 Clear history for \"{current}\""]
    if len(names) > 1:
        options.append("📀 View other playlist history")
        options.append("💥 Clear ALL history (all playlists)")
    choice = menu_select(options)
    if choice == 0:
        if menu_confirm(f"Clear song history for \"{current}\"?"):
            clear_history(current)
            print(f"  🧹 History cleared for \"{current}\".")
    elif choice == 1 and len(names) > 1:
        other_names = [n for n in names if n != current]
        print()
        pick = menu_select(other_names)
        if pick is not None:
            print(f"\n    {BOLD}{other_names[pick]}{RESET}")
            _show_history_for(other_names[pick], settings)
            styled_separator()
            if menu_confirm(f"Clear history for \"{other_names[pick]}\"?"):
                clear_history(other_names[pick])
                print(f"  🧹 History cleared for \"{other_names[pick]}\".")
    elif choice == 2 and len(names) > 1:
        if menu_confirm("Clear ALL song history for every playlist?"):
            clear_history()
            print("  💥 All history cleared.")


def main_menu(settings):
    blocks = build_blocks_from_schedule(settings)
    total_tracks = sum(b["track_count"] for b in blocks)
    total_hours = sum(b["duration_hours"] for b in blocks)

    styled_header("🎂", f"{BIRTHDAY_NAME}'s Waveform Playlist")

    model_name = settings.get("gemini_model", DEFAULT_GEMINI_MODEL)
    if HAS_GEMINI and GEMINI_API_KEY:
        print(f"    🤖 {DIM}Powered by{RESET} {BOLD}Gemini AI{RESET} {DIM}({model_name}){RESET}")
    else:
        print(f"    {YELLOW}⚠️  Set GOOGLE_GENERATIVE_AI_API_KEY in .env to enable AI{RESET}")

    flow = " → ".join(f"{b['emoji']}" for b in blocks)
    print(f"    🕐 {flow}  {DIM}({total_hours:.0f}h, ~{total_tracks} tracks){RESET}")

    ref = settings.get("reference_playlist_url", "")
    if ref:
        print(f"    📋 {DIM}Reference playlist loaded{RESET}")
    mood = settings.get("mood_rules", "")
    if mood:
        print(f"    🎭 {DIM}Mood: {mood[:60]}{'...' if len(mood) > 60 else ''}{RESET}")

    styled_separator()

    options = [
        # Create
        "🌙 Full Night — single playlist, all blocks in order",
        "💿 Split Night — one playlist per vibe, shuffle each",
        "🪩 Both — full night + split playlists at once",
        # Configure
        "⚙️  Settings & schedule",
        "🎧 Reference playlist",
        "🎭 Mood rules",
        "📀 Song history",
        "🤖 Choose Gemini model",
        "🎤 Master prompt",
    ]
    help_texts = [
        "Creates one big Spotify playlist with all blocks in sequence. Press play when the party starts and don't touch it. Optionally offers to also create split playlists afterward.",
        "Creates a separate Spotify playlist for each block/vibe. Play each on shuffle and switch when the energy shifts. If extra songs is set, each block gets more tracks for variety.",
        "Creates both a Full Night playlist AND separate per-block playlists in one go — same songs, no extra AI cost.",
        "Configure the party schedule, toggle psytrance, shuffle, song repeats, extra songs for split mode, AI model, and more.",
        "Link a Spotify playlist that captures the birthday person's taste. The AI matches its genre ratios, energy levels, and artist choices.",
        "Add quick natural-language rules like 'no breakup songs' or 'heavy on the reggaeton'. These apply on top of the master prompt for this run.",
        "View songs used in previous runs and how many per block. Clear history to make all songs eligible again.",
        "Choose which Gemini model generates the playlist. Larger models are more creative, smaller ones are faster.",
        "Open or edit master_prompt.md — the main AI instruction file that controls the overall music direction and party context.",
    ]
    return options, help_texts


def main():
    # Validate minimum config
    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
        print("\n  ❌ Missing Spotify credentials!")
        print("  Create a .env file with SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET")
        print("  See .env.example for the template.\n")
        return

    settings = load_settings()
    sp = None

    while True:
        options, help_texts = main_menu(settings)
        choice = menu_select(options, back_label="🚪 Exit", help_texts=help_texts)

        if choice in (0, 1, 2):
            sp = ensure_spotify(sp)
            if sp is None:
                continue

            if choice == 0:
                mode_single_playlist(sp, settings)
            elif choice == 1:
                mode_split_playlists(sp, settings)
            else:
                mode_both(sp, settings)

            print("\n  ✨ Done! Check your Spotify.\n")

        elif choice == 3:
            settings_menu(settings)

        elif choice == 4:
            sp = reference_playlist_menu(sp, settings)

        elif choice == 5:
            mood_rules_menu(settings)

        elif choice == 6:
            history_menu(settings)

        elif choice == 7:
            gemini_model_menu(settings)

        elif choice == 8:
            master_prompt_menu()

        elif choice == 9 or choice is None:
            print(f"\n  👋 Happy birthday {BIRTHDAY_NAME}! 🎂🎈\n")
            break


if __name__ == "__main__":
    main()

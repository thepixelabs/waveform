"""
genre.py — GenreWeight domain model and GenreTagIndex.

GenreWeight: a (tag, weight) pair with weight in [0.0, 0.8] (0–80%).
GenreTagIndex: curated tag list with prefix+infix autocomplete.
"""
from __future__ import annotations

import dataclasses
from typing import List


# ---------------------------------------------------------------------------
# GenreWeight
# ---------------------------------------------------------------------------

MAX_WEIGHT = 0.8  # 80% cap (per epic §5.3)


@dataclasses.dataclass(frozen=True)
class GenreWeight:
    tag: str
    weight: float  # 0.0–0.8

    def __post_init__(self) -> None:
        if not self.tag or not self.tag.strip():
            raise ValueError("genre tag must be a non-empty string")
        if not (0.0 <= self.weight <= MAX_WEIGHT):
            raise ValueError(
                f"weight {self.weight} out of range [0.0, {MAX_WEIGHT}]"
            )

    def normalised_tag(self) -> str:
        return self.tag.lower().strip()


# ---------------------------------------------------------------------------
# Genre tag index (~230 curated tags — expanded in Phase 2B)
# ---------------------------------------------------------------------------

_GENRE_TAGS: List[str] = sorted([
    # Electronic — House family
    "house", "deep-house", "tech-house", "progressive-house", "afro-house",
    "melodic-house", "organic-house", "lo-fi-house", "soulful-house",
    "funky-house", "tribal-house", "chicago-house", "french-house",
    # Electronic — Techno / Industrial
    "techno", "minimal-techno", "acid-techno", "industrial-techno",
    "peak-time-techno", "melodic-techno", "dark-techno", "dub-techno",
    # Electronic — Trance
    "trance", "psytrance", "progressive-trance", "uplifting-trance",
    "dark-psytrance", "goa-trance", "full-on", "forest-psytrance",
    # Electronic — Drum and Bass / Jungle
    "drum-and-bass", "liquid-dnb", "neuro-dnb", "jump-up", "jungle",
    "half-step", "rollers",
    # Electronic — Dubstep / Bass
    "dubstep", "brostep", "deep-dubstep", "bass-music", "riddim",
    "future-bass", "wave",
    # Electronic — Ambient / Downtempo
    "ambient", "dark-ambient", "drone", "downtempo", "chillout",
    "atmospheric", "new-age", "meditation", "binaural",
    # Electronic — IDM / Experimental
    "idm", "glitch", "experimental-electronic", "noise", "microsound",
    "modular", "electroacoustic",
    # Electronic — UK / Garage
    "uk-garage", "2-step", "grime", "uk-funky", "bassline", "speed-garage",
    # Electronic — Breaks / Big Beat
    "breakbeat", "nu-skool-breaks", "big-beat", "miami-bass", "electro",
    # Electronic — Lo-fi / Chill
    "lo-fi", "lo-fi-hip-hop", "chillhop", "jazz-hop", "bedroom-pop",
    # Electronic — Other
    "edm", "electro-house", "complextro", "trap-edm", "hardstyle",
    "gabber", "hardcore-techno", "rave", "acid-house", "eurodance",
    "synthwave", "retrowave", "darkwave", "ebm", "industrial",
    "witch-house", "hyperpop", "cloud-rap", "phonk",
    # Pop
    "pop", "synth-pop", "art-pop", "dream-pop", "power-pop", "indie-pop",
    "electropop", "dance-pop", "bubblegum-pop", "k-pop", "j-pop",
    "teen-pop", "chamber-pop", "sophisti-pop",
    # Rock
    "rock", "indie-rock", "alternative-rock", "classic-rock", "hard-rock",
    "punk-rock", "post-punk", "new-wave", "grunge", "shoegaze",
    "dream-rock", "prog-rock", "psychedelic-rock", "garage-rock",
    "math-rock", "emo", "pop-punk", "post-rock",
    # Metal
    "metal", "heavy-metal", "death-metal", "black-metal", "doom-metal",
    "thrash-metal", "nu-metal", "metalcore", "post-metal",
    # Hip-Hop / R&B
    "hip-hop", "rap", "trap", "boom-bap", "conscious-rap", "cloud-rap",
    "drill", "uk-drill", "mumble-rap", "r-and-b", "neo-soul", "soul",
    "funk", "g-funk", "west-coast-hip-hop", "east-coast-hip-hop",
    # Jazz
    "jazz", "bebop", "cool-jazz", "free-jazz", "jazz-fusion", "acid-jazz",
    "nu-jazz", "smooth-jazz", "latin-jazz", "swing",
    # Classical / Orchestral
    "classical", "orchestral", "chamber-music", "opera", "baroque",
    "minimalist-classical", "neo-classical", "contemporary-classical",
    "film-score", "post-classical",
    # World / Latin
    "latin", "reggaeton", "salsa", "cumbia", "merengue", "bachata",
    "bossa-nova", "samba", "afrobeats", "afropop", "highlife",
    "juju", "kwaito", "gqom", "amapiano", "baile-funk", "dancehall",
    "reggae", "ska", "dub", "roots-reggae", "soca", "calypso",
    "fado", "flamenco", "tango", "cumbia", "vallenato",
    # Folk / Country / Americana
    "folk", "indie-folk", "contemporary-folk", "freak-folk", "country",
    "alt-country", "americana", "bluegrass", "country-pop", "outlaw-country",
    "singer-songwriter",
    # Blues / Gospel
    "blues", "delta-blues", "chicago-blues", "gospel", "soul-gospel",
    # Disco / Funk
    "disco", "nu-disco", "italo-disco", "funk", "p-funk",
    # Other
    "soundtrack", "video-game-music", "vaporwave", "seapunk",
    "chillwave", "glo-fi", "indie", "alternative",
])


class GenreTagIndex:
    """Autocomplete index for genre tags. Prefix matches ranked first, infix second."""

    def __init__(self, tags: List[str] | None = None) -> None:
        self._tags: List[str] = list(tags) if tags is not None else list(_GENRE_TAGS)

    def search(self, query: str, limit: int = 8) -> List[str]:
        if not query:
            return self._tags[:limit]
        q = query.lower().strip()
        prefix = [t for t in self._tags if t.startswith(q)]
        infix = [t for t in self._tags if q in t and not t.startswith(q)]
        results = prefix + infix
        return results[:limit]

    def add(self, tag: str) -> None:
        """Add a custom tag to the index (runtime expansion)."""
        normalised = tag.lower().strip()
        if normalised and normalised not in self._tags:
            self._tags.append(normalised)
            self._tags.sort()

    def __len__(self) -> int:
        return len(self._tags)


# Module-level singleton used by the UI
DEFAULT_INDEX = GenreTagIndex()

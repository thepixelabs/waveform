"""
block.py — Block domain model with archetype system.

BlockArchetype: the 10 named visual worlds from epic §7.
ArchetypeSpec: metadata (energy, palette, description) per archetype.
Block: a timeline segment with genre weights.
CustomArchetype: user-defined archetype (Phase 2B).
"""
from __future__ import annotations

import dataclasses
import uuid
from enum import Enum
from typing import Dict, List, Optional, Tuple, Union

from waveform.domain.genre import GenreWeight


# ---------------------------------------------------------------------------
# Built-in archetypes
# ---------------------------------------------------------------------------

class BlockArchetype(str, Enum):
    ARRIVAL = "arrival"
    CHILL = "chill"
    SINGALONG = "singalong"
    GROOVE = "groove"
    DANCE_FLOOR = "dance_floor"
    CLUB_NIGHT = "club_night"
    LATE_NIGHT = "late_night"
    SUNRISE = "sunrise"
    CEREMONY = "ceremony"
    PEAK = "peak"


@dataclasses.dataclass(frozen=True)
class ArchetypeSpec:
    archetype: BlockArchetype
    display_name: str
    description: str
    default_energy: int  # 1–5
    cover_palette: Tuple[str, str, str]  # (primary, secondary, accent)
    emoji: str


ARCHETYPE_SPECS: Dict[BlockArchetype, ArchetypeSpec] = {
    BlockArchetype.ARRIVAL: ArchetypeSpec(
        archetype=BlockArchetype.ARRIVAL,
        display_name="Arrival",
        description="Guests arriving; warm, anticipatory, unhurried.",
        default_energy=2,
        cover_palette=("#F5E6C8", "#D4A5A5", "#4A1942"),
        emoji="🥂",
    ),
    BlockArchetype.CHILL: ArchetypeSpec(
        archetype=BlockArchetype.CHILL,
        display_name="Chill / Ambient",
        description="Low-key, atmospheric, lava-lamp energy.",
        default_energy=2,
        cover_palette=("#0A2540", "#E0F4F4", "#C8B8D8"),
        emoji="🌊",
    ),
    BlockArchetype.SINGALONG: ArchetypeSpec(
        archetype=BlockArchetype.SINGALONG,
        display_name="Singalong",
        description="Crowd-pleasing anthems everyone knows the words to.",
        default_energy=3,
        cover_palette=("#FFF3E0", "#FF7043", "#FFD600"),
        emoji="🎤",
    ),
    BlockArchetype.GROOVE: ArchetypeSpec(
        archetype=BlockArchetype.GROOVE,
        display_name="Groove",
        description="Rhythmic and funky; bodies moving, not yet sweaty.",
        default_energy=4,
        cover_palette=("#2D1B00", "#FF8C00", "#8B4513"),
        emoji="🎸",
    ),
    BlockArchetype.DANCE_FLOOR: ArchetypeSpec(
        archetype=BlockArchetype.DANCE_FLOOR,
        display_name="Dance Floor",
        description="Full energy; neon and sweat.",
        default_energy=5,
        cover_palette=("#000000", "#22D3EE", "#E040FB"),
        emoji="💃",
    ),
    BlockArchetype.CLUB_NIGHT: ArchetypeSpec(
        archetype=BlockArchetype.CLUB_NIGHT,
        display_name="Club Night",
        description="Acid green and UV violet; circuit-board intensity.",
        default_energy=5,
        cover_palette=("#0A0A0A", "#39FF14", "#7B00D4"),
        emoji="🎧",
    ),
    BlockArchetype.LATE_NIGHT: ArchetypeSpec(
        archetype=BlockArchetype.LATE_NIGHT,
        display_name="Late Night",
        description="Smoky, slow-burning; the crowd has thinned.",
        default_energy=3,
        cover_palette=("#1A1020", "#6B6B8A", "#3D3050"),
        emoji="🌙",
    ),
    BlockArchetype.SUNRISE: ArchetypeSpec(
        archetype=BlockArchetype.SUNRISE,
        display_name="Sunrise",
        description="Rothko bands of coral and peach as the night ends.",
        default_energy=2,
        cover_palette=("#FF6B6B", "#FFB347", "#E8C4E8"),
        emoji="🌅",
    ),
    BlockArchetype.CEREMONY: ArchetypeSpec(
        archetype=BlockArchetype.CEREMONY,
        display_name="Ceremony / Reverent",
        description="Linen texture, muted pastels; quiet and meaningful.",
        default_energy=1,
        cover_palette=("#FAF7F2", "#D4C5B0", "#8B7D6B"),
        emoji="🕊️",
    ),
    BlockArchetype.PEAK: ArchetypeSpec(
        archetype=BlockArchetype.PEAK,
        display_name="Peak",
        description="Radial burst; the climax of the night.",
        default_energy=5,
        cover_palette=("#1A0533", "#6B2FFA", "#E040FB"),
        emoji="⚡",
    ),
}


def get_spec(archetype: BlockArchetype) -> ArchetypeSpec:
    return ARCHETYPE_SPECS[archetype]


# ---------------------------------------------------------------------------
# Custom archetype (Phase 2B)
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class CustomArchetype:
    id: str  # e.g. "custom_my_vibe"
    name: str
    emoji: str
    description: str
    palette_start: str  # hex
    palette_end: str    # hex
    energy: int = 3

    # Duck-type compatibility with ArchetypeSpec
    @property
    def display_name(self) -> str:
        return self.name

    @property
    def default_energy(self) -> int:
        return self.energy

    @property
    def cover_palette(self) -> Tuple[str, str, str]:
        """Three-tuple with start, end, and a midpoint blend."""
        return (self.palette_start, self.palette_end, self.palette_start)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "emoji": self.emoji,
            "description": self.description,
            "palette_start": self.palette_start,
            "palette_end": self.palette_end,
            "energy": self.energy,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CustomArchetype":
        return cls(
            id=data.get("id", f"custom_{uuid.uuid4().hex[:8]}"),
            name=data.get("name", "Custom"),
            emoji=data.get("emoji", "🎵"),
            description=data.get("description", ""),
            palette_start=data.get("palette_start", "#1A0533"),
            palette_end=data.get("palette_end", "#6B2FFA"),
            energy=int(data.get("energy", 3)),
        )


_CUSTOM_REGISTRY: Dict[str, CustomArchetype] = {}


def register_custom_archetypes(archetypes: List[CustomArchetype]) -> None:
    """Populate the custom registry from persisted data (called at startup)."""
    _CUSTOM_REGISTRY.clear()
    for a in archetypes:
        _CUSTOM_REGISTRY[a.id] = a


def get_custom_archetype(archetype_id: str) -> Optional[CustomArchetype]:
    return _CUSTOM_REGISTRY.get(archetype_id)


def list_custom_archetypes() -> List[CustomArchetype]:
    return list(_CUSTOM_REGISTRY.values())


def is_custom_archetype_id(archetype_id: str) -> bool:
    return archetype_id in _CUSTOM_REGISTRY


def get_spec_for_id(archetype_id: str) -> Union[ArchetypeSpec, CustomArchetype]:
    """Resolve either a built-in or custom archetype by string id."""
    # Try built-in first
    try:
        arch = BlockArchetype(archetype_id)
        return ARCHETYPE_SPECS[arch]
    except ValueError:
        pass
    # Try custom registry
    custom = _CUSTOM_REGISTRY.get(archetype_id)
    if custom is not None:
        return custom
    raise KeyError(f"Unknown archetype id: {archetype_id!r}")


# ---------------------------------------------------------------------------
# Block
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class Block:
    id: str
    name: str
    archetype: Union[BlockArchetype, str]
    duration_minutes: int  # always a positive integer
    energy_level: int      # 1–5
    genre_weights: List[GenreWeight] = dataclasses.field(default_factory=list)

    def __post_init__(self) -> None:
        if self.duration_minutes < 5:
            raise ValueError("block duration must be at least 5 minutes")
        if not (1 <= self.energy_level <= 5):
            raise ValueError("energy_level must be between 1 and 5")

    @classmethod
    def from_archetype(
        cls,
        archetype: Union[BlockArchetype, str],
        name: str | None = None,
        duration_minutes: int = 60,
        genre_weights: List[GenreWeight] | None = None,
    ) -> "Block":
        spec = get_spec_for_id(str(archetype))
        return cls(
            id=str(uuid.uuid4()),
            name=name or spec.display_name,
            archetype=archetype,
            duration_minutes=duration_minutes,
            energy_level=spec.default_energy,
            genre_weights=genre_weights or [],
        )

    @property
    def track_count(self) -> int:
        """Estimated track count based on 3 min/song average."""
        return max(1, self.duration_minutes // 3)

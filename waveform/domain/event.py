"""
event.py — EventTemplate domain model and all 10 built-in event templates.

EventTemplate is the unit of selection on the Event Setup screen.  It seeds
the block timeline and genre weights when a user picks a template, but every
field is subsequently editable.
"""
from __future__ import annotations

import dataclasses
from typing import Dict, List, Optional

from waveform.domain.block import BlockArchetype
from waveform.domain.genre import GenreWeight


@dataclasses.dataclass
class EventTemplate:
    id: str
    name: str
    description: str
    default_blocks: List[BlockArchetype]        # ordered list of archetypes
    default_genre_weights: List[GenreWeight]    # event-level genre nudges
    skin_id: str                                # palette / texture key
    suggested_duration: int                     # minutes
    accent_color: str = "#7C3AED"              # brand violet default; per-template override


# ---------------------------------------------------------------------------
# 10 built-in templates (epic §8)
# ---------------------------------------------------------------------------

BUILTIN_TEMPLATES: List[EventTemplate] = [
    EventTemplate(
        id="birthday",
        name="Birthday",
        description="From arrival champagne to late-night dancing.",
        default_blocks=[
            BlockArchetype.ARRIVAL,
            BlockArchetype.SINGALONG,
            BlockArchetype.GROOVE,
            BlockArchetype.DANCE_FLOOR,
            BlockArchetype.LATE_NIGHT,
        ],
        default_genre_weights=[
            GenreWeight("pop", 0.5),
            GenreWeight("dance-pop", 0.4),
            GenreWeight("r-and-b", 0.3),
        ],
        skin_id="birthday",
        suggested_duration=300,
        accent_color="#FF6B35",  # hot coral
    ),
    EventTemplate(
        id="wedding",
        name="Wedding",
        description="Ceremony through to first dance and beyond.",
        default_blocks=[
            BlockArchetype.CEREMONY,
            BlockArchetype.ARRIVAL,
            BlockArchetype.SINGALONG,
            BlockArchetype.GROOVE,
            BlockArchetype.DANCE_FLOOR,
            BlockArchetype.SUNRISE,
        ],
        default_genre_weights=[
            GenreWeight("pop", 0.4),
            GenreWeight("soul", 0.3),
            GenreWeight("r-and-b", 0.3),
        ],
        skin_id="wedding",
        suggested_duration=360,
        accent_color="#C9A96E",  # rose gold
    ),
    EventTemplate(
        id="club_night",
        name="Club Night",
        description="Warm-up through to the peak and the cool-down.",
        default_blocks=[
            BlockArchetype.ARRIVAL,
            BlockArchetype.GROOVE,
            BlockArchetype.DANCE_FLOOR,
            BlockArchetype.PEAK,
            BlockArchetype.CLUB_NIGHT,
            BlockArchetype.LATE_NIGHT,
        ],
        default_genre_weights=[
            GenreWeight("techno", 0.5),
            GenreWeight("house", 0.4),
            GenreWeight("tech-house", 0.4),
        ],
        skin_id="club_night",
        suggested_duration=360,
        accent_color="#39FF14",  # acid green
    ),
    EventTemplate(
        id="rooftop_bar",
        name="Rooftop Bar",
        description="Sunset drinks with a view.",
        default_blocks=[
            BlockArchetype.CHILL,
            BlockArchetype.GROOVE,
            BlockArchetype.DANCE_FLOOR,
            BlockArchetype.SUNRISE,
        ],
        default_genre_weights=[
            GenreWeight("nu-disco", 0.4),
            GenreWeight("afrobeats", 0.4),
            GenreWeight("house", 0.3),
        ],
        skin_id="rooftop_bar",
        suggested_duration=240,
        accent_color="#FF7043",  # warm sunset
    ),
    EventTemplate(
        id="corporate_dinner",
        name="Corporate Dinner",
        description="Professional, tasteful background music throughout dinner.",
        default_blocks=[
            BlockArchetype.ARRIVAL,
            BlockArchetype.CHILL,
            BlockArchetype.GROOVE,
        ],
        default_genre_weights=[
            GenreWeight("jazz", 0.4),
            GenreWeight("soul", 0.3),
            GenreWeight("neo-soul", 0.3),
        ],
        skin_id="corporate_dinner",
        suggested_duration=180,
        accent_color="#6B7280",  # muted slate
    ),
    EventTemplate(
        id="house_party",
        name="House Party",
        description="Living room bangers start to finish.",
        default_blocks=[
            BlockArchetype.ARRIVAL,
            BlockArchetype.SINGALONG,
            BlockArchetype.GROOVE,
            BlockArchetype.DANCE_FLOOR,
        ],
        default_genre_weights=[
            GenreWeight("pop", 0.5),
            GenreWeight("hip-hop", 0.4),
            GenreWeight("r-and-b", 0.3),
        ],
        skin_id="house_party",
        suggested_duration=240,
        accent_color="#7C3AED",  # brand violet
    ),
    EventTemplate(
        id="funeral_memorial",
        name="Funeral / Memorial",
        description="Gentle, respectful music to honour a life.",
        default_blocks=[
            BlockArchetype.CEREMONY,
            BlockArchetype.CHILL,
            BlockArchetype.SINGALONG,
        ],
        default_genre_weights=[
            GenreWeight("classical", 0.4),
            GenreWeight("folk", 0.3),
            GenreWeight("soul", 0.3),
        ],
        skin_id="funeral_memorial",
        suggested_duration=120,
        accent_color="#7A8C99",  # desaturated linen blue
    ),
    EventTemplate(
        id="road_trip",
        name="Road Trip",
        description="Windows down, miles ahead.",
        default_blocks=[
            BlockArchetype.SINGALONG,
            BlockArchetype.GROOVE,
            BlockArchetype.SINGALONG,
        ],
        default_genre_weights=[
            GenreWeight("rock", 0.4),
            GenreWeight("pop", 0.4),
            GenreWeight("country", 0.3),
        ],
        skin_id="road_trip",
        suggested_duration=180,
        accent_color="#F59E0B",  # warm amber
    ),
    EventTemplate(
        id="workout",
        name="Workout",
        description="High-intensity training fuel.",
        default_blocks=[
            BlockArchetype.PEAK,
            BlockArchetype.DANCE_FLOOR,
            BlockArchetype.GROOVE,
        ],
        default_genre_weights=[
            GenreWeight("hip-hop", 0.5),
            GenreWeight("edm", 0.4),
            GenreWeight("trap", 0.3),
        ],
        skin_id="workout",
        suggested_duration=60,
        accent_color="#22D3EE",  # cyan
    ),
    EventTemplate(
        id="focus_session",
        name="Focus Session",
        description="Deep work — minimal, non-intrusive, flow-inducing.",
        default_blocks=[
            BlockArchetype.CHILL,
            BlockArchetype.CHILL,
        ],
        default_genre_weights=[
            GenreWeight("ambient", 0.6),
            GenreWeight("lo-fi", 0.4),
        ],
        skin_id="focus_session",
        suggested_duration=120,
        accent_color="#9CA3AF",  # mono grey
    ),
]

TEMPLATE_BY_ID: Dict[str, EventTemplate] = {t.id: t for t in BUILTIN_TEMPLATES}


def get_template(template_id: str) -> Optional[EventTemplate]:
    return TEMPLATE_BY_ID.get(template_id)

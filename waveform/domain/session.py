"""
session.py — PlaylistSession, VetoContext, and related domain objects.

The session is the central domain aggregate for a single user event planning
session.  It accumulates veto/keep history across the lifetime of one event.
"""
from __future__ import annotations

import dataclasses
import uuid
from typing import Any, Dict, List, Optional, Set

from waveform.domain.block import Block, BlockArchetype, GenreWeight, get_spec_for_id


# ---------------------------------------------------------------------------
# Veto system
# ---------------------------------------------------------------------------

VETO_REASON_TAGS = [
    "too slow",
    "wrong genre",
    "overplayed",
    "not the vibe",
    "artist already used",
]


@dataclasses.dataclass
class VetoEntry:
    block_id: str
    title: str
    artist: str
    reason_tag: Optional[str] = None


@dataclasses.dataclass
class KeepEntry:
    block_id: str
    title: str
    artist: str


@dataclasses.dataclass
class VetoContext:
    """Accumulates veto and keep signals across a session.

    This is the core feedback loop — it feeds back into AI prompts so the
    model learns user taste within a session.
    """

    vetoes: List[VetoEntry] = dataclasses.field(default_factory=list)
    keeps: List[KeepEntry] = dataclasses.field(default_factory=list)
    _vetoed_ids: Set[str] = dataclasses.field(
        default_factory=set, repr=False, compare=False
    )

    def add_veto(
        self,
        block_id: str,
        title: str,
        artist: str,
        reason_tag: Optional[str] = None,
    ) -> None:
        entry = VetoEntry(block_id=block_id, title=title, artist=artist, reason_tag=reason_tag)
        self.vetoes.append(entry)
        self._vetoed_ids.add(self._key(title, artist))

    def add_keep(self, block_id: str, title: str, artist: str) -> None:
        self.keeps.append(KeepEntry(block_id=block_id, title=title, artist=artist))

    def is_vetoed(self, title: str, artist: str) -> bool:
        return self._key(title, artist) in self._vetoed_ids

    def vetoes_for_block(self, block_id: str) -> List[VetoEntry]:
        return [v for v in self.vetoes if v.block_id == block_id]

    def format_for_prompt(self) -> str:
        """Render the veto/keep context as a human-readable block for injection into AI prompts."""
        parts: List[str] = []

        if self.vetoes:
            parts.append("=== Songs to AVOID (user has rejected these) ===")
            for v in self.vetoes:
                reason = f" ({v.reason_tag})" if v.reason_tag else ""
                parts.append(f"- \"{v.title}\" by {v.artist}{reason}")
            parts.append(
                "Do NOT suggest any of the above songs, and avoid songs with a very similar feel unless the reason tag is unrelated."
            )

        if self.keeps:
            parts.append("=== Songs the user LIKED (use as calibration) ===")
            for k in self.keeps:
                parts.append(f"- \"{k.title}\" by {k.artist}")
            parts.append(
                "Use these as a reference for the vibe and energy the user is looking for. "
                "Do not suggest the same songs again, but do explore similar territory."
            )

        return "\n".join(parts)

    @staticmethod
    def _key(title: str, artist: str) -> str:
        return f"{title.lower().strip()}||{artist.lower().strip()}"

    @property
    def veto_count(self) -> int:
        return len(self.vetoes)


# ---------------------------------------------------------------------------
# PlaylistSession
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class PlaylistSession:
    """Root aggregate for one event planning session."""

    session_id: str
    event_name: str
    event_template: Any  # EventTemplate | None
    blocks: List[Block]
    vibe_override: str = ""
    keep_history: Dict[str, bool] = dataclasses.field(default_factory=dict)
    veto_context: VetoContext = dataclasses.field(default_factory=VetoContext)
    playlist_urls: List[str] = dataclasses.field(default_factory=list)

    # Ephemeral (not serialised in all paths)
    _resume_missing_fields: List[str] = dataclasses.field(
        default_factory=list, repr=False, compare=False
    )

    def add_block(self, block: Block) -> None:
        self.blocks.append(block)

    def remove_block(self, block_id: str) -> None:
        self.blocks = [b for b in self.blocks if b.id != block_id]

    def reorder_blocks(self, from_index: int, to_index: int) -> None:
        if from_index == to_index:
            return
        block = self.blocks.pop(from_index)
        self.blocks.insert(to_index, block)

    def mark_kept(self, title: str, artist: str) -> None:
        key = f"{title.lower().strip()}||{artist.lower().strip()}"
        self.keep_history[key] = True

    def was_kept(self, title: str, artist: str) -> bool:
        key = f"{title.lower().strip()}||{artist.lower().strip()}"
        return self.keep_history.get(key, False)

    # -------------------------------------------------------------------
    # Serialisation helpers (Phase 9 / Phase 11)
    # -------------------------------------------------------------------

    @classmethod
    def from_dict(cls, data: dict) -> "PlaylistSession":
        """Reconstruct a PlaylistSession from a persisted snapshot dict."""
        import waveform.domain.event as _event_module  # local import to avoid cycles

        session_id = data.get("session_id") or data.get("id") or str(uuid.uuid4())
        event_name = data.get("event_name", "")

        # Best-effort template lookup
        template_id = data.get("template_id") or data.get("event_type", "")
        event_template = None
        if template_id:
            event_template = _event_module.get_template(template_id)
        if event_template is None and event_name:
            # Scan by name (case-insensitive)
            for tpl in _event_module.BUILTIN_TEMPLATES:
                if tpl.name.lower() == event_name.lower():
                    event_template = tpl
                    break

        # Reconstruct blocks
        blocks: List[Block] = []
        missing_fields: List[str] = []

        for b_data in data.get("blocks", []):
            try:
                arch_str = b_data.get("archetype", "arrival")
                try:
                    arch: Any = BlockArchetype(arch_str)
                except ValueError:
                    arch = arch_str  # custom archetype id

                # Restore genre weights
                gw_list: List[GenreWeight] = []
                for gw_data in b_data.get("genre_weights", []):
                    try:
                        gw_list.append(
                            GenreWeight(
                                tag=gw_data["tag"],
                                weight=float(gw_data["weight"]),
                            )
                        )
                    except Exception:
                        pass

                block = Block(
                    id=b_data.get("id", str(uuid.uuid4())),
                    name=b_data.get("name", "Block"),
                    archetype=arch,
                    duration_minutes=int(b_data.get("duration_minutes", 60)),
                    energy_level=int(b_data.get("energy_level", 3)),
                    genre_weights=gw_list,
                )
                blocks.append(block)
            except Exception:
                pass  # skip malformed entries

        # Restore keep history
        keep_history = dict(data.get("keep_history", {}))

        # Restore veto entries if present
        veto_context = VetoContext()
        veto_entries = data.get("veto_entries", [])
        if veto_entries:
            for ve in veto_entries:
                try:
                    veto_context.add_veto(
                        block_id=ve.get("block_id", ""),
                        title=ve.get("title", ""),
                        artist=ve.get("artist", ""),
                        reason_tag=ve.get("reason_tag"),
                    )
                except Exception:
                    pass
        elif data.get("veto_count", 0) > 0:
            missing_fields.append("veto_entries")

        keep_entries = data.get("keep_entries", [])
        if keep_entries:
            for ke in keep_entries:
                try:
                    veto_context.add_keep(
                        block_id=ke.get("block_id", ""),
                        title=ke.get("title", ""),
                        artist=ke.get("artist", ""),
                    )
                except Exception:
                    pass
        elif keep_history and not keep_entries:
            missing_fields.append("keep_entries")

        playlist_urls = data.get("playlist_urls", [])
        if isinstance(playlist_urls, str):
            playlist_urls = [playlist_urls] if playlist_urls else []

        instance = cls(
            session_id=session_id,
            event_name=event_name,
            event_template=event_template,
            blocks=blocks,
            vibe_override=data.get("vibe_override", ""),
            keep_history=keep_history,
            veto_context=veto_context,
            playlist_urls=playlist_urls,
        )
        instance._resume_missing_fields = missing_fields
        return instance

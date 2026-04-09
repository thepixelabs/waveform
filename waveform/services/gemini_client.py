"""
gemini_client.py — Gemini AI generation client.

GeminiClient: real Google GenAI wrapper; generate_songs() is an Iterator.
FakeGeminiClient: deterministic test double.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterator, List, Optional

from waveform.domain.genre import GenreWeight
from waveform.domain.session import VetoContext

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_MASTER_PROMPT_PATH = _PROMPTS_DIR / "master_prompt.md"
_VETO_ADDENDUM_PATH = _PROMPTS_DIR / "veto_addendum.md"

VETO_REASON_TAG_INSTRUCTIONS = {
    "too slow": "Avoid songs with BPM below the block's expected energy range.",
    "wrong genre": "Stay strictly within the requested genre tags for this block.",
    "overplayed": "Avoid chart hits from the past 5 years; prefer deeper cuts.",
    "not the vibe": "Recalibrate toward the block's archetype description more precisely.",
    "artist already used": "Do not suggest this artist again in this session.",
}


def _load_master_prompt(override_path: Optional[str] = None) -> str:
    if override_path:
        try:
            return Path(override_path).read_text(encoding="utf-8")
        except Exception:
            pass
    try:
        return _MASTER_PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        return ""


def _weight_to_adverb(weight: float) -> str:
    if weight >= 0.6:
        return "heavily"
    if weight >= 0.4:
        return "strongly"
    if weight >= 0.25:
        return "moderately"
    return "lightly"


def _build_genre_instruction(
    genre_weights: List[GenreWeight],
    archetype_name: str = "",
) -> str:
    if not genre_weights:
        return ""
    sorted_weights = sorted(genre_weights, key=lambda gw: gw.weight, reverse=True)
    # Enforce max 6
    sorted_weights = sorted_weights[:6]
    parts = []
    for gw in sorted_weights:
        adverb = _weight_to_adverb(gw.weight)
        pct = int(gw.weight * 100)
        parts.append(f"lean {adverb} into {gw.tag} (~{pct}%)")

    genre_clause = ", ".join(parts)
    archetype_clause = f"For this {archetype_name} block, " if archetype_name else ""
    fill = "Fill the rest with what fits the vibe."
    return f"{archetype_clause}{genre_clause}. {fill}"


class GeminiClient:
    """Wraps google-genai for song generation with streaming."""

    def __init__(
        self,
        api_key: str = "",
        model: str = "gemini-2.5-flash",
        master_prompt_path: Optional[str] = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._master_prompt_path = master_prompt_path
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            from google import genai  # type: ignore

            self._client = genai.Client(api_key=self._api_key)
        return self._client

    def _build_prompt(
        self,
        block: Any,
        session: Any,
        veto_context: VetoContext,
        n_songs: int = 10,
    ) -> str:
        master = _load_master_prompt(self._master_prompt_path)
        parts = [master] if master else []

        archetype_name = str(block.archetype).replace("_", " ").title()
        parts.append(f"\n## Block: {block.name} ({archetype_name})")
        parts.append(f"Duration: {block.duration_minutes} minutes")
        parts.append(f"Energy level: {block.energy_level}/5")

        # Vibe override
        vibe = getattr(session, "vibe_override", "")
        if vibe:
            parts.append(f"Event vibe: {vibe}")

        # Genre weights
        genre_instr = _build_genre_instruction(
            block.genre_weights,
            archetype_name=archetype_name,
        )
        if genre_instr:
            parts.append(f"Genre guidance: {genre_instr}")

        # Veto context
        veto_text = veto_context.format_for_prompt()
        if veto_text:
            parts.append(f"\n{veto_text}")

        # Keep history (positive signals)
        keep_keys = list(getattr(session, "keep_history", {}).keys())
        if keep_keys:
            # Reconstruct titles from keys (title||artist format)
            likes = []
            for k in keep_keys[:5]:  # cap at 5 examples
                parts_k = k.split("||")
                if len(parts_k) == 2:
                    likes.append(f'"{parts_k[0].title()}" by {parts_k[1].title()}')
            if likes:
                parts.append("Songs this user has loved (for calibration):")
                parts.extend(f"- {s}" for s in likes)

        parts.append(
            f"\nReturn exactly {n_songs} song suggestions as a numbered list. "
            "Format each as: Title — Artist\n"
            "Do not include extra commentary. Do not number with dots, use hyphens. "
            "One song per line."
        )
        return "\n".join(parts)

    def generate_songs(
        self,
        block: Any,
        session: Any,
        veto_context: Optional[VetoContext] = None,
        n_songs: int = 10,
    ) -> Iterator[Any]:
        """Stream song suggestions from Gemini. Yields SongSuggestion objects."""
        from waveform.services.spotify_client import SongSuggestion

        if veto_context is None:
            veto_context = getattr(session, "veto_context", VetoContext())

        prompt = self._build_prompt(block, session, veto_context, n_songs)
        client = self._get_client()

        try:
            response = client.models.generate_content(
                model=self._model,
                contents=prompt,
            )
            text = response.text or ""
        except Exception as exc:
            raise RuntimeError(f"Gemini generation failed: {exc}") from exc

        for song in _parse_song_list(text):
            yield song

    def generate_single_replacement(
        self,
        block: Any,
        session: Any,
        veto_context: Optional[VetoContext] = None,
        exclude_titles: Optional[List[str]] = None,
    ) -> Optional[Any]:
        """Generate a single replacement song (for Swap flow)."""
        from waveform.services.spotify_client import SongSuggestion

        if veto_context is None:
            veto_context = getattr(session, "veto_context", VetoContext())

        exclude_text = ""
        if exclude_titles:
            exclude_text = "Exclude: " + ", ".join(f'"{t}"' for t in exclude_titles[:10]) + "\n"

        prompt = self._build_prompt(block, session, veto_context, n_songs=1)
        prompt += f"\n{exclude_text}Return exactly 1 song."

        client = self._get_client()
        try:
            response = client.models.generate_content(
                model=self._model,
                contents=prompt,
            )
            text = response.text or ""
        except Exception as exc:
            raise RuntimeError(f"Gemini replacement failed: {exc}") from exc

        songs = _parse_song_list(text)
        return songs[0] if songs else None


def _parse_song_list(text: str) -> List[Any]:
    """Parse 'Title — Artist' lines from Gemini output."""
    from waveform.services.spotify_client import SongSuggestion

    songs = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        # Strip leading list markers: "1.", "1)", "-", "•", etc.
        line = re.sub(r"^[\d]+[.)]\s*", "", line)
        line = re.sub(r"^[-•*]\s*", "", line)

        # Try "Title — Artist" or "Title - Artist"
        for sep in [" — ", " – ", " - "]:
            if sep in line:
                parts = line.split(sep, 1)
                title = parts[0].strip().strip('"')
                artist = parts[1].strip().strip('"')
                if title and artist:
                    songs.append(SongSuggestion(title=title, artist=artist))
                break
    return songs


# ---------------------------------------------------------------------------
# Fake for tests
# ---------------------------------------------------------------------------

class FakeGeminiClient:
    """Returns deterministic songs without hitting the network."""

    def __init__(self, songs_per_call: int = 5) -> None:
        self._songs_per_call = songs_per_call
        self.generate_calls: List[dict] = []

    def generate_songs(
        self,
        block: Any,
        session: Any,
        veto_context: Optional[VetoContext] = None,
        n_songs: int = 10,
    ) -> Iterator[Any]:
        from waveform.services.spotify_client import SongSuggestion

        self.generate_calls.append({"block_id": block.id, "n_songs": n_songs})
        count = min(n_songs, self._songs_per_call)
        for i in range(count):
            yield SongSuggestion(
                title=f"Fake Song {block.name} #{i + 1}",
                artist=f"Artist {i + 1}",
                reasoning=f"Great fit for {block.name}",
            )

    def generate_single_replacement(
        self,
        block: Any,
        session: Any,
        veto_context: Optional[VetoContext] = None,
        exclude_titles: Optional[List[str]] = None,
    ) -> Optional[Any]:
        from waveform.services.spotify_client import SongSuggestion

        return SongSuggestion(
            title=f"Replacement for {block.name}",
            artist="Replacement Artist",
        )

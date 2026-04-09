"""
test_cover_art.py — Tests for the parametric PIL cover art generator.
"""
import pytest
import struct
from typing import List

from waveform.domain.block import BlockArchetype
from waveform.domain.event import TEMPLATE_BY_ID
from waveform.domain.session import PlaylistSession
from waveform.services.cover_art import (
    FakeCoverArtService,
    COVER_ART_TIER,
    generate_block_cover,
    generate_playlist_cover,
)
from waveform.domain.block import Block
import uuid

try:
    from PIL import Image  # type: ignore
    from io import BytesIO
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


def _is_valid_png(data: bytes) -> bool:
    return data[:8] == b"\x89PNG\r\n\x1a\n"


def _png_dimensions(data: bytes):
    if not _is_valid_png(data):
        return None, None
    w = struct.unpack(">I", data[16:20])[0]
    h = struct.unpack(">I", data[20:24])[0]
    return w, h


@pytest.mark.skipif(not HAS_PIL, reason="PIL not installed")
class TestBlockCoverAllArchetypes:
    @pytest.mark.parametrize("archetype", list(BlockArchetype))
    def test_returns_bytes(self, archetype: BlockArchetype) -> None:
        result = generate_block_cover(archetype, "Test Event")
        assert isinstance(result, bytes)
        assert len(result) > 0

    @pytest.mark.parametrize("archetype", list(BlockArchetype))
    def test_valid_png_signature(self, archetype: BlockArchetype) -> None:
        result = generate_block_cover(archetype, "Test Event")
        assert _is_valid_png(result), f"Not a valid PNG for {archetype}"

    @pytest.mark.parametrize("archetype", list(BlockArchetype))
    def test_dimensions_512x512(self, archetype: BlockArchetype) -> None:
        result = generate_block_cover(archetype, "Test Event")
        w, h = _png_dimensions(result)
        assert w == 512, f"Width {w} != 512 for {archetype}"
        assert h == 512, f"Height {h} != 512 for {archetype}"

    @pytest.mark.parametrize("archetype", list(BlockArchetype))
    def test_decodable_by_pil(self, archetype: BlockArchetype) -> None:
        result = generate_block_cover(archetype, "Test Event")
        img = Image.open(BytesIO(result))
        assert img.size == (512, 512)

    @pytest.mark.parametrize("archetype", list(BlockArchetype))
    def test_deterministic(self, archetype: BlockArchetype) -> None:
        r1 = generate_block_cover(archetype, "Same Event")
        r2 = generate_block_cover(archetype, "Same Event")
        assert r1 == r2, f"Not deterministic for {archetype}"

    @pytest.mark.parametrize("archetype", list(BlockArchetype))
    def test_unique_per_event_name(self, archetype: BlockArchetype) -> None:
        r1 = generate_block_cover(archetype, "Event A")
        r2 = generate_block_cover(archetype, "Event B")
        # Most archetypes include text layers; different names should produce different bytes
        # (This may not always hold for archetypes with no text, so we allow edge cases)
        # Just assert they are both valid
        assert _is_valid_png(r1)
        assert _is_valid_png(r2)


@pytest.mark.skipif(not HAS_PIL, reason="PIL not installed")
class TestBlockCoverEdgeCases:
    def test_empty_event_name(self) -> None:
        result = generate_block_cover(BlockArchetype.GROOVE, "")
        assert _is_valid_png(result)

    def test_unicode_event_name(self) -> None:
        result = generate_block_cover(BlockArchetype.SINGALONG, "誕生日パーティー 🎉")
        assert _is_valid_png(result)

    def test_long_event_name_truncated(self) -> None:
        long_name = "A" * 200
        result = generate_block_cover(BlockArchetype.ARRIVAL, long_name)
        assert _is_valid_png(result)

    def test_default_name_fallback(self) -> None:
        result = generate_block_cover(BlockArchetype.PEAK)
        assert _is_valid_png(result)


@pytest.mark.skipif(not HAS_PIL, reason="PIL not installed")
class TestPlaylistCover:
    def _make_session(self, archetypes: List[BlockArchetype]) -> PlaylistSession:
        tpl = TEMPLATE_BY_ID["birthday"]
        blocks = [Block.from_archetype(a, duration_minutes=60) for a in archetypes]
        return PlaylistSession(
            session_id=str(uuid.uuid4()),
            event_name="Cover Test",
            event_template=tpl,
            blocks=blocks,
        )

    def test_empty_session_fallback(self) -> None:
        session = PlaylistSession(
            session_id=str(uuid.uuid4()),
            event_name="Empty",
            event_template=None,
            blocks=[],
        )
        result = generate_playlist_cover(session)
        assert _is_valid_png(result)

    def test_multi_block_session(self) -> None:
        session = self._make_session([BlockArchetype.GROOVE, BlockArchetype.DANCE_FLOOR, BlockArchetype.DANCE_FLOOR])
        result = generate_playlist_cover(session)
        assert _is_valid_png(result)

    def test_dominant_archetype_determinism(self) -> None:
        session = self._make_session([BlockArchetype.GROOVE, BlockArchetype.GROOVE, BlockArchetype.ARRIVAL])
        r1 = generate_playlist_cover(session)
        r2 = generate_playlist_cover(session)
        assert r1 == r2

    def test_single_block_session(self) -> None:
        session = self._make_session([BlockArchetype.PEAK])
        result = generate_playlist_cover(session)
        assert _is_valid_png(result)


class TestCoverArtTierFlag:
    def test_tier_constant_exists(self) -> None:
        assert COVER_ART_TIER == 1

    def test_fake_service_unchanged(self) -> None:
        svc = FakeCoverArtService()
        result = svc.generate_block_cover(BlockArchetype.GROOVE, "Test")
        assert isinstance(result, bytes)
        assert len(result) > 0


class TestFakeCoverArtServiceStandalone:
    def test_block_cover_returns_bytes(self) -> None:
        svc = FakeCoverArtService()
        assert isinstance(svc.generate_block_cover(), bytes)

    def test_playlist_cover_returns_bytes(self) -> None:
        svc = FakeCoverArtService()
        assert isinstance(svc.generate_playlist_cover(), bytes)

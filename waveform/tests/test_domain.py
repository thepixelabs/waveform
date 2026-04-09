"""
test_domain.py — Unit tests for the pure domain layer.

Covers GenreWeight, GenreTagIndex, BlockArchetype, Block, EventTemplate,
VetoContext, and PlaylistSession.
"""
import pytest

from waveform.domain.genre import DEFAULT_INDEX, GenreTagIndex, GenreWeight
from waveform.domain.block import (
    ARCHETYPE_SPECS,
    BlockArchetype,
    Block,
    get_spec,
    get_spec_for_id,
)
from waveform.domain.event import BUILTIN_TEMPLATES, TEMPLATE_BY_ID, EventTemplate, get_template
from waveform.domain.session import (
    PlaylistSession,
    VetoContext,
    VETO_REASON_TAGS,
)
import uuid


class TestGenreWeight:
    def test_valid_weight(self) -> None:
        gw = GenreWeight("house", 0.6)
        assert gw.tag == "house"
        assert gw.weight == 0.6

    def test_zero_weight_valid(self) -> None:
        gw = GenreWeight("techno", 0.0)
        assert gw.weight == 0.0

    def test_max_weight_valid(self) -> None:
        gw = GenreWeight("dnb", 0.8)
        assert gw.weight == 0.8

    def test_above_max_raises(self) -> None:
        with pytest.raises(ValueError):
            GenreWeight("dnb", 0.81)

    def test_empty_tag_raises(self) -> None:
        with pytest.raises(ValueError):
            GenreWeight("", 0.5)

    def test_whitespace_tag_raises(self) -> None:
        with pytest.raises(ValueError):
            GenreWeight("   ", 0.5)

    def test_normalised_tag(self) -> None:
        gw = GenreWeight("  House  ", 0.4)
        assert gw.normalised_tag() == "house"

    def test_frozen(self) -> None:
        gw = GenreWeight("pop", 0.3)
        with pytest.raises(Exception):
            gw.weight = 0.5  # type: ignore


class TestGenreTagIndex:
    def test_search_prefix(self) -> None:
        results = DEFAULT_INDEX.search("house")
        assert "house" in results
        # Prefix results come before infix
        assert results.index("house") < results.index("tech-house")

    def test_search_infix(self) -> None:
        results = DEFAULT_INDEX.search("house")
        assert "tech-house" in results

    def test_empty_query_returns_first_n(self) -> None:
        results = DEFAULT_INDEX.search("", limit=5)
        assert len(results) <= 5

    def test_case_insensitive(self) -> None:
        results_lower = DEFAULT_INDEX.search("house")
        results_upper = DEFAULT_INDEX.search("HOUSE")
        assert set(results_lower) == set(results_upper)

    def test_psytrance_in_index(self) -> None:
        results = DEFAULT_INDEX.search("psytrance")
        assert "psytrance" in results

    def test_add_custom_tag(self) -> None:
        idx = GenreTagIndex()
        idx.add("hyper-minimal")
        results = idx.search("hyper")
        assert "hyper-minimal" in results

    def test_add_duplicate_no_op(self) -> None:
        idx = GenreTagIndex()
        before = len(idx)
        idx.add("house")
        after = len(idx)
        assert before == after

    def test_limit_respected(self) -> None:
        results = DEFAULT_INDEX.search("", limit=3)
        assert len(results) <= 3


class TestBlockArchetype:
    def test_all_archetypes_have_specs(self) -> None:
        for arch in BlockArchetype:
            spec = get_spec(arch)
            assert spec.archetype == arch

    def test_palette_is_3_tuple(self) -> None:
        for arch in BlockArchetype:
            spec = get_spec(arch)
            assert len(spec.cover_palette) == 3

    def test_energy_in_range(self) -> None:
        for arch in BlockArchetype:
            spec = get_spec(arch)
            assert 1 <= spec.default_energy <= 5

    def test_get_spec_for_id_builtin(self) -> None:
        spec = get_spec_for_id("arrival")
        assert spec.display_name == "Arrival"

    def test_get_spec_for_id_unknown_raises(self) -> None:
        with pytest.raises(KeyError):
            get_spec_for_id("nonexistent_archetype_xyz")


class TestBlock:
    def test_from_archetype(self) -> None:
        block = Block.from_archetype(BlockArchetype.GROOVE)
        assert block.archetype == BlockArchetype.GROOVE
        assert block.energy_level == 4
        assert block.duration_minutes == 60
        assert block.id

    def test_too_short_raises(self) -> None:
        with pytest.raises(ValueError):
            Block(id=str(uuid.uuid4()), name="x", archetype=BlockArchetype.CHILL, duration_minutes=4, energy_level=2)

    def test_invalid_energy_raises(self) -> None:
        with pytest.raises(ValueError):
            Block(id=str(uuid.uuid4()), name="x", archetype=BlockArchetype.CHILL, duration_minutes=30, energy_level=6)

    def test_track_count(self) -> None:
        block = Block.from_archetype(BlockArchetype.DANCE_FLOOR, duration_minutes=60)
        assert block.track_count == 20  # 60 // 3

    def test_genre_weights_default_empty(self) -> None:
        block = Block.from_archetype(BlockArchetype.ARRIVAL)
        assert block.genre_weights == []

    def test_genre_weights_passed_through(self) -> None:
        gws = [GenreWeight("house", 0.5)]
        block = Block.from_archetype(BlockArchetype.GROOVE, genre_weights=gws)
        assert block.genre_weights == gws


class TestEventTemplate:
    def test_ten_builtin_templates(self) -> None:
        assert len(BUILTIN_TEMPLATES) == 10

    def test_all_have_id_and_name(self) -> None:
        for tpl in BUILTIN_TEMPLATES:
            assert tpl.id
            assert tpl.name

    def test_template_by_id_lookup(self) -> None:
        tpl = TEMPLATE_BY_ID["birthday"]
        assert tpl.name == "Birthday"

    def test_get_template_returns_none_for_missing(self) -> None:
        assert get_template("nonexistent") is None

    def test_birthday_blocks(self) -> None:
        tpl = TEMPLATE_BY_ID["birthday"]
        assert BlockArchetype.ARRIVAL in tpl.default_blocks
        assert BlockArchetype.DANCE_FLOOR in tpl.default_blocks

    def test_accent_colors_are_hex(self) -> None:
        for tpl in BUILTIN_TEMPLATES:
            assert tpl.accent_color.startswith("#")
            assert len(tpl.accent_color) == 7


class TestVetoContext:
    def test_add_veto_and_is_vetoed(self) -> None:
        vc = VetoContext()
        vc.add_veto("b1", "Bohemian Rhapsody", "Queen")
        assert vc.is_vetoed("Bohemian Rhapsody", "Queen")

    def test_is_vetoed_case_insensitive(self) -> None:
        vc = VetoContext()
        vc.add_veto("b1", "Test Song", "Test Artist")
        assert vc.is_vetoed("test song", "test artist")

    def test_add_keep(self) -> None:
        vc = VetoContext()
        vc.add_keep("b1", "Blue", "A-Ha")
        assert len(vc.keeps) == 1

    def test_veto_count(self) -> None:
        vc = VetoContext()
        vc.add_veto("b1", "Song 1", "Artist 1")
        vc.add_veto("b1", "Song 2", "Artist 2")
        assert vc.veto_count == 2

    def test_vetoes_for_block(self) -> None:
        vc = VetoContext()
        vc.add_veto("b1", "Song 1", "Artist 1")
        vc.add_veto("b2", "Song 2", "Artist 2")
        assert len(vc.vetoes_for_block("b1")) == 1

    def test_format_for_prompt_empty(self) -> None:
        vc = VetoContext()
        assert vc.format_for_prompt() == ""

    def test_format_for_prompt_with_vetoes(self) -> None:
        vc = VetoContext()
        vc.add_veto("b1", "Song 1", "Artist 1", reason_tag="too slow")
        prompt = vc.format_for_prompt()
        assert "Song 1" in prompt
        assert "too slow" in prompt
        assert "AVOID" in prompt

    def test_format_for_prompt_with_keeps(self) -> None:
        vc = VetoContext()
        vc.add_keep("b1", "Good Song", "Good Artist")
        prompt = vc.format_for_prompt()
        assert "Good Song" in prompt
        assert "LIKED" in prompt

    def test_veto_reason_tags_exist(self) -> None:
        assert len(VETO_REASON_TAGS) == 5
        assert "too slow" in VETO_REASON_TAGS


class TestPlaylistSession:
    def _make_session(self) -> PlaylistSession:
        tpl = TEMPLATE_BY_ID["birthday"]
        blocks = [Block.from_archetype(arch, duration_minutes=60) for arch in tpl.default_blocks[:2]]
        return PlaylistSession(
            session_id=str(uuid.uuid4()),
            event_name="Test Party",
            event_template=tpl,
            blocks=blocks,
        )

    def test_add_block(self) -> None:
        s = self._make_session()
        new_block = Block.from_archetype(BlockArchetype.PEAK)
        count_before = len(s.blocks)
        s.add_block(new_block)
        assert len(s.blocks) == count_before + 1

    def test_remove_block(self) -> None:
        s = self._make_session()
        block_id = s.blocks[0].id
        s.remove_block(block_id)
        assert all(b.id != block_id for b in s.blocks)

    def test_reorder_blocks(self) -> None:
        s = self._make_session()
        first_id = s.blocks[0].id
        s.reorder_blocks(0, 1)
        assert s.blocks[1].id == first_id

    def test_mark_kept(self) -> None:
        s = self._make_session()
        s.mark_kept("Blue", "A-Ha")
        assert s.was_kept("Blue", "A-Ha")
        assert not s.was_kept("Red", "X")

    def test_was_kept_case_insensitive(self) -> None:
        s = self._make_session()
        s.mark_kept("Blue", "A-Ha")
        assert s.was_kept("blue", "a-ha")

    def test_from_dict_round_trip(self) -> None:
        s = self._make_session()
        data = {
            "session_id": s.session_id,
            "event_name": s.event_name,
            "template_id": "birthday",
            "vibe_override": "very fun",
            "blocks": [
                {
                    "id": b.id,
                    "name": b.name,
                    "archetype": b.archetype.value,
                    "duration_minutes": b.duration_minutes,
                    "energy_level": b.energy_level,
                    "genre_weights": [],
                }
                for b in s.blocks
            ],
            "keep_history": {},
            "veto_count": 0,
            "veto_entries": [],
            "keep_entries": [],
        }
        restored = PlaylistSession.from_dict(data)
        assert restored.session_id == s.session_id
        assert restored.event_name == s.event_name
        assert len(restored.blocks) == len(s.blocks)
        assert restored.vibe_override == "very fun"
        assert restored.event_template is not None

    def test_from_dict_with_veto_entries(self) -> None:
        data = {
            "session_id": str(uuid.uuid4()),
            "event_name": "Test",
            "template_id": "birthday",
            "vibe_override": "",
            "blocks": [],
            "keep_history": {},
            "veto_count": 1,
            "veto_entries": [{"block_id": "b1", "title": "Song", "artist": "Artist", "reason_tag": "too slow"}],
            "keep_entries": [],
        }
        session = PlaylistSession.from_dict(data)
        assert session.veto_context.veto_count == 1
        assert session.veto_context.is_vetoed("Song", "Artist")

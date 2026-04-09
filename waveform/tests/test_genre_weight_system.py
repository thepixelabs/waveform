"""
test_genre_weight_system.py — Tests for the genre weight system.
"""
import pytest
import dataclasses
from typing import List

from waveform.domain.genre import DEFAULT_INDEX, GenreTagIndex, GenreWeight
from waveform.domain.block import Block, BlockArchetype
from waveform.domain.event import TEMPLATE_BY_ID
from waveform.domain.session import PlaylistSession
from waveform.services.gemini_client import _build_genre_instruction
from waveform.ui.widgets.genre_weight_panel import wire_genre_panel_to_store
from waveform.app.state import StateStore, AppState
import uuid


class TestMigrationToGenreWeight:
    def test_psytrance_migration_produces_valid_genre_weights(self) -> None:
        from waveform.services.persistence import migrate_v1_settings
        v1 = {"psytrance_enabled": True, "psytrance_pct": 60, "psytrance_count": 5}
        v2 = migrate_v1_settings(v1)
        overrides = v2.get("block_genre_overrides", {})
        for block_key, gw_list in overrides.items():
            for gw_data in gw_list:
                # Must be constructable as GenreWeight
                gw = GenreWeight(tag=gw_data["tag"], weight=float(gw_data["weight"]))
                assert gw.weight > 0

    def test_psytrance_disabled_no_overrides(self) -> None:
        from waveform.services.persistence import migrate_v1_settings
        v1 = {"psytrance_enabled": False, "psytrance_pct": 50}
        v2 = migrate_v1_settings(v1)
        assert not v2.get("block_genre_overrides", {})

    def test_100pct_psytrance_capped_at_80(self) -> None:
        from waveform.services.persistence import migrate_v1_settings
        v1 = {"psytrance_enabled": True, "psytrance_pct": 100}
        v2 = migrate_v1_settings(v1)
        for block_gws in v2.get("block_genre_overrides", {}).values():
            for gw in block_gws:
                assert gw["weight"] <= 0.8


class TestGenreTagIndex:
    def test_autocomplete_prefix_first(self) -> None:
        idx = GenreTagIndex()
        results = idx.search("house")
        prefix_results = [r for r in results if r.startswith("house")]
        infix_results = [r for r in results if not r.startswith("house") and "house" in r]
        if prefix_results and infix_results:
            assert results.index(prefix_results[0]) < results.index(infix_results[0])

    def test_infix_search(self) -> None:
        idx = GenreTagIndex()
        results = idx.search("house")
        assert any("house" in r for r in results)

    def test_empty_query_returns_items(self) -> None:
        idx = GenreTagIndex()
        results = idx.search("", limit=10)
        assert len(results) > 0

    def test_case_insensitivity(self) -> None:
        idx = GenreTagIndex()
        lower = set(idx.search("TECH"))
        upper = set(idx.search("tech"))
        assert lower == upper

    def test_psytrance_still_present(self) -> None:
        idx = GenreTagIndex()
        results = idx.search("psytrance")
        assert "psytrance" in results

    def test_custom_tag_add(self) -> None:
        idx = GenreTagIndex()
        idx.add("future-garage")
        assert "future-garage" in idx.search("future")

    def test_add_normalises_tag(self) -> None:
        idx = GenreTagIndex()
        idx.add("  Future Garage  ")
        results = idx.search("future garage")
        assert "future garage" in results


class TestBuildGenreInstruction:
    def test_empty_weights_returns_empty(self) -> None:
        result = _build_genre_instruction([])
        assert result == ""

    def test_single_weight_correct_adverb(self) -> None:
        gws = [GenreWeight("house", 0.7)]
        result = _build_genre_instruction(gws)
        assert "heavily" in result
        assert "house" in result

    def test_multiple_weights_descending_order(self) -> None:
        gws = [GenreWeight("house", 0.4), GenreWeight("techno", 0.7)]
        result = _build_genre_instruction(gws)
        # Techno (0.7) should appear before house (0.4) in the output
        assert result.index("techno") < result.index("house")

    def test_fill_the_rest_phrase(self) -> None:
        gws = [GenreWeight("house", 0.5)]
        result = _build_genre_instruction(gws)
        assert "Fill the rest" in result

    def test_max_6_enforcement(self) -> None:
        gws = [GenreWeight(f"genre{i}", 0.3) for i in range(10)]
        result = _build_genre_instruction(gws)
        # Only 6 should appear
        genre_mentions = sum(1 for i in range(10) if f"genre{i}" in result)
        assert genre_mentions <= 6

    def test_archetype_in_output(self) -> None:
        gws = [GenreWeight("house", 0.5)]
        result = _build_genre_instruction(gws, archetype_name="Groove")
        assert "Groove" in result

    def test_percentage_in_output(self) -> None:
        gws = [GenreWeight("house", 0.6)]
        result = _build_genre_instruction(gws)
        assert "60%" in result

    def test_adverb_mapping(self) -> None:
        cases = [
            (0.7, "heavily"),
            (0.5, "strongly"),
            (0.3, "moderately"),
            (0.1, "lightly"),
        ]
        for weight, expected_adverb in cases:
            gws = [GenreWeight("house", weight)]
            result = _build_genre_instruction(gws)
            assert expected_adverb in result, f"Expected '{expected_adverb}' for weight {weight}"


class TestWireGenrePanelToStore:
    def _make_session_with_blocks(self) -> tuple:
        tpl = TEMPLATE_BY_ID["birthday"]
        blocks = [Block.from_archetype(BlockArchetype.GROOVE, duration_minutes=60) for _ in range(2)]
        session = PlaylistSession(
            session_id=str(uuid.uuid4()),
            event_name="Test",
            event_template=tpl,
            blocks=blocks,
        )
        store = StateStore()
        store.set("session", session)
        return store, session

    def test_new_session_published(self) -> None:
        store, session = self._make_session_with_blocks()
        block_id = session.blocks[0].id
        new_weights = [GenreWeight("house", 0.5)]
        wire_genre_panel_to_store(store, block_id, new_weights)
        updated = store.get("session")
        assert updated is not session

    def test_original_not_mutated(self) -> None:
        store, session = self._make_session_with_blocks()
        original_weights = list(session.blocks[0].genre_weights)
        wire_genre_panel_to_store(store, session.blocks[0].id, [GenreWeight("house", 0.5)])
        assert session.blocks[0].genre_weights == original_weights

    def test_updated_block_has_new_weights(self) -> None:
        store, session = self._make_session_with_blocks()
        block_id = session.blocks[0].id
        new_weights = [GenreWeight("house", 0.6), GenreWeight("techno", 0.4)]
        wire_genre_panel_to_store(store, block_id, new_weights)
        updated = store.get("session")
        target = next(b for b in updated.blocks if b.id == block_id)
        assert len(target.genre_weights) == 2

    def test_other_blocks_unchanged(self) -> None:
        store, session = self._make_session_with_blocks()
        other_block_id = session.blocks[1].id
        wire_genre_panel_to_store(store, session.blocks[0].id, [GenreWeight("house", 0.5)])
        updated = store.get("session")
        other = next(b for b in updated.blocks if b.id == other_block_id)
        assert other.genre_weights == session.blocks[1].genre_weights

    def test_noop_on_missing_session(self) -> None:
        store = StateStore()  # No session
        wire_genre_panel_to_store(store, "some_block_id", [GenreWeight("house", 0.5)])
        assert store.get("session") is None


class TestGenreWeightValidation:
    def test_zero_weight_valid(self) -> None:
        gw = GenreWeight("house", 0.0)
        assert gw.weight == 0.0

    def test_max_weight_valid(self) -> None:
        gw = GenreWeight("house", 0.8)
        assert gw.weight == 0.8

    def test_above_max_raises(self) -> None:
        with pytest.raises(ValueError):
            GenreWeight("house", 0.9)

    def test_empty_tag_raises(self) -> None:
        with pytest.raises(ValueError):
            GenreWeight("", 0.5)

    def test_normalisation(self) -> None:
        gw = GenreWeight("  House  ", 0.4)
        assert gw.normalised_tag() == "house"

"""
test_custom_archetypes.py — Phase 2B: custom archetype round-trip and registry.
"""
import pytest
import uuid
from waveform.domain.block import (
    BlockArchetype,
    CustomArchetype,
    ARCHETYPE_SPECS,
    get_spec_for_id,
    is_custom_archetype_id,
    list_custom_archetypes,
    register_custom_archetypes,
    get_custom_archetype,
)
from waveform.services.persistence import FakePersistenceService


def _make_custom(suffix: str = "") -> CustomArchetype:
    return CustomArchetype(
        id=f"custom_{uuid.uuid4().hex[:8]}",
        name=f"Test Archetype {suffix}",
        emoji="🎵",
        description="A test archetype",
        palette_start="#1A0533",
        palette_end="#6B2FFA",
        energy=3,
    )


class TestCustomArchetypeRoundTrip:
    def test_to_dict_from_dict(self) -> None:
        ca = _make_custom("rt")
        d = ca.to_dict()
        restored = CustomArchetype.from_dict(d)
        assert restored.id == ca.id
        assert restored.name == ca.name
        assert restored.emoji == ca.emoji
        assert restored.energy == ca.energy

    def test_missing_field_tolerance(self) -> None:
        # from_dict should use defaults for missing fields
        ca = CustomArchetype.from_dict({"name": "Minimal"})
        assert ca.name == "Minimal"
        assert ca.emoji == "🎵"
        assert ca.energy == 3

    def test_cover_palette_format(self) -> None:
        ca = _make_custom()
        palette = ca.cover_palette
        assert len(palette) == 3
        for color in palette:
            assert color.startswith("#")
            assert len(color) in (4, 7)


class TestRegistryOperations:
    def setup_method(self) -> None:
        register_custom_archetypes([])

    def test_register_and_get(self) -> None:
        ca = _make_custom("reg")
        register_custom_archetypes([ca])
        assert get_custom_archetype(ca.id) is ca

    def test_list_custom_archetypes(self) -> None:
        ca1 = _make_custom("1")
        ca2 = _make_custom("2")
        register_custom_archetypes([ca1, ca2])
        result = list_custom_archetypes()
        assert len(result) == 2

    def test_is_custom_archetype_id_true(self) -> None:
        ca = _make_custom()
        register_custom_archetypes([ca])
        assert is_custom_archetype_id(ca.id)

    def test_is_custom_archetype_id_false_for_builtin(self) -> None:
        register_custom_archetypes([])
        assert not is_custom_archetype_id("groove")

    def test_get_unknown_returns_none(self) -> None:
        register_custom_archetypes([])
        assert get_custom_archetype("unknown_xyz") is None

    def test_register_clears_old(self) -> None:
        ca1 = _make_custom("old")
        register_custom_archetypes([ca1])
        ca2 = _make_custom("new")
        register_custom_archetypes([ca2])
        assert get_custom_archetype(ca1.id) is None
        assert get_custom_archetype(ca2.id) is ca2


class TestGetSpecForId:
    @pytest.mark.parametrize("arch", list(BlockArchetype))
    def test_builtin_archetypes(self, arch: BlockArchetype) -> None:
        spec = get_spec_for_id(arch.value)
        assert spec.display_name

    def test_custom_archetype(self) -> None:
        ca = _make_custom("spec")
        register_custom_archetypes([ca])
        spec = get_spec_for_id(ca.id)
        assert spec.display_name == ca.name

    def test_unknown_raises(self) -> None:
        register_custom_archetypes([])
        with pytest.raises(KeyError):
            get_spec_for_id("totally_unknown_xyz_abc")


class TestFakePersistenceServiceRoundTrip:
    def test_save_and_load_archetypes(self) -> None:
        svc = FakePersistenceService()
        ca = _make_custom("persist")
        svc.save_custom_archetypes([ca.to_dict()])
        loaded = svc.load_custom_archetypes()
        assert len(loaded) == 1
        restored = CustomArchetype.from_dict(loaded[0])
        assert restored.name == ca.name

    def test_empty_load(self) -> None:
        svc = FakePersistenceService()
        assert svc.load_custom_archetypes() == []

"""
tests/test_custom_archetypes.py — Tests for CustomArchetype data model (Phase 2B).

Covers:
- CustomArchetype round-trips through to_dict / from_dict
- register_custom_archetypes / get_custom_archetype / list_custom_archetypes
- get_spec_for_id works for both built-ins and customs
- is_custom_archetype_id distinguishes built-ins from custom ids
- PersistenceService (FakePersistenceService) save/load round-trip
- cover_palette property returns three hex strings
"""

from __future__ import annotations

import uuid

import pytest

from waveform.domain.block import (
    BlockArchetype,
    CustomArchetype,
    get_custom_archetype,
    get_spec_for_id,
    is_custom_archetype_id,
    list_custom_archetypes,
    register_custom_archetypes,
)
from waveform.services.persistence import FakePersistenceService


# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clean_registry():
    """Reset the custom archetype registry before and after each test."""
    register_custom_archetypes([])
    yield
    register_custom_archetypes([])


def _make_ca(**overrides) -> CustomArchetype:
    defaults = dict(
        id=str(uuid.uuid4()),
        name="Sunset Chill",
        emoji="🌅",
        description="Golden hour vibes",
        color_start=(255, 180, 50),
        color_end=(100, 50, 200),
        energy_default=2,
    )
    defaults.update(overrides)
    return CustomArchetype(**defaults)


# ─────────────────────────────────────────────────────────────
# CustomArchetype data class
# ─────────────────────────────────────────────────────────────

def test_to_dict_round_trips():
    ca = _make_ca()
    d = ca.to_dict()
    ca2 = CustomArchetype.from_dict(d)
    assert ca2.id == ca.id
    assert ca2.name == ca.name
    assert ca2.emoji == ca.emoji
    assert ca2.description == ca.description
    assert ca2.color_start == ca.color_start
    assert ca2.color_end == ca.color_end
    assert ca2.energy_default == ca.energy_default


def test_from_dict_tolerates_missing_optional_fields():
    minimal = {"id": "abc123", "name": "Minimal", "energy_default": 3}
    ca = CustomArchetype.from_dict(minimal)
    assert ca.id == "abc123"
    assert ca.emoji == ""
    assert ca.description == ""
    assert ca.color_start == (100, 100, 100)
    assert ca.color_end == (50, 50, 50)


def test_cover_palette_returns_three_hex_strings():
    ca = _make_ca(color_start=(255, 0, 0), color_end=(0, 0, 255))
    palette = ca.cover_palette
    assert len(palette) == 3
    for hex_str in palette:
        assert hex_str.startswith("#"), f"{hex_str!r} does not start with #"
        assert len(hex_str) == 7, f"{hex_str!r} is not a 6-char hex color"


# ─────────────────────────────────────────────────────────────
# Registry operations
# ─────────────────────────────────────────────────────────────

def test_register_and_get():
    ca = _make_ca()
    register_custom_archetypes([ca])
    retrieved = get_custom_archetype(ca.id)
    assert retrieved is not None
    assert retrieved.name == ca.name


def test_get_unknown_returns_none():
    assert get_custom_archetype("not-a-real-id") is None


def test_list_returns_all_registered():
    cas = [_make_ca(id=str(i), name=f"Arch {i}") for i in range(3)]
    register_custom_archetypes(cas)
    result = list_custom_archetypes()
    assert len(result) == 3
    ids = {ca.id for ca in result}
    assert ids == {"0", "1", "2"}


def test_register_replaces_existing():
    ca1 = _make_ca(id="fixed-id", name="First")
    register_custom_archetypes([ca1])
    ca2 = _make_ca(id="fixed-id", name="Second")
    register_custom_archetypes([ca2])
    retrieved = get_custom_archetype("fixed-id")
    assert retrieved is not None
    assert retrieved.name == "Second"
    assert len(list_custom_archetypes()) == 1


def test_register_empty_clears_registry():
    register_custom_archetypes([_make_ca()])
    register_custom_archetypes([])
    assert list_custom_archetypes() == []


# ─────────────────────────────────────────────────────────────
# get_spec_for_id
# ─────────────────────────────────────────────────────────────

def test_get_spec_for_builtin():
    spec = get_spec_for_id("dance_floor")
    assert spec.display_name == "Dance Floor"
    assert spec.default_energy == 5


def test_get_spec_for_custom():
    ca = _make_ca(id="custom-001", name="My Vibe", energy_default=4)
    register_custom_archetypes([ca])
    spec = get_spec_for_id("custom-001")
    assert spec.name == "My Vibe"
    assert spec.energy_default == 4


def test_get_spec_for_unknown_raises():
    with pytest.raises(KeyError):
        get_spec_for_id("totally-unknown-xyz")


@pytest.mark.parametrize("arch", list(BlockArchetype))
def test_get_spec_for_all_builtins(arch):
    """All built-in archetypes must be resolvable via get_spec_for_id."""
    spec = get_spec_for_id(arch.value)
    assert spec is not None
    assert spec.display_name
    assert 1 <= spec.default_energy <= 5


# ─────────────────────────────────────────────────────────────
# is_custom_archetype_id
# ─────────────────────────────────────────────────────────────

def test_builtin_is_not_custom():
    for arch in BlockArchetype:
        assert not is_custom_archetype_id(arch.value), (
            f"{arch.value!r} should not be recognised as a custom archetype id"
        )


def test_registered_custom_is_custom():
    ca = _make_ca()
    register_custom_archetypes([ca])
    assert is_custom_archetype_id(ca.id)


def test_unregistered_id_is_not_custom():
    assert not is_custom_archetype_id("not-in-registry-at-all")


# ─────────────────────────────────────────────────────────────
# Persistence round-trip (FakePersistenceService)
# ─────────────────────────────────────────────────────────────

def test_fake_persistence_save_load_round_trip():
    ps = FakePersistenceService()
    ca = _make_ca()
    ps.save_custom_archetypes([ca.to_dict()])
    loaded = ps.load_custom_archetypes()
    assert len(loaded) == 1
    ca2 = CustomArchetype.from_dict(loaded[0])
    assert ca2.id == ca.id
    assert ca2.name == ca.name


def test_fake_persistence_load_empty_by_default():
    ps = FakePersistenceService()
    assert ps.load_custom_archetypes() == []


def test_fake_persistence_save_overwrites():
    ps = FakePersistenceService()
    ca1 = _make_ca(name="First")
    ca2 = _make_ca(name="Second")
    ps.save_custom_archetypes([ca1.to_dict()])
    ps.save_custom_archetypes([ca2.to_dict()])
    loaded = ps.load_custom_archetypes()
    assert len(loaded) == 1
    assert loaded[0]["name"] == "Second"

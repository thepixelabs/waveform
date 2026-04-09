"""
tests/test_genre_expansion.py — Tests for the expanded GenreTagIndex (Phase 2B).

Covers:
- No duplicate tags in DEFAULT_INDEX
- Total tag count is in the expanded range (~300)
- Prefix search works on newly added tags
- Infix search finds tags that don't start with the query
- spot-checks for representative tags from each new family
"""

from __future__ import annotations

import pytest

from waveform.domain.genre import DEFAULT_INDEX, GenreTagIndex, _GENRE_TAGS


# ─────────────────────────────────────────────────────────────
# Basic integrity
# ─────────────────────────────────────────────────────────────

def test_no_duplicate_tags():
    """Every tag in the source list must be unique."""
    assert len(_GENRE_TAGS) == len(set(_GENRE_TAGS)), (
        "Duplicate tags found in _GENRE_TAGS: "
        + str([t for t in _GENRE_TAGS if _GENRE_TAGS.count(t) > 1])
    )


def test_default_index_no_duplicates():
    """DEFAULT_INDEX must not expose duplicates through its all_tags property."""
    all_tags = DEFAULT_INDEX.all_tags
    assert len(all_tags) == len(set(all_tags))


def test_tag_count_expanded():
    """Index should have significantly more tags than the original ~90."""
    assert len(DEFAULT_INDEX.all_tags) >= 200, (
        f"Expected >= 200 tags after expansion, got {len(DEFAULT_INDEX.all_tags)}"
    )


def test_tags_are_sorted():
    """all_tags must be sorted alphabetically (GenreTagIndex contract)."""
    tags = DEFAULT_INDEX.all_tags
    assert tags == sorted(tags)


# ─────────────────────────────────────────────────────────────
# Spot-checks for new families
# ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("tag", [
    # Electronic / Dance
    "acid-house", "big-room", "breakbeat", "chicago-house", "chillstep",
    "dark-techno", "deep-dubstep", "detroit-techno", "disco",
    "drum-and-bass", "dub", "dutch-house", "footwork", "french-house",
    "happy-hardcore", "hard-trance", "hi-nrg", "mainstage",
    "melodic-house", "melodic-techno", "new-beat", "new-rave", "nu-disco",
    "organic-electronic", "progressive-trance", "psy-trance", "rave",
    "soul-house", "tech-house", "tropical-house", "uk-hard-house",
    # Hip-hop / R&B
    "afro-pop", "alternative-hip-hop", "boom-bap", "cloud-rap",
    "conscious-hip-hop", "east-coast-hip-hop", "gangsta-rap", "grime",
    "lo-fi-hip-hop", "memphis-hip-hop", "neo-soul", "new-jack-swing",
    "south-african-hip-hop", "trap-soul", "uk-hip-hop", "west-coast-hip-hop",
    # Rock / Alternative
    "alternative-rock", "art-rock", "dream-pop", "emo", "garage-rock",
    "heavy-metal", "math-rock", "new-wave", "noise-rock", "pop-punk",
    "post-punk", "progressive-rock", "psychedelic-rock", "shoegaze", "soft-rock",
    # World / Latin
    "afro-house", "afro-latin", "bachata", "baile-funk", "forro",
    "funk-brasileiro", "latin-pop", "merengue", "mpb", "pagode",
    "samba", "sertanejo",
    # Pop / Mainstream
    "baroque-pop", "bubblegum-pop", "chamber-pop", "j-pop", "teen-pop",
    # Jazz / Soul / Blues
    "blues-rock", "contemporary-jazz", "cool-jazz", "delta-blues",
    "easy-listening", "gospel", "jazz-fusion", "smooth-jazz", "vocal-jazz",
    # Classical / Ambient
    "ambient-pop", "cinematic", "dark-ambient", "drone", "modern-classical",
    "new-age", "soundtrack", "space-ambient",
])
def test_spot_check_new_tags_present(tag):
    assert DEFAULT_INDEX.contains(tag), f"Expected tag {tag!r} in DEFAULT_INDEX"


# ─────────────────────────────────────────────────────────────
# Search behaviour
# ─────────────────────────────────────────────────────────────

def test_prefix_search_returns_prefix_matches_first():
    """Tags that start with the query must come before infix matches."""
    results = DEFAULT_INDEX.search("deep")
    prefix_matches = [t for t in results if t.startswith("deep")]
    infix_matches = [t for t in results if not t.startswith("deep") and "deep" in t]
    # All prefix matches must appear before any infix match
    if prefix_matches and infix_matches:
        last_prefix_pos = max(results.index(t) for t in prefix_matches)
        first_infix_pos = min(results.index(t) for t in infix_matches)
        assert last_prefix_pos < first_infix_pos, (
            "Prefix matches should come before infix matches in search results"
        )


def test_infix_search_finds_tags():
    """Searching for a substring not at the start should still return results."""
    results = DEFAULT_INDEX.search("house")
    # Many tags contain 'house' not at position 0
    infix_hits = [t for t in results if "house" in t and not t.startswith("house")]
    assert len(infix_hits) > 0, "Expected infix 'house' matches (e.g. deep-house)"


def test_search_empty_query_returns_up_to_limit():
    results = DEFAULT_INDEX.search("", limit=10)
    assert len(results) <= 10


def test_search_no_results_for_nonsense():
    results = DEFAULT_INDEX.search("zzznomatch999")
    assert results == []


def test_search_limit_respected():
    results = DEFAULT_INDEX.search("a", limit=5)
    assert len(results) <= 5


def test_search_case_insensitive():
    lower = DEFAULT_INDEX.search("house")
    upper = DEFAULT_INDEX.search("HOUSE")
    assert lower == upper


# ─────────────────────────────────────────────────────────────
# GenreTagIndex.add — still works with expanded list
# ─────────────────────────────────────────────────────────────

def test_add_custom_tag():
    idx = GenreTagIndex()
    assert not idx.contains("my-custom-vibe")
    idx.add("my-custom-vibe")
    assert idx.contains("my-custom-vibe")


def test_add_duplicate_is_noop():
    idx = GenreTagIndex()
    before = len(idx.all_tags)
    idx.add("house")   # already present
    assert len(idx.all_tags) == before


def test_add_normalises_case_and_whitespace():
    idx = GenreTagIndex()
    idx.add("  My Genre  ")
    assert idx.contains("my genre")

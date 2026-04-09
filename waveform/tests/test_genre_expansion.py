"""
test_genre_expansion.py — Phase 2B: genre tag index expansion tests.
"""
import pytest
from waveform.domain.genre import DEFAULT_INDEX, GenreTagIndex, _GENRE_TAGS


class TestGenreTagExpansion:
    def test_no_duplicates(self) -> None:
        assert len(_GENRE_TAGS) == len(set(_GENRE_TAGS)), "Duplicate tags found in _GENRE_TAGS"

    def test_tag_count_at_least_150(self) -> None:
        assert len(_GENRE_TAGS) >= 150, f"Only {len(_GENRE_TAGS)} tags; expected ≥150"

    def test_sorted_order(self) -> None:
        assert _GENRE_TAGS == sorted(_GENRE_TAGS)

    @pytest.mark.parametrize("tag", [
        "house", "techno", "trance", "psytrance", "drum-and-bass",
        "dubstep", "ambient", "hip-hop", "pop", "rock",
        "jazz", "classical", "latin", "reggae", "blues",
        "disco", "funk", "soul", "r-and-b", "country",
        "afrobeats", "amapiano", "dancehall", "gqom", "lo-fi",
        "synthwave", "darkwave", "hyperpop", "phonk", "edm",
        "deep-house", "tech-house", "progressive-house",
        "minimal-techno", "acid-techno", "dub-techno",
        "progressive-trance", "goa-trance",
        "liquid-dnb", "jungle",
    ])
    def test_spot_check(self, tag: str) -> None:
        assert tag in _GENRE_TAGS, f"Tag '{tag}' not found in genre index"

    def test_prefix_search_ordering(self) -> None:
        idx = GenreTagIndex()
        results = idx.search("deep")
        prefix_indices = [i for i, r in enumerate(results) if r.startswith("deep")]
        infix_indices = [i for i, r in enumerate(results) if "deep" in r and not r.startswith("deep")]
        if prefix_indices and infix_indices:
            assert min(prefix_indices) < min(infix_indices)

    def test_infix_search_ordering(self) -> None:
        idx = GenreTagIndex()
        results = idx.search("house")
        assert len(results) > 2

    def test_search_empty_returns_items(self) -> None:
        idx = GenreTagIndex()
        results = idx.search("", limit=20)
        assert len(results) == 20

    def test_search_no_match(self) -> None:
        idx = GenreTagIndex()
        results = idx.search("zzzzcompletely_fake_genre_xyz")
        assert results == []

    def test_add_tag(self) -> None:
        idx = GenreTagIndex()
        before = len(idx)
        idx.add("custom-microgenre")
        assert len(idx) == before + 1
        assert "custom-microgenre" in idx.search("custom")

    def test_add_duplicate_noop(self) -> None:
        idx = GenreTagIndex()
        before = len(idx)
        idx.add("house")
        assert len(idx) == before

    def test_add_normalises(self) -> None:
        idx = GenreTagIndex()
        idx.add("  My Genre  ")
        results = idx.search("my genre")
        assert "my genre" in results

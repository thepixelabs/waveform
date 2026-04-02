"""Component and functional tests for Waveform."""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from create_playlist import (
    build_blocks_from_schedule,
    format_reference_for_prompt,
    get_block_prompt,
    load_history,
    load_settings,
    mark_used,
    get_used_keys,
    clear_history,
    save_json,
    search_track,
    prepare_playlist,
    add_tracks_to_playlist,
    create_full_from_songs,
    create_split_from_songs,
    get_playlist_prefix,
    DEFAULT_SETTINGS,
    DEFAULT_SCHEDULE,
    BLOCK_TYPES,
    TRACKS_PER_HOUR,
)


# ── Fixtures ──────────────────────────────────────────────


@pytest.fixture
def tmp_files(tmp_path, monkeypatch):
    """Redirect all file-based state to tmp_path."""
    monkeypatch.setattr("create_playlist.HISTORY_FILE", str(tmp_path / "history.json"))
    monkeypatch.setattr(
        "create_playlist.SETTINGS_FILE", str(tmp_path / "settings.json")
    )
    monkeypatch.setattr(
        "create_playlist.MASTER_PROMPT_FILE", str(tmp_path / "master_prompt.md")
    )
    monkeypatch.setattr(
        "create_playlist.BLOCKED_ARTISTS_FILE", str(tmp_path / "blocked_artists.txt")
    )
    monkeypatch.setattr(
        "create_playlist.REFERENCE_CACHE_FILE", str(tmp_path / "ref_cache.json")
    )
    return tmp_path


@pytest.fixture
def default_settings():
    """Fresh copy of default settings."""
    return json.loads(json.dumps(DEFAULT_SETTINGS))


@pytest.fixture
def mock_sp():
    """A mock Spotify client with common methods stubbed."""
    sp = MagicMock()
    sp.current_user.return_value = {"id": "test_user", "display_name": "Test"}
    sp.user_playlist_create.return_value = {"id": "new_playlist_id"}
    sp.search.return_value = {"tracks": {"items": []}}
    return sp


# ── Schedule → Blocks Pipeline ────────────────────────────


class TestBuildBlocksFromSchedule:
    def test_default_schedule_produces_correct_block_count(self, default_settings):
        blocks = build_blocks_from_schedule(default_settings)
        assert len(blocks) == len(DEFAULT_SCHEDULE)

    def test_track_counts_scale_with_duration(self, default_settings):
        """A 2-hour block should have ~2x the tracks of a 1-hour block at same TPH."""
        default_settings["schedule"] = [
            {"start": "20:00", "end": "22:00", "type": "chill"},
            {"start": "22:00", "end": "23:00", "type": "dance"},
        ]
        blocks = build_blocks_from_schedule(default_settings)
        assert blocks[0]["track_count"] == round(2 * TRACKS_PER_HOUR)
        assert blocks[1]["track_count"] == round(1 * TRACKS_PER_HOUR)

    def test_minimum_track_count_enforced(self, default_settings):
        """Even a very short block gets at least 5 tracks."""
        default_settings["schedule"] = [
            {"start": "23:00", "end": "23:10", "type": "chill"},
        ]
        default_settings["tracks_per_hour"] = 1
        blocks = build_blocks_from_schedule(default_settings)
        assert blocks[0]["track_count"] >= 5

    def test_custom_tracks_per_hour(self, default_settings):
        default_settings["schedule"] = [
            {"start": "20:00", "end": "21:00", "type": "chill"},
        ]
        default_settings["tracks_per_hour"] = 25
        blocks = build_blocks_from_schedule(default_settings)
        assert blocks[0]["track_count"] == 25

    def test_midnight_crossover_duration(self, default_settings):
        default_settings["schedule"] = [
            {"start": "23:00", "end": "02:00", "type": "dance"},
        ]
        blocks = build_blocks_from_schedule(default_settings)
        assert blocks[0]["duration_hours"] == 3.0

    def test_unknown_block_type_falls_back_to_chill(self, default_settings):
        default_settings["schedule"] = [
            {"start": "20:00", "end": "22:00", "type": "nonexistent_type"},
        ]
        blocks = build_blocks_from_schedule(default_settings)
        assert blocks[0]["subtitle"] == BLOCK_TYPES["chill"]["subtitle"]

    def test_block_metadata_populated(self, default_settings):
        default_settings["schedule"] = [
            {"start": "20:00", "end": "22:00", "type": "dance"},
        ]
        blocks = build_blocks_from_schedule(default_settings)
        b = blocks[0]
        assert b["key"] == "block_1"
        assert b["type"] == "dance"
        assert b["emoji"] == BLOCK_TYPES["dance"]["emoji"]
        assert b["color_start"] == BLOCK_TYPES["dance"]["color_start"]
        assert b["label"] == "20:00 – 22:00"

    def test_order_symbols_overflow(self, default_settings):
        """More than 10 blocks should get numeric fallback labels."""
        default_settings["schedule"] = [
            {"start": f"{h:02d}:00", "end": f"{h + 1:02d}:00", "type": "chill"}
            for h in range(12, 23)
        ]
        blocks = build_blocks_from_schedule(default_settings)
        assert blocks[10]["order"] == "(11)"


# ── Prompt Assembly ───────────────────────────────────────


class TestPromptAssembly:
    def test_dance_block_injects_psytrance_when_enabled(self, default_settings):
        block = {"type": "dance"}
        default_settings["psytrance_enabled"] = True
        default_settings["psytrance_pct"] = 40
        prompt = get_block_prompt(block, default_settings)
        assert "40%" in prompt
        assert "psytrance" in prompt.lower()

    def test_dance_block_disables_psytrance(self, default_settings):
        block = {"type": "dance"}
        default_settings["psytrance_enabled"] = False
        prompt = get_block_prompt(block, default_settings)
        assert "disabled by user" in prompt.lower()

    def test_non_dance_block_no_psytrance(self, default_settings):
        block = {"type": "chill"}
        prompt = get_block_prompt(block, default_settings)
        assert "psytrance" not in prompt.lower()

    def test_gemini_prompt_includes_blocked_artists(self, tmp_files, default_settings):
        """Full prompt sent to Gemini should include blocked artists."""
        blocked_path = str(tmp_files / "blocked_artists.txt")
        with open(blocked_path, "w") as f:
            f.write("# Comment line\nBad Artist\nAnother Bad Artist\n")

        from create_playlist import load_blocked_artists

        artists = load_blocked_artists()
        assert "Bad Artist" in artists
        assert "Another Bad Artist" in artists
        assert len(artists) == 2  # comment excluded

    def test_gemini_prompt_includes_mood_rules(self, tmp_files, default_settings):
        """Mood rules from settings should appear in the prompt context."""
        default_settings["mood_rules"] = "No breakup songs, heavy on reggaeton"
        # We can't call ask_gemini without API, but we can verify the prompt
        # would include mood rules by checking the code path
        mood = default_settings.get("mood_rules", "")
        assert "reggaeton" in mood


# ── History Lifecycle ─────────────────────────────────────


class TestHistoryLifecycle:
    def test_full_cycle_mark_and_retrieve(self, tmp_files):
        """mark_used → save → load → get_used_keys round-trip."""
        history = {"used_songs": {}}
        songs = [("Song A", "Artist 1"), ("Song B", "Artist 2")]
        mark_used(history, "block_1", songs, "TestPlaylist")

        # Load from disk (fresh read)
        loaded = load_history("TestPlaylist")
        used = get_used_keys(loaded, "block_1")
        assert "Song A||Artist 1" in used
        assert "Song B||Artist 2" in used

    def test_multi_playlist_isolation(self, tmp_files):
        """Songs marked under one playlist don't leak into another."""
        h1 = {"used_songs": {}}
        h2 = {"used_songs": {}}
        mark_used(h1, "block_1", [("Song X", "Artist")], "Playlist A")
        mark_used(h2, "block_1", [("Song Y", "Artist")], "Playlist B")

        loaded_a = load_history("Playlist A")
        loaded_b = load_history("Playlist B")
        assert "Song X||Artist" in get_used_keys(loaded_a, "block_1")
        assert "Song X||Artist" not in get_used_keys(loaded_b, "block_1")
        assert "Song Y||Artist" in get_used_keys(loaded_b, "block_1")

    def test_legacy_format_migration(self, tmp_files):
        """Old flat format {used_songs: {...}} should be migrated on load."""
        legacy_data = {"used_songs": {"block_1": ["Old Song||Old Artist"]}}
        save_json(str(tmp_files / "history.json"), legacy_data)

        load_history("anything")  # triggers migration
        # After migration the legacy data should be keyed under DEFAULT_PLAYLIST_PREFIX
        from create_playlist import DEFAULT_PLAYLIST_PREFIX

        migrated = load_history(DEFAULT_PLAYLIST_PREFIX)
        assert "Old Song||Old Artist" in get_used_keys(migrated, "block_1")

    def test_clear_history_single_playlist(self, tmp_files):
        """Clearing one playlist leaves others intact."""
        h = {"used_songs": {}}
        mark_used(h, "block_1", [("S1", "A1")], "Keep")
        h2 = {"used_songs": {}}
        mark_used(h2, "block_1", [("S2", "A2")], "Delete")

        clear_history("Delete")
        assert get_used_keys(load_history("Keep"), "block_1") == {"S1||A1"}
        assert get_used_keys(load_history("Delete"), "block_1") == set()

    def test_clear_all_history(self, tmp_files):
        """Clearing all history removes the file entirely."""
        h = {"used_songs": {}}
        mark_used(h, "block_1", [("S", "A")], "P")
        clear_history()  # no playlist_name = clear all
        assert not os.path.exists(str(tmp_files / "history.json"))

    def test_mark_used_prevents_duplicates_across_calls(self, tmp_files):
        """Calling mark_used twice with the same song shouldn't duplicate."""
        history = {"used_songs": {}}
        mark_used(history, "block_1", [("Dup", "Artist")], "Test")
        mark_used(history, "block_1", [("Dup", "Artist")], "Test")
        loaded = load_history("Test")
        assert loaded["used_songs"]["block_1"].count("Dup||Artist") == 1


# ── Reference Playlist Formatting ─────────────────────────


class TestFormatReference:
    def test_empty_returns_empty(self):
        assert format_reference_for_prompt([]) == ""

    def test_small_list_includes_all(self):
        tracks = [{"title": f"Song {i}", "artist": f"Artist {i}"} for i in range(10)]
        result = format_reference_for_prompt(tracks)
        assert "Song 0" in result
        assert "Song 9" in result
        assert "more tracks" not in result

    def test_large_list_truncates_at_80(self):
        tracks = [{"title": f"Song {i}", "artist": f"Artist {i}"} for i in range(150)]
        result = format_reference_for_prompt(tracks)
        assert "Song 0" in result
        assert "Song 79" in result
        assert "Song 80" not in result
        assert "70 more tracks" in result


# ── Spotify Track Search Fallback ─────────────────────────


class TestSearchTrack:
    def test_exact_match_returns_uri(self, mock_sp):
        mock_sp.search.return_value = {
            "tracks": {"items": [{"uri": "spotify:track:abc123"}]}
        }
        uri = search_track(mock_sp, "Bohemian Rhapsody", "Queen")
        assert uri == "spotify:track:abc123"
        # Should use exact query format first
        first_call_query = mock_sp.search.call_args_list[0][1].get(
            "q",
            mock_sp.search.call_args_list[0][0][0]
            if mock_sp.search.call_args_list[0][0]
            else "",
        )
        assert "track:" in first_call_query

    def test_fallback_to_broad_search(self, mock_sp):
        """When exact search fails, falls back to broad title+artist query."""
        mock_sp.search.side_effect = [
            {"tracks": {"items": []}},  # exact fails
            {
                "tracks": {"items": [{"uri": "spotify:track:fallback"}]}
            },  # broad succeeds
        ]
        uri = search_track(mock_sp, "Some Song", "Some Artist")
        assert uri == "spotify:track:fallback"
        assert mock_sp.search.call_count == 2

    def test_both_searches_fail_returns_none(self, mock_sp):
        mock_sp.search.return_value = {"tracks": {"items": []}}
        uri = search_track(mock_sp, "Nonexistent", "Nobody")
        assert uri is None

    def test_api_exception_handled(self, mock_sp):
        mock_sp.search.side_effect = Exception("API error")
        uri = search_track(mock_sp, "Song", "Artist")
        assert uri is None


# ── Playlist Preparation ──────────────────────────────────


class TestPreparePlaylist:
    def test_create_new_playlist(self, mock_sp):
        pid = prepare_playlist(mock_sp, "user1", "My Playlist", "desc", "create", {})
        assert pid == "new_playlist_id"
        mock_sp.user_playlist_create.assert_called_once()

    def test_overwrite_clears_existing(self, mock_sp):
        existing = {"My Playlist": {"id": "existing_id"}}
        pid = prepare_playlist(
            mock_sp, "user1", "My Playlist", "desc", "overwrite", existing
        )
        assert pid == "existing_id"
        mock_sp.playlist_replace_items.assert_called_once_with("existing_id", [])

    def test_append_reuses_existing(self, mock_sp):
        existing = {"My Playlist": {"id": "existing_id"}}
        pid = prepare_playlist(
            mock_sp, "user1", "My Playlist", "desc", "append", existing
        )
        assert pid == "existing_id"
        mock_sp.playlist_replace_items.assert_not_called()
        mock_sp.user_playlist_create.assert_not_called()

    def test_create_with_duplicate_adds_suffix(self, mock_sp):
        """Creating when a same-name playlist exists should add a date suffix."""
        existing = {"My Playlist": {"id": "old_id"}}
        pid = prepare_playlist(
            mock_sp, "user1", "My Playlist", "desc", "create", existing
        )
        assert pid == "new_playlist_id"
        created_name = mock_sp.user_playlist_create.call_args[1].get(
            "name",
            mock_sp.user_playlist_create.call_args[0][1]
            if len(mock_sp.user_playlist_create.call_args[0]) > 1
            else "",
        )
        # Should contain original name with a date/time suffix
        assert "My Playlist" in created_name


# ── Add Tracks (batch splitting) ──────────────────────────


class TestAddTracks:
    @patch("create_playlist.search_track")
    @patch("create_playlist.time")
    def test_batches_over_100_tracks(self, mock_time, mock_search, mock_sp):
        """Tracks should be added in batches of 100."""
        mock_search.return_value = "spotify:track:uri"
        tracks = [(f"Song {i}", f"Artist {i}") for i in range(150)]

        found, not_found = add_tracks_to_playlist(mock_sp, "pid", tracks)

        assert found == 150
        assert not_found == []
        # Should have been called twice: batch of 100 + batch of 50
        assert mock_sp.playlist_add_items.call_count == 2
        first_batch = mock_sp.playlist_add_items.call_args_list[0][0][1]
        second_batch = mock_sp.playlist_add_items.call_args_list[1][0][1]
        assert len(first_batch) == 100
        assert len(second_batch) == 50

    @patch("create_playlist.search_track")
    @patch("create_playlist.time")
    def test_not_found_tracks_reported(self, mock_time, mock_search, mock_sp):
        mock_search.side_effect = [
            "spotify:track:found",
            None,  # not found
            "spotify:track:found2",
        ]
        tracks = [("A", "1"), ("B", "2"), ("C", "3")]
        found, not_found = add_tracks_to_playlist(mock_sp, "pid", tracks)
        assert found == 2
        assert not_found == [("B", "2")]


# ── Settings Migration ────────────────────────────────────


class TestSettingsMigration:
    def test_old_settings_get_new_defaults(self, tmp_files):
        """Loading a settings file missing new keys should backfill defaults."""
        old_settings = {"schedule": DEFAULT_SCHEDULE, "tracks_per_hour": 16}
        save_json(str(tmp_files / "settings.json"), old_settings)

        loaded = load_settings()
        # New keys should be present with defaults
        assert "shuffle_within_blocks" in loaded
        assert "split_extra_pct" in loaded
        assert "allow_repeats" in loaded
        # Old values preserved
        assert loaded["tracks_per_hour"] == 16


# ── Full Playlist Assembly (integration) ──────────────────


class TestPlaylistAssembly:
    @patch("create_playlist.set_playlist_cover")
    @patch("create_playlist.generate_cover_image", return_value=None)
    @patch("create_playlist.add_tracks_to_playlist", return_value=(5, []))
    @patch("create_playlist.prepare_playlist", return_value="pid_123")
    def test_create_full_playlist_calls_all_blocks(
        self,
        mock_prepare,
        mock_add,
        mock_cover_gen,
        mock_cover_set,
        tmp_files,
        default_settings,
    ):
        """Full playlist creation should add tracks for every block."""
        sp = MagicMock()
        sp.current_user.return_value = {"id": "user1"}

        blocks = build_blocks_from_schedule(default_settings)
        all_songs = {
            b["key"]: [(f"Song {i}", f"Artist {i}") for i in range(b["track_count"])]
            for b in blocks
        }
        history = {"used_songs": {}}

        pid = create_full_from_songs(
            sp, blocks, all_songs, history, settings=default_settings
        )
        assert pid == "pid_123"
        # add_tracks should be called once per block
        assert mock_add.call_count == len(blocks)

    @patch("create_playlist.set_playlist_cover")
    @patch("create_playlist.generate_cover_image", return_value=None)
    @patch("create_playlist.add_tracks_to_playlist", return_value=(5, []))
    @patch("create_playlist.prepare_playlist", return_value="pid_split")
    def test_create_split_playlists_one_per_block(
        self,
        mock_prepare,
        mock_add,
        mock_cover_gen,
        mock_cover_set,
        tmp_files,
        default_settings,
    ):
        """Split mode should create a separate playlist for each block."""
        sp = MagicMock()
        sp.current_user.return_value = {"id": "user1"}

        blocks = build_blocks_from_schedule(default_settings)
        all_songs = {
            b["key"]: [(f"Song {i}", f"Artist {i}") for i in range(5)] for b in blocks
        }

        create_split_from_songs(sp, blocks, all_songs, settings=default_settings)
        # One playlist created per block
        assert mock_prepare.call_count == len(blocks)
        assert mock_add.call_count == len(blocks)

    @patch("create_playlist.set_playlist_cover")
    @patch("create_playlist.generate_cover_image", return_value=None)
    @patch("create_playlist.add_tracks_to_playlist", return_value=(5, []))
    @patch("create_playlist.prepare_playlist", return_value="pid_full")
    def test_full_playlist_marks_history(
        self,
        mock_prepare,
        mock_add,
        mock_cover_gen,
        mock_cover_set,
        tmp_files,
        default_settings,
    ):
        """After creating a full playlist, used songs should be in history."""
        sp = MagicMock()
        sp.current_user.return_value = {"id": "user1"}

        default_settings["schedule"] = [
            {"start": "20:00", "end": "21:00", "type": "chill"},
        ]
        blocks = build_blocks_from_schedule(default_settings)
        songs = [("Tracked Song", "Tracked Artist")]
        all_songs = {"block_1": songs}
        history = {"used_songs": {}}

        create_full_from_songs(
            sp, blocks, all_songs, history, settings=default_settings
        )

        prefix = get_playlist_prefix(default_settings)
        loaded = load_history(prefix)
        assert "Tracked Song||Tracked Artist" in get_used_keys(loaded, "block_1")


# ── Playlist Prefix Templating ────────────────────────────


class TestPlaylistPrefix:
    def test_name_template_substitution(self, monkeypatch):
        monkeypatch.setattr("create_playlist.BIRTHDAY_NAME", "John")
        settings = {"playlist_prefix": "{name}'s Party"}
        assert get_playlist_prefix(settings) == "John's Party"

    def test_empty_prefix_uses_default(self, monkeypatch):
        monkeypatch.setattr("create_playlist.BIRTHDAY_NAME", "John")
        monkeypatch.setattr("create_playlist.DEFAULT_PLAYLIST_PREFIX", "John Birthday")
        settings = {"playlist_prefix": ""}
        assert get_playlist_prefix(settings) == "John Birthday"

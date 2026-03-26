"""Tests for BirthDJ core utilities."""

import json
import os
import tempfile

import pytest

# Import testable utilities from the main module
from create_playlist import (
    block_duration_hours,
    extract_playlist_id,
    get_used_keys,
    load_json,
    mark_used,
    parse_time,
    save_json,
)


# ── parse_time ──────────────────────────────────────────────


class TestParseTime:
    def test_midnight(self):
        assert parse_time("00:00") == 0.0

    def test_noon(self):
        assert parse_time("12:00") == 12.0

    def test_with_minutes(self):
        assert parse_time("14:30") == 14.5

    def test_quarter_hour(self):
        assert parse_time("09:15") == 9.25


# ── block_duration_hours ────────────────────────────────────


class TestBlockDuration:
    def test_same_day(self):
        block = {"start": "18:00", "end": "21:00"}
        assert block_duration_hours(block) == 3.0

    def test_crosses_midnight(self):
        block = {"start": "23:00", "end": "02:00"}
        assert block_duration_hours(block) == 3.0

    def test_half_hour_block(self):
        block = {"start": "20:00", "end": "20:30"}
        assert block_duration_hours(block) == 0.5


# ── extract_playlist_id ────────────────────────────────────


class TestExtractPlaylistId:
    def test_full_url(self):
        url = "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"
        assert extract_playlist_id(url) == "37i9dQZF1DXcBWIGoYBM5M"

    def test_url_with_query_params(self):
        url = "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M?si=abc123"
        assert extract_playlist_id(url) == "37i9dQZF1DXcBWIGoYBM5M"

    def test_bare_id(self):
        assert extract_playlist_id("37i9dQZF1DXcBWIGoYBM5M") == "37i9dQZF1DXcBWIGoYBM5M"

    def test_empty_string(self):
        assert extract_playlist_id("") == ""

    def test_none(self):
        assert extract_playlist_id(None) == ""

    def test_spotify_uri(self):
        uri = "spotify:playlist:37i9dQZF1DXcBWIGoYBM5M"
        assert extract_playlist_id(uri) == "37i9dQZF1DXcBWIGoYBM5M"


# ── JSON persistence ───────────────────────────────────────


class TestJsonPersistence:
    def test_save_and_load(self, tmp_path):
        path = str(tmp_path / "test.json")
        data = {"key": "value", "number": 42}
        save_json(path, data)
        loaded = load_json(path, {})
        assert loaded == data

    def test_load_missing_file_returns_default(self, tmp_path):
        path = str(tmp_path / "nonexistent.json")
        assert load_json(path, {"default": True}) == {"default": True}

    def test_unicode_roundtrip(self, tmp_path):
        path = str(tmp_path / "unicode.json")
        data = {"artist": "עידן רייכל", "song": "שובי אל ביתי"}
        save_json(path, data)
        loaded = load_json(path, {})
        assert loaded == data


# ── Song history helpers ────────────────────────────────────


class TestSongHistory:
    def test_get_used_keys_empty(self):
        history = {"used_songs": {}}
        assert get_used_keys(history, "block_1") == set()

    def test_get_used_keys_with_data(self):
        history = {"used_songs": {"block_1": ["Song||Artist"]}}
        assert get_used_keys(history, "block_1") == {"Song||Artist"}

    def test_mark_used_creates_block(self, tmp_path, monkeypatch):
        # Redirect history file to temp dir so mark_used can save
        history_path = str(tmp_path / "history.json")
        monkeypatch.setattr("create_playlist.HISTORY_FILE", history_path)

        history = {"used_songs": {}}
        mark_used(history, "block_1", [("Bohemian Rhapsody", "Queen")])
        assert "Bohemian Rhapsody||Queen" in history["used_songs"]["block_1"]

    def test_mark_used_no_duplicates(self, tmp_path, monkeypatch):
        history_path = str(tmp_path / "history.json")
        monkeypatch.setattr("create_playlist.HISTORY_FILE", history_path)

        history = {"used_songs": {"block_1": ["Song||Artist"]}}
        mark_used(history, "block_1", [("Song", "Artist")])
        assert history["used_songs"]["block_1"].count("Song||Artist") == 1

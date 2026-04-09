"""
test_services.py — Tests for Fake* service test doubles and integration flows.
"""
import pytest
from typing import List

from waveform.services.spotify_client import (
    FakeSpotifyClient,
    SongSuggestion,
    SpotifyTrack,
)
from waveform.services.gemini_client import FakeGeminiClient
from waveform.services.cover_art import FakeCoverArtService
from waveform.services.preview_audio import FakePreviewAudioPlayer
from waveform.services.analytics import FakeAnalyticsService, SessionMetrics
from waveform.services.persistence import FakePersistenceService
from waveform.domain.block import Block, BlockArchetype, BUILTIN_TEMPLATES
from waveform.domain.event import TEMPLATE_BY_ID
from waveform.domain.session import PlaylistSession, VetoContext
import uuid


# ---------------------------------------------------------------------------
# SpotifyTrack / SongSuggestion serialisation
# ---------------------------------------------------------------------------

class TestSpotifyTrackSerialization:
    def test_round_trip(self) -> None:
        track = SpotifyTrack(
            uri="spotify:track:abc123",
            title="Test Song",
            artist="Test Artist",
            album="Test Album",
            duration_ms=210000,
            preview_url="https://example.com/preview",
            album_art_url="https://example.com/art.jpg",
        )
        d = track.to_dict()
        restored = SpotifyTrack.from_dict(d)
        assert restored.uri == track.uri
        assert restored.title == track.title
        assert restored.preview_url == track.preview_url

    def test_from_dict_handles_missing_fields(self) -> None:
        track = SpotifyTrack.from_dict({"uri": "spotify:track:x", "title": "T"})
        assert track.artist == ""
        assert track.preview_url is None


class TestSongSuggestionSerialization:
    def test_round_trip_with_track(self) -> None:
        track = SpotifyTrack(uri="spotify:track:x", title="T", artist="A")
        song = SongSuggestion(title="T", artist="A", reasoning="Good fit", track=track)
        d = song.to_dict()
        restored = SongSuggestion.from_dict(d)
        assert restored.title == "T"
        assert restored.track is not None
        assert restored.track.uri == "spotify:track:x"

    def test_round_trip_without_track(self) -> None:
        song = SongSuggestion(title="T", artist="A")
        d = song.to_dict()
        restored = SongSuggestion.from_dict(d)
        assert restored.track is None


# ---------------------------------------------------------------------------
# FakeSpotifyClient
# ---------------------------------------------------------------------------

class TestFakeSpotifyClient:
    def test_create_playlist_returns_id(self) -> None:
        client = FakeSpotifyClient()
        pid = client.create_playlist("Test Playlist")
        assert pid
        assert isinstance(pid, str)

    def test_add_tracks(self) -> None:
        client = FakeSpotifyClient()
        pid = client.create_playlist("Test")
        client.add_tracks(pid, ["spotify:track:a", "spotify:track:b"])
        tracks = client.get_playlist_tracks(pid)
        assert "spotify:track:a" in tracks

    def test_replace_tracks(self) -> None:
        client = FakeSpotifyClient()
        pid = client.create_playlist("Test")
        client.add_tracks(pid, ["spotify:track:a"])
        client.replace_tracks(pid, ["spotify:track:b"])
        tracks = client.get_playlist_tracks(pid)
        assert tracks == ["spotify:track:b"]

    def test_upload_cover_art(self) -> None:
        client = FakeSpotifyClient()
        pid = client.create_playlist("Test")
        client.upload_cover_art(pid, b"\xff\xd8\xff")
        assert client._covers[pid] == b"\xff\xd8\xff"

    def test_find_track_returns_track(self) -> None:
        client = FakeSpotifyClient()
        track = client.find_track("Blue", "A-Ha")
        assert track is not None
        assert track.title == "Blue"
        assert track.artist == "A-Ha"

    def test_search_user_playlists(self) -> None:
        client = FakeSpotifyClient()
        pid = client.create_playlist("My Party Mix")
        results = client.search_user_playlists("My Party Mix")
        assert pid in results

    def test_search_user_playlists_case_insensitive(self) -> None:
        client = FakeSpotifyClient()
        pid = client.create_playlist("My Party Mix")
        results = client.search_user_playlists("my party mix")
        assert pid in results

    def test_search_user_playlists_no_match(self) -> None:
        client = FakeSpotifyClient()
        client.create_playlist("Something Else")
        results = client.search_user_playlists("Nonexistent")
        assert results == []


# ---------------------------------------------------------------------------
# FakeGeminiClient
# ---------------------------------------------------------------------------

class TestFakeGeminiClient:
    def _make_block(self) -> Block:
        return Block.from_archetype(BlockArchetype.GROOVE, duration_minutes=60)

    def _make_session(self) -> PlaylistSession:
        return PlaylistSession(
            session_id=str(uuid.uuid4()),
            event_name="Test",
            event_template=TEMPLATE_BY_ID["birthday"],
            blocks=[self._make_block()],
        )

    def test_generate_songs_yields(self) -> None:
        client = FakeGeminiClient(songs_per_call=5)
        block = self._make_block()
        session = self._make_session()
        songs = list(client.generate_songs(block, session, n_songs=5))
        assert len(songs) == 5

    def test_songs_have_title_and_artist(self) -> None:
        client = FakeGeminiClient()
        block = self._make_block()
        session = self._make_session()
        songs = list(client.generate_songs(block, session, n_songs=3))
        for song in songs:
            assert song.title
            assert song.artist

    def test_generate_replacement(self) -> None:
        client = FakeGeminiClient()
        block = self._make_block()
        session = self._make_session()
        replacement = client.generate_single_replacement(block, session)
        assert replacement is not None
        assert replacement.title

    def test_records_generate_calls(self) -> None:
        client = FakeGeminiClient()
        block = self._make_block()
        session = self._make_session()
        list(client.generate_songs(block, session))
        assert len(client.generate_calls) == 1
        assert client.generate_calls[0]["block_id"] == block.id


# ---------------------------------------------------------------------------
# FakeCoverArtService
# ---------------------------------------------------------------------------

class TestFakeCoverArtService:
    def test_returns_bytes(self) -> None:
        svc = FakeCoverArtService()
        art = svc.generate_block_cover(BlockArchetype.GROOVE, "Test")
        assert isinstance(art, bytes)
        assert len(art) > 0

    def test_playlist_cover_returns_bytes(self) -> None:
        svc = FakeCoverArtService()
        art = svc.generate_playlist_cover()
        assert isinstance(art, bytes)


# ---------------------------------------------------------------------------
# FakePreviewAudioPlayer
# ---------------------------------------------------------------------------

class TestFakePreviewAudioPlayer:
    def test_play_records_url(self) -> None:
        player = FakePreviewAudioPlayer()
        player.play("https://example.com/preview.mp3")
        assert player.is_playing
        assert "https://example.com/preview.mp3" in player.plays

    def test_stop(self) -> None:
        player = FakePreviewAudioPlayer()
        player.play("https://example.com/preview.mp3")
        player.stop()
        assert not player.is_playing
        assert player.stops == 1


# ---------------------------------------------------------------------------
# FakeAnalyticsService
# ---------------------------------------------------------------------------

class TestFakeAnalyticsService:
    def test_events_recorded(self) -> None:
        svc = FakeAnalyticsService()
        svc.app_opened()
        svc.session_started("birthday")
        assert len(svc.events) == 2
        assert svc.events[0]["event"] == "app_opened"
        assert svc.events[1]["event"] == "session_started"
        assert svc.events[1]["event_type"] == "birthday"

    def test_opt_out_suppresses(self) -> None:
        svc = FakeAnalyticsService()
        svc.set_enabled(False)
        svc.app_opened()
        assert len(svc.events) == 0

    def test_song_vetoed_with_reason(self) -> None:
        svc = FakeAnalyticsService()
        svc.song_vetoed(track_id="abc", block_id="b1", reason_tag="too slow")
        ev = svc.events[0]
        assert ev["event"] == "song_vetoed"
        assert ev["reason_tag"] == "too slow"

    def test_playlist_exported_with_metrics(self) -> None:
        svc = FakeAnalyticsService()
        metrics = SessionMetrics(songs_suggested=10, songs_kept=7, songs_vetoed=2)
        svc.playlist_exported(n_blocks=3, n_tracks=15, metrics=metrics)
        ev = svc.events[0]
        assert ev["n_tracks"] == 15
        assert ev["songs_kept"] == 7

    def test_no_pii_in_events(self) -> None:
        svc = FakeAnalyticsService()
        svc.playlist_exported(n_blocks=2, n_tracks=10)
        ev = svc.events[0]
        # Track names should not appear in the payload
        assert "title" not in ev
        assert "track_name" not in ev


class TestSessionMetrics:
    def test_preview_to_keep_rate(self) -> None:
        m = SessionMetrics(songs_kept=7, previews_played=10)
        assert m.preview_to_keep_rate == 0.7

    def test_preview_to_keep_rate_zero_previews(self) -> None:
        m = SessionMetrics(songs_kept=5, previews_played=0)
        assert m.preview_to_keep_rate == 0.0

    def test_veto_depth(self) -> None:
        m = SessionMetrics(songs_kept=5, songs_vetoed=10)
        assert m.veto_depth == 2.0

    def test_veto_depth_zero_keeps(self) -> None:
        m = SessionMetrics(songs_vetoed=5, songs_kept=0)
        assert m.veto_depth == 0.0

    def test_as_dict_keys(self) -> None:
        m = SessionMetrics(songs_suggested=5, songs_kept=3, previews_played=4)
        d = m.as_dict()
        assert "songs_suggested" in d
        assert "preview_to_keep_rate" in d
        assert "veto_depth" in d


# ---------------------------------------------------------------------------
# Integration: session + service workflow
# ---------------------------------------------------------------------------

class TestServiceIntegration:
    def test_generation_to_export_flow(self) -> None:
        """Full happy path: generate songs → add to approved → export."""
        persistence = FakePersistenceService()
        spotify = FakeSpotifyClient()
        gemini = FakeGeminiClient(songs_per_call=3)
        analytics = FakeAnalyticsService()

        tpl = TEMPLATE_BY_ID["birthday"]
        blocks = [Block.from_archetype(arch, duration_minutes=60) for arch in tpl.default_blocks[:2]]
        session = PlaylistSession(
            session_id=str(uuid.uuid4()),
            event_name="Integration Test Party",
            event_template=tpl,
            blocks=blocks,
        )

        # Generate songs for first block
        songs: List[SongSuggestion] = []
        for song in gemini.generate_songs(blocks[0], session, n_songs=3):
            # Simulate Spotify lookup
            track = spotify.find_track(song.title, song.artist)
            import dataclasses
            song = dataclasses.replace(song, track=track)
            songs.append(song)
            session.mark_kept(song.title, song.artist)
            persistence.mark_used(song.title, song.artist)

        assert len(songs) == 3
        assert all(s.track is not None for s in songs)

        # Export
        approved_songs = {blocks[0].id: songs}
        playlist_id = spotify.create_playlist("Integration Test Party")
        uris = [s.track.uri for s in songs if s.track]
        spotify.add_tracks(playlist_id, uris)
        tracks_in_playlist = spotify.get_playlist_tracks(playlist_id)
        assert len(tracks_in_playlist) == len(uris)

        # Analytics
        analytics.playlist_exported(n_blocks=1, n_tracks=len(uris))
        assert any(e["event"] == "playlist_exported" for e in analytics.events)

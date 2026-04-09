"""
test_export.py — Tests for ExportController.
"""
import io
import time
import uuid
from typing import Any, Dict, List, Optional

import pytest

from waveform.app.export import (
    ExistingPlaylistAction,
    ExportController,
    ExportMode,
    ExportResult,
    _png_to_jpeg,
    _serialize_session,
)
from waveform.app.state import AppState, StateStore
from waveform.domain.block import Block, BlockArchetype
from waveform.domain.event import TEMPLATE_BY_ID
from waveform.domain.session import PlaylistSession
from waveform.services.analytics import FakeAnalyticsService
from waveform.services.cover_art import FakeCoverArtService
from waveform.services.persistence import FakePersistenceService
from waveform.services.spotify_client import FakeSpotifyClient, SongSuggestion, SpotifyTrack


def _make_session(n_blocks: int = 2) -> PlaylistSession:
    tpl = TEMPLATE_BY_ID["birthday"]
    blocks = [Block.from_archetype(BlockArchetype.GROOVE, duration_minutes=60) for _ in range(n_blocks)]
    return PlaylistSession(
        session_id=str(uuid.uuid4()),
        event_name="Test Party",
        event_template=tpl,
        blocks=blocks,
    )


def _make_songs(n: int = 3) -> List[SongSuggestion]:
    songs = []
    for i in range(n):
        track = SpotifyTrack(
            uri=f"spotify:track:test{i}",
            title=f"Song {i}",
            artist=f"Artist {i}",
        )
        songs.append(SongSuggestion(title=f"Song {i}", artist=f"Artist {i}", track=track))
    return songs


def _make_controller() -> tuple:
    store = StateStore()
    spotify = FakeSpotifyClient()
    cover_art = FakeCoverArtService()
    persistence = FakePersistenceService()
    analytics = FakeAnalyticsService()
    ctrl = ExportController(
        store=store,
        spotify_client=spotify,
        cover_art_service=cover_art,
        persistence=persistence,
        analytics=analytics,
    )
    return ctrl, store, spotify, persistence, analytics


class TestFullNightExport:
    def test_creates_one_playlist(self) -> None:
        ctrl, store, spotify, persistence, analytics = _make_controller()
        session = _make_session(2)
        songs_per_block = _make_songs(3)
        approved = {b.id: songs_per_block for b in session.blocks}

        results = []
        errors = []
        done = [False]

        def _on_complete(r: ExportResult) -> None:
            results.append(r)
            done[0] = True

        def _on_error(msg: str) -> None:
            errors.append(msg)
            done[0] = True

        ctrl.export_session(
            session=session,
            approved_songs=approved,
            mode=ExportMode.FULL_NIGHT,
            playlist_name="Test Party",
            on_complete=_on_complete,
            on_error=_on_error,
        )

        # Wait for background thread
        for _ in range(50):
            if done[0]:
                break
            time.sleep(0.1)

        assert not errors, f"Export error: {errors}"
        assert len(results) == 1
        assert results[0].track_count == 6  # 2 blocks × 3 songs

    def test_correct_track_count(self) -> None:
        ctrl, store, spotify, persistence, analytics = _make_controller()
        session = _make_session(1)
        songs = _make_songs(5)
        approved = {session.blocks[0].id: songs}

        results = []
        done = [False]
        ctrl.export_session(
            session=session,
            approved_songs=approved,
            mode=ExportMode.FULL_NIGHT,
            playlist_name="Test",
            on_complete=lambda r: (results.append(r), done.__setitem__(0, True)),
            on_error=lambda e: done.__setitem__(0, True),
        )
        for _ in range(50):
            if done[0]: break
            time.sleep(0.1)
        assert results[0].track_count == 5

    def test_analytics_event_fires(self) -> None:
        ctrl, store, spotify, persistence, analytics = _make_controller()
        session = _make_session(1)
        songs = _make_songs(2)
        approved = {session.blocks[0].id: songs}
        done = [False]
        ctrl.export_session(
            session=session,
            approved_songs=approved,
            mode=ExportMode.FULL_NIGHT,
            playlist_name="Test",
            on_complete=lambda r: done.__setitem__(0, True),
            on_error=lambda e: done.__setitem__(0, True),
        )
        for _ in range(50):
            if done[0]: break
            time.sleep(0.1)
        assert any(e["event"] == "playlist_exported" for e in analytics.events)

    def test_session_saved(self) -> None:
        ctrl, store, spotify, persistence, analytics = _make_controller()
        session = _make_session(1)
        songs = _make_songs(2)
        approved = {session.blocks[0].id: songs}
        done = [False]
        ctrl.export_session(
            session=session,
            approved_songs=approved,
            mode=ExportMode.FULL_NIGHT,
            playlist_name="Test",
            on_complete=lambda r: done.__setitem__(0, True),
            on_error=lambda e: done.__setitem__(0, True),
        )
        for _ in range(50):
            if done[0]: break
            time.sleep(0.1)
        assert session.session_id in persistence.list_sessions()

    def test_empty_approved_songs(self) -> None:
        ctrl, store, spotify, persistence, analytics = _make_controller()
        session = _make_session(1)
        done = [False]
        results = []
        ctrl.export_session(
            session=session,
            approved_songs={},
            mode=ExportMode.FULL_NIGHT,
            playlist_name="Empty",
            on_complete=lambda r: (results.append(r), done.__setitem__(0, True)),
            on_error=lambda e: done.__setitem__(0, True),
        )
        for _ in range(50):
            if done[0]: break
            time.sleep(0.1)
        assert results[0].track_count == 0


class TestSplitExport:
    def test_n_playlists_for_n_blocks(self) -> None:
        ctrl, store, spotify, persistence, analytics = _make_controller()
        session = _make_session(3)
        approved = {b.id: _make_songs(2) for b in session.blocks}
        results = []
        done = [False]
        ctrl.export_session(
            session=session,
            approved_songs=approved,
            mode=ExportMode.SPLIT,
            playlist_name="Party",
            on_complete=lambda r: (results.append(r), done.__setitem__(0, True)),
            on_error=lambda e: done.__setitem__(0, True),
        )
        for _ in range(50):
            if done[0]: break
            time.sleep(0.1)
        assert len(results[0].playlist_urls) == 3

    def test_blocks_without_songs_skipped(self) -> None:
        ctrl, store, spotify, persistence, analytics = _make_controller()
        session = _make_session(3)
        # Only first block has songs
        approved = {session.blocks[0].id: _make_songs(2)}
        results = []
        done = [False]
        ctrl.export_session(
            session=session,
            approved_songs=approved,
            mode=ExportMode.SPLIT,
            playlist_name="Party",
            on_complete=lambda r: (results.append(r), done.__setitem__(0, True)),
            on_error=lambda e: done.__setitem__(0, True),
        )
        for _ in range(50):
            if done[0]: break
            time.sleep(0.1)
        assert results[0].block_count == 1


class TestCollisionHandling:
    def test_rename_creates_new_playlist(self) -> None:
        ctrl, store, spotify, persistence, analytics = _make_controller()
        # Pre-create a playlist with same name
        spotify.create_playlist("Party Mix")

        session = _make_session(1)
        songs = _make_songs(2)
        approved = {session.blocks[0].id: songs}
        results = []
        done = [False]

        def _on_collision(name: str, resolve: Any) -> None:
            resolve(ExistingPlaylistAction.RENAME, "Party Mix (2)")

        ctrl.export_session(
            session=session,
            approved_songs=approved,
            mode=ExportMode.FULL_NIGHT,
            playlist_name="Party Mix",
            on_existing_playlist=_on_collision,
            on_complete=lambda r: (results.append(r), done.__setitem__(0, True)),
            on_error=lambda e: done.__setitem__(0, True),
        )
        for _ in range(50):
            if done[0]: break
            time.sleep(0.1)
        assert len(results) == 1

    def test_append_reuses_existing(self) -> None:
        ctrl, store, spotify, persistence, analytics = _make_controller()
        existing_pid = spotify.create_playlist("Party Mix")
        spotify.add_tracks(existing_pid, ["spotify:track:existing"])

        session = _make_session(1)
        songs = _make_songs(2)
        approved = {session.blocks[0].id: songs}
        results = []
        done = [False]

        def _on_collision(name: str, resolve: Any) -> None:
            resolve(ExistingPlaylistAction.APPEND)

        ctrl.export_session(
            session=session,
            approved_songs=approved,
            mode=ExportMode.FULL_NIGHT,
            playlist_name="Party Mix",
            on_existing_playlist=_on_collision,
            on_complete=lambda r: (results.append(r), done.__setitem__(0, True)),
            on_error=lambda e: done.__setitem__(0, True),
        )
        for _ in range(50):
            if done[0]: break
            time.sleep(0.1)
        assert len(results) == 1


class TestSongHistory:
    def test_history_saved_after_export(self) -> None:
        ctrl, store, spotify, persistence, analytics = _make_controller()
        session = _make_session(1)
        songs = _make_songs(2)
        approved = {session.blocks[0].id: songs}
        done = [False]
        ctrl.export_session(
            session=session,
            approved_songs=approved,
            mode=ExportMode.FULL_NIGHT,
            playlist_name="Test",
            on_complete=lambda r: done.__setitem__(0, True),
            on_error=lambda e: done.__setitem__(0, True),
        )
        for _ in range(50):
            if done[0]: break
            time.sleep(0.1)
        used = persistence.get_used_keys()
        assert len(used) == 2


class TestV1Migration:
    def test_psytrance_to_genre_weight(self) -> None:
        from waveform.services.persistence import migrate_v1_settings
        v1 = {"psytrance_enabled": True, "psytrance_pct": 60}
        v2 = migrate_v1_settings(v1)
        assert v2["schema_version"] == 2
        overrides = v2.get("block_genre_overrides", {})
        # Should have psytrance entries
        all_weights = []
        for block_overrides in overrides.values():
            all_weights.extend(gw["weight"] for gw in block_overrides)
        assert any(w > 0 for w in all_weights)

    def test_fake_persistence_noop(self) -> None:
        from waveform.services.persistence import FakePersistenceService
        svc = FakePersistenceService()
        assert svc.migrate_v1_if_needed() is False


class TestExportResult:
    def test_primary_url(self) -> None:
        r = ExportResult(
            playlist_urls=["https://open.spotify.com/playlist/abc"],
            track_count=10,
            block_count=2,
            elapsed_ms=500,
        )
        assert r.primary_url == "https://open.spotify.com/playlist/abc"

    def test_empty_urls(self) -> None:
        r = ExportResult(playlist_urls=[], track_count=0, block_count=0, elapsed_ms=0)
        assert r.primary_url is None

    def test_attribute_correctness(self) -> None:
        r = ExportResult(playlist_urls=["u1", "u2"], track_count=15, block_count=3, elapsed_ms=1200)
        assert r.track_count == 15
        assert r.block_count == 3
        assert r.elapsed_ms == 1200


try:
    from PIL import Image
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False


@pytest.mark.skipif(not _HAS_PIL, reason="PIL not installed")
class TestPngToJpeg:
    def test_jpeg_magic_bytes(self) -> None:
        from waveform.services.cover_art import generate_block_cover
        png_bytes = generate_block_cover(BlockArchetype.GROOVE, "Test")
        jpeg_bytes = _png_to_jpeg(png_bytes)
        assert jpeg_bytes[:2] == b"\xff\xd8"

    def test_size_under_256kb(self) -> None:
        from waveform.services.cover_art import generate_block_cover
        png_bytes = generate_block_cover(BlockArchetype.PEAK, "Big Event")
        jpeg_bytes = _png_to_jpeg(png_bytes)
        assert len(jpeg_bytes) <= 256 * 1024

"""
test_analytics.py — Tests for PostHog analytics instrumentation.
"""
import uuid
import pytest
from waveform.services.analytics import FakeAnalyticsService, SessionMetrics, AnalyticsService


class TestOptOutGate:
    def test_disabled_by_default(self) -> None:
        svc = FakeAnalyticsService()
        svc.set_enabled(False)
        svc.app_opened()
        assert len(svc.events) == 0

    def test_enabled_records(self) -> None:
        svc = FakeAnalyticsService()
        svc.app_opened()
        assert len(svc.events) == 1


class TestEventProperties:
    def test_session_started_has_event_type(self) -> None:
        svc = FakeAnalyticsService()
        svc.session_started(event_type="birthday")
        ev = svc.events[0]
        assert ev["event_type"] == "birthday"

    def test_generation_requested(self) -> None:
        svc = FakeAnalyticsService()
        svc.generation_requested(block_id="b1", n_existing_vetoes=3)
        ev = svc.events[0]
        assert ev["block_id"] == "b1"
        assert ev["n_existing_vetoes"] == 3

    def test_generation_completed(self) -> None:
        svc = FakeAnalyticsService()
        svc.generation_completed(block_id="b1", latency_ms=1500, n_songs_returned=8)
        ev = svc.events[0]
        assert ev["latency_ms"] == 1500
        assert ev["n_songs_returned"] == 8

    def test_song_previewed(self) -> None:
        svc = FakeAnalyticsService()
        svc.song_previewed(track_id="t1", block_id="b1", preview_duration_played=15000)
        ev = svc.events[0]
        assert ev["preview_duration_played"] == 15000

    def test_block_resized(self) -> None:
        svc = FakeAnalyticsService()
        svc.block_resized(archetype="groove", new_duration=75)
        ev = svc.events[0]
        assert ev["new_duration"] == 75

    def test_genre_weight_changed(self) -> None:
        svc = FakeAnalyticsService()
        svc.genre_weight_changed(block_id="b1", tag="house", weight=0.6)
        ev = svc.events[0]
        assert ev["tag"] == "house"
        assert ev["weight"] == 0.6

    def test_song_vetoed_with_reason(self) -> None:
        svc = FakeAnalyticsService()
        svc.song_vetoed(track_id="t1", block_id="b1", reason_tag="too slow")
        ev = svc.events[0]
        assert ev["reason_tag"] == "too slow"

    def test_song_vetoed_no_reason_defaults_empty(self) -> None:
        svc = FakeAnalyticsService()
        svc.song_vetoed(track_id="t1", block_id="b1", reason_tag=None)
        ev = svc.events[0]
        assert ev["reason_tag"] == ""

    def test_playlist_exported(self) -> None:
        svc = FakeAnalyticsService()
        svc.playlist_exported(n_blocks=3, n_tracks=15, time_from_open_ms=12000, event_type="birthday")
        ev = svc.events[0]
        assert ev["n_blocks"] == 3
        assert ev["n_tracks"] == 15
        assert ev["event_type"] == "birthday"


class TestNoPiiAssertions:
    def test_no_track_name_in_standard_events(self) -> None:
        svc = FakeAnalyticsService()
        svc.song_kept(track_id="spotify:track:abc", block_id="b1")
        ev = svc.events[0]
        # track_id is an opaque URI, not a human-readable name — acceptable
        # but the event must not include 'title' or 'track_name'
        assert "title" not in ev
        assert "track_name" not in ev
        assert "artist" not in ev

    def test_no_event_name_in_exported(self) -> None:
        svc = FakeAnalyticsService()
        svc.playlist_exported(n_blocks=2, n_tracks=10, event_type="birthday")
        ev = svc.events[0]
        assert "event_name" not in ev


class TestSessionMetricsComputed:
    def test_preview_to_keep_rate_normal(self) -> None:
        m = SessionMetrics(songs_kept=7, previews_played=10)
        assert abs(m.preview_to_keep_rate - 0.7) < 0.001

    def test_preview_to_keep_rate_division_by_zero(self) -> None:
        m = SessionMetrics(songs_kept=5, previews_played=0)
        assert m.preview_to_keep_rate == 0.0

    def test_veto_depth_normal(self) -> None:
        m = SessionMetrics(songs_kept=5, songs_vetoed=10)
        assert abs(m.veto_depth - 2.0) < 0.001

    def test_veto_depth_zero_keeps(self) -> None:
        m = SessionMetrics(songs_vetoed=5, songs_kept=0)
        assert m.veto_depth == 0.0

    def test_as_dict_has_all_keys(self) -> None:
        m = SessionMetrics(songs_suggested=10, songs_kept=7, songs_vetoed=2, previews_played=9)
        d = m.as_dict()
        expected = [
            "songs_suggested", "songs_kept", "songs_skipped", "songs_vetoed",
            "previews_played", "preview_seconds_played",
            "preview_to_keep_rate", "veto_depth",
        ]
        for k in expected:
            assert k in d, f"Missing key: {k}"


class TestDistinctIdPersistence:
    def test_distinct_id_set(self) -> None:
        did = str(uuid.uuid4())
        svc = AnalyticsService(distinct_id=did, enabled=False)
        assert svc._distinct_id == did


class TestFakeAnalyticsShutdown:
    def test_shutdown_noop(self) -> None:
        svc = FakeAnalyticsService()
        svc.shutdown()  # Must not raise


class TestAllEventTypes:
    def test_all_event_methods_callable(self) -> None:
        svc = FakeAnalyticsService()
        svc.app_opened()
        svc.session_started()
        svc.event_template_selected("birthday")
        svc.block_added("groove")
        svc.block_removed("groove")
        svc.block_resized("groove", 60)
        svc.block_reordered()
        svc.genre_weight_changed("b1", "house", 0.5)
        svc.generation_requested("b1")
        svc.generation_completed("b1", 1000, 5)
        svc.song_suggested("t1", "b1", 0)
        svc.song_previewed("t1", "b1", 15000)
        svc.song_kept("t1", "b1")
        svc.song_skipped("t1", "b1")
        svc.song_vetoed("t1", "b1", "too slow")
        svc.swap_requested("b1")
        svc.playlist_exported(3, 15, 12000, "birthday")
        svc.session_abandoned("timeline")
        svc.error_surfaced("generation", "timeout")
        assert len(svc.events) == 19

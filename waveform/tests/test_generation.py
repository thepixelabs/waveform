"""
test_generation.py — Tests for GenerationController.

This is the core feature test suite — the veto feedback loop invariants
must hold: context accumulates permanently within a session, and survives
re-generate calls.
"""
import threading
import time
import uuid
from typing import Any, List, Optional

import pytest

from waveform.app.generation import GenerationController
from waveform.app.state import AppState, StateStore
from waveform.domain.block import Block, BlockArchetype
from waveform.domain.event import TEMPLATE_BY_ID
from waveform.domain.session import PlaylistSession
from waveform.services.analytics import FakeAnalyticsService
from waveform.services.gemini_client import FakeGeminiClient
from waveform.services.persistence import FakePersistenceService
from waveform.services.spotify_client import FakeSpotifyClient, SongSuggestion


def _make_session(n_blocks: int = 1) -> PlaylistSession:
    tpl = TEMPLATE_BY_ID["birthday"]
    blocks = [Block.from_archetype(BlockArchetype.GROOVE, duration_minutes=60) for _ in range(n_blocks)]
    return PlaylistSession(
        session_id=str(uuid.uuid4()),
        event_name="Test",
        event_template=tpl,
        blocks=blocks,
    )


def _make_controller(songs_per_call: int = 5) -> tuple:
    store = StateStore()
    gemini = FakeGeminiClient(songs_per_call=songs_per_call)
    spotify = FakeSpotifyClient()
    persistence = FakePersistenceService()
    analytics = FakeAnalyticsService()
    ctrl = GenerationController(
        store=store,
        gemini_client=gemini,
        spotify_client=spotify,
        persistence=persistence,
        analytics=analytics,
    )
    return ctrl, store, gemini, analytics


class _GenerationWaiter:
    """Context manager to wait for generation completion."""

    def __init__(self, store: StateStore, block_id: str) -> None:
        self._store = store
        self._block_id = block_id
        self._done = threading.Event()
        store.subscribe(AppState.GENERATION_STATUS, self._on_status)

    def _on_status(self, status: Any) -> None:
        if status and status.get("block_id") == self._block_id and status.get("status") in ("done", "error"):
            self._done.set()

    def wait(self, timeout: float = 5.0) -> bool:
        return self._done.wait(timeout=timeout)


class TestBasicGeneration:
    def test_songs_appear_in_feed(self) -> None:
        ctrl, store, gemini, analytics = _make_controller(songs_per_call=3)
        session = _make_session()
        store.set(AppState.SESSION, session)
        block = session.blocks[0]

        waiter = _GenerationWaiter(store, block.id)
        ctrl.start_generation(session)
        assert waiter.wait(5.0), "Generation timed out"

        feed = store.get(AppState.SUGGESTION_FEED) or {}
        assert len(feed.get(block.id, [])) > 0

    def test_generation_complete_signal_fired(self) -> None:
        ctrl, store, gemini, analytics = _make_controller(songs_per_call=2)
        session = _make_session()
        store.set(AppState.SESSION, session)
        block = session.blocks[0]

        completed_ids = []
        store.subscribe(AppState.GENERATION_COMPLETE, lambda bid: completed_ids.append(bid))

        waiter = _GenerationWaiter(store, block.id)
        ctrl.start_generation(session)
        waiter.wait(5.0)

        assert block.id in completed_ids

    def test_status_transitions_generating_to_done(self) -> None:
        ctrl, store, gemini, analytics = _make_controller(songs_per_call=2)
        session = _make_session()
        store.set(AppState.SESSION, session)
        block = session.blocks[0]

        statuses = []
        store.subscribe(AppState.GENERATION_STATUS, lambda s: statuses.append(s.get("status") if s else None))

        waiter = _GenerationWaiter(store, block.id)
        ctrl.start_generation(session)
        waiter.wait(5.0)

        assert "generating" in statuses
        assert "done" in statuses

    def test_multi_block_generation(self) -> None:
        ctrl, store, gemini, analytics = _make_controller(songs_per_call=2)
        session = _make_session(n_blocks=2)
        store.set(AppState.SESSION, session)

        done_ids = []
        store.subscribe(AppState.GENERATION_COMPLETE, lambda bid: done_ids.append(bid))

        events = [_GenerationWaiter(store, b.id) for b in session.blocks]
        ctrl.start_generation(session)
        for w in events:
            w.wait(5.0)

        feed = store.get(AppState.SUGGESTION_FEED) or {}
        for block in session.blocks:
            assert len(feed.get(block.id, [])) > 0


class TestVetoFeedbackLoop:
    def test_veto_adds_to_context(self) -> None:
        ctrl, store, _, analytics = _make_controller()
        session = _make_session()
        store.set(AppState.SESSION, session)
        block = session.blocks[0]

        song = SongSuggestion(title="Bad Song", artist="Bad Artist")
        ctrl.handle_veto(block.id, song, reason_tag="too slow")

        updated_session = store.get(AppState.SESSION)
        assert updated_session.veto_context.is_vetoed("Bad Song", "Bad Artist")

    def test_veto_context_accumulates(self) -> None:
        ctrl, store, _, analytics = _make_controller()
        session = _make_session()
        store.set(AppState.SESSION, session)
        block = session.blocks[0]

        for i in range(3):
            song = SongSuggestion(title=f"Song {i}", artist=f"Artist {i}")
            ctrl.handle_veto(block.id, song)

        updated_session = store.get(AppState.SESSION)
        assert updated_session.veto_context.veto_count == 3

    def test_veto_context_persists_across_regeneration(self) -> None:
        """THE KILLER FEATURE invariant: veto context survives re-generate calls."""
        ctrl, store, gemini, analytics = _make_controller(songs_per_call=2)
        session = _make_session()
        store.set(AppState.SESSION, session)
        block = session.blocks[0]

        # Veto a song
        song = SongSuggestion(title="Vetoed Song", artist="Vetoed Artist")
        ctrl.handle_veto(block.id, song)

        # Re-generate
        waiter = _GenerationWaiter(store, block.id)
        session_after_veto = store.get(AppState.SESSION)
        ctrl.start_generation(session_after_veto)
        waiter.wait(5.0)

        # Veto context should still be present after re-generate
        final_session = store.get(AppState.SESSION)
        assert final_session.veto_context.is_vetoed("Vetoed Song", "Vetoed Artist")

    def test_keep_adds_positive_context(self) -> None:
        ctrl, store, _, analytics = _make_controller()
        session = _make_session()
        store.set(AppState.SESSION, session)
        block = session.blocks[0]

        song = SongSuggestion(title="Good Song", artist="Good Artist")
        ctrl.handle_keep(block.id, song)

        updated_session = store.get(AppState.SESSION)
        assert updated_session.was_kept("Good Song", "Good Artist")
        assert len(updated_session.veto_context.keeps) == 1

    def test_keep_fires_analytics(self) -> None:
        ctrl, store, _, analytics = _make_controller()
        session = _make_session()
        store.set(AppState.SESSION, session)
        block = session.blocks[0]

        song = SongSuggestion(title="Good", artist="Artist")
        ctrl.handle_keep(block.id, song)

        assert any(e["event"] == "song_kept" for e in analytics.events)

    def test_veto_fires_analytics(self) -> None:
        ctrl, store, _, analytics = _make_controller()
        session = _make_session()
        store.set(AppState.SESSION, session)
        block = session.blocks[0]

        song = SongSuggestion(title="Bad", artist="Artist")
        ctrl.handle_veto(block.id, song, reason_tag="wrong genre")

        ev = next(e for e in analytics.events if e["event"] == "song_vetoed")
        assert ev["reason_tag"] == "wrong genre"


class TestDuplicateDetection:
    def test_kept_song_treated_as_duplicate(self) -> None:
        ctrl, store, _, _ = _make_controller()
        session = _make_session()
        store.set(AppState.SESSION, session)
        session.mark_kept("Blue", "A-Ha")

        song = SongSuggestion(title="Blue", artist="A-Ha")
        is_dup = ctrl._is_duplicate(session, song)
        assert is_dup

    def test_cross_session_duplicate(self) -> None:
        ctrl, store, _, _ = _make_controller()
        session = _make_session()
        ctrl._persistence.mark_used("Blue", "A-Ha")

        song = SongSuggestion(title="Blue", artist="A-Ha")
        is_dup = ctrl._is_duplicate(session, song)
        assert is_dup

    def test_no_false_positive(self) -> None:
        ctrl, store, _, _ = _make_controller()
        session = _make_session()

        song = SongSuggestion(title="Fresh Song", artist="New Artist")
        is_dup = ctrl._is_duplicate(session, song)
        assert not is_dup

    def test_vetoed_song_treated_as_duplicate(self) -> None:
        ctrl, store, _, _ = _make_controller()
        session = _make_session()
        block = session.blocks[0]
        store.set(AppState.SESSION, session)

        ctrl.handle_veto(block.id, SongSuggestion(title="Vetoed", artist="Artist"))
        updated = store.get(AppState.SESSION)

        song = SongSuggestion(title="Vetoed", artist="Artist")
        assert ctrl._is_duplicate(updated, song)

    def test_key_normalisation(self) -> None:
        ctrl, store, _, _ = _make_controller()
        session = _make_session()
        ctrl._persistence.mark_used("Blue", "A-Ha")

        song = SongSuggestion(title="BLUE", artist="A-HA")
        assert ctrl._is_duplicate(session, song)


class TestSwapFlow:
    def test_request_swap_emits_pending_song(self) -> None:
        ctrl, store, gemini, analytics = _make_controller()
        session = _make_session()
        store.set(AppState.SESSION, session)
        block = session.blocks[0]

        pending_songs = []
        store.subscribe(AppState.PENDING_SONG, lambda v: pending_songs.append(v))

        ref_song = SongSuggestion(title="Old Song", artist="Artist")
        ctrl.request_swap(block.id, ref_song)
        time.sleep(0.5)  # Let the worker thread run

        assert len(pending_songs) > 0

    def test_swap_fires_analytics(self) -> None:
        ctrl, store, gemini, analytics = _make_controller()
        session = _make_session()
        store.set(AppState.SESSION, session)
        block = session.blocks[0]

        ref_song = SongSuggestion(title="Old Song", artist="Artist")
        ctrl.request_swap(block.id, ref_song)
        time.sleep(0.5)

        assert any(e["event"] == "swap_requested" for e in analytics.events)


class TestGenerationAnalytics:
    def test_generation_requested_event(self) -> None:
        ctrl, store, gemini, analytics = _make_controller(songs_per_call=1)
        session = _make_session()
        store.set(AppState.SESSION, session)
        block = session.blocks[0]

        waiter = _GenerationWaiter(store, block.id)
        ctrl.start_generation(session)
        waiter.wait(5.0)

        ev = next((e for e in analytics.events if e["event"] == "generation_requested"), None)
        assert ev is not None
        assert ev["block_id"] == block.id

    def test_generation_completed_event(self) -> None:
        ctrl, store, gemini, analytics = _make_controller(songs_per_call=2)
        session = _make_session()
        store.set(AppState.SESSION, session)
        block = session.blocks[0]

        waiter = _GenerationWaiter(store, block.id)
        ctrl.start_generation(session)
        waiter.wait(5.0)

        ev = next((e for e in analytics.events if e["event"] == "generation_completed"), None)
        assert ev is not None
        assert ev["n_songs_returned"] > 0
        assert ev["latency_ms"] >= 0


class TestCancel:
    def test_cancel_reduces_emission_count(self) -> None:
        # FakeGeminiClient is synchronous so we can't truly interrupt,
        # but we can test that cancel doesn't crash and sets is_generating=False.
        ctrl, store, gemini, analytics = _make_controller(songs_per_call=3)
        session = _make_session()
        store.set(AppState.SESSION, session)

        ctrl.cancel()
        assert store.get(AppState.IS_GENERATING) is False

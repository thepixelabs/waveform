"""
generation.py — GenerationController: orchestrates AI generation + veto feedback.

This is the core of Waveform's killer feature: the veto feedback loop.
VetoContext accumulates rejections permanently within a session, and every
re-generation call for that session injects the context into the AI prompt.
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from waveform.app.state import AppState, StateStore
from waveform.domain.session import PlaylistSession


class GenerationController:
    def __init__(
        self,
        store: StateStore,
        gemini_client: Any,
        spotify_client: Any,
        persistence: Any,
        analytics: Any,
    ) -> None:
        self._store = store
        self._gemini = gemini_client
        self._spotify = spotify_client
        self._persistence = persistence
        self._analytics = analytics
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="gen")
        self._cancel_event = threading.Event()

        # Register self in store so shell can retrieve it
        store.set(AppState.GENERATION_CONTROLLER, self)

    def start_generation(
        self,
        session: PlaylistSession,
        block_id: Optional[str] = None,
    ) -> None:
        """Submit generation futures for all blocks (or a single block)."""
        self._cancel_event.clear()

        blocks = session.blocks if block_id is None else [b for b in session.blocks if b.id == block_id]
        if not blocks:
            return

        # Initialise suggestion feed
        feed = self._store.get(AppState.SUGGESTION_FEED) or {}
        for block in blocks:
            feed[block.id] = []
        self._store.set(AppState.SUGGESTION_FEED, feed)
        self._store.set(AppState.IS_GENERATING, True)

        for block in blocks:
            self._analytics.generation_requested(
                block_id=block.id,
                n_existing_vetoes=session.veto_context.veto_count,
            )
            self._executor.submit(self._stream_songs, session, block)

    def cancel(self) -> None:
        self._cancel_event.set()
        self._store.set(AppState.IS_GENERATING, False)

    def handle_keep(self, block_id: str, song: Any) -> None:
        session: Optional[PlaylistSession] = self._store.get(AppState.SESSION)
        if session is None:
            return
        session.veto_context.add_keep(
            block_id=block_id,
            title=song.title,
            artist=song.artist,
        )
        session.mark_kept(song.title, song.artist)
        self._analytics.song_kept(
            track_id=getattr(getattr(song, "track", None), "uri", ""),
            block_id=block_id,
        )
        self._store.set(AppState.SESSION, session)

    def handle_skip(self, block_id: str, song: Any) -> None:
        self._analytics.song_skipped(
            track_id=getattr(getattr(song, "track", None), "uri", ""),
            block_id=block_id,
        )

    def handle_veto(
        self,
        block_id: str,
        song: Any,
        reason_tag: Optional[str] = None,
    ) -> None:
        session: Optional[PlaylistSession] = self._store.get(AppState.SESSION)
        if session is None:
            return
        session.veto_context.add_veto(
            block_id=block_id,
            title=song.title,
            artist=song.artist,
            reason_tag=reason_tag,
        )
        self._analytics.song_vetoed(
            track_id=getattr(getattr(song, "track", None), "uri", ""),
            block_id=block_id,
            reason_tag=reason_tag,
        )
        self._store.set(AppState.SESSION, session)

    def request_swap(self, block_id: str, reference_song: Any) -> None:
        session: Optional[PlaylistSession] = self._store.get(AppState.SESSION)
        if session is None:
            return
        self._analytics.swap_requested(block_id=block_id)
        block = next((b for b in session.blocks if b.id == block_id), None)
        if block is None:
            return
        self._executor.submit(self._swap_worker, session, block, reference_song)

    # -------------------------------------------------------------------
    # Background workers
    # -------------------------------------------------------------------

    def _stream_songs(self, session: PlaylistSession, block: Any) -> None:
        start_ms = int(time.time() * 1000)
        position = 0
        n_returned = 0

        try:
            self._store.set(AppState.GENERATION_STATUS, {
                "block_id": block.id,
                "status": "generating",
                "progress": 0,
                "total": block.track_count,
            })

            for song in self._gemini.generate_songs(
                block=block,
                session=session,
                veto_context=session.veto_context,
                n_songs=block.track_count,
            ):
                if self._cancel_event.is_set():
                    break

                # Duplicate detection (with up to 3 retries)
                is_duplicate = self._is_duplicate(session, song)
                retries = 0
                while is_duplicate and retries < 3:
                    replacement = self._gemini.generate_single_replacement(
                        block=block,
                        session=session,
                        veto_context=session.veto_context,
                    )
                    if replacement and not self._is_duplicate(session, replacement):
                        song = replacement
                        is_duplicate = False
                    retries += 1

                # Spotify lookup
                if song.track is None:
                    try:
                        track = self._spotify.find_track(song.title, song.artist)
                        if track:
                            import dataclasses as _dc
                            song = _dc.replace(song, track=track)
                    except Exception:
                        pass

                annotated = {
                    "song": song,
                    "is_duplicate": is_duplicate,
                    "position": position,
                }

                # Accumulate in feed
                feed = self._store.get(AppState.SUGGESTION_FEED) or {}
                feed.setdefault(block.id, []).append(annotated)
                self._store.set(AppState.SUGGESTION_FEED, feed)

                # Signal the UI
                self._store.set(AppState.PENDING_SONG, (block.id, annotated))

                # Analytics
                track_id = getattr(getattr(song, "track", None), "uri", "")
                self._analytics.song_suggested(
                    track_id=track_id,
                    block_id=block.id,
                    position=position,
                )

                position += 1
                n_returned += 1

                self._store.set(AppState.GENERATION_STATUS, {
                    "block_id": block.id,
                    "status": "generating",
                    "progress": position,
                    "total": block.track_count,
                })

            latency_ms = int(time.time() * 1000) - start_ms
            self._analytics.generation_completed(
                block_id=block.id,
                latency_ms=latency_ms,
                n_songs_returned=n_returned,
            )
            self._store.set(AppState.GENERATION_STATUS, {
                "block_id": block.id,
                "status": "done",
                "progress": n_returned,
                "total": n_returned,
            })
            self._store.set(AppState.GENERATION_COMPLETE, block.id)

        except Exception as exc:
            self._store.set(AppState.TOAST, {
                "message": f"Generation failed: {exc}",
                "type": "error",
            })
            self._store.set(AppState.GENERATION_STATUS, {
                "block_id": block.id,
                "status": "error",
                "progress": 0,
                "total": 0,
            })

    def _swap_worker(self, session: PlaylistSession, block: Any, reference_song: Any) -> None:
        try:
            exclude = [reference_song.title]
            replacement = self._gemini.generate_single_replacement(
                block=block,
                session=session,
                veto_context=session.veto_context,
                exclude_titles=exclude,
            )
            if replacement is None:
                return

            # Spotify lookup
            if replacement.track is None:
                try:
                    track = self._spotify.find_track(replacement.title, replacement.artist)
                    if track:
                        import dataclasses as _dc
                        replacement = _dc.replace(replacement, track=track)
                except Exception:
                    pass

            annotated = {
                "song": replacement,
                "is_duplicate": False,
                "position": -1,  # swap doesn't have a position
            }
            self._store.set(AppState.PENDING_SONG, (block.id, annotated))
        except Exception as exc:
            self._store.set(AppState.TOAST, {
                "message": f"Swap failed: {exc}",
                "type": "error",
            })

    def _is_duplicate(self, session: PlaylistSession, song: Any) -> bool:
        title, artist = song.title, song.artist
        # In-session keep history
        if session.was_kept(title, artist):
            return True
        # Cross-session
        key = f"{title.lower().strip()}||{artist.lower().strip()}"
        if self._persistence.get_used_keys().get(key):
            return True
        # Vetoed
        if session.veto_context.is_vetoed(title, artist):
            return True
        return False

"""
export.py — ExportController: orchestrates Spotify playlist export.

Handles full-night and split-by-block modes, name collision resolution,
cover art upload, session save, and analytics.
"""
from __future__ import annotations

import dataclasses
import enum
import io
import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

from waveform.app.state import AppState, StateStore
from waveform.domain.session import PlaylistSession


class ExportMode(enum.Enum):
    FULL_NIGHT = "full_night"
    SPLIT = "split"


class ExistingPlaylistAction(enum.Enum):
    OVERWRITE = "overwrite"
    APPEND = "append"
    RENAME = "rename"


@dataclasses.dataclass
class ExportResult:
    playlist_urls: List[str]
    track_count: int
    block_count: int
    elapsed_ms: int

    @property
    def primary_url(self) -> Optional[str]:
        return self.playlist_urls[0] if self.playlist_urls else None


class ExportController:
    def __init__(
        self,
        store: StateStore,
        spotify_client: Any,
        cover_art_service: Any,
        persistence: Any,
        analytics: Any,
    ) -> None:
        self._store = store
        self._spotify = spotify_client
        self._cover_art = cover_art_service
        self._persistence = persistence
        self._analytics = analytics
        self._renamed_playlist_name: Optional[str] = None

    def export_session(
        self,
        session: PlaylistSession,
        approved_songs: Dict[str, List[Any]],
        mode: ExportMode,
        playlist_name: str,
        on_progress: Optional[Callable[[str], None]] = None,
        on_existing_playlist: Optional[Callable[[str, Callable], None]] = None,
        on_complete: Optional[Callable[["ExportResult"], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
        app_open_time_ms: int = 0,
    ) -> None:
        """Run export in a background thread."""
        t = threading.Thread(
            target=self._export_worker,
            args=(
                session,
                approved_songs,
                mode,
                playlist_name,
                on_progress,
                on_existing_playlist,
                on_complete,
                on_error,
                app_open_time_ms,
            ),
            daemon=True,
        )
        t.start()

    def _export_worker(
        self,
        session: PlaylistSession,
        approved_songs: Dict[str, List[Any]],
        mode: ExportMode,
        playlist_name: str,
        on_progress: Optional[Callable],
        on_existing_playlist: Optional[Callable],
        on_complete: Optional[Callable],
        on_error: Optional[Callable],
        app_open_time_ms: int,
    ) -> None:
        start_ms = int(time.time() * 1000)
        try:
            if mode == ExportMode.FULL_NIGHT:
                result = self._export_full_night(
                    session,
                    approved_songs,
                    playlist_name,
                    on_progress,
                    on_existing_playlist,
                )
            else:
                result = self._export_split(
                    session,
                    approved_songs,
                    playlist_name,
                    on_progress,
                )

            elapsed = int(time.time() * 1000) - start_ms
            result = dataclasses.replace(result, elapsed_ms=elapsed)

            # Analytics
            event_type = self._session_event_name(session)
            self._analytics.playlist_exported(
                n_blocks=result.block_count,
                n_tracks=result.track_count,
                time_from_open_ms=app_open_time_ms,
                event_type=event_type,
            )

            # Save session
            self._save_session(session, approved_songs, result)

            if on_complete:
                on_complete(result)

        except Exception as exc:
            if on_error:
                on_error(str(exc))

    def _export_full_night(
        self,
        session: PlaylistSession,
        approved_songs: Dict[str, List[Any]],
        playlist_name: str,
        on_progress: Optional[Callable],
        on_existing_playlist: Optional[Callable],
    ) -> ExportResult:
        effective_name = self._resolve_collision(
            playlist_name,
            on_existing_playlist,
        )

        if on_progress:
            on_progress(f"Creating playlist '{effective_name}'…")

        # Collect all track URIs (in block order)
        all_uris: List[str] = []
        for block in session.blocks:
            songs = approved_songs.get(block.id, [])
            for song in songs:
                track = getattr(song, "track", None)
                if track and track.uri:
                    all_uris.append(track.uri)
                    self._persistence.mark_used(song.title, song.artist)

        if not all_uris:
            # Still create the playlist, just empty
            pass

        # Check for rename action
        existing_ids = self._spotify.search_user_playlists(effective_name)
        if existing_ids and hasattr(self, "_pending_action"):
            action = getattr(self, "_pending_action", ExistingPlaylistAction.OVERWRITE)
            pid = existing_ids[0]
            if action == ExistingPlaylistAction.OVERWRITE:
                if on_progress:
                    on_progress("Overwriting existing playlist…")
                self._spotify.replace_tracks(pid, all_uris)
            elif action == ExistingPlaylistAction.APPEND:
                if on_progress:
                    on_progress("Appending to existing playlist…")
                self._spotify.add_tracks(pid, all_uris)
            else:
                pid = self._spotify.create_playlist(effective_name, public=False)
                self._spotify.add_tracks(pid, all_uris)
        else:
            if on_progress:
                on_progress("Creating new playlist…")
            pid = self._spotify.create_playlist(effective_name, public=False)
            self._spotify.add_tracks(pid, all_uris)

        # Cover art
        if on_progress:
            on_progress("Uploading cover art…")
        try:
            art_bytes = self._cover_art.generate_playlist_cover(session)
            jpeg_bytes = _png_to_jpeg(art_bytes)
            self._spotify.upload_cover_art(pid, jpeg_bytes)
        except Exception:
            pass

        playlist_url = f"https://open.spotify.com/playlist/{pid}"
        return ExportResult(
            playlist_urls=[playlist_url],
            track_count=len(all_uris),
            block_count=len(session.blocks),
            elapsed_ms=0,
        )

    def _export_split(
        self,
        session: PlaylistSession,
        approved_songs: Dict[str, List[Any]],
        base_name: str,
        on_progress: Optional[Callable],
    ) -> ExportResult:
        urls: List[str] = []
        total_tracks = 0
        blocks_with_songs = [b for b in session.blocks if approved_songs.get(b.id)]

        for i, block in enumerate(blocks_with_songs):
            name = f"{base_name} — {block.name}"
            songs = approved_songs.get(block.id, [])
            uris = []
            for song in songs:
                track = getattr(song, "track", None)
                if track and track.uri:
                    uris.append(track.uri)
                    self._persistence.mark_used(song.title, song.artist)

            if on_progress:
                on_progress(f"Creating block {i + 1}/{len(blocks_with_songs)}: {block.name}")

            pid = self._spotify.create_playlist(name, public=False)
            if uris:
                self._spotify.add_tracks(pid, uris)

            # Per-block cover art
            try:
                art_bytes = self._cover_art.generate_block_cover(block.archetype, getattr(getattr(session, "event_template", None), "name", ""))
                jpeg_bytes = _png_to_jpeg(art_bytes)
                self._spotify.upload_cover_art(pid, jpeg_bytes)
            except Exception:
                pass

            urls.append(f"https://open.spotify.com/playlist/{pid}")
            total_tracks += len(uris)

        return ExportResult(
            playlist_urls=urls,
            track_count=total_tracks,
            block_count=len(blocks_with_songs),
            elapsed_ms=0,
        )

    def _resolve_collision(
        self,
        name: str,
        on_existing_playlist: Optional[Callable],
    ) -> str:
        """Check for an existing playlist with this name.
        If found, fire on_existing_playlist and block until resolved."""
        existing_ids = self._spotify.search_user_playlists(name)
        if not existing_ids:
            return name

        if on_existing_playlist is None:
            return name

        result_holder: List[Optional[ExistingPlaylistAction]] = [None]
        rename_holder: List[str] = [name]
        event = threading.Event()

        def resolve(action: ExistingPlaylistAction, new_name: Optional[str] = None) -> None:
            result_holder[0] = action
            if new_name:
                rename_holder[0] = new_name
            event.set()

        on_existing_playlist(name, resolve)
        event.wait(timeout=300)  # 5 min timeout

        action = result_holder[0] or ExistingPlaylistAction.OVERWRITE
        self._pending_action = action
        return rename_holder[0]

    def _save_session(
        self,
        session: PlaylistSession,
        approved_songs: Dict[str, List[Any]],
        result: ExportResult,
    ) -> None:
        import datetime

        session_data = _serialize_session(session, approved_songs, result)
        self._persistence.save_session(session.session_id, session_data)

    @staticmethod
    def _session_event_name(session: PlaylistSession) -> str:
        tpl = getattr(session, "event_template", None)
        if tpl is not None:
            return getattr(tpl, "id", "")
        return ""


# ---------------------------------------------------------------------------
# Session serialisation
# ---------------------------------------------------------------------------

def _serialize_session(
    session: PlaylistSession,
    approved_songs: Optional[Dict[str, List[Any]]] = None,
    result: Optional[ExportResult] = None,
) -> dict:
    import datetime

    blocks_data = []
    for block in session.blocks:
        gw_list = [{"tag": gw.tag, "weight": gw.weight} for gw in block.genre_weights]
        blocks_data.append({
            "id": block.id,
            "name": block.name,
            "archetype": str(block.archetype.value if hasattr(block.archetype, "value") else block.archetype),
            "duration_minutes": block.duration_minutes,
            "energy_level": block.energy_level,
            "genre_weights": gw_list,
        })

    # Veto entries
    veto_entries = []
    for ve in session.veto_context.vetoes:
        veto_entries.append({
            "block_id": ve.block_id,
            "title": ve.title,
            "artist": ve.artist,
            "reason_tag": ve.reason_tag,
        })

    # Keep entries
    keep_entries = []
    for ke in session.veto_context.keeps:
        keep_entries.append({
            "block_id": ke.block_id,
            "title": ke.title,
            "artist": ke.artist,
        })

    # Approved songs
    approved_data: Dict[str, List[Any]] = {}
    if approved_songs:
        for block_id, songs in approved_songs.items():
            song_list = []
            for song in songs:
                try:
                    song_list.append(song.to_dict())
                except Exception:
                    pass
            approved_data[block_id] = song_list

    tpl = getattr(session, "event_template", None)
    data = {
        "session_id": session.session_id,
        "event_name": session.event_name,
        "template_id": getattr(tpl, "id", "") if tpl else "",
        "event_type": getattr(tpl, "id", "") if tpl else "",
        "vibe_override": session.vibe_override,
        "blocks": blocks_data,
        "keep_history": dict(session.keep_history),
        "veto_count": session.veto_context.veto_count,
        "veto_entries": veto_entries,
        "keep_entries": keep_entries,
        "approved_songs": approved_data,
        "playlist_urls": list(getattr(session, "playlist_urls", [])),
        "exported_at": datetime.datetime.utcnow().isoformat() + "Z",
    }

    if result is not None:
        data["playlist_urls"] = result.playlist_urls
        data["track_count"] = result.track_count

    return data


# ---------------------------------------------------------------------------
# JPEG conversion
# ---------------------------------------------------------------------------

def _png_to_jpeg(png_bytes: bytes, max_size: int = 256 * 1024) -> bytes:
    """Convert PNG bytes to JPEG ≤256 KB (Spotify limit)."""
    try:
        from PIL import Image  # type: ignore

        img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
        quality = 90
        while quality >= 40:
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=quality)
            if buf.tell() <= max_size:
                return buf.getvalue()
            quality -= 10

        # Last resort: resize
        scale = 0.7
        while scale > 0.3:
            new_size = (int(img.width * scale), int(img.height * scale))
            resized = img.resize(new_size)
            buf = io.BytesIO()
            resized.save(buf, format="JPEG", quality=60)
            if buf.tell() <= max_size:
                return buf.getvalue()
            scale -= 0.15

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=40)
        return buf.getvalue()

    except Exception:
        return png_bytes

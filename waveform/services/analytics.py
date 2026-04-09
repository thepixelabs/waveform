"""
analytics.py — PostHog analytics service.

All events described in epic §9.  Instrumentation is opt-in; the enabled flag
is set via set_enabled() after consent.

Privacy: no PII is collected.  Track names are NOT sent unless the user opts
into "help improve suggestions" (not yet implemented).  The distinct_id is a
random UUID stored in settings.json; it never maps to a real-world identity.
"""
from __future__ import annotations

import dataclasses
import threading
import time
from typing import Any, Dict, List, Optional


@dataclasses.dataclass
class SessionMetrics:
    """Within-session accumulator for key funnel metrics."""

    songs_suggested: int = 0
    songs_kept: int = 0
    songs_skipped: int = 0
    songs_vetoed: int = 0
    previews_played: int = 0
    preview_seconds_played: float = 0.0

    @property
    def preview_to_keep_rate(self) -> float:
        if self.previews_played == 0:
            return 0.0
        return self.songs_kept / self.previews_played

    @property
    def veto_depth(self) -> float:
        if self.songs_kept == 0:
            return 0.0
        return self.songs_vetoed / self.songs_kept

    def as_dict(self) -> Dict[str, Any]:
        return {
            "songs_suggested": self.songs_suggested,
            "songs_kept": self.songs_kept,
            "songs_skipped": self.songs_skipped,
            "songs_vetoed": self.songs_vetoed,
            "previews_played": self.previews_played,
            "preview_seconds_played": round(self.preview_seconds_played, 1),
            "preview_to_keep_rate": round(self.preview_to_keep_rate, 3),
            "veto_depth": round(self.veto_depth, 3),
        }


class AnalyticsService:
    """Real PostHog wrapper.  Captures are fire-and-forget on daemon threads."""

    def __init__(
        self,
        api_key: str = "",
        distinct_id: str = "",
        enabled: bool = False,
    ) -> None:
        self._api_key = api_key
        self._distinct_id = distinct_id
        self._enabled = enabled
        self._ph: Optional[Any] = None
        self._lock = threading.Lock()

        if api_key:
            self._init_posthog()

    def _init_posthog(self) -> None:
        try:
            import posthog  # type: ignore

            posthog.project_api_key = self._api_key
            posthog.host = "https://app.posthog.com"
            self._ph = posthog
        except ImportError:
            pass

    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            self._enabled = enabled

    def _capture(self, event: str, properties: Dict[str, Any]) -> None:
        if not self._enabled or self._ph is None:
            return
        distinct_id = self._distinct_id

        def _do() -> None:
            try:
                self._ph.capture(distinct_id, event, properties)
            except Exception:
                pass

        t = threading.Thread(target=_do, daemon=True)
        t.start()

    # --- All typed event methods (epic §9) ---

    def app_opened(self) -> None:
        self._capture("app_opened", {})

    def session_started(self, event_type: str = "") -> None:
        self._capture("session_started", {"event_type": event_type})

    def event_template_selected(self, template_id: str, has_vibe_text: bool = False) -> None:
        self._capture("event_template_selected", {
            "template_id": template_id,
            "has_vibe_text": has_vibe_text,
        })

    def block_added(self, archetype: str = "") -> None:
        self._capture("block_added", {"archetype": archetype})

    def block_removed(self, archetype: str = "") -> None:
        self._capture("block_removed", {"archetype": archetype})

    def block_resized(self, archetype: str = "", new_duration: int = 0) -> None:
        self._capture("block_resized", {"archetype": archetype, "new_duration": new_duration})

    def block_reordered(self) -> None:
        self._capture("block_reordered", {})

    def genre_weight_changed(self, block_id: str, tag: str, weight: float) -> None:
        self._capture("genre_weight_changed", {
            "block_id": block_id,
            "tag": tag,
            "weight": round(weight, 2),
        })

    def generation_requested(self, block_id: str, n_existing_vetoes: int = 0) -> None:
        self._capture("generation_requested", {
            "block_id": block_id,
            "n_existing_vetoes": n_existing_vetoes,
        })

    def generation_completed(self, block_id: str, latency_ms: int = 0, n_songs_returned: int = 0) -> None:
        self._capture("generation_completed", {
            "block_id": block_id,
            "latency_ms": latency_ms,
            "n_songs_returned": n_songs_returned,
        })

    def song_suggested(self, track_id: str, block_id: str, position: int = 0) -> None:
        self._capture("song_suggested", {
            "track_id": track_id,
            "block_id": block_id,
            "position": position,
        })

    def song_previewed(self, track_id: str, block_id: str, preview_duration_played: int = 0) -> None:
        self._capture("song_previewed", {
            "track_id": track_id,
            "block_id": block_id,
            "preview_duration_played": preview_duration_played,
        })

    def song_kept(self, track_id: str = "", block_id: str = "") -> None:
        self._capture("song_kept", {"track_id": track_id, "block_id": block_id})

    def song_skipped(self, track_id: str = "", block_id: str = "") -> None:
        self._capture("song_skipped", {"track_id": track_id, "block_id": block_id})

    def song_vetoed(
        self,
        track_id: str = "",
        block_id: str = "",
        reason_tag: Optional[str] = None,
    ) -> None:
        self._capture("song_vetoed", {
            "track_id": track_id,
            "block_id": block_id,
            "reason_tag": reason_tag or "",
        })

    def swap_requested(self, block_id: str = "") -> None:
        self._capture("swap_requested", {"block_id": block_id})

    def playlist_exported(
        self,
        n_blocks: int = 0,
        n_tracks: int = 0,
        time_from_open_ms: int = 0,
        event_type: str = "",
        metrics: Optional[SessionMetrics] = None,
    ) -> None:
        props: Dict[str, Any] = {
            "n_blocks": n_blocks,
            "n_tracks": n_tracks,
            "time_from_open_ms": time_from_open_ms,
            "event_type": event_type,
        }
        if metrics is not None:
            props.update(metrics.as_dict())
        self._capture("playlist_exported", props)

    def session_abandoned(self, last_step_reached: str = "") -> None:
        self._capture("session_abandoned", {"last_step_reached": last_step_reached})

    def error_surfaced(self, source: str = "", error_type: str = "") -> None:
        self._capture("error_surfaced", {"source": source, "type": error_type})

    def shutdown(self) -> None:
        if self._ph is not None:
            try:
                self._ph.shutdown()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Fake for tests
# ---------------------------------------------------------------------------

class FakeAnalyticsService:
    """Synchronous, always-enabled, records events to self.events list."""

    def __init__(self) -> None:
        self.events: List[Dict[str, Any]] = []
        self._enabled = True

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled

    def _record(self, event: str, properties: Dict[str, Any]) -> None:
        if self._enabled:
            self.events.append({"event": event, **properties})

    def app_opened(self) -> None:
        self._record("app_opened", {})

    def session_started(self, event_type: str = "") -> None:
        self._record("session_started", {"event_type": event_type})

    def event_template_selected(self, template_id: str, has_vibe_text: bool = False) -> None:
        self._record("event_template_selected", {"template_id": template_id, "has_vibe_text": has_vibe_text})

    def block_added(self, archetype: str = "") -> None:
        self._record("block_added", {"archetype": archetype})

    def block_removed(self, archetype: str = "") -> None:
        self._record("block_removed", {"archetype": archetype})

    def block_resized(self, archetype: str = "", new_duration: int = 0) -> None:
        self._record("block_resized", {"archetype": archetype, "new_duration": new_duration})

    def block_reordered(self) -> None:
        self._record("block_reordered", {})

    def genre_weight_changed(self, block_id: str, tag: str, weight: float) -> None:
        self._record("genre_weight_changed", {"block_id": block_id, "tag": tag, "weight": weight})

    def generation_requested(self, block_id: str, n_existing_vetoes: int = 0) -> None:
        self._record("generation_requested", {"block_id": block_id, "n_existing_vetoes": n_existing_vetoes})

    def generation_completed(self, block_id: str, latency_ms: int = 0, n_songs_returned: int = 0) -> None:
        self._record("generation_completed", {"block_id": block_id, "latency_ms": latency_ms, "n_songs_returned": n_songs_returned})

    def song_suggested(self, track_id: str, block_id: str, position: int = 0) -> None:
        self._record("song_suggested", {"track_id": track_id, "block_id": block_id, "position": position})

    def song_previewed(self, track_id: str, block_id: str, preview_duration_played: int = 0) -> None:
        self._record("song_previewed", {"track_id": track_id, "block_id": block_id, "preview_duration_played": preview_duration_played})

    def song_kept(self, track_id: str = "", block_id: str = "") -> None:
        self._record("song_kept", {"track_id": track_id, "block_id": block_id})

    def song_skipped(self, track_id: str = "", block_id: str = "") -> None:
        self._record("song_skipped", {"track_id": track_id, "block_id": block_id})

    def song_vetoed(self, track_id: str = "", block_id: str = "", reason_tag: Optional[str] = None) -> None:
        self._record("song_vetoed", {"track_id": track_id, "block_id": block_id, "reason_tag": reason_tag or ""})

    def swap_requested(self, block_id: str = "") -> None:
        self._record("swap_requested", {"block_id": block_id})

    def playlist_exported(self, n_blocks: int = 0, n_tracks: int = 0, time_from_open_ms: int = 0, event_type: str = "", metrics: Optional[SessionMetrics] = None) -> None:
        props: Dict[str, Any] = {"n_blocks": n_blocks, "n_tracks": n_tracks, "time_from_open_ms": time_from_open_ms, "event_type": event_type}
        if metrics is not None:
            props.update(metrics.as_dict())
        self._record("playlist_exported", props)

    def session_abandoned(self, last_step_reached: str = "") -> None:
        self._record("session_abandoned", {"last_step_reached": last_step_reached})

    def error_surfaced(self, source: str = "", error_type: str = "") -> None:
        self._record("error_surfaced", {"source": source, "type": error_type})

    def shutdown(self) -> None:
        pass

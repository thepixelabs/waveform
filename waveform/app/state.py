"""
state.py — Observable app state store.

StateStore: a simple callback dict on a lock.  UI widgets subscribe to keys
and are notified synchronously when a value changes.  No external reactive
library required.

All long-running operations run on thread pool threads; they call
store.set() which is thread-safe.  The UI must dispatch any Tk operations
to the main thread via widget.after(0, callback).
"""
from __future__ import annotations

import enum
import threading
from typing import Any, Callable, Dict, List, Optional


class AppScreen(enum.Enum):
    WELCOME = "welcome"
    EVENT_SETUP = "event_setup"
    TIMELINE = "timeline"
    SETTINGS = "settings"
    GENERATION = "generation"
    REVIEW = "review"
    EXPORT = "export"


class StateStore:
    """Thread-safe key-value store with subscription callbacks."""

    def __init__(self) -> None:
        self._data: Dict[str, Any] = {}
        self._subscribers: Dict[str, List[Callable[[Any], None]]] = {}
        self._lock = threading.Lock()

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = value
            callbacks = list(self._subscribers.get(key, []))
        for cb in callbacks:
            try:
                cb(value)
            except Exception:
                pass

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._data.get(key, default)

    def subscribe(self, key: str, callback: Callable[[Any], None]) -> None:
        with self._lock:
            self._subscribers.setdefault(key, []).append(callback)

    def unsubscribe(self, key: str, callback: Callable[[Any], None]) -> None:
        with self._lock:
            subs = self._subscribers.get(key, [])
            if callback in subs:
                subs.remove(callback)


class AppState:
    """Named accessor constants — use these as store keys."""

    SESSION = "session"
    SELECTED_TEMPLATE = "selected_template"
    CURRENT_SCREEN = "current_screen"
    IS_GENERATING = "is_generating"
    SETTINGS = "settings"
    TOAST = "toast"

    # Phase 6
    PENDING_SONG = "pending_song"
    SUGGESTION_FEED = "suggestion_feed"
    GENERATION_COMPLETE = "generation_complete"
    GENERATION_STATUS = "generation_status"
    GENERATION_CONTROLLER = "generation_controller"

    # Phase 7
    APPROVED_SONGS = "approved_songs"
    SELECTED_BLOCK_ID = "selected_block_id"

    # Phase 10
    EXPORT_COMPLETED = "export_completed"

    # Phase 2B
    CUSTOM_ARCHETYPES_UPDATED = "custom_archetypes_updated"

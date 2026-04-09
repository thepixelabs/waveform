"""
persistence.py — settings, session history, song history, prompt management.

PersistenceService: real filesystem persistence under ~/.waveform/
FakePersistenceService: in-memory test double
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Default settings schema
# ---------------------------------------------------------------------------

DEFAULT_SETTINGS: Dict[str, Any] = {
    "schema_version": 2,
    "theme": "dark",
    "reduce_motion": False,
    "analytics_enabled": False,  # opt-in
    "analytics_id": "",
    "gemini_model": "gemini-2.5-flash",
    "tracks_per_hour": 16,
    "allow_repeats": False,
    "shuffle_within_blocks": False,
    "block_genre_overrides": {},
}

_WAVEFORM_DIR = Path.home() / ".waveform"
_SESSIONS_DIR = _WAVEFORM_DIR / "sessions"


# ---------------------------------------------------------------------------
# V1 migration helpers
# ---------------------------------------------------------------------------

def _is_v1_schema(settings: dict) -> bool:
    return (
        "psytrance_enabled" in settings
        or "psytrance_pct" in settings
        or "psytrance_count" in settings
    )


def migrate_v1_settings(v1: dict) -> dict:
    """Convert a v1 psytrance settings dict to v2 genre weight schema."""
    v2 = {k: v for k, v in v1.items() if k not in ("psytrance_enabled", "psytrance_pct", "psytrance_count")}
    v2["schema_version"] = 2

    pct_raw = v1.get("psytrance_pct", 0)
    enabled = v1.get("psytrance_enabled", False)

    if enabled and pct_raw:
        weight = min(float(pct_raw) / 100.0, 0.8)
        v2.setdefault("block_genre_overrides", {})
        v2["block_genre_overrides"]["dance"] = [{"tag": "psytrance", "weight": weight}]
        v2["block_genre_overrides"]["groove"] = [{"tag": "psytrance", "weight": weight}]

    return v2


# ---------------------------------------------------------------------------
# Real persistence service
# ---------------------------------------------------------------------------

class PersistenceService:
    def __init__(self, base_dir: Path | None = None) -> None:
        self._base = base_dir or _WAVEFORM_DIR
        self._sessions = self._base / "sessions"
        self._base.mkdir(parents=True, exist_ok=True)
        self._sessions.mkdir(parents=True, exist_ok=True)

    # --- Settings ---

    def load_settings(self) -> dict:
        path = self._base / "settings.json"
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if _is_v1_schema(data):
                    data = migrate_v1_settings(data)
                    self._write_json(path, data)
                return {**DEFAULT_SETTINGS, **data}
            except Exception:
                pass
        return dict(DEFAULT_SETTINGS)

    def save_settings(self, settings: dict) -> None:
        self._write_json(self._base / "settings.json", settings)

    # --- Session history ---

    def list_sessions(self) -> List[str]:
        """Return session IDs sorted newest-first by file mtime."""
        paths = sorted(
            self._sessions.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        return [p.stem for p in paths]

    def load_session(self, session_id: str) -> Optional[dict]:
        path = self._sessions / f"{session_id}.json"
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return None
        return None

    def save_session(self, session_id: str, data: dict) -> None:
        self._sessions.mkdir(parents=True, exist_ok=True)
        self._write_json(self._sessions / f"{session_id}.json", data)

    def delete_session(self, session_id: str) -> bool:
        path = self._sessions / f"{session_id}.json"
        if path.exists():
            path.unlink()
            return True
        return False

    def clear_all_sessions(self) -> None:
        for p in self._sessions.glob("*.json"):
            p.unlink()

    # --- Song history (duplicate detection) ---

    def _song_history_path(self) -> Path:
        return self._base / "song_history.json"

    def load_song_history(self) -> Dict[str, bool]:
        path = self._song_history_path()
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def mark_used(self, title: str, artist: str) -> None:
        history = self.load_song_history()
        key = f"{title.lower().strip()}||{artist.lower().strip()}"
        history[key] = True
        self._write_json(self._song_history_path(), history)

    def get_used_keys(self) -> Dict[str, bool]:
        return self.load_song_history()

    def clear_song_history(self) -> None:
        self._write_json(self._song_history_path(), {})

    # --- Master prompt ---

    def load_master_prompt(self, fallback_path: str | None = None) -> str:
        path = self._base / "master_prompt.md"
        if path.exists():
            try:
                return path.read_text(encoding="utf-8")
            except Exception:
                pass
        if fallback_path:
            try:
                return Path(fallback_path).read_text(encoding="utf-8")
            except Exception:
                pass
        return ""

    def save_master_prompt(self, text: str) -> None:
        path = self._base / "master_prompt.md"
        path.write_text(text, encoding="utf-8")

    # --- Custom templates (Phase 2C) ---

    def load_custom_templates(self) -> List[Dict]:
        path = self._base / "custom_templates.json"
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return []
        return []

    def save_custom_template(self, template_data: dict) -> None:
        templates = self.load_custom_templates()
        tid = template_data.get("id", str(uuid.uuid4()))
        template_data["id"] = tid
        existing = [t for t in templates if t.get("id") != tid]
        existing.append(template_data)
        self._write_json(self._base / "custom_templates.json", existing)

    def delete_custom_template(self, template_id: str) -> bool:
        templates = self.load_custom_templates()
        filtered = [t for t in templates if t.get("id") != template_id]
        if len(filtered) == len(templates):
            return False
        self._write_json(self._base / "custom_templates.json", filtered)
        return True

    # --- Custom archetypes (Phase 2B) ---

    def load_custom_archetypes(self) -> List[Dict]:
        path = self._base / "custom_archetypes.json"
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return []
        return []

    def save_custom_archetypes(self, archetypes: List[Dict]) -> None:
        self._write_json(self._base / "custom_archetypes.json", archetypes)

    # --- V1 migration ---

    @staticmethod
    def _rename_to_bak(path: Path) -> None:
        bak = path.with_suffix(".bak")
        path.rename(bak)

    def migrate_v1_if_needed(self) -> bool:
        """Scan known v1 paths and migrate to ~/.waveform/ if found. Returns True if migrated."""
        # Typical v1 location: project root (cwd at time of v1 install)
        migrated = False
        v1_candidates = [
            Path.cwd() / "settings.json",
            Path.home() / "settings.json",
        ]
        for candidate in v1_candidates:
            if not candidate.exists():
                continue
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
                if _is_v1_schema(data):
                    migrated_data = migrate_v1_settings(data)
                    self.save_settings(migrated_data)
                    self._rename_to_bak(candidate)
                    migrated = True
            except Exception:
                pass

        # Migrate v1 song history
        v1_history = Path.cwd() / "song_history.json"
        if v1_history.exists():
            try:
                dest = self._song_history_path()
                if not dest.exists():
                    shutil.copy2(v1_history, dest)
                self._rename_to_bak(v1_history)
                migrated = True
            except Exception:
                pass

        return migrated

    # --- Internal ---

    def _write_json(self, path: Path, data: Any) -> None:
        """Atomic write via tmp → rename to avoid partial reads."""
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            Path(tmp).replace(path)
        except Exception:
            try:
                os.unlink(tmp)
            except Exception:
                pass
            raise


# ---------------------------------------------------------------------------
# Fake (in-memory) for tests
# ---------------------------------------------------------------------------

class FakePersistenceService:
    def __init__(self) -> None:
        self._settings: dict = dict(DEFAULT_SETTINGS)
        self._sessions: Dict[str, dict] = {}
        self._song_history: Dict[str, bool] = {}
        self._master_prompt: str = ""
        self._custom_templates: List[Dict] = []
        self._custom_archetypes: List[Dict] = []

    def load_settings(self) -> dict:
        return dict(self._settings)

    def save_settings(self, settings: dict) -> None:
        self._settings = dict(settings)

    def list_sessions(self) -> List[str]:
        return list(self._sessions.keys())

    def load_session(self, session_id: str) -> Optional[dict]:
        return self._sessions.get(session_id)

    def save_session(self, session_id: str, data: dict) -> None:
        self._sessions[session_id] = data

    def delete_session(self, session_id: str) -> bool:
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    def clear_all_sessions(self) -> None:
        self._sessions.clear()

    def load_song_history(self) -> Dict[str, bool]:
        return dict(self._song_history)

    def mark_used(self, title: str, artist: str) -> None:
        key = f"{title.lower().strip()}||{artist.lower().strip()}"
        self._song_history[key] = True

    def get_used_keys(self) -> Dict[str, bool]:
        return dict(self._song_history)

    def clear_song_history(self) -> None:
        self._song_history.clear()

    def load_master_prompt(self, fallback_path: str | None = None) -> str:
        if self._master_prompt:
            return self._master_prompt
        if fallback_path:
            try:
                return Path(fallback_path).read_text(encoding="utf-8")
            except Exception:
                pass
        return ""

    def save_master_prompt(self, text: str) -> None:
        self._master_prompt = text

    def load_custom_templates(self) -> List[Dict]:
        return list(self._custom_templates)

    def save_custom_template(self, template_data: dict) -> None:
        tid = template_data.get("id", str(uuid.uuid4()))
        template_data["id"] = tid
        self._custom_templates = [t for t in self._custom_templates if t.get("id") != tid]
        self._custom_templates.append(template_data)

    def delete_custom_template(self, template_id: str) -> bool:
        before = len(self._custom_templates)
        self._custom_templates = [t for t in self._custom_templates if t.get("id") != template_id]
        return len(self._custom_templates) < before

    def load_custom_archetypes(self) -> List[Dict]:
        return list(self._custom_archetypes)

    def save_custom_archetypes(self, archetypes: List[Dict]) -> None:
        self._custom_archetypes = list(archetypes)

    def migrate_v1_if_needed(self) -> bool:
        return False

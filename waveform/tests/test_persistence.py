"""
test_persistence.py — Tests for PersistenceService and V1 migration.
"""
import pytest
import tempfile
from pathlib import Path

from waveform.services.persistence import (
    DEFAULT_SETTINGS,
    FakePersistenceService,
    PersistenceService,
    _is_v1_schema,
    migrate_v1_settings,
)


class TestV1SchemaDetection:
    def test_detects_psytrance_enabled(self) -> None:
        assert _is_v1_schema({"psytrance_enabled": True})

    def test_detects_psytrance_pct(self) -> None:
        assert _is_v1_schema({"psytrance_pct": 40})

    def test_detects_psytrance_count(self) -> None:
        assert _is_v1_schema({"psytrance_count": 3})

    def test_clean_v2_schema_not_detected(self) -> None:
        assert not _is_v1_schema({"schema_version": 2, "theme": "dark"})

    def test_empty_dict_not_detected(self) -> None:
        assert not _is_v1_schema({})


class TestV1Migration:
    def test_psytrance_enabled_converts(self) -> None:
        v1 = {"psytrance_enabled": True, "psytrance_pct": 60, "psytrance_count": 5, "theme": "dark"}
        v2 = migrate_v1_settings(v1)
        assert v2["schema_version"] == 2
        assert "psytrance_enabled" not in v2
        assert "psytrance_pct" not in v2
        assert "psytrance_count" not in v2
        assert "theme" in v2  # non-psytrance keys preserved
        overrides = v2.get("block_genre_overrides", {})
        assert "dance" in overrides or "groove" in overrides

    def test_psytrance_disabled_no_overrides(self) -> None:
        v1 = {"psytrance_enabled": False, "psytrance_pct": 50, "psytrance_count": 5}
        v2 = migrate_v1_settings(v1)
        assert v2.get("block_genre_overrides", {}) == {}

    def test_weight_capped_at_80(self) -> None:
        v1 = {"psytrance_enabled": True, "psytrance_pct": 100}
        v2 = migrate_v1_settings(v1)
        overrides = v2.get("block_genre_overrides", {})
        for block_key in overrides.values():
            for gw in block_key:
                assert gw["weight"] <= 0.8

    def test_non_psytrance_keys_preserved(self) -> None:
        v1 = {"psytrance_enabled": False, "gemini_model": "gemini-2.5-flash", "custom_key": "value"}
        v2 = migrate_v1_settings(v1)
        assert v2["gemini_model"] == "gemini-2.5-flash"
        assert v2["custom_key"] == "value"


class TestFakePersistenceService:
    def test_settings_roundtrip(self) -> None:
        svc = FakePersistenceService()
        settings = svc.load_settings()
        settings["gemini_model"] = "test-model"
        svc.save_settings(settings)
        loaded = svc.load_settings()
        assert loaded["gemini_model"] == "test-model"

    def test_session_roundtrip(self) -> None:
        svc = FakePersistenceService()
        data = {"event_name": "Test Party", "blocks": []}
        svc.save_session("sess-1", data)
        assert "sess-1" in svc.list_sessions()
        loaded = svc.load_session("sess-1")
        assert loaded["event_name"] == "Test Party"

    def test_delete_session(self) -> None:
        svc = FakePersistenceService()
        svc.save_session("s1", {})
        assert svc.delete_session("s1") is True
        assert svc.load_session("s1") is None

    def test_delete_nonexistent_returns_false(self) -> None:
        svc = FakePersistenceService()
        assert svc.delete_session("nonexistent") is False

    def test_mark_used_and_get_used_keys(self) -> None:
        svc = FakePersistenceService()
        svc.mark_used("Blue", "A-Ha")
        keys = svc.get_used_keys()
        assert "blue||a-ha" in keys

    def test_clear_song_history(self) -> None:
        svc = FakePersistenceService()
        svc.mark_used("Song", "Artist")
        svc.clear_song_history()
        assert not svc.get_used_keys()

    def test_master_prompt_roundtrip(self) -> None:
        svc = FakePersistenceService()
        svc.save_master_prompt("my custom prompt")
        assert svc.load_master_prompt() == "my custom prompt"

    def test_custom_templates_roundtrip(self) -> None:
        svc = FakePersistenceService()
        tpl = {"id": "t1", "name": "My Template"}
        svc.save_custom_template(tpl)
        loaded = svc.load_custom_templates()
        assert any(t["id"] == "t1" for t in loaded)

    def test_delete_custom_template(self) -> None:
        svc = FakePersistenceService()
        svc.save_custom_template({"id": "t1", "name": "X"})
        assert svc.delete_custom_template("t1") is True
        assert not any(t["id"] == "t1" for t in svc.load_custom_templates())

    def test_custom_archetypes_roundtrip(self) -> None:
        svc = FakePersistenceService()
        archetypes = [{"id": "custom_abc", "name": "Test", "emoji": "🎵", "description": "", "palette_start": "#000", "palette_end": "#FFF", "energy": 3}]
        svc.save_custom_archetypes(archetypes)
        loaded = svc.load_custom_archetypes()
        assert len(loaded) == 1
        assert loaded[0]["id"] == "custom_abc"

    def test_migrate_v1_noop(self) -> None:
        svc = FakePersistenceService()
        assert svc.migrate_v1_if_needed() is False


class TestRealPersistenceService:
    def test_settings_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            svc = PersistenceService(base_dir=Path(tmp))
            settings = svc.load_settings()
            settings["gemini_model"] = "test-model-real"
            svc.save_settings(settings)
            loaded = svc.load_settings()
            assert loaded["gemini_model"] == "test-model-real"

    def test_session_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            svc = PersistenceService(base_dir=Path(tmp))
            svc.save_session("s1", {"event_name": "Real Test"})
            assert "s1" in svc.list_sessions()
            data = svc.load_session("s1")
            assert data["event_name"] == "Real Test"

    def test_clear_all_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            svc = PersistenceService(base_dir=Path(tmp))
            svc.save_session("s1", {})
            svc.save_session("s2", {})
            svc.clear_all_sessions()
            assert svc.list_sessions() == []

    def test_v1_schema_auto_migrated_on_load(self) -> None:
        import json
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            settings_path = p / "settings.json"
            v1 = {"psytrance_enabled": True, "psytrance_pct": 50, "psytrance_count": 3}
            settings_path.write_text(json.dumps(v1))
            svc = PersistenceService(base_dir=p)
            loaded = svc.load_settings()
            assert loaded["schema_version"] == 2
            assert "psytrance_enabled" not in loaded

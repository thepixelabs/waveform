"""
main.py — Waveform v2 application entry point.

Boots the service layer, initialises the state store, launches the UI.
"""
from __future__ import annotations

import os
import time
import uuid
from pathlib import Path
from typing import Any


def run() -> None:
    """Primary entry point.  Called from __main__.py and from pyproject.toml."""
    _app_open_time = int(time.time() * 1000)

    # --- Load settings and set up persistence ---
    from waveform.services.persistence import PersistenceService

    persistence = PersistenceService()
    try:
        persistence.migrate_v1_if_needed()
    except Exception:
        pass

    settings = persistence.load_settings()

    # --- Analytics ---
    analytics = _build_analytics_service(settings, persistence)

    # --- State store ---
    from waveform.app.state import AppState, AppScreen, StateStore

    store = StateStore()
    store.set(AppState.SETTINGS, settings)
    store.set(AppState.CURRENT_SCREEN, AppScreen.EVENT_SETUP)

    # --- Spotify client ---
    from waveform.services.spotify_client import FakeSpotifyClient, SpotifyClient

    spotify_client_id = os.environ.get("SPOTIFY_CLIENT_ID", "")
    spotify_client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET", "")
    spotify_redirect = os.environ.get("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback/")

    if spotify_client_id and spotify_client_secret:
        spotify = SpotifyClient(
            client_id=spotify_client_id,
            client_secret=spotify_client_secret,
            redirect_uri=spotify_redirect,
        )
    else:
        spotify = FakeSpotifyClient()  # type: ignore

    # --- Gemini client ---
    from waveform.services.gemini_client import FakeGeminiClient, GeminiClient

    gemini_api_key = os.environ.get("GOOGLE_GENERATIVE_AI_API_KEY", "")
    gemini_model = settings.get("gemini_model", "gemini-2.5-flash")

    prompts_dir = Path(__file__).parent.parent / "prompts"
    master_prompt_path = str(prompts_dir / "master_prompt.md")

    if gemini_api_key:
        gemini = GeminiClient(
            api_key=gemini_api_key,
            model=gemini_model,
            master_prompt_path=master_prompt_path,
        )
    else:
        gemini = FakeGeminiClient()  # type: ignore

    # --- Audio player ---
    from waveform.services.preview_audio import PreviewAudioPlayer

    try:
        audio_player = PreviewAudioPlayer(strategy="pygame")
    except Exception:
        from waveform.services.preview_audio import FakePreviewAudioPlayer
        audio_player = FakePreviewAudioPlayer()  # type: ignore

    # --- Generation controller ---
    from waveform.app.generation import GenerationController

    try:
        gen_controller = GenerationController(
            store=store,
            gemini_client=gemini,
            spotify_client=spotify,
            persistence=persistence,
            analytics=analytics,
        )
    except Exception:
        gen_controller = None  # type: ignore

    # --- Cover art ---
    from waveform.services import cover_art as cover_art_module

    # --- Export controller ---
    from waveform.app.export import ExportController

    export_controller = ExportController(
        store=store,
        spotify_client=spotify,
        cover_art_service=cover_art_module,
        persistence=persistence,
        analytics=analytics,
    )

    # --- Custom archetypes ---
    try:
        from waveform.domain.block import CustomArchetype, register_custom_archetypes
        raw = persistence.load_custom_archetypes()
        register_custom_archetypes([CustomArchetype.from_dict(d) for d in raw])
    except Exception:
        pass

    # --- UI ---
    import customtkinter as ctk  # type: ignore

    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")

    from waveform.ui.shell import WaveformApp

    app = WaveformApp(
        store=store,
        analytics=analytics,
        audio_player=audio_player,
        spotify_client=spotify,
        generation_controller=gen_controller,
        export_controller=export_controller,
        persistence=persistence,
    )

    # --- WM_DELETE_WINDOW: analytics + audio cleanup ---
    def _on_close() -> None:
        try:
            analytics.session_abandoned(last_step_reached=str(store.get(AppState.CURRENT_SCREEN, "")))
        except Exception:
            pass
        try:
            audio_player.stop()
        except Exception:
            pass
        try:
            analytics.shutdown()
        except Exception:
            pass
        app.destroy()

    app.protocol("WM_DELETE_WINDOW", _on_close)

    # --- Analytics consent (shown 500ms after mainloop) ---
    def _show_consent() -> None:
        analytics_id = settings.get("analytics_id", "")
        if not analytics_id and not settings.get("analytics_enabled", False):
            try:
                from waveform.ui.analytics_consent import AnalyticsConsentDialog
                AnalyticsConsentDialog(
                    parent=app,
                    on_consent=lambda enabled: _handle_consent(enabled),
                )
            except Exception:
                pass

    def _handle_consent(enabled: bool) -> None:
        analytics.set_enabled(enabled)
        settings["analytics_enabled"] = enabled
        if enabled:
            analytics.app_opened()
        persistence.save_settings(settings)
        store.set(AppState.SETTINGS, settings)

    # Export completed hook for analytics
    def _on_export_completed(_val: Any) -> None:
        pass  # placeholder; analytics already instrumented in ExportController

    store.subscribe(AppState.EXPORT_COMPLETED, _on_export_completed)

    app.after(500, _show_consent)
    app.mainloop()


def _build_analytics_service(settings: dict, persistence: Any) -> Any:
    from waveform.services.analytics import AnalyticsService

    analytics_id = settings.get("analytics_id", "")
    if not analytics_id:
        analytics_id = str(uuid.uuid4())
        settings["analytics_id"] = analytics_id
        try:
            persistence.save_settings(settings)
        except Exception:
            pass

    posthog_key = os.environ.get("POSTHOG_API_KEY", "")
    enabled = settings.get("analytics_enabled", False)

    return AnalyticsService(
        api_key=posthog_key,
        distinct_id=analytics_id,
        enabled=enabled,
    )

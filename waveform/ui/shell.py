"""
shell.py — WaveformApp: the three-column CTk shell.

Top bar: WaveformAnim logo + wordmark | event name (clickable) | utility buttons | Build button.
Left: ScheduleSidebar (280px).
Centre: TimelineCanvas (flex).
Right: TrackPanel (360px).

Phase 11: Event Skin Change tween, Build button multi-block fix, session resume.
Phase 2A: session resume via PlaylistSession.from_dict, fork session.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

try:
    import customtkinter as ctk  # type: ignore
    HAS_CTK = True
except ImportError:
    HAS_CTK = False

from waveform.app.state import AppScreen, AppState, StateStore
from waveform.ui import theme
from waveform.ui.widgets.waveform_anim import WaveformAnim


class WaveformApp(ctk.CTk if HAS_CTK else object):  # type: ignore
    def __init__(
        self,
        store: StateStore,
        analytics: Any = None,
        audio_player: Any = None,
        spotify_client: Any = None,
        generation_controller: Any = None,
        export_controller: Any = None,
        persistence: Any = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._store = store
        self._analytics = analytics
        self._audio = audio_player
        self._spotify = spotify_client
        self._generation_controller = generation_controller
        self._export_controller = export_controller
        self._persistence = persistence
        self._app_open_time_ms = int(time.time() * 1000)
        self._current_accent = theme.ACCENT_VIOLET
        self._tween_after_id: Optional[str] = None
        self._generating_block_count = 0
        self._toast_after_id: Optional[str] = None

        self.title("Waveform")
        self.geometry(f"{theme.MIN_WINDOW_WIDTH}x{theme.MIN_WINDOW_HEIGHT}")
        self.minsize(theme.MIN_WINDOW_WIDTH, theme.MIN_WINDOW_HEIGHT)
        self.configure(fg_color=theme.BG_BASE)

        self._build_top_bar()
        self._build_main_area()
        self._build_screens()

        # Subscribe
        store.subscribe(AppState.CURRENT_SCREEN, lambda v: self.after(0, lambda: self._navigate_to(v)))
        store.subscribe(AppState.SESSION, lambda v: self.after(0, lambda: self._on_session_changed(v)))
        store.subscribe(AppState.SELECTED_TEMPLATE, lambda v: self.after(0, lambda: self._on_template_changed(v)))
        store.subscribe(AppState.GENERATION_STATUS, lambda v: self.after(0, lambda: self._on_generation_status(v)))
        store.subscribe(AppState.TOAST, lambda v: self.after(0, lambda: self._on_toast(v)))
        store.subscribe(AppState.APPROVED_SONGS, lambda v: self.after(0, lambda: self._on_approved_songs_changed(v)))
        store.subscribe(AppState.SESSION, lambda v: self.after(0, lambda: self._on_session_changed_for_counter(v)))

        # Initial navigation
        initial = store.get(AppState.CURRENT_SCREEN) or AppScreen.EVENT_SETUP
        self._navigate_to(initial)

    def _build_top_bar(self) -> None:
        bar = ctk.CTkFrame(self, height=theme.TOP_BAR_HEIGHT, fg_color=theme.BG_SURFACE)
        bar.pack(fill="x", side="top")
        bar.pack_propagate(False)

        # Logo + wordmark
        logo_frame = ctk.CTkFrame(bar, fg_color="transparent")
        logo_frame.pack(side="left", padx=theme.SP_4)

        WaveformAnim(logo_frame, width=36, height=28, animate=True, store=self._store).pack(side="left", padx=(0, theme.SP_2))

        ctk.CTkLabel(
            logo_frame,
            text="Waveform",
            font=(theme.FONT_UI, theme.TEXT_MD, "bold"),
            text_color=theme.BRAND_GRADIENT_MID,
        ).pack(side="left")

        # Event name (clickable → EVENT_SETUP)
        self._event_name_label = ctk.CTkLabel(
            bar,
            text="New Event",
            font=(theme.FONT_UI, theme.TEXT_SM),
            text_color=theme.TEXT_SECONDARY,
            cursor="hand2",
        )
        self._event_name_label.pack(side="left", padx=theme.SP_4)
        self._event_name_label.bind(
            "<Button-1>",
            lambda e: self._store.set(AppState.CURRENT_SCREEN, AppScreen.EVENT_SETUP),
        )

        # Utility buttons (right side) — Export hidden initially
        util_frame = ctk.CTkFrame(bar, fg_color="transparent")
        util_frame.pack(side="right", padx=theme.SP_4)

        self._export_btn = ctk.CTkButton(
            util_frame,
            text="Export",
            font=(theme.FONT_UI, theme.TEXT_XS),
            fg_color=theme.SUCCESS_GREEN,
            text_color=theme.BG_BASE,
            width=80,
            height=32,
            command=self._on_export_click,
        )
        self._export_btn.pack(side="right", padx=(theme.SP_2, 0))
        self._export_btn.pack_forget()  # hidden until approved songs exist

        ctk.CTkButton(
            util_frame,
            text="History",
            font=(theme.FONT_UI, theme.TEXT_XS),
            fg_color=theme.BG_OVERLAY,
            width=70,
            height=32,
            command=self._on_history_click,
        ).pack(side="right", padx=(theme.SP_2, 0))

        ctk.CTkButton(
            util_frame,
            text="Settings",
            font=(theme.FONT_UI, theme.TEXT_XS),
            fg_color=theme.BG_OVERLAY,
            width=70,
            height=32,
            command=self._on_settings_click,
        ).pack(side="right", padx=(theme.SP_2, 0))

        # Build button
        self._build_btn = ctk.CTkButton(
            util_frame,
            text="▶ Build",
            font=(theme.FONT_UI, theme.TEXT_SM, "bold"),
            fg_color=theme.ACCENT_VIOLET,
            hover_color="#6830D0",
            width=100,
            height=32,
            command=self._on_build_click,
        )
        self._build_btn.pack(side="right", padx=(theme.SP_2, 0))
        theme.apply_focus_ring(self._build_btn)

        # Toast label (bottom-right, hidden initially)
        self._toast_label = ctk.CTkLabel(
            self,
            text="",
            font=(theme.FONT_UI, theme.TEXT_SM),
            fg_color=theme.BG_OVERLAY,
            corner_radius=8,
            text_color=theme.TEXT_PRIMARY,
            padx=theme.SP_3,
            pady=theme.SP_2,
        )

    def _build_main_area(self) -> None:
        self._main = ctk.CTkFrame(self, fg_color=theme.BG_BASE)
        self._main.pack(fill="both", expand=True)
        self._main.grid_columnconfigure(1, weight=1)
        self._main.grid_rowconfigure(0, weight=1)

        # Left: sidebar (created in _build_screens, needs store)
        # Centre: timeline canvas
        # Right: track panel

    def _build_screens(self) -> None:
        from waveform.ui.sidebar_schedule import ScheduleSidebar
        from waveform.ui.timeline_canvas import TimelineCanvas
        from waveform.ui.track_panel import TrackPanel
        from waveform.ui.event_setup import EventSetupScreen

        # Left sidebar
        self._sidebar = ScheduleSidebar(self._main, store=self._store, analytics=self._analytics)
        self._sidebar.grid(row=0, column=0, sticky="nsew")
        self._sidebar.set_on_block_select(self._on_block_selected)

        # Timeline canvas
        self._timeline = TimelineCanvas(
            self._main,
            on_block_select=self._on_block_selected,
            store=self._store,
            analytics=self._analytics,
        )
        self._timeline.grid(row=0, column=1, sticky="nsew")

        # Track panel
        self._track_panel = TrackPanel(
            self._main,
            store=self._store,
            audio_player=self._audio,
            generation_controller=self._generation_controller,
            analytics=self._analytics,
        )
        self._track_panel.grid(row=0, column=2, sticky="nsew")

        # Placeholder screens as frames
        self._screens: Dict[AppScreen, Any] = {}

        # TIMELINE is the main view (sidebar + canvas + track panel are always present)
        timeline_frame = ctk.CTkFrame(self._main, fg_color="transparent")
        timeline_frame.grid_forget()
        self._screens[AppScreen.TIMELINE] = timeline_frame

        # EVENT_SETUP
        event_setup = EventSetupScreen(
            self._main,
            store=self._store,
            analytics=self._analytics,
            persistence=self._persistence,
        )
        event_setup.grid(row=0, column=0, columnspan=3, sticky="nsew")
        event_setup.grid_remove()
        self._screens[AppScreen.EVENT_SETUP] = event_setup

    def _navigate_to(self, screen: AppScreen) -> None:
        if screen == AppScreen.TIMELINE:
            # Show the three-column layout
            if AppScreen.EVENT_SETUP in self._screens:
                self._screens[AppScreen.EVENT_SETUP].grid_remove()
            self._sidebar.grid()
            self._timeline.grid()
            self._track_panel.grid()
        elif screen == AppScreen.EVENT_SETUP:
            # Cover the three-column layout
            self._sidebar.grid_remove()
            self._timeline.grid_remove()
            self._track_panel.grid_remove()
            if AppScreen.EVENT_SETUP in self._screens:
                self._screens[AppScreen.EVENT_SETUP].grid(row=0, column=0, columnspan=3, sticky="nsew")

    def _on_session_changed(self, session: Any) -> None:
        if session is None:
            return
        name = session.event_name or "New Event"
        self._event_name_label.configure(text=name)

    def _on_session_changed_for_counter(self, session: Any) -> None:
        if session is None:
            return
        self._generating_block_count = len(session.blocks)

    def _on_template_changed(self, template: Any) -> None:
        if template is None:
            return
        old_accent = self._current_accent
        new_accent = getattr(template, "accent_color", theme.ACCENT_VIOLET) or theme.ACCENT_VIOLET
        if old_accent != new_accent:
            self._tween_accent(old_accent, new_accent)

    def _tween_accent(self, from_color: str, to_color: str) -> None:
        """16-frame tween over 400ms. reduce_motion: snap immediately."""
        settings = self._store.get(AppState.SETTINGS) or {}
        if settings.get("reduce_motion", False):
            self._current_accent = to_color
            self._apply_accent(to_color)
            return

        steps = 16
        interval_ms = theme.MOTION_SLOW_MS // steps

        if self._tween_after_id:
            try:
                self.after_cancel(self._tween_after_id)
            except Exception:
                pass

        def _step(n: int) -> None:
            t = n / steps
            color = theme.lerp_hex(from_color, to_color, t)
            self._apply_accent(color)
            if n < steps:
                self._tween_after_id = self.after(interval_ms, lambda: _step(n + 1))
            else:
                self._current_accent = to_color
                self._tween_after_id = None

        _step(0)

    def _apply_accent(self, color: str) -> None:
        try:
            self._build_btn.configure(fg_color=color)
        except Exception:
            pass

    def _on_generation_status(self, status: Any) -> None:
        if status is None:
            return
        state = status.get("status")
        if state == "done":
            self._generating_block_count -= 1
            if self._generating_block_count <= 0:
                self._generating_block_count = 0
                self._build_btn.configure(text="▶ Build", state="normal")
                self._store.set(AppState.IS_GENERATING, False)
        elif state == "error":
            self._generating_block_count = 0
            self._build_btn.configure(text="▶ Build", state="normal")
            self._store.set(AppState.IS_GENERATING, False)

    def _on_approved_songs_changed(self, approved: Any) -> None:
        has_songs = bool(approved and any(approved.values()))
        if has_songs:
            self._export_btn.pack(side="right", padx=(theme.SP_2, 0), before=self._build_btn)
        else:
            try:
                self._export_btn.pack_forget()
            except Exception:
                pass

    def _on_toast(self, toast: Any) -> None:
        if toast is None:
            return
        msg = toast.get("message", "")
        toast_type = toast.get("type", "info")
        color = {
            "error": theme.DANGER_RED,
            "success": theme.SUCCESS_GREEN,
            "info": theme.TEXT_SECONDARY,
        }.get(toast_type, theme.TEXT_SECONDARY)

        self._toast_label.configure(text=msg, text_color=color)
        self._toast_label.place(relx=1.0, rely=1.0, anchor="se", x=-theme.SP_4, y=-theme.SP_4)

        # Cancel previous dismiss job
        if self._toast_after_id:
            try:
                self.after_cancel(self._toast_after_id)
            except Exception:
                pass
        self._toast_after_id = self.after(3000, lambda: self._toast_label.place_forget())

    def _on_block_selected(self, block: Any) -> None:
        self._sidebar.select_block(block.id)
        self._timeline.select_block(block.id)
        self._track_panel.set_active_block(block)

    def _on_build_click(self) -> None:
        session = self._store.get(AppState.SESSION)
        if session is None:
            self._store.set(AppState.TOAST, {"message": "Set up an event first.", "type": "info"})
            return

        current_text = self._build_btn.cget("text")
        if current_text.startswith("⏹"):
            # Stop
            ctrl = self._generation_controller or self._store.get(AppState.GENERATION_CONTROLLER)
            if ctrl:
                ctrl.cancel()
            self._build_btn.configure(text="▶ Build", state="normal")
            self._store.set(AppState.IS_GENERATING, False)
            return

        # Start generation
        ctrl = self._generation_controller or self._store.get(AppState.GENERATION_CONTROLLER)
        if ctrl is None:
            self._store.set(AppState.TOAST, {"message": "Generation service unavailable.", "type": "error"})
            return

        self._generating_block_count = len(session.blocks)
        self._build_btn.configure(text="⏹ Stop", state="normal")
        self._store.set(AppState.IS_GENERATING, True)
        ctrl.start_generation(session)

    def _on_export_click(self) -> None:
        from waveform.ui.export_dialog import ExportDialog

        session = self._store.get(AppState.SESSION)
        approved = self._store.get(AppState.APPROVED_SONGS) or {}
        if session is None:
            return

        ExportDialog(
            parent=self,
            store=self._store,
            export_controller=self._export_controller,
            session=session,
            approved_songs=approved,
            app_open_time_ms=int(time.time() * 1000) - self._app_open_time_ms,
        )

    def _on_history_click(self) -> None:
        if not self._persistence:
            return
        from waveform.ui.session_history import SessionHistoryDialog

        SessionHistoryDialog(
            parent=self,
            persistence=self._persistence,
            on_resume=self._on_resume,
            on_fork=self._on_resume,
            store=self._store,
        )

    def _on_resume(self, session_data: dict) -> None:
        try:
            from waveform.domain.session import PlaylistSession

            session = PlaylistSession.from_dict(session_data)
            self._store.set(AppState.SESSION, session)
            self._store.set(AppState.SELECTED_TEMPLATE, session.event_template)
            self._store.set(AppState.CURRENT_SCREEN, AppScreen.TIMELINE)

            if session._resume_missing_fields:
                self._store.set(AppState.TOAST, {
                    "message": "Session restored. Some history may be incomplete.",
                    "type": "info",
                })
            else:
                self._store.set(AppState.TOAST, {
                    "message": f"Resumed: {session.event_name}",
                    "type": "success",
                })
        except Exception as exc:
            self._store.set(AppState.TOAST, {
                "message": f"Could not resume session: {exc}",
                "type": "error",
            })

    def _on_settings_click(self) -> None:
        if not self._persistence:
            return
        from waveform.ui.settings_screen import SettingsScreen

        SettingsScreen(
            parent=self,
            store=self._store,
            persistence=self._persistence,
            analytics=self._analytics,
        )

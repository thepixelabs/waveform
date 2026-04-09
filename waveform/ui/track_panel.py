"""
track_panel.py — TrackPanel: right column of the three-column layout.

Three display states:
1. EMPTY — no pending song.
2. GENERATING — shimmer + WaveformAnim.
3. PREVIEW — album art, waveform, action buttons (Approve/Swap/Veto).

Phase 11: Song Approved particle burst, Block Transition crossfade.
"""
from __future__ import annotations

import random
import threading
from typing import Any, Dict, List, Optional

try:
    import customtkinter as ctk  # type: ignore
    import tkinter as tk
    HAS_CTK = True
except ImportError:
    HAS_CTK = False

from waveform.ui import theme
from waveform.ui.widgets.track_card import TrackCard
from waveform.ui.widgets.waveform_anim import WaveformAnim


class TrackPanel(ctk.CTkFrame if HAS_CTK else object):  # type: ignore
    def __init__(
        self,
        parent: Any,
        store: Any,
        audio_player: Any = None,
        generation_controller: Any = None,
        analytics: Any = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            parent,
            width=theme.TRACK_PANEL_WIDTH,
            fg_color=theme.BG_SURFACE,
            **kwargs,
        )
        self._store = store
        self._audio = audio_player
        self._gen_ctrl = generation_controller
        self._analytics = analytics

        self._current_song: Optional[Any] = None
        self._current_block_id: Optional[str] = None
        self._active_block: Optional[Any] = None
        self._playback_after_id: Optional[str] = None
        self._preview_started_ms: int = 0

        self.grid_propagate(False)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Header
        ctk.CTkLabel(
            self,
            text="TRACKS",
            font=(theme.FONT_UI, theme.TEXT_XS, "bold"),
            text_color=theme.TEXT_MUTED,
        ).grid(row=0, column=0, padx=theme.SP_3, pady=(theme.SP_3, theme.SP_1), sticky="w")

        # Content frame
        self._preview_frame = ctk.CTkFrame(self, fg_color=theme.BG_SURFACE)
        self._preview_frame.grid(row=1, column=0, sticky="nsew", padx=theme.SP_2)
        self._preview_frame.grid_columnconfigure(0, weight=1)
        self._preview_frame.grid_rowconfigure(0, weight=1)

        # Approved songs list
        self._approved_label = ctk.CTkLabel(
            self,
            text="APPROVED",
            font=(theme.FONT_UI, theme.TEXT_XS, "bold"),
            text_color=theme.TEXT_MUTED,
        )
        self._approved_label.grid(row=2, column=0, padx=theme.SP_3, pady=(theme.SP_2, theme.SP_1), sticky="w")

        self._approved_scroll = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            height=160,
        )
        self._approved_scroll.grid(row=3, column=0, sticky="ew", padx=theme.SP_2, pady=(0, theme.SP_2))
        self._approved_scroll.grid_columnconfigure(0, weight=1)

        self._show_empty()

        # Keyboard shortcuts on root window
        try:
            root = self.winfo_toplevel()
            root.bind("<space>", self._kb_approve, add="+")
            root.bind("<s>", self._kb_swap, add="+")
            root.bind("<S>", self._kb_swap, add="+")
            root.bind("<BackSpace>", self._kb_veto, add="+")
        except Exception:
            pass

        # Store subscriptions
        store.subscribe("pending_song", lambda v: self.after(0, lambda: self._on_pending_song(v)))
        store.subscribe("is_generating", lambda v: self.after(0, lambda: self._on_is_generating(v)))
        store.subscribe("approved_songs", lambda v: self.after(0, lambda: self._refresh_approved_list()))
        store.subscribe("selected_block_id", lambda v: self.after(0, lambda: self._on_selected_block_changed(v)))

    # -------------------------------------------------------------------
    # State display
    # -------------------------------------------------------------------

    def _show_empty(self) -> None:
        self._clear_preview_frame()
        inner = ctk.CTkFrame(self._preview_frame, fg_color="transparent")
        inner.place(relx=0.5, rely=0.5, anchor="center")

        WaveformAnim(inner, width=60, height=48, animate=False).pack(pady=(0, theme.SP_3))

        ctk.CTkLabel(
            inner,
            text="Select a block and hit Build\nto get suggestions",
            font=(theme.FONT_UI, theme.TEXT_SM),
            text_color=theme.TEXT_MUTED,
            justify="center",
        ).pack()

        # Dimmed action buttons
        btn_row = ctk.CTkFrame(inner, fg_color="transparent")
        btn_row.pack(pady=theme.SP_3)
        for text, color in [("Approve\n(Space)", theme.SUCCESS_GREEN), ("Swap\n(S)", theme.BG_OVERLAY), ("Veto\n(⌫)", theme.DANGER_RED)]:
            ctk.CTkButton(
                btn_row,
                text=text,
                font=(theme.FONT_UI, theme.TEXT_XS),
                fg_color="transparent",
                border_color=color,
                border_width=1,
                text_color=theme.TEXT_MUTED,
                state="disabled",
                width=80,
                height=48,
            ).pack(side="left", padx=theme.SP_1)

    def _show_generating(self) -> None:
        self._clear_preview_frame()
        inner = ctk.CTkFrame(self._preview_frame, fg_color="transparent")
        inner.place(relx=0.5, rely=0.5, anchor="center")

        self._wave_generating = WaveformAnim(inner, width=60, height=48, store=self._store)
        self._wave_generating.start_animation(mode="generating")
        self._wave_generating.pack(pady=(0, theme.SP_3))

        ctk.CTkLabel(
            inner,
            text="Generating suggestions…",
            font=(theme.FONT_UI, theme.TEXT_SM),
            text_color=theme.TEXT_SECONDARY,
        ).pack()

    def _show_preview(self, song: Any, block_id: str) -> None:
        self._clear_preview_frame()
        self._current_song = song
        self._current_block_id = block_id

        track = getattr(song, "track", None)

        # Album art frame
        art_frame = ctk.CTkFrame(
            self._preview_frame,
            width=180,
            height=180,
            fg_color=theme.BG_OVERLAY,
            corner_radius=theme.RADIUS_CARD,
        )
        art_frame.grid(row=0, column=0, padx=theme.SP_4, pady=(theme.SP_4, theme.SP_2))
        art_frame.grid_propagate(False)
        self._art_frame = art_frame

        # Load art async
        art_url = getattr(track, "album_art_url", None) if track else None
        if art_url:
            self._load_art_async(art_url)

        # No preview badge
        preview_url = getattr(track, "preview_url", None) if track else None
        if not preview_url:
            ctk.CTkLabel(
                art_frame,
                text="No preview",
                font=(theme.FONT_UI, theme.TEXT_XS),
                text_color=theme.TEXT_MUTED,
            ).place(relx=0.5, rely=0.5, anchor="center")

        # Playback progress bar
        self._progress_bar = ctk.CTkProgressBar(
            self._preview_frame,
            progress_color=theme.ACCENT_CYAN,
            height=3,
        )
        self._progress_bar.set(0)
        self._progress_bar.grid(row=1, column=0, sticky="ew", padx=theme.SP_4, pady=(0, theme.SP_2))

        # Track info
        ctk.CTkLabel(
            self._preview_frame,
            text=song.title[:50],
            font=(theme.FONT_UI, theme.TEXT_LG, "bold"),
            text_color=theme.TEXT_PRIMARY,
        ).grid(row=2, column=0, padx=theme.SP_4)

        ctk.CTkLabel(
            self._preview_frame,
            text=song.artist[:40],
            font=(theme.FONT_UI, theme.TEXT_SM),
            text_color=theme.TEXT_SECONDARY,
        ).grid(row=3, column=0, padx=theme.SP_4)

        # Duration
        duration_ms = getattr(track, "duration_ms", 0) if track else 0
        if duration_ms:
            dur_str = f"{duration_ms // 60000}:{(duration_ms % 60000) // 1000:02d}"
            ctk.CTkLabel(
                self._preview_frame,
                text=dur_str,
                font=(theme.FONT_MONO, theme.TEXT_SM),
                text_color=theme.TEXT_MUTED,
            ).grid(row=4, column=0, padx=theme.SP_4, pady=(0, theme.SP_2))

        # WaveformAnim breathing
        wave = WaveformAnim(self._preview_frame, width=80, height=36, store=self._store)
        wave.start_animation(mode="idle")
        wave.grid(row=5, column=0, pady=(0, theme.SP_2))

        # Action buttons
        btn_frame = ctk.CTkFrame(self._preview_frame, fg_color="transparent")
        btn_frame.grid(row=6, column=0, padx=theme.SP_3, pady=(0, theme.SP_3))

        self._approve_btn = ctk.CTkButton(
            btn_frame,
            text="Approve\n(Space)",
            font=(theme.FONT_UI, theme.TEXT_XS),
            fg_color=theme.SUCCESS_GREEN,
            text_color=theme.TEXT_PRIMARY,
            hover_color="#2CBF8A",
            width=100,
            height=52,
            command=self._on_approve,
        )
        self._approve_btn.pack(side="left", padx=theme.SP_1)

        ctk.CTkButton(
            btn_frame,
            text="Swap\n(S)",
            font=(theme.FONT_UI, theme.TEXT_XS),
            fg_color=theme.BG_OVERLAY,
            text_color=theme.TEXT_SECONDARY,
            hover_color=theme.BG_BASE,
            width=80,
            height=52,
            command=self._on_swap,
        ).pack(side="left", padx=theme.SP_1)

        ctk.CTkButton(
            btn_frame,
            text="Veto\n(⌫)",
            font=(theme.FONT_UI, theme.TEXT_XS),
            fg_color="transparent",
            border_color=theme.DANGER_RED,
            border_width=1,
            text_color=theme.DANGER_RED,
            hover_color="#3A1010",
            width=80,
            height=52,
            command=self._on_veto,
        ).pack(side="left", padx=theme.SP_1)

        # Start audio playback
        if preview_url:
            self._start_playback(preview_url)

    # -------------------------------------------------------------------
    # Store subscriptions
    # -------------------------------------------------------------------

    def _on_pending_song(self, value: Any) -> None:
        if value is None:
            return
        block_id, annotated = value
        song = annotated["song"]
        self._transition_to_block(lambda: self._show_preview(song, block_id))

    def _on_is_generating(self, is_generating: bool) -> None:
        if is_generating and self._current_song is None:
            self._show_generating()
        elif not is_generating and self._current_song is None:
            self._show_empty()

    def _on_selected_block_changed(self, block_id: Optional[str]) -> None:
        self._current_block_id = block_id
        self._refresh_approved_list()

    def _refresh_approved_list(self) -> None:
        for w in self._approved_scroll.winfo_children():
            w.destroy()

        block_id = self._current_block_id or self._store.get("selected_block_id")
        if block_id is None:
            return

        approved = self._store.get("approved_songs") or {}
        songs = approved.get(block_id, [])

        if not songs:
            ctk.CTkLabel(
                self._approved_scroll,
                text="No approved songs yet",
                font=(theme.FONT_UI, theme.TEXT_XS),
                text_color=theme.TEXT_MUTED,
            ).grid(row=0, column=0, sticky="w")
            return

        for i, song in enumerate(songs):
            card = TrackCard(
                self._approved_scroll,
                song=song,
                on_remove=lambda s: self._remove_approved(block_id, s),
            )
            card.grid(row=i, column=0, sticky="ew", pady=(0, theme.SP_1))

    def _remove_approved(self, block_id: str, song: Any) -> None:
        approved = dict(self._store.get("approved_songs") or {})
        songs = list(approved.get(block_id, []))
        songs = [s for s in songs if s is not song]
        approved[block_id] = songs
        self._store.set("approved_songs", approved)

    # -------------------------------------------------------------------
    # Action handlers
    # -------------------------------------------------------------------

    def _on_approve(self) -> None:
        if self._current_song is None:
            return
        song = self._current_song
        block_id = self._current_block_id

        # Add to approved songs
        approved = dict(self._store.get("approved_songs") or {})
        approved.setdefault(block_id, []).append(song)
        self._store.set("approved_songs", approved)

        # Handle keep in generation controller
        ctrl = self._gen_ctrl or self._store.get("generation_controller")
        if ctrl:
            ctrl.handle_keep(block_id, song)

        # Particle burst (Phase 11)
        self._fire_burst_on_widget(self._approve_btn)

        # Analytics
        if self._analytics and getattr(song, "track", None):
            self._analytics.song_kept(track_id=song.track.uri, block_id=block_id)

        self._stop_playback()
        self._current_song = None
        self._show_empty()
        self._refresh_approved_list()

    def _on_swap(self) -> None:
        if self._current_song is None:
            return
        ctrl = self._gen_ctrl or self._store.get("generation_controller")
        if ctrl:
            ctrl.request_swap(self._current_block_id, self._current_song)
        self._stop_playback()
        self._current_song = None

    def _on_veto(self) -> None:
        if self._current_song is None:
            return
        song = self._current_song
        block_id = self._current_block_id
        self._show_veto_reason_picker(song, block_id)

    def _show_veto_reason_picker(self, song: Any, block_id: str) -> None:
        from waveform.domain.session import VETO_REASON_TAGS

        dialog = ctk.CTkToplevel(self)
        dialog.title("Why veto?")
        dialog.geometry("320x280")
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()
        dialog.focus_set()

        ctk.CTkLabel(
            dialog,
            text="Why are you vetoing this song?",
            font=(theme.FONT_UI, theme.TEXT_SM),
            text_color=theme.TEXT_PRIMARY,
        ).pack(padx=theme.SP_4, pady=(theme.SP_4, theme.SP_2))

        def _submit(reason: Optional[str]) -> None:
            dialog.destroy()
            ctrl = self._gen_ctrl or self._store.get("generation_controller")
            if ctrl:
                ctrl.handle_veto(block_id, song, reason_tag=reason)
            if self._analytics and getattr(song, "track", None):
                self._analytics.song_vetoed(track_id=song.track.uri, block_id=block_id, reason_tag=reason)
            self._stop_playback()
            self._current_song = None
            self._show_empty()

        # No reason (always first)
        ctk.CTkButton(
            dialog,
            text="No reason",
            fg_color=theme.BG_OVERLAY,
            command=lambda: _submit(None),
        ).pack(fill="x", padx=theme.SP_4, pady=(0, theme.SP_1))

        for reason in VETO_REASON_TAGS:
            ctk.CTkButton(
                dialog,
                text=reason,
                fg_color=theme.BG_OVERLAY if reason != "artist already used" else "transparent",
                border_color=theme.DANGER_RED if reason == "artist already used" else "transparent",
                border_width=1 if reason == "artist already used" else 0,
                text_color=theme.DANGER_RED if reason == "artist already used" else theme.TEXT_SECONDARY,
                command=lambda r=reason: _submit(r),
            ).pack(fill="x", padx=theme.SP_4, pady=(0, theme.SP_1))

    # -------------------------------------------------------------------
    # Keyboard shortcuts
    # -------------------------------------------------------------------

    def _kb_approve(self, event: Any) -> None:
        if self._current_song is not None:
            self._on_approve()

    def _kb_swap(self, event: Any) -> None:
        if self._current_song is not None:
            self._on_swap()

    def _kb_veto(self, event: Any) -> None:
        if self._current_song is not None:
            self._on_veto()

    # -------------------------------------------------------------------
    # Playback
    # -------------------------------------------------------------------

    def _start_playback(self, url: str) -> None:
        import time
        self._preview_started_ms = int(time.time() * 1000)
        if self._audio:
            self._audio.play(url)
        self._poll_playback()

    def _poll_playback(self) -> None:
        try:
            if self._audio and self._audio.is_playing:
                elapsed_frac = min(1.0, self._audio.elapsed_seconds() / 30.0)
                if hasattr(self, "_progress_bar"):
                    self._progress_bar.set(elapsed_frac)
                self._playback_after_id = self.after(250, self._poll_playback)
            else:
                self._stop_playback_poll()
        except Exception:
            pass

    def _stop_playback(self) -> None:
        if self._playback_after_id:
            try:
                self.after_cancel(self._playback_after_id)
            except Exception:
                pass
            self._playback_after_id = None
        if self._audio:
            self._audio.stop()
        self._stop_playback_poll()

    def _stop_playback_poll(self) -> None:
        import time
        if self._analytics and self._current_song and self._preview_started_ms:
            elapsed_ms = int(time.time() * 1000) - self._preview_started_ms
            track = getattr(self._current_song, "track", None)
            if track:
                self._analytics.song_previewed(
                    track_id=track.uri,
                    block_id=self._current_block_id or "",
                    preview_duration_played=elapsed_ms,
                )

    def _load_art_async(self, url: str) -> None:
        def _fetch() -> None:
            try:
                import urllib.request
                from io import BytesIO
                from PIL import Image  # type: ignore

                data = urllib.request.urlopen(url, timeout=8).read()
                img = Image.open(BytesIO(data)).convert("RGB").resize((180, 180))
                ctk_img = ctk.CTkImage(img, size=(180, 180))
                self.after(0, lambda: self._set_art(ctk_img))
            except Exception:
                pass

        threading.Thread(target=_fetch, daemon=True).start()

    def _set_art(self, ctk_img: Any) -> None:
        try:
            lbl = ctk.CTkLabel(self._art_frame, image=ctk_img, text="")
            lbl.place(x=0, y=0, relwidth=1, relheight=1)
        except Exception:
            pass

    # -------------------------------------------------------------------
    # Phase 11 animations
    # -------------------------------------------------------------------

    def _particle_burst(self, anchor_widget: Any) -> None:
        """7 small rectangles fly outward from anchor with fading colour."""
        try:
            # Get position relative to preview_frame
            x = anchor_widget.winfo_x() + anchor_widget.winfo_width() // 2
            y = anchor_widget.winfo_y() + anchor_widget.winfo_height() // 2

            canvas = tk.Canvas(
                self._preview_frame,
                bg=theme.BG_SURFACE,
                highlightthickness=0,
                width=self._preview_frame.winfo_width(),
                height=self._preview_frame.winfo_height(),
            )
            canvas.place(x=0, y=0, relwidth=1, relheight=1)

            rng = random.Random()
            particles = []
            colors = [theme.SUCCESS_GREEN, theme.ACCENT_VIOLET, theme.ACCENT_CYAN]
            for _ in range(7):
                import math
                angle = rng.uniform(0, 2 * math.pi)
                speed = rng.uniform(30, 80)
                color = rng.choice(colors)
                pid = canvas.create_rectangle(x, y, x + 3, y + 8, fill=color, outline="")
                particles.append({"id": pid, "angle": angle, "speed": speed, "color": color, "step": 0})

            steps = 12

            def _animate(n: int) -> None:
                if not canvas.winfo_exists():
                    return
                for p in particles:
                    import math
                    dx = p["speed"] * math.cos(p["angle"]) * n / steps
                    dy = p["speed"] * math.sin(p["angle"]) * n / steps
                    canvas.coords(p["id"], x + dx, y + dy, x + dx + 3, y + dy + 8)
                    faded = theme.lerp_hex(p["color"], theme.BG_SURFACE, n / steps)
                    canvas.itemconfig(p["id"], fill=faded)
                if n < steps:
                    canvas.after(25, lambda: _animate(n + 1))
                else:
                    canvas.destroy()

            canvas.after(10, lambda: _animate(1))
        except Exception:
            pass

    def _fire_burst_on_widget(self, widget: Any) -> None:
        """Walk the preview frame tree to find the approve button, fire burst."""
        try:
            settings = self._store.get("settings") or {}
            if settings.get("reduce_motion", False):
                return
            self._particle_burst(widget)
        except Exception:
            pass

    def _transition_to_block(self, callback: Any) -> None:
        """Simulate crossfade by tweening fg_color toward background. Phase 11."""
        try:
            settings = self._store.get("settings") or {}
            if settings.get("reduce_motion", False):
                callback()
                return

            steps_out = 6
            steps_in = 8

            def _fade_out(n: int) -> None:
                if not self._preview_frame.winfo_exists():
                    return
                faded = theme.lerp_hex(theme.BG_SURFACE, theme.BG_BASE, n / steps_out)
                try:
                    self._preview_frame.configure(fg_color=faded)
                except Exception:
                    pass
                if n < steps_out:
                    self.after(25, lambda: _fade_out(n + 1))
                else:
                    callback()
                    _fade_in(0)

            def _fade_in(n: int) -> None:
                if not self._preview_frame.winfo_exists():
                    return
                faded = theme.lerp_hex(theme.BG_BASE, theme.BG_SURFACE, n / steps_in)
                try:
                    self._preview_frame.configure(fg_color=faded)
                except Exception:
                    pass
                if n < steps_in:
                    self.after(25, lambda: _fade_in(n + 1))

            _fade_out(0)
        except Exception:
            callback()

    def set_active_block(self, block: Any) -> None:
        self._active_block = block
        self._current_block_id = block.id
        self._store.set("selected_block_id", block.id)
        self._refresh_approved_list()

    def _clear_preview_frame(self) -> None:
        for w in self._preview_frame.winfo_children():
            w.destroy()

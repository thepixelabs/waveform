"""
genre_weight_panel.py — Full genre weight editor panel.

Includes:
- Tag autocomplete search input (backed by DEFAULT_INDEX)
- Active genre rows (GenreSlider with remove)
- Inherited genre rows (ghosted, click-to-override)
- Max 6 genres per block enforcement
- wire_genre_panel_to_store() helper for immutable state updates
"""
from __future__ import annotations

import dataclasses
from typing import Any, Callable, Dict, List, Optional

try:
    import customtkinter as ctk  # type: ignore
    HAS_CTK = True
except ImportError:
    HAS_CTK = False

from waveform.domain.genre import DEFAULT_INDEX, GenreWeight
from waveform.ui import theme
from waveform.ui.widgets.genre_slider import GenreSlider

MAX_GENRES = 6


class GenreWeightPanel(ctk.CTkFrame if HAS_CTK else object):  # type: ignore
    """Full genre weight editor: search + active + inherited rows."""

    def __init__(
        self,
        parent: Any,
        block: Any,
        session: Any,
        on_weights_changed: Optional[Callable[[str, List[GenreWeight]], None]] = None,
        analytics: Any = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(parent, fg_color=theme.BG_OVERLAY, corner_radius=theme.RADIUS_CARD, **kwargs)
        self._block = block
        self._session = session
        self._on_weights_changed = on_weights_changed
        self._analytics = analytics
        self._analytics_debounce_jobs: Dict[str, Optional[str]] = {}

        self.grid_columnconfigure(0, weight=1)

        # Header
        ctk.CTkLabel(
            self,
            text="GENRE WEIGHTS",
            font=(theme.FONT_UI, theme.TEXT_XS, "bold"),
            text_color=theme.TEXT_MUTED,
        ).grid(row=0, column=0, padx=theme.SP_3, pady=(theme.SP_3, theme.SP_1), sticky="w")

        # Search input
        self._search_var = ctk.StringVar()
        self._search_var.trace_add("write", self._on_search_changed)
        at_capacity = len(block.genre_weights) >= MAX_GENRES
        self._search_entry = ctk.CTkEntry(
            self,
            textvariable=self._search_var,
            placeholder_text="Max 6 genres per block" if at_capacity else "Search genres…",
            font=(theme.FONT_UI, theme.TEXT_SM),
            fg_color=theme.BG_SURFACE,
            border_color=theme.BG_OVERLAY,
            state="disabled" if at_capacity else "normal",
            height=32,
        )
        self._search_entry.grid(row=1, column=0, padx=theme.SP_3, pady=(0, theme.SP_2), sticky="ew")

        # Suggestion pills container
        self._pills_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._pills_frame.grid(row=2, column=0, padx=theme.SP_3, sticky="ew")

        # Active genres container
        self._active_frame = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            height=120,
        )
        self._active_frame.grid(row=3, column=0, padx=theme.SP_3, pady=(0, theme.SP_1), sticky="ew")
        self._active_frame.grid_columnconfigure(0, weight=1)

        # Inherited genres container
        self._inherited_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._inherited_frame.grid(row=4, column=0, padx=theme.SP_3, pady=(0, theme.SP_3), sticky="ew")
        self._inherited_frame.grid_columnconfigure(0, weight=1)

        self._render_active()
        self._render_inherited()

    def refresh(self, block: Any, session: Any) -> None:
        """Rebuild the panel for a new block/session."""
        self._block = block
        self._session = session
        self._render_active()
        self._render_inherited()
        self._update_search_state()

    def _on_search_changed(self, *_: Any) -> None:
        query = self._search_var.get()
        results = DEFAULT_INDEX.search(query, limit=8)
        self._refresh_pills(results)

    def _refresh_pills(self, tags: List[str]) -> None:
        for widget in self._pills_frame.winfo_children():
            widget.destroy()
        active_tags = {gw.tag for gw in self._block.genre_weights}
        for i, tag in enumerate(tags):
            if tag in active_tags:
                continue
            pill = ctk.CTkButton(
                self._pills_frame,
                text=tag,
                font=(theme.FONT_UI, theme.TEXT_XS),
                height=24,
                fg_color=theme.BG_SURFACE,
                text_color=theme.TEXT_SECONDARY,
                hover_color=theme.ACCENT_VIOLET,
                border_color=theme.BG_OVERLAY,
                border_width=1,
                corner_radius=12,
                command=lambda t=tag: self._add_genre(t),
            )
            pill.grid(row=0, column=i, padx=(0, theme.SP_1), sticky="w")
            theme.apply_focus_ring(pill)

    def _add_genre(self, tag: str) -> None:
        if len(self._block.genre_weights) >= MAX_GENRES:
            return
        new_weights = list(self._block.genre_weights) + [GenreWeight(tag, 0.4)]
        self._emit_change(new_weights)
        self._search_var.set("")

    def _handle_weight_change(self, tag: str, weight: float) -> None:
        new_weights = [
            GenreWeight(gw.tag, weight) if gw.tag == tag else gw
            for gw in self._block.genre_weights
        ]
        self._emit_change(new_weights)

        # Analytics debounce (300ms)
        if self._analytics:
            old_job = self._analytics_debounce_jobs.get(tag)
            if old_job:
                try:
                    self.after_cancel(old_job)
                except Exception:
                    pass
            block_id = self._block.id
            job = self.after(
                300,
                lambda t=tag, w=weight, bid=block_id: self._analytics.genre_weight_changed(bid, t, w),
            )
            self._analytics_debounce_jobs[tag] = job

    def _remove_genre(self, tag: str) -> None:
        new_weights = [gw for gw in self._block.genre_weights if gw.tag != tag]
        self._emit_change(new_weights)

    def _handle_activate_inherited(self, tag: str) -> None:
        # Clone inherited weight into active list
        inherited_weight = 0.4
        tpl = getattr(self._session, "event_template", None)
        if tpl:
            for gw in getattr(tpl, "default_genre_weights", []):
                if gw.tag == tag:
                    inherited_weight = gw.weight
                    break
        if len(self._block.genre_weights) < MAX_GENRES:
            new_weights = list(self._block.genre_weights) + [GenreWeight(tag, inherited_weight)]
            self._emit_change(new_weights)

    def _emit_change(self, new_weights: List[GenreWeight]) -> None:
        # Update block reference immutably
        self._block = dataclasses.replace(self._block, genre_weights=new_weights)
        if self._on_weights_changed:
            self._on_weights_changed(self._block.id, new_weights)
        self._render_active()
        self._render_inherited()
        self._update_search_state()

    def _render_active(self) -> None:
        for w in self._active_frame.winfo_children():
            w.destroy()
        if not self._block.genre_weights:
            ctk.CTkLabel(
                self._active_frame,
                text="No genres set — search above to add",
                font=(theme.FONT_UI, theme.TEXT_XS),
                text_color=theme.TEXT_MUTED,
            ).grid(row=0, column=0, sticky="w")
            return
        for i, gw in enumerate(self._block.genre_weights):
            row = GenreSlider(
                self._active_frame,
                tag=gw.tag,
                weight=gw.weight,
                on_change=self._handle_weight_change,
                on_remove=self._remove_genre,
                inherited=False,
            )
            row.grid(row=i, column=0, sticky="ew", pady=(0, theme.SP_1))

    def _render_inherited(self) -> None:
        for w in self._inherited_frame.winfo_children():
            w.destroy()
        tpl = getattr(self._session, "event_template", None)
        if tpl is None:
            return
        inherited = getattr(tpl, "default_genre_weights", [])
        if not inherited:
            return
        active_tags = {gw.tag for gw in self._block.genre_weights}
        visible = [gw for gw in inherited if gw.tag not in active_tags]
        if not visible:
            return

        ctk.CTkLabel(
            self._inherited_frame,
            text="EVENT DEFAULTS",
            font=(theme.FONT_UI, theme.TEXT_XS),
            text_color=theme.TEXT_MUTED,
        ).grid(row=0, column=0, sticky="w", pady=(theme.SP_2, 0))

        for i, gw in enumerate(visible):
            row = GenreSlider(
                self._inherited_frame,
                tag=gw.tag,
                weight=gw.weight,
                on_activate=self._handle_activate_inherited,
                inherited=True,
            )
            row.grid(row=i + 1, column=0, sticky="ew", pady=(0, theme.SP_1))

    def _update_search_state(self) -> None:
        at_capacity = len(self._block.genre_weights) >= MAX_GENRES
        try:
            self._search_entry.configure(
                state="disabled" if at_capacity else "normal",
                placeholder_text="Max 6 genres per block" if at_capacity else "Search genres…",
            )
        except Exception:
            pass


def wire_genre_panel_to_store(
    store: Any,
    block_id: str,
    new_weights: List[GenreWeight],
) -> None:
    """Immutable update helper: apply new genre weights to the store session."""
    session = store.get("session")
    if session is None:
        return
    updated_blocks = []
    for block in session.blocks:
        if block.id == block_id:
            updated_blocks.append(dataclasses.replace(block, genre_weights=new_weights))
        else:
            updated_blocks.append(block)
    updated_session = dataclasses.replace(session, blocks=updated_blocks)
    store.set("session", updated_session)

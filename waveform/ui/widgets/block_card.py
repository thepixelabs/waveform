"""
block_card.py — BlockCard widget: sidebar schedule entry for one block.

Shows archetype emoji, name, time range, duration, energy dots, and an
expandable detail panel with energy slider, archetype chips, and genre weights.

Phase 2A: added keyboard navigation (on_delete, _bind_keyboard, focus ring).
Phase 2B: custom archetype support via get_spec_for_id().
"""
from __future__ import annotations

import dataclasses
from typing import Any, Callable, Dict, List, Optional

try:
    import customtkinter as ctk  # type: ignore
    import tkinter as tk
    HAS_CTK = True
except ImportError:
    HAS_CTK = False

from waveform.domain.block import (
    ARCHETYPE_SPECS,
    BlockArchetype,
    get_spec_for_id,
    list_custom_archetypes,
)
from waveform.ui import theme

# Public emoji dict for use by timeline and sidebar
ARCHETYPE_EMOJI: Dict[str, str] = {
    BlockArchetype.ARRIVAL.value: "🥂",
    BlockArchetype.CHILL.value: "🌊",
    BlockArchetype.SINGALONG.value: "🎤",
    BlockArchetype.GROOVE.value: "🎸",
    BlockArchetype.DANCE_FLOOR.value: "💃",
    BlockArchetype.CLUB_NIGHT.value: "🎧",
    BlockArchetype.LATE_NIGHT.value: "🌙",
    BlockArchetype.SUNRISE.value: "🌅",
    BlockArchetype.CEREMONY.value: "🕊️",
    BlockArchetype.PEAK.value: "⚡",
}


def _archetype_emoji(archetype: Any) -> str:
    arch_str = str(archetype.value if hasattr(archetype, "value") else archetype)
    # Built-in
    if arch_str in ARCHETYPE_EMOJI:
        return ARCHETYPE_EMOJI[arch_str]
    # Custom
    from waveform.domain.block import get_custom_archetype
    custom = get_custom_archetype(arch_str)
    if custom:
        return custom.emoji
    return "🎵"


def _energy_dots(level: int) -> str:
    filled = "●" * level
    empty = "○" * (5 - level)
    return filled + empty


def _minutes_to_hhmm(minutes: int) -> str:
    h = minutes // 60
    m = minutes % 60
    return f"{h:02d}:{m:02d}"


class BlockCard(ctk.CTkFrame if HAS_CTK else object):  # type: ignore
    """Sidebar card for a single block. Expandable with detail panel."""

    def __init__(
        self,
        parent: Any,
        block: Any,
        start_minute: int = 0,
        on_click: Optional[Callable[[Any], None]] = None,
        on_mutate: Optional[Callable[[Any], None]] = None,
        on_delete: Optional[Callable[[Any], None]] = None,
        store: Any = None,
        analytics: Any = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            parent,
            fg_color=theme.BG_SURFACE,
            corner_radius=theme.RADIUS_CARD,
            border_width=1,
            border_color=theme.BG_OVERLAY,
            **kwargs,
        )
        self._block = block
        self._start_minute = start_minute
        self._on_click = on_click
        self._on_mutate = on_mutate
        self._on_delete = on_delete
        self._store = store
        self._analytics = analytics
        self._selected = False
        self._detail_visible = False
        self._genre_panel: Any = None

        self.grid_columnconfigure(0, weight=1)
        if HAS_CTK:
            tk.Frame.configure(self, takefocus=True)

        self._build_header()
        self._bind_click()
        self._bind_keyboard()

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=theme.SP_3, pady=theme.SP_2)
        header.grid_columnconfigure(1, weight=1)

        # Left accent bar
        spec = get_spec_for_id(str(self._block.archetype.value if hasattr(self._block.archetype, "value") else self._block.archetype))
        accent = spec.cover_palette[0]
        accent_bar = ctk.CTkFrame(header, width=3, fg_color=accent, corner_radius=2)
        accent_bar.grid(row=0, column=0, rowspan=2, sticky="ns", padx=(0, theme.SP_2))

        # Emoji + name
        emoji = _archetype_emoji(self._block.archetype)
        name_label = ctk.CTkLabel(
            header,
            text=f"{emoji}  {self._block.name}",
            font=(theme.FONT_UI, theme.TEXT_SM, "bold"),
            text_color=theme.TEXT_PRIMARY,
            anchor="w",
        )
        name_label.grid(row=0, column=1, sticky="w")

        # Archetype right-aligned
        arch_label = ctk.CTkLabel(
            header,
            text=spec.display_name,
            font=(theme.FONT_UI, theme.TEXT_XS),
            text_color=theme.TEXT_MUTED,
            anchor="e",
        )
        arch_label.grid(row=0, column=2, sticky="e")

        # Time range + duration + energy dots
        start_hhmm = _minutes_to_hhmm(1200 + self._start_minute)
        end_hhmm = _minutes_to_hhmm(1200 + self._start_minute + self._block.duration_minutes)
        meta_text = (
            f"{start_hhmm} – {end_hhmm}  •  "
            f"{self._block.duration_minutes}m  •  "
            f"{_energy_dots(self._block.energy_level)}"
        )
        meta_label = ctk.CTkLabel(
            header,
            text=meta_text,
            font=(theme.FONT_UI, theme.TEXT_XS),
            text_color=theme.TEXT_MUTED,
            anchor="w",
        )
        meta_label.grid(row=1, column=1, columnspan=2, sticky="w")

        # Store references for click propagation
        for widget in (header, name_label, arch_label, meta_label, accent_bar):
            widget.bind("<Button-1>", self._handle_click)

    def _build_detail_panel(self) -> None:
        if self._detail_visible:
            return
        self._detail_visible = True

        self._detail = ctk.CTkFrame(self, fg_color="transparent")
        self._detail.grid(row=1, column=0, sticky="ew", padx=theme.SP_3, pady=(0, theme.SP_2))
        self._detail.grid_columnconfigure(0, weight=1)

        # Energy slider
        ctk.CTkLabel(
            self._detail,
            text="Energy",
            font=(theme.FONT_UI, theme.TEXT_XS),
            text_color=theme.TEXT_MUTED,
        ).grid(row=0, column=0, sticky="w")

        energy_row = ctk.CTkFrame(self._detail, fg_color="transparent")
        energy_row.grid(row=1, column=0, sticky="ew")
        energy_row.grid_columnconfigure(0, weight=1)

        energy_var = ctk.DoubleVar(value=self._block.energy_level)
        energy_slider = ctk.CTkSlider(
            energy_row,
            from_=1,
            to=5,
            variable=energy_var,
            command=self._on_energy_changed,
            progress_color=theme.ACCENT_CYAN,
            button_color=theme.ACCENT_CYAN,
        )
        energy_slider.grid(row=0, column=0, sticky="ew")
        self._energy_var = energy_var

        self._energy_val_label = ctk.CTkLabel(
            energy_row,
            text=str(self._block.energy_level),
            font=(theme.FONT_MONO, theme.TEXT_SM),
            text_color=theme.ACCENT_CYAN,
            width=20,
        )
        self._energy_val_label.grid(row=0, column=1, padx=(theme.SP_2, 0))

        # Archetype chip grid
        ctk.CTkLabel(
            self._detail,
            text="Archetype",
            font=(theme.FONT_UI, theme.TEXT_XS),
            text_color=theme.TEXT_MUTED,
        ).grid(row=2, column=0, sticky="w", pady=(theme.SP_2, theme.SP_1))

        chip_frame = ctk.CTkFrame(self._detail, fg_color="transparent")
        chip_frame.grid(row=3, column=0, sticky="ew")
        self._arch_chips: Dict[str, ctk.CTkButton] = {}
        archetypes = list(ARCHETYPE_SPECS.keys())
        custom_archetypes = list_custom_archetypes()

        for i, arch in enumerate(archetypes):
            spec = ARCHETYPE_SPECS[arch]
            is_active = str(self._block.archetype.value if hasattr(self._block.archetype, "value") else self._block.archetype) == arch.value
            chip_color = spec.cover_palette[0] if is_active else theme.BG_OVERLAY
            chip = ctk.CTkButton(
                chip_frame,
                text=spec.emoji,
                font=(theme.FONT_UI, theme.TEXT_SM),
                width=36,
                height=30,
                fg_color=chip_color,
                hover_color=spec.cover_palette[0],
                corner_radius=6,
                border_color=theme.ACCENT_VIOLET if is_active else "transparent",
                border_width=2 if is_active else 0,
                command=lambda a=arch: self._on_arch_chip_click(a.value),
            )
            chip.grid(row=i // 5, column=i % 5, padx=2, pady=2)
            self._arch_chips[arch.value] = chip

        # Custom archetype chips
        for j, custom in enumerate(custom_archetypes):
            idx = len(archetypes) + j
            is_active = str(self._block.archetype.value if hasattr(self._block.archetype, "value") else self._block.archetype) == custom.id
            chip = ctk.CTkButton(
                chip_frame,
                text=custom.emoji,
                font=(theme.FONT_UI, theme.TEXT_SM),
                width=36,
                height=30,
                fg_color=custom.palette_start if is_active else theme.BG_OVERLAY,
                hover_color=custom.palette_start,
                corner_radius=6,
                border_color=theme.ACCENT_VIOLET if is_active else "transparent",
                border_width=2 if is_active else 0,
                command=lambda cid=custom.id: self._on_arch_chip_click(cid),
            )
            chip.grid(row=idx // 5, column=idx % 5, padx=2, pady=2)
            self._arch_chips[custom.id] = chip

        # Genre weights — Phase 5
        ctk.CTkLabel(
            self._detail,
            text="Genre Weights",
            font=(theme.FONT_UI, theme.TEXT_XS),
            text_color=theme.TEXT_MUTED,
        ).grid(row=4, column=0, sticky="w", pady=(theme.SP_2, theme.SP_1))

        if self._store is not None:
            from waveform.ui.widgets.genre_weight_panel import GenreWeightPanel, wire_genre_panel_to_store

            session = self._store.get("session")
            if session is not None:
                self._genre_panel = GenreWeightPanel(
                    self._detail,
                    block=self._block,
                    session=session,
                    on_weights_changed=lambda bid, w: wire_genre_panel_to_store(self._store, bid, w),
                    analytics=self._analytics,
                )
                self._genre_panel.grid(row=5, column=0, sticky="ew")
        else:
            ctk.CTkLabel(
                self._detail,
                text="(Genre weights — select event to configure)",
                font=(theme.FONT_UI, theme.TEXT_XS),
                text_color=theme.TEXT_MUTED,
            ).grid(row=5, column=0, sticky="w")

    def _remove_detail_panel(self) -> None:
        if not self._detail_visible:
            return
        self._detail_visible = False
        if hasattr(self, "_detail"):
            self._detail.destroy()

    def _on_energy_changed(self, value: float) -> None:
        snapped = max(1, min(5, round(value)))
        self._energy_var.set(snapped)
        self._energy_val_label.configure(text=str(snapped))
        updated = dataclasses.replace(self._block, energy_level=snapped)
        self._block = updated
        if self._on_mutate:
            self._on_mutate(updated)

    def _on_arch_chip_click(self, arch_id: str) -> None:
        try:
            new_arch = BlockArchetype(arch_id)
        except ValueError:
            new_arch = arch_id  # type: ignore
        updated = dataclasses.replace(self._block, archetype=new_arch)
        self._block = updated
        if self._on_mutate:
            self._on_mutate(updated)
        # Rebuild detail panel to update chip highlights
        self._remove_detail_panel()
        self._build_detail_panel()

    def _handle_click(self, event: Any = None) -> None:
        if self._on_click:
            self._on_click(self._block)

    def _bind_click(self) -> None:
        self.bind("<Button-1>", self._handle_click)

    def _bind_keyboard(self) -> None:
        """Phase 2A: keyboard navigation."""
        self.bind("<Return>", self._handle_click)
        self.bind("<space>", self._handle_click)
        if self._on_delete:
            self.bind("<Delete>", lambda e: self._on_delete(self._block) if self._on_delete else None)
            self.bind("<BackSpace>", lambda e: self._on_delete(self._block) if self._on_delete else None)
        self.bind("<Up>", self._focus_prev_sibling)
        self.bind("<Down>", self._focus_next_sibling)
        theme.apply_focus_ring(self)

    def _focus_prev_sibling(self, event: Any = None) -> None:
        siblings = [w for w in self.master.winfo_children() if isinstance(w, BlockCard)]
        idx = siblings.index(self)
        if idx > 0:
            siblings[idx - 1].focus_set()

    def _focus_next_sibling(self, event: Any = None) -> None:
        siblings = [w for w in self.master.winfo_children() if isinstance(w, BlockCard)]
        idx = siblings.index(self)
        if idx < len(siblings) - 1:
            siblings[idx + 1].focus_set()

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        if selected:
            self.configure(
                fg_color=theme.BG_OVERLAY,
                border_color=theme.ACCENT_VIOLET,
                border_width=2,
            )
            self._build_detail_panel()
        else:
            self.configure(
                fg_color=theme.BG_SURFACE,
                border_color=theme.BG_OVERLAY,
                border_width=1,
            )
            self._remove_detail_panel()

    def update_block(self, block: Any, start_minute: int) -> None:
        self._block = block
        self._start_minute = start_minute
        # Rebuild header
        for widget in self.winfo_children():
            widget.destroy()
        self._detail_visible = False
        self._build_header()
        self._bind_click()
        self._bind_keyboard()
        if self._selected:
            self._build_detail_panel()

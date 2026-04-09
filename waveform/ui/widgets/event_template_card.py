"""
event_template_card.py — EventTemplateCard: template picker gallery card.

Phase 2C: custom_border kwarg for user-created templates.
Phase 11: keyboard navigation (takefocus, Return/space, focus ring).
"""
from __future__ import annotations

from typing import Any, Callable, Optional

try:
    import customtkinter as ctk  # type: ignore
    import tkinter as tk
    HAS_CTK = True
except ImportError:
    HAS_CTK = False

from waveform.domain.block import ARCHETYPE_SPECS, BlockArchetype, get_spec_for_id
from waveform.ui import theme

_TEMPLATE_EMOJI = {
    "birthday": "🎂",
    "wedding": "💍",
    "club_night": "🎧",
    "rooftop_bar": "🌇",
    "corporate_dinner": "🍽️",
    "house_party": "🏠",
    "funeral_memorial": "🕊️",
    "road_trip": "🚗",
    "workout": "💪",
    "focus_session": "🧠",
    "__custom__": "✨",
}


class EventTemplateCard(ctk.CTkFrame if HAS_CTK else object):  # type: ignore
    def __init__(
        self,
        parent: Any,
        template: Any,  # EventTemplate | None (for custom)
        on_select: Optional[Callable[[Any], None]] = None,
        custom_border: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            parent,
            fg_color=theme.BG_OVERLAY,
            corner_radius=theme.RADIUS_CARD,
            border_width=1,
            border_color=theme.ACCENT_CYAN if custom_border else theme.BG_OVERLAY,
            **kwargs,
        )
        self._template = template
        self._on_select = on_select
        self._selected = False
        self._custom_border = custom_border

        self.grid_columnconfigure(0, weight=1)

        tid = getattr(template, "id", "__custom__") if template else "__custom__"
        emoji = _TEMPLATE_EMOJI.get(tid, "🎵")
        name = getattr(template, "name", "+ Custom") if template else "+ Custom"
        desc = getattr(template, "description", "Start from scratch") if template else "Start from scratch"
        blocks = getattr(template, "default_blocks", []) if template else []

        # Emoji + name
        title_row = ctk.CTkFrame(self, fg_color="transparent")
        title_row.grid(row=0, column=0, sticky="ew", padx=theme.SP_3, pady=(theme.SP_3, theme.SP_1))
        title_row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            title_row,
            text=emoji,
            font=(theme.FONT_UI, theme.TEXT_XL),
        ).grid(row=0, column=0, padx=(0, theme.SP_2))

        ctk.CTkLabel(
            title_row,
            text=name,
            font=(theme.FONT_UI, theme.TEXT_SM, "bold"),
            text_color=theme.TEXT_PRIMARY,
            anchor="w",
        ).grid(row=0, column=1, sticky="w")

        # Description
        ctk.CTkLabel(
            self,
            text=desc,
            font=(theme.FONT_UI, theme.TEXT_XS),
            text_color=theme.TEXT_SECONDARY,
            anchor="w",
            wraplength=160,
            justify="left",
        ).grid(row=1, column=0, sticky="w", padx=theme.SP_3, pady=(0, theme.SP_2))

        # Archetype chips
        if blocks:
            chip_row = ctk.CTkFrame(self, fg_color="transparent")
            chip_row.grid(row=2, column=0, sticky="w", padx=theme.SP_3, pady=(0, theme.SP_3))
            for i, arch in enumerate(blocks[:6]):
                try:
                    spec = get_spec_for_id(str(arch.value if hasattr(arch, "value") else arch))
                    bg = spec.cover_palette[0]
                    # Auto text color for contrast
                    r, g, b = int(bg[1:3], 16), int(bg[3:5], 16), int(bg[5:7], 16)
                    lum = 0.299 * r + 0.587 * g + 0.114 * b
                    text_color = "#F5F5F7" if lum < 128 else "#1A1A1A"
                    chip = ctk.CTkLabel(
                        chip_row,
                        text=spec.emoji,
                        font=(theme.FONT_UI, theme.TEXT_XS),
                        fg_color=bg,
                        text_color=text_color,
                        corner_radius=4,
                        width=24,
                        height=20,
                    )
                    chip.grid(row=0, column=i, padx=(0, 2))
                    chip.bind("<Button-1>", self._handle_click)
                except Exception:
                    pass

        # Keyboard navigation (Phase 11)
        if HAS_CTK:
            tk.Frame.configure(self, takefocus=True)
        self.bind("<Return>", self._handle_click)
        self.bind("<space>", self._handle_click)
        self.bind("<FocusIn>", self._show_focus)
        self.bind("<FocusOut>", self._hide_focus)

        # Click binding on all children
        self.bind("<Button-1>", self._handle_click)
        for child in self.winfo_children():
            child.bind("<Button-1>", self._handle_click)
            for grandchild in child.winfo_children():
                grandchild.bind("<Button-1>", self._handle_click)

    def _handle_click(self, event: Any = None) -> None:
        if self._on_select:
            self._on_select(self._template)

    def _show_focus(self, event: Any = None) -> None:
        try:
            self.configure(border_color=theme.ACCENT_VIOLET, border_width=2)
        except Exception:
            pass

    def _hide_focus(self, event: Any = None) -> None:
        self._apply_selection_style()

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self._apply_selection_style()

    def _apply_selection_style(self) -> None:
        if self._selected:
            self.configure(
                fg_color=theme.BG_SURFACE,
                border_color=theme.ACCENT_VIOLET,
                border_width=2,
            )
        else:
            border = theme.ACCENT_CYAN if self._custom_border else theme.BG_OVERLAY
            self.configure(
                fg_color=theme.BG_OVERLAY,
                border_color=border,
                border_width=1,
            )

    @property
    def template(self) -> Any:
        return self._template

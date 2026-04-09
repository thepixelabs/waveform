"""
genre_slider.py — GenreSlider widget: one genre tag + weight slider row.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

try:
    import customtkinter as ctk  # type: ignore
    HAS_CTK = True
except ImportError:
    HAS_CTK = False

from waveform.ui import theme


class GenreSlider(ctk.CTkFrame if HAS_CTK else object):  # type: ignore
    """One genre tag row: label | slider | percentage | ✕ remove button."""

    def __init__(
        self,
        parent: Any,
        tag: str,
        weight: float,
        on_change: Optional[Callable[[str, float], None]] = None,
        on_remove: Optional[Callable[[str], None]] = None,
        on_activate: Optional[Callable[[str], None]] = None,
        inherited: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            parent,
            fg_color="transparent",
            **kwargs,
        )
        self._tag = tag
        self._weight = weight
        self._on_change = on_change
        self._on_remove = on_remove
        self._on_activate = on_activate
        self._inherited = inherited

        self.grid_columnconfigure(1, weight=1)

        # Tag label
        label_color = theme.TEXT_MUTED if inherited else theme.TEXT_SECONDARY
        self._tag_label = ctk.CTkLabel(
            self,
            text=tag,
            font=(theme.FONT_UI, theme.TEXT_SM),
            text_color=label_color,
            width=100,
            anchor="w",
        )
        self._tag_label.grid(row=0, column=0, padx=(0, theme.SP_2), sticky="w")

        if inherited:
            # Show "inherited — click to override" badge
            self._badge = ctk.CTkButton(
                self,
                text="inherited — click to override",
                font=(theme.FONT_UI, theme.TEXT_XS),
                fg_color="transparent",
                text_color=theme.TEXT_MUTED,
                hover_color=theme.BG_OVERLAY,
                height=20,
                command=lambda: self._on_activate(self._tag) if self._on_activate else None,
            )
            self._badge.grid(row=0, column=1, columnspan=2, padx=theme.SP_2, sticky="w")
            # Bind click on the whole row
            for widget in (self, self._tag_label, self._badge):
                widget.bind("<Button-1>", lambda e: self._on_activate(self._tag) if self._on_activate else None)
        else:
            # Active slider row
            self._slider_var = ctk.DoubleVar(value=weight)
            self._slider = ctk.CTkSlider(
                self,
                from_=0.0,
                to=0.8,
                variable=self._slider_var,
                command=self._handle_slider_change,
                progress_color=theme.ACCENT_VIOLET,
                button_color=theme.ACCENT_VIOLET,
                height=16,
            )
            self._slider.grid(row=0, column=1, padx=theme.SP_2, sticky="ew")

            self._pct_label = ctk.CTkLabel(
                self,
                text=f"{int(weight * 100)}%",
                font=(theme.FONT_MONO, theme.TEXT_XS),
                text_color=theme.TEXT_SECONDARY,
                width=32,
            )
            self._pct_label.grid(row=0, column=2, padx=(theme.SP_1, 0))

            if on_remove:
                self._remove_btn = ctk.CTkButton(
                    self,
                    text="✕",
                    font=(theme.FONT_UI, theme.TEXT_XS),
                    width=24,
                    height=24,
                    fg_color="transparent",
                    text_color=theme.TEXT_MUTED,
                    hover_color=theme.DANGER_RED,
                    command=lambda: on_remove(self._tag),
                )
                self._remove_btn.grid(row=0, column=3, padx=(theme.SP_1, 0))

    def _handle_slider_change(self, value: float) -> None:
        self._weight = value
        self._pct_label.configure(text=f"{int(value * 100)}%")
        if self._on_change:
            self._on_change(self._tag, value)

    @property
    def tag(self) -> str:
        return self._tag

    @property
    def weight(self) -> float:
        return self._weight

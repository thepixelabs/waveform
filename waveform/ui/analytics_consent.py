"""
analytics_consent.py — One-time analytics opt-in consent dialog.

Non-closeable. Shown 500ms after mainloop starts on first launch.
"""
from __future__ import annotations

from typing import Any, Callable

try:
    import customtkinter as ctk  # type: ignore
    HAS_CTK = True
except ImportError:
    HAS_CTK = False

from waveform.ui import theme


class AnalyticsConsentDialog(ctk.CTkToplevel if HAS_CTK else object):  # type: ignore
    def __init__(
        self,
        parent: Any,
        on_consent: Callable[[bool], None],
        **kwargs: Any,
    ) -> None:
        super().__init__(parent, **kwargs)
        self.title("Help improve Waveform")
        self.geometry("440x260")
        self.transient(parent)
        self.grab_set()
        self.focus_set()
        self.resizable(False, False)

        # Prevent closing via window manager
        self.protocol("WM_DELETE_WINDOW", lambda: None)

        self._on_consent = on_consent

        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self,
            text="Help improve Waveform?",
            font=(theme.FONT_UI, theme.TEXT_LG, "bold"),
            text_color=theme.TEXT_PRIMARY,
        ).grid(row=0, column=0, padx=theme.SP_4, pady=(theme.SP_6, theme.SP_2))

        ctk.CTkLabel(
            self,
            text=(
                "We'd like to collect anonymous usage data to understand how people use Waveform "
                "and improve the experience.\n\n"
                "No personal information, no track names, no account data is collected. "
                "You can change this in Settings at any time."
            ),
            font=(theme.FONT_UI, theme.TEXT_SM),
            text_color=theme.TEXT_SECONDARY,
            wraplength=400,
            justify="left",
        ).grid(row=1, column=0, padx=theme.SP_4, pady=(0, theme.SP_4))

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.grid(row=2, column=0, padx=theme.SP_4, pady=(0, theme.SP_6))

        ctk.CTkButton(
            btn_row,
            text="Yes, share data",
            fg_color=theme.ACCENT_VIOLET,
            font=(theme.FONT_UI, theme.TEXT_SM),
            width=160,
            height=40,
            command=lambda: self._submit(True),
        ).pack(side="left", padx=(0, theme.SP_3))

        ctk.CTkButton(
            btn_row,
            text="No thanks",
            fg_color=theme.BG_OVERLAY,
            text_color=theme.TEXT_SECONDARY,
            font=(theme.FONT_UI, theme.TEXT_SM),
            width=120,
            height=40,
            command=lambda: self._submit(False),
        ).pack(side="left")

    def _submit(self, enabled: bool) -> None:
        self.destroy()
        self._on_consent(enabled)

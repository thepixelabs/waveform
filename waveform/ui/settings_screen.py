"""
settings_screen.py — SettingsScreen: app settings modal.

Phase 2C: "Advanced" button opens PromptEditor.
"""
from __future__ import annotations

from typing import Any, Optional

try:
    import customtkinter as ctk  # type: ignore
    HAS_CTK = True
except ImportError:
    HAS_CTK = False

from waveform.ui import theme

GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-3-flash-preview",
    "gemini-3.1-pro-preview",
]


class SettingsScreen(ctk.CTkToplevel if HAS_CTK else object):  # type: ignore
    def __init__(
        self,
        parent: Any,
        store: Any,
        persistence: Any,
        analytics: Any = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(parent, **kwargs)
        self.title("Settings")
        self.geometry("480x620")
        self.transient(parent)
        self.grab_set()
        self.focus_set()
        self.resizable(False, False)

        self._store = store
        self._persistence = persistence
        self._analytics = analytics

        settings = store.get("settings") or {}

        self.grid_columnconfigure(0, weight=1)

        row = 0

        # --- Gemini model ---
        ctk.CTkLabel(
            self,
            text="AI Model",
            font=(theme.FONT_UI, theme.TEXT_XS, "bold"),
            text_color=theme.TEXT_MUTED,
        ).grid(row=row, column=0, padx=theme.SP_4, pady=(theme.SP_4, theme.SP_1), sticky="w")
        row += 1

        self._model_var = ctk.StringVar(value=settings.get("gemini_model", GEMINI_MODELS[0]))
        ctk.CTkOptionMenu(
            self,
            values=GEMINI_MODELS,
            variable=self._model_var,
            font=(theme.FONT_UI, theme.TEXT_SM),
            height=36,
        ).grid(row=row, column=0, padx=theme.SP_4, pady=(0, theme.SP_3), sticky="ew")
        row += 1

        # --- Tracks per hour ---
        ctk.CTkLabel(
            self,
            text="Tracks Per Hour",
            font=(theme.FONT_UI, theme.TEXT_XS, "bold"),
            text_color=theme.TEXT_MUTED,
        ).grid(row=row, column=0, padx=theme.SP_4, pady=(0, theme.SP_1), sticky="w")
        row += 1

        tph_row = ctk.CTkFrame(self, fg_color="transparent")
        tph_row.grid(row=row, column=0, padx=theme.SP_4, pady=(0, theme.SP_3), sticky="ew")
        tph_row.grid_columnconfigure(0, weight=1)
        row += 1

        self._tph_var = ctk.DoubleVar(value=settings.get("tracks_per_hour", 16))
        ctk.CTkSlider(
            tph_row,
            from_=8,
            to=24,
            variable=self._tph_var,
            progress_color=theme.ACCENT_VIOLET,
        ).grid(row=0, column=0, sticky="ew")

        self._tph_label = ctk.CTkLabel(
            tph_row,
            text=str(int(self._tph_var.get())),
            font=(theme.FONT_MONO, theme.TEXT_SM),
            text_color=theme.TEXT_SECONDARY,
            width=24,
        )
        self._tph_label.grid(row=0, column=1, padx=(theme.SP_2, 0))
        self._tph_var.trace_add("write", lambda *_: self._tph_label.configure(text=str(int(self._tph_var.get()))))

        # --- Toggles ---
        toggle_defs = [
            ("allow_repeats", "Allow Repeated Songs"),
            ("shuffle_within_blocks", "Shuffle Within Blocks"),
            ("analytics_enabled", "Share Anonymous Analytics"),
            ("reduce_motion", "Reduce Motion"),
        ]
        for key, label in toggle_defs:
            var = ctk.BooleanVar(value=settings.get(key, False))
            setattr(self, f"_var_{key}", var)
            ctk.CTkSwitch(
                self,
                text=label,
                variable=var,
                font=(theme.FONT_UI, theme.TEXT_SM),
                progress_color=theme.ACCENT_VIOLET,
            ).grid(row=row, column=0, padx=theme.SP_4, pady=(0, theme.SP_3), sticky="w")
            row += 1

        # --- Danger zone ---
        ctk.CTkLabel(
            self,
            text="DANGER ZONE",
            font=(theme.FONT_UI, theme.TEXT_XS, "bold"),
            text_color=theme.DANGER_RED,
        ).grid(row=row, column=0, padx=theme.SP_4, pady=(theme.SP_2, theme.SP_1), sticky="w")
        row += 1

        ctk.CTkButton(
            self,
            text="Clear song history",
            fg_color="transparent",
            border_color=theme.DANGER_RED,
            border_width=1,
            text_color=theme.DANGER_RED,
            height=36,
            command=lambda: self._confirm_danger("Clear song history?", persistence.clear_song_history),
        ).grid(row=row, column=0, padx=theme.SP_4, pady=(0, theme.SP_2), sticky="ew")
        row += 1

        ctk.CTkButton(
            self,
            text="Clear all sessions",
            fg_color="transparent",
            border_color=theme.DANGER_RED,
            border_width=1,
            text_color=theme.DANGER_RED,
            height=36,
            command=lambda: self._confirm_danger("Delete all session history?", persistence.clear_all_sessions),
        ).grid(row=row, column=0, padx=theme.SP_4, pady=(0, theme.SP_3), sticky="ew")
        row += 1

        # --- Buttons row ---
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.grid(row=row, column=0, padx=theme.SP_4, pady=(0, theme.SP_3), sticky="ew")
        btn_row.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(
            btn_row,
            text="Close",
            fg_color=theme.BG_OVERLAY,
            command=lambda: (self._save_settings(), self.destroy()),
            width=120,
        ).grid(row=0, column=0, sticky="e", padx=(0, theme.SP_2))

        ctk.CTkButton(
            btn_row,
            text="Advanced",
            fg_color="transparent",
            text_color=theme.TEXT_MUTED,
            border_color=theme.BG_OVERLAY,
            border_width=1,
            width=100,
            command=self._open_prompt_editor,
        ).grid(row=0, column=1)

    def _save_settings(self) -> None:
        settings = self._store.get("settings") or {}
        settings["gemini_model"] = self._model_var.get()
        settings["tracks_per_hour"] = int(self._tph_var.get())
        for key, _ in [
            ("allow_repeats", None),
            ("shuffle_within_blocks", None),
            ("analytics_enabled", None),
            ("reduce_motion", None),
        ]:
            var = getattr(self, f"_var_{key}", None)
            if var is not None:
                settings[key] = var.get()
        self._persistence.save_settings(settings)
        self._store.set("settings", settings)
        if self._analytics:
            self._analytics.set_enabled(settings.get("analytics_enabled", False))

    def _confirm_danger(self, message: str, action: Any) -> None:
        dialog = _ConfirmDialog(self, message=message, on_confirm=action)

    def _open_prompt_editor(self) -> None:
        from waveform.ui.prompt_editor import PromptEditor
        PromptEditor(self, persistence=self._persistence)


class _ConfirmDialog(ctk.CTkToplevel if HAS_CTK else object):  # type: ignore
    def __init__(self, parent: Any, message: str, on_confirm: Any, **kwargs: Any) -> None:
        super().__init__(parent, **kwargs)
        self.title("Confirm")
        self.geometry("320x140")
        self.transient(parent)
        self.grab_set()
        self.focus_set()

        ctk.CTkLabel(
            self,
            text=message,
            font=(theme.FONT_UI, theme.TEXT_SM),
            wraplength=280,
        ).pack(padx=theme.SP_4, pady=(theme.SP_4, theme.SP_2))

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(padx=theme.SP_4)

        ctk.CTkButton(
            row,
            text="Confirm",
            fg_color=theme.DANGER_RED,
            command=lambda: (self.destroy(), on_confirm()),
            width=100,
        ).pack(side="left", padx=(0, theme.SP_2))

        ctk.CTkButton(
            row,
            text="Cancel",
            fg_color=theme.BG_OVERLAY,
            command=self.destroy,
            width=100,
        ).pack(side="left")

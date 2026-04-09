"""
prompt_editor.py — PromptEditor: in-app master prompt editor modal.

Phase 2C: full implementation with collapsible guidance sidebar,
save/reset/cancel with unsaved-changes guard.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    import customtkinter as ctk  # type: ignore
    HAS_CTK = True
except ImportError:
    HAS_CTK = False

from waveform.ui import theme

_BUNDLED_PROMPT = str(Path(__file__).parent.parent / "prompts" / "master_prompt.md")

_GUIDANCE_SECTIONS = [
    ("CORE RULES", "One song per line. Title — Artist format. No extra commentary."),
    ("QUALITY STANDARD", "Real songs only. No AI-generated filler. Verify artist exists."),
    ("LANGUAGE NOTES", "English by default. Match event vibe language if specified."),
    ("PARTY CONTEXT", "Block archetype and energy level are injected automatically."),
    ("ARTIST POOL", "Prefer variety. Max 2 songs per artist unless instructed otherwise."),
    ("LANGUAGE MIX", "Match the genre instruction's cultural context for best results."),
]


class PromptEditor(ctk.CTkToplevel if HAS_CTK else object):  # type: ignore
    def __init__(
        self,
        parent: Any,
        persistence: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(parent, **kwargs)
        self.title("Edit Master Prompt")
        self.geometry("780x560")
        self.transient(parent)
        self.grab_set()
        self.focus_set()
        self.resizable(True, True)

        self._persistence = persistence
        self._original_text: str = ""
        self._sidebar_visible = True

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0)

        # Main editor
        editor_outer = ctk.CTkFrame(self, fg_color=theme.BG_SURFACE)
        editor_outer.grid(row=0, column=0, sticky="nsew", padx=(0, 1))
        editor_outer.grid_rowconfigure(1, weight=1)
        editor_outer.grid_columnconfigure(0, weight=1)

        toolbar = ctk.CTkFrame(editor_outer, fg_color="transparent")
        toolbar.grid(row=0, column=0, sticky="ew", padx=theme.SP_3, pady=(theme.SP_3, 0))

        ctk.CTkLabel(
            toolbar,
            text="Master Prompt",
            font=(theme.FONT_UI, theme.TEXT_SM, "bold"),
            text_color=theme.TEXT_PRIMARY,
        ).pack(side="left")

        ctk.CTkButton(
            toolbar,
            text="⟵ Guide",
            font=(theme.FONT_UI, theme.TEXT_XS),
            fg_color="transparent",
            text_color=theme.TEXT_MUTED,
            width=70,
            height=28,
            command=self._toggle_sidebar,
        ).pack(side="right")

        self._textbox = ctk.CTkTextbox(
            editor_outer,
            font=(theme.FONT_MONO, theme.TEXT_SM),
            fg_color=theme.BG_BASE,
            text_color=theme.TEXT_PRIMARY,
            wrap="word",
        )
        self._textbox.grid(row=1, column=0, sticky="nsew", padx=theme.SP_3, pady=theme.SP_2)

        # Load content
        text = persistence.load_master_prompt(fallback_path=_BUNDLED_PROMPT)
        self._textbox.insert("1.0", text)
        self._original_text = text

        # Toast label
        self._toast_var = ctk.StringVar(value="")
        self._toast_label = ctk.CTkLabel(
            editor_outer,
            textvariable=self._toast_var,
            font=(theme.FONT_UI, theme.TEXT_XS),
            text_color=theme.SUCCESS_GREEN,
        )
        self._toast_label.grid(row=2, column=0, padx=theme.SP_3, sticky="w")

        # Button row
        btn_row = ctk.CTkFrame(editor_outer, fg_color="transparent")
        btn_row.grid(row=3, column=0, padx=theme.SP_3, pady=(0, theme.SP_3), sticky="ew")
        btn_row.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(
            btn_row,
            text="Save",
            fg_color=theme.ACCENT_VIOLET,
            width=100,
            command=self._save,
        ).grid(row=0, column=0, sticky="e", padx=(0, theme.SP_2))

        ctk.CTkButton(
            btn_row,
            text="Reset to default",
            fg_color="transparent",
            text_color=theme.TEXT_MUTED,
            border_color=theme.BG_OVERLAY,
            border_width=1,
            width=130,
            command=self._reset,
        ).grid(row=0, column=1)

        ctk.CTkButton(
            btn_row,
            text="Cancel",
            fg_color=theme.BG_OVERLAY,
            width=80,
            command=self._cancel,
        ).grid(row=0, column=2, padx=(theme.SP_2, 0))

        # Guidance sidebar
        self._sidebar = ctk.CTkFrame(self, fg_color=theme.BG_OVERLAY, width=210)
        self._sidebar.grid(row=0, column=1, sticky="nsew", padx=(0, 0))
        self._sidebar.grid_propagate(False)
        self._sidebar.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self._sidebar,
            text="PROMPT GUIDE",
            font=(theme.FONT_UI, theme.TEXT_XS, "bold"),
            text_color=theme.TEXT_MUTED,
        ).grid(row=0, column=0, padx=theme.SP_3, pady=(theme.SP_3, theme.SP_2), sticky="w")

        for i, (section, desc) in enumerate(_GUIDANCE_SECTIONS):
            ctk.CTkLabel(
                self._sidebar,
                text=section,
                font=(theme.FONT_UI, theme.TEXT_XS, "bold"),
                text_color=theme.ACCENT_VIOLET,
                anchor="w",
            ).grid(row=i * 2 + 1, column=0, padx=theme.SP_3, sticky="w")
            ctk.CTkLabel(
                self._sidebar,
                text=desc,
                font=(theme.FONT_UI, theme.TEXT_XS),
                text_color=theme.TEXT_MUTED,
                anchor="w",
                wraplength=190,
                justify="left",
            ).grid(row=i * 2 + 2, column=0, padx=theme.SP_3, pady=(0, theme.SP_2), sticky="w")

        self.protocol("WM_DELETE_WINDOW", self._cancel)

    def _toggle_sidebar(self) -> None:
        if self._sidebar_visible:
            self._sidebar.grid_remove()
        else:
            self._sidebar.grid()
        self._sidebar_visible = not self._sidebar_visible

    def _save(self) -> None:
        text = self._textbox.get("1.0", "end-1c")
        try:
            self._persistence.save_master_prompt(text)
            self._original_text = text
            self._show_toast("Prompt saved.", color=theme.SUCCESS_GREEN)
        except Exception as exc:
            self._show_toast(f"Error: {exc}", color=theme.DANGER_RED)

    def _reset(self) -> None:
        try:
            import tkinter.messagebox as mb
            if not mb.askyesno("Reset Prompt", "Reset to the bundled default? Your changes will be lost."):
                return
        except Exception:
            pass
        # Try .example first, fall back to default
        example = Path(_BUNDLED_PROMPT).with_suffix(".md.example")
        src = example if example.exists() else Path(_BUNDLED_PROMPT)
        try:
            text = src.read_text(encoding="utf-8")
        except Exception:
            text = ""
        self._textbox.delete("1.0", "end")
        self._textbox.insert("1.0", text)

    def _cancel(self) -> None:
        current = self._textbox.get("1.0", "end-1c")
        if current != self._original_text:
            try:
                import tkinter.messagebox as mb
                if not mb.askyesno("Discard changes?", "You have unsaved changes. Discard them?"):
                    return
            except Exception:
                pass
        self.destroy()

    def _show_toast(self, message: str, color: str = theme.TEXT_SECONDARY) -> None:
        self._toast_var.set(message)
        self._toast_label.configure(text_color=color)
        self.after(4000, lambda: self._toast_var.set(""))

"""
archetype_editor.py — ArchetypeEditor: create/edit/delete custom block archetypes.

Phase 2B. User-defined archetypes stored via persistence and loaded into the
block registry at startup.
"""
from __future__ import annotations

import uuid
from typing import Any, Callable, List, Optional

try:
    import customtkinter as ctk  # type: ignore
    HAS_CTK = True
except ImportError:
    HAS_CTK = False

from waveform.domain.block import (
    CustomArchetype,
    list_custom_archetypes,
    register_custom_archetypes,
)
from waveform.ui import theme

_EMOJI_OPTIONS = [
    "🎵", "🎸", "🎹", "🎺", "🎻", "🥁", "🎷", "🪗", "🎤", "🎧",
    "💃", "🕺", "🌊", "🌅", "🌙", "⚡", "🔥", "💫", "✨", "🎉",
]

_COLOR_OPTIONS = [
    "#FF6B35", "#7C3AED", "#22D3EE", "#E040FB", "#34D399",
    "#FBBF24", "#F87171", "#60A5FA", "#A78BFA", "#34D399",
    "#1A0533", "#0A2540", "#2D1B00", "#000000", "#FAF7F2",
]


class ArchetypeEditor(ctk.CTkToplevel if HAS_CTK else object):  # type: ignore
    def __init__(
        self,
        parent: Any,
        persistence: Any,
        store: Any = None,
        on_saved: Optional[Callable] = None,
        edit_id: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(parent, **kwargs)
        self.title("Custom Archetype")
        self.geometry("560x620")
        self.transient(parent)
        self.grab_set()
        self.focus_set()
        self.resizable(False, True)

        self._persistence = persistence
        self._store = store
        self._on_saved = on_saved
        self._edit_id = edit_id
        self._editing: Optional[CustomArchetype] = None

        # Load existing if editing
        if edit_id:
            from waveform.domain.block import get_custom_archetype
            self._editing = get_custom_archetype(edit_id)

        self.grid_columnconfigure(0, weight=1)

        # List panel
        self._list_frame = ctk.CTkScrollableFrame(self, fg_color=theme.BG_SURFACE, height=180)
        self._list_frame.grid(row=0, column=0, sticky="ew", padx=theme.SP_3, pady=(theme.SP_3, 0))
        self._list_frame.grid_columnconfigure(0, weight=1)
        self._rebuild_list()

        ctk.CTkLabel(
            self,
            text="CREATE / EDIT",
            font=(theme.FONT_UI, theme.TEXT_XS, "bold"),
            text_color=theme.TEXT_MUTED,
        ).grid(row=1, column=0, padx=theme.SP_4, pady=(theme.SP_3, theme.SP_1), sticky="w")

        form = ctk.CTkFrame(self, fg_color=theme.BG_SURFACE)
        form.grid(row=2, column=0, sticky="ew", padx=theme.SP_3, pady=(0, theme.SP_2))
        form.grid_columnconfigure(1, weight=1)

        # Name
        ctk.CTkLabel(form, text="Name", font=(theme.FONT_UI, theme.TEXT_XS), text_color=theme.TEXT_MUTED).grid(row=0, column=0, padx=theme.SP_3, pady=(theme.SP_3, theme.SP_1), sticky="w")
        self._name_var = ctk.StringVar(value=getattr(self._editing, "name", ""))
        ctk.CTkEntry(form, textvariable=self._name_var, height=32, font=(theme.FONT_UI, theme.TEXT_SM)).grid(row=0, column=1, padx=(0, theme.SP_3), pady=(theme.SP_3, theme.SP_1), sticky="ew")

        # Emoji picker
        ctk.CTkLabel(form, text="Emoji", font=(theme.FONT_UI, theme.TEXT_XS), text_color=theme.TEXT_MUTED).grid(row=1, column=0, padx=theme.SP_3, pady=(0, theme.SP_1), sticky="w")
        emoji_frame = ctk.CTkFrame(form, fg_color="transparent")
        emoji_frame.grid(row=1, column=1, padx=(0, theme.SP_3), sticky="w")
        self._emoji_var = ctk.StringVar(value=getattr(self._editing, "emoji", "🎵"))
        for i, em in enumerate(_EMOJI_OPTIONS):
            btn = ctk.CTkButton(
                emoji_frame,
                text=em,
                width=30,
                height=30,
                font=(theme.FONT_UI, theme.TEXT_SM),
                fg_color=theme.ACCENT_VIOLET if em == self._emoji_var.get() else theme.BG_OVERLAY,
                command=lambda e=em: self._select_emoji(e),
            )
            btn.grid(row=i // 10, column=i % 10, padx=1, pady=1)

        # Description
        ctk.CTkLabel(form, text="Description", font=(theme.FONT_UI, theme.TEXT_XS), text_color=theme.TEXT_MUTED).grid(row=2, column=0, padx=theme.SP_3, pady=(0, theme.SP_1), sticky="w")
        self._desc_var = ctk.StringVar(value=getattr(self._editing, "description", ""))
        ctk.CTkEntry(form, textvariable=self._desc_var, height=32, font=(theme.FONT_UI, theme.TEXT_SM)).grid(row=2, column=1, padx=(0, theme.SP_3), sticky="ew")

        # Palette start/end
        ctk.CTkLabel(form, text="Colour Start", font=(theme.FONT_UI, theme.TEXT_XS), text_color=theme.TEXT_MUTED).grid(row=3, column=0, padx=theme.SP_3, pady=(theme.SP_2, theme.SP_1), sticky="w")
        self._start_var = ctk.StringVar(value=getattr(self._editing, "palette_start", "#1A0533"))
        self._start_strip = self._make_color_strip(form, self._start_var, row=3)

        ctk.CTkLabel(form, text="Colour End", font=(theme.FONT_UI, theme.TEXT_XS), text_color=theme.TEXT_MUTED).grid(row=4, column=0, padx=theme.SP_3, pady=(0, theme.SP_1), sticky="w")
        self._end_var = ctk.StringVar(value=getattr(self._editing, "palette_end", "#6B2FFA"))
        self._end_strip = self._make_color_strip(form, self._end_var, row=4)

        # Energy
        ctk.CTkLabel(form, text="Default Energy", font=(theme.FONT_UI, theme.TEXT_XS), text_color=theme.TEXT_MUTED).grid(row=5, column=0, padx=theme.SP_3, pady=(theme.SP_2, theme.SP_3), sticky="w")
        self._energy_var = ctk.DoubleVar(value=getattr(self._editing, "energy", 3))
        energy_row = ctk.CTkFrame(form, fg_color="transparent")
        energy_row.grid(row=5, column=1, padx=(0, theme.SP_3), sticky="ew", pady=(theme.SP_2, theme.SP_3))
        energy_row.grid_columnconfigure(0, weight=1)
        ctk.CTkSlider(energy_row, from_=1, to=5, variable=self._energy_var).grid(row=0, column=0, sticky="ew")
        self._energy_lbl = ctk.CTkLabel(energy_row, text=str(int(self._energy_var.get())), font=(theme.FONT_MONO, theme.TEXT_SM), text_color=theme.ACCENT_CYAN, width=20)
        self._energy_lbl.grid(row=0, column=1, padx=(theme.SP_1, 0))
        self._energy_var.trace_add("write", lambda *_: self._energy_lbl.configure(text=str(int(self._energy_var.get()))))

        # Buttons
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.grid(row=3, column=0, padx=theme.SP_4, pady=(0, theme.SP_3))

        ctk.CTkButton(btn_row, text="Save", fg_color=theme.ACCENT_VIOLET, width=100, command=self._on_save).pack(side="left", padx=(0, theme.SP_2))
        ctk.CTkButton(btn_row, text="Cancel", fg_color=theme.BG_OVERLAY, width=80, command=self.destroy).pack(side="left")

    def _make_color_strip(self, parent: Any, var: Any, row: int) -> Any:
        strip_frame = ctk.CTkFrame(parent, fg_color="transparent")
        strip_frame.grid(row=row, column=1, padx=(0, theme.SP_3), sticky="w")
        current = var.get()
        for c in _COLOR_OPTIONS:
            is_sel = c == current
            btn = ctk.CTkButton(
                strip_frame,
                text="✓" if is_sel else "",
                width=24,
                height=24,
                fg_color=c,
                text_color="#FFFFFF",
                corner_radius=4,
                command=lambda col=c, v=var, sf=strip_frame: self._select_color(col, v, sf),
            )
            btn.pack(side="left", padx=1)
        return strip_frame

    def _select_color(self, color: str, var: Any, strip_frame: Any) -> None:
        var.set(color)
        for btn in strip_frame.winfo_children():
            btn_color = btn.cget("fg_color")
            btn.configure(text="✓" if btn_color == color else "")

    def _select_emoji(self, emoji: str) -> None:
        self._emoji_var.set(emoji)
        # Update button highlights in emoji_frame
        # (simplified — just store the value)

    def _on_save(self) -> None:
        name = self._name_var.get().strip()
        if not name:
            return

        existing = list_custom_archetypes()
        if len(existing) >= 20 and self._edit_id is None:
            self._store.set("toast", {"message": "Maximum 20 custom archetypes reached.", "type": "error"})
            return

        archetype_id = self._edit_id or f"custom_{uuid.uuid4().hex[:8]}"
        custom = CustomArchetype(
            id=archetype_id,
            name=name,
            emoji=self._emoji_var.get(),
            description=self._desc_var.get().strip()[:100],
            palette_start=self._start_var.get(),
            palette_end=self._end_var.get(),
            energy=int(self._energy_var.get()),
        )

        # Persist
        raw = self._persistence.load_custom_archetypes()
        raw = [r for r in raw if r.get("id") != archetype_id]
        raw.append(custom.to_dict())
        self._persistence.save_custom_archetypes(raw)

        # Re-register
        all_custom = [CustomArchetype.from_dict(r) for r in raw]
        register_custom_archetypes(all_custom)

        if self._store:
            self._store.set("custom_archetypes_updated", True)

        if self._on_saved:
            self._on_saved()

        self.destroy()

    def _rebuild_list(self) -> None:
        for w in self._list_frame.winfo_children():
            w.destroy()
        archetypes = list_custom_archetypes()
        if not archetypes:
            ctk.CTkLabel(
                self._list_frame,
                text="No custom archetypes yet",
                font=(theme.FONT_UI, theme.TEXT_XS),
                text_color=theme.TEXT_MUTED,
            ).grid(row=0, column=0, pady=theme.SP_3)
            return
        for i, a in enumerate(archetypes):
            row = ctk.CTkFrame(self._list_frame, fg_color=theme.BG_OVERLAY, corner_radius=8)
            row.grid(row=i, column=0, sticky="ew", pady=(0, theme.SP_1))
            row.grid_columnconfigure(1, weight=1)

            ctk.CTkLabel(row, text=a.emoji, font=(theme.FONT_UI, theme.TEXT_MD), width=30).grid(row=0, column=0, padx=theme.SP_2)
            ctk.CTkLabel(row, text=a.name, font=(theme.FONT_UI, theme.TEXT_SM), text_color=theme.TEXT_PRIMARY, anchor="w").grid(row=0, column=1, sticky="w")

            ctk.CTkButton(
                row, text="Delete", fg_color="transparent", text_color=theme.DANGER_RED, width=60, height=24,
                command=lambda aid=a.id: self._delete_archetype(aid),
            ).grid(row=0, column=2, padx=theme.SP_2)

    def _delete_archetype(self, archetype_id: str) -> None:
        raw = self._persistence.load_custom_archetypes()
        raw = [r for r in raw if r.get("id") != archetype_id]
        self._persistence.save_custom_archetypes(raw)
        all_custom = [CustomArchetype.from_dict(r) for r in raw]
        register_custom_archetypes(all_custom)
        if self._store:
            self._store.set("custom_archetypes_updated", True)
        self._rebuild_list()

"""
event_setup.py — EventSetupScreen: template picker + detail panel.

Phase 2C: Save as template, custom template gallery, context menu delete.
"""
from __future__ import annotations

import dataclasses
import uuid
from typing import Any, Dict, List, Optional

try:
    import customtkinter as ctk  # type: ignore
    HAS_CTK = True
except ImportError:
    HAS_CTK = False

from waveform.domain.block import Block, BlockArchetype
from waveform.domain.event import BUILTIN_TEMPLATES, EventTemplate, get_template
from waveform.domain.session import PlaylistSession
from waveform.ui import theme
from waveform.ui.widgets.event_template_card import EventTemplateCard


class EventSetupScreen(ctk.CTkFrame if HAS_CTK else object):  # type: ignore
    def __init__(
        self,
        parent: Any,
        store: Any,
        analytics: Any = None,
        persistence: Any = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(parent, fg_color=theme.BG_BASE, **kwargs)
        self._store = store
        self._analytics = analytics
        self._persistence = persistence
        self._selected_template: Optional[EventTemplate] = None
        self._cards: Dict[str, EventTemplateCard] = {}
        self._gallery_scroll: Optional[Any] = None

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=0)

        self._build_gallery()
        self._build_detail_panel()
        self._select_template(BUILTIN_TEMPLATES[0])

    def _build_gallery(self) -> None:
        gallery_outer = ctk.CTkFrame(self, fg_color=theme.BG_SURFACE)
        gallery_outer.grid(row=0, column=0, sticky="nsew", padx=(0, 1))
        gallery_outer.grid_rowconfigure(1, weight=1)
        gallery_outer.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            gallery_outer,
            text="CHOOSE EVENT TYPE",
            font=(theme.FONT_UI, theme.TEXT_XS, "bold"),
            text_color=theme.TEXT_MUTED,
        ).grid(row=0, column=0, padx=theme.SP_4, pady=(theme.SP_4, theme.SP_2), sticky="w")

        scroll = ctk.CTkScrollableFrame(gallery_outer, fg_color="transparent")
        scroll.grid(row=1, column=0, sticky="nsew", padx=theme.SP_2, pady=(0, theme.SP_2))
        self._gallery_scroll = scroll

        self._render_gallery_cards(scroll)

    def _render_gallery_cards(self, scroll: Any) -> None:
        for w in scroll.winfo_children():
            w.destroy()
        self._cards.clear()

        all_templates: List[Optional[EventTemplate]] = list(BUILTIN_TEMPLATES)

        # Custom templates (Phase 2C)
        if self._persistence:
            for raw in self._persistence.load_custom_templates():
                tpl = self._custom_dict_to_template(raw)
                if tpl:
                    all_templates.append(tpl)

        # Blank slate "custom" card
        all_templates.append(None)

        col_count = 3
        for i, tpl in enumerate(all_templates):
            tid = getattr(tpl, "id", "__custom__") if tpl else "__custom__"
            is_user = getattr(tpl, "is_user_template", False)
            card = EventTemplateCard(
                scroll,
                template=tpl,
                on_select=self._select_template,
                custom_border=is_user,
            )
            card.grid(row=i // col_count, column=i % col_count, padx=theme.SP_1, pady=theme.SP_1, sticky="nsew")
            self._cards[tid] = card

            if is_user and tpl:
                self._bind_custom_card_context_menu(card, tpl)

        for c in range(col_count):
            scroll.grid_columnconfigure(c, weight=1)

        # Re-apply selection
        if self._selected_template:
            tid = getattr(self._selected_template, "id", "__custom__")
            if tid in self._cards:
                self._cards[tid].set_selected(True)

    def _rebuild_gallery(self) -> None:
        if self._gallery_scroll:
            self._render_gallery_cards(self._gallery_scroll)

    def _build_detail_panel(self) -> None:
        detail_outer = ctk.CTkFrame(self, fg_color=theme.BG_SURFACE, width=340)
        detail_outer.grid(row=0, column=1, sticky="nsew")
        detail_outer.grid_propagate(False)
        detail_outer.grid_rowconfigure(0, weight=1)
        detail_outer.grid_columnconfigure(0, weight=1)

        detail_scroll = ctk.CTkScrollableFrame(detail_outer, fg_color="transparent")
        detail_scroll.grid(row=0, column=0, sticky="nsew", padx=theme.SP_3, pady=theme.SP_3)
        detail_scroll.grid_columnconfigure(0, weight=1)

        # Event name
        ctk.CTkLabel(
            detail_scroll,
            text="Event Name",
            font=(theme.FONT_UI, theme.TEXT_XS),
            text_color=theme.TEXT_MUTED,
        ).grid(row=0, column=0, sticky="w", pady=(0, theme.SP_1))

        self._event_name_var = ctk.StringVar()
        self._event_name_entry = ctk.CTkEntry(
            detail_scroll,
            textvariable=self._event_name_var,
            placeholder_text="e.g. Maya's 30th",
            font=(theme.FONT_UI, theme.TEXT_SM),
            height=36,
        )
        self._event_name_entry.grid(row=1, column=0, sticky="ew", pady=(0, theme.SP_3))
        self._last_auto_name: Optional[str] = None

        # Vibe description
        ctk.CTkLabel(
            detail_scroll,
            text="Vibe / Description",
            font=(theme.FONT_UI, theme.TEXT_XS),
            text_color=theme.TEXT_MUTED,
        ).grid(row=2, column=0, sticky="w", pady=(0, theme.SP_1))

        self._vibe_text = ctk.CTkTextbox(
            detail_scroll,
            height=90,
            font=(theme.FONT_UI, theme.TEXT_SM),
            fg_color=theme.BG_OVERLAY,
        )
        self._vibe_text.grid(row=3, column=0, sticky="ew", pady=(0, theme.SP_1))
        self._vibe_text.bind("<KeyRelease>", self._on_vibe_changed)

        self._char_count_label = ctk.CTkLabel(
            detail_scroll,
            text="0 / 300",
            font=(theme.FONT_UI, theme.TEXT_XS),
            text_color=theme.TEXT_MUTED,
        )
        self._char_count_label.grid(row=4, column=0, sticky="e", pady=(0, theme.SP_3))

        # Metadata toggles
        toggle_defs = [
            ("Venue", ["Indoor", "Outdoor"]),
            ("Size", ["Intimate", "Medium", "Large"]),
            ("Formality", ["Casual", "Semi-formal", "Formal"]),
            ("Time of day", ["Afternoon", "Evening", "Late night"]),
            ("Age range", ["All ages", "Adult", "21+"]),
        ]
        self._toggle_vars: Dict[str, ctk.StringVar] = {}
        row_idx = 5
        for label, options in toggle_defs:
            ctk.CTkLabel(
                detail_scroll,
                text=label,
                font=(theme.FONT_UI, theme.TEXT_XS),
                text_color=theme.TEXT_MUTED,
            ).grid(row=row_idx, column=0, sticky="w", pady=(0, theme.SP_1))
            row_idx += 1

            var = ctk.StringVar(value=options[0])
            self._toggle_vars[label] = var
            seg = ctk.CTkSegmentedButton(
                detail_scroll,
                values=options,
                variable=var,
                font=(theme.FONT_UI, theme.TEXT_XS),
                height=28,
            )
            seg.grid(row=row_idx, column=0, sticky="ew", pady=(0, theme.SP_3))
            row_idx += 1

        # Start Building button
        self._start_btn = ctk.CTkButton(
            detail_scroll,
            text="Start Building →",
            font=(theme.FONT_UI, theme.TEXT_SM, "bold"),
            fg_color=theme.ACCENT_VIOLET,
            hover_color="#6830D0",
            height=44,
            command=self._on_start_building,
        )
        self._start_btn.grid(row=row_idx, column=0, sticky="ew", pady=(0, theme.SP_2))
        theme.apply_focus_ring(self._start_btn)
        row_idx += 1

        # Save as template (Phase 2C)
        if self._persistence:
            self._save_tpl_btn = ctk.CTkButton(
                detail_scroll,
                text="Save as template",
                font=(theme.FONT_UI, theme.TEXT_XS),
                fg_color="transparent",
                border_color=theme.BG_OVERLAY,
                border_width=1,
                text_color=theme.TEXT_MUTED,
                height=32,
                command=self._on_save_as_template,
            )
            self._save_tpl_btn.grid(row=row_idx, column=0, sticky="ew")

    def _select_template(self, template: Optional[EventTemplate]) -> None:
        # Deselect old
        if self._selected_template:
            old_id = getattr(self._selected_template, "id", "__custom__")
            if old_id in self._cards:
                self._cards[old_id].set_selected(False)

        self._selected_template = template
        tid = getattr(template, "id", "__custom__") if template else "__custom__"
        if tid in self._cards:
            self._cards[tid].set_selected(True)

        # Auto-fill event name (smart: only if empty or was a previous auto-fill)
        name = getattr(template, "name", "") if template else ""
        current_name = self._event_name_var.get()
        if not current_name or current_name == self._last_auto_name:
            self._event_name_var.set(name)
            self._last_auto_name = name

        if self._analytics and template:
            self._analytics.event_template_selected(
                template_id=tid,
                has_vibe_text=bool(self._vibe_text.get("1.0", "end-1c").strip()),
            )

        self._store.set("selected_template", template)

    def _on_vibe_changed(self, event: Any = None) -> None:
        text = self._vibe_text.get("1.0", "end-1c")
        if len(text) > 300:
            self._vibe_text.delete("300", "end")
            text = text[:300]
        count = len(text)
        color = theme.WARNING_AMBER if count > 250 else theme.TEXT_MUTED
        self._char_count_label.configure(text=f"{count} / 300", text_color=color)

    def _on_start_building(self) -> None:
        from waveform.app.state import AppScreen

        template = self._selected_template
        event_name = self._event_name_var.get().strip() or (getattr(template, "name", "My Event") if template else "My Event")
        vibe_text = self._vibe_text.get("1.0", "end-1c").strip()

        # Collect toggle metadata and append to vibe
        toggle_meta = self._collect_toggle_meta()
        vibe_override = vibe_text
        if toggle_meta:
            vibe_override = (vibe_text + "\n" + toggle_meta).strip() if vibe_text else toggle_meta

        blocks = self._blocks_from_template(template)

        session = PlaylistSession(
            session_id=str(uuid.uuid4()),
            event_name=event_name,
            event_template=template,
            blocks=blocks,
            vibe_override=vibe_override,
        )

        self._store.set("session", session)
        self._store.set("selected_template", template)
        self._store.set("current_screen", AppScreen.TIMELINE)

        if self._analytics:
            self._analytics.session_started(event_type=getattr(template, "id", "") if template else "")

    def _collect_toggle_meta(self) -> str:
        parts = []
        for label, var in self._toggle_vars.items():
            val = var.get()
            parts.append(f"{label}: {val}")
        return "  ".join(parts) + "." if parts else ""

    def _blocks_from_template(self, template: Optional[EventTemplate]) -> List[Block]:
        if template is None:
            return [Block.from_archetype(BlockArchetype.ARRIVAL, duration_minutes=60)]

        archetypes = template.default_blocks
        duration = template.suggested_duration
        n = len(archetypes)
        per_block = max(15, (duration // n // 5) * 5)  # rounded to 5, min 15

        blocks = []
        for arch in archetypes:
            block = Block.from_archetype(
                arch,
                duration_minutes=per_block,
                genre_weights=list(template.default_genre_weights),
            )
            blocks.append(block)
        return blocks

    def _on_save_as_template(self) -> None:
        if not self._persistence:
            return
        dialog = _SaveTemplateDialog(
            parent=self,
            on_save=self._do_save_template,
        )

    def _do_save_template(self, name: str) -> None:
        if not name or not self._persistence:
            return
        template = self._selected_template
        blocks = self._blocks_from_template(template)
        tpl_data = {
            "id": f"custom_{uuid.uuid4().hex[:8]}",
            "name": name,
            "description": self._vibe_text.get("1.0", "end-1c").strip()[:100],
            "default_blocks": [str(b.archetype.value if hasattr(b.archetype, "value") else b.archetype) for b in blocks],
            "default_genre_weights": [
                {"tag": gw.tag, "weight": gw.weight}
                for gw in (getattr(template, "default_genre_weights", []) if template else [])
            ],
            "skin_id": getattr(template, "skin_id", "house_party") if template else "house_party",
            "suggested_duration": getattr(template, "suggested_duration", 240) if template else 240,
            "accent_color": getattr(template, "accent_color", theme.ACCENT_VIOLET) if template else theme.ACCENT_VIOLET,
        }
        try:
            self._persistence.save_custom_template(tpl_data)
            self._rebuild_gallery()
        except Exception as exc:
            self._store.set("toast", {"message": f"Could not save template: {exc}", "type": "error"})

    def _custom_dict_to_template(self, data: dict) -> Optional[EventTemplate]:
        """Convert a persisted custom template dict to an EventTemplate instance."""
        try:
            from waveform.domain.genre import GenreWeight as GW
            blocks = []
            for arch_str in data.get("default_blocks", []):
                try:
                    blocks.append(BlockArchetype(arch_str))
                except ValueError:
                    pass
            genre_weights = []
            for gw_data in data.get("default_genre_weights", []):
                try:
                    genre_weights.append(GW(tag=gw_data["tag"], weight=float(gw_data["weight"])))
                except Exception:
                    pass

            tpl = EventTemplate(
                id=data.get("id", f"custom_{uuid.uuid4().hex[:8]}"),
                name=data.get("name", "Custom"),
                description=data.get("description", ""),
                default_blocks=blocks,
                default_genre_weights=genre_weights,
                skin_id=data.get("skin_id", "house_party"),
                suggested_duration=int(data.get("suggested_duration", 240)),
                accent_color=data.get("accent_color", theme.ACCENT_VIOLET),
            )
            tpl.is_user_template = True  # type: ignore
            return tpl
        except Exception:
            return None

    def _bind_custom_card_context_menu(self, card: EventTemplateCard, tpl: EventTemplate) -> None:
        def _show_menu(event: Any) -> None:
            try:
                import tkinter as tk
                menu = tk.Menu(card, tearoff=0)
                menu.add_command(label="Delete template", command=lambda: self._delete_custom_template(tpl))
                menu.tk_popup(event.x_root, event.y_root)
            except Exception:
                pass

        card.bind("<Button-2>", _show_menu)
        card.bind("<Button-3>", _show_menu)
        # Ctrl+Click
        card.bind("<Control-Button-1>", _show_menu)

    def _delete_custom_template(self, tpl: EventTemplate) -> None:
        if not self._persistence:
            return
        try:
            import tkinter.messagebox as mb
            if not mb.askyesno("Delete Template", f"Delete template \"{tpl.name}\"?"):
                return
        except Exception:
            pass
        try:
            self._persistence.delete_custom_template(tpl.id)
            if self._selected_template and self._selected_template.id == tpl.id:
                self._selected_template = None
            self._rebuild_gallery()
        except Exception as exc:
            self._store.set("toast", {"message": f"Could not delete template: {exc}", "type": "error"})


class _SaveTemplateDialog(ctk.CTkToplevel if HAS_CTK else object):  # type: ignore
    def __init__(
        self,
        parent: Any,
        on_save: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(parent, **kwargs)
        self.title("Save as Template")
        self.geometry("340x160")
        self.transient(parent)
        self.grab_set()
        self.focus_set()
        self._on_save = on_save

        ctk.CTkLabel(
            self,
            text="Template name:",
            font=(theme.FONT_UI, theme.TEXT_SM),
        ).pack(padx=theme.SP_4, pady=(theme.SP_4, theme.SP_2), anchor="w")

        self._name_var = ctk.StringVar()
        self._entry = ctk.CTkEntry(self, textvariable=self._name_var, height=36)
        self._entry.pack(fill="x", padx=theme.SP_4, pady=(0, theme.SP_3))
        self._entry.focus_set()
        self._entry.bind("<Return>", self._submit)

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(padx=theme.SP_4)

        ctk.CTkButton(btn_row, text="Save", fg_color=theme.ACCENT_VIOLET, command=self._submit, width=100).pack(side="left", padx=(0, theme.SP_2))
        ctk.CTkButton(btn_row, text="Cancel", fg_color=theme.BG_OVERLAY, command=self.destroy, width=100).pack(side="left")

    def _submit(self, event: Any = None) -> None:
        name = self._name_var.get().strip()
        self.destroy()
        if name:
            self._on_save(name)

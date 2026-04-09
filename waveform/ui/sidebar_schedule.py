"""
sidebar_schedule.py — ScheduleSidebar: left column of the three-column layout.

Shows ordered BlockCard instances for the current session's blocks.
Add Block popover, block mutation propagation, Phase 2A keyboard delete.
Phase 11: block card reveal animation (staggered ease-out height tween).
"""
from __future__ import annotations

import dataclasses
from typing import Any, Callable, Dict, List, Optional, Set

try:
    import customtkinter as ctk  # type: ignore
    HAS_CTK = True
except ImportError:
    HAS_CTK = False

from waveform.domain.block import ARCHETYPE_SPECS, BlockArchetype, Block
from waveform.ui import theme
from waveform.ui.widgets.block_card import BlockCard, ARCHETYPE_EMOJI


class ScheduleSidebar(ctk.CTkFrame if HAS_CTK else object):  # type: ignore
    def __init__(
        self,
        parent: Any,
        store: Any,
        analytics: Any = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            parent,
            width=theme.SIDEBAR_WIDTH,
            fg_color=theme.BG_SURFACE,
            **kwargs,
        )
        self._store = store
        self._analytics = analytics
        self._selected_block_id: Optional[str] = None
        self._cards: Dict[str, BlockCard] = {}
        self._on_block_select_external: Optional[Callable] = None
        self._prev_block_ids: Set[str] = set()

        self.grid_propagate(False)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Header
        ctk.CTkLabel(
            self,
            text="SCHEDULE",
            font=(theme.FONT_UI, theme.TEXT_XS, "bold"),
            text_color=theme.TEXT_MUTED,
        ).grid(row=0, column=0, padx=theme.SP_3, pady=(theme.SP_3, theme.SP_1), sticky="w")

        # Scrollable card list
        self._scroll = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
        )
        self._scroll.grid(row=1, column=0, sticky="nsew", padx=theme.SP_2, pady=0)
        self._scroll.grid_columnconfigure(0, weight=1)

        # Add block button
        self._add_btn = ctk.CTkButton(
            self,
            text="+ Add Block",
            font=(theme.FONT_UI, theme.TEXT_SM),
            fg_color="transparent",
            border_color=theme.ACCENT_VIOLET,
            border_width=1,
            text_color=theme.ACCENT_VIOLET,
            hover_color=theme.BG_OVERLAY,
            command=self._open_add_block_popover,
        )
        self._add_btn.grid(row=2, column=0, padx=theme.SP_3, pady=theme.SP_2, sticky="ew")
        theme.apply_focus_ring(self._add_btn)

        store.subscribe("session", lambda s: self.after(0, lambda: self._on_session_changed(s)))
        # Render initial state
        session = store.get("session")
        if session:
            self._render_blocks(session.blocks, animate_new=False)

    def _on_session_changed(self, session: Any) -> None:
        if session is None:
            self._render_blocks([], animate_new=False)
        else:
            self._render_blocks(session.blocks, animate_new=True)

    def _render_blocks(self, blocks: List[Any], animate_new: bool = False) -> None:
        new_ids = {b.id for b in blocks}
        truly_new = new_ids - self._prev_block_ids if animate_new else set()
        self._prev_block_ids = new_ids

        for widget in self._scroll.winfo_children():
            widget.destroy()
        self._cards.clear()

        start_min = 0
        for i, block in enumerate(blocks):
            card = BlockCard(
                self._scroll,
                block=block,
                start_minute=start_min,
                on_click=self._on_card_clicked,
                on_mutate=self._on_block_mutated,
                on_delete=self._on_block_delete_requested,
                store=self._store,
                analytics=self._analytics,
            )
            card.grid(row=i, column=0, sticky="ew", pady=(0, theme.SP_1))

            if block.id == self._selected_block_id:
                card.set_selected(True)

            self._cards[block.id] = card
            start_min += block.duration_minutes

            # Phase 11: staggered reveal animation for newly added blocks
            if block.id in truly_new:
                settings = self._store.get("settings") or {}
                if not settings.get("reduce_motion", False):
                    delay = list(truly_new).index(block.id) * 80 if len(truly_new) > 1 else 0
                    self.after(delay, lambda c=card: self._animate_card_reveal(c))

    def _animate_card_reveal(self, card: BlockCard) -> None:
        """Ease-out height tween from 0 → full height over 9 frames × 20ms."""
        try:
            full_h = card.winfo_reqheight() or 80
            steps = 9
            frame_ms = 20

            def _step(n: int) -> None:
                if not card.winfo_exists():
                    return
                t = n / steps
                ease = 1 - (1 - t) ** 2  # ease-out quadratic
                h = max(4, int(full_h * ease))
                try:
                    card.grid_propagate(False)
                    card.configure(height=h)
                except Exception:
                    pass
                if n < steps:
                    card.after(frame_ms, lambda: _step(n + 1))
                else:
                    try:
                        card.grid_propagate(True)
                        card.configure(height=full_h)
                    except Exception:
                        pass

            card.configure(height=0)
            card.grid_propagate(False)
            card.after(10, lambda: _step(0))
        except Exception:
            pass

    def _on_card_clicked(self, block: Any) -> None:
        # Toggle collapse if already selected
        if self._selected_block_id == block.id:
            if block.id in self._cards:
                old_card = self._cards[block.id]
                old_card.set_selected(False)
            self._selected_block_id = None
            return

        # Deselect previous
        if self._selected_block_id and self._selected_block_id in self._cards:
            self._cards[self._selected_block_id].set_selected(False)

        self._selected_block_id = block.id
        if block.id in self._cards:
            self._cards[block.id].set_selected(True)

        if self._on_block_select_external:
            self._on_block_select_external(block)

        if self._store:
            self._store.set("selected_block_id", block.id)

    def _on_block_mutated(self, updated_block: Any) -> None:
        session = self._store.get("session")
        if session is None:
            return
        updated_blocks = [
            updated_block if b.id == updated_block.id else b
            for b in session.blocks
        ]
        updated_session = dataclasses.replace(session, blocks=updated_blocks)
        self._store.set("session", updated_session)

    def _on_block_delete_requested(self, block: Any) -> None:
        """Phase 2A: open confirmation dialog before deleting."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Delete Block")
        dialog.geometry("320x140")
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()
        dialog.focus_set()

        ctk.CTkLabel(
            dialog,
            text=f"Delete block \"{block.name}\"?",
            font=(theme.FONT_UI, theme.TEXT_SM),
            text_color=theme.TEXT_PRIMARY,
            wraplength=280,
        ).pack(padx=theme.SP_4, pady=(theme.SP_4, theme.SP_2))

        btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_row.pack(padx=theme.SP_4, pady=(0, theme.SP_4))

        def _do_delete() -> None:
            dialog.destroy()
            session = self._store.get("session")
            if session is None:
                return
            updated_blocks = [b for b in session.blocks if b.id != block.id]
            updated_session = dataclasses.replace(session, blocks=updated_blocks)
            self._store.set("session", updated_session)
            if self._analytics:
                arch_str = str(block.archetype.value if hasattr(block.archetype, "value") else block.archetype)
                self._analytics.block_removed(archetype=arch_str)

        ctk.CTkButton(
            btn_row,
            text="Delete",
            fg_color=theme.DANGER_RED,
            text_color=theme.TEXT_PRIMARY,
            command=_do_delete,
            width=100,
        ).pack(side="left", padx=(0, theme.SP_2))

        ctk.CTkButton(
            btn_row,
            text="Cancel",
            fg_color=theme.BG_OVERLAY,
            command=dialog.destroy,
            width=100,
        ).pack(side="left")

    def _open_add_block_popover(self) -> None:
        popover = ctk.CTkToplevel(self)
        popover.title("Add Block")
        popover.geometry("360x440")
        popover.transient(self.winfo_toplevel())
        popover.grab_set()
        popover.focus_set()

        ctk.CTkLabel(
            popover,
            text="Choose a block type",
            font=(theme.FONT_UI, theme.TEXT_MD, "bold"),
            text_color=theme.TEXT_PRIMARY,
        ).pack(padx=theme.SP_4, pady=(theme.SP_4, theme.SP_2))

        scroll = ctk.CTkScrollableFrame(popover, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=theme.SP_3, pady=(0, theme.SP_3))
        scroll.grid_columnconfigure(0, weight=1)

        for i, arch in enumerate(BlockArchetype):
            spec = ARCHETYPE_SPECS[arch]
            row = ctk.CTkFrame(scroll, fg_color=theme.BG_OVERLAY, corner_radius=8)
            row.grid(row=i, column=0, sticky="ew", pady=(0, theme.SP_1))
            row.grid_columnconfigure(1, weight=1)

            swatch = ctk.CTkFrame(row, width=20, height=40, fg_color=spec.cover_palette[0], corner_radius=4)
            swatch.grid(row=0, column=0, rowspan=2, padx=(theme.SP_2, theme.SP_2), pady=theme.SP_2)

            ctk.CTkLabel(
                row,
                text=f"{spec.emoji}  {spec.display_name}",
                font=(theme.FONT_UI, theme.TEXT_SM, "bold"),
                text_color=theme.TEXT_PRIMARY,
                anchor="w",
            ).grid(row=0, column=1, sticky="w")

            ctk.CTkLabel(
                row,
                text=spec.description[:60],
                font=(theme.FONT_UI, theme.TEXT_XS),
                text_color=theme.TEXT_MUTED,
                anchor="w",
            ).grid(row=1, column=1, sticky="w", pady=(0, theme.SP_1))

            energy_label = ctk.CTkLabel(
                row,
                text=f"Energy {spec.default_energy}/5",
                font=(theme.FONT_UI, theme.TEXT_XS),
                text_color=theme.TEXT_MUTED,
                width=60,
            )
            energy_label.grid(row=0, column=2, rowspan=2, padx=theme.SP_2)

            row.bind("<Button-1>", lambda e, a=arch: (popover.destroy(), self._add_block_with_archetype(a)))
            for child in row.winfo_children():
                child.bind("<Button-1>", lambda e, a=arch: (popover.destroy(), self._add_block_with_archetype(a)))

    def _add_block_with_archetype(self, arch: BlockArchetype) -> None:
        session = self._store.get("session")
        if session is None:
            return
        spec = ARCHETYPE_SPECS[arch]
        new_block = Block.from_archetype(arch, duration_minutes=60)
        updated_blocks = list(session.blocks) + [new_block]
        updated_session = dataclasses.replace(session, blocks=updated_blocks)
        self._store.set("session", updated_session)
        if self._analytics:
            self._analytics.block_added(archetype=arch.value)

    def select_block(self, block_id: str) -> None:
        """External sync: highlight the given block without firing on_click."""
        if self._selected_block_id and self._selected_block_id in self._cards:
            self._cards[self._selected_block_id].set_selected(False)
        self._selected_block_id = block_id
        if block_id in self._cards:
            self._cards[block_id].set_selected(True)

    def set_on_block_select(self, callback: Callable) -> None:
        self._on_block_select_external = callback

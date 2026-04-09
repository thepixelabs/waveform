"""
timeline_canvas.py — Interactive block timeline canvas.

- Block bands proportional to duration_minutes, archetype palette fill.
- Click-to-select, drag-to-reorder, grab-edge-to-resize.
- Energy-arc sparkline above the strip.
- Double-click inline rename, right-click context menu.
- Snap-to-5-minutes default; hold Shift for freeform.
"""
from __future__ import annotations

import dataclasses
import math
from typing import Any, Callable, Dict, List, Optional

try:
    import customtkinter as ctk  # type: ignore
    import tkinter as tk
    HAS_CTK = True
except ImportError:
    HAS_CTK = False

from waveform.domain.block import ARCHETYPE_SPECS, BlockArchetype, get_spec_for_id
from waveform.ui import theme
from waveform.ui.widgets.block_card import ARCHETYPE_EMOJI

EDGE_GRAB_PX = 8
MIN_BLOCK_MINUTES = 5
SNAP_MINUTES = 5
EVENT_START_MINUTE = 20 * 60  # 20:00


class TimelineCanvas(ctk.CTkFrame if HAS_CTK else object):  # type: ignore
    def __init__(
        self,
        parent: Any,
        on_block_select: Optional[Callable[[Any], None]] = None,
        store: Any = None,
        analytics: Any = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(parent, fg_color=theme.BG_BASE, **kwargs)
        self._on_block_select = on_block_select
        self._store = store
        self._analytics = analytics

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Sparkline area
        self._sparkline = tk.Canvas(
            self,
            height=theme.SPARKLINE_HEIGHT,
            bg=theme.BG_BASE,
            highlightthickness=0,
        )
        self._sparkline.grid(row=0, column=0, sticky="ew")

        # Main canvas
        self._canvas = tk.Canvas(
            self,
            height=theme.TIMELINE_MIN_HEIGHT,
            bg=theme.BG_BASE,
            highlightthickness=0,
        )
        self._canvas.grid(row=1, column=0, sticky="nsew")

        # State
        self._selected_block_id: Optional[str] = None
        self._drag_state: Optional[dict] = None
        self._resize_state: Optional[dict] = None
        self._rename_entry: Optional[tk.Entry] = None

        # Bind
        self._canvas.bind("<Configure>", self._on_resize)
        self._canvas.bind("<Button-1>", self._on_mouse_press)
        self._canvas.bind("<B1-Motion>", self._on_mouse_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_mouse_release)
        self._canvas.bind("<Double-Button-1>", self._on_double_click)
        self._canvas.bind("<Button-2>", self._on_right_click)
        self._canvas.bind("<Button-3>", self._on_right_click)

        if store:
            store.subscribe("session", lambda _: self.after(0, self._redraw))

    def _get_session(self) -> Optional[Any]:
        if self._store:
            return self._store.get("session")
        return None

    def _blocks(self) -> List[Any]:
        session = self._get_session()
        if session is None:
            return []
        return session.blocks

    def _canvas_width(self) -> int:
        w = self._canvas.winfo_width()
        return max(w, 200)

    def _total_minutes(self) -> int:
        blocks = self._blocks()
        if not blocks:
            return 60
        total = sum(b.duration_minutes for b in blocks)
        return max(total, 60)

    def _px_per_minute(self) -> float:
        return (self._canvas_width() - 20) / self._total_minutes()

    def _block_rects(self) -> List[Dict]:
        """Compute pixel rectangles for each block."""
        blocks = self._blocks()
        ppm = self._px_per_minute()
        rects = []
        x = 10
        for block in blocks:
            w = max(4, int(block.duration_minutes * ppm))
            rects.append({
                "block": block,
                "x": x,
                "y": 10,
                "w": w,
                "h": theme.TIMELINE_MIN_HEIGHT - 30,
            })
            x += w
        return rects

    def _redraw(self) -> None:
        self._canvas.delete("all")
        self._sparkline.delete("all")
        blocks = self._blocks()
        if not blocks:
            self._canvas.create_text(
                self._canvas_width() // 2, theme.TIMELINE_MIN_HEIGHT // 2,
                text="No blocks — add one in the schedule panel",
                fill=theme.TEXT_MUTED,
                font=(theme.FONT_UI, theme.TEXT_SM),
            )
            return

        rects = self._block_rects()
        ppm = self._px_per_minute()

        for rect_info in rects:
            block = rect_info["block"]
            x, y, w, h = rect_info["x"], rect_info["y"], rect_info["w"], rect_info["h"]

            spec = get_spec_for_id(str(block.archetype.value if hasattr(block.archetype, "value") else block.archetype))
            fill = spec.cover_palette[0]
            is_selected = block.id == self._selected_block_id
            outline = theme.ACCENT_VIOLET if is_selected else theme.BG_OVERLAY
            outline_w = 2 if is_selected else 1

            self._canvas.create_rectangle(
                x, y, x + w, y + h,
                fill=fill,
                outline=outline,
                width=outline_w,
                tags=("block", block.id),
            )

            # Block name label (hidden if block is too narrow)
            if w > 60:
                emoji = ARCHETYPE_EMOJI.get(str(block.archetype.value if hasattr(block.archetype, "value") else block.archetype), "🎵")
                self._canvas.create_text(
                    x + w // 2, y + h // 2,
                    text=f"{emoji} {block.name}",
                    fill=theme.TEXT_PRIMARY,
                    font=(theme.FONT_UI, theme.TEXT_XS),
                    width=w - 8,
                    tags=("label", block.id),
                )

            # Time label below
            start_min = sum(b.duration_minutes for b in blocks[:blocks.index(block)])
            start_hhmm = _minutes_to_hhmm(EVENT_START_MINUTE + start_min)
            self._canvas.create_text(
                x + 4, y + h + 12,
                text=start_hhmm,
                fill=theme.TEXT_MUTED,
                font=(theme.FONT_UI, theme.TEXT_XS),
                anchor="w",
            )

        # Total duration label
        total_min = sum(b.duration_minutes for b in blocks)
        end_hhmm = _minutes_to_hhmm(EVENT_START_MINUTE + total_min)
        last_x = rects[-1]["x"] + rects[-1]["w"] if rects else self._canvas_width() - 10
        self._canvas.create_text(
            last_x, rects[-1]["y"] + rects[-1]["h"] + 12 if rects else 30,
            text=end_hhmm,
            fill=theme.TEXT_MUTED,
            font=(theme.FONT_UI, theme.TEXT_XS),
            anchor="w",
        )

        # Energy sparkline
        self._draw_sparkline(blocks, rects)

    def _draw_sparkline(self, blocks: List[Any], rects: List[Dict]) -> None:
        if not blocks or not rects:
            return
        pts = []
        for rect_info in rects:
            block = rect_info["block"]
            mid_x = rect_info["x"] + rect_info["w"] // 2
            y = int(theme.SPARKLINE_HEIGHT - 8 - (block.energy_level / 5.0) * (theme.SPARKLINE_HEIGHT - 16))
            pts.append((mid_x, y))

        if len(pts) >= 2:
            flat = [coord for pt in pts for coord in pt]
            self._sparkline.create_line(
                *flat,
                fill=theme.ACCENT_CYAN,
                width=2,
                smooth=True,
            )
            for px, py in pts:
                self._sparkline.create_oval(px - 3, py - 3, px + 3, py + 3, fill=theme.ACCENT_CYAN, outline="")

    def _on_resize(self, event: Any) -> None:
        self.after(10, self._redraw)

    def _hit_test(self, x: int) -> Optional[Dict]:
        for rect in self._block_rects():
            if rect["x"] <= x <= rect["x"] + rect["w"]:
                return rect
        return None

    def _on_mouse_press(self, event: Any) -> None:
        hit = self._hit_test(event.x)
        if hit is None:
            return
        block = hit["block"]

        # Check if near right edge (resize mode)
        if event.x >= hit["x"] + hit["w"] - EDGE_GRAB_PX:
            self._resize_state = {
                "block_id": block.id,
                "start_x": event.x,
                "original_duration": block.duration_minutes,
            }
            return

        # Select block
        self._selected_block_id = block.id
        self._redraw()
        if self._on_block_select:
            self._on_block_select(block)

        # Start drag state
        blocks = self._blocks()
        idx = next((i for i, b in enumerate(blocks) if b.id == block.id), -1)
        self._drag_state = {
            "block_id": block.id,
            "start_x": event.x,
            "original_index": idx,
        }

    def _on_mouse_drag(self, event: Any) -> None:
        if self._resize_state is not None:
            self._handle_resize_drag(event)
        elif self._drag_state is not None:
            self._handle_reorder_drag(event)

    def _handle_resize_drag(self, event: Any) -> None:
        state = self._resize_state
        dx = event.x - state["start_x"]
        ppm = self._px_per_minute()
        delta_min = int(dx / ppm)

        snap = SNAP_MINUTES if not (event.state & 0x1) else 1  # Shift = freeform
        new_dur = max(MIN_BLOCK_MINUTES, state["original_duration"] + delta_min)
        new_dur = (new_dur // snap) * snap

        # Update session
        session = self._get_session()
        if session is None:
            return
        updated_blocks = []
        for b in session.blocks:
            if b.id == state["block_id"]:
                updated_blocks.append(dataclasses.replace(b, duration_minutes=new_dur))
            else:
                updated_blocks.append(b)
        updated_session = dataclasses.replace(session, blocks=updated_blocks)
        if self._store:
            self._store.set("session", updated_session)
        self._redraw()

    def _handle_reorder_drag(self, event: Any) -> None:
        # Show ghost line at target position
        self._canvas.delete("ghost")
        blocks = self._blocks()
        rects = self._block_rects()
        target_idx = 0
        for i, rect in enumerate(rects):
            if event.x > rect["x"] + rect["w"] // 2:
                target_idx = i + 1
        x_ghost = rects[target_idx]["x"] if target_idx < len(rects) else (rects[-1]["x"] + rects[-1]["w"] if rects else 10)
        self._canvas.create_line(
            x_ghost, 10, x_ghost, theme.TIMELINE_MIN_HEIGHT - 30,
            fill=theme.ACCENT_VIOLET,
            width=2,
            dash=(4, 2),
            tags="ghost",
        )
        self._drag_state["target_index"] = target_idx

    def _on_mouse_release(self, event: Any) -> None:
        if self._resize_state is not None:
            block_id = self._resize_state["block_id"]
            session = self._get_session()
            if session and self._analytics:
                for b in session.blocks:
                    if b.id == block_id:
                        arch_str = str(b.archetype.value if hasattr(b.archetype, "value") else b.archetype)
                        self._analytics.block_resized(archetype=arch_str, new_duration=b.duration_minutes)
                        break
            self._resize_state = None

        if self._drag_state is not None:
            target_idx = self._drag_state.get("target_index", self._drag_state["original_index"])
            from_idx = self._drag_state["original_index"]
            if target_idx != from_idx and target_idx != from_idx + 1:
                session = self._get_session()
                if session is not None:
                    blocks = list(session.blocks)
                    block = blocks.pop(from_idx)
                    insert_at = target_idx if target_idx <= from_idx else target_idx - 1
                    blocks.insert(insert_at, block)
                    updated = dataclasses.replace(session, blocks=blocks)
                    if self._store:
                        self._store.set("session", updated)
                    if self._analytics:
                        self._analytics.block_reordered()
            self._canvas.delete("ghost")
            self._drag_state = None
            self._redraw()

    def _on_double_click(self, event: Any) -> None:
        hit = self._hit_test(event.x)
        if hit is None:
            return
        self._start_inline_rename(hit)

    def _start_inline_rename(self, rect: Dict) -> None:
        if self._rename_entry is not None:
            self._rename_entry.destroy()
        block = rect["block"]
        entry = tk.Entry(
            self._canvas,
            font=(theme.FONT_UI, theme.TEXT_SM),
            bg=theme.BG_SURFACE,
            fg=theme.TEXT_PRIMARY,
            relief="flat",
            insertbackground=theme.TEXT_PRIMARY,
        )
        entry.insert(0, block.name)
        entry.select_range(0, tk.END)
        cx = rect["x"] + rect["w"] // 2
        cy = rect["y"] + rect["h"] // 2
        self._canvas.create_window(cx, cy, window=entry, width=max(100, rect["w"] - 16), tags="rename")
        entry.focus_set()

        def _commit(e: Any = None) -> None:
            new_name = entry.get().strip() or block.name
            self._commit_rename(block, new_name)
            entry.destroy()
            self._rename_entry = None
            self._canvas.delete("rename")

        def _cancel(e: Any = None) -> None:
            entry.destroy()
            self._rename_entry = None
            self._canvas.delete("rename")

        entry.bind("<Return>", _commit)
        entry.bind("<FocusOut>", _commit)
        entry.bind("<Escape>", _cancel)
        self._rename_entry = entry

    def _commit_rename(self, block: Any, new_name: str) -> None:
        session = self._get_session()
        if session is None:
            return
        updated_blocks = [
            dataclasses.replace(b, name=new_name) if b.id == block.id else b
            for b in session.blocks
        ]
        updated = dataclasses.replace(session, blocks=updated_blocks)
        if self._store:
            self._store.set("session", updated)
        self._redraw()

    def _on_right_click(self, event: Any) -> None:
        hit = self._hit_test(event.x)
        if hit is None:
            return
        block = hit["block"]
        try:
            menu = tk.Menu(self._canvas, tearoff=0)
            menu.add_command(label="Rename", command=lambda: self._start_inline_rename(hit))
            menu.add_command(label="Duplicate", command=lambda: self._duplicate_block(block))

            # Archetype submenu
            arch_menu = tk.Menu(menu, tearoff=0)
            for arch in BlockArchetype:
                spec = ARCHETYPE_SPECS[arch]
                arch_menu.add_command(
                    label=f"{spec.emoji} {spec.display_name}",
                    command=lambda a=arch: self._change_archetype(block, a),
                )
            menu.add_cascade(label="Change Archetype", menu=arch_menu)

            menu.add_separator()
            menu.add_command(
                label="Delete",
                foreground=theme.DANGER_RED,
                command=lambda: self._delete_block(block),
            )
            menu.tk_popup(event.x_root, event.y_root)
        except Exception:
            pass

    def _duplicate_block(self, block: Any) -> None:
        import uuid
        session = self._get_session()
        if session is None:
            return
        new_block = dataclasses.replace(block, id=str(uuid.uuid4()), name=block.name + " (2)")
        idx = next((i for i, b in enumerate(session.blocks) if b.id == block.id), len(session.blocks))
        blocks = list(session.blocks)
        blocks.insert(idx + 1, new_block)
        updated = dataclasses.replace(session, blocks=blocks)
        if self._store:
            self._store.set("session", updated)
        if self._analytics:
            arch_str = str(block.archetype.value if hasattr(block.archetype, "value") else block.archetype)
            self._analytics.block_added(archetype=arch_str)
        self._redraw()

    def _change_archetype(self, block: Any, new_arch: Any) -> None:
        session = self._get_session()
        if session is None:
            return
        updated_blocks = [
            dataclasses.replace(b, archetype=new_arch) if b.id == block.id else b
            for b in session.blocks
        ]
        updated = dataclasses.replace(session, blocks=updated_blocks)
        if self._store:
            self._store.set("session", updated)
        self._redraw()

    def _delete_block(self, block: Any) -> None:
        session = self._get_session()
        if session is None:
            return
        updated_blocks = [b for b in session.blocks if b.id != block.id]
        updated = dataclasses.replace(session, blocks=updated_blocks)
        if self._store:
            self._store.set("session", updated)
        if self._analytics:
            arch_str = str(block.archetype.value if hasattr(block.archetype, "value") else block.archetype)
            self._analytics.block_removed(archetype=arch_str)
        if self._selected_block_id == block.id:
            self._selected_block_id = None
        self._redraw()

    def select_block(self, block_id: str) -> None:
        self._selected_block_id = block_id
        self._redraw()


def _minutes_to_hhmm(minutes: int) -> str:
    total = minutes % (24 * 60)
    h = total // 60
    m = total % 60
    return f"{h:02d}:{m:02d}"

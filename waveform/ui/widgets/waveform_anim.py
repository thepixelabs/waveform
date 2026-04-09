"""
waveform_anim.py — Five-bar waveform animation widget.

Used in the top bar logo and the Track Panel empty/generating states.

Phase 11: added start_animation(mode) / stop_animation() API.
  - "idle" mode: 0.5 Hz sine breathing.
  - "generating" mode: 5 independent frequencies for an organic active feel.
  - reduce_motion: skips animation, shows static bars.
"""
from __future__ import annotations

import math
from typing import Any, Optional

try:
    import customtkinter as ctk  # type: ignore
    HAS_CTK = True
except ImportError:
    HAS_CTK = False

from waveform.ui import theme


class WaveformAnim(ctk.CTkFrame if HAS_CTK else object):  # type: ignore
    """Five vertical bars with brand gradient, animated breathing."""

    # Bar silhouette heights (0.0–1.0), centre-peaked
    _SILHOUETTE = [0.4, 0.65, 1.0, 0.65, 0.4]
    _COLORS = [
        theme.BRAND_GRADIENT_START,
        "#3A1480",
        theme.BRAND_GRADIENT_MID,
        "#B030D0",
        theme.BRAND_GRADIENT_END,
    ]

    def __init__(
        self,
        parent: Any,
        width: int = 40,
        height: int = 32,
        animate: bool = False,
        store: Any = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            parent,
            width=width,
            height=height,
            fg_color="transparent",
            **kwargs,
        )
        self._width_val = width
        self._height_val = height
        self._store = store
        self._phase = 0.0
        self._anim_after_id: Optional[str] = None
        self._mode = "idle"

        bar_w = max(3, width // 7)
        gap = max(1, (width - 5 * bar_w) // 6)
        self._bars = []
        for i in range(5):
            bar = ctk.CTkFrame(self, width=bar_w, height=height, fg_color=self._COLORS[i], corner_radius=2)
            x = i * (bar_w + gap)
            bar.place(x=x, y=0, anchor="nw")
            self._bars.append(bar)

        if animate:
            self.start_animation(mode="idle")

        # Shims for legacy callers
        self._start_pulse = lambda: self.start_animation(mode="idle")
        self._do_pulse = self._tick

    def start_animation(self, mode: str = "idle") -> None:
        """Start breathing animation. mode: 'idle' | 'generating'."""
        self._mode = mode
        if self._anim_after_id is None:
            self._tick()

    def stop_animation(self) -> None:
        """Freeze bars at current position."""
        if self._anim_after_id is not None:
            try:
                self.after_cancel(self._anim_after_id)
            except Exception:
                pass
            self._anim_after_id = None

    def _tick(self) -> None:
        # Respect reduce_motion setting
        if self._store is not None:
            settings = self._store.get("settings") or {}
            if settings.get("reduce_motion", False):
                self._draw_static()
                return

        self._phase += 0.105  # ~0.5 Hz at 30fps

        # Independent per-bar frequencies for "generating" mode
        _FREQS_GENERATING = [0.4, 0.52, 0.70, 0.45, 0.60]
        _PHASE_OFFSETS = [0.0, 0.8, 1.6, 2.4, 3.2]

        for i, bar in enumerate(self._bars):
            sil = self._SILHOUETTE[i]
            if self._mode == "generating":
                freq = _FREQS_GENERATING[i]
                wave = math.sin(self._phase * freq + _PHASE_OFFSETS[i])
                amplitude = 0.35
            else:
                wave = math.sin(self._phase + i * 0.5)
                amplitude = 0.225

            scale = sil * (0.775 + amplitude * wave)
            new_h = max(4, int(self._height_val * scale))
            bar.configure(height=new_h)
            bar.place(y=self._height_val - new_h)

        self._anim_after_id = self.after(33, self._tick)  # ~30fps

    def _draw_static(self) -> None:
        for i, bar in enumerate(self._bars):
            sil = self._SILHOUETTE[i]
            h = max(4, int(self._height_val * sil))
            bar.configure(height=h)
            bar.place(y=self._height_val - h)

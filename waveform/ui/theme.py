"""
theme.py — Design system tokens for Waveform v2.

Colors, typography, spacing, radii, layout dimensions, and motion constants.
Pure Python — no Tk imports.  Safe to import anywhere in the codebase.

WCAG AA contrast notes:
  TEXT_PRIMARY (#F5F5F7) on BG_SURFACE (#17171B) — ~14:1 (passes AAA)
  TEXT_SECONDARY (#A1A1AA) on BG_BASE (#0D0D0F) — ~6.8:1 (passes AA)
  TEXT_MUTED (#6B6B73) on BG_BASE — ~3.1:1 (fails AA at small sizes)
    → Use TEXT_SECONDARY for body copy; TEXT_MUTED only for decorative labels.
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# Color palette (dark, warm — epic §6)
# ---------------------------------------------------------------------------

BG_BASE = "#0D0D0F"
BG_SURFACE = "#17171B"
BG_OVERLAY = "#1F1F25"

TEXT_PRIMARY = "#F5F5F7"
TEXT_SECONDARY = "#A1A1AA"
TEXT_MUTED = "#6B6B73"

BRAND_GRADIENT_START = "#1A0533"
BRAND_GRADIENT_MID = "#6B2FFA"
BRAND_GRADIENT_END = "#E040FB"

ACCENT_VIOLET = "#7C3AED"
ACCENT_CYAN = "#22D3EE"

SUCCESS_GREEN = "#34D399"
WARNING_AMBER = "#FBBF24"
DANGER_RED = "#F87171"

# Convenience alias
BRAND_VIOLET = BRAND_GRADIENT_MID


# ---------------------------------------------------------------------------
# Typography
# ---------------------------------------------------------------------------

FONT_DISPLAY = "Inter Tight"   # 700 — block titles, logo
FONT_UI = "Inter"              # 400/500/600 — all UI
FONT_MONO = "JetBrains Mono"  # debug / advanced panels only

# Font fallback chains (CTk uses these as-is)
FONT_DISPLAY_FALLBACK = ("Inter Tight", "Inter", "Helvetica Neue", "Arial", "sans-serif")
FONT_UI_FALLBACK = ("Inter", "Helvetica Neue", "Arial", "sans-serif")
FONT_MONO_FALLBACK = ("JetBrains Mono", "Menlo", "Consolas", "Courier New", "monospace")

# Sizes
TEXT_XS = 11
TEXT_SM = 13
TEXT_BASE = 14
TEXT_MD = 16
TEXT_LG = 18
TEXT_XL = 22
TEXT_2XL = 28
TEXT_DISPLAY = 36


# ---------------------------------------------------------------------------
# Spacing scale (px)
# ---------------------------------------------------------------------------

SP_1 = 4
SP_2 = 8
SP_3 = 12
SP_4 = 16
SP_6 = 24
SP_8 = 32
SP_12 = 48
SP_16 = 64


# ---------------------------------------------------------------------------
# Border radii (px)
# ---------------------------------------------------------------------------

RADIUS_INPUT = 8
RADIUS_CARD = 14
RADIUS_MODAL = 20


# ---------------------------------------------------------------------------
# Layout dimensions
# ---------------------------------------------------------------------------

SIDEBAR_WIDTH = 280        # left column (schedule)
TRACK_PANEL_WIDTH = 360    # right column (track preview)
TOP_BAR_HEIGHT = 48
MIN_WINDOW_WIDTH = 1100
MIN_WINDOW_HEIGHT = 680
TIMELINE_MIN_HEIGHT = 180
SPARKLINE_HEIGHT = 40


# ---------------------------------------------------------------------------
# Motion constants (Phase 11)
# ---------------------------------------------------------------------------

MOTION_FAST_MS = 150
MOTION_MEDIUM_MS = 300
MOTION_SLOW_MS = 400

# Easing descriptions (used as documentation; CTk doesn't accept easing strings)
EASE_OUT = "ease-out"
EASE_IN_OUT = "ease-in-out"

# Spring physics parameters (for Phase 11 spring animations)
SPRING_STIFFNESS = 300
SPRING_DAMPING = 28


# ---------------------------------------------------------------------------
# Phase 11 utilities
# ---------------------------------------------------------------------------

def lerp_hex(color_a: str, color_b: str, t: float) -> str:
    """Linear interpolation between two hex color strings. t in [0.0, 1.0]."""
    def _parse(h: str) -> tuple:
        h = h.lstrip("#")
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

    ra, ga, ba = _parse(color_a)
    rb, gb, bb = _parse(color_b)
    t = max(0.0, min(1.0, t))
    r = int(ra + (rb - ra) * t)
    g = int(ga + (gb - ga) * t)
    b = int(ba + (bb - ba) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


def apply_focus_ring(widget: object) -> None:
    """Bind FocusIn/FocusOut to any CTk widget with border support.
    Sets border_color=ACCENT_VIOLET, border_width=2 on focus.
    Silently no-ops for widgets that don't support border config.
    """
    def _on_focus_in(_event: object = None) -> None:
        try:
            widget.configure(border_color=ACCENT_VIOLET, border_width=2)  # type: ignore
        except Exception:
            pass

    def _on_focus_out(_event: object = None) -> None:
        try:
            widget.configure(border_color=BG_OVERLAY, border_width=1)  # type: ignore
        except Exception:
            pass

    try:
        widget.bind("<FocusIn>", _on_focus_in)  # type: ignore
        widget.bind("<FocusOut>", _on_focus_out)  # type: ignore
    except Exception:
        pass

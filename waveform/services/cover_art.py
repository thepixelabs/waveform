"""
cover_art.py — Parametric PIL cover art generator (Tier 1).

Tier 1: multi-stop gradients, noise overlays, geometric accents, typography.
Tier 2 (DALL-E / Imagen composite): stubbed behind COVER_ART_TIER flag, deferred.
Tier 3 (generative SVG): deferred.

All renderers produce 512x512 PNG bytes.

Note on Perlin noise: approximated with a 3-octave sine grid. True Perlin
requires a C extension (noise package). The sine approximation produces
acceptable organic texture at 10-35% opacity on cover-art-sized output.

Note on performance: _radial_gradient_image() uses putdata() rather than
per-pixel draw.point(), which is ~100x faster in pure Python but still
iterates 262,144 pixels. ~1-2 seconds per radial archetype on a modern Mac.
This is acceptable for a once-per-export generation path.
"""
from __future__ import annotations

import math
import os
import random
from io import BytesIO
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont  # type: ignore
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

from waveform.domain.block import BlockArchetype

COVER_ART_TIER = 1  # 1 = parametric PIL; 2 = DALL-E overlay (stub)
SIZE = 512

_ASSETS_DIR = Path(__file__).parent.parent / "assets" / "fonts"

# Brand colours used in watermark and text layers
_BRAND_VIOLET = "#6B2FFA"
_BRAND_MAGENTA = "#E040FB"
_BRAND_START = "#1A0533"
_TEXT_LIGHT = "#F5F5F7"
_TEXT_DARK = "#1A1A1A"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_block_cover(
    archetype: Union[BlockArchetype, str],
    event_name: str = "",
    width: int = 512,
    height: int = 512,
) -> bytes:
    """Generate parametric cover art for a block archetype. Returns PNG bytes."""
    if not HAS_PIL:
        return _fallback_bytes()

    if width != 512 or height != 512:
        import logging
        logging.getLogger(__name__).warning(
            "generate_block_cover: non-512 dimensions requested (%sx%s); rendering at 512x512",
            width, height,
        )

    if COVER_ART_TIER == 2:
        base = _dispatch(archetype, event_name)
        return _generate_dalle_overlay(base, archetype, event_name)

    return _dispatch(archetype, event_name)


def generate_playlist_cover(session: Any) -> bytes:
    """Generate a playlist-level cover based on the dominant block archetype."""
    if not HAS_PIL:
        return _fallback_bytes()

    blocks = getattr(session, "blocks", [])
    if not blocks:
        return generate_block_cover(BlockArchetype.ARRIVAL, "Event")

    # Find dominant archetype by total duration
    duration_by_arch: Dict[str, int] = {}
    for block in blocks:
        arch_str = str(block.archetype)
        duration_by_arch[arch_str] = duration_by_arch.get(arch_str, 0) + block.duration_minutes

    dominant_arch_str = max(duration_by_arch, key=lambda k: duration_by_arch[k])
    try:
        dominant_arch = BlockArchetype(dominant_arch_str)
    except ValueError:
        dominant_arch = dominant_arch_str  # type: ignore

    event_template = getattr(session, "event_template", None)
    event_name = getattr(event_template, "name", None) or getattr(session, "event_name", "Event")

    return generate_block_cover(dominant_arch, event_name)


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

def _dispatch(archetype: Union[BlockArchetype, str], event_name: str) -> bytes:
    arch_str = str(archetype)
    render_fn = _RENDER_FNS.get(arch_str)
    if render_fn is None:
        # Custom archetype fallback — use GROOVE with custom palette
        return _render_custom_fallback(archetype, event_name)
    img = render_fn(event_name)
    _add_text_layer(img, event_name, arch_str.replace("_", " ").title())
    _draw_waveform_watermark(img)
    return _to_png_bytes(img)


# ---------------------------------------------------------------------------
# Shared infrastructure
# ---------------------------------------------------------------------------

def _new_image(color: str = "#000000") -> "Image.Image":
    img = Image.new("RGB", (SIZE, SIZE), color)
    return img


def _radial_gradient_image(
    center: Tuple[int, int],
    stops: List[Tuple[float, str]],  # [(position 0-1, hex_color), ...]
) -> "Image.Image":
    """Build a radial gradient using putdata() for performance."""
    img = Image.new("RGB", (SIZE, SIZE))
    cx, cy = center
    max_r = math.sqrt(cx**2 + cy**2) * 1.2 + 1

    def _hex_to_rgb(h: str) -> Tuple[int, int, int]:
        h = h.lstrip("#")
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

    stop_rgbs = [(_hex_to_rgb(c), pos) for pos, c in stops]

    def _interp(t: float) -> Tuple[int, int, int]:
        # Find surrounding stops
        for i in range(len(stops) - 1):
            p0, c0 = stops[i][0], _hex_to_rgb(stops[i][1])
            p1, c1 = stops[i + 1][0], _hex_to_rgb(stops[i + 1][1])
            if p0 <= t <= p1:
                u = (t - p0) / max(p1 - p0, 1e-9)
                r = int(c0[0] + (c1[0] - c0[0]) * u)
                g = int(c0[1] + (c1[1] - c0[1]) * u)
                b = int(c0[2] + (c1[2] - c0[2]) * u)
                return (r, g, b)
        return _hex_to_rgb(stops[-1][1])

    pixels = []
    for y in range(SIZE):
        for x in range(SIZE):
            dist = math.sqrt((x - cx) ** 2 + (y - cy) ** 2)
            t = min(dist / max_r, 1.0)
            pixels.append(_interp(t))
    img.putdata(pixels)
    return img


def _blurred_circle(
    canvas: "Image.Image",
    cx: int,
    cy: int,
    r: int,
    color: str,
    opacity: int = 160,
    blur_radius: int = 30,
) -> None:
    layer = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    hex_rgb = tuple(int(color.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(*hex_rgb, opacity))  # type: ignore
    layer = layer.filter(ImageFilter.GaussianBlur(blur_radius))
    canvas_rgba = canvas.convert("RGBA")
    canvas_rgba = Image.alpha_composite(canvas_rgba, layer)
    canvas.paste(canvas_rgba.convert("RGB"))


def _sine_noise_overlay(img: "Image.Image", opacity: float = 0.15) -> None:
    """3-octave sine grid approximating Perlin noise. Documented approximation."""
    noise = Image.new("RGB", (SIZE, SIZE))
    pixels = []
    for y in range(SIZE):
        for x in range(SIZE):
            # 3 octaves
            v = (
                0.5 * math.sin(x * 0.05 + y * 0.03)
                + 0.3 * math.sin(x * 0.13 - y * 0.11)
                + 0.2 * math.sin(x * 0.07 + y * 0.19 + 1.5)
            )
            v = (v + 1) / 2  # normalise to [0,1]
            g = int(v * 255)
            pixels.append((g, g, g))
    noise.putdata(pixels)

    img_rgba = img.convert("RGBA")
    noise_rgba = noise.convert("RGBA")
    # Set alpha channel to opacity
    alpha_val = int(opacity * 255)
    r, g, b, _ = noise_rgba.split()
    noise_rgba = Image.merge("RGBA", (r, g, b, Image.new("L", (SIZE, SIZE), alpha_val)))
    result = Image.alpha_composite(img_rgba, noise_rgba)
    img.paste(result.convert("RGB"))


def _noise_overlay(img: "Image.Image", density: int = 8000, opacity: int = 80) -> None:
    """Fast scatter-point noise."""
    rng = random.Random(42)
    overlay = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for _ in range(density):
        x = rng.randint(0, SIZE - 1)
        y = rng.randint(0, SIZE - 1)
        v = rng.randint(180, 255)
        draw.point((x, y), fill=(v, v, v, opacity))
    img_rgba = img.convert("RGBA")
    combined = Image.alpha_composite(img_rgba, overlay)
    img.paste(combined.convert("RGB"))


def _draw_waveform_watermark(img: "Image.Image") -> None:
    """5-bar brand gradient watermark at bottom-right, 60% opacity."""
    bar_w, bar_gap = 4, 3
    heights = [16, 26, 34, 26, 16]
    total_w = 5 * bar_w + 4 * bar_gap
    x0 = SIZE - total_w - 12
    y_base = SIZE - 12

    colors = [_BRAND_START, _BRAND_VIOLET, _BRAND_MAGENTA, _BRAND_VIOLET, _BRAND_START]
    overlay = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for i, (h, c) in enumerate(zip(heights, colors)):
        rgb = tuple(int(c.lstrip("#")[j : j + 2], 16) for j in (0, 2, 4))
        x = x0 + i * (bar_w + bar_gap)
        draw.rectangle([x, y_base - h, x + bar_w, y_base], fill=(*rgb, 153))  # 60% = 153/255
    img_rgba = img.convert("RGBA")
    result = Image.alpha_composite(img_rgba, overlay)
    img.paste(result.convert("RGB"))


def _load_font(size: int, bold: bool = False) -> "ImageFont.FreeTypeFont":
    """Load Inter from assets, then system fonts, then PIL default."""
    font_name = "Inter-Bold.ttf" if bold else "Inter-Regular.ttf"
    candidates = [
        str(_ASSETS_DIR / font_name),
        # macOS system
        f"/Library/Fonts/{'Arial Bold.ttf' if bold else 'Arial.ttf'}",
        f"/System/Library/Fonts/Helvetica.ttc",
        # Linux
        f"/usr/share/fonts/truetype/dejavu/{'DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf'}",
        f"/usr/share/fonts/truetype/liberation/{'LiberationSans-Bold.ttf' if bold else 'LiberationSans-Regular.ttf'}",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    import logging
    logging.getLogger(__name__).warning("PIL default font in use; install Inter for best results")
    return ImageFont.load_default()


def _add_text_layer(img: "Image.Image", event_name: str, archetype_label: str) -> None:
    draw = ImageDraw.Draw(img)
    # Archetype label — top right, small, secondary
    if archetype_label:
        small_font = _load_font(14, bold=False)
        draw.text((SIZE - 12, 12), archetype_label[:30], font=small_font, fill="#A1A1AA", anchor="rt")  # type: ignore

    # Event name — bottom left, bold
    if event_name:
        name = event_name[:40]
        bold_font = _load_font(22, bold=True)
        draw.text((12, SIZE - 38), name, font=bold_font, fill=_TEXT_LIGHT)


def _to_png_bytes(img: "Image.Image") -> bytes:
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _fallback_bytes() -> bytes:
    """Minimal 1x1 PNG when PIL is not available."""
    import base64
    # A minimal valid 1x1 PNG
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    )


# ---------------------------------------------------------------------------
# Tier 2 stub
# ---------------------------------------------------------------------------

def _generate_dalle_overlay(
    base_img: bytes,
    archetype: Union[BlockArchetype, str],
    event_name: str,
) -> bytes:
    """Phase 2 roadmap: compose DALL-E generated image at 60% blend over base.
    Currently a passthrough — returns base unchanged."""
    return base_img


# ---------------------------------------------------------------------------
# Per-archetype renderers
# ---------------------------------------------------------------------------

def _render_arrival(event_name: str) -> "Image.Image":
    """3-stop radial gradient + watercolor pooling circles + sine-noise."""
    img = _radial_gradient_image(
        center=(SIZE // 2, SIZE // 2),
        stops=[
            (0.0, "#F5E6C8"),   # champagne
            (0.5, "#D4A5A5"),   # dusty rose
            (1.0, "#4A1942"),   # deep plum
        ],
    )
    rng = random.Random(7)
    for _ in range(rng.randint(5, 8)):
        cx = rng.randint(80, SIZE - 80)
        cy = rng.randint(80, SIZE - 80)
        r = rng.randint(40, 90)
        c = rng.choice(["#F5E6C8", "#D4A5A5", "#C8A8C8"])
        _blurred_circle(img, cx, cy, r, c, opacity=120, blur_radius=25)
    _sine_noise_overlay(img, opacity=0.15)
    return img


def _render_chill(event_name: str) -> "Image.Image":
    """Ocean base + blurred teal/sage/moon-white blobs."""
    img = _new_image("#0A2540")
    rng = random.Random(13)
    colors = ["#00B4D8", "#90E0EF", "#CAF0F8", "#D4E8E8", "#B8C8D8"]
    for _ in range(rng.randint(4, 6)):
        cx = rng.randint(60, SIZE - 60)
        cy = rng.randint(60, SIZE - 60)
        r = rng.randint(50, 120)
        c = rng.choice(colors)
        _blurred_circle(img, cx, cy, r, c, opacity=rng.randint(80, 160), blur_radius=40)
    return img


def _render_singalong(event_name: str) -> "Image.Image":
    """Cream base + diagonal texture lines + confetti circles."""
    img = _new_image("#FFF8F0")
    draw = ImageDraw.Draw(img)
    # Diagonal texture lines
    for i in range(-SIZE, SIZE * 2, 30):
        draw.line([(i, 0), (i + SIZE, SIZE)], fill="#F0E8D8", width=1)
    # Confetti
    rng = random.Random(17)
    colors = ["#FF7043", "#FFD600", "#FF5252", "#FF8A65", "#FFA726"]
    for _ in range(rng.randint(22, 30)):
        cx = rng.randint(10, SIZE - 10)
        cy = rng.randint(10, SIZE - 10)
        r = rng.randint(5, 18)
        c = rng.choice(colors)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=c)
    return img


def _render_groove(event_name: str) -> "Image.Image":
    """Dark warm base + pill shapes with glow halos."""
    img = _new_image("#1A0D00")
    rng = random.Random(23)
    colors = ["#FF8C00", "#D2691E", "#8B4513", "#CD853F"]
    for _ in range(rng.randint(3, 5)):
        cx = rng.randint(80, SIZE - 80)
        cy = rng.randint(80, SIZE - 80)
        w = rng.randint(60, 180)
        h = rng.randint(20, 60)
        c = rng.choice(colors)
        # Glow halo
        _blurred_circle(img, cx, cy, max(w, h) // 2 + 20, c, opacity=80, blur_radius=35)
        # Pill (rounded rectangle approximated with ellipses + rectangle)
        draw = ImageDraw.Draw(img)
        rgb = tuple(int(c.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
        draw.rounded_rectangle([cx - w // 2, cy - h // 2, cx + w // 2, cy + h // 2], radius=h // 2, fill=rgb)  # type: ignore
    return img


def _render_dance_floor(event_name: str) -> "Image.Image":
    """Black base + concentric rings with motion-blur simulation."""
    img = _new_image("#000000")
    draw = ImageDraw.Draw(img)
    cx, cy = SIZE // 2, SIZE // 2
    colors_cycle = ["#22D3EE", "#E040FB", "#FFFFFF40"]
    rng = random.Random(31)
    n_rings = rng.randint(9, 12)
    for i in range(n_rings):
        r = 20 + i * (SIZE // (2 * n_rings + 2)) + rng.randint(-5, 5)
        c = colors_cycle[i % len(colors_cycle)]
        rgb = tuple(int(c.lstrip("#")[j : j + 2], 16) for j in (0, 2, 4))
        alpha = int(c[7:9], 16) if len(c) > 7 else 200
        # 3-pass blur simulation: draw slightly offset rings
        for dx, dy in [(0, 0), (2, 1), (-1, 2)]:
            draw.ellipse(
                [cx - r + dx, cy - r + dy, cx + r + dx, cy + r + dy],
                outline=(*rgb, alpha // (1 + abs(dx) + abs(dy))),  # type: ignore
                width=2,
            )
    return img


def _render_club_night(event_name: str) -> "Image.Image":
    """Near-black + circuit-board grid + angular polygons."""
    img = _new_image("#080810")
    draw = ImageDraw.Draw(img)
    # Circuit-board grid
    grid = 32
    for x in range(0, SIZE, grid):
        draw.line([(x, 0), (x, SIZE)], fill="#1A2A1A", width=1)
    for y in range(0, SIZE, grid):
        draw.line([(0, y), (SIZE, y)], fill="#1A2A1A", width=1)
    # Dot nodes at intersections
    for gx in range(0, SIZE, grid * 2):
        for gy in range(0, SIZE, grid * 2):
            draw.ellipse([gx - 3, gy - 3, gx + 3, gy + 3], fill="#39FF14")
    # Angular polygons
    rng = random.Random(37)
    colors = ["#39FF14", "#7B00D4", "#00FF88"]
    for _ in range(rng.randint(4, 6)):
        cx = rng.randint(80, SIZE - 80)
        cy = rng.randint(80, SIZE - 80)
        pts = []
        n = rng.randint(3, 6)
        for k in range(n):
            angle = 2 * math.pi * k / n + rng.uniform(-0.3, 0.3)
            r = rng.randint(30, 100)
            pts.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
        c = rng.choice(colors)
        rgb = tuple(int(c.lstrip("#")[j : j + 2], 16) for j in (0, 2, 4))
        draw.polygon(pts, fill=(*rgb, 60), outline=(*rgb, 200))  # type: ignore
    return img


def _render_late_night(event_name: str) -> "Image.Image":
    """Dark smoky base + sinusoidal blurred curves + heavy noise."""
    img = _new_image("#100818")
    rng = random.Random(43)
    # Sinusoidal curves
    colors = ["#4A3060", "#6B5080", "#3D4060"]
    overlay = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for _ in range(rng.randint(3, 5)):
        amp = rng.randint(30, 80)
        freq = rng.uniform(0.008, 0.02)
        phase = rng.uniform(0, 2 * math.pi)
        y_center = rng.randint(80, SIZE - 80)
        c = rng.choice(colors)
        rgb = tuple(int(c.lstrip("#")[j : j + 2], 16) for j in (0, 2, 4))
        pts = [(x, int(y_center + amp * math.sin(freq * x + phase))) for x in range(SIZE)]
        draw.line(pts, fill=(*rgb, 160), width=rng.randint(8, 20))  # type: ignore
    overlay = overlay.filter(ImageFilter.GaussianBlur(15))
    img_rgba = img.convert("RGBA")
    img.paste(Image.alpha_composite(img_rgba, overlay).convert("RGB"))
    # Heavy noise
    _noise_overlay(img, density=12000, opacity=38)
    return img


def _render_sunrise(event_name: str) -> "Image.Image":
    """Rothko horizontal bands with per-band scatter noise."""
    img = _new_image("#FFB347")
    draw = ImageDraw.Draw(img)
    band_colors = ["#FF6B6B", "#FF8C42", "#FFB347", "#FFD166", "#E8C4E8", "#C4A8E8"]
    rng = random.Random(53)
    n = rng.randint(4, 6)
    band_h = SIZE // n
    colors = rng.sample(band_colors, min(n, len(band_colors)))
    for i, c in enumerate(colors):
        rgb = tuple(int(c.lstrip("#")[j : j + 2], 16) for j in (0, 2, 4))
        draw.rectangle([0, i * band_h, SIZE, (i + 1) * band_h], fill=rgb)
        # 1px divider
        draw.line([(0, (i + 1) * band_h), (SIZE, (i + 1) * band_h)], fill="#FFFFFF20", width=1)
    _noise_overlay(img, density=4000, opacity=40)
    return img


def _render_ceremony(event_name: str) -> "Image.Image":
    """Linen base + crossed diagonal texture + blurred pastel edge shapes. DARK TEXT."""
    img = _new_image("#FAF7F2")
    draw = ImageDraw.Draw(img)
    # Crossed diagonal texture
    for i in range(-SIZE, SIZE * 2, 12):
        draw.line([(i, 0), (i + SIZE, SIZE)], fill="#E8E0D0", width=1)
        draw.line([(i, SIZE), (i + SIZE, 0)], fill="#E8E0D0", width=1)
    # Blurred pastel edge shapes
    rng = random.Random(59)
    pastels = ["#D4C5B0", "#E8D5C0", "#C8D0B0", "#D0C8C0"]
    for _ in range(rng.randint(2, 3)):
        x = rng.choice([0, SIZE - 100])
        y = rng.randint(100, SIZE - 200)
        r = rng.randint(60, 120)
        c = rng.choice(pastels)
        _blurred_circle(img, x + r // 2, y + r // 2, r, c, opacity=100, blur_radius=40)
    return img


def _render_peak(event_name: str) -> "Image.Image":
    """5-stop radial burst (brand gradient maxed) + sunburst rays + noise."""
    img = _radial_gradient_image(
        center=(SIZE // 2, SIZE // 2),
        stops=[
            (0.0, "#FFFFFF"),
            (0.2, "#E040FB"),
            (0.5, "#6B2FFA"),
            (0.8, "#1A0533"),
            (1.0, "#0D0D0F"),
        ],
    )
    draw = ImageDraw.Draw(img)
    cx, cy = SIZE // 2, SIZE // 2
    rng = random.Random(67)
    n_rays = rng.randint(9, 13)
    for i in range(n_rays):
        angle = 2 * math.pi * i / n_rays + rng.uniform(-0.1, 0.1)
        length = rng.randint(SIZE // 3, SIZE // 2)
        ex = int(cx + length * math.cos(angle))
        ey = int(cy + length * math.sin(angle))
        draw.line([(cx, cy), (ex, ey)], fill=(255, 255, 255, 25), width=rng.randint(1, 3))  # type: ignore
    _sine_noise_overlay(img, opacity=0.10)
    return img


def _render_custom_fallback(archetype: Any, event_name: str) -> "Image.Image":
    """Custom archetype: GROOVE structure with custom palette."""
    from waveform.domain.block import get_custom_archetype

    arch_id = str(archetype)
    custom = get_custom_archetype(arch_id)
    start = getattr(custom, "palette_start", "#1A0533")
    end = getattr(custom, "palette_end", "#6B2FFA")

    img = _radial_gradient_image(
        center=(SIZE // 2, SIZE // 2),
        stops=[(0.0, start), (1.0, end)],
    )
    return img


# Dispatch table (after all render functions are defined)
_RENDER_FNS: Dict[str, Callable] = {
    BlockArchetype.ARRIVAL.value: _render_arrival,
    BlockArchetype.CHILL.value: _render_chill,
    BlockArchetype.SINGALONG.value: _render_singalong,
    BlockArchetype.GROOVE.value: _render_groove,
    BlockArchetype.DANCE_FLOOR.value: _render_dance_floor,
    BlockArchetype.CLUB_NIGHT.value: _render_club_night,
    BlockArchetype.LATE_NIGHT.value: _render_late_night,
    BlockArchetype.SUNRISE.value: _render_sunrise,
    BlockArchetype.CEREMONY.value: _render_ceremony,
    BlockArchetype.PEAK.value: _render_peak,
}


# ---------------------------------------------------------------------------
# Fake for tests
# ---------------------------------------------------------------------------

class FakeCoverArtService:
    """Returns a minimal valid JPEG for tests."""

    @staticmethod
    def generate_block_cover(archetype: Any = None, event_name: str = "") -> bytes:
        if HAS_PIL:
            buf = BytesIO()
            Image.new("RGB", (1, 1), "#000000").save(buf, format="JPEG")
            return buf.getvalue()
        return b"\xff\xd8\xff\xd9"  # minimal JPEG

    @staticmethod
    def generate_playlist_cover(session: Any = None) -> bytes:
        return FakeCoverArtService.generate_block_cover()

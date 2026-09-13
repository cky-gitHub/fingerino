"""Application icon.

The icon is drawn programmatically (no binary asset in the repo) and cached as
a multi-resolution ``.ico`` next to the downloaded model. The mark is a
stylised fingerprint: concentric arcs in the accent colour on a dark rounded
square, with the arc count thinned at small sizes so 16px still reads as a
fingerprint instead of a smudge.
"""

from __future__ import annotations

import os

from PIL import Image, ImageDraw

# Bumped when the artwork changes so cached icons are regenerated.
ICON_VERSION = 1
ICON_SIZES = (16, 20, 24, 32, 48, 64, 128, 256)

_BG_TOP = (34, 32, 30)
_BG_BOTTOM = (20, 19, 18)
_ACCENT = (196, 162, 112)      # RGB (config stores BGR)
_ACCENT_DIM = (150, 124, 86)


def _draw_icon(size: int) -> Image.Image:
    # Supersample, then downscale — gives clean anti-aliased arcs at every size.
    ss = 4
    n = size * ss
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Rounded-square plate with a subtle vertical gradient.
    radius = int(n * 0.22)
    plate = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    pd = ImageDraw.Draw(plate)
    for y in range(n):
        t = y / max(1, n - 1)
        pd.line(
            [(0, y), (n, y)],
            fill=tuple(int(a + (b - a) * t)
                       for a, b in zip(_BG_TOP, _BG_BOTTOM, strict=True)) + (255,),
        )
    mask = Image.new("L", (n, n), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, n - 1, n - 1], radius, fill=255)
    img.paste(plate, (0, 0), mask)

    # Fingerprint ridges: nested ovals, each open at the bottom like a real
    # print, the opening widening outward so it reads as a fingertip rather
    # than a bullseye. Fewer, chunkier ridges when the icon is tiny.
    ridges = 3 if size <= 24 else (4 if size <= 48 else 5)
    width = max(1, round(n * (0.075 if size <= 24 else 0.055)))
    cx, cy = n / 2, n / 2 - n * 0.03

    for i in range(ridges):
        f = (i + 1) / (ridges + 0.30)
        rx, ry = n * 0.30 * f, n * 0.355 * f
        # PIL angles: 0 deg = 3 o'clock, sweeping clockwise; 90 deg = bottom.
        half_gap = 14 + i * 4          # outer ridges open wider
        start, end = 90 + half_gap, 90 - half_gap
        d.arc([cx - rx, cy - ry, cx + rx, cy + ry], start, end,
              fill=_ACCENT, width=width)

    # Core: a short vertical ridge so the centre isn't hollow.
    core = n * 0.05
    d.rounded_rectangle(
        [cx - width / 2, cy - core, cx + width / 2, cy + core],
        width / 2, fill=_ACCENT,
    )

    return img.resize((size, size), Image.Resampling.LANCZOS)


def render(size: int) -> Image.Image:
    """Render the mark at ``size`` px. Used by the packaging icon builder."""
    return _draw_icon(size)


def icon_path(cache_dir: str) -> str | None:
    """Return a cached .ico, generating it on first use. None on failure."""
    path = os.path.join(cache_dir, f"fingerino-v{ICON_VERSION}.ico")
    if os.path.exists(path):
        return path
    try:
        frames = [_draw_icon(s) for s in ICON_SIZES]
        tmp = path + ".part"
        frames[-1].save(tmp, format="ICO",
                        sizes=[(s, s) for s in ICON_SIZES])
        os.replace(tmp, path)
        return path
    except Exception:
        return None  # a missing icon is cosmetic; never block startup

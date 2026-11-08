"""Application icon.

The icon is drawn in code (no binary asset in the repo) and cached as a
multi-resolution ``.ico`` next to the downloaded model. The mark is a black
shaka hand on a cream rounded square; the outlines come from the logo's SVG
(docs/brand/fingerino-logo.svg, 1024 units square). Up to 32px the hand is
drawn larger, so 16px still reads as a hand, and the plate's edge darker, so
it keeps its shape on a light taskbar. Every size is drawn on its own, not shrunk from the largest.
"""

from __future__ import annotations

import os

from PIL import Image, ImageDraw

# Bumped when the artwork changes so cached icons are regenerated.
ICON_VERSION = 2
ICON_SIZES = (16, 20, 24, 32, 48, 64, 128, 256)

_PLATE = (247, 242, 233)       # #F7F2E9
_EDGE = (200, 191, 177)        # #C8BFB1
_EDGE_SMALL = (150, 141, 127)  # darker, for the 1-2px edge of tiny icons
_INK = (23, 23, 23)            # #171717

# The hand: thumb, three curled fingers, and the little finger with the palm.
_HAND = (
    # thumb
    (201.5, 232.4, 180.0, 238.9, 160.2, 248.7, 145.3, 263.3, 142.0, 276.3,
     150.3, 292.6, 171.8, 315.3, 191.6, 343.0, 201.5, 360.8, 216.4, 396.6,
     231.2, 448.6, 259.3, 577.0, 269.2, 611.1, 287.4, 659.9, 285.7, 653.4,
     287.4, 601.4, 294.0, 562.4, 303.9, 529.9, 325.4, 482.7, 346.8, 448.6,
     373.3, 414.5, 374.9, 403.1, 365.0, 373.8, 341.9, 318.6, 325.4, 287.7,
     312.2, 268.2, 289.0, 247.1, 265.9, 235.7, 244.4, 230.8),
    # index
    (548.3, 336.5, 523.6, 321.8, 502.1, 317.0, 479.0, 321.8, 465.8, 330.0,
     454.2, 341.3, 348.5, 479.5, 340.2, 497.4, 340.2, 515.3, 346.8, 526.6,
     366.7, 541.3, 389.8, 551.0, 414.6, 552.6, 427.8, 547.8, 449.2, 525.0,
     558.2, 383.6, 563.2, 369.0, 563.2, 360.8, 558.2, 347.8),
    # middle
    (639.2, 401.5, 611.1, 388.5, 596.2, 388.5, 586.3, 391.7, 573.1, 401.5,
     487.2, 510.4, 459.1, 549.4, 455.8, 559.1, 455.8, 568.9, 459.1, 578.6,
     469.1, 590.0, 493.8, 604.6, 510.3, 609.5, 531.8, 607.9, 546.7, 596.5,
     655.7, 450.2, 659.0, 442.1, 659.0, 424.2, 652.4, 412.9),
    # ring finger, little finger and palm
    (910.0, 347.8, 896.8, 333.2, 886.9, 326.7, 877.0, 323.5, 852.2, 325.1,
     840.7, 331.6, 829.1, 343.0, 739.9, 474.6, 726.7, 461.6, 711.8, 453.5,
     692.0, 450.2, 672.2, 456.7, 571.5, 586.8, 563.2, 599.8, 559.9, 611.1,
     563.2, 624.2, 573.1, 633.9, 596.2, 643.7, 614.4, 646.9, 642.5, 646.9,
     644.1, 645.3, 670.6, 643.7, 710.2, 635.5, 746.5, 622.5, 749.8, 622.5,
     751.5, 624.2, 706.9, 643.7, 677.2, 653.4, 632.6, 663.2, 533.5, 674.5,
     426.1, 690.8, 356.7, 698.9, 313.8, 707.0, 313.8, 710.3, 348.5, 742.8,
     441.0, 819.2, 467.4, 835.5, 497.1, 845.2, 525.2, 846.8, 553.3, 840.3,
     576.4, 829.0, 611.1, 799.7, 678.8, 720.1, 761.4, 612.8, 882.0, 447.0,
     905.1, 411.2, 915.0, 388.5, 916.6, 367.3),
)
_HAND_CENTRE = (529.3, 538.9)  # middle of the hand's bounding box


def _draw_icon(size: int) -> Image.Image:
    # Supersample, then downscale: clean anti-aliased edges at every size.
    ss = 4 if size >= 64 else 8
    n = size * ss
    small = size <= 32

    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    edge = max(ss, round(n * 10 / 1024))
    d.rounded_rectangle([0, 0, n - 1, n - 1], round(n * 235 / 1024),
                        fill=_PLATE + (255,),
                        outline=(_EDGE_SMALL if small else _EDGE) + (255,),
                        width=edge)

    # Tiny icons get a bigger hand: there is no room to spare for margins.
    scale = n / 1024 * (1.18 if small else 1.0)
    cx, cy = _HAND_CENTRE
    ink = Image.new("L", (n, n), 0)
    di = ImageDraw.Draw(ink)
    for outline in _HAND:
        pts = [(n / 2 + (x - cx) * scale, n / 2 + (y - cy) * scale)
               for x, y in zip(outline[::2], outline[1::2], strict=True)]
        di.polygon(pts, fill=255)
    img.paste(Image.new("RGBA", (n, n), _INK + (255,)), (0, 0), ink)

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
                        sizes=[(s, s) for s in ICON_SIZES],
                        append_images=frames[:-1])
        os.replace(tmp, path)
    except Exception:
        return None  # a missing icon is cosmetic; never block startup
    for old in range(1, ICON_VERSION):  # the icons this one replaces
        try:
            os.remove(os.path.join(cache_dir, f"fingerino-v{old}.ico"))
        except OSError:
            pass
    return path

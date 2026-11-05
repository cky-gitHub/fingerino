"""Synthetic hands: 21 MediaPipe-style landmarks built from a description.

Enough anatomy for the posture tests -- each finger is a straight chain that is
either extended away from the wrist or folded back over the palm -- and nothing
more. Coordinates are normalised to the frame (0..1), y down, like MediaPipe's.

Landmark reference: 0 wrist · 1-4 thumb · 5-8 index · 9-12 middle ·
13-16 ring · 17-20 pinky (each finger MCP/PIP/DIP/TIP).
"""

from __future__ import annotations

import math

Landmark = tuple[float, float, float]

# Knuckle x offsets across the palm, in hand-size units, index -> pinky.
_KNUCKLE_X = (-0.3, -0.1, 0.1, 0.3)
# (PIP, DIP, TIP) heights above the knuckles, in hand-size units (+ = up).
_EXTENDED = (0.4, 0.65, 0.9)
_CURLED = (0.3, 0.15, 0.0)


def hand(*, thumb: bool = False, index: bool = False, middle: bool = False,
         ring: bool = False, pinky: bool = False,
         x: float = 0.5, y: float = 0.5, size: float = 0.1,
         angle: float = 0.0) -> list[Landmark]:
    """An upright hand with the given fingers out, centred on the middle knuckle.

    ``size`` is the wrist-to-middle-knuckle distance (the detector's hand
    scale). ``angle`` rotates the whole hand about its wrist, in degrees,
    positive tipping the fingers towards +x.
    """
    s = size
    wrist = (0.0, s)                    # relative to the middle knuckle
    pts: list[tuple[float, float]] = [wrist]
    # Thumb: CMC, MCP, IP, TIP, sweeping out to the -x side when extended.
    pts += [(-0.35 * s, 0.8 * s), (-0.55 * s, 0.6 * s)]
    if thumb:
        pts += [(-0.8 * s, 0.4 * s), (-1.05 * s, 0.25 * s)]
    else:
        pts += [(-0.45 * s, 0.45 * s), (-0.2 * s, 0.5 * s)]
    for kx, out in zip(_KNUCKLE_X, (index, middle, ring, pinky), strict=True):
        pts.append((kx * s, 0.0))
        pts += [(kx * s, -h * s) for h in (_EXTENDED if out else _CURLED)]

    a = math.radians(angle)
    ca, sa = math.cos(a), math.sin(a)
    wx, wy = wrist
    result = []
    for px, py in pts:
        dx, dy = px - wx, py - wy
        # Rotating "up" (-y) towards +x is a clockwise turn on screen.
        rx, ry = dx * ca - dy * sa, dx * sa + dy * ca
        result.append((x + wx + rx, y + wy + ry, 0.0))
    return result


def shaka(**kw) -> list[Landmark]:
    return hand(thumb=True, pinky=True, **kw)


def point(**kw) -> list[Landmark]:
    return hand(index=True, **kw)


def two_finger(**kw) -> list[Landmark]:
    return hand(index=True, middle=True, **kw)


def flat(**kw) -> list[Landmark]:
    return hand(thumb=True, index=True, middle=True, ring=True, pinky=True, **kw)


def fist(**kw) -> list[Landmark]:
    return hand(**kw)


def crossed() -> list[list[Landmark]]:
    """Two hands crossed into an X at the wrists' midline."""
    return [flat(x=0.42, y=0.55, angle=40), flat(x=0.58, y=0.55, angle=-40)]


def both_palms() -> list[list[Landmark]]:
    """Two open palms side by side, not crossing."""
    return [flat(x=0.3, y=0.5), flat(x=0.7, y=0.5)]

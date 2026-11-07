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


# Fingers neither out nor in: how a hand looks resting in view.
_RELAXED = (0.35, 0.45, 0.45)


def hand(*, thumb: bool = False, index: bool = False, middle: bool = False,
         ring: bool = False, pinky: bool = False,
         x: float = 0.5, y: float = 0.5, size: float = 0.1,
         angle: float = 0.0, relaxed: bool = False,
         cross: bool = False) -> list[Landmark]:
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
    elif relaxed:
        pts += [(-0.65 * s, 0.4 * s), (-0.6 * s, 0.2 * s)]
    else:
        pts += [(-0.45 * s, 0.45 * s), (-0.2 * s, 0.5 * s)]
    for kx, out in zip(_KNUCKLE_X, (index, middle, ring, pinky), strict=True):
        pts.append((kx * s, 0.0))
        folded = _RELAXED if relaxed else _CURLED
        pts += [(kx * s, -h * s) for h in (_EXTENDED if out else folded)]

    if cross:
        # Index and middle swap sides: the index tip lands right of the middle tip.
        for k, (dx_i, dx_m) in zip((6, 7, 8), ((0.1, -0.03), (0.2, -0.07), (0.3, -0.1)),
                                   strict=True):
            pts[k] = (pts[k][0] + dx_i * s, pts[k][1])
            pts[k + 4] = (pts[k + 4][0] + dx_m * s, pts[k + 4][1])

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


def crossed_fingers(**kw) -> list[Landmark]:
    """Index and middle crossed over each other, ring and pinky folded."""
    return hand(index=True, middle=True, cross=True, **kw)


def both_palms() -> list[list[Landmark]]:
    """Two open palms side by side, not crossing."""
    return [flat(x=0.3, y=0.5), flat(x=0.7, y=0.5)]


def thumbs_up(**kw) -> list[Landmark]:
    """A fist with the thumb out, turned so the thumb points up."""
    return hand(thumb=True, **{"angle": 55.0, **kw})


def thumbs_down(**kw) -> list[Landmark]:
    """The same shape turned upside down."""
    return hand(thumb=True, **{"angle": 235.0, **kw})


def peace(**kw) -> list[Landmark]:
    return hand(index=True, middle=True, **kw)


def relaxed(**kw) -> list[Landmark]:
    return hand(relaxed=True, **kw)


def mirrored(lms: list[Landmark]) -> list[Landmark]:
    """The same pose made by the other hand: a left-right mirror image."""
    cx = lms[0][0]
    return [(2 * cx - px, py, pz) for px, py, pz in lms]


def jitter(lms: list[Landmark], rng, amount: float = 0.015,
           size: float = 0.1) -> list[Landmark]:
    """Tracker noise: each landmark nudged by up to ``amount`` hand sizes."""
    a = amount * size
    return [(px + rng.uniform(-a, a), py + rng.uniform(-a, a), pz) for px, py, pz in lms]


def recording(make, rng, n: int = 30, wobble: float = 8.0, **kw) -> list[list[Landmark]]:
    """What a few seconds of holding a sign gives: the pose, drifting a
    little in position, size and angle, with tracker noise on top."""
    base_angle = kw.pop("angle", None)
    out = []
    for _ in range(n):
        extra = {"x": 0.5 + rng.uniform(-0.1, 0.1), "y": 0.5 + rng.uniform(-0.1, 0.1),
                 "size": 0.1 * rng.uniform(0.85, 1.15)}
        if base_angle is not None:
            extra["angle"] = base_angle + rng.uniform(-wobble, wobble)
        lms = make(**{**kw, **extra}) if base_angle is not None else \
            _rotated(make(**{**kw, **extra}), rng.uniform(-wobble, wobble))
        out.append(jitter(lms, rng))
    return out


def _rotated(lms: list[Landmark], degrees: float) -> list[Landmark]:
    """Rotate a finished hand about its wrist (positive: fingers towards +x)."""
    a = math.radians(degrees)
    ca, sa = math.cos(a), math.sin(a)
    wx, wy, _ = lms[0]
    return [(wx + (px - wx) * ca - (py - wy) * sa, wy + (px - wx) * sa + (py - wy) * ca, pz)
            for px, py, pz in lms]

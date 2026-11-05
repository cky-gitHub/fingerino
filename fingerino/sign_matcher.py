"""Recognising the user's own signs from a handful of recorded samples.

No training step: a sign is just the samples recorded for it, and a live hand
is compared with every sample (nearest neighbour). What makes that work is
comparing the right thing.

**Normalising.** Landmarks arrive as fractions of a 16:9 frame, so x is first
rescaled to the same units as y. Then the wrist is moved to the origin, the
hand is scaled to a fixed size (the mean wrist-to-knuckle distance, which
barely changes as fingers bend), and a left hand is mirrored onto a right one
so a sign recorded with either hand works with both.

**Shape and orientation, separately.** The posture predicates in
gesture_detector measure distances to the wrist, which throws orientation
away -- thumbs up and thumbs down would look the same. Here the shape is
compared with the hand rotated upright, and the hand's orientation (the angle
of the wrist-to-middle-knuckle axis) is compared on its own, with a tolerance.
So a sign made a little tilted still matches, while the same shape turned
upside down is a different sign.

**Rejecting weak matches.** A match must be close in absolute terms
(``SIGN_MATCH_MAX_DIST``) and clearly closer to one sign than to any other
(``SIGN_MATCH_MARGIN``); otherwise the answer is "no sign". A relaxed hand
should almost always land here.

Standard library only, so it runs in the dependency-free CI job.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from . import config

Landmark = tuple[float, float, float]
Landmarks = list[Landmark]
Point = tuple[float, float, float]

_WRIST = 0
_MIDDLE_MCP = 9
_KNUCKLES = (5, 9, 13, 17)
# Depth is MediaPipe's noisiest axis; it counts, but for less.
_Z_WEIGHT = 0.5


def canonical(lms: Landmarks, handedness: str | None = None,
              aspect: float | None = None) -> list[Point]:
    """Wrist at the origin, hand size 1, x in the same units as y, right-handed.

    This is what signs.json stores for each sample: it is independent of where
    the hand was in the frame, how far from the camera, and which hand made
    it, but it keeps the hand's orientation.
    """
    if aspect is None:
        aspect = config.CAMERA_WIDTH / config.CAMERA_HEIGHT
    wx, wy, wz = lms[_WRIST]
    pts = [((x - wx) * aspect, y - wy, (z - wz) * aspect) for x, y, z in lms]
    scale = sum(math.hypot(pts[i][0], pts[i][1]) for i in _KNUCKLES) / len(_KNUCKLES)
    scale = max(scale, 1e-6)
    mirror = -1.0 if handedness == "Left" else 1.0
    return [(mirror * x / scale, y / scale, z / scale) for x, y, z in pts]


@dataclass(frozen=True)
class Features:
    shape: tuple[float, ...]      # canonical points, rotated upright, flattened
    angle: float                  # orientation of the palm axis, radians; 0 = up


def features(points: list[Point]) -> Features:
    """Split canonical points into an upright shape and an orientation."""
    ax, ay = points[_MIDDLE_MCP][0], points[_MIDDLE_MCP][1]
    angle = math.atan2(ax, -ay)          # 0 when the knuckles are above the wrist
    c, s = math.cos(angle), math.sin(angle)
    shape: list[float] = []
    for x, y, z in points:
        # Rotate by -angle so the palm axis points straight up.
        shape += [x * c + y * s, -x * s + y * c, z * _Z_WEIGHT]
    return Features(tuple(shape), angle)


def shape_distance(a: Features, b: Features) -> float:
    """Root-mean-square distance between corresponding landmarks."""
    total = 0.0
    sa, sb = a.shape, b.shape
    for i in range(0, len(sa), 3):
        dx, dy, dz = sa[i] - sb[i], sa[i + 1] - sb[i + 1], sa[i + 2] - sb[i + 2]
        total += dx * dx + dy * dy + dz * dz
    return math.sqrt(total / (len(sa) // 3))


def angle_between(a: float, b: float) -> float:
    """Smallest difference between two angles, in degrees (0..180)."""
    d = abs(a - b) % (2 * math.pi)
    return math.degrees(min(d, 2 * math.pi - d))


@dataclass
class Sign:
    """A user's sign: a name and the samples recorded for it."""
    id: str
    name: str
    samples: list[list[Point]]            # canonical points, see canonical()
    enabled: bool = True
    # A built-in the sign looked like when recorded ("" if none); kept so the
    # card can say the sign may never fire. See signs.Library.warning.
    builtin: str = ""
    _features: list[Features] = field(default_factory=list, repr=False, compare=False)

    def feature_list(self) -> list[Features]:
        if len(self._features) != len(self.samples):
            self._features = [features(s) for s in self.samples]
        return self._features


@dataclass(frozen=True)
class Match:
    sign_id: str
    distance: float                       # shape distance to the nearest sample
    second: float                         # nearest distance for any other sign


class Matcher:
    """Nearest-neighbour matching against a fixed set of signs.

    Immutable once built: the session swaps in a new one when signs change,
    so it is safe to share across threads without a lock.
    """

    def __init__(self, signs: list[Sign]) -> None:
        self._signs = [(s.id, s.feature_list()) for s in signs if s.enabled and s.samples]

    def __bool__(self) -> bool:
        return bool(self._signs)

    def nearest(self, live: Features) -> list[tuple[float, str]]:
        """(distance, sign id) per sign, nearest first, over samples whose
        orientation is within tolerance; signs with none are left out."""
        out = []
        for sign_id, feats in self._signs:
            best = math.inf
            for f in feats:
                if angle_between(f.angle, live.angle) > config.SIGN_MAX_ANGLE_DEG:
                    continue
                best = min(best, shape_distance(live, f))
            if best < math.inf:
                out.append((best, sign_id))
        out.sort()
        return out

    def match(self, lms: Landmarks, handedness: str | None = None) -> Match | None:
        """The sign this hand is making, or None if it isn't clearly one."""
        if not self._signs:
            return None
        # Without handedness, either mirror might be the right one: take the
        # better. With it, canonical() has already made the hand right-handed.
        candidates = [handedness] if handedness in ("Left", "Right") else ["Right", "Left"]
        best: list[tuple[float, str]] = []
        for hand in candidates:
            ranked = self.nearest(features(canonical(lms, hand)))
            if ranked and (not best or ranked[0][0] < best[0][0]):
                best = ranked
        if not best:
            return None
        distance, sign_id = best[0]
        second = best[1][0] if len(best) > 1 else math.inf
        if distance > config.SIGN_MATCH_MAX_DIST:
            return None
        if second < distance * config.SIGN_MATCH_MARGIN:
            return None                   # too close to call between two signs
        return Match(sign_id, distance, second)


class SignHold:
    """Turns per-frame matches into one firing per deliberate hold.

    A sign fires after being held for ``SIGN_HOLD_S`` -- longer than the
    shaka's, because a custom sign is matched less strictly than a built-in
    posture and hands are in view all day. It fires once per hold: the hand
    has to leave the sign before it can fire again. A frame or two of lost
    tracking inside ``SIGN_RELEASE_GRACE_S`` doesn't restart the count.
    """

    def __init__(self) -> None:
        self._id: str | None = None
        self._since = 0.0
        self._last_seen = -1e9
        self._fired = False
        self._last_fire = -1e9

    def update(self, sign_id: str | None, now: float) -> tuple[str | None, str | None, float]:
        """Feed this frame's match; get (fired, pending, progress 0..1)."""
        if sign_id is None:
            if self._id is not None and now - self._last_seen > config.SIGN_RELEASE_GRACE_S:
                self._id = None
                self._fired = False
            return None, None, 0.0
        if sign_id != self._id:
            self._id, self._since, self._fired = sign_id, now, False
        self._last_seen = now
        if self._fired:
            return None, None, 0.0
        progress = min(1.0, (now - self._since) / max(config.SIGN_HOLD_S, 1e-6))
        if progress >= 1.0 and now - self._last_fire >= config.SIGN_COOLDOWN_S:
            self._fired = True
            self._last_fire = now
            return sign_id, None, 0.0
        return None, sign_id, progress

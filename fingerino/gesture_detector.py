"""Gesture recognition: turns raw hand landmarks into high-level intents.

The engine classifies the primary hand's posture into a *mode* and emits
discrete events each frame:

    posture              -> mode      -> action
    -----------------------------------------------------------------
    index out, middle in -> move      -> drive cursor; a fresh point = click
    index + middle out   -> scroll    -> vertical fingertip motion scrolls
    flat hand (4 out)    -> flat      -> a downward wave minimises windows
    both hands crossed   -> exit      -> hold the "X" briefly to quit

All thresholds live in ``config``. Every posture test is built from distances
to the wrist, so it is rotation-invariant — the gestures work whichever way
the hand is turned.

Landmark reference: 0 wrist · 4 thumb tip · 5-8 index · 9-12 middle ·
13-16 ring · 17-20 pinky (each finger MCP/PIP/DIP/TIP).
"""

from __future__ import annotations

import enum
import math
from collections import deque
from dataclasses import dataclass
from typing import Callable

from . import config

Landmark = tuple[float, float, float]
Landmarks = list[Landmark]

_WRIST = 0
_MIDDLE_MCP = 9
_INDEX_TIP = 8
_MIDDLE_TIP = 12
_PALM_POINTS = (0, 5, 9, 13, 17)
# Scroll follows the two extended fingertips, so the motion that drives the
# wheel is the one the user is actually watching.
_SCROLL_POINTS = (_INDEX_TIP, _MIDDLE_TIP)
# (tip, pip) per finger.
_INDEX = (8, 6)
_MIDDLE = (12, 10)
_RING = (16, 14)
_PINKY = (20, 18)
_THUMB = (4, 2)               # thumb tip vs thumb MCP
_FOUR = (_INDEX, _MIDDLE, _RING, _PINKY)


def _dist(a: Landmark, b: Landmark) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _hand_scale(lms: Landmarks) -> float:
    return max(_dist(lms[_WRIST], lms[_MIDDLE_MCP]), 1e-6)


def _palm_center(lms: Landmarks) -> tuple[float, float]:
    xs = sum(lms[i][0] for i in _PALM_POINTS) / len(_PALM_POINTS)
    ys = sum(lms[i][1] for i in _PALM_POINTS) / len(_PALM_POINTS)
    return xs, ys


def scroll_point(lms: Landmarks) -> tuple[float, float]:
    """Midpoint of the index and middle fingertips — the scroll anchor.

    Averaging the two tips rather than picking one keeps the anchor steady if
    a single fingertip is momentarily mis-landmarked.
    """
    xs = sum(lms[i][0] for i in _SCROLL_POINTS) / len(_SCROLL_POINTS)
    ys = sum(lms[i][1] for i in _SCROLL_POINTS) / len(_SCROLL_POINTS)
    return xs, ys


def _extended(lms: Landmarks, finger: tuple[int, int], margin_frac: float) -> bool:
    wrist = lms[_WRIST]
    margin = margin_frac * _hand_scale(lms)
    tip, pip = finger
    return _dist(lms[tip], wrist) > _dist(lms[pip], wrist) + margin


# ---------------------------------------------------------------------------
# Posture predicates
# ---------------------------------------------------------------------------
def is_index_extended(lms: Landmarks) -> bool:
    return _extended(lms, _INDEX, config.INDEX_EXTEND_MARGIN)


def is_pointing(lms: Landmarks) -> bool:
    """Index out, middle in — the click posture."""
    return is_index_extended(lms) and not _extended(lms, _MIDDLE, config.FINGER_EXTEND_MARGIN)


def is_two_finger(lms: Landmarks) -> bool:
    """Index + middle out, ring + pinky in — the scroll posture."""
    m = config.FINGER_EXTEND_MARGIN
    return (
        _extended(lms, _INDEX, m)
        and _extended(lms, _MIDDLE, m)
        and not _extended(lms, _RING, m)
        and not _extended(lms, _PINKY, m)
    )


def is_flat_hand(lms: Landmarks) -> bool:
    """All four fingers extended — an open palm."""
    m = config.FINGER_EXTEND_MARGIN
    return all(_extended(lms, f, m) for f in _FOUR)


def is_fist(lms: Landmarks) -> bool:
    m = config.FINGER_EXTEND_MARGIN
    return not any(_extended(lms, f, m) for f in _FOUR)


def is_thumb_extended(lms: Landmarks) -> bool:
    return _extended(lms, _THUMB, config.THUMB_EXTEND_MARGIN)


def is_shaka(lms: Landmarks) -> bool:
    """Thumb + pinky out, middle three in — the "call me" / shaka sign."""
    m = config.FINGER_EXTEND_MARGIN
    return (
        is_thumb_extended(lms)
        and _extended(lms, _PINKY, m)
        and not _extended(lms, _INDEX, m)
        and not _extended(lms, _MIDDLE, m)
        and not _extended(lms, _RING, m)
    )


# ---------------------------------------------------------------------------
# Geometry for the two-hand "X"
# ---------------------------------------------------------------------------
def _ccw(a, b, c) -> float:
    return (c[1] - a[1]) * (b[0] - a[0]) - (b[1] - a[1]) * (c[0] - a[0])


def _segments_cross(p1, p2, p3, p4) -> bool:
    d1, d2 = _ccw(p3, p4, p1), _ccw(p3, p4, p2)
    d3, d4 = _ccw(p1, p2, p3), _ccw(p1, p2, p4)
    return (d1 > 0) != (d2 > 0) and (d3 > 0) != (d4 > 0)


def _cross_angle_deg(p1, p2, p3, p4) -> float:
    v1 = (p2[0] - p1[0], p2[1] - p1[1])
    v2 = (p4[0] - p3[0], p4[1] - p3[1])
    n1, n2 = math.hypot(*v1), math.hypot(*v2)
    if n1 == 0 or n2 == 0:
        return 0.0
    c = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)))
    a = math.degrees(math.acos(c))
    return min(a, 180.0 - a)  # undirected crossing angle


# ---------------------------------------------------------------------------
# Rising-edge click trigger (debounced, armed only after a release)
# ---------------------------------------------------------------------------
class _State(enum.Enum):
    READY = "READY"
    HELD = "HELD"


class ClickTrigger:
    def __init__(self, predicate: Callable[[Landmarks], bool] = is_pointing) -> None:
        self._predicate = predicate
        self.state = _State.READY
        self._last_t = -1e9
        self._armed = False

    def reset(self) -> None:
        self.state = _State.READY
        self._armed = False

    def update(self, lms: Landmarks, now: float) -> bool:
        active = self._predicate(lms)
        if not active:
            self._armed = True
            self.state = _State.READY
            return False
        if self.state is _State.HELD:
            return False
        self.state = _State.HELD
        if not self._armed or now - self._last_t < config.CLICK_COOLDOWN_S:
            return False
        self._last_t = now
        return True


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
@dataclass
class GestureOutput:
    mode: str = "none"          # none | move | scroll | flat | shaka | exit
    mode_label: str = ""
    click: bool = False
    scroll_steps: int = 0
    minimize: bool = False      # flat swipe down
    restore: bool = False       # flat swipe up
    switch_window: bool = False  # flat swipe left (Alt+Tab)
    new_chat: bool = False      # shaka sign
    exit: bool = False
    exit_progress: float = 0.0  # 0..1 while the X is being held


class GestureEngine:
    def __init__(self) -> None:
        self._click = ClickTrigger(is_pointing)
        self._scroll_prev_y: float | None = None
        self._scroll_acc = 0.0
        self._swipe: deque[tuple[float, float, float]] = deque()  # (t, x, y)
        self._last_swipe_t = -1e9
        self._x_start: float | None = None
        self._shaka_start: float | None = None
        self._shaka_fired = False
        self._last_shaka_t = -1e9

    def reset(self) -> None:
        self._click.reset()
        self._scroll_prev_y = None
        self._scroll_acc = 0.0
        self._swipe.clear()
        self._x_start = None
        self._shaka_start = None
        self._shaka_fired = False

    def _reset_shaka(self) -> None:
        self._shaka_start = None
        self._shaka_fired = False

    # -- sub-behaviours ------------------------------------------------------
    def _check_exit(self, hands: list[Landmarks], now: float) -> float:
        if len(hands) < 2:
            self._x_start = None
            return 0.0
        a1, a2 = hands[0][_WRIST][:2], hands[0][_MIDDLE_TIP][:2]
        b1, b2 = hands[1][_WRIST][:2], hands[1][_MIDDLE_TIP][:2]
        if _segments_cross(a1, a2, b1, b2) and \
                _cross_angle_deg(a1, a2, b1, b2) >= config.EXIT_MIN_ANGLE_DEG:
            if self._x_start is None:
                self._x_start = now
            return min(1.0, (now - self._x_start) / config.EXIT_HOLD_S)
        self._x_start = None
        return 0.0

    def _scroll(self, lms: Landmarks) -> int:
        y = scroll_point(lms)[1]
        if self._scroll_prev_y is None:
            self._scroll_prev_y = y
            return 0
        dy = y - self._scroll_prev_y            # + = hand moved down
        self._scroll_prev_y = y
        sign = 1.0 if config.SCROLL_INVERT else -1.0  # hand down -> scroll down
        self._scroll_acc += dy * config.SCROLL_GAIN * sign
        steps = int(self._scroll_acc)
        self._scroll_acc -= steps
        return steps

    def _flat_swipe(self, lms: Landmarks, now: float) -> str | None:
        """Direction of a flat-hand swipe over the look-back window, or None.

        Whichever axis has the larger travel wins, provided it clears the
        threshold: down / up (vertical) or left / right (horizontal).
        """
        x, y = _palm_center(lms)
        self._swipe.append((now, x, y))
        while self._swipe and now - self._swipe[0][0] > config.WAVE_WINDOW_S:
            self._swipe.popleft()
        if now - self._last_swipe_t <= config.SWIPE_COOLDOWN_S:
            return None
        dx = x - self._swipe[0][1]
        dy = y - self._swipe[0][2]
        if abs(dy) >= abs(dx) and abs(dy) > config.WAVE_MIN_TRAVEL:
            direction = "down" if dy > 0 else "up"
        elif abs(dx) > config.WAVE_MIN_TRAVEL:
            direction = "left" if dx < 0 else "right"  # mirrored frame: -x = left
        else:
            return None
        self._last_swipe_t = now
        self._swipe.clear()
        return direction

    # -- main entry ----------------------------------------------------------
    def update(self, hands: list[Landmarks], now: float) -> GestureOutput:
        out = GestureOutput()
        if not hands:
            self.reset()
            return out

        # Two-hand "X" takes priority and suppresses everything else.
        progress = self._check_exit(hands, now)
        if progress > 0.0:
            self._click.reset()
            self._scroll_prev_y = None
            self._swipe.clear()
            self._reset_shaka()
            out.mode = "exit"
            out.mode_label = "Exit"
            out.exit_progress = progress
            out.exit = progress >= 1.0
            return out

        primary = hands[0]

        # Flat open hand -> directional swipes.
        if is_flat_hand(primary):
            self._click.reset()
            self._scroll_prev_y = None
            self._reset_shaka()
            out.mode = "flat"
            out.mode_label = "Flat"
            direction = self._flat_swipe(primary, now)
            if direction == "down":
                out.minimize = True
                out.mode_label = "Minimize"
            elif direction == "up":
                out.restore = True
                out.mode_label = "Restore"
            elif direction == "left":
                out.switch_window = True
                out.mode_label = "Switch"
            return out

        self._swipe.clear()

        # Two fingers -> scroll.
        if is_two_finger(primary):
            self._click.reset()
            self._reset_shaka()
            out.mode = "scroll"
            out.mode_label = "Scroll"
            out.scroll_steps = self._scroll(primary)
            return out

        self._scroll_prev_y = None

        # Shaka sign -> new AI chat (held briefly to avoid accidents).
        if is_shaka(primary):
            self._click.reset()
            out.mode = "shaka"
            out.mode_label = "New chat"
            if self._shaka_start is None:
                self._shaka_start = now
            if (now - self._shaka_start >= config.SHAKA_HOLD_S
                    and not self._shaka_fired
                    and now - self._last_shaka_t > config.SHAKA_COOLDOWN_S):
                out.new_chat = True
                self._shaka_fired = True
                self._last_shaka_t = now
            return out

        self._reset_shaka()

        # Default: move + click.
        out.mode = "move"
        out.mode_label = "Move"
        out.click = self._click.update(primary, now)
        return out

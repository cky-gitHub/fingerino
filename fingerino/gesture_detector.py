"""Gesture recognition: turns raw hand landmarks into high-level intents.

The engine classifies the primary hand's posture into a *mode* and emits
discrete events each frame:

    posture              -> mode      -> action
    -----------------------------------------------------------------
    index out, middle in -> move      -> drive cursor; a brief point clicks,
                                         a held one presses and drags
    index + middle out   -> scroll    -> vertical fingertip motion scrolls
    flat hand (4 out)    -> flat      -> a downward wave minimises windows
    both hands flat      -> hold      -> hold both palms still to pause
    both hands crossed   -> exit      -> hold the "X" briefly to quit

All thresholds live in ``config``. Every posture test is built from distances
to the wrist, so it is rotation-invariant — the gestures work whichever way
the hand is turned.

Landmark reference: 0 wrist · 4 thumb tip · 5-8 index · 9-12 middle ·
13-16 ring · 17-20 pinky (each finger MCP/PIP/DIP/TIP).
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import NamedTuple

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
    """Index out, middle in — the click / drag posture."""
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


def both_flat(hands: list[Landmarks]) -> bool:
    """Two open palms — the pause posture.

    One flat hand swipes and two of them pause, so this is checked first and
    suppresses the swipes entirely: raising both hands can't wave a window
    away on the way up, and the two gestures can never be read at once.
    """
    return len(hands) >= 2 and all(is_flat_hand(h) for h in hands[:2])


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
# Left-button trigger: a short point clicks, a held one presses and drags
# ---------------------------------------------------------------------------
class ButtonEdges(NamedTuple):
    click: bool = False         # a complete left click (a short point)
    press: bool = False         # button down — a drag is starting
    release: bool = False       # button up — the drag ended


class DragTrigger:
    """Turns the pointing posture into either a click or a press-and-hold drag.

    A point that ends before ``DRAG_HOLD_S`` is an ordinary click, and nothing
    is held down while it happens — pointing changes the shape of the hand,
    which drifts the tracked fingertip, and a button held through that drift
    is what turns an intended click into a stray drag. Keeping the index out
    past the threshold is unambiguous, and only then does the button go down
    and stay down until the finger relaxes.

    Both edges are debounced, with a longer grace once the button is down: a
    click arriving a frame late is cheap, dropping a drag halfway is not.
    """

    def __init__(self) -> None:
        self.down = False
        self._down_since = 0.0
        self._on_since: float | None = None   # posture held since (None = off)
        self._off_since: float | None = None  # posture broken since
        self._last_t = -1e9                   # last click or release
        # Ignore the posture until it has been seen broken once, so a hand
        # that arrives already pointing doesn't fire on sight.
        self._ignore = True

    def progress(self, now: float) -> float:
        """How far a pending point has come towards latching as a drag, 0..1."""
        if self.down or self._ignore or self._on_since is None:
            return 0.0
        return min(1.0, (now - self._on_since) / max(config.DRAG_HOLD_S, 1e-6))

    def update(self, active: bool, now: float) -> ButtonEdges:
        """Feed this frame's posture and get back the button edges it caused."""
        if active:
            self._off_since = None
            if self._ignore:
                return ButtonEdges()
            if self.down:
                if now - self._down_since < config.DRAG_MAX_S:
                    return ButtonEdges()
                # Safety valve: nothing legitimate holds this long, so the
                # posture is stuck (a frozen hand, a persistent mis-read).
                # Let go, and ignore it until it genuinely breaks.
                return ButtonEdges(release=self._end(now, ignore=True))
            if self._on_since is None:
                self._on_since = now
                return ButtonEdges()
            if (now - self._on_since >= config.DRAG_HOLD_S
                    and now - self._last_t >= config.CLICK_COOLDOWN_S):
                self.down = True
                self._down_since = now
                return ButtonEdges(press=True)
            return ButtonEdges()

        # Posture gone: whatever it was can start fresh next time.
        self._ignore = False
        if self._on_since is None and not self.down:
            return ButtonEdges()
        if self._off_since is None:
            self._off_since = now
        grace = (config.DRAG_RELEASE_GRACE_S if self.down
                 else config.CLICK_RELEASE_GRACE_S)
        if now - self._off_since < grace:
            return ButtonEdges()
        if self.down:
            return ButtonEdges(release=self._end(now))

        # A point that ended before the threshold: an ordinary click.
        self._on_since = self._off_since = None
        if now - self._last_t < config.CLICK_COOLDOWN_S:
            return ButtonEdges()
        self._last_t = now
        return ButtonEdges(click=True)

    def _end(self, now: float, ignore: bool = False) -> bool:
        """Drop the button and close out the episode. Always True — an edge."""
        self.down = False
        self._on_since = self._off_since = None
        self._last_t = now
        self._ignore = ignore
        return True


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
@dataclass
class GestureOutput:
    mode: str = "none"          # none | move | scroll | flat | shaka | hold | exit
    mode_label: str = ""
    click: bool = False         # a short point — a discrete left click
    press: bool = False         # left button just went down (drag starting)
    release: bool = False       # left button just came back up (drag ended)
    dragging: bool = False      # button currently held
    drag_progress: float = 0.0  # 0..1 while a point is arming into a drag
    scroll_steps: int = 0
    minimize: bool = False      # flat swipe down
    restore: bool = False       # flat swipe up
    switch_window: bool = False  # flat swipe left (Alt+Tab)
    new_chat: bool = False      # shaka sign
    hold_toggle: bool = False   # both palms held still — pause / resume
    hold_progress: float = 0.0  # 0..1 while both palms are being held
    exit: bool = False
    exit_progress: float = 0.0  # 0..1 while the X is being held


class GestureEngine:
    def __init__(self) -> None:
        self._drag = DragTrigger()
        self._scroll_prev_y: float | None = None
        self._scroll_acc = 0.0
        self._swipe: deque[tuple[float, float, float]] = deque()  # (t, x, y)
        self._last_swipe_t = -1e9
        self._x_start: float | None = None
        self._shaka_start: float | None = None
        self._shaka_fired = False
        self._last_shaka_t = -1e9
        self._hold_start: float | None = None
        self._hold_anchor: list[tuple[float, float]] | None = None
        self._hold_off_since: float | None = None
        self._hold_fired = False
        self._last_hold_t = -1e9

    def reset(self) -> None:
        """Forget posture history.

        The button trigger is deliberately left alone: it is fed every frame
        from :meth:`update`, so losing the hand goes through the same grace
        window as relaxing the finger instead of dropping a drag instantly.
        The both-palms hold is left alone for the same reason -- it expires
        through :meth:`_expire_hold`, not on the first frame that misses a
        hand.
        """
        self._scroll_prev_y = None
        self._scroll_acc = 0.0
        self._swipe.clear()
        self._x_start = None
        self._reset_shaka()

    def _reset_shaka(self) -> None:
        self._shaka_start = None
        self._shaka_fired = False

    def _reset_hold(self) -> None:
        self._hold_start = None
        self._hold_anchor = None
        self._hold_off_since = None
        self._hold_fired = False

    def _expire_hold(self, now: float) -> None:
        """Drop a pending hold once the posture has really gone.

        Grace-windowed rather than immediate: a hand the tracker misses for a
        frame or two is common enough that resetting on sight would make a
        one-second hold hard to finish, and it is the same window that has to
        pass before the gesture can toggle again.
        """
        if self._hold_start is None and not self._hold_fired:
            return
        if self._hold_off_since is None:
            self._hold_off_since = now
        elif now - self._hold_off_since >= config.HOLD_RELEASE_GRACE_S:
            self._reset_hold()

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

    def _check_hold(self, hands: list[Landmarks], now: float,
                    out: GestureOutput) -> None:
        """Count down the both-palms hold and emit the toggle when it lands.

        The countdown restarts whenever a palm travels more than
        ``HOLD_MAX_DRIFT``, so this really is "hold both hands up and wait"
        rather than "have both hands open for a moment while doing something
        else". It fires once per posture: the hands have to come down (or
        stop being flat) before another toggle is possible, which is what
        makes the same gesture pause and then resume.
        """
        self._hold_off_since = None
        centers = [_palm_center(h) for h in hands[:2]]
        if self._hold_start is None or self._drifted(centers):
            self._hold_start = now
            self._hold_anchor = centers
        if self._hold_fired:
            return
        progress = min(1.0, (now - self._hold_start) / max(config.HOLD_TOGGLE_S, 1e-6))
        out.hold_progress = progress
        if progress >= 1.0 and now - self._last_hold_t > config.HOLD_COOLDOWN_S:
            out.hold_toggle = True
            out.hold_progress = 0.0
            self._hold_fired = True
            self._last_hold_t = now

    def _drifted(self, centers: list[tuple[float, float]]) -> bool:
        if self._hold_anchor is None or len(self._hold_anchor) != len(centers):
            return True
        return any(math.hypot(c[0] - a[0], c[1] - a[1]) > config.HOLD_MAX_DRIFT
                   for c, a in zip(centers, self._hold_anchor, strict=True))

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
        pointing = self._classify(hands, now, out)

        # The button is driven from exactly one place, so every way of leaving
        # the posture — relaxing the finger, switching to another gesture,
        # losing the hand — takes the same release path and none of them can
        # strand it down.
        out.click, out.press, out.release = self._drag.update(pointing, now)
        out.dragging = self._drag.down
        out.drag_progress = self._drag.progress(now)
        if out.dragging and out.mode == "move":
            out.mode_label = "Drag"
        return out

    def _classify(self, hands: list[Landmarks], now: float,
                  out: GestureOutput) -> bool:
        """Fill ``out`` with this frame's mode and events.

        Returns whether the click/drag posture is being held, which is all the
        button trigger needs from the classification.
        """
        if not hands:
            self.reset()
            self._expire_hold(now)
            return False

        # Two-hand "X" takes priority and suppresses everything else.
        progress = self._check_exit(hands, now)
        if progress > 0.0:
            self._scroll_prev_y = None
            self._swipe.clear()
            self._reset_shaka()
            self._reset_hold()
            out.mode = "exit"
            out.mode_label = "Exit"
            out.exit_progress = progress
            out.exit = progress >= 1.0
            return False

        # Both palms up and still -> pause / resume everything. Ahead of the
        # flat-hand swipes because the postures overlap: one open hand is a
        # swipe, two are the master switch, and the swipe path has to be shut
        # out entirely or raising both hands would minimise a window first.
        if both_flat(hands):
            self._scroll_prev_y = None
            self._swipe.clear()
            self._reset_shaka()
            out.mode = "hold"
            out.mode_label = "Hold"
            self._check_hold(hands, now, out)
            return False

        self._expire_hold(now)
        primary = hands[0]

        # Flat open hand -> directional swipes.
        if is_flat_hand(primary):
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
            return False

        self._swipe.clear()

        # Two fingers -> scroll.
        if is_two_finger(primary):
            self._reset_shaka()
            out.mode = "scroll"
            out.mode_label = "Scroll"
            out.scroll_steps = self._scroll(primary)
            return False

        self._scroll_prev_y = None

        # Shaka sign -> new AI chat (held briefly to avoid accidents).
        if is_shaka(primary):
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
            return False

        self._reset_shaka()

        # Default: move, and point to click / hold the point to drag.
        out.mode = "move"
        out.mode_label = "Move"
        return is_pointing(primary)

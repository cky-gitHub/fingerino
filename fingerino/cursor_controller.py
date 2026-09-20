"""Maps the tracked fingertip to a screen coordinate, smooths it with a
One Euro Filter, and drives the OS cursor via pynput.

The left button is exposed both ways: a one-shot ``click`` for a quick point,
and ``press`` / ``release`` for a held one, which is what drags.
"""

from __future__ import annotations

import math
import sys
from collections import deque

from pynput.mouse import Button, Controller

from . import config


# ---------------------------------------------------------------------------
# One Euro Filter
# ---------------------------------------------------------------------------
def _smoothing_factor(t_e: float, cutoff: float) -> float:
    r = 2.0 * math.pi * cutoff * t_e
    return r / (r + 1.0)


def _exp_smooth(alpha: float, x: float, x_prev: float) -> float:
    return alpha * x + (1.0 - alpha) * x_prev


class _OneEuro:
    """Scalar One Euro Filter (Casiez et al., 2012)."""

    def __init__(self, min_cutoff: float, beta: float, d_cutoff: float):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self.x_prev: float | None = None
        self.dx_prev = 0.0
        self.t_prev: float | None = None

    def reset(self) -> None:
        self.x_prev = None
        self.dx_prev = 0.0
        self.t_prev = None

    def __call__(self, t: float, x: float) -> float:
        if self.x_prev is None or self.t_prev is None:
            self.x_prev = x
            self.t_prev = t
            return x

        t_e = t - self.t_prev
        if t_e <= 0.0:
            return self.x_prev

        a_d = _smoothing_factor(t_e, self.d_cutoff)
        dx = (x - self.x_prev) / t_e
        dx_hat = _exp_smooth(a_d, dx, self.dx_prev)

        cutoff = self.min_cutoff + self.beta * abs(dx_hat)
        a = _smoothing_factor(t_e, cutoff)
        x_hat = _exp_smooth(a, x, self.x_prev)

        self.x_prev = x_hat
        self.dx_prev = dx_hat
        self.t_prev = t
        return x_hat


def _screen_size_macos() -> tuple[int, int] | None:
    """Main display size from CoreGraphics, or None if it can't be read.

    Asked of the OS directly rather than through a GUI toolkit, because the
    packaged app ships no toolkit at all.
    """
    import ctypes

    try:
        cg = ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
        cg.CGMainDisplayID.restype = ctypes.c_uint32
        cg.CGDisplayPixelsWide.restype = ctypes.c_size_t
        cg.CGDisplayPixelsWide.argtypes = [ctypes.c_uint32]
        cg.CGDisplayPixelsHigh.restype = ctypes.c_size_t
        cg.CGDisplayPixelsHigh.argtypes = [ctypes.c_uint32]
        display = cg.CGMainDisplayID()
        w, h = int(cg.CGDisplayPixelsWide(display)), int(cg.CGDisplayPixelsHigh(display))
        return (w, h) if w > 0 and h > 0 else None
    except Exception:
        return None


def _get_screen_size() -> tuple[int, int]:
    """Physical primary-screen resolution, DPI-aware on Windows."""
    if sys.platform.startswith("win"):
        import ctypes

        try:
            # Per-monitor DPI awareness so coordinates are physical pixels
            # and line up with what pynput's SetCursorPos expects.
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass
        user32 = ctypes.windll.user32
        return int(user32.GetSystemMetrics(0)), int(user32.GetSystemMetrics(1))

    if sys.platform == "darwin":
        size = _screen_size_macos()
        if size:
            return size

    # Last resort for Linux: tkinter. Deliberately not the macOS path — the
    # packaged app excludes tkinter, so there it would always fall through to
    # the hardcoded guess below and map the cursor to the wrong screen.
    try:
        import tkinter

        root = tkinter.Tk()
        root.withdraw()
        size = (root.winfo_screenwidth(), root.winfo_screenheight())
        root.destroy()
        return size
    except Exception:
        return (1920, 1080)


class CursorController:
    """Translates a normalized fingertip position into smoothed cursor moves."""

    def __init__(self) -> None:
        self._mouse = Controller()
        self.screen_w, self.screen_h = _get_screen_size()

        self._fx = _OneEuro(
            config.ONE_EURO_MIN_CUTOFF, config.ONE_EURO_BETA, config.ONE_EURO_D_CUTOFF
        )
        self._fy = _OneEuro(
            config.ONE_EURO_MIN_CUTOFF, config.ONE_EURO_BETA, config.ONE_EURO_D_CUTOFF
        )

        # Last smoothed screen position (for click location + HUD).
        self.last_screen: tuple[int, int] | None = None

        # Recent (time, x, y), newest last. Read by anchor_at() so a button can
        # be delivered where the cursor was before the hand started reshaping
        # to produce the gesture. Bounded by CURSOR_HISTORY_S, so at 30 fps
        # this is a few dozen tuples.
        self._history: deque[tuple[float, int, int]] = deque()

        # Whether the left button is currently held. Tracked here so releases
        # are idempotent and shutdown can let go unconditionally.
        self.pressed = False

    def reset(self) -> None:
        """Drop filter history — call when the hand is lost so the cursor does
        not lurch when tracking resumes elsewhere.

        The position history goes too: once the hand has been lost, where the
        cursor was before it vanished says nothing about where the user is
        aiming now, and anchoring a click there would be worse than not
        anchoring at all.
        """
        self._fx.reset()
        self._fy.reset()
        self._history.clear()

    @staticmethod
    def _map_zone(value: float, margin: float) -> float:
        """Map a normalized frame coordinate through the control zone to 0..1."""
        lo = margin
        hi = 1.0 - margin
        if hi <= lo:
            return value
        return (value - lo) / (hi - lo)

    def update(self, norm_x: float, norm_y: float, t: float) -> tuple[int, int]:
        """Feed a raw normalized fingertip position; move + return the cursor.

        norm_x / norm_y are in [0, 1] frame coordinates (already mirrored to
        match the displayed frame).
        """
        zx = self._map_zone(norm_x, config.CONTROL_ZONE_X_MARGIN)
        zy = self._map_zone(norm_y, config.CONTROL_ZONE_Y_MARGIN)

        # Clamp to the zone so the cursor pins to an edge instead of jumping
        # when the finger drifts outside the mapped rectangle.
        zx = min(max(zx, 0.0), 1.0)
        zy = min(max(zy, 0.0), 1.0)

        sx = self._fx(t, zx * self.screen_w)
        sy = self._fy(t, zy * self.screen_h)

        ix = int(min(max(sx, 0), self.screen_w - 1))
        iy = int(min(max(sy, 0), self.screen_h - 1))

        self._mouse.position = (ix, iy)
        self.last_screen = (ix, iy)

        self._history.append((t, ix, iy))
        cutoff = t - config.CURSOR_HISTORY_S
        while self._history and self._history[0][0] < cutoff:
            self._history.popleft()
        return ix, iy

    def anchor_at(self, t: float) -> tuple[int, int] | None:
        """Where the cursor was at time ``t``, or None if that is not on record.

        Nearest recorded sample rather than an interpolation: the samples are a
        frame apart and already smoothed, so interpolating between them would
        invent precision that isn't there.
        """
        if not self._history:
            return None
        best = min(self._history, key=lambda row: abs(row[0] - t))
        return best[1], best[2]

    def _anchor(self, anchor_t: float | None) -> None:
        """Put the cursor back where it was before the gesture reshaped the hand.

        ``anchor_t`` is when the pointing posture registered. The lookback goes
        back further still, because the finger has to travel past
        INDEX_EXTEND_MARGIN before the posture is recognised and the drift
        starts on the first millimetre of that travel.
        """
        if not config.CLICK_ANCHOR or anchor_t is None:
            return
        target = self.anchor_at(anchor_t - config.CLICK_ANCHOR_LOOKBACK_S)
        if target is None:
            return
        self._mouse.position = target
        self.last_screen = target

    def click(self, anchor_t: float | None = None) -> None:
        """One discrete left click, delivered at the commit point."""
        self._anchor(anchor_t)
        self._mouse.click(Button.left, 1)

    def press(self, anchor_t: float | None = None) -> None:
        """Hold the left button down. Moving from here drags.

        Anchored like a click so a drag starts where it was aimed; the drag
        itself then tracks the hand normally from that point.
        """
        if not self.pressed:
            self._anchor(anchor_t)
            self._mouse.press(Button.left)
            self.pressed = True

    def release(self) -> None:
        """Let the left button go. A no-op if it isn't held, so it is safe to
        call on shutdown or from any error path."""
        if self.pressed:
            self._mouse.release(Button.left)
            self.pressed = False

    def scroll(self, steps: int) -> None:
        """Vertical wheel scroll; positive = up, negative = down."""
        if steps:
            self._mouse.scroll(0, steps)

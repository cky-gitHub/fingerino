"""Maps the tracked fingertip to a screen coordinate, smooths it with a
One Euro Filter, and drives the OS cursor via pynput.
"""

from __future__ import annotations

import math
import sys

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

    # Fallback for non-Windows: best effort via tkinter.
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

    def reset(self) -> None:
        """Drop filter history — call when the hand is lost so the cursor does
        not lurch when tracking resumes elsewhere."""
        self._fx.reset()
        self._fy.reset()

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
        return ix, iy

    def click(self) -> None:
        self._mouse.click(Button.left, 1)

    def scroll(self, steps: int) -> None:
        """Vertical wheel scroll; positive = up, negative = down."""
        if steps:
            self._mouse.scroll(0, steps)

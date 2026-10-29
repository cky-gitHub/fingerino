"""HUD rendering — clean and flat, no glow, no colour.

Neutral greys throughout, hairline strokes, state carried by brightness
rather than hue; the status dot is the only thing that stays coloured,
because it reports a live condition. Text is rendered with PIL for crisp
anti-aliasing. The raw skeleton and FPS live behind ``debug``.

Everything here is drawn *onto the camera frame* at the camera's native
resolution, which the HUD window then shrinks to its own size; :meth:`UIOverlay.s`
inflates design sizes by that ratio so the chrome holds a constant apparent
size. Design against roughly 480x270. The gesture guide that used to be drawn
here now lives in the Home window (qml/Home.qml).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import config

_HAND_CONNECTIONS = (
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12),
    (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (17, 18), (18, 19), (19, 20),
    (0, 17),
)
_PALM_POINTS = (0, 5, 9, 13, 17)
_SCROLL_POINTS = (8, 12)   # index + middle fingertips

# Sketch icons for the gesture tutorial page, keyed by the same icon id used
# for the per-gesture enabled/disabled state in main.py.
_GESTURE_ICON_FILES = {
    "thumb": "01-move-cursor.png",
    "point": "02-click.png",
    "point_hold": "03-drag.png",
    "two_finger": "04-scroll.png",
    "flat_down": "05-minimize.png",
    "flat_up": "06-restore.png",
    "flat_left": "07-switch-window.png",
    "shaka": "08-new-chat.png",
    "cross": "09-exit.png",
    "both_flat": "10-hold.png",
}



def _asset_root() -> Path:
    """Locate the bundled assets/ folder, in dev or a PyInstaller bundle.

    Mirrors hand_tracker._default_model_path()'s sys.frozen / _MEIPASS check
    -- packaging/fingerino.spec bundles assets/ under that same name.
    """
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", "")) / "assets"
    return Path(__file__).resolve().parent.parent / "assets"










def _bgr2rgb(c: tuple[int, int, int]) -> tuple[int, int, int]:
    return (c[2], c[1], c[0])


def _load_font(size: int,
               bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Inter, bundled in assets/fonts/, so the app looks the same on every
    machine instead of falling back to whatever system UI font is installed.
    Semibold (not heavy Bold) for emphasis -- reads cleaner at small sizes.
    """
    bundled = _asset_root() / "fonts" / ("Inter-SemiBold.ttf" if bold else "Inter-Regular.ttf")
    try:
        return ImageFont.truetype(str(bundled), size)
    except Exception:
        pass
    names = (
        ["segoeuisb.ttf", "segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"]
        if bold
        else ["segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"]
    )
    for name in names:
        for path in (f"C:/Windows/Fonts/{name}", name):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _rounded_rect(img, x1, y1, x2, y2, r, color, thickness=-1) -> None:
    r = int(min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    lt = cv2.LINE_AA
    if thickness < 0:
        cv2.rectangle(img, (x1 + r, y1), (x2 - r, y2), color, -1, lt)
        cv2.rectangle(img, (x1, y1 + r), (x2, y2 - r), color, -1, lt)
        for cx, cy, a in ((x1 + r, y1 + r, 180), (x2 - r, y1 + r, 270),
                          (x1 + r, y2 - r, 90), (x2 - r, y2 - r, 0)):
            cv2.ellipse(img, (cx, cy), (r, r), a, 0, 90, color, -1, lt)
    else:
        cv2.line(img, (x1 + r, y1), (x2 - r, y1), color, thickness, lt)
        cv2.line(img, (x1 + r, y2), (x2 - r, y2), color, thickness, lt)
        cv2.line(img, (x1, y1 + r), (x1, y2 - r), color, thickness, lt)
        cv2.line(img, (x2, y1 + r), (x2, y2 - r), color, thickness, lt)
        for cx, cy, a in ((x1 + r, y1 + r, 180), (x2 - r, y1 + r, 270),
                          (x1 + r, y2 - r, 90), (x2 - r, y2 - r, 0)):
            cv2.ellipse(img, (cx, cy), (r, r), a, 0, 90, color, thickness, lt)


def _blend_ring(frame, center, radius, color, alpha, thickness=1) -> None:
    x, y = int(center[0]), int(center[1])
    pad = radius + thickness + 1
    x0, y0 = max(0, x - pad), max(0, y - pad)
    x1, y1 = min(frame.shape[1], x + pad), min(frame.shape[0], y + pad)
    if x0 >= x1 or y0 >= y1:
        return
    roi = frame[y0:y1, x0:x1]
    ov = roi.copy()
    cv2.circle(ov, (x - x0, y - y0), radius, color, thickness, cv2.LINE_AA)
    cv2.addWeighted(ov, alpha, roi, 1.0 - alpha, 0, roi)










def _chevron(frame, cx, cy, size, up, color, thickness=2) -> None:
    dy = -size // 2 if up else size // 2
    pts = np.array([(cx - size, cy - dy), (cx, cy + dy), (cx + size, cy - dy)])
    cv2.polylines(frame, [pts], False, color, thickness, cv2.LINE_AA)




class UIOverlay:
    def __init__(self, ui_scale: float = 1.0) -> None:
        # Never shrink below the design-native size — only compensate for a
        # preview window smaller than the camera's native resolution.
        self._scale = max(1.0, ui_scale)
        self.f_status = _load_font(self.s(13), bold=True)
        self.f_mode = _load_font(self.s(12), bold=True)
        self.f_exit = _load_font(self.s(14), bold=True)
        self.f_toast = _load_font(self.s(12), bold=True)
        self.f_debug = _load_font(self.s(10))
        self._flashes: list[tuple[int, int, float]] = []
        self._toasts: list[tuple[str, float]] = []
        # queued PIL text draws and icon pastes for the single compositing pass
        self._texts: list[tuple] = []
        self._icons: list[tuple[Image.Image, int, int]] = []

    def s(self, v: float) -> int:
        """Scale a design-space size into frame-space.

        Chrome that overlays live video -- the status pill, cursor reticle,
        toasts -- uses this: it keeps a *constant apparent size* regardless
        of window size, which is what you want for a HUD element.
        """
        return max(1, round(v * self._scale))


    # -- surfaces ------------------------------------------------------------
    def _panel(self, frame, x1, y1, x2, y2, r=None) -> None:
        """Translucent panel: soft drop shadow, flat fill, hairline border."""
        r = self.s(7) if r is None else r
        off = self.s(2)
        ov = frame.copy()
        _rounded_rect(ov, x1 + off, y1 + off, x2 + off, y2 + off, r, (0, 0, 0), -1)
        cv2.addWeighted(ov, config.SHADOW_ALPHA, frame,
                        1.0 - config.SHADOW_ALPHA, 0, frame)

        ov = frame.copy()
        _rounded_rect(ov, x1, y1, x2, y2, r, config.COLOR_PANEL, -1)
        cv2.addWeighted(ov, config.PANEL_ALPHA, frame,
                        1.0 - config.PANEL_ALPHA, 0, frame)
        _rounded_rect(frame, x1, y1, x2, y2, r, config.COLOR_PANEL_BORDER, self.s(1))

    # -- transient feedback --------------------------------------------------
    def flash_click(self, pos_px: tuple[int, int]) -> None:
        self._flashes.append((int(pos_px[0]), int(pos_px[1]), time.time()))

    def toast(self, text: str) -> None:
        self._toasts.append((text, time.time()))

    # -- text / icon queues ---------------------------------------------------
    def _text(self, xy, s, font, fill, anchor="la", alpha=255) -> None:
        self._texts.append((xy, s, font, (*_bgr2rgb(fill), alpha), anchor))

    def _icon(self, img: Image.Image, x: int, y: int) -> None:
        """Queue a pre-scaled RGBA icon, top-left at (x, y), for the same
        single compositing pass as the queued text.
        """
        self._icons.append((img, x, y))

    # -- elements ------------------------------------------------------------
    def _draw_zone(self, frame, zone, tracking) -> None:
        """Corner brackets rather than a full outline — less visual noise."""
        x1, y1, x2, y2 = zone
        color = config.COLOR_STROKE_ACTIVE if tracking else config.COLOR_STROKE
        th = self.s(1)
        ln = self.s(14)
        for cx, cy, dx, dy in ((x1, y1, 1, 1), (x2, y1, -1, 1),
                               (x1, y2, 1, -1), (x2, y2, -1, -1)):
            cv2.line(frame, (cx, cy), (cx + dx * ln, cy), color, th, cv2.LINE_AA)
            cv2.line(frame, (cx, cy), (cx, cy + dy * ln), color, th, cv2.LINE_AA)

    def _draw_cursor(self, frame, pos, dragging=False, progress=0.0) -> None:
        """Crosshair reticle — reads as a precision pointer, not a blob.

        While the button is held the reticle takes the accent colour and its
        centre fills in, so a drag is never a silent state. Before that, the
        ring fills round like a clock to show the point arming into a drag —
        the same "hold this" language the exit gesture uses.
        """
        cx, cy = int(pos[0]), int(pos[1])
        r, gap, arm, th = self.s(9), self.s(3), self.s(5), self.s(1)
        color = config.COLOR_ACCENT if dragging else config.COLOR_CURSOR
        cv2.circle(frame, (cx, cy), r, color, th, cv2.LINE_AA)
        if progress > 0.0:
            cv2.ellipse(frame, (cx, cy), (r, r), -90, 0, 360 * min(progress, 1.0),
                        config.COLOR_ACCENT, self.s(2), cv2.LINE_AA)
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            cv2.line(frame, (cx + dx * (r + gap), cy + dy * (r + gap)),
                     (cx + dx * (r + gap + arm), cy + dy * (r + gap + arm)),
                     color, th, cv2.LINE_AA)
        cv2.circle(frame, (cx, cy), self.s(4) if dragging else self.s(1), color,
                   -1, cv2.LINE_AA)

    def _draw_flashes(self, frame) -> None:
        now = time.time()
        self._flashes = [f for f in self._flashes if now - f[2] < config.CLICK_FLASH_S]
        for x, y, t0 in self._flashes:
            p = (now - t0) / config.CLICK_FLASH_S
            radius = self.s(9) + int(p * self.s(13))
            _blend_ring(frame, (x, y), radius, config.COLOR_ACCENT,
                        max(0.0, (1.0 - p) * 0.9), thickness=self.s(1))

    def _palm_px(self, hand_px):
        xs = sum(hand_px[i][0] for i in _PALM_POINTS) / len(_PALM_POINTS)
        ys = sum(hand_px[i][1] for i in _PALM_POINTS) / len(_PALM_POINTS)
        return int(xs), int(ys)

    def _tips_px(self, hand_px):
        """Index/middle fingertip midpoint — mirrors the scroll anchor."""
        xs = sum(hand_px[i][0] for i in _SCROLL_POINTS) / len(_SCROLL_POINTS)
        ys = sum(hand_px[i][1] for i in _SCROLL_POINTS) / len(_SCROLL_POINTS)
        return int(xs), int(ys)

    def _draw_scroll(self, frame, center) -> None:
        cx, cy = center
        off, sz, th = self.s(14), self.s(7), self.s(2)
        _chevron(frame, cx, cy - off, sz, True, config.COLOR_ACCENT, th)
        _chevron(frame, cx, cy + off, sz, False, config.COLOR_ACCENT, th)
        cv2.circle(frame, (cx, cy), self.s(2), config.COLOR_ACCENT, -1, cv2.LINE_AA)

    def _draw_flat(self, frame, center) -> None:
        cx, cy = center
        step, sz, th = self.s(9), self.s(8), self.s(2)
        for i in range(3):
            _chevron(frame, cx, cy - self.s(8) + i * step, sz, False,
                     config.COLOR_ACCENT, th)



    def _draw_status(self, frame, tracking, mode_label, paused=False) -> None:
        """One compact bar: state dot + label, then the live mode after a rule.

        Paused outranks both: the hand is still tracked and still has a
        posture, but none of it does anything, so the pill says so and drops
        the mode rather than reading "Tracking · Scroll" while scrolling
        nothing.
        """
        pad, gap = self.s(9), self.s(7)
        h = self.s(26)
        x1, y1 = self.s(10), self.s(10)
        dot_r = self.s(4)

        live = tracking and not paused
        label = "Paused" if paused else ("Tracking" if tracking else "No hand")
        w = pad + dot_r * 2 + gap + int(self.f_status.getlength(label)) + pad
        show_mode = bool(live and mode_label)
        if show_mode:
            mode_w = int(self.f_mode.getlength(mode_label))
            w += self.s(1) + gap + mode_w + pad - self.s(2)

        x2, y2 = x1 + w, y1 + h
        self._panel(frame, x1, y1, x2, y2, r=h // 2)

        cy = y1 + h // 2
        dc = (x1 + pad + dot_r, cy)
        cv2.circle(frame, dc, dot_r,
                   config.COLOR_OK if live else config.COLOR_IDLE, -1, cv2.LINE_AA)
        if live:  # soft halo so the live state reads at a glance
            _blend_ring(frame, dc, dot_r + self.s(3), config.COLOR_OK, 0.45, self.s(1))

        tx = dc[0] + dot_r + gap
        self._text((tx, cy - 1), label, self.f_status, config.COLOR_TEXT, anchor="lm")

        if show_mode:
            rule_x = tx + int(self.f_status.getlength(label)) + gap
            cv2.line(frame, (rule_x, y1 + self.s(7)), (rule_x, y2 - self.s(7)),
                     config.COLOR_DIVIDER, self.s(1), cv2.LINE_AA)
            active = mode_label != "Move"
            self._text((rule_x + gap, cy - 1), mode_label, self.f_mode,
                       config.COLOR_ACCENT if active else config.COLOR_TEXT_DIM,
                       anchor="lm")




    # -- gesture guide panel ---------------------------------------------------
    # Rendered as its own standalone image -- NOT drawn on top of the camera
    # frame -- so it isn't limited to the tiny preview window's resolution.
    # main.py composites this directly below the camera preview and grows the
    # actual OS window to fit both, so the panel is always exactly win_w wide
    # and the two stack edge to edge.
    #
    # The layout follows the vocabulary Windows 11 settings pages use: one
    # column of rows, grouped under section headers, each row an icon, a
    # label and a description with its control on the right. Exactly one
    # container level -- the row -- separated from its neighbours by a gap
    # rather than by borders. Every size is a design unit from config scaled
    # by fs(), so the whole thing is proportional to the screen.










    def _draw_hold_prompt(self, frame, text, progress) -> None:
        """Centred "keep holding" card with a filling bar underneath.

        Shared by the two gestures that must be held to fire — the exit X and
        the both-palms pause — so they read as the same kind of commitment.
        """
        h, w = frame.shape[:2]
        bw = max(self.s(180), int(self.f_exit.getlength(text)) + self.s(48))
        bh = self.s(56)
        x1, x2 = w // 2 - bw // 2, w // 2 + bw // 2
        y1 = int(h * 0.36)
        y2 = y1 + bh
        self._panel(frame, x1, y1, x2, y2, r=self.s(9))
        self._text((w // 2, y1 + self.s(18)), text, self.f_exit,
                   config.COLOR_TEXT, anchor="mm")
        bx1, bx2 = x1 + self.s(16), x2 - self.s(16)
        by = y2 - self.s(16)
        track_h, r = self.s(5), self.s(3)
        _rounded_rect(frame, bx1, by, bx2, by + track_h, r,
                      config.COLOR_DIVIDER, -1)
        fill_x = int(bx1 + (bx2 - bx1) * max(0.0, min(1.0, progress)))
        if fill_x > bx1 + 2:
            _rounded_rect(frame, bx1, by, fill_x, by + track_h, r,
                          config.COLOR_ACCENT, -1)

    def _draw_toasts(self, frame) -> None:
        now = time.time()
        self._toasts = [t for t in self._toasts if now - t[1] < config.TOAST_S]
        w = frame.shape[1]
        bh, gap, top = self.s(28), self.s(6), self.s(46)
        for i, (text, t0) in enumerate(self._toasts):
            p = (now - t0) / config.TOAST_S
            alpha = int(max(0.0, min(1.0, (1.0 - p) * 1.4)) * 255)
            bw = int(self.f_toast.getlength(text)) + self.s(28)
            x1 = w // 2 - bw // 2
            y1 = top + i * (bh + gap)
            self._panel(frame, x1, y1, x1 + bw, y1 + bh, r=bh // 2)
            self._text((w // 2, y1 + bh // 2 - 1), text, self.f_toast,
                       config.COLOR_TEXT, anchor="mm", alpha=alpha)

    def _draw_skeleton(self, frame, hands_px) -> None:
        th, r = self.s(1), self.s(2)
        for hand in hands_px:
            for a, b in _HAND_CONNECTIONS:
                cv2.line(frame, hand[a], hand[b], config.COLOR_STROKE, th, cv2.LINE_AA)
            for p in hand:
                cv2.circle(frame, p, r, config.COLOR_STROKE_ACTIVE, -1, cv2.LINE_AA)

    def _build_overlay(self, size) -> Image.Image:
        """Drain the queued icon pastes and text draws into an RGBA layer."""
        layer = Image.new("RGBA", size, (0, 0, 0, 0))
        for img, x, y in self._icons:
            layer.paste(img, (x, y), img)
        self._icons.clear()
        d = ImageDraw.Draw(layer)
        for xy, s, font, fill, anchor in self._texts:
            d.text(xy, s, font=font, fill=fill, anchor=anchor)
        self._texts.clear()
        return layer

    def _composite(self, frame, layer: Image.Image) -> np.ndarray:
        """Alpha-blend a prepared RGBA layer onto a BGR frame."""
        base = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)).convert("RGBA")
        out = Image.alpha_composite(base, layer).convert("RGB")
        return cv2.cvtColor(np.asarray(out), cv2.COLOR_RGB2BGR)

    def _flush_overlay(self, frame) -> np.ndarray:
        """Single PIL compositing pass: queued icon pastes, then queued text
        drawn on top, both alpha-blended onto the frame in one round-trip.
        """
        h, w = frame.shape[:2]
        return self._composite(frame, self._build_overlay((w, h)))

    # -- public --------------------------------------------------------------
    def draw(self, frame, *, tracking, mode="none", mode_label="", cursor_px=None,
             zone_px, hands_px=None, exit_progress=0.0, dragging=False,
             drag_progress=0.0, debug=False, fps=0.0,
             paused=False, hold_progress=0.0) -> np.ndarray:
        self._draw_zone(frame, zone_px, tracking)

        if debug and hands_px:
            self._draw_skeleton(frame, hands_px)

        # None of the per-mode chrome is drawn while paused: a reticle that
        # doesn't move the cursor, or scroll chevrons that scroll nothing,
        # would say the opposite of what the pill says.
        if not paused:
            if mode == "move" and tracking and cursor_px is not None:
                self._draw_cursor(frame, cursor_px, dragging, drag_progress)
            elif mode == "scroll" and hands_px:
                self._draw_scroll(frame, self._tips_px(hands_px[0]))
            elif mode == "flat" and hands_px:
                self._draw_flat(frame, self._palm_px(hands_px[0]))

        self._draw_flashes(frame)
        self._draw_status(frame, tracking, mode_label, paused)
        if exit_progress > 0.0:
            self._draw_hold_prompt(frame, "Hold to exit", exit_progress)
        elif hold_progress > 0.0:
            self._draw_hold_prompt(
                frame, "Hold to resume" if paused else "Hold to pause",
                hold_progress)
        self._draw_toasts(frame)

        if debug:
            self._text((self.s(10), frame.shape[0] - self.s(10)),
                       f"{fps:4.1f} fps   {mode}", self.f_debug,
                       config.COLOR_TEXT_FAINT, anchor="ld")

        return self._flush_overlay(frame)

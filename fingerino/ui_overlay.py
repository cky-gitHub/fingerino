"""HUD rendering — clean and flat, styled to read like a professional tool.

No glow, no saturated colour: neutral greys, hairline strokes, one restrained
steel-blue accent used only to signal an active state. Text is rendered with
PIL for crisp anti-aliasing. The raw skeleton and FPS live behind ``debug``.
"""

from __future__ import annotations

import time

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


def _bgr2rgb(c: tuple[int, int, int]) -> tuple[int, int, int]:
    return (c[2], c[1], c[0])


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
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


def _panel(frame, x1, y1, x2, y2, r=12) -> None:
    """Flat translucent panel with a hairline border."""
    ov = frame.copy()
    _rounded_rect(ov, x1, y1, x2, y2, r, config.COLOR_PANEL, -1)
    cv2.addWeighted(ov, config.PANEL_ALPHA, frame, 1.0 - config.PANEL_ALPHA, 0, frame)
    _rounded_rect(frame, x1, y1, x2, y2, r, config.COLOR_PANEL_BORDER, 1)


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
    def __init__(self) -> None:
        self.f_label = _load_font(19, bold=True)
        self.f_mode = _load_font(16, bold=True)
        self.f_hint = _load_font(14)
        self.f_exit = _load_font(18, bold=True)
        self.f_toast = _load_font(18, bold=True)
        self.f_debug = _load_font(15)
        self._flashes: list[tuple[int, int, float]] = []
        self._toasts: list[tuple[str, float]] = []
        # queued PIL text draws for the single compositing pass
        self._texts: list[tuple] = []

    # -- transient feedback --------------------------------------------------
    def flash_click(self, pos_px: tuple[int, int]) -> None:
        self._flashes.append((int(pos_px[0]), int(pos_px[1]), time.time()))

    def toast(self, text: str) -> None:
        self._toasts.append((text, time.time()))

    # -- text queue ----------------------------------------------------------
    def _text(self, xy, s, font, fill, anchor="la", alpha=255) -> None:
        self._texts.append((xy, s, font, (*_bgr2rgb(fill), alpha), anchor))

    # -- elements ------------------------------------------------------------
    def _draw_zone(self, frame, zone, tracking) -> None:
        x1, y1, x2, y2 = zone
        color = config.COLOR_STROKE_ACTIVE if tracking else config.COLOR_STROKE
        _rounded_rect(frame, x1, y1, x2, y2, 18, color, 1)

    def _draw_cursor(self, frame, pos) -> None:
        c = (int(pos[0]), int(pos[1]))
        cv2.circle(frame, c, 10, config.COLOR_CURSOR, 1, cv2.LINE_AA)
        cv2.circle(frame, c, 2, config.COLOR_CURSOR, -1, cv2.LINE_AA)

    def _draw_flashes(self, frame) -> None:
        now = time.time()
        self._flashes = [f for f in self._flashes if now - f[2] < config.CLICK_FLASH_S]
        for x, y, t0 in self._flashes:
            p = (now - t0) / config.CLICK_FLASH_S
            _blend_ring(frame, (x, y), int(10 + p * 14), config.COLOR_CURSOR,
                        max(0.0, (1.0 - p) * 0.85), thickness=1)

    def _palm_px(self, hand_px):
        xs = sum(hand_px[i][0] for i in _PALM_POINTS) / len(_PALM_POINTS)
        ys = sum(hand_px[i][1] for i in _PALM_POINTS) / len(_PALM_POINTS)
        return int(xs), int(ys)

    def _draw_scroll(self, frame, center) -> None:
        cx, cy = center
        _chevron(frame, cx, cy - 16, 9, True, config.COLOR_ACCENT)
        _chevron(frame, cx, cy + 16, 9, False, config.COLOR_ACCENT)
        cv2.circle(frame, (cx, cy), 2, config.COLOR_ACCENT, -1, cv2.LINE_AA)

    def _draw_flat(self, frame, center) -> None:
        cx, cy = center
        for i in range(3):
            _chevron(frame, cx, cy - 10 + i * 11, 10, False, config.COLOR_ACCENT)

    def _draw_status(self, frame, tracking, mode_label) -> None:
        # Status pill.
        x1, y1, h = 20, 20, 42
        sw = 150
        _panel(frame, x1, y1, x1 + sw, y1 + h, r=h // 2)
        dot = config.COLOR_OK if tracking else config.COLOR_IDLE
        dc = (x1 + 24, y1 + h // 2)
        cv2.circle(frame, dc, 6, dot, -1, cv2.LINE_AA)
        self._text((x1 + 42, y1 + h // 2 - 1), "Tracking" if tracking else "No hand",
                   self.f_label, config.COLOR_TEXT, anchor="lm")

        # Mode pill (only while tracking).
        if tracking and mode_label:
            mx1 = x1 + sw + 10
            mw = 150
            _panel(frame, mx1, y1, mx1 + mw, y1 + h, r=h // 2)
            active = mode_label not in ("Move",)
            mc = config.COLOR_ACCENT if active else config.COLOR_IDLE
            cv2.circle(frame, (mx1 + 22, y1 + h // 2), 5, mc, -1, cv2.LINE_AA)
            self._text((mx1 + 40, y1 + h // 2 - 1), mode_label, self.f_mode,
                       config.COLOR_TEXT if active else config.COLOR_TEXT_DIM,
                       anchor="lm")

    def _draw_hint(self, frame) -> None:
        h, w = frame.shape[:2]
        y2 = h - 18
        y1 = y2 - 40
        _panel(frame, 20, y1, w - 20, y2, r=12)
        self._text((w // 2, (y1 + y2) // 2 - 1), config.HINT_TEXT, self.f_hint,
                   config.COLOR_TEXT_DIM, anchor="mm")

    def _draw_exit(self, frame, progress) -> None:
        h, w = frame.shape[:2]
        bw, bh = 320, 82
        x1, x2 = w // 2 - bw // 2, w // 2 + bw // 2
        y1 = int(h * 0.34)
        y2 = y1 + bh
        _panel(frame, x1, y1, x2, y2, r=14)
        self._text((w // 2, y1 + 26), "Hold to exit", self.f_exit,
                   config.COLOR_TEXT, anchor="mm")
        # progress track + fill
        bx1, bx2 = x1 + 24, x2 - 24
        by = y2 - 24
        _rounded_rect(frame, bx1, by, bx2, by + 8, 4, config.COLOR_PANEL_BORDER, -1)
        fill_x = int(bx1 + (bx2 - bx1) * max(0.0, min(1.0, progress)))
        if fill_x > bx1 + 2:
            _rounded_rect(frame, bx1, by, fill_x, by + 8, 4, config.COLOR_ACCENT, -1)

    def _draw_toasts(self, frame) -> None:
        now = time.time()
        self._toasts = [t for t in self._toasts if now - t[1] < config.TOAST_S]
        w = frame.shape[1]
        for i, (text, t0) in enumerate(self._toasts):
            p = (now - t0) / config.TOAST_S
            alpha = int(max(0.0, min(1.0, (1.0 - p) * 1.4)) * 255)
            bw, bh = 220, 44
            x1 = w // 2 - bw // 2
            y1 = 80 + i * (bh + 8)
            _panel(frame, x1, y1, x1 + bw, y1 + bh, r=bh // 2)
            self._text((w // 2, y1 + bh // 2 - 1), text, self.f_toast,
                       config.COLOR_TEXT, anchor="mm", alpha=alpha)

    def _draw_skeleton(self, frame, hands_px) -> None:
        for hand in hands_px:
            for a, b in _HAND_CONNECTIONS:
                cv2.line(frame, hand[a], hand[b], config.COLOR_STROKE, 1, cv2.LINE_AA)
            for p in hand:
                cv2.circle(frame, p, 2, config.COLOR_STROKE_ACTIVE, -1, cv2.LINE_AA)

    def _flush_text(self, frame) -> np.ndarray:
        base = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)).convert("RGBA")
        layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        for xy, s, font, fill, anchor in self._texts:
            d.text(xy, s, font=font, fill=fill, anchor=anchor)
        self._texts.clear()
        out = Image.alpha_composite(base, layer).convert("RGB")
        return cv2.cvtColor(np.asarray(out), cv2.COLOR_RGB2BGR)

    # -- public --------------------------------------------------------------
    def draw(self, frame, *, tracking, mode="none", mode_label="", cursor_px=None,
             zone_px, hands_px=None, exit_progress=0.0, debug=False,
             fps=0.0) -> np.ndarray:
        self._draw_zone(frame, zone_px, tracking)

        if debug and hands_px:
            self._draw_skeleton(frame, hands_px)

        if mode == "move" and tracking and cursor_px is not None:
            self._draw_cursor(frame, cursor_px)
        elif mode == "scroll" and hands_px:
            self._draw_scroll(frame, self._palm_px(hands_px[0]))
        elif mode == "flat" and hands_px:
            self._draw_flat(frame, self._palm_px(hands_px[0]))

        self._draw_flashes(frame)

        self._draw_status(frame, tracking, mode_label)
        self._draw_hint(frame)
        if exit_progress > 0.0:
            self._draw_exit(frame, exit_progress)
        self._draw_toasts(frame)

        if debug:
            self._text((frame.shape[1] - 20, 76), f"FPS {fps:4.1f}", self.f_debug,
                       config.COLOR_TEXT_DIM, anchor="ra")
            self._text((frame.shape[1] - 20, 98), f"mode {mode}", self.f_debug,
                       config.COLOR_TEXT_DIM, anchor="ra")

        return self._flush_text(frame)

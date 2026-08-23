"""HUD rendering — clean and flat, styled to read like a professional tool.

No glow, no saturated colour: neutral greys, hairline strokes, one restrained
accent used only to signal an active state. Text is rendered with PIL for
crisp anti-aliasing. The raw skeleton and FPS live behind ``debug``.

Sizes are written in *design space* and converted by :meth:`UIOverlay.s`.
The frame is rendered at the camera's native resolution and then shrunk by
OpenCV into a much smaller preview window, so design space is defined as the
on-screen pixel grid: a design size of 13 lands as ~13 real pixels on screen
regardless of camera resolution. Design the layout against roughly 480x270.
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
_SCROLL_POINTS = (8, 12)   # index + middle fingertips


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


def _chevron_lr(frame, cx, cy, size, left, color, thickness=2) -> None:
    dx = -size // 2 if left else size // 2
    pts = np.array([(cx - dx, cy - size), (cx + dx, cy), (cx - dx, cy + size)])
    cv2.polylines(frame, [pts], False, color, thickness, cv2.LINE_AA)


class UIOverlay:
    def __init__(self, ui_scale: float = 1.0) -> None:
        # Never shrink below the design-native size — only compensate for a
        # preview window smaller than the camera's native resolution.
        self._scale = max(1.0, ui_scale)
        self.f_status = _load_font(self.s(13), bold=True)
        self.f_mode = _load_font(self.s(12), bold=True)
        self.f_head = _load_font(self.s(10), bold=True)
        self.f_row = _load_font(self.s(11))
        self.f_row_b = _load_font(self.s(11), bold=True)
        self.f_key = _load_font(self.s(9), bold=True)
        self.f_exit = _load_font(self.s(14), bold=True)
        self.f_toast = _load_font(self.s(12), bold=True)
        self.f_debug = _load_font(self.s(10))
        self._flashes: list[tuple[int, int, float]] = []
        self._toasts: list[tuple[str, float]] = []
        # queued PIL text draws for the single compositing pass
        self._texts: list[tuple] = []

    def s(self, v: float) -> int:
        """Scale a design-space size into frame-space."""
        return max(1, int(round(v * self._scale)))

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

    def _keycap(self, frame, x, y, label, font) -> int:
        """Small key badge (e.g. Tab). Returns its width."""
        pad = self.s(4)
        h = self.s(14)
        w = int(font.getlength(label)) + pad * 2
        _rounded_rect(frame, x, y, x + w, y + h, self.s(3),
                      config.COLOR_DIVIDER, -1)
        _rounded_rect(frame, x, y, x + w, y + h, self.s(3),
                      config.COLOR_PANEL_BORDER, self.s(1))
        self._text((x + w // 2, y + h // 2 - 1), label, font,
                   config.COLOR_TEXT_DIM, anchor="mm")
        return w

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

    def _draw_status(self, frame, tracking, mode_label) -> None:
        """One compact bar: state dot + label, then the live mode after a rule."""
        pad, gap = self.s(9), self.s(7)
        h = self.s(26)
        x1, y1 = self.s(10), self.s(10)
        dot_r = self.s(4)

        label = "Tracking" if tracking else "No hand"
        w = pad + dot_r * 2 + gap + int(self.f_status.getlength(label)) + pad
        show_mode = bool(tracking and mode_label)
        if show_mode:
            mode_w = int(self.f_mode.getlength(mode_label))
            w += self.s(1) + gap + mode_w + pad - self.s(2)

        x2, y2 = x1 + w, y1 + h
        self._panel(frame, x1, y1, x2, y2, r=h // 2)

        cy = y1 + h // 2
        dc = (x1 + pad + dot_r, cy)
        cv2.circle(frame, dc, dot_r,
                   config.COLOR_OK if tracking else config.COLOR_IDLE, -1, cv2.LINE_AA)
        if tracking:  # soft halo so the live state reads at a glance
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

    # -- side menu geometry --------------------------------------------------
    # Drawing and hit-testing share these so the clickable area can never
    # drift away from what's painted.
    def _tab_rect(self, w: int, h: int) -> tuple[int, int, int, int]:
        pad = self.s(10)
        tab_w, tab_h = self.s(16), self.s(52)
        x2, y1 = w - pad, h // 2 - tab_h // 2
        return x2 - tab_w, y1, x2, y1 + tab_h

    def _panel_rect(self, w: int, h: int) -> tuple[int, int, int, int, int]:
        pad = self.s(10)
        head_h = self.s(24)
        panel_h = min(head_h + self.s(19) * len(config.GESTURE_LEGEND)
                      + self.s(22) + self.s(6), h - pad * 2)
        x2 = w - pad
        x1 = x2 - self.s(186)
        y1 = max(pad, (h - panel_h) // 2)
        return x1, y1, x2, y1 + panel_h, head_h

    def menu_toggle_rect(self, w: int, h: int, open_: bool) -> tuple[int, int, int, int]:
        """Clickable rect (frame coords) that toggles the menu.

        Padded outward: the collapsed tab is only ~16 design px wide, which is
        a fiddly target once the frame is scaled down into a small window.
        """
        if not open_:
            x1, y1, x2, y2 = self._tab_rect(w, h)
        else:
            px1, py1, px2, py2, head_h = self._panel_rect(w, h)
            x1, y1, x2, y2 = px1, py1, px2, py1 + head_h  # header row
        g = self.s(6)
        return x1 - g, y1 - g, x2 + g, y2 + g

    def _draw_side_menu(self, frame, open_: bool) -> None:
        """Collapsible gesture legend docked to the right edge. Tab toggles it."""
        h, w = frame.shape[:2]

        if not open_:
            x1, y1, x2, y2 = self._tab_rect(w, h)
            self._panel(frame, x1, y1, x2, y2, r=self.s(5))
            _chevron_lr(frame, (x1 + x2) // 2, (y1 + y2) // 2, self.s(4), True,
                        config.COLOR_TEXT_DIM, self.s(1))
            return

        legend = config.GESTURE_LEGEND
        row_h = self.s(19)
        x1, y1, x2, y2, head_h = self._panel_rect(w, h)
        self._panel(frame, x1, y1, x2, y2, r=self.s(8))

        ix1, ix2 = x1 + self.s(11), x2 - self.s(11)

        # Header + collapse affordance.
        self._text((ix1, y1 + head_h // 2 - 1), "GESTURES", self.f_head,
                   config.COLOR_TEXT_FAINT, anchor="lm")
        _chevron_lr(frame, ix2 - self.s(3), y1 + head_h // 2, self.s(4), False,
                    config.COLOR_TEXT_FAINT, self.s(1))
        cv2.line(frame, (ix1, y1 + head_h), (ix2, y1 + head_h),
                 config.COLOR_DIVIDER, self.s(1), cv2.LINE_AA)

        # Rows: gesture on the left, resulting action right-aligned.
        ry = y1 + head_h
        for gesture, action in legend:
            cy = ry + row_h // 2 - 1
            self._text((ix1, cy), gesture, self.f_row_b,
                       config.COLOR_TEXT, anchor="lm")
            self._text((ix2, cy), action, self.f_row,
                       config.COLOR_TEXT_DIM, anchor="rm")
            ry += row_h

        # Footer: how to collapse it again.
        cv2.line(frame, (ix1, ry + self.s(2)), (ix2, ry + self.s(2)),
                 config.COLOR_DIVIDER, self.s(1), cv2.LINE_AA)
        kw = self._keycap(frame, ix1, ry + self.s(7), "Tab", self.f_key)
        self._text((ix1 + kw + self.s(6), ry + self.s(7) + self.s(7)), "hide",
                   self.f_row, config.COLOR_TEXT_FAINT, anchor="lm")

    def _draw_exit(self, frame, progress) -> None:
        h, w = frame.shape[:2]
        bw, bh = self.s(180), self.s(56)
        x1, x2 = w // 2 - bw // 2, w // 2 + bw // 2
        y1 = int(h * 0.36)
        y2 = y1 + bh
        self._panel(frame, x1, y1, x2, y2, r=self.s(9))
        self._text((w // 2, y1 + self.s(18)), "Hold to exit", self.f_exit,
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
             zone_px, hands_px=None, exit_progress=0.0, dragging=False,
             drag_progress=0.0, debug=False, fps=0.0,
             menu_open=False) -> np.ndarray:
        self._draw_zone(frame, zone_px, tracking)

        if debug and hands_px:
            self._draw_skeleton(frame, hands_px)

        if mode == "move" and tracking and cursor_px is not None:
            self._draw_cursor(frame, cursor_px, dragging, drag_progress)
        elif mode == "scroll" and hands_px:
            self._draw_scroll(frame, self._tips_px(hands_px[0]))
        elif mode == "flat" and hands_px:
            self._draw_flat(frame, self._palm_px(hands_px[0]))

        self._draw_flashes(frame)

        self._draw_status(frame, tracking, mode_label)
        self._draw_side_menu(frame, menu_open)
        if exit_progress > 0.0:
            self._draw_exit(frame, exit_progress)
        self._draw_toasts(frame)

        if debug:
            self._text((self.s(10), frame.shape[0] - self.s(10)),
                       f"{fps:4.1f} fps   {mode}", self.f_debug,
                       config.COLOR_TEXT_FAINT, anchor="ld")

        return self._flush_text(frame)

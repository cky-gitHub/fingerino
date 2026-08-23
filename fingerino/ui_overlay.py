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
}


def _assets_dir() -> Path:
    """Locate assets/tutorial-gestures/, in dev or a PyInstaller bundle.

    Mirrors hand_tracker._default_model_path()'s sys.frozen / _MEIPASS check
    -- packaging/fingerino.spec bundles the folder at "assets/tutorial-gestures".
    """
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", "")) / "assets" / "tutorial-gestures"
    return Path(__file__).resolve().parent.parent / "assets" / "tutorial-gestures"


def _prep_icon(im: Image.Image, box: int) -> Image.Image:
    """Crop to the drawn content, re-pad it square, then resize to box x box.

    The source PNGs are 1024x1024 with wildly different amounts of empty
    margin (a tall pointing finger vs. two wide crossed arms) -- without this
    they'd read at inconsistent sizes next to each other in the row grid.
    """
    bbox = im.getbbox()
    if bbox:
        im = im.crop(bbox)
    w, h = im.size
    side = max(w, h)
    pad = max(1, side // 10)
    canvas = Image.new("RGBA", (side + pad * 2, side + pad * 2), (0, 0, 0, 0))
    canvas.paste(im, ((canvas.width - w) // 2, (canvas.height - h) // 2), im)
    return canvas.resize((box, box), Image.LANCZOS)


def _flat_tint(im: Image.Image, rgb: tuple[int, int, int]) -> Image.Image:
    """Flatten to a single-colour silhouette, keeping the source alpha shape.

    Used for the disabled-row icon -- same "everything faint" language as
    the dimmed title text next to it.
    """
    solid = Image.new("RGBA", im.size, (*rgb, 255))
    solid.putalpha(im.split()[3])
    return solid


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
        self.f_title = _load_font(self.s(15), bold=True)
        self.f_row = _load_font(self.s(11))
        self.f_row_b = _load_font(self.s(16), bold=True)  # gesture-guide row titles
        self.f_key = _load_font(self.s(9), bold=True)
        self.f_exit = _load_font(self.s(14), bold=True)
        self.f_toast = _load_font(self.s(12), bold=True)
        self.f_debug = _load_font(self.s(10))
        self._flashes: list[tuple[int, int, float]] = []
        self._toasts: list[tuple[str, float]] = []
        # queued PIL text draws and icon pastes for the single compositing pass
        self._texts: list[tuple] = []
        self._icons: list[tuple[Image.Image, int, int]] = []

        icon_box = self.s(self._ICON_BOX)
        assets = _assets_dir()
        self._gesture_icons: dict[str, tuple[Image.Image, Image.Image]] = {}
        for icon_id, fname in _GESTURE_ICON_FILES.items():
            raw = Image.open(assets / fname).convert("RGBA")
            normal = _prep_icon(raw, icon_box)
            muted = _flat_tint(normal, _bgr2rgb(config.COLOR_TEXT_FAINT))
            self._gesture_icons[icon_id] = (normal, muted)

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

    def _card(self, frame, x1, y1, x2, y2, r) -> None:
        """Solid rounded tile for one gesture row.

        Deliberately not _panel(): that does a soft drop shadow via a
        full-frame copy + blend, cheap once per HUD but not nine times a
        frame for a small tile. This is flat fill + hairline border only,
        which cv2 already scopes to the rect -- no full-frame work at all.
        """
        _rounded_rect(frame, x1, y1, x2, y2, r, config.COLOR_CARD, -1)
        _rounded_rect(frame, x1, y1, x2, y2, r, config.COLOR_PANEL_BORDER, self.s(1))

    def _draw_toggle(self, frame, cx, cy, on: bool) -> None:
        """Small iOS-style switch: filled+accent track with the knob at the
        right when on, hollow dim track with the knob at the left when off.
        """
        tw, th_ = self.s(20), self.s(11)
        x1, y1 = cx - tw // 2, cy - th_ // 2
        x2, y2 = cx + tw // 2, cy + th_ // 2
        if on:
            _rounded_rect(frame, x1, y1, x2, y2, th_ // 2, config.COLOR_ACCENT, -1)
        else:
            _rounded_rect(frame, x1, y1, x2, y2, th_ // 2, config.COLOR_DIVIDER, -1)
            _rounded_rect(frame, x1, y1, x2, y2, th_ // 2, config.COLOR_PANEL_BORDER,
                          self.s(1))
        knob_r = self.s(4)
        knob_x = x2 - knob_r - self.s(1) if on else x1 + knob_r + self.s(1)
        cv2.circle(frame, (knob_x, cy), knob_r, config.COLOR_TEXT, -1, cv2.LINE_AA)

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

    def _page_rect(self, w: int, h: int) -> tuple[int, int, int, int]:
        m = self.s(12)
        return m, m, w - m, h - m

    def _page_close_rect(self, w: int, h: int) -> tuple[int, int, int, int]:
        """Header close-control hit box, shared by drawing and hit-testing."""
        x1, y1, x2, _ = self._page_rect(w, h)
        pad = self.s(14)
        cy = y1 + pad
        kx = x2 - pad - self.s(64)
        return kx, cy - self.s(9), x2 - pad, cy + self.s(9)

    def menu_toggle_rect(self, w: int, h: int, open_: bool) -> tuple[int, int, int, int]:
        """Clickable rect (frame coords) that toggles the gesture guide.

        Padded outward: the collapsed tab is only ~16 design px wide, which is
        a fiddly target once the frame is scaled down into a small window.
        """
        x1, y1, x2, y2 = (self._tab_rect(w, h) if not open_
                          else self._page_close_rect(w, h))
        g = self.s(6)
        return x1 - g, y1 - g, x2 + g, y2 + g

    # Grid constants shared between drawing and hit-testing, fixed design
    # units per the note in _gesture_row_rect below.
    _GRID_COLS = 2
    _GRID_PAD = 14
    _GRID_HEAD_GAP = 14
    _GRID_TOP_GAP = 6
    _ROW_H = 38
    _COL_W = 205
    _ICON_BOX = 30  # gesture sketch, square, design units

    def _gesture_row_rect(self, w: int, h: int, index: int) -> tuple[int, int, int, int]:
        """Frame-coords rect for gesture-tutorial row ``index``, shared by
        drawing and hit-testing so a click always lands on what's drawn.
        """
        x1, y1, _, _ = self._page_rect(w, h)
        ix1 = x1 + self.s(self._GRID_PAD)
        head_cy = y1 + self.s(self._GRID_PAD)
        rule_y = head_cy + self.s(self._GRID_HEAD_GAP)
        grid_y1 = rule_y + self.s(self._GRID_TOP_GAP)
        row_h, col_w = self.s(self._ROW_H), self.s(self._COL_W)
        col, row = index % self._GRID_COLS, index // self._GRID_COLS
        rx, ry = ix1 + col * col_w, grid_y1 + row * row_h
        return rx, ry, rx + col_w, ry + row_h

    def gesture_row_rects(self, w: int, h: int) -> list[tuple[int, int, int, int]]:
        """All gesture-tutorial row rects, in config.GESTURE_TUTORIAL order."""
        return [self._gesture_row_rect(w, h, i)
                for i in range(len(config.GESTURE_TUTORIAL))]

    def _draw_side_menu(self, frame, open_: bool, enabled=None) -> None:
        """Collapsed: a small tab docked to the right edge. Open: the
        full-page gesture guide. Tab (or a click) toggles it.
        """
        if not open_:
            h, w = frame.shape[:2]
            x1, y1, x2, y2 = self._tab_rect(w, h)
            self._panel(frame, x1, y1, x2, y2, r=self.s(5))
            _chevron_lr(frame, (x1 + x2) // 2, (y1 + y2) // 2, self.s(4), True,
                        config.COLOR_TEXT_DIM, self.s(1))
            return
        self._draw_tutorial_page(frame, enabled)

    def _draw_tutorial_page(self, frame, enabled) -> None:
        """Full-page gesture guide: a rounded card per gesture, the sketch
        on the left and one large title on the right -- sized to actually
        read on a small preview window, not a legend squeezed into a strip.

        Each card also carries a toggle switch: click a row to stop that
        gesture from being recognised, without needing a separate settings
        screen.
        """
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = self._page_rect(w, h)
        self._panel(frame, x1, y1, x2, y2, r=self.s(10))

        pad = self.s(14)
        ix1, ix2 = x1 + pad, x2 - pad
        head_cy = y1 + pad

        self._text((ix1, head_cy), "GESTURES", self.f_title, config.COLOR_TEXT,
                   anchor="lm")
        kx1, ky1, kx2, ky2 = self._page_close_rect(w, h)
        kw = self._keycap(frame, kx1, ky1, "Tab", self.f_key)
        self._text((kx1 + kw + self.s(6), (ky1 + ky2) // 2 - 1), "close",
                   self.f_row, config.COLOR_TEXT_FAINT, anchor="lm")

        rule_y = head_cy + self.s(self._GRID_HEAD_GAP)
        cv2.line(frame, (ix1, rule_y), (ix2, rule_y), config.COLOR_DIVIDER,
                 self.s(1), cv2.LINE_AA)

        gap = self.s(2)  # gutter between adjacent cards
        for i, (icon, title) in enumerate(config.GESTURE_TUTORIAL):
            rx, ry, rx2, ry2 = self._gesture_row_rect(w, h, i)
            on = enabled is None or enabled.get(icon, True)
            row_h = ry2 - ry

            self._card(frame, rx + gap, ry + gap, rx2 - gap, ry2 - gap, self.s(8))

            icon_img = self._gesture_icons[icon][0 if on else 1]
            icon_cy = ry + row_h // 2
            icon_x = rx + self.s(10)
            self._icon(icon_img, icon_x, icon_cy - icon_img.height // 2)

            tx = rx + self.s(10) + icon_img.width + self.s(12)
            title_color = config.COLOR_TEXT if on else config.COLOR_TEXT_FAINT
            self._text((tx, icon_cy - 1), title, self.f_row_b,
                       title_color, anchor="lm")

            self._draw_toggle(frame, rx2 - self.s(18), icon_cy, on)

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

    def _flush_overlay(self, frame) -> np.ndarray:
        """Single PIL compositing pass: queued icon pastes, then queued text
        drawn on top, both alpha-blended onto the frame in one round-trip.
        """
        base = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)).convert("RGBA")
        layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
        for img, x, y in self._icons:
            layer.paste(img, (x, y), img)
        self._icons.clear()
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
             menu_open=False, gesture_enabled=None) -> np.ndarray:
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

        # The gesture guide takes over the whole frame like a modal, so the
        # status pill (top-left) would otherwise poke out from behind its
        # rounded corner.
        if not menu_open:
            self._draw_status(frame, tracking, mode_label)
        self._draw_side_menu(frame, menu_open, gesture_enabled)
        if exit_progress > 0.0:
            self._draw_exit(frame, exit_progress)
        self._draw_toasts(frame)

        if debug:
            self._text((self.s(10), frame.shape[0] - self.s(10)),
                       f"{fps:4.1f} fps   {mode}", self.f_debug,
                       config.COLOR_TEXT_FAINT, anchor="ld")

        return self._flush_overlay(frame)

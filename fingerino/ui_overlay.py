"""HUD and gesture-panel rendering — clean and flat, no glow, no colour.

Neutral greys throughout, hairline strokes, state carried by brightness
rather than hue; the status dot is the only thing that stays coloured,
because it reports a live condition. Text is rendered with PIL for crisp
anti-aliasing. The raw skeleton and FPS live behind ``debug``.

There are two independent scales, and picking the wrong one is the usual bug:

* :meth:`UIOverlay.s` — HUD chrome drawn *onto the camera frame* (status
  pill, reticle, toasts, control-zone brackets). The frame is rendered at the
  camera's native resolution and then shrunk by OpenCV into a much smaller
  preview window, so ``s()`` inflates by that ratio to hold a constant
  apparent size. Design that layer against roughly 480x270.
* :meth:`UIOverlay.fs` — the gesture panel, which is a page of window content
  on its own canvas rather than an overlay. It scales with the window and the
  screen; see :func:`panel_scale_for`. Design units for it live in config as
  ``PANEL_*`` and are laid out against a 340-unit width.
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

# icon id -> the one-line "how you do it" shown under each row's label.
_GESTURE_DESCRIPTIONS = {
    icon: desc
    for _, rows in config.GESTURE_GROUPS
    for icon, _, desc in rows
}


def _asset_root() -> Path:
    """Locate the bundled assets/ folder, in dev or a PyInstaller bundle.

    Mirrors hand_tracker._default_model_path()'s sys.frozen / _MEIPASS check
    -- packaging/fingerino.spec bundles assets/ under that same name.
    """
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", "")) / "assets"
    return Path(__file__).resolve().parent.parent / "assets"


def _square_pad(im: Image.Image) -> Image.Image:
    """Crop to the drawn content and re-pad it square.

    The source PNGs are 1024x1024 with wildly different amounts of empty
    margin (a tall pointing finger vs. two wide crossed arms) -- without this
    they'd read at inconsistent sizes next to each other in the row grid.
    Kept separate from the resize so the ink can be remapped at full
    resolution first, which _recolor_icon depends on.
    """
    bbox = im.getbbox()
    if bbox:
        im = im.crop(bbox)
    w, h = im.size
    side = max(w, h)
    pad = max(1, side // 10)
    canvas = Image.new("RGBA", (side + pad * 2, side + pad * 2), (0, 0, 0, 0))
    canvas.paste(im, ((canvas.width - w) // 2, (canvas.height - h) // 2), im)
    return canvas


def _recolor_icon(im: Image.Image, dim_rgb: tuple[int, int, int],
                  key_rgb: tuple[int, int, int]) -> Image.Image:
    """Remap the artwork's two inks onto theme colours.

    The sketches are light-mode drawings: a grey outline plus a blue
    highlight over the fingers the gesture actually uses. The highlight
    becomes the bright key colour and the outline goes dim, which keeps the
    which-fingers-matter cue without keeping the colour. Doing this *before*
    the downscale matters -- the antialiasing then blends the target inks
    instead of smearing blue into every edge.
    """
    a = np.asarray(im).astype(np.int16)
    key = (a[..., 2] - a[..., 0]) > 18       # blue channel well above red
    out = np.empty_like(a)
    for c in range(3):
        out[..., c] = np.where(key, key_rgb[c], dim_rgb[c])
    out[..., 3] = a[..., 3]
    return Image.fromarray(out.astype(np.uint8), "RGBA")


def _flat_tint(im: Image.Image, rgb: tuple[int, int, int]) -> Image.Image:
    """Flatten to a single-colour silhouette, keeping the source alpha shape.

    Used for the disabled-row icon -- same "everything faint" language as
    the dimmed title text next to it.
    """
    solid = Image.new("RGBA", im.size, (*rgb, 255))
    solid.putalpha(im.split()[3])
    return solid


def _fit_icon(im: Image.Image, box: int, gain: float) -> Image.Image:
    """Resize a prepared square to box x box and put back the stroke weight
    the downscale ate.

    The sketches' strokes are ~14px on a 1024px canvas, so at icon size they
    land at well under a pixel and wash out to a grey smudge. Multiplying the
    resized alpha restores the weight without the halo a sharpen filter adds.
    """
    small = im.resize((box, box), Image.LANCZOS)
    if gain == 1.0:
        return small
    a = np.asarray(small).astype(np.float32)
    a[..., 3] = np.clip(a[..., 3] * gain, 0.0, 255.0)
    return Image.fromarray(a.astype(np.uint8), "RGBA")


def _bgr2rgb(c: tuple[int, int, int]) -> tuple[int, int, int]:
    return (c[2], c[1], c[0])


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
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


def _fs(v: float, scale: float) -> int:
    """The panel's design-unit -> pixel rounding. Shared by UIOverlay.fs and
    the sizing maths so the two can never disagree."""
    return max(1, int(round(v * scale)))


def _panel_design_h(comfortable: bool) -> int:
    """Height of the gesture panel in design units, at one density."""
    row = (config.PANEL_ROW_H_COMFORTABLE if comfortable
           else config.PANEL_ROW_H_COMPACT)
    h = config.PANEL_PAD * 2 + config.PANEL_HEADER_H
    for i, (_, rows) in enumerate(config.GESTURE_GROUPS):
        if i:
            h += config.PANEL_SECTION_GAP
        h += (config.PANEL_SECTION_H + len(rows) * row
              + (len(rows) - 1) * config.PANEL_CARD_GAP)
    return h


def _panel_px_h(scale: float, comfortable: bool) -> int:
    """Real pixel height at this scale, mirroring _panel_layout's rounding.

    _panel_layout rounds each piece independently, and there are two dozen of
    them, so the total lands a few pixels above ``scale * _panel_design_h()``
    -- which was enough to push the window four pixels off a 1920x1200
    screen. Anything that sizes the window has to measure with this rather
    than trust the design-space estimate.
    """
    f = lambda v: _fs(v, scale)
    row = f(config.PANEL_ROW_H_COMFORTABLE if comfortable
            else config.PANEL_ROW_H_COMPACT)
    sec, sec_gap, card_gap = (f(config.PANEL_SECTION_H),
                              f(config.PANEL_SECTION_GAP),
                              f(config.PANEL_CARD_GAP))
    h = f(config.PANEL_PAD) * 2 + f(config.PANEL_HEADER_H)
    for i, (_, rows) in enumerate(config.GESTURE_GROUPS):
        if i:
            h += sec_gap
        h += sec + len(rows) * row + (len(rows) - 1) * card_gap
    return h


def panel_scale_for(screen_h: int, win_w: int, win_h: int) -> tuple[float, bool]:
    """Pick the gesture panel's scale and density for this screen.

    Returns ``(scale, comfortable)``. Two constraints: the panel must not
    push the expanded window off the bottom of the screen, and its type must
    not grow out of proportion to a narrow window. Where there isn't the
    height for two-line rows the layout drops to a single-line density rather
    than shrinking the text into illegibility -- so a 1366x768 laptop gets a
    compact list and a 1440p screen gets descriptions.
    """
    avail = max(1, screen_h - config.PANEL_SCREEN_MARGIN - win_h)
    k_w = win_w / config.PANEL_DESIGN_W

    for comfortable in (True, False):
        k = min(k_w, avail / _panel_design_h(comfortable), config.PANEL_SCALE_MAX)
        # Estimate first, then walk down until what will actually be drawn
        # fits -- see _panel_px_h on why the two differ.
        while k > config.PANEL_SCALE_MIN and _panel_px_h(k, comfortable) > avail:
            k -= 0.01
        k = max(config.PANEL_SCALE_MIN, k)
        if comfortable and k < 1.0:
            continue        # no room for description lines; try single-line
        return k, comfortable
    return config.PANEL_SCALE_MIN, False


def _chevron(frame, cx, cy, size, up, color, thickness=2) -> None:
    dy = -size // 2 if up else size // 2
    pts = np.array([(cx - size, cy - dy), (cx, cy + dy), (cx + size, cy - dy)])
    cv2.polylines(frame, [pts], False, color, thickness, cv2.LINE_AA)


def _chevron_lr(frame, cx, cy, size, left, color, thickness=2) -> None:
    dx = -size // 2 if left else size // 2
    pts = np.array([(cx - dx, cy - size), (cx + dx, cy), (cx - dx, cy + size)])
    cv2.polylines(frame, [pts], False, color, thickness, cv2.LINE_AA)


class UIOverlay:
    def __init__(self, ui_scale: float = 1.0, panel_scale: float = 1.0,
                 comfortable: bool = True) -> None:
        # Never shrink below the design-native size — only compensate for a
        # preview window smaller than the camera's native resolution.
        self._scale = max(1.0, ui_scale)
        # The gesture panel gets its own scale and density, worked out once
        # from the screen by panel_scale_for(); see fs().
        self._panel_scale = panel_scale
        self._comfortable = comfortable
        self.f_status = _load_font(self.s(13), bold=True)
        self.f_mode = _load_font(self.s(12), bold=True)
        # Gesture-guide fonts: sized via fs(), not s() -- see fs()'s docstring.
        self.f_title = _load_font(self.fs(config.PANEL_FONT_TITLE), bold=True)
        self.f_sub = _load_font(self.fs(config.PANEL_FONT_SUB))
        self.f_section = _load_font(self.fs(config.PANEL_FONT_SECTION), bold=True)
        self.f_label = _load_font(self.fs(config.PANEL_FONT_LABEL), bold=True)
        self.f_desc = _load_font(self.fs(config.PANEL_FONT_DESC))
        self.f_exit = _load_font(self.s(14), bold=True)
        self.f_toast = _load_font(self.s(12), bold=True)
        self.f_debug = _load_font(self.s(10))
        self._flashes: list[tuple[int, int, float]] = []
        self._toasts: list[tuple[str, float]] = []
        # queued PIL text draws and icon pastes for the single compositing pass
        self._texts: list[tuple] = []
        self._icons: list[tuple[Image.Image, int, int]] = []
        # Memos for the gesture panel: the finished image, the text+icon
        # layer, the geometry and a blank canvas to copy. See
        # render_gesture_panel(), _panel_layout() and _panel_bg().
        self._panel_cache: tuple | None = None
        self._content_cache: tuple | None = None
        self._layout_cache: tuple | None = None
        self._bg_cache: tuple | None = None

        # Never let the sketch crowd the row it sits in: the compact density's
        # rows are shorter than the nominal icon size, and an icon running
        # edge to edge inside its row reads as a cramped mistake.
        row_design = (config.PANEL_ROW_H_COMFORTABLE if comfortable
                      else config.PANEL_ROW_H_COMPACT)
        box = self.fs(min(config.PANEL_ICON, row_design - 8))
        gain = config.PANEL_ICON_ALPHA_GAIN
        key = _bgr2rgb(config.COLOR_TEXT)
        dim = _bgr2rgb(config.COLOR_TEXT_DIM)
        faint = _bgr2rgb(config.COLOR_TEXT_FAINT)
        assets = _asset_root() / "tutorial-gestures"
        self._gesture_icons: dict[str, tuple[Image.Image, Image.Image]] = {}
        for icon_id, fname in _GESTURE_ICON_FILES.items():
            square = _square_pad(Image.open(assets / fname).convert("RGBA"))
            self._gesture_icons[icon_id] = (
                _fit_icon(_recolor_icon(square, dim, key), box, gain),
                _fit_icon(_flat_tint(square, faint), box, gain),
            )

    def s(self, v: float) -> int:
        """Scale a design-space size into frame-space.

        Chrome that overlays live video -- the status pill, cursor reticle,
        toasts -- uses this: it keeps a *constant apparent size* regardless
        of window size, which is what you want for a HUD element.
        """
        return max(1, int(round(v * self._scale)))

    def fs(self, v: float) -> int:
        """Scale a gesture-panel design size into real pixels.

        The guide is a full page of window content, not HUD chrome -- it
        should fill whatever window the user actually has, the way any other
        window's content does, rather than holding a fixed apparent size.
        The factor comes from panel_scale_for(), which works it out once from
        the screen so the panel is always guaranteed to fit on it. Used only
        by the guide and nothing that overlays live video.
        """
        return _fs(v, self._panel_scale)

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

    def _card(self, frame, x1, y1, x2, y2, r, hover: bool = False) -> None:
        """Solid rounded tile for one gesture row.

        Fill only, no border. The row already sits a value step above the
        panel behind it and the gap between rows does the separating; a
        stroke on top of that is the third container level that made the old
        panel read as a stack of boxes. Deliberately not _panel(): that does
        a soft drop shadow via a full-frame copy + blend, cheap once per HUD
        but not nine times over for small tiles.
        """
        _rounded_rect(frame, x1, y1, x2, y2, r,
                      config.COLOR_CARD_HOVER if hover else config.COLOR_CARD, -1)

    def _draw_toggle(self, frame, cx, cy, on: bool) -> None:
        """Switch: a lit white track with a dark knob at the right when on, a
        dim filled track with a grey knob at the left when off.

        Filling the track rather than outlining it means the armed state
        reads from the fill, not from knob position alone. Sized via fs() --
        called only from the guide.
        """
        tw, th_ = self.fs(config.PANEL_TOGGLE_W), self.fs(config.PANEL_TOGGLE_H)
        x1, y1 = cx - tw // 2, cy - th_ // 2
        x2, y2 = x1 + tw, y1 + th_
        r = th_ // 2
        ty = y1 + r
        track = (config.COLOR_TOGGLE_TRACK_ON if on
                 else config.COLOR_TOGGLE_TRACK_OFF)
        # Two caps plus a bar, rather than _rounded_rect: at this size its
        # quarter-ellipse corners leave a visible seam where they meet the
        # straight edge, and a switch is small enough for that to show.
        cv2.rectangle(frame, (x1 + r, y1), (x2 - r, y2), track, -1, cv2.LINE_AA)
        cv2.circle(frame, (x1 + r, ty), r, track, -1, cv2.LINE_AA)
        cv2.circle(frame, (x2 - r, ty), r, track, -1, cv2.LINE_AA)

        # Knob centred on whichever cap it rests in, so its margin is even
        # all the way round however the track rounds off.
        knob_r = max(1, round(th_ * 0.3))
        knob = config.COLOR_TOGGLE_KNOB_ON if on else config.COLOR_TOGGLE_KNOB_OFF
        cv2.circle(frame, (x2 - r if on else x1 + r, ty), knob_r, knob, -1, cv2.LINE_AA)

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

    # -- collapsed tab --------------------------------------------------------
    # Drawing and hit-testing share this so the clickable area can never
    # drift away from what's painted. Shown only while the guide is closed;
    # once open, the panel's own X (see below) closes it instead.
    def _tab_rect(self, w: int, h: int) -> tuple[int, int, int, int]:
        pad = self.s(10)
        tab_w, tab_h = self.s(16), self.s(52)
        x2, y1 = w - pad, h // 2 - tab_h // 2
        return x2 - tab_w, y1, x2, y1 + tab_h

    def collapsed_tab_rect(self, w: int, h: int) -> tuple[int, int, int, int]:
        """Clickable rect (frame coords) for the collapsed tab that opens
        the gesture guide. Padded outward -- it's only ~16 design px wide,
        a fiddly target once shrunk into a small preview window.
        """
        x1, y1, x2, y2 = self._tab_rect(w, h)
        g = self.s(6)
        return x1 - g, y1 - g, x2 + g, y2 + g

    def _draw_collapsed_tab(self, frame) -> None:
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = self._tab_rect(w, h)
        self._panel(frame, x1, y1, x2, y2, r=self.s(5))
        _chevron_lr(frame, (x1 + x2) // 2, (y1 + y2) // 2, self.s(4), True,
                    config.COLOR_TEXT_DIM, self.s(1))

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

    def _panel_layout(self, win_w: int):
        """Everything the panel's drawing and hit-testing need, in panel-local
        coordinates: ``(total_h, head, close, sections, rows)``.

        ``sections`` is [(name, x, baseline_y)]; ``rows`` is one rect per
        entry of GESTURE_TUTORIAL, in that order. Both come out of a single
        walk down the panel, so what gets painted and what is clickable
        cannot drift apart. Memoised because main.py wants the hit-rects once
        at startup and the renderer wants the same layout every frame.
        """
        if self._layout_cache and self._layout_cache[0] == win_w:
            return self._layout_cache[1]

        pad = self.fs(config.PANEL_PAD)
        x1, x2 = pad, win_w - pad
        row_h = self.fs(config.PANEL_ROW_H_COMFORTABLE if self._comfortable
                        else config.PANEL_ROW_H_COMPACT)
        sec_h = self.fs(config.PANEL_SECTION_H)
        sec_gap = self.fs(config.PANEL_SECTION_GAP)
        card_gap = self.fs(config.PANEL_CARD_GAP)

        y = pad
        head = (x1, y, x2, y + self.fs(config.PANEL_HEADER_H))
        side = self.fs(config.PANEL_FONT_TITLE * 1.3)
        close = (x2 - side, y, x2, y + side)
        y = head[3]

        sections, rows = [], []
        for i, (name, entries) in enumerate(config.GESTURE_GROUPS):
            if i:
                y += sec_gap
            # The label sits on the baseline at the foot of its band; the card
            # gap below is what separates it from the section's first row.
            sections.append((name, x1, y + sec_h - card_gap))
            y += sec_h
            for _ in entries:
                rows.append((x1, y, x2, y + row_h))
                y += row_h + card_gap
            y -= card_gap

        layout = (y + pad, head, close, sections, rows)
        self._layout_cache = (win_w, layout)
        return layout

    def _panel_bg(self, win_w: int, total_h: int) -> np.ndarray:
        """A fresh panel-coloured canvas to draw a frame's surface onto.

        Kept and copied rather than rebuilt: np.full over a megabyte of
        pixels costs several milliseconds, which is most of the budget for
        repainting the panel when the hovered row changes.
        """
        size = (win_w, total_h)
        if not self._bg_cache or self._bg_cache[0] != size:
            self._bg_cache = (size, np.full((total_h, win_w, 3),
                                            config.COLOR_PANEL, dtype=np.uint8))
        return self._bg_cache[1].copy()

    def panel_size(self, win_w: int) -> tuple[int, int]:
        """(w, h) of the standalone gesture-guide panel canvas -- always
        win_w wide, so it lines up exactly with the camera preview above it.
        """
        return win_w, self._panel_layout(win_w)[0]

    def panel_close_rect(self, win_w: int) -> tuple[int, int, int, int]:
        """Panel-local hit box for the header's close button."""
        return self._panel_layout(win_w)[2]

    def panel_row_rects(self, win_w: int) -> list[tuple[int, int, int, int]]:
        """Panel-local hit box for each gesture row, in GESTURE_TUTORIAL order."""
        return self._panel_layout(win_w)[4]

    def _draw_close_x(self, frame, rect, hover: bool) -> None:
        """A vector-drawn close button, not a font glyph -- crisp regardless
        of what fonts are available, and reads as a control rather than text.
        Bare until hovered: a ring drawn permanently around it is chrome the
        header doesn't need.
        """
        x1, y1, x2, y2 = rect
        if hover:
            _rounded_rect(frame, x1, y1, x2, y2, self.fs(config.PANEL_RADIUS),
                          config.COLOR_CARD_HOVER, -1)
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        d = max(2, (x2 - x1) // 4)
        th = max(1, self.fs(1.5))
        cv2.line(frame, (cx - d, cy - d), (cx + d, cy + d),
                 config.COLOR_TEXT_DIM, th, cv2.LINE_AA)
        cv2.line(frame, (cx + d, cy - d), (cx - d, cy + d),
                 config.COLOR_TEXT_DIM, th, cv2.LINE_AA)

    def render_gesture_panel(self, enabled, win_w: int, hover_row=None,
                             hover_close: bool = False,
                             paused: bool = False) -> np.ndarray:
        """The full gesture guide, rendered on its own canvas at panel_size().

        Cached twice over, because the main loop composites this into every
        frame and a full build costs ~70ms:

        * the finished image, on exactly the state it draws from -- so an
          unchanged panel costs a dict lookup rather than a redraw;
        * the text and icons, on the toggle state alone. Rasterising glyphs
          is nearly all of that 70ms and none of it depends on what's
          hovered, so moving the pointer down the list only repaints the
          surface underneath and re-composites the layer it already has.
        """
        state = (paused, None if enabled is None else
                 tuple(enabled.get(i, True) for i, _ in config.GESTURE_TUTORIAL))
        key = (win_w, hover_row, hover_close, state)
        if self._panel_cache and self._panel_cache[0] == key:
            return self._panel_cache[1]

        total_h, head, close, sections, rows = self._panel_layout(win_w)
        content_key = (win_w, state)
        cached = (self._content_cache[1]
                  if self._content_cache and self._content_cache[0] == content_key
                  else None)
        frame = self._panel_bg(win_w, total_h)
        hx1, hy1 = head[0], head[1]

        # Header: the name, then how many gestures are actually live. The
        # count is real state, and it's what makes a dimmed row read as a
        # deliberate choice rather than as something failing to draw. While
        # the session is paused the count would be a lie, so the subtitle
        # reports the pause and how to get out of it instead -- the rows keep
        # showing their own switches, because those are what comes back live.
        on_count = sum(1 for i, _ in config.GESTURE_TUTORIAL
                       if enabled is None or enabled.get(i, True))
        if cached is None:
            self._text((hx1, hy1), "Gestures", self.f_title, config.COLOR_TEXT,
                       anchor="la")
            sub_text = ("Paused — both palms up to resume" if paused else
                        f"{on_count} of {len(config.GESTURE_TUTORIAL)} enabled")
            self._text((hx1, hy1 + self.fs(config.PANEL_FONT_TITLE * 1.2) + self.fs(2)),
                       sub_text, self.f_sub,
                       config.COLOR_TEXT if paused else config.COLOR_TEXT_DIM,
                       anchor="la")
            for name, sx, sy in sections:
                self._text((sx, sy), name, self.f_section, config.COLOR_TEXT_DIM,
                           anchor="ls")
        self._draw_close_x(frame, close, hover_close)

        radius = self.fs(config.PANEL_RADIUS)
        card_pad = self.fs(config.PANEL_CARD_PAD)
        icon_gap = self.fs(config.PANEL_ICON_GAP)
        tw = self.fs(config.PANEL_TOGGLE_W)
        gap2 = self.fs(2)
        lh_label = self.fs(config.PANEL_FONT_LABEL * 1.25)
        lh_desc = self.fs(config.PANEL_FONT_DESC * 1.25)

        for i, ((icon, title), rect) in enumerate(zip(config.GESTURE_TUTORIAL, rows)):
            rx1, ry1, rx2, ry2 = rect
            on = enabled is None or enabled.get(icon, True)
            cy = (ry1 + ry2) // 2

            self._card(frame, rx1, ry1, rx2, ry2, radius, hover=i == hover_row)
            self._draw_toggle(frame, rx2 - card_pad - tw // 2, cy, on)

            if cached is not None:
                continue
            icon_img = self._gesture_icons[icon][0 if on else 1]
            self._icon(icon_img, rx1 + card_pad, cy - icon_img.height // 2)

            tx = rx1 + card_pad + icon_img.width + icon_gap
            label_c = config.COLOR_TEXT if on else config.COLOR_TEXT_FAINT
            if self._comfortable:
                top = cy - (lh_label + gap2 + lh_desc) // 2
                self._text((tx, top), title, self.f_label, label_c, anchor="la")
                self._text((tx, top + lh_label + gap2), _GESTURE_DESCRIPTIONS[icon],
                           self.f_desc,
                           config.COLOR_TEXT_DIM if on else config.COLOR_TEXT_FAINT,
                           anchor="la")
            else:
                self._text((tx, cy - 1), title, self.f_label, label_c, anchor="lm")

        if cached is None:
            cached = self._build_overlay((win_w, total_h))
            self._content_cache = (content_key, cached)
        out = self._composite(frame, cached)
        self._panel_cache = (key, out)
        return out

    def expanded_layout(self, win_w: int, win_h: int) -> dict:
        """Composite geometry for the expanded (guide-open) window: the
        gesture panel sits directly beneath the camera preview at exactly
        its width and left edge, so the preview doesn't move or resize when
        the guide opens -- the window just grows downward to fit both. A
        pure function of panel_size() and the collapsed window's own size,
        so it's computed once at startup and reused both for the per-frame
        composite and for offsetting the (also computed once) panel
        hit-rects into window space.

        The panel butts straight up against the preview with no gap: it is
        the window's content area, not a floating card, and a strip of
        background between the two would read as a seam.
        """
        panel_w, panel_h = self.panel_size(win_w)
        return {
            "size": (win_w, win_h + panel_h),
            "cam_xy": (0, 0),
            "panel_xy": (0, win_h),
        }

    def compose_expanded(self, cam_disp: np.ndarray, panel_img: np.ndarray,
                         layout: dict) -> np.ndarray:
        """Paste the (already display-sized) camera preview and the guide
        panel onto one background-filled canvas, per expanded_layout()."""
        w, h = layout["size"]
        canvas = np.full((h, w, 3), config.COLOR_APP_BG, dtype=np.uint8)
        cx, cy = layout["cam_xy"]
        ch, cw = cam_disp.shape[:2]
        canvas[cy:cy + ch, cx:cx + cw] = cam_disp
        px, py = layout["panel_xy"]
        ph, pw = panel_img.shape[:2]
        canvas[py:py + ph, px:px + pw] = panel_img
        return canvas

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
             menu_open=False, paused=False, hold_progress=0.0) -> np.ndarray:
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
        # The guide now renders on its own canvas (render_gesture_panel) and
        # is composited below the camera preview by main.py, so this camera
        # frame only ever needs the collapsed "open me" tab.
        if not menu_open:
            self._draw_collapsed_tab(frame)
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

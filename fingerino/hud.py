"""The HUD: a small always-on-top camera preview in the top-left corner.

Frameless, so it carries no title bar while you use it. Hovering shows a thin
frame and two caption buttons in the usual top-right spot: **minimize** hides the
HUD while tracking carries on, and **close** stops tracking (the Home window stays
open). On Windows it gets the system's own drop shadow and, on Windows 11,
rounded corners, so it sits on the desktop like any other window.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QHBoxLayout, QToolButton, QVBoxLayout, QWidget

from . import winui

_WIN = sys.platform.startswith("win")
# Windows caption-button glyphs (Segoe Fluent Icons / MDL2 Assets), so the
# buttons look exactly like the ones on every other window. Plain text
# elsewhere.
_GLYPH_MIN, _GLYPH_CLOSE = ("\uE921", "\uE8BB") if _WIN else ("-", "x")
_RADIUS = 8          # Windows 11 top-level window corner radius


class _CaptionButton(QToolButton):
    def __init__(self, glyph: str, tip: str, danger: bool, parent: QWidget) -> None:
        super().__init__(parent)
        self.setText(glyph)
        self.setToolTip(tip)
        self.setAccessibleName(tip)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setFixedSize(36, 26)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        if _WIN:
            font = QFont("Segoe Fluent Icons")
            font.setFamilies(["Segoe Fluent Icons", "Segoe MDL2 Assets"])
            font.setPixelSize(10)
            self.setFont(font)
        # Same hover colours as the system caption buttons: a faint wash, or
        # the Windows close-button red.
        hover = "#c42b1c" if danger else "rgba(255, 255, 255, 40)"
        self.setStyleSheet(
            "QToolButton { color: white; background: rgba(0, 0, 0, 90);"
            " border: none; border-radius: 4px; }"
            f"QToolButton:hover {{ background: {hover}; }}"
            "QToolButton:pressed { background: rgba(255, 255, 255, 25); }")


class Hud(QWidget):
    minimizeRequested = Signal()
    closeRequested = Signal()

    def __init__(self, size: QSize) -> None:
        super().__init__(None, Qt.WindowType.Window
                         | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint
                         # No taskbar button, and clicking it never takes
                         # focus from the app the hand is controlling.
                         | Qt.WindowType.Tool
                         | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setWindowTitle("Fingerino")
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setFixedSize(size)
        self._image: QImage | None = None
        self._hover = False
        self._decorated = False

        self._min = _CaptionButton(_GLYPH_MIN, "Hide preview (tracking continues)",
                                   False, self)
        self._close = _CaptionButton(_GLYPH_CLOSE, "Stop Fingerino", True, self)
        self._min.clicked.connect(self.minimizeRequested)
        self._close.clicked.connect(self.closeRequested)

        bar = QHBoxLayout()
        bar.setContentsMargins(0, 6, 6, 0)
        bar.setSpacing(4)
        bar.addStretch(1)
        bar.addWidget(self._min)
        bar.addWidget(self._close)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addLayout(bar)
        outer.addStretch(1)
        self._set_chrome(False)

    def set_frame(self, image: QImage) -> None:
        self._image = image
        self.update()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._decorated:
            # The native handle exists from the first show onwards.
            winui.add_shadow(int(self.winId()))
            self._decorated = True

    # -- hover chrome -------------------------------------------------------

    def _set_chrome(self, on: bool) -> None:
        self._hover = on
        self._min.setVisible(on)
        self._close.setVisible(on)
        self.update()

    def enterEvent(self, event) -> None:
        self._set_chrome(True)

    def leaveEvent(self, event) -> None:
        self._set_chrome(False)

    # -- painting -----------------------------------------------------------

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        r = QRectF(self.rect())
        if not _WIN:
            # Windows 11 rounds the window itself (winui.add_shadow); other
            # platforms get the same shape by clipping.
            clip = QPainterPath()
            clip.addRoundedRect(r, _RADIUS, _RADIUS)
            p.setClipPath(clip)
        p.fillRect(self.rect(), QColor(16, 16, 18))
        if self._image is not None:
            p.drawImage(QRect(0, 0, self.width(), self.height()), self._image)
        if self._hover:
            # A hairline frame says "this is a window you can act on".
            p.setPen(QPen(QColor(255, 255, 255, 110), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), _RADIUS, _RADIUS)
        p.end()

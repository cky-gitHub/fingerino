"""The HUD is drawn at its own size: the camera's resolution doesn't change
how it looks, and its chrome grows with the HUD. No camera needed."""

from __future__ import annotations

import pytest

pytest.importorskip("cv2")
pytest.importorskip("pynput")

import numpy as np
import sessionkit

from fingerino import engine
from fingerino.ui_overlay import UIOverlay


def _hud(monkeypatch, camera, preview=(320, 180)):
    world = sessionkit.run(monkeypatch, [[]] * 3, camera=camera,
                           options=engine.Options(drive=False, preview_size=preview))
    assert world.error is None
    return world.last_frame


def _drawn_box(frame) -> tuple[int, int]:
    """Width and height of everything drawn on the (black) picture."""
    ys, xs = np.nonzero(frame.max(axis=2) > 8)
    return int(xs.max() - xs.min()), int(ys.max() - ys.min())


def test_the_hud_looks_the_same_whatever_the_camera_sends(monkeypatch):
    # A laptop camera may ignore the 1280x720 Fingerino asks for.
    usual = _hud(monkeypatch, (1280, 720))
    assert usual.shape == (180, 320, 3)
    for camera in ((1920, 1080), (2560, 1440), (640, 480)):
        assert np.array_equal(_hud(monkeypatch, camera), usual), camera


def test_the_hud_chrome_grows_with_the_hud(monkeypatch):
    # A bigger screen, or display scaling, makes a bigger HUD: the status
    # pill must grow with it rather than stay the same number of pixels.
    small_w, small_h = _drawn_box(_hud(monkeypatch, (1280, 720), (320, 180)))
    big_w, big_h = _drawn_box(_hud(monkeypatch, (1280, 720), (640, 360)))
    assert 1.8 < big_w / small_w < 2.2
    assert 1.8 < big_h / small_h < 2.2


def test_a_small_hud_keeps_the_design_size():
    assert UIOverlay(ui_scale=0.6).s(13) == 13
    assert UIOverlay(ui_scale=2.0).s(13) == 26


def test_hud_buttons_need_no_icon_font():
    # Their glyphs are drawn, so a missing Segoe font can't turn them into boxes.
    pytest.importorskip("PySide6")
    from PySide6.QtCore import QSize
    from PySide6.QtWidgets import QApplication

    from fingerino.hud import Hud

    _ = QApplication.instance() or QApplication([])
    hud = Hud(QSize(320, 180))
    assert [b.text() for b in (hud._min, hud._close)] == ["", ""]
    assert (hud._min.kind, hud._close.kind) == ("minimize", "close")
    hud.close()

"""The Home window loads, and what it does reaches the settings and the app.

Needs PySide6, so the dependency-free CI job skips it. The QML is only
checked at load time, so a typo there would otherwise first show up as an
empty Home window in a user's hands. Nothing here opens the camera.
"""

import json

import pytest

pytest.importorskip("PySide6")

from fingerino import config, settings, shell


@pytest.mark.parametrize("combo, label", [
    ("<ctrl>+<alt>+f", "Ctrl+Alt+F"),
    ("<cmd>+<shift>+k", "Cmd+Shift+K"),
])
def test_hotkey_label(combo, label):
    assert shell.hotkey_label(combo) == label


def test_hud_keeps_the_camera_aspect_and_its_share_of_the_screen():
    w, h = shell.hud_size(1920, 1080)
    assert abs(w / h - config.CAMERA_WIDTH / config.CAMERA_HEIGHT) < 0.01
    assert abs(w * h / (1920 * 1080) - config.WINDOW_SCREEN_FRACTION) < 0.01


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    data = tmp_path_factory.mktemp("data")
    a = shell.Shell(settings.Settings(), str(data), None, tray=False, hotkey=False)
    yield a, data
    a.close()


def test_qml_loads(app):
    a, _ = app
    assert a.window is not None, "Home.qml failed to load; see stderr for the QML error"


def test_opens_with_tracking_off(app):
    a, _ = app
    assert a.session is None
    assert a.bridge.property("running") is False
    assert not a.hud.isVisible()


def test_groups_mirror_the_gesture_list(app):
    a, _ = app
    groups = a.bridge.property("groups")
    assert [g["name"] for g in groups] == [name for name, _ in config.GESTURE_GROUPS]
    assert sum(len(g["rows"]) for g in groups) == len(config.GESTURE_TUTORIAL)


def test_switching_a_gesture_off_is_saved(app):
    a, data = app
    a.bridge.setGestureEnabled("shaka", False)
    assert a.bridge.gestureEnabled("shaka") is False
    stored = json.loads((data / settings.FILENAME).read_text(encoding="utf-8"))
    assert stored["gestures"]["shaka"] is False
    a.bridge.setGestureEnabled("not_a_gesture", False)
    assert "not_a_gesture" not in a.prefs.gestures


def test_start_on_open_is_saved(app):
    a, data = app
    a.bridge.setStartOnOpen(True)
    stored = json.loads((data / settings.FILENAME).read_text(encoding="utf-8"))
    assert stored["start_on_open"] is True
    a.bridge.setStartOnOpen(False)


def test_stop_and_pause_are_harmless_when_off(app):
    a, _ = app
    a.bridge.stop()
    a.bridge.togglePause()
    assert a.session is None


def test_closing_home_while_off_quits(app, monkeypatch):
    a, _ = app
    quits = []
    monkeypatch.setattr(a, "quit", lambda: quits.append(True))
    a.bridge.homeClosed()
    assert quits == [True]

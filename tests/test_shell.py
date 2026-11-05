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


def test_cursor_switch_is_saved_and_marks_the_pointer_group(app):
    a, data = app
    assert a.bridge.property("cursorEnabled") is False
    a.bridge.setCursorEnabled(True)
    stored = json.loads((data / settings.FILENAME).read_text(encoding="utf-8"))
    assert stored["cursor"] is True
    assert a.bridge.property("cursorEnabled") is True
    a.bridge.setCursorEnabled(False)
    groups = a.bridge.property("groups")
    pointer = [g for g in groups if g["cursor"]]
    assert [g["name"] for g in pointer] == ["Pointer"]
    assert {r["icon"] for r in pointer[0]["rows"] if r["cursor"]} == config.CURSOR_GESTURES


def test_rebinding_a_sign_from_home_is_saved_and_shown(app):
    a, data = app
    assert a.bridge.actionInfo("shaka")["label"] == "New chat"
    version = a.bridge.property("bindingsVersion")
    err = a.bridge.setAction("shaka", "open", "https://open.spotify.com/playlist/x", "")
    assert err == ""
    assert a.bridge.property("bindingsVersion") == version + 1
    info = a.bridge.actionInfo("shaka")
    assert info["kind"] == "open" and info["label"] == "Open spotify.com"
    stored = json.loads((data / "actions.json").read_text(encoding="utf-8"))
    assert stored["bindings"]["shaka"].startswith("user-")
    assert stored["actions"][0]["target"] == "https://open.spotify.com/playlist/x"
    # The running session shares the registry, so this reaches it at once.
    assert a.registry.action_for("shaka").kind == "open"

    a.bridge.resetAction("shaka")
    assert a.bridge.actionInfo("shaka")["label"] == "New chat"
    a.bridge.clearAction("flat_left")
    assert a.bridge.actionInfo("flat_left")["label"] == "Does nothing"
    a.bridge.resetAction("flat_left")


def test_invalid_action_is_refused_with_a_message(app):
    a, _ = app
    assert a.bridge.setAction("shaka", "hotkey", "ctrl+shift", "") != ""
    assert a.bridge.setAction("shaka", "open", "  ", "") != ""
    assert a.bridge.actionInfo("shaka")["label"] == "New chat"


def test_sign_rows_are_marked_for_the_action_editor(app):
    a, _ = app
    rows = [r for g in a.bridge.property("groups") for r in g["rows"]]
    assert {r["icon"] for r in rows if r["sign"]} == {
        "shaka", "flat_down", "flat_up", "flat_left", "flat_right"}


@pytest.mark.parametrize("key, mods, combo", [
    ("Key_K", ("ControlModifier", "ShiftModifier"), "ctrl+shift+k"),
    ("Key_F5", (), "f5"),
    ("Key_Space", ("AltModifier",), "alt+space"),
    ("Key_Control", ("ControlModifier",), ""),          # still waiting for a key
])
def test_shortcut_recorder_turns_key_presses_into_shortcuts(key, mods, combo, monkeypatch):
    from PySide6.QtCore import Qt
    monkeypatch.setattr(shell.sys, "platform", "win32")
    m = 0
    for name in mods:
        m |= getattr(Qt.KeyboardModifier, name).value
    assert shell.combo_from_qt(getattr(Qt.Key, key).value, m) == combo


def test_shortcut_recorder_swaps_cmd_and_ctrl_on_macos(monkeypatch):
    from PySide6.QtCore import Qt
    monkeypatch.setattr(shell.sys, "platform", "darwin")
    m = Qt.KeyboardModifier.ControlModifier.value
    assert shell.combo_from_qt(Qt.Key.Key_K.value, m) == "cmd+k"

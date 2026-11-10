"""The design-review changes to Home: colours that hold contrast in both
themes, rows named by their sign, pointer switches that show off while the
cursor is, the pause shortcut, text size and custom-sign pictures.
Camera-free; the QML is loaded offscreen where it's needed."""

import re
from pathlib import Path

import pytest

HOME_QML = Path(__file__).resolve().parents[1] / "fingerino" / "qml" / "Home.qml"
# The Fluent card surfaces Home's text sits on, in each theme.
CARD = {"dark": "#2b2b2b", "light": "#fbfbfb"}


def _luminance(hex_color):
    def channel(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def _contrast(a, b):
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


@pytest.mark.parametrize("name", ["warnColor", "errorColor", "okColor"])
def test_status_colours_hold_4_5_to_1_in_both_themes(name):
    qml = HOME_QML.read_text(encoding="utf-8")
    m = re.search(rf'property color {name}: dark \? "(#\w{{6}})" : "(#\w{{6}})"', qml)
    assert m, f"{name} should be a dark/light pair"
    dark, light = m.groups()
    assert _contrast(dark, CARD["dark"]) >= 4.5
    assert _contrast(light, CARD["light"]) >= 4.5


def test_no_fixed_status_colours_are_left_in_home():
    qml = HOME_QML.read_text(encoding="utf-8")
    for old in ("#f85149", "#d29922", "#3fb950"):
        assert old not in qml


def test_type_sizes_go_through_the_text_scale():
    qml = HOME_QML.read_text(encoding="utf-8")
    assert not re.search(r"pixelSize: \d", qml)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def _shell_module():
    pytest.importorskip("PySide6")
    from fingerino import shell
    return shell


def test_pause_shortcut_converts_for_pynput():
    shell = _shell_module()
    assert shell.to_pynput("ctrl+alt+f") == "<ctrl>+<alt>+f"
    assert shell.to_pynput("ctrl+shift+f5") == "<ctrl>+<shift>+<f5>"


def test_text_scale_reads_windows_text_size(monkeypatch):
    import sys
    import types
    shell = _shell_module()

    class Key:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake(value):
        return types.SimpleNamespace(
            HKEY_CURRENT_USER=0, OpenKey=lambda *a: Key(),
            QueryValueEx=lambda key, name: (value, 4))

    monkeypatch.setattr(shell.sys, "platform", "win32")
    for stored, expected in ((150, 1.5), (100, 1.0), (300, 2.25), ("x", 1.0)):
        monkeypatch.setitem(sys.modules, "winreg", fake(stored))
        assert shell.text_scale() == expected
    monkeypatch.setattr(shell.sys, "platform", "darwin")
    assert shell.text_scale() == 1.0


# ---------------------------------------------------------------------------
# Home, through the bridge and the real QML
# ---------------------------------------------------------------------------

@pytest.fixture
def home(tmp_path):
    pytest.importorskip("PySide6")
    from fingerino import settings, shell
    a = shell.Shell(settings.Settings(), str(tmp_path), None, tray=False, hotkey=False)
    yield a
    a.close()


def test_built_in_sign_rows_are_titled_by_the_sign(home):
    rows = {r["icon"]: r for g in home.bridge.property("groups") for r in g["rows"]}
    assert rows["shaka"]["title"] == "Shaka"
    assert rows["flat_right"]["title"] == "Swipe right"
    assert rows["thumb"]["title"] == "Move cursor"         # functions keep their name


def _item(window, name):
    """An item by objectName, through the visual tree: what a Repeater
    creates isn't in the QObject tree findChild walks."""
    todo = [window.contentItem()]
    while todo:
        item = todo.pop()
        if item.objectName() == name:
            return item
        todo.extend(item.childItems())
    return None


def test_pointer_switches_show_off_while_the_cursor_is_off(home):
    a = home
    switch = _item(a.window, "switch-point")
    assert a.prefs.gestures["point"] is True                # enabled underneath
    assert switch.property("checked") is False              # but shown off
    a.bridge.setCursorEnabled(True)
    assert switch.property("checked") is True
    a.bridge.setGestureEnabled("point", False)
    a.bridge.setCursorEnabled(False)
    a.bridge.setCursorEnabled(True)
    assert switch.property("checked") is False              # its own setting again
    shaka = _item(a.window, "switch-shaka")
    assert shaka.property("checked") is True                # signs don't depend on it


def test_changing_the_pause_shortcut(home, monkeypatch):
    a = home
    assert a.bridge.setHotkey("f")                          # no modifier: refused
    assert a.bridge.setHotkey("shift+f")                    # shift alone: refused
    assert a.bridge.setHotkey("ctrl+shift+p") == ""
    assert a.prefs.hotkey == "<ctrl>+<shift>+p"
    assert a.bridge.property("hotkey") == "Ctrl+Shift+P"


def test_a_shortcut_that_cant_be_used_keeps_the_old_one(home, monkeypatch):
    from fingerino import shell
    a = home
    a._hotkey_wanted = True
    monkeypatch.setattr(shell.system_actions, "listen_hotkey", lambda combo, cb: None)
    before = a.prefs.hotkey
    assert a.bridge.setHotkey("ctrl+alt+k")
    assert a.prefs.hotkey == before


def test_only_built_in_signs_have_a_picture(home):
    import random

    from landmarks import recording, thumbs_up

    from fingerino import config, signs
    a = home
    rec = signs.Recorder(0.0, config.SIGN_RECORD_S, False)
    for lms in recording(thumbs_up, random.Random(1), n=40):
        rec.add(lms, "Right")
    a.library.add("Up", rec.result().samples)
    (card,) = a.bridge.property("customSigns")
    assert "image" not in card
    rows = {r["icon"]: r for g in a.bridge.property("groups") for r in g["rows"]}
    assert rows["shaka"]["image"]


def test_theme_setting(home, tmp_path):
    from PySide6.QtCore import QObject, Qt

    from fingerino import settings

    a = home
    hints = a.app.styleHints()
    assert a.bridge.property("theme") == "dark"                 # the default
    box = a.window.findChild(QObject, "themeBox")
    assert box.property("displayText") == "Dark"                 # not blank
    a.bridge.setTheme("light")
    assert hints.colorScheme() == Qt.ColorScheme.Light
    assert a.prefs.theme == "light"
    a.bridge.setTheme("dark")
    assert hints.colorScheme() == Qt.ColorScheme.Dark
    assert box.property("displayText") == "Dark"
    a.bridge.setTheme("purple")                          # ignored
    assert a.prefs.theme == "dark"
    a.bridge.setTheme("system")
    assert box.property("displayText") == "Use system setting"
    assert settings.Settings.from_json({"appearance": "nope"}).theme == "dark"
    assert settings.Settings.from_json({"appearance": "system"}).theme == "system"
    # v0.3.0 files: "system" was the old default, so it becomes dark; light stays.
    assert settings.Settings.from_json({"theme": "system"}).theme == "dark"
    assert settings.Settings.from_json({"theme": "light"}).theme == "light"
    assert settings.Settings.from_json(settings.Settings(theme="light").to_json()).theme == "light"


def test_navigation_icons_are_drawn_not_font_glyphs(home):
    """The icons used to be Segoe Fluent Icons glyphs, which showed as empty
    boxes on PCs without that font. They are drawn outlines now."""
    from PySide6.QtCore import QObject

    for name in ("home", "hand", "gear"):
        icon = home.window.findChild(QObject, "navIcon-" + name)
        assert icon is not None, name
        assert icon.property("width") > 0


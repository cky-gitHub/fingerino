"""The cursor is a module that can be switched off, and is off by default.

With it off, no mouse event can come out of the engine, the pointing and
two-finger poses are left unclaimed, and every sign and safety gesture still
works. With it on, nothing changed -- including the drag safety.
"""

import json

from landmarks import both_palms, crossed, fist, flat, point, shaka, two_finger

from fingerino import config, settings
from fingerino.gesture_detector import GestureEngine

FPS = 30
DT = 1 / FPS


def run(engine, frames, start=0.0):
    return [engine.update(hands, start + i * DT) for i, hands in enumerate(frames)]


def steady(hands, seconds):
    return [hands] * round(seconds * FPS)


def mouse_events(outs):
    return sum(o.click + o.press + abs(o.scroll_steps) for o in outs)


# ---------------------------------------------------------------------------
# Off: no mouse, poses free
# ---------------------------------------------------------------------------

def test_off_points_and_holds_produce_no_button_events():
    frames = (steady([fist()], 0.1) + steady([point()], 0.2) + steady([fist()], 0.3)
              + steady([point()], config.DRAG_HOLD_S + 1.0) + steady([fist()], 0.5))
    outs = run(GestureEngine(cursor=False), frames)
    assert mouse_events(outs) == 0
    assert not any(o.release or o.dragging or o.aiming for o in outs)


def test_off_two_fingers_do_not_scroll_and_are_left_free():
    n = 15
    frames = [[two_finger(y=0.4 + 0.2 * i / n)] for i in range(n + 1)]
    outs = run(GestureEngine(cursor=False), frames)
    assert mouse_events(outs) == 0
    assert all(o.mode == "idle" for o in outs)


def test_off_a_pointing_hand_is_idle_not_move():
    outs = run(GestureEngine(cursor=False), steady([point()], 0.5))
    assert all(o.mode == "idle" and o.mode_label == "" for o in outs)


def test_off_shaka_swipes_hold_and_exit_still_work():
    engine = GestureEngine(cursor=False)
    assert [s for o in run(engine, steady([shaka()], 1.0)) for s in o.signs] == ["shaka"]

    n = 9
    swipe = [[flat(x=0.5, y=0.5 + 0.3 * i / n)] for i in range(n + 1)]
    assert [s for o in run(GestureEngine(cursor=False), swipe) for s in o.signs] \
        == ["flat_down"]

    outs = run(GestureEngine(cursor=False), steady(both_palms(), config.HOLD_TOGGLE_S + 0.5))
    assert sum(o.hold_toggle for o in outs) == 1

    outs = run(GestureEngine(cursor=False), steady(crossed(), config.EXIT_HOLD_S + 0.2))
    assert any(o.exit for o in outs)


# ---------------------------------------------------------------------------
# On: unchanged, including the safety paths
# ---------------------------------------------------------------------------

def test_on_click_and_scroll_work():
    frames = steady([fist()], 0.1) + steady([point()], 0.2) + steady([fist()], 0.3)
    assert sum(o.click for o in run(GestureEngine(cursor=True), frames)) == 1
    n = 15
    scroll = [[two_finger(y=0.4 + 0.2 * i / n)] for i in range(n + 1)]
    assert any(o.scroll_steps for o in run(GestureEngine(cursor=True), scroll))


def test_switching_the_cursor_off_mid_drag_releases_the_button():
    engine = GestureEngine(cursor=True)
    outs = run(engine, steady([fist()], 0.1) + steady([point()], config.DRAG_HOLD_S + 0.2))
    assert sum(o.press for o in outs) == 1 and outs[-1].dragging

    engine.cursor = False
    t0 = len(outs) * DT
    later = run(engine, steady([point()], config.DRAG_RELEASE_GRACE_S + 0.2), start=t0)
    assert sum(o.release for o in later) == 1
    assert not later[-1].dragging
    assert mouse_events(later) == 0


def test_drag_safety_valve_still_applies_with_the_cursor_on():
    engine = GestureEngine(cursor=True)
    frames = steady([fist()], 0.1) + steady([point()], config.DRAG_HOLD_S + config.DRAG_MAX_S
                                            + 0.5)
    outs = run(engine, frames)
    assert sum(o.press for o in outs) == 1
    assert sum(o.release for o in outs) == 1
    assert not outs[-1].dragging


# ---------------------------------------------------------------------------
# The setting
# ---------------------------------------------------------------------------

def test_cursor_is_off_by_default():
    assert settings.Settings().cursor is False


def test_a_v02_settings_file_turns_the_cursor_off(tmp_path):
    # Decided: off for everyone, upgraders included.
    old = {"schema": 1, "gestures": {"shaka": False}, "onboarded": True,
           "start_on_open": False, "hotkey": "<ctrl>+<alt>+f"}
    (tmp_path / settings.FILENAME).write_text(json.dumps(old), encoding="utf-8")
    s = settings.load(str(tmp_path))
    assert s.cursor is False
    assert s.gestures["shaka"] is False


def test_cursor_setting_round_trips(tmp_path):
    s = settings.Settings(cursor=True)
    assert settings.save(str(tmp_path), s)
    assert settings.load(str(tmp_path)).cursor is True
    assert settings.Settings.from_json({"cursor": "yes"}).cursor is False


def test_cursor_rows_are_real_gestures():
    assert {icon for icon, _ in config.GESTURE_TUTORIAL} >= config.CURSOR_GESTURES

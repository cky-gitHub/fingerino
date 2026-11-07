"""A whole tracking session, camera-free: engine.Session end to end.

See sessionkit.py. These check the wiring the unit tests can't: that the
cursor switch really keeps the mouse still, that signs reach their actions,
that pausing and the per-sign switches gate them, and that the button is
released on the way out.
"""

import pytest

pytest.importorskip("cv2")
pytest.importorskip("pynput")

import sessionkit
from landmarks import both_palms, crossed_fingers, fist, point, shaka, two_finger
from sessionkit import steady

from fingerino import config, settings


def mouse_calls(world):
    return [c for c in world.cursor_calls
            if c[0] in ("update", "click", "press", "scroll")]


def test_cursor_off_sends_no_mouse_events(monkeypatch):
    n = 15
    frames = (steady([fist()], 0.2) + steady([point()], 0.2) + steady([fist()], 0.3)
              + steady([point()], config.DRAG_HOLD_S + 0.5)
              + [[two_finger(y=0.4 + 0.2 * i / n)] for i in range(n + 1)])
    world = sessionkit.run(monkeypatch, frames, settings.Settings(cursor=False))
    assert world.error is None
    assert mouse_calls(world) == []


def test_cursor_on_moves_clicks_and_releases_on_exit(monkeypatch):
    frames = (steady([fist()], 0.2) + steady([point()], 0.2) + steady([fist()], 0.3)
              + steady([point()], config.DRAG_HOLD_S + 0.3))
    world = sessionkit.run(monkeypatch, frames, settings.Settings(cursor=True))
    names = [c[0] for c in world.cursor_calls]
    assert "update" in names
    assert names.count("click") == 1
    assert names.count("press") == 1
    # Stopped mid-drag: the shutdown path lets go of the button.
    assert names[-1] == "release"


def test_shaka_runs_its_action_with_the_cursor_off(monkeypatch):
    frames = steady([fist()], 0.2) + steady([shaka()], 1.0)
    world = sessionkit.run(monkeypatch, frames, settings.Settings(cursor=False))
    assert world.actions == ["open_ai_chat"]
    assert "New chat" in world.toasts


def test_a_switched_off_sign_does_nothing(monkeypatch):
    prefs = settings.Settings()
    prefs.gestures["shaka"] = False
    world = sessionkit.run(monkeypatch, steady([shaka()], 1.0), prefs)
    assert world.actions == []


def test_no_move_mode_never_acts(monkeypatch):
    world = sessionkit.run(monkeypatch, steady([shaka()], 1.0), drive=False)
    assert world.actions == []
    assert "New chat" in world.toasts         # still shown on the HUD


def test_hold_pauses_signs_and_hold_again_resumes(monkeypatch):
    hold = steady(both_palms(), config.HOLD_TOGGLE_S + 0.3)
    gap = steady([], config.HOLD_COOLDOWN_S + 0.3)
    frames = hold + gap + steady([shaka()], 1.0) + gap + hold + gap \
        + steady([shaka()], 1.0)
    world = sessionkit.run(monkeypatch, frames)
    assert world.toasts.count("Paused — gestures off") == 1
    assert world.toasts.count("Resumed") == 1
    assert world.actions == ["open_ai_chat"]           # only the second shaka


def test_exit_gesture_ends_the_session(monkeypatch):
    frames = steady([crossed_fingers()], config.EXIT_HOLD_S + 0.3) + steady([shaka()], 2.0)
    world = sessionkit.run(monkeypatch, frames)
    assert world.error is None
    assert world.i < len(frames) - 1                   # stopped early
    assert world.actions == []


def test_a_rebound_shaka_runs_its_new_action(monkeypatch):
    from fingerino.actions import Registry, make_action
    registry = Registry()
    music = make_action("open", "https://open.spotify.com/playlist/x")
    registry.bind("shaka", music)
    world = sessionkit.run(monkeypatch, steady([shaka()], 1.0), registry=registry)
    assert world.actions == [music.id]
    assert "Open spotify.com" in world.toasts


def test_a_failing_action_is_reported_not_fatal(monkeypatch):
    from fingerino import engine
    from fingerino.actions import make_action

    def boom(action):
        raise FileNotFoundError("no such app")

    monkeypatch.setattr(engine.system_actions, "perform", boom)
    assert engine.perform_action(make_action("open_app", "/nope/Spotify.app")) \
        == "Couldn't open Spotify"


def test_a_custom_sign_runs_its_action_through_the_session(monkeypatch):
    import random

    from landmarks import recording, thumbs_up

    from fingerino import signs
    from fingerino.actions import Registry, make_action
    from fingerino.sign_matcher import canonical

    library = signs.Library()
    rng = random.Random(1)
    sign = library.add("Thumbs up", [canonical(h) for h in recording(thumbs_up, rng)])
    registry = Registry()
    mute = make_action("media", "mute")
    registry.bind(sign.id, mute)
    world = sessionkit.run(monkeypatch, steady([fist()], 0.2) + steady([thumbs_up()], 1.5),
                           registry=registry, library=library)
    assert world.actions == [mute.id]
    assert "Mute" in world.toasts

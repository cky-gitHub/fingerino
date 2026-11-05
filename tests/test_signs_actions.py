"""Every built-in gesture, end to end through GestureEngine and the registry.

Synthetic landmark sequences on a synthetic clock: no camera, no OS input.
The point of these is to pin down today's behaviour, so the split between
signs (what the detector sees) and actions (what the registry does) can move
code around without changing what anyone's hand does.
"""

import pytest
from landmarks import (
    both_palms,
    crossed_fingers,
    fist,
    flat,
    point,
    shaka,
    two_finger,
)

from fingerino import config, gesture_detector
from fingerino.actions import BUILTIN_ACTIONS, DEFAULT_BINDINGS, Action, Registry
from fingerino.gesture_detector import GestureEngine, GestureOutput

FPS = 30
DT = 1 / FPS


def run(engine, frames, start=0.0):
    """Feed ``frames`` (a list of hand-lists) one per tick; return outputs."""
    return [engine.update(hands, start + i * DT) for i, hands in enumerate(frames)]


def steady(hands, seconds):
    return [hands] * round(seconds * FPS)


def all_signs(outs):
    return [s for o in outs for s in o.signs]


# ---------------------------------------------------------------------------
# The synthetic hands read as the postures they are meant to be
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("angle", [0, 30, -45, 90, 180])
def test_fixtures_classify_whichever_way_the_hand_is_turned(angle):
    gd = gesture_detector
    assert gd.is_shaka(shaka(angle=angle))
    assert gd.is_pointing(point(angle=angle))
    assert gd.is_two_finger(two_finger(angle=angle))
    assert gd.is_flat_hand(flat(angle=angle))
    assert gd.is_fist(fist(angle=angle))
    assert not gd.is_shaka(flat(angle=angle))
    assert not gd.is_pointing(two_finger(angle=angle))


# ---------------------------------------------------------------------------
# Signs
# ---------------------------------------------------------------------------

def test_shaka_emits_its_sign_once_after_the_hold():
    engine = GestureEngine()
    outs = run(engine, steady([shaka()], 1.0))
    fired = [i for i, o in enumerate(outs) if o.signs]
    assert len(fired) == 1
    assert outs[fired[0]].signs == ["shaka"]
    assert fired[0] * DT >= config.SHAKA_HOLD_S
    assert all(o.mode == "shaka" and o.pending_sign == "shaka" for o in outs)


def test_a_brief_shaka_emits_nothing():
    engine = GestureEngine()
    frames = steady([shaka()], config.SHAKA_HOLD_S * 0.6) + steady([fist()], 0.5)
    assert all_signs(run(engine, frames)) == []


def test_shaka_respects_its_cooldown_then_fires_again():
    engine = GestureEngine()
    gap = steady([fist()], 0.2)
    first = steady([shaka()], 0.5) + gap + steady([shaka()], 0.5)
    assert all_signs(run(engine, first)).count("shaka") == 1      # inside cooldown

    engine = GestureEngine()
    later = steady([shaka()], 0.5) + steady([fist()], config.SHAKA_COOLDOWN_S) \
        + steady([shaka()], 0.5)
    assert all_signs(run(engine, later)).count("shaka") == 2


def _swipe(dx, dy, seconds=0.3):
    n = int(seconds * FPS)
    return [[flat(x=0.5 + dx * i / n, y=0.5 + dy * i / n)] for i in range(n + 1)]


@pytest.mark.parametrize(("dx", "dy", "sign"), [
    (0, 0.3, "flat_down"),
    (0, -0.3, "flat_up"),
    (-0.3, 0, "flat_left"),
    (0.3, 0, "flat_right"),
])
def test_flat_swipes_emit_their_direction(dx, dy, sign):
    outs = run(GestureEngine(), _swipe(dx, dy))
    assert all_signs(outs) == [sign]
    assert all(o.mode == "flat" for o in outs)


def test_a_small_flat_movement_is_not_a_swipe():
    assert all_signs(run(GestureEngine(), _swipe(0, 0.1))) == []


def test_swipes_respect_their_cooldown():
    frames = _swipe(0, 0.3) + _swipe(0, -0.3)        # straight back up
    assert all_signs(run(GestureEngine(), frames)) == ["flat_down"]


# ---------------------------------------------------------------------------
# Pointer: move, click, drag, scroll
# ---------------------------------------------------------------------------

def test_a_relaxed_hand_moves_and_never_clicks():
    outs = run(GestureEngine(), steady([fist()], 1.0))
    assert all(o.mode == "move" for o in outs)
    assert not any(o.click or o.press or o.release or o.signs for o in outs)


def test_short_point_clicks():
    frames = steady([fist()], 0.1) + steady([point()], 0.2) + steady([fist()], 0.3)
    outs = run(GestureEngine(), frames)
    assert sum(o.click for o in outs) == 1
    assert not any(o.press for o in outs)


def test_held_point_drags_and_releases_when_the_hand_leaves():
    frames = steady([fist()], 0.1) + steady([point()], config.DRAG_HOLD_S + 0.2) \
        + steady([], config.DRAG_RELEASE_GRACE_S + 0.2)
    outs = run(GestureEngine(), frames)
    assert sum(o.press for o in outs) == 1
    assert sum(o.release for o in outs) == 1
    assert not outs[-1].dragging


def test_switching_to_a_sign_mid_drag_releases_the_button():
    frames = steady([fist()], 0.1) + steady([point()], config.DRAG_HOLD_S + 0.2) \
        + steady([shaka()], 0.5)
    outs = run(GestureEngine(), frames)
    assert sum(o.press for o in outs) == 1
    assert sum(o.release for o in outs) == 1


def test_two_fingers_scroll_with_vertical_motion():
    n = 15
    frames = [[two_finger(y=0.4 + 0.2 * i / n)] for i in range(n + 1)]   # moving down
    outs = run(GestureEngine(), frames)
    assert all(o.mode == "scroll" for o in outs)
    steps = sum(o.scroll_steps for o in outs)
    assert steps < 0 if not config.SCROLL_INVERT else steps > 0
    assert not any(o.signs for o in outs)


# ---------------------------------------------------------------------------
# Session controls: Hold and Exit stay wired in, never routed as signs
# ---------------------------------------------------------------------------

def test_both_palms_held_toggle_hold_once_and_never_swipe():
    outs = run(GestureEngine(), steady(both_palms(), config.HOLD_TOGGLE_S + 0.5))
    assert sum(o.hold_toggle for o in outs) == 1
    assert all(o.mode == "hold" for o in outs)
    assert all_signs(outs) == []


def test_crossed_fingers_exit_after_the_hold():
    outs = run(GestureEngine(), steady([crossed_fingers()], config.EXIT_HOLD_S + 0.2))
    # The first crossed frame starts the clock at zero progress; from the
    # next frame on it is Exit.
    assert all(o.mode == "exit" for o in outs[1:])
    first = next(i for i, o in enumerate(outs) if o.exit)
    assert first * DT >= config.EXIT_HOLD_S - DT
    assert all_signs(outs) == []


def test_a_brief_cross_does_not_exit():
    frames = steady([crossed_fingers()], config.EXIT_HOLD_S / 2) + steady([fist()], 0.3)
    assert not any(o.exit for o in run(GestureEngine(), frames))


# ---------------------------------------------------------------------------
# Registry: which action a sign runs, and when it may
# ---------------------------------------------------------------------------

def _out(*signs, pending=None):
    return GestureOutput(mode="flat", mode_label="Flat", signs=list(signs),
                         pending_sign=pending)


def test_default_bindings_are_todays_behaviour():
    reg = Registry()
    assert {s: reg.action_for(s).id for s in DEFAULT_BINDINGS} == {
        "flat_down": "minimize_all",
        "flat_up": "restore_all",
        "flat_left": "switch_window",
        "shaka": "open_ai_chat",
    }
    assert reg.action_for("flat_right") is None


def test_every_bound_sign_is_a_sign_the_detector_emits():
    assert set(DEFAULT_BINDINGS) <= set(gesture_detector.BUILTIN_SIGNS)
    assert set(DEFAULT_BINDINGS.values()) <= set(BUILTIN_ACTIONS)


def test_every_home_toggle_for_a_sign_names_a_real_sign():
    # The per-sign switches in Home are keyed by sign id; a typo would leave
    # a switch that silently controls nothing.
    home = {icon for icon, _ in config.GESTURE_TUTORIAL}
    assert set(DEFAULT_BINDINGS) <= home


@pytest.mark.parametrize(("sign", "label", "toast"), [
    ("flat_down", "Minimize", "Minimized"),
    ("flat_up", "Restore", "Restored"),
    ("flat_left", "Switch", "Switch window"),
    ("shaka", "New chat", "New chat"),
])
def test_resolve_fires_the_bound_action_with_todays_labels(sign, label, toast):
    out = _out(sign)
    fired = Registry().resolve(out, lambda s: True)
    assert [a.toast for a in fired] == [toast]
    assert out.mode_label == label


def test_a_switched_off_sign_is_labelled_but_does_nothing():
    out = _out("flat_down")
    assert Registry().resolve(out, lambda s: s != "flat_down") == []
    assert out.mode_label == "Minimize"


def test_paused_fires_nothing():
    for sign in DEFAULT_BINDINGS:
        assert Registry().resolve(_out(sign), lambda s: False) == []


def test_an_unbound_sign_does_nothing():
    out = _out("flat_right")
    assert Registry().resolve(out, lambda s: True) == []
    assert out.mode_label == "Flat"


def test_a_held_sign_is_named_by_its_action():
    out = GestureOutput(mode="shaka", mode_label="Shaka", pending_sign="shaka")
    Registry().resolve(out, lambda s: True)
    assert out.mode_label == "New chat"


def test_rebinding_a_sign_changes_only_what_it_does():
    music = Action("play_music", "Music", "Playing")
    reg = Registry(bindings={**DEFAULT_BINDINGS, "shaka": "play_music"},
                   actions={**BUILTIN_ACTIONS, "play_music": music})
    assert reg.resolve(_out("shaka"), lambda s: True) == [music]
    assert reg.action_for("flat_down").id == "minimize_all"


def test_system_actions_implements_every_builtin_action():
    system_actions = pytest.importorskip("fingerino.system_actions")
    assert set(BUILTIN_ACTIONS) <= set(system_actions.BUILTIN)

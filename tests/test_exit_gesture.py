"""Exit is crossed index and middle fingers: one hand, any turn, held briefly.

Camera-free: synthetic hands. The thresholds live in config.EXIT_CROSS_RATIO
and need checking against a real camera.
"""

import random

import pytest
from landmarks import (
    both_palms,
    crossed_fingers,
    fist,
    flat,
    jitter,
    mirrored,
    peace,
    point,
    shaka,
    two_finger,
)

from fingerino import config
from fingerino.gesture_detector import GestureEngine, is_crossed_fingers

FPS = 30


def run(engine, frames):
    return [engine.update(h, i / FPS) for i, h in enumerate(frames)]


@pytest.mark.parametrize("angle", [0, 25, -25, 60])
def test_crossed_fingers_are_recognised_however_the_hand_is_turned(angle):
    assert is_crossed_fingers(crossed_fingers(angle=angle))
    assert is_crossed_fingers(mirrored(crossed_fingers(angle=angle)))


@pytest.mark.parametrize("make", [peace, two_finger, point, fist, flat, shaka])
def test_other_postures_are_not_crossed_fingers(make):
    assert not is_crossed_fingers(make())


def test_crossed_fingers_need_the_other_two_folded():
    from landmarks import hand
    assert not is_crossed_fingers(hand(index=True, middle=True, ring=True, cross=True))


def test_crossed_fingers_survive_tracker_jitter():
    rng = random.Random(3)
    hits = sum(is_crossed_fingers(jitter(crossed_fingers(), rng)) for _ in range(200))
    assert hits >= 195


def test_a_peace_sign_never_reads_as_crossed_even_with_jitter():
    rng = random.Random(4)
    assert not any(is_crossed_fingers(jitter(peace(), rng)) for _ in range(500))


def test_holding_crossed_fingers_exits_and_a_peace_sign_does_not():
    held = run(GestureEngine(cursor=True), [[crossed_fingers()]] * round(
        (config.EXIT_HOLD_S + 0.3) * FPS))
    assert any(o.exit for o in held)
    peace_held = run(GestureEngine(cursor=True), [[peace()]] * (3 * FPS))
    assert not any(o.exit for o in peace_held)


def test_exit_works_with_one_hand_in_view_or_two():
    frames = [[crossed_fingers(x=0.3), flat(x=0.7)]] * round((config.EXIT_HOLD_S + 0.3) * FPS)
    assert any(o.exit for o in run(GestureEngine(), frames))


def test_two_palms_are_still_hold_and_do_not_exit():
    outs = run(GestureEngine(), [both_palms()] * round((config.HOLD_TOGGLE_S + 0.5) * FPS))
    assert not any(o.exit for o in outs)
    assert sum(o.hold_toggle for o in outs) == 1


def test_a_recording_of_crossed_fingers_is_flagged():
    import random as _r

    from landmarks import recording

    from fingerino import signs
    rec = signs.Recorder(0.0, config.SIGN_RECORD_S, False)
    for lms in recording(crossed_fingers, _r.Random(1), n=60):
        rec.add(lms, "Right")
    assert "crossed fingers" in rec.result().builtin

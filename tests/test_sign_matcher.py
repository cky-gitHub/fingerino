"""Matching the user's own signs: landmark fixtures in, sign ids out.

Every hand here is put into real 16:9 frame coordinates first (``in_frame``),
the way MediaPipe reports them, so the aspect correction is exercised too.
Recordings drift in position, size and angle and carry tracker-like noise.
"""

import math
import random

import pytest
from landmarks import (
    fist,
    flat,
    hand,
    mirrored,
    peace,
    point,
    recording,
    relaxed,
    shaka,
    thumbs_down,
    thumbs_up,
)

from fingerino import config, signs
from fingerino.gesture_detector import GestureEngine
from fingerino.sign_matcher import (
    Matcher,
    Sign,
    SignHold,
    angle_between,
    canonical,
    features,
)

ASPECT = config.CAMERA_WIDTH / config.CAMERA_HEIGHT


def in_frame(lms):
    """Square fixture coordinates -> a 16:9 frame's normalised coordinates."""
    return [(0.5 + (x - 0.5) / ASPECT, y, z / ASPECT) for x, y, z in lms]


def record(make, seed, **kw):
    rng = random.Random(seed)
    return [canonical(in_frame(lms)) for lms in recording(make, rng, **kw)]


@pytest.fixture(scope="module")
def library():
    return [
        Sign("up", "Thumbs up", record(thumbs_up, 1)),
        Sign("down", "Thumbs down", record(thumbs_down, 2)),
        Sign("peace", "Peace", record(peace, 3)),
        Sign("point", "Point", record(point, 4)),
    ]


@pytest.fixture(scope="module")
def matcher(library):
    return Matcher(library)


def live(make, seed=99, **kw):
    """One live frame of a sign, with its own drift and noise."""
    return in_frame(recording(make, random.Random(seed), n=1, **kw)[0])


def matched(matcher, lms, handedness=None):
    m = matcher.match(lms, handedness)
    return None if m is None else m.sign_id


# ---------------------------------------------------------------------------
# Normalising
# ---------------------------------------------------------------------------

def test_canonical_ignores_position_and_size():
    a = canonical(in_frame(peace(x=0.3, y=0.4, size=0.08)))
    b = canonical(in_frame(peace(x=0.7, y=0.6, size=0.14)))
    assert max(abs(p - q) for pa, pb in zip(a, b, strict=True)
               for p, q in zip(pa, pb, strict=True)) < 1e-9


def test_canonical_corrects_the_frame_aspect():
    # A square-unit hand squeezed into a 16:9 frame comes back out square.
    square = canonical(peace(), aspect=1.0)
    framed = canonical(in_frame(peace()))
    assert max(abs(p - q) for pa, pb in zip(square, framed, strict=True)
               for p, q in zip(pa, pb, strict=True)) < 1e-9


def test_a_left_hand_canonicalises_onto_the_right():
    right = canonical(in_frame(thumbs_up()), "Right")
    left = canonical(in_frame(mirrored(thumbs_up())), "Left")
    assert max(abs(p - q) for pa, pb in zip(right, left, strict=True)
               for p, q in zip(pa, pb, strict=True)) < 1e-9


def test_orientation_is_kept_apart_from_shape():
    up, down = features(canonical(thumbs_up())), features(canonical(thumbs_down()))
    assert angle_between(up.angle, down.angle) == pytest.approx(180, abs=1e-6)
    same_shape = sum((a - b) ** 2 for a, b in zip(up.shape, down.shape, strict=True))
    assert same_shape < 1e-9


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

def test_thumbs_up_and_thumbs_down_are_told_apart(matcher):
    for seed in range(20):
        assert matched(matcher, live(thumbs_up, seed)) == "up"
        assert matched(matcher, live(thumbs_down, seed)) == "down"


def test_each_recorded_sign_matches_itself(matcher):
    for seed in range(20):
        assert matched(matcher, live(peace, seed)) == "peace"
        assert matched(matcher, live(point, seed)) == "point"


@pytest.mark.parametrize("idle", [
    lambda **kw: relaxed(**kw),
    lambda **kw: relaxed(angle=30, **kw),
    lambda **kw: relaxed(angle=-40, **kw),
    lambda **kw: fist(**kw),
    lambda **kw: flat(**kw),
    lambda **kw: shaka(**kw),
    lambda **kw: hand(index=True, middle=True, ring=True, **kw),
])
def test_idle_and_other_hands_are_ignored(matcher, idle):
    for seed in range(20):
        assert matched(matcher, live(idle, seed)) is None


def test_either_hand_works(matcher):
    left = in_frame(mirrored(live(thumbs_up)))
    left = mirrored(live(thumbs_up))
    assert matched(matcher, left, "Left") == "up"
    # Without handedness both mirrors are tried.
    assert matched(matcher, left) == "up"
    assert matched(matcher, mirrored(live(thumbs_down)), "Left") == "down"


def test_a_tilted_sign_still_matches_but_a_turned_one_does_not(matcher):
    assert matched(matcher, in_frame(peace(angle=20))) == "peace"
    assert matched(matcher, in_frame(peace(angle=-20))) == "peace"
    assert matched(matcher, in_frame(peace(angle=90))) is None


def test_two_signs_that_are_too_alike_give_no_answer():
    near_twins = Matcher([Sign("a", "A", record(peace, 1)), Sign("b", "B", record(peace, 2))])
    assert matched(near_twins, live(peace)) is None


def test_disabled_and_empty_signs_never_match():
    m = Matcher([Sign("p", "P", record(peace, 1), enabled=False), Sign("e", "E", [])])
    assert not m
    assert matched(m, live(peace)) is None


# ---------------------------------------------------------------------------
# Holding
# ---------------------------------------------------------------------------

def feed(hold, seq, dt=1 / 30, start=0.0):
    return [hold.update(s, start + i * dt) for i, s in enumerate(seq)]


def frames(seconds, value):
    return [value] * round(seconds * 30)


def test_a_sign_fires_once_after_the_hold():
    outs = feed(SignHold(), frames(2.0, "up"))
    fired = [i for i, (f, _, _) in enumerate(outs) if f]
    assert len(fired) == 1
    assert fired[0] / 30 >= config.SIGN_HOLD_S - 1 / 30
    assert all(p == "up" for _, p, _ in outs[: fired[0]])


def test_a_brief_sign_does_not_fire():
    outs = feed(SignHold(), frames(config.SIGN_HOLD_S * 0.6, "up") + frames(0.5, None))
    assert not any(f for f, _, _ in outs)


def test_a_dropped_frame_does_not_restart_the_hold():
    seq = frames(config.SIGN_HOLD_S * 0.6, "up") + [None] + frames(0.5, "up")
    outs = feed(SignHold(), seq)
    first = next(i for i, (f, _, _) in enumerate(outs) if f)
    assert first / 30 < config.SIGN_HOLD_S + 0.1


def test_switching_sign_restarts_the_hold():
    seq = frames(config.SIGN_HOLD_S * 0.7, "up") + frames(config.SIGN_HOLD_S * 0.7, "down")
    assert not any(f for f, _, _ in feed(SignHold(), seq))


def test_firing_again_needs_the_hand_to_leave_the_sign():
    seq = frames(3.0, "up") + frames(0.5, None) + frames(1.0, "up")
    fired = [f for f, _, _ in feed(SignHold(), seq) if f]
    assert fired == ["up", "up"]


# ---------------------------------------------------------------------------
# In the gesture engine
# ---------------------------------------------------------------------------

def run(engine, frames_, handed=None):
    return [engine.update(h, i / 30, handed) for i, h in enumerate(frames_)]


def test_engine_emits_a_custom_sign_and_names_it(library):
    engine = GestureEngine(cursor=False)
    engine.matcher = Matcher(library)
    engine.sign_names = {s.id: s.name for s in library}
    outs = run(engine, [[in_frame(thumbs_up())]] * 40)
    assert [s for o in outs for s in o.signs] == ["up"]
    assert outs[5].mode == "sign" and outs[5].mode_label == "Thumbs up"
    assert 0 < outs[5].sign_progress < 1 and outs[5].pending_sign == "up"


def test_builtins_keep_their_poses(library):
    # A shaka stays the shaka even if a recorded sign resembled it.
    engine = GestureEngine(cursor=False)
    engine.matcher = Matcher([*library, Sign("my-shaka", "Mine", record(shaka, 5))])
    signs_seen = [s for o in run(engine, [[in_frame(shaka())]] * 40) for s in o.signs]
    assert signs_seen == ["shaka"]


def test_with_the_cursor_on_pointing_clicks_rather_than_signs(library):
    engine = GestureEngine(cursor=True)
    engine.matcher = Matcher(library)
    seq = [[in_frame(fist())]] * 3 + [[in_frame(point())]] * 40
    outs = run(engine, seq)
    assert not any(o.signs for o in outs)
    assert any(o.press for o in outs)
    engine = GestureEngine(cursor=False)
    engine.matcher = Matcher(library)
    assert [s for o in run(engine, seq) for s in o.signs] == ["point"]


def test_idle_hands_never_fire_in_the_engine(library):
    engine = GestureEngine(cursor=False)
    engine.matcher = Matcher(library)
    rng = random.Random(7)
    seq = [[in_frame(recording(relaxed, rng, n=1, angle=rng.uniform(-60, 60))[0])]
           for _ in range(300)]
    assert not any(o.signs for o in run(engine, seq))


# ---------------------------------------------------------------------------
# signs.json
# ---------------------------------------------------------------------------

def test_library_round_trip(tmp_path):
    lib = signs.Library()
    sign = lib.add("  Thumbs up  ", record(thumbs_up, 1))
    assert sign.name == "Thumbs up"
    assert signs.save(str(tmp_path), lib)
    back = signs.load(str(tmp_path))
    assert [s.name for s in back.signs] == ["Thumbs up"]
    assert matched(back.matcher, live(thumbs_up)) == sign.id


def test_samples_are_thinned_to_the_limit():
    lib = signs.Library()
    sign = lib.add("x", record(peace, 1, n=200))
    assert len(sign.samples) == signs.MAX_SAMPLES


def test_library_edits_swap_the_matcher():
    lib = signs.Library()
    before = lib.matcher
    sign = lib.add("x", record(peace, 1))
    assert lib.matcher is not before and lib.matcher
    lib.set_enabled(sign.id, False)
    assert not lib.matcher
    lib.set_enabled(sign.id, True)
    lib.rename(sign.id, "Peace")
    assert lib.name(sign.id) == "Peace"
    lib.delete(sign.id)
    assert lib.signs == [] and not lib.matcher


def test_bad_signs_are_skipped(tmp_path):
    good = signs.to_json([Sign("s1", "Good", record(peace, 1, n=3))])["signs"][0]
    data = {"signs": [
        good,
        {**good, "id": "s1"},                         # duplicate id
        {**good, "id": "s2", "name": "  "},           # no name
        {**good, "id": "s3", "samples": [[[0, 0]] * 21]},
        {**good, "id": "s4", "samples": [[[0, 0, math.nan]] * 21]},
        {**good, "id": "s5", "samples": "lots"},
        "nonsense",
    ]}
    assert [s.id for s in signs.from_json(data)] == ["s1"]
    assert signs.from_json(None) == [] and signs.from_json({"signs": 3}) == []
    (tmp_path / signs.FILENAME).write_text("{oops", encoding="utf-8")
    assert signs.load(str(tmp_path)).signs == []

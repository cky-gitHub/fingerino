"""The free version's sign limit, enforced in signs.Library (camera-free).

Past the limit a sign is *locked*: kept and still switched on in signs.json,
but left out of the matcher, so it can't fire however the file is edited.
"""

from __future__ import annotations

import random

from landmarks import peace, recording, shaka, thumbs_down, thumbs_up

from fingerino import signs
from fingerino.sign_matcher import canonical


def _samples(make, seed: int = 1):
    return [canonical(lms, "Right") for lms in recording(make, random.Random(seed))]


def _library(limit=None):
    lib = signs.Library(limit=limit)
    a = lib.add("Up", _samples(thumbs_up))
    b = lib.add("Down", _samples(thumbs_down))
    c = lib.add("Peace", _samples(peace))
    return lib, a, b, c


def _fires(lib, make) -> str:
    match = lib.matcher.match(make(), "Right")
    return lib.name(match.sign_id) if match else ""


def test_no_limit_means_every_switched_on_sign():
    lib, a, b, c = _library()
    assert [s.id for s in lib.active()] == [a.id, b.id, c.id]
    assert not any(lib.locked(s.id) for s in (a, b, c))
    assert not lib.at_limit()


def test_past_the_limit_signs_are_kept_but_never_fire():
    lib, a, b, c = _library(limit=1)
    assert [s.id for s in lib.active()] == [a.id]
    assert [lib.locked(s.id) for s in (a, b, c)] == [False, True, True]
    assert lib.at_limit()
    assert _fires(lib, thumbs_up) == "Up"
    assert _fires(lib, thumbs_down) == ""
    assert _fires(lib, peace) == ""
    # Nothing about them changes in the file: unlocking brings them back.
    stored = signs.to_json(lib.signs)["signs"]
    assert [s["enabled"] for s in stored] == [True, True, True]


def test_unlocking_brings_every_sign_back():
    lib, a, b, c = _library(limit=1)
    lib.set_limit(30)
    assert not any(lib.locked(s.id) for s in (a, b, c))
    assert _fires(lib, thumbs_down) == "Down"
    assert not lib.at_limit()


def test_switched_off_signs_dont_count():
    lib, a, b, _ = _library(limit=1)
    lib.set_enabled(a.id, False)
    assert [s.id for s in lib.active()] == [b.id]
    assert not lib.locked(a.id)                  # off, not locked
    assert _fires(lib, thumbs_down) == "Down"


def test_use_this_one_instead():
    lib, a, b, c = _library(limit=1)
    lib.move_to_front(c.id)
    assert [s.id for s in lib.active()] == [c.id]
    assert lib.locked(a.id) and lib.locked(b.id)
    assert _fires(lib, peace) == "Peace"
    assert _fires(lib, thumbs_up) == ""
    # The order is what's saved, so the choice survives a restart.
    reloaded = signs.Library(signs.from_json(signs.to_json(lib.signs)), limit=1)
    assert [s.id for s in reloaded.active()] == [c.id]


def test_switching_a_sign_on_at_the_limit_swaps_it_in():
    lib, a, b, _ = _library(limit=1)
    lib.set_enabled(b.id, False)
    lib.set_enabled(b.id, True)
    assert [s.id for s in lib.active()] == [b.id]
    assert lib.locked(a.id)


def test_a_new_sign_at_the_limit_is_saved_locked():
    lib, _, _, _ = _library(limit=1)
    new = lib.add("Shaka-ish", _samples(shaka, seed=3))
    assert lib.get(new.id) is not None and lib.locked(new.id)


def test_locked_signs_carry_no_warning():
    lib = signs.Library(limit=1)
    lib.add("Up", _samples(thumbs_up, seed=1))
    twin = lib.add("Up again", _samples(thumbs_up, seed=2))
    assert lib.locked(twin.id)
    assert lib.warning(twin.id, cursor=False) == ""
    lib.set_limit(None)
    assert "Looks a lot like" in lib.warning(twin.id, cursor=False)


def test_a_zero_limit_locks_everything():
    lib, a, _, _ = _library(limit=0)
    assert lib.active() == [] and lib.locked(a.id)
    assert not lib.matcher

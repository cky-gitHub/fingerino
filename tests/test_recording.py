"""Recording a new sign: the recorder, the session, and Home's flow.

Camera-free like the rest: the recorder is fed synthetic hands, the session
runs in sessionkit's scripted world, and Home's flow is driven through the
same bridge the QML calls.
"""

import json
import random

import pytest
from landmarks import flat, peace, point, recording, shaka, thumbs_down, thumbs_up

from fingerino import config, signs
from fingerino.sign_matcher import canonical


def fed(make, *, cursor=False, n=60, missing=0, seed=1, **kw):
    rec = signs.Recorder(0.0, config.SIGN_RECORD_S, cursor)
    rng = random.Random(seed)
    for lms in recording(make, rng, n=n, **kw):
        rec.add(lms, "Right")
    for _ in range(missing):
        rec.add(None, None)
    return rec.result()


def test_a_good_recording_keeps_every_sample():
    result = fed(thumbs_up)
    assert result.error == "" and result.builtin == ""
    assert len(result.samples) == result.seen == 60


def test_a_hand_mostly_out_of_view_is_refused():
    assert fed(thumbs_up, n=20, missing=40).error
    assert fed(thumbs_up, n=5).error                     # too few to learn from


@pytest.mark.parametrize(("make", "cursor", "looks_like"), [
    (shaka, False, "the shaka"),
    (flat, False, "an open palm"),
    (point, True, "pointing"),
    (peace, True, "two fingers"),
])
def test_signs_the_builtins_would_swallow_are_flagged(make, cursor, looks_like):
    assert looks_like in fed(make, cursor=cursor).builtin


def test_pointing_and_two_fingers_are_free_with_the_cursor_off():
    assert fed(point, cursor=False).builtin == ""
    assert fed(peace, cursor=False).builtin == ""


def test_progress_and_done():
    rec = signs.Recorder(10.0, 3.0, False)
    assert rec.progress(10.0) == 0.0 and rec.progress(11.5) == 0.5
    assert not rec.done(12.9) and rec.done(13.0)


def test_a_recording_close_to_an_existing_sign_names_it():
    lib = signs.Library()
    lib.add("Thumbs up", fed(thumbs_up, seed=1).samples)
    assert signs.similar_sign(lib, fed(thumbs_up, seed=2).samples) == "Thumbs up"
    assert signs.similar_sign(lib, fed(thumbs_down, seed=3).samples) == ""
    assert signs.similar_sign(lib, fed(peace, seed=4).samples) == ""


# ---------------------------------------------------------------------------
# In a session
# ---------------------------------------------------------------------------

def test_recording_in_a_session_and_then_using_the_sign(monkeypatch):
    pytest.importorskip("cv2")
    pytest.importorskip("pynput")
    import sessionkit
    from landmarks import fist
    from sessionkit import steady

    from fingerino.actions import Registry, make_action

    def start_at_frame_10(world, session):
        if world.i == 10:
            session.start_recording(config.SIGN_RECORD_S)

    rng = random.Random(5)
    showing = [[h] for h in recording(thumbs_up, rng, n=150)]
    world = sessionkit.run(monkeypatch, steady([fist()], 0.4) + showing,
                           hook=start_at_frame_10)
    (rec,) = world.recordings
    assert rec.error == "" and len(rec.samples) >= 80
    assert world.actions == []                    # nothing fires while recording

    library = signs.Library()
    sign = library.add("Thumbs up", rec.samples)
    registry = Registry()
    registry.bind(sign.id, make_action("media", "play_pause"))
    world = sessionkit.run(monkeypatch, steady([fist()], 0.3) + steady([thumbs_up()], 1.5),
                           registry=registry, library=library)
    assert world.signs_fired == [sign.id]
    assert len(world.actions) == 1
    assert "Play / pause" in world.toasts


def test_recording_does_not_fire_the_shaka(monkeypatch):
    pytest.importorskip("cv2")
    pytest.importorskip("pynput")
    import sessionkit
    from sessionkit import steady

    def start(world, session):
        if world.i == 0:
            session.start_recording(config.SIGN_RECORD_S)

    world = sessionkit.run(monkeypatch, steady([shaka()], config.SIGN_RECORD_S + 1.0),
                           hook=start)
    assert world.actions == []
    assert "the shaka" in world.recordings[0].builtin


# ---------------------------------------------------------------------------
# Home's flow, through the bridge
# ---------------------------------------------------------------------------

@pytest.fixture
def home(tmp_path):
    pytest.importorskip("PySide6")
    from fingerino import settings, shell
    a = shell.Shell(settings.Settings(), str(tmp_path), None, tray=False, hotkey=False)
    yield a, tmp_path
    a.close()


class FakeSession:
    def __init__(self):
        self.recordings = []

    def start_recording(self, seconds):
        self.recordings.append(seconds)

    def stop(self):
        pass


def record_through_home(a, make, seed=1):
    a.session = FakeSession()
    a.bridge.captureSign()
    assert a.bridge.property("recordState") == "capturing"
    assert a.session.recordings == [config.SIGN_RECORD_S]
    a._on_record(0.5, None)
    assert a.bridge.property("recordProgress") == 0.5
    a._on_record(1.0, fed(make, seed=seed))
    a.session = None


def test_record_name_bind_and_delete(home):
    a, data = home
    record_through_home(a, thumbs_up)
    assert a.bridge.property("recordState") == "review"
    assert a.bridge.property("recordWarning") == ""
    assert a.bridge.saveSign("  ")["error"]
    sign_id = a.bridge.saveSign("Thumbs up")["id"]
    assert a.bridge.property("recordState") == "idle"

    stored = json.loads((data / signs.FILENAME).read_text(encoding="utf-8"))
    assert [s["name"] for s in stored["signs"]] == ["Thumbs up"]
    assert len(stored["signs"][0]["samples"][0]) == 21

    assert a.bridge.setAction(sign_id, "open", "https://open.spotify.com/x", "") == ""
    (card,) = a.bridge.property("customSigns")
    assert card == {"id": sign_id, "name": "Thumbs up", "enabled": True,
                    "action": "Open spotify.com"}
    # The matcher the session reads already knows it.
    assert a.library.matcher.match(thumbs_up(), "Right").sign_id == sign_id

    a.bridge.renameSign(sign_id, "Music")
    a.bridge.setSignEnabled(sign_id, False)
    assert a.bridge.property("customSigns")[0]["name"] == "Music"
    assert not a.library.matcher

    a.bridge.deleteSign(sign_id)
    assert a.bridge.property("customSigns") == []
    assert sign_id not in a.registry.bindings
    stored = json.loads((data / "actions.json").read_text(encoding="utf-8"))
    assert sign_id not in stored["bindings"] and stored["actions"] == []


def test_recording_a_near_twin_warns(home):
    a, _ = home
    record_through_home(a, thumbs_up, seed=1)
    a.bridge.saveSign("Thumbs up")
    record_through_home(a, thumbs_up, seed=2)
    assert "Thumbs up" in a.bridge.property("recordWarning")


def test_recording_a_shaka_warns(home):
    a, _ = home
    record_through_home(a, shaka)
    assert "shaka" in a.bridge.property("recordWarning")


def test_recording_without_tracking_fails_politely(home):
    a, _ = home
    a.bridge.captureSign()
    assert a.bridge.property("recordState") == "failed"
    assert "Start" in a.bridge.property("recordMessage")


def test_a_bad_recording_shows_why(home):
    a, _ = home
    a.session = FakeSession()
    a.bridge.captureSign()
    a._on_record(1.0, fed(thumbs_up, n=3))
    assert a.bridge.property("recordState") == "failed"
    assert a.bridge.saveSign("x")["error"]


def test_signs_survive_a_restart(home, tmp_path):
    a, data = home
    record_through_home(a, peace)
    sign_id = a.bridge.saveSign("Peace")["id"]
    a.bridge.setAction(sign_id, "media", "next", "")
    from fingerino import actions
    assert signs.load(str(data)).signs[0].name == "Peace"
    assert actions.load(str(data)).action_for(sign_id).target == "next"


def test_sign_fired_reaches_home(home):
    a, _ = home
    seen = []
    a.bridge.signFired.connect(seen.append)
    a._on_sign("sign-123")
    assert seen == ["sign-123"]


def test_canonical_samples_are_what_gets_stored():
    rec = fed(thumbs_up, n=20)
    assert rec.samples[0] == canonical(recording(thumbs_up, random.Random(1), n=20)[0],
                                       "Right")

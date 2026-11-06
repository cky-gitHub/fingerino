"""'Try it' in the action editor: the sign being edited runs the unsaved
action, and nothing else acts, until the editor closes. Camera-free."""

import pytest
from landmarks import flat, point, shaka

from fingerino import config
from fingerino.actions import Registry, make_action


def _session_deps():
    pytest.importorskip("cv2")
    pytest.importorskip("pynput")


def test_during_a_trial_only_the_tried_sign_acts_and_with_the_new_action(monkeypatch):
    _session_deps()
    import sessionkit
    from sessionkit import steady

    from fingerino import settings
    trial = make_action("media", "play_pause")
    registry = Registry()          # the shaka is still bound to its saved action

    def arm(world, session):
        if world.i == 0:
            session.set_trial(("shaka", trial))

    n = 12
    swipe = [[flat(x=0.5, y=0.3 + 0.4 * i / n)] for i in range(n + 1)]
    frames = steady([shaka()], 1.0) + steady([], 0.5) + swipe + steady([point()], 1.0)
    world = sessionkit.run(monkeypatch, frames, settings.Settings(cursor=True),
                           hook=arm, registry=registry)
    assert world.actions == [trial.id]                 # the trial, not open_ai_chat
    assert world.signs_fired == ["shaka"]              # the editor hears it
    assert not [c for c in world.cursor_calls if c[0] in ("click", "press")]


def test_ending_the_trial_puts_everything_back(monkeypatch):
    _session_deps()
    import sessionkit
    from sessionkit import steady

    trial = make_action("media", "play_pause")

    def arm_then_end(world, session):
        if world.i == 0:
            session.set_trial(("shaka", trial))
        if world.i == 45:
            session.set_trial(None)

    frames = steady([shaka()], 1.0) + steady([], 0.5) + steady([shaka()], 1.0)
    world = sessionkit.run(monkeypatch, frames, hook=arm_then_end)
    assert world.actions == [trial.id, "open_ai_chat"]


def test_exit_still_works_during_a_trial(monkeypatch):
    _session_deps()
    import sessionkit
    from landmarks import crossed_fingers
    from sessionkit import steady

    trial = make_action("media", "play_pause")
    frames = steady([crossed_fingers()], config.EXIT_HOLD_S + 0.3) + steady([shaka()], 2.0)
    world = sessionkit.run(monkeypatch, frames,
                           hook=lambda w, s: s.set_trial(("shaka", trial)))
    assert world.i < len(frames) - 1
    assert world.actions == []


# ---------------------------------------------------------------------------
# Home
# ---------------------------------------------------------------------------

@pytest.fixture
def home(tmp_path):
    pytest.importorskip("PySide6")
    from fingerino import settings, shell
    a = shell.Shell(settings.Settings(), str(tmp_path), None, tray=False, hotkey=False)
    yield a
    a.session = None
    a.close()


class FakeSession:
    def __init__(self):
        self.trials = []

    def set_trial(self, trial):
        self.trials.append(trial)

    def stop(self):
        pass


def test_try_it_arms_the_session_and_closing_ends_it(home):
    a = home
    a.session = FakeSession()
    assert a.bridge.tryAction("shaka", "media", "play_pause", "") == ""
    (sign, action), = a.session.trials
    assert sign == "shaka" and action.target == "play_pause"
    assert a.registry.action_for("shaka").id == "open_ai_chat"   # nothing saved
    a.bridge.endTrial()
    assert a.session.trials[-1] is None and a.trial is None


def test_try_it_reports_a_bad_action_and_arms_nothing(home):
    a = home
    a.session = FakeSession()
    assert a.bridge.tryAction("shaka", "open", "", "")
    assert a.session.trials == [] and a.trial is None


def test_try_it_starts_tracking_when_it_is_off(home, monkeypatch):
    a = home
    started = []
    monkeypatch.setattr(a, "start", lambda: started.append(a.trial))
    assert a.bridge.tryAction("shaka", "media", "next", "") == ""
    assert started and started[0][0] == "shaka"

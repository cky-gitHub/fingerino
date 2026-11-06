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


# ---------------------------------------------------------------------------
# Held from the countdown until the action editor closes -- through the QML
# ---------------------------------------------------------------------------

class HoldSession(FakeSession):
    """Records every hold and trial Home sends, like the real Session."""

    def __init__(self):
        super().__init__()
        self.holds = []

    def hold_gestures(self, on):
        self.holds.append(on)

    def start_recording(self, seconds):
        pass


def _settle(app, ms=700):
    """Let QML transitions (dialog open/close animations) finish."""
    from PySide6.QtCore import QElapsedTimer
    t = QElapsedTimer()
    t.start()
    while t.elapsed() < ms:
        app.processEvents()


def _child(window, name):
    from PySide6.QtCore import QObject
    return window.findChild(QObject, name)


def _button(dialog, text):
    from PySide6.QtCore import QObject
    return next(o for o in dialog.findChildren(QObject) if o.property("text") == text)


def test_gestures_stay_held_from_the_countdown_until_the_editor_closes(home):
    import random

    from landmarks import recording, thumbs_up
    from PySide6.QtCore import QMetaObject, QObject

    from fingerino import config, signs
    a = home
    a.session = session = HoldSession()
    record, editor = _child(a.window, "recordDialog"), _child(a.window, "actionEditor")

    # Start recording: the countdown holds everything.
    QMetaObject.invokeMethod(record, "begin")
    QMetaObject.invokeMethod(record, "startCountdown")
    _settle(a.app, 100)
    assert session.holds[-1] is True
    # The capture finishes (as the session would report it).
    a.capture_sign()
    rec = signs.Recorder(0.0, config.SIGN_RECORD_S, False)
    for lms in recording(thumbs_up, random.Random(1), n=60):
        rec.add(lms, "Right")
    a._on_record(1.0, rec.result())
    field = next(o for o in record.findChildren(QObject)
                 if o.property("placeholderText") == "e.g. Thumbs up")
    field.setProperty("text", "Thumbs up")
    # "Save and choose what it does": the record dialog closes, the editor opens.
    QMetaObject.invokeMethod(_button(record, "Save and choose what it does"), "clicked")
    _settle(a.app)
    assert editor.property("visible") and not record.property("visible")
    assert a.gestures_held
    assert False not in session.holds                  # never let go in between

    # Try it, then Cancel: only now does everything come back.
    sign_id = editor.property("sign")
    assert a.bridge.tryAction(sign_id, "media", "play_pause", "") == ""
    assert session.trials[-1][0] == sign_id
    QMetaObject.invokeMethod(_button(editor, "Cancel"), "clicked")
    _settle(a.app)
    assert session.holds[-1] is False and not a.gestures_held
    assert session.trials[-1] is None


def test_the_editor_holds_gestures_on_its_own_too(home):
    from PySide6.QtCore import Q_ARG, QMetaObject
    a = home
    a.session = session = HoldSession()
    editor = _child(a.window, "actionEditor")
    QMetaObject.invokeMethod(editor, "edit", Q_ARG("QVariant", "shaka"),
                             Q_ARG("QVariant", "When you make the shaka"))
    _settle(a.app, 300)
    assert session.holds == [True]
    QMetaObject.invokeMethod(_button(editor, "Save"), "clicked")
    _settle(a.app)
    assert session.holds[-1] is False


# ---------------------------------------------------------------------------
# The HUD: green pulse on recognition, then a thin green frame
# ---------------------------------------------------------------------------

def _overlay():
    pytest.importorskip("cv2")
    from fingerino import ui_overlay
    return ui_overlay


def _frame():
    import numpy as np
    return np.full((270, 480, 3), 40, dtype=np.uint8)


def test_the_hud_pulses_green_then_keeps_a_thin_frame(monkeypatch):
    ui = _overlay()
    clock = [1000.0]
    monkeypatch.setattr(ui.time, "time", lambda: clock[0])
    o = ui.UIOverlay()
    green = tuple(config.COLOR_TRIAL)

    plain = _frame()
    o._draw_trial(plain, True)                          # armed, not recognised yet
    assert (plain == 40).all()

    o.trial_recognised()
    clock[0] += config.TRIAL_PULSE_S / 2                # the top of the pulse
    mid = _frame()
    o._draw_trial(mid, True)
    assert tuple(mid[0, 0]) == green                    # thick frame at the edge
    assert mid[135, 240][1] > 40 + 20                   # the middle is tinted green

    clock[0] += config.TRIAL_PULSE_S                    # after the pulse
    after = _frame()
    o._draw_trial(after, True)
    assert tuple(after[0, 0]) == green                  # thin frame stays
    assert (after[135, 240] == 40).all()                # no tint any more
    edge = o.s(config.TRIAL_FRAME_PX) * 2
    assert (after[edge + 2, 240] == 40).all()

    ended = _frame()
    o._draw_trial(ended, False)                         # editor closed
    o._draw_trial(ended, True)                          # a new trial starts clean
    assert (ended == 40).all()


def test_the_session_tells_the_hud_about_a_trial_and_its_recognition(monkeypatch):
    _session_deps()
    import sessionkit
    from sessionkit import steady

    from fingerino import engine
    seen, drawn = [], []
    monkeypatch.setattr(engine.UIOverlay, "trial_recognised", lambda self: seen.append(1))
    original = engine.UIOverlay.draw

    def draw(self, frame, **kw):
        drawn.append(kw.get("trial"))
        return original(self, frame, **kw)

    monkeypatch.setattr(engine.UIOverlay, "draw", draw)
    trial = make_action("media", "play_pause")
    sessionkit.run(monkeypatch, steady([shaka()], 1.0),
                   hook=lambda w, s: s.set_trial(("shaka", trial)) if w.i == 0 else None)
    assert seen == [1]
    assert all(drawn[1:])

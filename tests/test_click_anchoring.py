"""Retroactive click anchoring.

Clicking means extending a finger, which reshapes the hand and moves whatever
landmark the cursor rides on. At the ~2.5x gain the control zone applies, a
centimetre of that drift is tens of screen pixels — the size of the button
being aimed at. So the click is delivered where the cursor was *before* the
posture began, not where it ended up by the time the edge fired.
"""

import pytest

from fingerino import config
from fingerino.gesture_detector import DragTrigger


def armed():
    trigger = DragTrigger()
    trigger.update(False, 0.0)
    return trigger


# --------------------------------------------------------------------------
# The trigger reports when the posture began
# --------------------------------------------------------------------------

def test_a_click_carries_the_moment_the_point_began():
    trigger = armed()
    trigger.update(True, 1.00)                       # posture starts here
    trigger.update(True, 1.10)
    trigger.update(False, 1.20)
    edges = trigger.update(False, 1.20 + config.CLICK_RELEASE_GRACE_S + 0.01)

    assert edges.click
    # Not 1.2x — that is where the finger had already relaxed again.
    assert edges.anchor_t == pytest.approx(1.00)


def test_a_press_carries_the_moment_the_point_began():
    trigger = armed()
    trigger.update(True, 2.00)
    edges = trigger.update(True, 2.00 + config.DRAG_HOLD_S + 0.01)

    assert edges.press
    assert edges.anchor_t == pytest.approx(2.00)


def test_a_release_has_no_anchor():
    # A drag ends where the hand actually is; rewinding that would undo the
    # drag the user just performed.
    trigger = armed()
    trigger.update(True, 0.10)
    trigger.update(True, 0.10 + config.DRAG_HOLD_S + 0.01)
    t = 1.0
    trigger.update(False, t)
    edges = trigger.update(False, t + config.DRAG_RELEASE_GRACE_S + 0.01)

    assert edges.release
    assert edges.anchor_t is None


def test_pending_since_tracks_the_commit_window():
    trigger = armed()
    assert trigger.pending_since is None             # nothing pending

    trigger.update(True, 5.00)
    assert trigger.pending_since == pytest.approx(5.00)

    # Once it latches into a drag the user is no longer committing, they are
    # dragging — and the cursor has to start following the hand again.
    trigger.update(True, 5.00 + config.DRAG_HOLD_S + 0.01)
    assert trigger.down
    assert trigger.pending_since is None


def test_a_hand_arriving_mid_point_reports_nothing_pending():
    trigger = DragTrigger()          # never saw the posture absent
    trigger.update(True, 1.0)
    assert trigger.pending_since is None


# --------------------------------------------------------------------------
# The cursor delivers the button there
# --------------------------------------------------------------------------

pytest.importorskip("pynput", exc_type=ImportError,
                    reason="not installed, or no display backend to bind to")

from fingerino.cursor_controller import CursorController


class FakeMouse:
    def __init__(self):
        self.position = (0, 0)
        self.clicks = []
        self.presses = []

    def click(self, button, count):
        self.clicks.append(self.position)

    def press(self, button):
        self.presses.append(self.position)

    def release(self, button):
        pass


@pytest.fixture
def cursor(monkeypatch):
    monkeypatch.setattr("fingerino.cursor_controller.Controller", FakeMouse)
    monkeypatch.setattr("fingerino.cursor_controller._get_screen_size",
                        lambda: (1920, 1080))
    return CursorController()


def _sweep(cursor, start=0.0, frames=20, step=1 / 30):
    """Drive the cursor left to right; return the time of each sample."""
    times = []
    for i in range(frames):
        t = start + i * step
        cursor.update(0.20 + 0.03 * i, 0.5, t)      # x rises, y constant
        times.append(t)
    return times


def test_history_is_recorded_and_bounded(cursor):
    _sweep(cursor, frames=200)
    span = cursor._history[-1][0] - cursor._history[0][0]
    assert span <= config.CURSOR_HISTORY_S + 0.05


def test_a_click_lands_where_the_cursor_was_not_where_it_is(cursor):
    times = _sweep(cursor)
    drifted = cursor.last_screen
    anchor_t = times[-1]

    # Then the hand keeps moving, the way it does while a finger extends.
    for i in range(1, 6):
        cursor.update(0.80, 0.5, anchor_t + i / 30)
    assert cursor.last_screen != drifted            # premise: it moved

    cursor.click(anchor_t=anchor_t)
    landed = cursor._mouse.clicks[-1]
    expected = cursor.anchor_at(anchor_t - config.CLICK_ANCHOR_LOOKBACK_S)
    assert landed == expected
    assert landed != cursor.last_screen or expected == cursor.last_screen


def test_a_press_is_anchored_too(cursor):
    times = _sweep(cursor)
    anchor_t = times[-1]
    for i in range(1, 6):
        cursor.update(0.80, 0.5, anchor_t + i / 30)

    cursor.press(anchor_t=anchor_t)
    assert cursor._mouse.presses[-1] == cursor.anchor_at(
        anchor_t - config.CLICK_ANCHOR_LOOKBACK_S)


def test_no_anchor_means_click_where_you_are(cursor):
    _sweep(cursor)
    here = cursor.last_screen
    cursor.click(anchor_t=None)
    assert cursor._mouse.clicks[-1] == here


def test_anchoring_can_be_switched_off(cursor, monkeypatch):
    monkeypatch.setattr(config, "CLICK_ANCHOR", False)
    times = _sweep(cursor)
    for i in range(1, 6):
        cursor.update(0.80, 0.5, times[-1] + i / 30)
    here = cursor.last_screen

    cursor.click(anchor_t=times[-1])
    assert cursor._mouse.clicks[-1] == here


def test_losing_the_hand_discards_the_anchor(cursor):
    times = _sweep(cursor)
    cursor.reset()                                   # hand lost
    assert cursor.anchor_at(times[-1]) is None
    # A click now must not rewind to a position from before the hand vanished.
    cursor.update(0.5, 0.5, times[-1] + 2.0)
    here = cursor.last_screen
    cursor.click(anchor_t=times[-1])
    assert cursor._mouse.clicks[-1] == here

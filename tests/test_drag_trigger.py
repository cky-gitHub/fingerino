"""DragTrigger: the state machine that decides click vs. press-and-hold.

Worth testing more heavily than anything else here, because its failure mode
is a mouse button left held down on someone's desktop. Everything below is
pure: synthetic (active, now) sequences, no camera, no clock.
"""

from fingerino import config
from fingerino.gesture_detector import DragTrigger


def hold(trigger, until, *, active=True, step=0.02, start=0.0):
    """Feed the posture from ``start`` to ``until``; return the edges seen."""
    seen, t = [], start
    while t <= until + 1e-9:
        edges = trigger.update(active, t)
        if any(edges):
            seen.append((round(t, 3), edges))
        t += step
    return seen


def armed():
    """A trigger that has seen the posture absent once, so it will fire."""
    trigger = DragTrigger()
    trigger.update(False, 0.0)
    return trigger


def test_hand_arriving_already_pointing_does_not_fire():
    # Someone walks into frame mid-point. Acting on that would click at
    # whatever the cursor happened to be over.
    trigger = DragTrigger()
    assert not any(e for _, e in hold(trigger, 5.0, start=0.0))


def test_short_point_clicks_and_never_presses():
    trigger = armed()
    trigger.update(True, 0.10)
    trigger.update(True, 0.20)                      # well under DRAG_HOLD_S
    assert trigger.update(False, 0.30) == (False, False, False)   # inside grace
    edges = trigger.update(False, 0.30 + config.CLICK_RELEASE_GRACE_S + 0.01)
    assert edges.click and not edges.press and not edges.release
    assert not trigger.down


def test_held_point_presses_then_releases():
    trigger = armed()
    trigger.update(True, 0.10)
    assert not trigger.update(True, 0.10 + config.DRAG_HOLD_S - 0.01).press
    press = trigger.update(True, 0.10 + config.DRAG_HOLD_S + 0.01)
    assert press.press and trigger.down

    t = 0.10 + config.DRAG_HOLD_S + 0.02
    assert not trigger.update(False, t).release                   # inside grace
    edges = trigger.update(False, t + config.DRAG_RELEASE_GRACE_S + 0.01)
    assert edges.release and not trigger.down


def test_brief_dropout_does_not_drop_a_live_drag():
    # MediaPipe loses the hand for a frame or two regularly; dropping the drag
    # halfway through is far worse than acting a frame late.
    trigger = armed()
    trigger.update(True, 0.10)
    trigger.update(True, 0.10 + config.DRAG_HOLD_S + 0.01)
    assert trigger.down

    t = 1.0
    assert not trigger.update(False, t).release
    trigger.update(True, t + config.DRAG_RELEASE_GRACE_S / 2)     # re-acquired
    assert trigger.down
    assert not trigger.update(False, t + config.DRAG_RELEASE_GRACE_S).release
    assert trigger.down


def test_drag_is_force_released_after_the_safety_valve():
    # A frozen hand or a persistent mis-read must never hold the button
    # forever, whatever the tracker believes it is still seeing.
    trigger = armed()
    trigger.update(True, 0.10)
    trigger.update(True, 0.10 + config.DRAG_HOLD_S + 0.01)
    assert trigger.down

    stuck = 0.10 + config.DRAG_HOLD_S + 0.01 + config.DRAG_MAX_S + 0.01
    assert trigger.update(True, stuck).release
    assert not trigger.down
    # ...and it stays released while the posture is still stuck on.
    assert not any(trigger.update(True, stuck + n).press for n in (1, 5, 30))


def test_second_click_inside_the_cooldown_is_swallowed():
    trigger = armed()
    trigger.update(True, 0.01)
    trigger.update(False, 0.02)
    assert trigger.update(False, 0.02 + config.CLICK_RELEASE_GRACE_S + 0.01).click

    t = 0.10
    trigger.update(True, t)
    trigger.update(False, t + 0.01)
    inside = t + 0.01 + config.CLICK_RELEASE_GRACE_S + 0.01
    assert inside - 0.09 < config.CLICK_COOLDOWN_S        # premise of the test
    assert not trigger.update(False, inside).click


def test_progress_reports_the_pending_hold():
    trigger = armed()
    assert trigger.progress(0.0) == 0.0        # nothing pending
    trigger.update(True, 1.0)
    assert trigger.progress(1.0) == 0.0
    assert trigger.progress(1.0 + config.DRAG_HOLD_S / 2) == 0.5
    assert trigger.progress(1.0 + config.DRAG_HOLD_S * 2) == 1.0
    trigger.update(True, 1.0 + config.DRAG_HOLD_S + 0.01)
    assert trigger.down
    assert trigger.progress(2.0) == 0.0        # already latched

"""Signs to actions: what each recognised sign does.

The gesture detector names the signs it sees (``gesture_detector.BUILTIN_SIGNS``)
and stops there. This module is the other half: a registry that maps a sign id
to an :class:`Action`, and the per-frame step that decides which actions fire.
Keeping the two apart is what lets a sign be rebound -- or a new sign added --
without touching recognition.

Standard library only, like config.py, so it is testable anywhere. Actually
pressing keys lives in system_actions.py, which looks actions up by ``id``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .gesture_detector import (
    SIGN_FLAT_DOWN,
    SIGN_FLAT_LEFT,
    SIGN_FLAT_UP,
    SIGN_SHAKA,
    GestureOutput,
)


@dataclass(frozen=True)
class Action:
    id: str        # how system_actions finds the code that performs it
    label: str     # the HUD's mode label while it happens
    toast: str     # the confirmation shown once it has fired


# The actions Fingerino has always had. system_actions.BUILTIN must provide a
# function for every id here (tests/test_signs_actions.py checks).
BUILTIN_ACTIONS: dict[str, Action] = {a.id: a for a in (
    Action("minimize_all", "Minimize", "Minimized"),
    Action("restore_all", "Restore", "Restored"),
    Action("switch_window", "Switch", "Switch window"),
    Action("open_ai_chat", "New chat", "New chat"),
)}

# Sign id -> action id. Today's behaviour, unchanged. flat_right is
# deliberately absent: it is recognised but has never done anything.
DEFAULT_BINDINGS: dict[str, str] = {
    SIGN_FLAT_DOWN: "minimize_all",
    SIGN_FLAT_UP: "restore_all",
    SIGN_FLAT_LEFT: "switch_window",
    SIGN_SHAKA: "open_ai_chat",
}


class Registry:
    """Which action, if any, each sign is bound to."""

    def __init__(self, bindings: dict[str, str] | None = None,
                 actions: dict[str, Action] | None = None) -> None:
        self.actions = dict(BUILTIN_ACTIONS if actions is None else actions)
        self.bindings = dict(DEFAULT_BINDINGS if bindings is None else bindings)

    def action_for(self, sign: str) -> Action | None:
        """The action ``sign`` is bound to; None if unbound or unknown."""
        action_id = self.bindings.get(sign)
        return None if action_id is None else self.actions.get(action_id)

    def resolve(self, out: GestureOutput,
                live: Callable[[str], bool]) -> list[Action]:
        """The actions this frame's signs fire, and the HUD label to match.

        ``live(sign)`` says whether a sign may act right now: false if it is
        switched off in Home, and false for every sign while paused. The label
        is updated whether or not the sign is live, as it always was -- the
        HUD names what was seen; the toast confirms what was done.
        """
        if out.pending_sign is not None:
            pending = self.action_for(out.pending_sign)
            if pending is not None:
                out.mode_label = pending.label
        fired = []
        for sign in out.signs:
            action = self.action_for(sign)
            if action is None:
                continue
            out.mode_label = action.label
            if live(sign):
                fired.append(action)
        return fired

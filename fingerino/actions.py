"""Signs to actions: what each recognised sign does.

The gesture detector names the signs it sees (``gesture_detector.BUILTIN_SIGNS``)
and stops there. This module is the other half: a registry that maps a sign id
to an :class:`Action`, the per-frame step that decides which actions fire, and
``actions.json``, where the user's choices are kept. Keeping the two apart is
what lets a sign be rebound -- or a new sign added -- without touching
recognition. Signs themselves are stored elsewhere (signs.py); this file only
names them by id.

Standard library only, like config.py, so it is testable anywhere. Actually
pressing keys or opening things lives in system_actions.perform().
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlparse

from .gesture_detector import (
    SIGN_FLAT_DOWN,
    SIGN_FLAT_LEFT,
    SIGN_FLAT_UP,
    SIGN_SHAKA,
    GestureOutput,
)

FILENAME = "actions.json"
SCHEMA = 1

# What an action can be. "builtin" is one of Fingerino's own (BUILTIN_ACTIONS);
# the rest are made by the user in Home.
KINDS: dict[str, str] = {
    "builtin": "Fingerino action",
    "hotkey": "Keyboard shortcut",
    "media": "Media key",
    "open_app": "Open an app",
    "open": "Open a website or file",
    "command": "Run a command",
}

MEDIA_KEYS: dict[str, str] = {
    "play_pause": "Play / pause",
    "next": "Next track",
    "previous": "Previous track",
    "volume_up": "Volume up",
    "volume_down": "Volume down",
    "mute": "Mute",
}

# Keyboard shortcuts are stored as "ctrl+shift+k": modifiers in this order,
# then exactly one key -- a single character or one of NAMED_KEYS.
MODIFIERS = ("ctrl", "alt", "shift", "cmd")
NAMED_KEYS = frozenset({
    "space", "tab", "enter", "esc", "backspace", "delete", "insert",
    "home", "end", "page_up", "page_down", "up", "down", "left", "right",
    *(f"f{n}" for n in range(1, 21)),
})


@dataclass(frozen=True)
class Action:
    id: str        # unique; how bindings refer to it
    label: str     # the HUD's mode label while it happens
    toast: str     # the confirmation shown once it has fired
    kind: str = "builtin"
    # What to act on: the built-in's name, a shortcut ("ctrl+shift+k"), a
    # media key, an app path, a URL or file, or a command line.
    target: str = ""
    # Commands only run once a person has approved them. Anything typed into
    # Home is approved by being typed there; a command that arrived some
    # other way (a shared sign pack) is not, and system_actions refuses it.
    approved: bool = True


# The actions Fingerino has always had. system_actions.BUILTIN must provide a
# function for every id here (tests/test_signs_actions.py checks).
BUILTIN_ACTIONS: dict[str, Action] = {a.id: a for a in (
    Action("minimize_all", "Minimize", "Minimized", "builtin", "minimize_all"),
    Action("restore_all", "Restore", "Restored", "builtin", "restore_all"),
    Action("switch_window", "Switch", "Switch window", "builtin", "switch_window"),
    Action("open_ai_chat", "New chat", "New chat", "builtin", "open_ai_chat"),
)}

# How Home names the built-ins in its action picker.
BUILTIN_TITLES: dict[str, str] = {
    "minimize_all": "Minimize everything (show desktop)",
    "restore_all": "Bring the windows back",
    "switch_window": "Switch to the last window",
    "open_ai_chat": "New AI chat (Alt+Space)",
}

# Sign id -> action id. Today's behaviour, unchanged. flat_right is
# deliberately absent: it is recognised but has never done anything.
DEFAULT_BINDINGS: dict[str, str] = {
    SIGN_FLAT_DOWN: "minimize_all",
    SIGN_FLAT_UP: "restore_all",
    SIGN_FLAT_LEFT: "switch_window",
    SIGN_SHAKA: "open_ai_chat",
}


# ---------------------------------------------------------------------------
# Building actions from what the user typed
# ---------------------------------------------------------------------------
def normalize_combo(text: str) -> str | None:
    """``"Shift + Ctrl+K"`` -> ``"ctrl+shift+k"``; None if it isn't a shortcut.

    Accepts pynput's ``<ctrl>`` spelling too. Needs exactly one non-modifier
    key, so a lone modifier or two letters at once are rejected.
    """
    parts = [p.strip().strip("<>").lower().replace(" ", "_") for p in text.split("+")]
    aliases = {"control": "ctrl", "option": "alt", "opt": "alt", "win": "cmd",
               "super": "cmd", "command": "cmd", "meta": "cmd", "return": "enter",
               "escape": "esc", "del": "delete", "pgup": "page_up",
               "pgdown": "page_down"}
    parts = [aliases.get(p, p) for p in parts if p]
    mods = [m for m in MODIFIERS if m in parts]
    keys = [p for p in parts if p not in MODIFIERS]
    if len(keys) != 1 or len(mods) + 1 != len(parts):
        return None
    key = keys[0]
    if len(key) != 1 and key not in NAMED_KEYS:
        return None
    return "+".join([*mods, key])


def combo_label(combo: str) -> str:
    """``"ctrl+shift+k"`` -> ``"Ctrl+Shift+K"``."""
    return "+".join(p.upper() if len(p) == 1 else p.replace("_", " ").title()
                    for p in combo.split("+"))


def _short_target(kind: str, target: str) -> str:
    """A few words naming what an open action opens, for its label.

    Works on any OS's paths whichever OS it runs on, so labels read the same
    everywhere: ``C:\\Apps\\Spotify.exe`` and ``/Applications/Spotify.app``
    both become "Spotify".
    """
    drive_path = len(target) > 2 and target[1] == ":" and target[2] in "/\\"
    if kind == "open" and not drive_path:
        url = urlparse(target)
        if url.scheme in ("http", "https") and url.netloc:
            host = url.netloc.removeprefix("www.")
            return host.removeprefix("open.")
        if len(url.scheme) > 1:
            return url.scheme.capitalize()          # spotify:track:... -> Spotify
    name = target.rstrip("/\\").replace("\\", "/").rsplit("/", 1)[-1] or target
    if kind == "open_app":
        name = os.path.splitext(name)[0]
    return name


def make_action(kind: str, target: str, name: str = "",
                approved: bool = True) -> Action | str:
    """Build an action from a kind and a target; a message if it's not valid.

    ``name`` replaces the automatic label (shown on the HUD and in the toast).
    The id is new each time, so editing a sign's action never changes an
    action another sign is still bound to.
    """
    target = target.strip()
    name = name.strip()
    if kind == "builtin":
        if target not in BUILTIN_ACTIONS:
            return "Choose one of Fingerino's actions."
        return BUILTIN_ACTIONS[target]
    if kind not in KINDS:
        return "Choose what the sign should do."
    if kind == "hotkey":
        combo = normalize_combo(target)
        if combo is None:
            return "Press the shortcut's keys: a key, with any of Ctrl, Alt, Shift or Cmd."
        target, label = combo, combo_label(combo)
    elif kind == "media":
        if target not in MEDIA_KEYS:
            return "Choose a media key."
        label = MEDIA_KEYS[target]
    elif not target:
        return {"open_app": "Choose the app to open.",
                "open": "Enter a web address, or choose a file.",
                "command": "Enter the command to run."}[kind]
    elif kind == "command":
        label = "Run command"
    else:
        label = f"Open {_short_target(kind, target)}"
    label = name or label
    return Action(f"user-{uuid.uuid4().hex[:12]}", label, label, kind, target, approved)


# ---------------------------------------------------------------------------
# The registry
# ---------------------------------------------------------------------------
class Registry:
    """Which action, if any, each sign is bound to.

    Shared between the Home window (which edits it on the UI thread) and the
    tracking session (which reads it every frame). Every edit is a single
    dict assignment, and an action is stored before anything is bound to it,
    so the session never sees a binding to an action that isn't there yet.
    """

    def __init__(self, bindings: dict[str, str | None] | None = None,
                 actions: dict[str, Action] | None = None) -> None:
        self.actions = dict(BUILTIN_ACTIONS if actions is None else actions)
        self.bindings: dict[str, str | None] = dict(
            DEFAULT_BINDINGS if bindings is None else bindings)

    def action_for(self, sign: str) -> Action | None:
        """The action ``sign`` is bound to; None if unbound or unknown."""
        action_id = self.bindings.get(sign)
        return None if action_id is None else self.actions.get(action_id)

    def bind(self, sign: str, action: Action | None) -> None:
        """Bind ``sign`` to ``action``; None leaves it doing nothing."""
        if action is None:
            self.bindings[sign] = None
        else:
            self.actions[action.id] = action
            self.bindings[sign] = action.id
        self._drop_orphans()

    def reset(self, sign: str) -> None:
        """Back to what the sign did out of the box (nothing, if custom)."""
        self.bindings[sign] = DEFAULT_BINDINGS.get(sign)
        self._drop_orphans()

    def forget(self, sign: str) -> None:
        """Remove a sign's binding altogether (the sign has been deleted)."""
        self.bindings.pop(sign, None)
        self._drop_orphans()

    def _drop_orphans(self) -> None:
        bound = set(self.bindings.values())
        for action_id in [a for a in self.actions
                          if a not in bound and a not in BUILTIN_ACTIONS]:
            del self.actions[action_id]

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

    # -- actions.json ---------------------------------------------------------
    def to_json(self) -> dict:
        user = [a for a in self.actions.values() if a.id not in BUILTIN_ACTIONS]
        return {
            "schema": SCHEMA,
            "actions": [{"id": a.id, "kind": a.kind, "target": a.target,
                         "label": a.label, "approved": a.approved} for a in user],
            # Only what differs from the defaults, so a later release can
            # change a default for everyone who never touched that sign.
            "bindings": {s: a for s, a in self.bindings.items()
                         if DEFAULT_BINDINGS.get(s) != a},
        }

    @classmethod
    def from_json(cls, data: object) -> Registry:
        """Build from whatever was on disk, keeping every valid entry.

        Like settings.json, a hand-edited or half-written file must never stop
        the app starting: bad actions are skipped, and a binding to an action
        that isn't there falls back to the sign's default.
        """
        reg = cls()
        if not isinstance(data, dict):
            return reg
        for item in data.get("actions") or []:
            if not isinstance(item, dict):
                continue
            raw = [item.get(k) for k in ("id", "kind", "target", "label")]
            fields = [v for v in raw if isinstance(v, str) and v]
            if len(fields) != len(raw):
                continue
            action_id, kind, target, label = fields
            if kind not in KINDS or kind == "builtin" or action_id in BUILTIN_ACTIONS:
                continue
            # A command whose approval isn't recorded as exactly True is
            # treated as unapproved: failing closed is the point.
            approved = item.get("approved") is True
            reg.actions[action_id] = Action(action_id, label, label, kind, target, approved)
        bindings = data.get("bindings")
        if isinstance(bindings, dict):
            for sign, action_id in bindings.items():
                if not isinstance(sign, str):
                    continue
                if action_id is None or (isinstance(action_id, str)
                                         and action_id in reg.actions):
                    reg.bindings[sign] = action_id
        reg._drop_orphans()
        return reg


def describe(action: Action | None) -> dict:
    """What Home needs to show and edit an action."""
    if action is None:
        return {"kind": "", "target": "", "name": "", "label": "Does nothing"}
    auto = make_action(action.kind, action.target)
    custom = action.label if isinstance(auto, Action) and auto.label != action.label else ""
    return {"kind": action.kind, "target": action.target, "name": custom,
            "label": action.label}


def load(folder: str) -> Registry:
    """Read actions.json from ``folder``; today's defaults if missing or bad."""
    try:
        with open(os.path.join(folder, FILENAME), encoding="utf-8") as fh:
            return Registry.from_json(json.load(fh))
    except (OSError, ValueError):
        return Registry()


def save(folder: str, registry: Registry) -> bool:
    """Write actions.json atomically. False if the folder isn't writable."""
    path = os.path.join(folder, FILENAME)
    tmp = path + ".tmp"
    try:
        os.makedirs(folder, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(registry.to_json(), fh, indent=2)
        os.replace(tmp, path)
        return True
    except OSError:
        return False

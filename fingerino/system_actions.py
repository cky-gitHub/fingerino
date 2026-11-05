"""OS-level actions triggered by signs (keyboard shortcuts).

Isolated here so the gesture layer stays platform-agnostic and the shortcuts
can be changed in one place. Which sign runs which of these is decided by
actions.Registry; :data:`BUILTIN` is how it finds them by id. On pynput,
``Key.cmd`` is the Windows / Super key.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable

from pynput.keyboard import Controller, GlobalHotKeys, Key

from . import config

_IS_MAC = sys.platform == "darwin"

_kb = Controller()

_MODIFIERS = {"alt": Key.alt, "ctrl": Key.ctrl, "cmd": Key.cmd, "shift": Key.shift}
_NAMED_KEYS = {"space": Key.space, "tab": Key.tab, "enter": Key.enter, "esc": Key.esc}


def _tap(key) -> None:
    _kb.press(key)
    _kb.release(key)


def _combo(*keys) -> None:
    """Press modifiers+key in order, release in reverse (chord)."""
    for k in keys:
        _kb.press(k)
    for k in reversed(keys):
        _kb.release(k)


def minimize_all() -> None:
    """Clear the desktop.

    Windows: show_desktop -> Win+D ; minimize_all -> Win+M.
    macOS: F11, Mission Control's Show Desktop (it toggles, so restore_all
    sends the same key). If F11 does nothing on your Mac, the shortcut is
    turned off or remapped in System Settings > Keyboard > Shortcuts.
    """
    if _IS_MAC:
        _tap(Key.f11)
        return
    _combo(Key.cmd, "d" if config.MINIMIZE_ACTION == "show_desktop" else "m")


def restore_all() -> None:
    """Bring the windows back. Win+D toggles the desktop; else Win+Shift+M."""
    if _IS_MAC:
        _tap(Key.f11)
        return
    if config.MINIMIZE_ACTION == "show_desktop":
        _combo(Key.cmd, "d")
    else:
        _combo(Key.cmd, Key.shift, "m")


def switch_window() -> None:
    """Alt+Tab (Cmd+Tab on macOS) to the most recent window."""
    _combo(Key.cmd if _IS_MAC else Key.alt, Key.tab)


def open_ai_chat() -> None:
    """Summon the AI chat app via its global hotkey (default Alt+Space)."""
    mod = _MODIFIERS.get(config.AI_CHAT_MODIFIER, Key.alt)
    key = _NAMED_KEYS.get(config.AI_CHAT_KEY, config.AI_CHAT_KEY)
    _combo(mod, key)


BUILTIN: dict[str, Callable[[], None]] = {
    "minimize_all": minimize_all,
    "restore_all": restore_all,
    "switch_window": switch_window,
    "open_ai_chat": open_ai_chat,
}


def run(action_id: str) -> None:
    """Perform the built-in action ``action_id`` (an actions.Action id)."""
    BUILTIN[action_id]()


_MEDIA = {
    "play_pause": "media_play_pause",
    "next": "media_next",
    "previous": "media_previous",
    "volume_up": "media_volume_up",
    "volume_down": "media_volume_down",
    "mute": "media_volume_mute",
}


def _key(name: str):
    """One part of an actions.normalize_combo() shortcut as a pynput key."""
    if name in _MODIFIERS:
        return _MODIFIERS[name]
    if len(name) == 1:
        return name
    return getattr(Key, name)


def open_target(target: str) -> None:
    """Open an app, file, folder or URL the way a double-click would.

    Never through a shell: the target is handed over as a single argument,
    so a file name can't smuggle a second command in.
    """
    if sys.platform.startswith("win"):
        os.startfile(target)  # noqa: S606 -- Windows only
    elif _IS_MAC:
        subprocess.Popen(["open", target], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    elif os.path.isfile(target) and os.access(target, os.X_OK):
        subprocess.Popen([target], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
    else:
        subprocess.Popen(["xdg-open", target], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)


def run_command(command: str) -> None:
    """Run a command line the user typed into Home, without waiting for it.

    Through the system shell on purpose -- people paste commands with pipes
    and quotes -- and only ever for an approved action (see perform()).
    """
    kwargs: dict = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
                    "stdin": subprocess.DEVNULL}
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(command, shell=True, **kwargs)  # noqa: S602


def perform(action) -> None:
    """Carry out an actions.Action. Raises if it can't be done.

    Called on the tracking thread, so nothing here waits: keys are tapped,
    and apps, files and commands are launched and left to run.
    """
    kind, target = action.kind, action.target
    if kind == "builtin":
        BUILTIN[target or action.id]()
    elif kind == "hotkey":
        _combo(*(_key(part) for part in target.split("+")))
    elif kind == "media":
        _tap(getattr(Key, _MEDIA[target]))
    elif kind in ("open_app", "open"):
        open_target(target)
    elif kind == "command":
        # The one rule that holds whatever else changes: a command nobody
        # approved does not run.
        if not action.approved:
            raise PermissionError("This command hasn't been approved yet.")
        run_command(target)
    else:
        raise ValueError(f"Unknown action kind {kind!r}")


def listen_hotkey(combo: str, callback):
    """Call ``callback`` from a background thread whenever ``combo`` is pressed.

    ``combo`` uses pynput's syntax, e.g. ``"<ctrl>+<alt>+f"``. Returns the
    running listener (stop it with ``.stop()``), or None if the combo doesn't
    parse or the platform refuses a keyboard hook -- a missing hotkey is a
    lost convenience, never a reason not to start.
    """
    try:
        listener = GlobalHotKeys({combo: callback})
        listener.daemon = True
        listener.start()
        return listener
    except Exception:
        return None

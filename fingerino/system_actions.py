"""OS-level actions triggered by signs (keyboard shortcuts).

Isolated here so the gesture layer stays platform-agnostic and the shortcuts
can be changed in one place. Which sign runs which of these is decided by
actions.Registry; :data:`BUILTIN` is how it finds them by id. On pynput,
``Key.cmd`` is the Windows / Super key.
"""

from __future__ import annotations

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

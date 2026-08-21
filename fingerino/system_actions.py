"""OS-level actions triggered by gestures (keyboard shortcuts).

Isolated here so the gesture layer stays platform-agnostic and the shortcuts
can be changed in one place. On pynput, ``Key.cmd`` is the Windows / Super key.
"""

from __future__ import annotations

from pynput.keyboard import Controller, Key

from . import config

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
    """Clear the desktop. show_desktop -> Win+D ; minimize_all -> Win+M."""
    _combo(Key.cmd, "d" if config.MINIMIZE_ACTION == "show_desktop" else "m")


def restore_all() -> None:
    """Bring the windows back. Win+D toggles the desktop; else Win+Shift+M."""
    if config.MINIMIZE_ACTION == "show_desktop":
        _combo(Key.cmd, "d")
    else:
        _combo(Key.cmd, Key.shift, "m")


def switch_window() -> None:
    """Alt+Tab to the most recent window."""
    _combo(Key.alt, Key.tab)


def open_ai_chat() -> None:
    """Summon the AI chat app via its global hotkey (default Alt+Space)."""
    mod = _MODIFIERS.get(config.AI_CHAT_MODIFIER, Key.alt)
    key = _NAMED_KEYS.get(config.AI_CHAT_KEY, config.AI_CHAT_KEY)
    _combo(mod, key)

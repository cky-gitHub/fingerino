"""Choices the user makes, kept across restarts.

config.py holds the defaults and the tuning constants; this is the small layer
on top that the Home window and the HUD's gesture guide write to. Standard
library only, like config.py, so it is testable anywhere.

The file lives in the same folder as everything else Fingerino writes (see
hand_tracker.cache_dir and the README's "What it writes to disk"), so the
uninstaller's cleanup and the privacy section stay true without exceptions.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from . import config

FILENAME = "settings.json"
# Bumped only if a stored field changes meaning; new fields just get defaults.
SCHEMA = 1

# pynput's GlobalHotKeys syntax. Toggles tracking from anywhere, which is the
# way back when gestures misbehave and the tray icon is hidden in overflow.
DEFAULT_HOTKEY = "<ctrl>+<alt>+f"


def _default_gestures() -> dict[str, bool]:
    return {icon: True for icon, _ in config.GESTURE_TUTORIAL}


@dataclass
class Settings:
    # Per-gesture on/off, keyed by the icon id used throughout
    # config.GESTURE_TUTORIAL.
    gestures: dict[str, bool] = field(default_factory=_default_gestures)
    # False until the user has dismissed the welcome on the Home page; the
    # first launch opens Home so there is somewhere to say hello.
    onboarded: bool = False
    # Off by default: opening Fingerino shows Home and leaves the camera off
    # until the user presses Start.
    start_on_open: bool = False
    hotkey: str = DEFAULT_HOTKEY

    def to_json(self) -> dict:
        return {"schema": SCHEMA, "gestures": dict(self.gestures),
                "onboarded": self.onboarded, "start_on_open": self.start_on_open,
                "hotkey": self.hotkey}

    @classmethod
    def from_json(cls, data: object) -> Settings:
        """Build from whatever was on disk, keeping every valid field.

        A hand-edited or half-written file must never stop the app starting,
        so anything of the wrong type is replaced by its default rather than
        rejected wholesale. Gesture ids that no longer exist are dropped and
        new ones arrive switched on.
        """
        s = cls()
        if not isinstance(data, dict):
            return s
        stored = data.get("gestures")
        if isinstance(stored, dict):
            for icon in s.gestures:
                if isinstance(stored.get(icon), bool):
                    s.gestures[icon] = stored[icon]
        if isinstance(data.get("onboarded"), bool):
            s.onboarded = data["onboarded"]
        if isinstance(data.get("start_on_open"), bool):
            s.start_on_open = data["start_on_open"]
        if isinstance(data.get("hotkey"), str) and data["hotkey"].strip():
            s.hotkey = data["hotkey"]
        return s


def load(folder: str) -> Settings:
    """Read settings from ``folder``; defaults if missing or unreadable."""
    try:
        with open(os.path.join(folder, FILENAME), encoding="utf-8") as fh:
            return Settings.from_json(json.load(fh))
    except (OSError, ValueError):
        return Settings()


def save(folder: str, s: Settings) -> bool:
    """Write settings atomically. False if the folder isn't writable.

    Written to a temporary file and swapped in, so a crash or power cut
    mid-write leaves the previous settings rather than a truncated file.
    """
    path = os.path.join(folder, FILENAME)
    tmp = path + ".tmp"
    try:
        os.makedirs(folder, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(s.to_json(), fh, indent=2)
        os.replace(tmp, path)
        return True
    except OSError:
        return False

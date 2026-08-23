"""macOS-specific bits: the Accessibility permission gate and error dialogs.

Mirrors :mod:`fingerino.winui` — everything here is a no-op on other
platforms, so callers don't need to guard.

macOS puts synthetic input behind the **Accessibility** permission (TCC).
Until the user grants it, pynput's cursor moves and key taps are dropped
*silently*: no error, no exception, just an app that appears to track your
hand perfectly and control nothing. Camera access prompts for itself on first
use; this one does not, so the app has to ask.
"""

from __future__ import annotations

import ctypes
import subprocess
import sys

_IS_MAC = sys.platform == "darwin"

_APPLICATION_SERVICES = (
    "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
)
_SETTINGS_URL = (
    "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
)

_MESSAGE = (
    "Fingerino needs Accessibility permission before it can move the cursor "
    "or send keyboard shortcuts. Without it you will see your hand tracked "
    "perfectly while nothing on screen responds.\n\n"
    "1. Open System Settings > Privacy & Security > Accessibility\n"
    "2. Switch Fingerino on. If it is not in the list yet, press + and pick "
    "Fingerino from your Applications folder\n"
    "3. Quit Fingerino and open it again — macOS only grants the permission "
    "to a freshly started app\n\n"
    "Fingerino only reads your camera locally. Nothing is recorded and "
    "nothing is uploaded."
)


def _as_string(text: str) -> str:
    """Quote a Python string as an AppleScript string literal."""
    escaped = text.replace(chr(92), chr(92) * 2).replace('"', chr(92) + '"')
    # AppleScript has no \n escape inside literals; splice in the constant.
    return '"' + escaped.replace(chr(10), '" & return & "') + '"'


def _osascript(script: str, timeout: float = 180) -> str:
    if not _IS_MAC:
        return ""
    try:
        done = subprocess.run(["osascript", "-e", script],
                              capture_output=True, text=True, timeout=timeout)
        return done.stdout or ""
    except Exception:
        return ""


def alert(title: str, text: str) -> None:
    """Show a modal error dialog.

    A packaged app has no console, so a startup failure printed to stderr goes
    nowhere and the app just seems not to open.
    """
    if not _IS_MAC:
        return
    _osascript(
        f"display dialog {_as_string(text)} with title {_as_string(title)} "
        'buttons {"OK"} default button "OK" with icon stop giving up after 120'
    )


def accessibility_trusted() -> bool:
    """Whether this process is allowed to drive the cursor and keyboard.

    Returns True on any non-macOS platform, and also when the check itself
    fails — a permission warning that fires by mistake is worse than none.
    """
    if not _IS_MAC:
        return True
    try:
        services = ctypes.cdll.LoadLibrary(_APPLICATION_SERVICES)
        services.AXIsProcessTrusted.restype = ctypes.c_bool
        services.AXIsProcessTrusted.argtypes = []
        return bool(services.AXIsProcessTrusted())
    except Exception:
        return True


def open_accessibility_settings() -> None:
    """Jump straight to the Accessibility pane in System Settings."""
    if not _IS_MAC:
        return
    try:
        subprocess.Popen(["open", _SETTINGS_URL])
    except Exception:
        pass


def warn_missing_accessibility() -> None:
    """Explain the permission in a dialog, and offer to open the settings pane.

    Not a HUD toast: this fires before the camera window exists, and a
    one-second toast is the wrong place for the single thing standing between
    the user and a working app. Gives up after two minutes so a packaged app
    can never hang on an unattended machine.
    """
    if not _IS_MAC:
        return
    out = _osascript(
        f"display dialog {_as_string(_MESSAGE)} with title \"Fingerino\" "
        'buttons {"Continue Anyway", "Open Settings"} '
        'default button "Open Settings" with icon caution giving up after 120'
    )
    if "Open Settings" in out:
        open_accessibility_settings()

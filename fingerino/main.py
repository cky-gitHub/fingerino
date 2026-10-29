"""Fingerino — webcam hand-tracking mouse.

Gestures (one hand unless noted):
    Move      thumb tip drives the cursor (see config.CURSOR_SOURCE)
    Click     point (index out, middle in) — lands where you aimed, not
              where the finger dragged the hand to on its way out
    Drag      hold the point ~0.5s — the button then stays down until the
              finger relaxes
    Scroll    two fingers out (index + middle), move the hand up / down
    Minimize  flat hand swiped down    Restore  flat hand swiped up
    Switch    flat hand swiped left (Alt+Tab)
    New chat  shaka sign (thumb + pinky out)
    Hold      both palms up, held still ~1s — pauses every gesture; do it
              again to hand control back to exactly the same set
    Exit      cross both hands into an "X" and hold briefly — stops tracking

    fingerino            # open Home; press Start to track (or: python -m fingerino)
    fingerino --debug    # add raw skeleton + FPS to the HUD
    fingerino --no-move  # track & show the HUD but don't drive the OS
    fingerino --selftest # check the install without a camera, then exit

Opening Fingerino shows the Home window with the camera off. Start opens the
camera and the HUD; Stop (in Home, on the HUD's hover X, or in the tray) closes
them again. Ctrl+Alt+F pauses or resumes from any app. The windows live in
shell.py and the tracking loop in engine.py.
"""

from __future__ import annotations

import argparse
import os
import platform
import sys
import time
import traceback

import cv2
import numpy as np

from . import __version__, branding, config, macui, settings, winui
from . import shell as _shell
from .cursor_controller import CursorController
from .engine import Options
from .hand_tracker import HandTracker, cache_dir

_APP_ID = "cky.fingerino"


def _selftest() -> int:
    """Exercise the runtime with no camera; report what broke.

    A packaged build fails in ways a source install never does — MediaPipe
    data left out of the bundle, a model that wasn't copied, a missing DLL —
    and it fails silently, because there is no console to print to. This runs
    everything except the camera and writes a report to the cache directory,
    so CI can check an installer isn't dead on arrival and a user who says
    "it won't start" has something to send back.
    """
    lines = [
        f"Fingerino {__version__} selftest",
        f"python {sys.version.split()[0]} on {sys.platform} "
        f"({platform.machine()})",
        f"frozen: {bool(getattr(sys, 'frozen', False))}",
        f"opencv: {cv2.__version__}",
    ]
    ok = True

    try:
        tracker = HandTracker()
        lines.append(f"model: {tracker.model_path}")
        blank = np.zeros((config.CAMERA_HEIGHT, config.CAMERA_WIDTH, 3), np.uint8)
        tracker.submit(blank, 1)
        time.sleep(0.5)          # detection is async; give the worker a moment
        tracker.close()
        lines.append("hand tracker: ok")
    except Exception as exc:
        ok = False
        lines.append(f"hand tracker: FAILED {exc!r}")

    try:
        cursor = CursorController()
        lines.append(f"screen: {cursor.screen_w}x{cursor.screen_h}")
    except Exception as exc:
        ok = False
        lines.append(f"cursor control: FAILED {exc!r}")

    if sys.platform == "darwin":
        trusted = macui.accessibility_trusted()
        lines.append(f"accessibility granted: {trusted}")

    # The QML is only parsed at load time, and a packaged build can lose Qt's
    # QML modules without any import failing -- so build the real windows
    # (never shown) rather than trusting that PySide6 imported.
    try:
        app = _shell.Shell(settings.Settings(), cache_dir(), None,
                           tray=False, hotkey=False)
        loaded = app.window is not None
        app.close()
        ok = ok and loaded
        lines.append("home window: ok" if loaded
                     else "home window: FAILED to load Home.qml")
    except Exception as exc:
        ok = False
        lines.append(f"home window: FAILED {exc!r}")

    lines.append("RESULT: ok" if ok else "RESULT: failed")
    report = "\n".join(lines)

    # print() is a no-op when there is no console, so the file is the only
    # copy a packaged build can leave behind.
    print(report)
    try:
        path = os.path.join(cache_dir(), "selftest.txt")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(report + "\n")
        print(f"written to {path}")
    except OSError:
        pass
    return 0 if ok else 1


def _run() -> int:
    parser = argparse.ArgumentParser(description="Webcam hand-tracking mouse.")
    parser.add_argument("--debug", action="store_true",
                        help="show the raw hand skeleton and FPS")
    parser.add_argument("--no-move", action="store_true",
                        help="track and render but do not drive the OS (safe test mode)")
    parser.add_argument("--camera", type=int, default=config.CAMERA_INDEX,
                        help="camera index (default %(default)s)")
    parser.add_argument("--selftest", action="store_true",
                        help="check the install (no camera) and exit")
    args = parser.parse_args()

    if args.selftest:
        return _selftest()

    if not winui.acquire_single_instance(_APP_ID):
        # Launching again should find the app, not complain about it.
        if _shell.bring_running_instance_forward():
            return 0
        message = "Fingerino is already running."
        print(f"[fingerino] {message}", file=sys.stderr)
        winui.alert(config.WINDOW_NAME, message)
        return 0

    # Must precede window creation or the taskbar keeps python.exe's identity.
    winui.set_app_id(_APP_ID)

    data_dir = cache_dir()
    app = _shell.Shell(
        settings.load(data_dir), data_dir, branding.icon_path(data_dir),
        Options(camera=args.camera, drive=not args.no_move, debug=args.debug),
        on_crash=_write_crash)
    print(f"[fingerino] ready — {'controlling the OS' if not args.no_move else 'HUD only'}"
          " once tracking starts.")
    return app.run()


def _write_crash(exc: BaseException) -> str:
    """Write a traceback beside the selftest report; return what to tell the
    user. Used for a crash in the tracking thread, which Home then shows
    rather than the app vanishing."""
    lines = [
        f"Fingerino {__version__} crashed",
        f"python {sys.version.split()[0]} on {sys.platform} "
        f"({platform.machine()})",
        f"frozen: {bool(getattr(sys, 'frozen', False))}",
        f"opencv: {cv2.__version__}",
        "",
    ]
    report = "\n".join(lines) + "".join(traceback.format_exception(exc))
    print(report, file=sys.stderr)

    path = None
    try:
        path = os.path.join(cache_dir(), "crash.txt")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(report)
    except OSError:
        path = None          # a cache we cannot write to is not worth a second failure

    message = (f"Fingerino stopped unexpectedly.\n\n"
               f"{type(exc).__name__}: {exc}")
    if path:
        message += (f"\n\nThe details were saved to:\n{path}\n\n"
                    "Attaching that file to a bug report is the fastest way "
                    "to get this fixed.")
    return message


def _crash_report(exc: BaseException) -> int:
    """Report a crash outside the tracking thread, where there may be no
    window left to show it in.

    A packaged build has no console, so an unhandled exception otherwise makes
    the window vanish leaving nothing on screen and nothing on disk: the user
    has "it stopped working" and no way to tell anyone more than that. The
    mouse button is released by the tracking session's own cleanup.
    """
    message = _write_crash(exc)
    winui.alert(config.WINDOW_NAME, message)
    macui.alert(config.WINDOW_NAME, message)
    return 1


def main() -> int:
    """Entry point for all three launch paths; see _run for the real work."""
    try:
        return _run()
    except SystemExit:
        raise                # argparse --help and friends: not a crash
    except KeyboardInterrupt:
        return 130
    except BaseException as exc:
        return _crash_report(exc)


if __name__ == "__main__":
    raise SystemExit(main())

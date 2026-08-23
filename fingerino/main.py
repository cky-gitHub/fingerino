"""Fingerino — webcam hand-tracking mouse.

Gestures (one hand unless noted):
    Move      thumb tip drives the cursor
    Click     point (index out, middle in)
    Drag      hold the point ~0.5s — the button then stays down until the
              finger relaxes
    Scroll    two fingers out (index + middle), move the hand up / down
    Minimize  flat hand swiped down    Restore  flat hand swiped up
    Switch    flat hand swiped left (Alt+Tab)
    New chat  shaka sign (thumb + pinky out)
    Exit      cross both hands into an "X" and hold briefly

    fingerino            # normal, clean HUD          (or: python -m fingerino)
    fingerino --debug    # add raw skeleton + FPS
    fingerino --no-move  # track & show HUD but don't drive the OS
    fingerino --selftest # check the install without a camera, then exit

Esc quits (so does the Exit gesture). Tab toggles the gesture legend panel.
"""

from __future__ import annotations

import argparse
import os
import platform
import sys
import time

import cv2
import numpy as np

from . import __version__
from . import branding
from . import config
from . import macui
from . import system_actions
from . import winui
from .cursor_controller import CursorController
from .gesture_detector import GestureEngine
from .hand_tracker import HandTracker, cache_dir
from .ui_overlay import UIOverlay


def _selftest() -> int:
    """Exercise the runtime with no camera and no window; report what broke.

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


def _open_camera(index: int) -> cv2.VideoCapture:
    # CAP_DSHOW starts noticeably faster than the default backend on Windows.
    backend = cv2.CAP_DSHOW if sys.platform.startswith("win") else 0
    cap = cv2.VideoCapture(index, backend)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.CAMERA_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.CAMERA_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, 30)
    return cap


_APP_ID = "cky.fingerino"


def _window_size(screen_w: int, screen_h: int) -> tuple[int, int]:
    """Window size hitting the configured area fraction, at the camera's aspect."""
    target_area = screen_w * screen_h * config.WINDOW_SCREEN_FRACTION
    aspect = config.CAMERA_WIDTH / config.CAMERA_HEIGHT
    win_h = max(1, int((target_area / aspect) ** 0.5))
    win_w = max(1, int(win_h * aspect))
    return win_w, win_h


def _finalize_window(name: str) -> tuple:
    """Apply icon, fixed size and always-on-top; return the HWND (or None).

    ``cv2.namedWindow`` only registers the window; the real OS window isn't
    created until the first ``imshow`` call, so this must run after that —
    calling it earlier finds no window and silently no-ops.
    """
    hwnd = winui.find_window(name)
    if not hwnd:
        return None
    ico = branding.icon_path(cache_dir())
    winui.apply_icon(hwnd, ico)
    # Windows 11 takes the taskbar button's icon from the shell property
    # store rather than the window icon, so both are set.
    winui.set_taskbar_icon(hwnd, ico, _APP_ID, config.WINDOW_NAME)
    winui.lock_size(hwnd)
    if config.WINDOW_ALWAYS_ON_TOP:
        winui.raise_above_all(hwnd)
    return hwnd


def _pin_topmost(name: str) -> None:
    """Keep the HUD above other windows on macOS and Linux.

    Windows goes through winui, which can renew the claim repeatedly without
    stealing focus. Everywhere else OpenCV's own topmost property is the only
    lever there is, and it only needs setting once. Without this the HUD sinks
    behind whatever app you are controlling, which for this app is fatal to
    the whole point of it.
    """
    if sys.platform.startswith("win") or not config.WINDOW_ALWAYS_ON_TOP:
        return
    try:
        cv2.setWindowProperty(name, cv2.WND_PROP_TOPMOST, 1)
    except Exception:
        pass  # older OpenCV builds don't expose the property


def _set_title_note(name: str, note: str | None) -> None:
    """Show a status note in the title bar. macOS only.

    The Windows build finds its own window by exact title to attach the icon
    and the always-on-top handling, so renaming it there would break both.
    """
    if sys.platform != "darwin":
        return
    try:
        cv2.setWindowTitle(
            name, f"{config.WINDOW_NAME} — {note}" if note else config.WINDOW_NAME)
    except Exception:
        pass


def _fatal(message: str) -> None:
    """Report a startup failure the user would otherwise never see.

    Both dialog helpers no-op off their own platform, so calling each is the
    whole dispatch. The console path still matters for `pip install` users.
    """
    print(f"[fingerino] {message}", file=sys.stderr)
    winui.alert(config.WINDOW_NAME, message)
    macui.alert(config.WINDOW_NAME, message)


def _zone_px(w: int, h: int) -> tuple[int, int, int, int]:
    x1 = int(config.CONTROL_ZONE_X_MARGIN * w)
    x2 = int((1.0 - config.CONTROL_ZONE_X_MARGIN) * w)
    y1 = int(config.CONTROL_ZONE_Y_MARGIN * h)
    y2 = int((1.0 - config.CONTROL_ZONE_Y_MARGIN) * h)
    return x1, y1, x2, y2


def main() -> int:
    parser = argparse.ArgumentParser(description="Webcam hand-tracking mouse.")
    parser.add_argument("--debug", action="store_true",
                        help="show the raw hand skeleton and FPS")
    parser.add_argument("--no-move", action="store_true",
                        help="track and render but do not drive the OS (safe test mode)")
    parser.add_argument("--camera", type=int, default=config.CAMERA_INDEX,
                        help="camera index (default %(default)s)")
    parser.add_argument("--selftest", action="store_true",
                        help="check the install (no camera, no window) and exit")
    args = parser.parse_args()

    if args.selftest:
        return _selftest()

    # Must precede window creation or the taskbar keeps python.exe's identity.
    winui.set_app_id(_APP_ID)

    # macOS drops synthetic input on the floor until Accessibility is granted,
    # so ask before the window opens rather than looking broken afterwards.
    needs_access = not args.no_move and not macui.accessibility_trusted()
    if needs_access:
        macui.warn_missing_accessibility()

    cap = _open_camera(args.camera)
    if not cap.isOpened():
        _fatal(f"Could not open camera {args.camera}.\n\n"
               "Another app may be using the webcam, or it may be on a "
               "different index — try starting Fingerino with --camera 1.")
        return 1

    tracker = HandTracker()
    cursor = CursorController()
    engine = GestureEngine()
    drive = not args.no_move

    win_w, win_h = _window_size(cursor.screen_w, cursor.screen_h)
    # The frame is drawn at native camera resolution then shrunk to win_w by
    # imshow, so HUD sizes must be inflated by this ratio to stay legible.
    ui_scale = config.CAMERA_WIDTH / win_w
    overlay = UIOverlay(ui_scale=ui_scale)

    print(f"[fingerino] screen {cursor.screen_w}x{cursor.screen_h} — "
          f"{'controlling OS' if drive else 'HUD only'}. Esc to quit.")

    cv2.namedWindow(config.WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(config.WINDOW_NAME, win_w, win_h)
    cv2.moveWindow(config.WINDOW_NAME, 0, 0)
    if needs_access:
        # A toast lasts a second; this has to stay visible, because until it
        # is fixed the app tracks perfectly and controls nothing.
        _set_title_note(config.WINDOW_NAME, "no Accessibility permission yet")

    # Mutable so the mouse callback can flip it. OpenCV reports click
    # coordinates in *image* space, the same space the overlay draws in, so
    # the rect from the overlay can be hit-tested directly.
    ui = {
        "menu_open": False,
        "w": config.CAMERA_WIDTH,
        "h": config.CAMERA_HEIGHT,
        # Per-gesture on/off, keyed by the icon id used throughout
        # GESTURE_TUTORIAL. Session-only -- resets to all-enabled on restart.
        "gesture_enabled": {icon: True for icon, _ in config.GESTURE_TUTORIAL},
    }

    def _on_mouse(event, x, y, flags, param):
        if event != cv2.EVENT_LBUTTONDOWN:
            return
        x1, y1, x2, y2 = overlay.menu_toggle_rect(ui["w"], ui["h"], ui["menu_open"])
        if x1 <= x <= x2 and y1 <= y <= y2:
            ui["menu_open"] = not ui["menu_open"]
            return
        if ui["menu_open"]:
            rects = overlay.gesture_row_rects(ui["w"], ui["h"])
            for (icon, _), (rx1, ry1, rx2, ry2) in zip(config.GESTURE_TUTORIAL, rects):
                if rx1 <= x <= rx2 and ry1 <= y <= ry2:
                    ui["gesture_enabled"][icon] = not ui["gesture_enabled"][icon]
                    return

    cv2.setMouseCallback(config.WINDOW_NAME, _on_mouse)

    hwnd = None
    pinned = False
    last_access_t = 0.0
    overlay.toast("Press Tab for gestures")

    last_ts_ms = 0
    fps = 0.0
    prev_t = time.perf_counter()
    last_topmost_t = prev_t

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("[fingerino] camera frame grab failed", file=sys.stderr)
                break

            if config.FLIP_HORIZONTAL:
                frame = cv2.flip(frame, 1)
            h, w = frame.shape[:2]
            ui["w"], ui["h"] = w, h

            # Push frame for async detection with a strictly increasing timestamp.
            rgb = np.ascontiguousarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            ts_ms = max(int(time.perf_counter() * 1000), last_ts_ms + 1)
            last_ts_ms = ts_ms
            tracker.submit(rgb, ts_ms)

            now = time.perf_counter()
            result = tracker.latest()
            hands = result.hands if result else []
            tracking = len(hands) > 0

            cursor_px = None
            hands_px = None
            out = engine.update(hands, now)
            enabled = ui["gesture_enabled"]

            if tracking:
                hands_px = [[(int(p[0] * w), int(p[1] * h)) for p in hand]
                            for hand in hands]
                tip = hands[0][config.CURSOR_LANDMARK]  # thumb tip
                cursor_px = (int(tip[0] * w), int(tip[1] * h))

                if out.mode == "move" and drive and enabled["thumb"]:
                    cursor.update(tip[0], tip[1], now)
                elif out.mode == "scroll" and drive and enabled["two_finger"]:
                    cursor.scroll(out.scroll_steps)

                if out.minimize and enabled["flat_down"]:
                    if drive:
                        system_actions.minimize_all()
                    overlay.toast("Minimized")
                if out.restore and enabled["flat_up"]:
                    if drive:
                        system_actions.restore_all()
                    overlay.toast("Restored")
                if out.switch_window and enabled["flat_left"]:
                    if drive:
                        system_actions.switch_window()
                    overlay.toast("Switch window")
                if out.new_chat and enabled["shaka"]:
                    if drive:
                        system_actions.open_ai_chat()
                    overlay.toast("New chat")
            else:
                cursor.reset()

            # Button edges are handled outside the tracking branch: both a
            # pending click and a live drag outlive the hand by the trigger's
            # grace window, so their edges have to get through even with
            # nothing tracked.
            if out.click and enabled["point"]:
                if drive:
                    cursor.click()
                if cursor_px is not None:
                    overlay.flash_click(cursor_px)
            if out.press and drive and enabled["point_hold"]:
                cursor.press()
            # Not gated by enabled["point_hold"]: release() is a safe no-op
            # if the button isn't held, but if Drag gets disabled mid-hold
            # this still has to go through or the button is stuck down.
            if out.release and drive:
                cursor.release()

            if out.exit and enabled["cross"]:
                print("[fingerino] exit gesture — closing.")
                break

            frame = overlay.draw(
                frame,
                tracking=tracking,
                mode=out.mode,
                mode_label=out.mode_label,
                cursor_px=cursor_px,
                zone_px=_zone_px(w, h),
                hands_px=hands_px,
                exit_progress=out.exit_progress,
                dragging=out.dragging,
                drag_progress=out.drag_progress,
                debug=args.debug,
                fps=fps,
                menu_open=ui["menu_open"],
                gesture_enabled=ui["gesture_enabled"],
            )

            cv2.imshow(config.WINDOW_NAME, frame)
            if not pinned:
                # imshow is what actually creates the OS window, so the
                # property can only be set from here on.
                _pin_topmost(config.WINDOW_NAME)
                pinned = True

            if needs_access and now - last_access_t >= 2.0:
                last_access_t = now
                if macui.accessibility_trusted():
                    # macOS only hands the permission to a freshly started
                    # process, so say so rather than pretending it works now.
                    needs_access = False
                    _set_title_note(config.WINDOW_NAME, "restart to enable control")
                    overlay.toast("Permission granted — restart Fingerino")

            if hwnd is None:
                hwnd = _finalize_window(config.WINDOW_NAME)
                last_topmost_t = now
            elif (config.WINDOW_ALWAYS_ON_TOP
                  and now - last_topmost_t >= config.TOPMOST_REASSERT_S):
                # Other apps promoting themselves to topmost -- or, if one is
                # also marked always-on-top, simply being clicked -- can bury
                # us, so the claim is renewed on a real-time cadence rather
                # than set just once.
                winui.raise_above_all(hwnd)
                last_topmost_t = now

            dt = now - prev_t
            prev_t = now
            if dt > 0:
                fps = 0.9 * fps + 0.1 * (1.0 / dt) if fps else (1.0 / dt)

            key = cv2.waitKey(1) & 0xFF
            if key == 27:  # Esc
                break
            if key == 9:  # Tab
                ui["menu_open"] = not ui["menu_open"]
            if cv2.getWindowProperty(config.WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
                break
    finally:
        # First thing on every exit path, including the exit gesture and any
        # crash: never leave the user's mouse button held down.
        cursor.release()
        cap.release()
        cv2.destroyAllWindows()
        tracker.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

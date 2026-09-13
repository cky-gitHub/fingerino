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
    Hold      both palms up, held still ~1s — pauses every gesture; do it
              again to hand control back to exactly the same set
    Exit      cross both hands into an "X" and hold briefly

    fingerino            # normal, clean HUD          (or: python -m fingerino)
    fingerino --debug    # add raw skeleton + FPS
    fingerino --no-move  # track & show HUD but don't drive the OS
    fingerino --selftest # check the install without a camera, then exit

Tab opens/closes the gesture guide. Esc closes the guide if it's open,
otherwise quits (so does the Exit gesture).
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
from .ui_overlay import UIOverlay, panel_scale_for


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


def _finalize_window(name: str, client_w: int, client_h: int):
    """Apply icon, fixed size and always-on-top; return the HWND (or None).

    Win32 HighGUI creates the real OS window inside ``cv2.namedWindow`` — not
    on the first ``imshow``, as this used to claim — and the HWND is unchanged
    once frames start arriving. So this runs during setup rather than from the
    frame loop, and the HUD never flashes up bordered and unpinned while the
    camera warms up. A backend that really does defer creation returns None
    here and gets picked up by the retry in the loop instead.
    """
    hwnd = winui.find_own_window(name)
    if not hwnd:
        return None
    ico = branding.icon_path(cache_dir())
    winui.apply_icon(hwnd, ico)
    # Windows 11 takes the taskbar button's icon from the shell property
    # store rather than the window icon, so both are set.
    winui.set_taskbar_icon(hwnd, ico, _APP_ID, config.WINDOW_NAME)
    winui.lock_size(hwnd)
    winui.make_borderless(hwnd)
    # Both of the above pass SWP_NOSIZE, so removing the caption and frame
    # leaves the *window* rect untouched and the client area grows by what
    # the chrome used to occupy — which stretches the 16:9 preview until
    # something resizes the window again. Put the client area back.
    winui.resize_client(hwnd, client_w, client_h)
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

    if not winui.acquire_single_instance(_APP_ID):
        # A second copy left running behind the one you meant to close is
        # the usual reason the topmost pin outlives "closing the app".
        message = "Fingerino is already running."
        print(f"[fingerino] {message}", file=sys.stderr)
        winui.alert(config.WINDOW_NAME, message)
        return 0

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
    # The gesture panel scales separately, off the screen rather than the
    # camera, so the expanded window is always guaranteed to fit on the
    # display -- and drops to a single-line row density when there isn't the
    # height for descriptions.
    panel_scale, comfortable = panel_scale_for(cursor.screen_h, win_w, win_h)
    overlay = UIOverlay(ui_scale=ui_scale, panel_scale=panel_scale,
                        comfortable=comfortable)

    # The gesture guide renders on its own canvas and gets composited below
    # the camera preview when open, so the window has two sizes: this small
    # collapsed one, and a taller/wider "expanded" one computed once here.
    # expanded_layout()'s offsets are also reused below to place the panel's
    # (also static) hit-rects in window coordinates.
    layout = overlay.expanded_layout(win_w, win_h)
    exp_w, exp_h = layout["size"]
    panel_x, panel_y = layout["panel_xy"]
    close_lx1, close_ly1, close_lx2, close_ly2 = overlay.panel_close_rect(win_w)
    row_rects_local = overlay.panel_row_rects(win_w)

    print(f"[fingerino] screen {cursor.screen_w}x{cursor.screen_h} — "
          f"{'controlling OS' if drive else 'HUD only'}. Esc to quit.")

    cv2.namedWindow(config.WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(config.WINDOW_NAME, win_w, win_h)
    cv2.moveWindow(config.WINDOW_NAME, 0, 0)
    hwnd = _finalize_window(config.WINDOW_NAME, win_w, win_h)
    if needs_access:
        # A toast lasts a second; this has to stay visible, because until it
        # is fixed the app tracks perfectly and controls nothing.
        _set_title_note(config.WINDOW_NAME, "no Accessibility permission yet")

    # Mutable so the mouse callback can flip it. OpenCV reports click
    # coordinates in the space of whatever array was last shown -- the
    # collapsed camera frame (always CAMERA_WIDTH x CAMERA_HEIGHT) or the
    # expanded composite (always exp_w x exp_h) -- so the two sets of
    # hit-rects below, precomputed once in those two fixed coordinate
    # spaces, never need to be recomputed per frame.
    ui = {
        "menu_open": False,
        "tab_rect": overlay.collapsed_tab_rect(config.CAMERA_WIDTH, config.CAMERA_HEIGHT),
        "close_rect": (close_lx1 + panel_x, close_ly1 + panel_y,
                       close_lx2 + panel_x, close_ly2 + panel_y),
        "row_rects": [(x1 + panel_x, y1 + panel_y, x2 + panel_x, y2 + panel_y)
                      for x1, y1, x2, y2 in row_rects_local],
        # Per-gesture on/off, keyed by the icon id used throughout
        # GESTURE_TUTORIAL. Session-only -- resets to all-enabled on restart.
        "gesture_enabled": {icon: True for icon, _ in config.GESTURE_TUTORIAL},
        # Which row (index into GESTURE_TUTORIAL) the pointer is over, and
        # whether it's over the close button. The whole row has always been
        # clickable; highlighting it is what makes that visible.
        "hover_row": None,
        "hover_close": False,
        # The both-palms hold parks the whole session. Deliberately a mode of
        # its own rather than switching every row off: the per-gesture
        # choices above are left exactly as they were, so resuming brings
        # back the set that was live and nothing else.
        "paused": False,
    }

    def _live(icon: str) -> bool:
        """May this gesture act on this frame? Off if it's switched off in the
        guide, and off for everything while the session is paused."""
        return ui["gesture_enabled"][icon] and not ui["paused"]

    def _hit(rect, x, y) -> bool:
        x1, y1, x2, y2 = rect
        return x1 <= x <= x2 and y1 <= y <= y2

    def _on_mouse(event, x, y, flags, param):
        if event == cv2.EVENT_MOUSEMOVE:
            if not ui["menu_open"]:
                return
            ui["hover_close"] = _hit(ui["close_rect"], x, y)
            ui["hover_row"] = next(
                (i for i, r in enumerate(ui["row_rects"]) if _hit(r, x, y)), None)
            return
        if event != cv2.EVENT_LBUTTONDOWN:
            return
        if not ui["menu_open"]:
            if _hit(ui["tab_rect"], x, y):
                ui["menu_open"] = True
            return
        if _hit(ui["close_rect"], x, y):
            ui["menu_open"] = False
            return
        for (icon, _), rect in zip(config.GESTURE_TUTORIAL, ui["row_rects"]):
            if _hit(rect, x, y):
                ui["gesture_enabled"][icon] = not ui["gesture_enabled"][icon]
                return

    cv2.setMouseCallback(config.WINDOW_NAME, _on_mouse)

    pinned = False
    # Covers an abrupt close (console X button, logoff, shutdown) that skips
    # straight past the try/finally below -- reads `hwnd` via closure, so it
    # still works if the fallback in the loop is what ends up setting it.
    winui.install_console_handler(lambda: winui.unpin(hwnd))
    prev_menu_open = False
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

            # The master switch. Turning the pause *off* is never gated on
            # the row's own toggle -- switching Hold off while paused would
            # otherwise leave no gesture able to give control back.
            if out.hold_toggle and (ui["paused"] or ui["gesture_enabled"]["both_flat"]):
                ui["paused"] = not ui["paused"]
                if ui["paused"]:
                    # Never park the session with the button still down or a
                    # stale filter waiting to snap the cursor on resume.
                    if drive:
                        cursor.release()
                    cursor.reset()
                overlay.toast("Paused — gestures off" if ui["paused"] else "Resumed")

            if tracking:
                hands_px = [[(int(p[0] * w), int(p[1] * h)) for p in hand]
                            for hand in hands]
                tip = hands[0][config.CURSOR_LANDMARK]  # thumb tip
                cursor_px = (int(tip[0] * w), int(tip[1] * h))

                if out.mode == "move" and drive and _live("thumb"):
                    cursor.update(tip[0], tip[1], now)
                elif out.mode == "scroll" and drive and _live("two_finger"):
                    cursor.scroll(out.scroll_steps)

                if out.minimize and _live("flat_down"):
                    if drive:
                        system_actions.minimize_all()
                    overlay.toast("Minimized")
                if out.restore and _live("flat_up"):
                    if drive:
                        system_actions.restore_all()
                    overlay.toast("Restored")
                if out.switch_window and _live("flat_left"):
                    if drive:
                        system_actions.switch_window()
                    overlay.toast("Switch window")
                if out.new_chat and _live("shaka"):
                    if drive:
                        system_actions.open_ai_chat()
                    overlay.toast("New chat")
            else:
                cursor.reset()

            # Button edges are handled outside the tracking branch: both a
            # pending click and a live drag outlive the hand by the trigger's
            # grace window, so their edges have to get through even with
            # nothing tracked.
            if out.click and _live("point"):
                if drive:
                    cursor.click()
                if cursor_px is not None:
                    overlay.flash_click(cursor_px)
            if out.press and drive and _live("point_hold"):
                cursor.press()
            # Not gated by _live("point_hold"): release() is a safe no-op if
            # the button isn't held, but if Drag gets disabled -- or the
            # session paused -- mid-hold this still has to go through or the
            # button is stuck down.
            if out.release and drive:
                cursor.release()

            if out.exit and _live("cross"):
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
                paused=ui["paused"],
                hold_progress=out.hold_progress,
            )

            # The gesture guide has its own canvas and gets composited below
            # the camera preview, so the window has to grow/shrink to fit --
            # only on the open/close transition, not every frame.
            if ui["menu_open"] != prev_menu_open:
                tgt_w, tgt_h = ((exp_w, exp_h) if ui["menu_open"]
                                else (win_w, win_h))
                cv2.resizeWindow(config.WINDOW_NAME, tgt_w, tgt_h)
                if hwnd:
                    # Authoritative once the window is borderless: sets the
                    # client area directly rather than trusting HighGUI's
                    # idea of how much chrome to allow for.
                    winui.resize_client(hwnd, tgt_w, tgt_h)
                # Borderless + no resize grip means the window can't drift
                # from here on its own, but reassert it defensively anyway.
                cv2.moveWindow(config.WINDOW_NAME, 0, 0)
                if not ui["menu_open"]:
                    ui["hover_row"] = None
                    ui["hover_close"] = False
                prev_menu_open = ui["menu_open"]

            if ui["menu_open"]:
                cam_disp = cv2.resize(frame, (win_w, win_h), interpolation=cv2.INTER_AREA)
                panel_img = overlay.render_gesture_panel(
                    ui["gesture_enabled"], win_w,
                    hover_row=ui["hover_row"], hover_close=ui["hover_close"],
                    paused=ui["paused"])
                shown = overlay.compose_expanded(cam_disp, panel_img, layout)
            else:
                shown = frame

            cv2.imshow(config.WINDOW_NAME, shown)
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
                # Only reached on a HighGUI backend that defers window
                # creation to the first imshow(); the Win32 one does not.
                hwnd = _finalize_window(config.WINDOW_NAME, win_w, win_h)
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
            if key == 27:  # Esc: close the guide first if it's open, else quit
                if ui["menu_open"]:
                    ui["menu_open"] = False
                else:
                    break
            if key == 9:  # Tab
                ui["menu_open"] = not ui["menu_open"]
            if cv2.getWindowProperty(config.WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
                break
    finally:
        # First thing on every exit path, including the exit gesture and any
        # crash: never leave the user's mouse button held down.
        cursor.release()
        # Before destroyAllWindows(), while the handle is still live. If it
        # isn't, _owned() rejects it and this no-ops rather than poking at
        # whatever window Windows may have recycled the handle to.
        winui.unpin(hwnd)
        cap.release()
        cv2.destroyAllWindows()
        tracker.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

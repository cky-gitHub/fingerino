"""Fingerino — webcam hand-tracking mouse.

Gestures (one hand unless noted):
    Move      thumb tip drives the cursor
    Click     point (index out, middle in)
    Scroll    two fingers out (index + middle), move the hand up / down
    Minimize  flat hand swiped down    Restore  flat hand swiped up
    Switch    flat hand swiped left (Alt+Tab)
    New chat  shaka sign (thumb + pinky out)
    Exit      cross both hands into an "X" and hold briefly

    fingerino            # normal, clean HUD          (or: python -m fingerino)
    fingerino --debug    # add raw skeleton + FPS
    fingerino --no-move  # track & show HUD but don't drive the OS

Esc quits (so does the Exit gesture).
"""

from __future__ import annotations

import argparse
import sys
import time

import cv2
import numpy as np

from . import config
from . import system_actions
from .cursor_controller import CursorController
from .gesture_detector import GestureEngine
from .hand_tracker import HandTracker
from .ui_overlay import UIOverlay


def _open_camera(index: int) -> cv2.VideoCapture:
    # CAP_DSHOW starts noticeably faster than the default backend on Windows.
    backend = cv2.CAP_DSHOW if sys.platform.startswith("win") else 0
    cap = cv2.VideoCapture(index, backend)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.CAMERA_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.CAMERA_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, 30)
    return cap


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
    args = parser.parse_args()

    cap = _open_camera(args.camera)
    if not cap.isOpened():
        print(f"[fingerino] could not open camera {args.camera}", file=sys.stderr)
        return 1

    tracker = HandTracker()
    cursor = CursorController()
    engine = GestureEngine()
    overlay = UIOverlay()
    drive = not args.no_move

    print(f"[fingerino] screen {cursor.screen_w}x{cursor.screen_h} — "
          f"{'controlling OS' if drive else 'HUD only'}. Esc to quit.")

    cv2.namedWindow(config.WINDOW_NAME, cv2.WINDOW_AUTOSIZE)

    last_ts_ms = 0
    fps = 0.0
    prev_t = time.perf_counter()

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

            if tracking:
                hands_px = [[(int(p[0] * w), int(p[1] * h)) for p in hand]
                            for hand in hands]
                tip = hands[0][config.CURSOR_LANDMARK]  # thumb tip
                cursor_px = (int(tip[0] * w), int(tip[1] * h))

                if out.mode == "move" and drive:
                    cursor.update(tip[0], tip[1], now)
                elif out.mode == "scroll" and drive:
                    cursor.scroll(out.scroll_steps)

                if out.click:
                    if drive:
                        cursor.click()
                    overlay.flash_click(cursor_px)

                if out.minimize:
                    if drive:
                        system_actions.minimize_all()
                    overlay.toast("Minimized")
                if out.restore:
                    if drive:
                        system_actions.restore_all()
                    overlay.toast("Restored")
                if out.switch_window:
                    if drive:
                        system_actions.switch_window()
                    overlay.toast("Switch window")
                if out.new_chat:
                    if drive:
                        system_actions.open_ai_chat()
                    overlay.toast("New chat")
            else:
                cursor.reset()

            if out.exit:
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
                debug=args.debug,
                fps=fps,
            )

            cv2.imshow(config.WINDOW_NAME, frame)

            dt = now - prev_t
            prev_t = now
            if dt > 0:
                fps = 0.9 * fps + 0.1 * (1.0 / dt) if fps else (1.0 / dt)

            key = cv2.waitKey(1) & 0xFF
            if key == 27:  # Esc
                break
            if cv2.getWindowProperty(config.WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()
        tracker.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

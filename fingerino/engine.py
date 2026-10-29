"""One tracking session: camera in, cursor and shortcuts out.

shell.py runs a Session on a background thread when tracking starts and asks
it to stop when tracking stops, so the Home window and the HUD stay smooth
whatever the camera and MediaPipe are doing. Nothing here touches Qt: finished
HUD frames and state changes go out through callbacks, and the caller decides
where to show them.

The gesture handling in run() is the loop that used to live in main.py,
unchanged apart from where its frames go.
"""

from __future__ import annotations

import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

import cv2
import numpy as np

from . import config, macui, system_actions
from .cursor_controller import CursorController
from .gesture_detector import GestureEngine, cursor_point
from .hand_tracker import HandTracker
from .ui_overlay import UIOverlay


@dataclass
class Options:
    camera: int = config.CAMERA_INDEX
    drive: bool = True          # False: track and draw, never touch the OS
    debug: bool = False         # raw skeleton + FPS on the HUD
    # Physical pixel size of the HUD. Frames are delivered at this size, and
    # the HUD chrome is scaled so it reads the same at any HUD size.
    preview_size: tuple[int, int] = (480, 270)


def open_camera(index: int) -> cv2.VideoCapture:
    # CAP_DSHOW starts noticeably faster than the default backend on Windows.
    backend = cv2.CAP_DSHOW if sys.platform.startswith("win") else 0
    cap = cv2.VideoCapture(index, backend)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.CAMERA_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.CAMERA_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, 30)
    return cap


def _screen_to_frame_px(cursor, sx: int, sy: int, w: int, h: int) -> tuple[int, int]:
    """Invert the control-zone mapping: screen pixels back to frame pixels.

    The HUD draws in camera-frame space while the anchored click position is
    worked out in screen space, so showing the user where a click will really
    land means coming back the other way.
    """
    zx = sx / max(cursor.screen_w - 1, 1)
    zy = sy / max(cursor.screen_h - 1, 1)
    nx = zx * (1.0 - 2 * config.CONTROL_ZONE_X_MARGIN) + config.CONTROL_ZONE_X_MARGIN
    ny = zy * (1.0 - 2 * config.CONTROL_ZONE_Y_MARGIN) + config.CONTROL_ZONE_Y_MARGIN
    return int(nx * w), int(ny * h)


def _anchored_frame_px(cursor, anchor_t: float | None, w: int, h: int):
    """Where a button with this anchor will actually land, in frame pixels.

    None when anchoring is off, when there is no anchor, or when the position
    is no longer in the cursor's history — in each of which cases the caller
    falls back to the live position, which is what used to happen always.
    """
    if not config.CLICK_ANCHOR or anchor_t is None:
        return None
    pos = cursor.anchor_at(anchor_t - config.CLICK_ANCHOR_LOOKBACK_S)
    if pos is None:
        return None
    return _screen_to_frame_px(cursor, pos[0], pos[1], w, h)


def _zone_px(w: int, h: int) -> tuple[int, int, int, int]:
    x1 = int(config.CONTROL_ZONE_X_MARGIN * w)
    x2 = int((1.0 - config.CONTROL_ZONE_X_MARGIN) * w)
    y1 = int(config.CONTROL_ZONE_Y_MARGIN * h)
    y2 = int((1.0 - config.CONTROL_ZONE_Y_MARGIN) * h)
    return x1, y1, x2, y2


class Session:
    """Track until stopped. Single use: start a new one to track again."""

    def __init__(self, options: Options, gestures: dict[str, bool]) -> None:
        self.options = options
        # Shared with the Home window, which flips entries from the UI
        # thread. Only ever read here, one bool at a time.
        self.gestures = gestures
        self.paused = False
        self._pause_request = threading.Event()
        self._stop = threading.Event()

    # -- called from other threads -----------------------------------------

    def toggle_pause(self) -> None:
        """Pause or resume at the next frame, on the session's own thread, so
        releasing a held button happens where the button is driven."""
        self._pause_request.set()

    def stop(self) -> None:
        self._stop.set()

    # -- the loop ------------------------------------------------------------

    def run(self, on_frame: Callable[[np.ndarray], None],
            on_state: Callable[[bool, bool], None]) -> str | None:
        """Track until stop() or the Exit gesture.

        ``on_frame`` gets each finished HUD frame (BGR, ``preview_size``);
        ``on_state`` gets ``(paused, hand_seen)`` whenever either changes.
        Returns None on a normal stop, or a message saying what went wrong.
        """
        opts = self.options
        drive = opts.drive

        # macOS drops synthetic input on the floor until Accessibility is
        # granted, so ask before tracking starts rather than looking broken.
        needs_access = drive and not macui.accessibility_trusted()
        if needs_access:
            macui.warn_missing_accessibility()

        cap = open_camera(opts.camera)
        if not cap.isOpened():
            cap.release()
            return (f"Could not open camera {opts.camera}. Another app may be "
                    "using it, or it may be on a different index — try "
                    "starting Fingerino with --camera 1.")

        tracker = HandTracker()
        cursor = CursorController()
        engine = GestureEngine()
        out_w, out_h = opts.preview_size
        # The frame is drawn at native camera resolution then shrunk to the
        # HUD, so HUD sizes must be inflated by this ratio to stay legible.
        overlay = UIOverlay(ui_scale=config.CAMERA_WIDTH / max(out_w, 1))
        if needs_access:
            overlay.toast("Allow Accessibility to control the mouse")

        def _live(icon: str) -> bool:
            """May this gesture act on this frame? Off if it's switched off in
            Home, and off for everything while the session is paused."""
            return self.gestures.get(icon, True) and not self.paused

        def _toggle_pause() -> None:
            self.paused = not self.paused
            if self.paused:
                # Never park the session with the button still down or a
                # stale filter waiting to snap the cursor on resume.
                if drive:
                    cursor.release()
                cursor.reset()
            overlay.toast("Paused — gestures off" if self.paused else "Resumed")

        error: str | None = None
        last_state: tuple[bool, bool] | None = None
        last_access_t = 0.0
        last_ts_ms = 0
        fps = 0.0
        prev_t = time.perf_counter()

        try:
            while not self._stop.is_set():
                ok, frame = cap.read()
                if not ok:
                    error = "The camera stopped sending frames."
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
                if out.hold_toggle and (self.paused or self.gestures.get("both_flat", True)):
                    _toggle_pause()
                if self._pause_request.is_set():
                    self._pause_request.clear()
                    _toggle_pause()

                if tracking:
                    hands_px = [[(int(p[0] * w), int(p[1] * h)) for p in hand]
                                for hand in hands]
                    tip = cursor_point(hands[0])
                    cursor_px = (int(tip[0] * w), int(tip[1] * h))

                    # While a point is pending the user is committing to a target,
                    # not still aiming at one -- so the cursor stops here. Without
                    # it, extending the finger reshapes the hand and drags the aim
                    # off the thing being aimed at. Tracking resumes the moment
                    # the point latches into a drag.
                    committing = config.FREEZE_WHILE_AIMING and out.aiming
                    if out.mode == "move" and drive and _live("thumb") and not committing:
                        cursor.update(tip[0], tip[1], now)

                    # Show the committed point rather than the hand's live
                    # position, so the reticle stops where the click will land
                    # instead of drifting off it while the finger extends.
                    if out.aiming:
                        aimed = _anchored_frame_px(cursor, out.aim_anchor_t, w, h)
                        if aimed is not None:
                            cursor_px = aimed
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
                        cursor.click(out.anchor_t)
                    flash_px = _anchored_frame_px(cursor, out.anchor_t, w, h) or cursor_px
                    if flash_px is not None:
                        overlay.flash_click(flash_px)
                if out.press and drive and _live("point_hold"):
                    cursor.press(out.anchor_t)
                # Not gated by _live("point_hold"): release() is a safe no-op if
                # the button isn't held, but if Drag gets disabled -- or the
                # session paused -- mid-hold this still has to go through or the
                # button is stuck down.
                if out.release and drive:
                    cursor.release()

                if out.exit and _live("cross"):
                    print("[fingerino] exit gesture — stopping.")
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
                    debug=opts.debug,
                    fps=fps,
                    paused=self.paused,
                    hold_progress=out.hold_progress,
                )
                on_frame(cv2.resize(frame, (out_w, out_h), interpolation=cv2.INTER_AREA))

                state = (self.paused, tracking)
                if state != last_state:
                    on_state(*state)
                    last_state = state

                if needs_access and now - last_access_t >= 2.0:
                    last_access_t = now
                    if macui.accessibility_trusted():
                        # macOS only hands the permission to a freshly started
                        # process, so say so rather than pretending it works now.
                        needs_access = False
                        overlay.toast("Permission granted — restart Fingerino")

                dt = now - prev_t
                prev_t = now
                if dt > 0:
                    fps = 0.9 * fps + 0.1 * (1.0 / dt) if fps else (1.0 / dt)
        finally:
            # First thing on every exit path, including the exit gesture and
            # any crash: never leave the user's mouse button held down.
            cursor.release()
            cap.release()
            tracker.close()
        return error

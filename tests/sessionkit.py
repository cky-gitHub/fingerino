"""Run a real engine.Session against a scripted, camera-free world.

The camera, the hand tracker, the mouse and the keyboard are replaced by
fakes; everything between them -- the gesture engine, the registry, the
pause and gating logic, the HUD drawing -- is the real code. Time is a fake
clock advanced one frame (1/30 s) per camera read, so holds and cooldowns
behave as they would live, without the test taking real seconds.
"""

from __future__ import annotations

import types

import numpy as np

from fingerino import config, engine
from fingerino.hand_tracker import HandResult

FPS = 30


class World:
    def __init__(self, frames, stop_at=None):
        self.frames = list(frames)            # per frame: list of hands
        self.i = -1
        self.t = 100.0
        self.stop_at = len(self.frames) if stop_at is None else stop_at
        self.session = None
        self.cursor_calls = []
        self.actions = []
        self.toasts = []
        self.frames_out = 0
        self.on_frame_hook = None             # called with the frame index

    # -- camera ---------------------------------------------------------------
    def open_camera(self, index):
        world = self

        class Cap:
            def isOpened(self):
                return True

            def read(self):
                world.i += 1
                world.t += 1 / FPS
                if world.i >= world.stop_at:
                    world.session.stop()
                frame = np.zeros((config.CAMERA_HEIGHT, config.CAMERA_WIDTH, 3), np.uint8)
                return True, frame

            def release(self):
                pass

        return Cap()

    # -- tracker --------------------------------------------------------------
    def tracker(self):
        world = self

        class Tracker:
            def submit(self, rgb, ts):
                pass

            def latest(self):
                if 0 <= world.i < len(world.frames) and world.frames[world.i]:
                    return HandResult(hands=world.frames[world.i], timestamp_ms=0)
                return None

            def close(self):
                pass

        return Tracker()

    # -- mouse ----------------------------------------------------------------
    def cursor(self):
        world = self

        class Cursor:
            screen_w, screen_h = 1920, 1080

            def __getattr__(self, name):
                def call(*args):
                    world.cursor_calls.append((name, *args))
                return call

            def anchor_at(self, t):
                return None

        return Cursor()


def run(monkeypatch, frames, prefs=None, *, drive=True, hook=None, registry=None):
    """Run a session over ``frames``; return the World with what happened."""
    world = World(frames)
    world.on_frame_hook = hook
    monkeypatch.setattr(engine, "open_camera", world.open_camera)
    monkeypatch.setattr(engine, "HandTracker", world.tracker)
    monkeypatch.setattr(engine, "CursorController", world.cursor)
    monkeypatch.setattr(engine, "time", types.SimpleNamespace(perf_counter=lambda: world.t))
    monkeypatch.setattr(engine.macui, "accessibility_trusted", lambda: True)

    def perform(action):
        world.actions.append(action.id)

    monkeypatch.setattr(engine, "perform_action", perform, raising=False)
    original_toast = engine.UIOverlay.toast

    def toast(self, text):
        world.toasts.append(text)
        original_toast(self, text)

    monkeypatch.setattr(engine.UIOverlay, "toast", toast)

    from fingerino import settings
    session = engine.Session(engine.Options(drive=drive), prefs or settings.Settings(),
                             registry)
    world.session = session

    def on_frame(frame):
        world.frames_out += 1
        if world.on_frame_hook:
            world.on_frame_hook(world, session)

    world.error = session.run(on_frame, lambda paused, seen: None)
    return world


def steady(hands, seconds):
    return [hands] * round(seconds * FPS)

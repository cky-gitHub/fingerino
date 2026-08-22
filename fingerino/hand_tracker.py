"""Thin wrapper around MediaPipe's Tasks API HandLandmarker.

Runs in LIVE_STREAM mode: frames are pushed in with :meth:`HandTracker.submit`
and results arrive on a background thread, which we stash so the main loop can
read the most recent landmarks without blocking.

The landmark model (~7 MB) is shipped inside the packaged app, but not inside
the Python package. When it isn't found alongside the code it is downloaded
once on first run into a per-user cache directory and reused thereafter.
"""

from __future__ import annotations

import os
import sys
import threading
import urllib.request
from dataclasses import dataclass

import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

from . import config

_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/1/hand_landmarker.task"
)


@dataclass
class HandResult:
    """A single frame's worth of tracking, in frame-normalized coordinates."""

    hands: list[list[tuple[float, float, float]]]  # per hand: 21 (x,y,z), 0..1
    timestamp_ms: int


def _cache_dir() -> str:
    """Per-user cache directory for the downloaded model."""
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Caches")
    else:
        base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    path = os.path.join(base, "fingerino")
    os.makedirs(path, exist_ok=True)
    return path


def cache_dir() -> str:
    """Public alias — other modules cache generated assets alongside the model."""
    return _cache_dir()


def _default_model_path() -> str:
    """Resolve the model location.

    Order: ``FINGERINO_MODEL`` env override, a model bundled beside the package
    (if a maintainer shipped one), else the per-user cache download target.
    """
    override = os.environ.get("FINGERINO_MODEL")
    if override:
        return override
    if getattr(sys, "frozen", False):
        # PyInstaller unpacks the bundled model beside the package in _MEIPASS.
        packaged = os.path.join(getattr(sys, "_MEIPASS", ""), "fingerino",
                                config.MODEL_FILENAME)
        if os.path.exists(packaged):
            return packaged
    bundled = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           config.MODEL_FILENAME)
    if os.path.exists(bundled):
        return bundled
    return os.path.join(_cache_dir(), config.MODEL_FILENAME)


_last_pct_shown = -1


def _out(text: str) -> None:
    """Write to stdout if there is one.

    A packaged app is built without a console, so ``sys.stdout`` is ``None``
    and writing to it directly raises. ``print`` already tolerates that; the
    progress bar needs partial writes, so it goes through here instead.
    """
    stream = sys.stdout
    if stream is None:
        return
    stream.write(text)
    stream.flush()


def _report_progress(block_count: int, block_size: int, total_size: int) -> None:
    global _last_pct_shown
    done = block_count * block_size
    if total_size > 0:
        done = min(done, total_size)
        pct = done * 100 // total_size
        if pct == _last_pct_shown and done < total_size:
            return  # skip redundant redraws — flushing on every 8 KB block stalls the download
        _last_pct_shown = pct
        bar_width = 30
        filled = bar_width * done // total_size
        bar = "#" * filled + "-" * (bar_width - filled)
        _out(
            f"\r[fingerino] downloading model [{bar}] {pct:3d}% "
            f"({done / 1e6:.1f}/{total_size / 1e6:.1f} MB)"
        )
    else:
        _out(f"\r[fingerino] downloading model ({done / 1e6:.1f} MB)")


def _ensure_model(path: str) -> None:
    if os.path.exists(path):
        return
    global _last_pct_shown
    _last_pct_shown = -1
    print(f"[fingerino] downloading hand model (~7 MB) to {path} ...")
    tmp = path + ".part"
    try:
        urllib.request.urlretrieve(_MODEL_URL, tmp, reporthook=_report_progress)
    finally:
        _out("\n")
    os.replace(tmp, path)                          # so a partial file is never used
    print("[fingerino] model ready.")


class HandTracker:
    """Feeds frames to HandLandmarker and exposes the latest result."""

    def __init__(self, model_path: str | None = None) -> None:
        model_path = model_path or _default_model_path()
        _ensure_model(model_path)
        self.model_path = model_path        # reported by --selftest

        self._lock = threading.Lock()
        self._latest: HandResult | None = None

        options = vision.HandLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=model_path),
            running_mode=vision.RunningMode.LIVE_STREAM,
            num_hands=config.NUM_HANDS,
            min_hand_detection_confidence=config.MIN_HAND_DETECTION_CONFIDENCE,
            min_hand_presence_confidence=config.MIN_HAND_PRESENCE_CONFIDENCE,
            min_tracking_confidence=config.MIN_TRACKING_CONFIDENCE,
            result_callback=self._on_result,
        )
        self._landmarker = vision.HandLandmarker.create_from_options(options)

    def _on_result(self, result, output_image, timestamp_ms: int) -> None:  # noqa: ANN001
        """LIVE_STREAM callback (runs on a MediaPipe worker thread)."""
        if result.hand_landmarks:
            hands = [
                [(lm.x, lm.y, lm.z) for lm in hand] for hand in result.hand_landmarks
            ]
            with self._lock:
                self._latest = HandResult(hands=hands, timestamp_ms=timestamp_ms)
        else:
            with self._lock:
                self._latest = None

    def submit(self, rgb_frame, timestamp_ms: int) -> None:
        """Push a frame (contiguous RGB uint8 array) for asynchronous detection.

        ``timestamp_ms`` must strictly increase between calls.
        """
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        self._landmarker.detect_async(mp_image, timestamp_ms)

    def latest(self) -> HandResult | None:
        """Most recent detection, or ``None`` if no hand is currently tracked."""
        with self._lock:
            return self._latest

    def close(self) -> None:
        self._landmarker.close()

    def __enter__(self) -> "HandTracker":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

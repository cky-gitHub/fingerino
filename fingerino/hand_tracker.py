"""Thin wrapper around MediaPipe's Tasks API HandLandmarker.

Runs in LIVE_STREAM mode: frames are pushed in with :meth:`HandTracker.submit`
and results arrive on a background thread, which we stash so the main loop can
read the most recent landmarks without blocking.

The landmark model (~7 MB) is shipped inside the packaged app, but not inside
the Python package. When it isn't found alongside the code it is downloaded
once on first run into a per-user cache directory and reused thereafter.
"""

from __future__ import annotations

import hashlib
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
# SHA-256 of the exact blob _MODEL_URL serves, verified against the CDN.
# These bytes are parsed by MediaPipe's TFLite interpreter in native code, so
# "whatever that URL returns today" is not a safe input. HTTPS protects the
# transfer; this pin is what protects against the artifact itself changing.
# Bump it deliberately, together with the URL, when moving to a new model.
_MODEL_SHA256 = "fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1"

# Applies per socket operation, not to the download as a whole. Without one,
# a connection that opens and then stalls hangs startup forever -- and a
# packaged build has no console, so the app just never appears.
_DOWNLOAD_TIMEOUT_S = 30
_BLOCK = 1 << 16


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

    Order: a model bundled beside the package (if a maintainer shipped one),
    else the per-user cache download target. The ``FINGERINO_MODEL`` override
    is handled by :class:`HandTracker` instead of here, because a path the
    caller named deliberately is exempt from the digest check.
    """
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


def _report_progress(done: int, total_size: int) -> None:
    global _last_pct_shown
    if total_size > 0:
        done = min(done, total_size)
        pct = done * 100 // total_size
        if pct == _last_pct_shown and done < total_size:
            return  # skip redundant redraws — flushing on every block stalls the download
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


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _download(url: str, dest: str) -> str:
    """Stream ``url`` into ``dest``; return the SHA-256 of what arrived.

    Streamed by hand rather than handed to ``urllib.request.urlretrieve``
    because that takes no timeout -- see _DOWNLOAD_TIMEOUT_S. Hashing the
    blocks on the way past also means the file never has to be read back.
    """
    digest = hashlib.sha256()
    done = 0
    with urllib.request.urlopen(url, timeout=_DOWNLOAD_TIMEOUT_S) as response:
        total = int(response.headers.get("Content-Length") or 0)
        with open(dest, "wb") as fh:
            while True:
                block = response.read(_BLOCK)
                if not block:
                    break
                fh.write(block)
                digest.update(block)
                done += len(block)
                _report_progress(done, total)
    return digest.hexdigest()


def _ensure_model(path: str, *, refetch: bool = False) -> None:
    """Put a model matching the pinned digest at ``path``.

    The digest is checked on every start, not only when the file is first
    written: a cache directory is user-writable, so what we downloaded last
    week is not necessarily what is sitting there today, and hashing 7 MB
    costs a few milliseconds against a MediaPipe startup measured in
    hundreds.

    ``refetch`` says whether a bad file may be replaced. True for a copy we
    downloaded ourselves; false for one bundled inside an install, because
    that came from the installer and quietly downloading over the top of it
    would paper over exactly the problem this check exists to find.
    """
    if os.path.exists(path):
        actual = _sha256(path)
        if actual == _MODEL_SHA256:
            return
        if not refetch:
            raise RuntimeError(
                f"the bundled hand model at {path} does not match its "
                f"expected checksum (got {actual}, expected {_MODEL_SHA256}). "
                "This installation is damaged or has been modified — "
                "reinstall Fingerino from the official releases page."
            )
        print("[fingerino] cached model failed its checksum — refetching.",
              file=sys.stderr)
        os.remove(path)

    global _last_pct_shown
    _last_pct_shown = -1
    print(f"[fingerino] downloading hand model (~7 MB) to {path} ...")
    tmp = path + ".part"
    try:
        actual = _download(_MODEL_URL, tmp)
    finally:
        _out("\n")
    if actual != _MODEL_SHA256:
        os.remove(tmp)
        raise RuntimeError(
            "the downloaded hand model does not match its expected checksum "
            f"(got {actual}, expected {_MODEL_SHA256}). It has been "
            "discarded. A proxy or captive portal that rewrites downloads is "
            "the usual cause; check your connection and try again."
        )
    os.replace(tmp, path)        # atomic: a partial file is never left behind
    print("[fingerino] model ready.")


class HandTracker:
    """Feeds frames to HandLandmarker and exposes the latest result."""

    def __init__(self, model_path: str | None = None) -> None:
        # A path the caller named -- constructor argument or FINGERINO_MODEL
        # -- is a deliberate choice (a newer model, a local experiment), so it
        # is taken as given and never checked against the pin. The locations
        # we pick ourselves are the ones that have to be verified.
        chosen = model_path or os.environ.get("FINGERINO_MODEL")
        if chosen:
            if not os.path.exists(chosen):
                raise FileNotFoundError(f"no hand model at {chosen}")
            self.model_path = chosen                # reported by --selftest
        else:
            self.model_path = _default_model_path()
            # Only the copy in our own cache may be replaced on a mismatch.
            cache_copy = os.path.join(_cache_dir(), config.MODEL_FILENAME)
            _ensure_model(self.model_path, refetch=(
                os.path.abspath(self.model_path) == os.path.abspath(cache_copy)))
        model_path = self.model_path

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

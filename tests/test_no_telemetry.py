"""Fingerino promises no network request besides the one-time model download.

MediaPipe's PyPI builds from 0.10.35 on carry Google's "Clearcut" telemetry
uploader (to play.googleapis.com), with no switch to turn it off
(google-ai-edge/mediapipe#6291). pyproject.toml pins MediaPipe below it; this
checks the MediaPipe that is actually installed (and so the one a build would
bundle), so the promise can't break silently through an upgrade.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

# Strings that only the telemetry uploader puts in the native library.
_MARKERS = (b"portable_clearcut_uploader", b"play.googleapis.com")


def _native_libraries() -> list[Path]:
    spec = importlib.util.find_spec("mediapipe")
    if spec is None or not spec.submodule_search_locations:
        pytest.skip("mediapipe is not installed")
    root = Path(next(iter(spec.submodule_search_locations)))
    libs = [p for p in root.rglob("*") if p.suffix in (".dll", ".so", ".dylib", ".pyd")]
    assert libs, f"no native libraries found under {root}"
    return libs


def test_installed_mediapipe_has_no_telemetry_uploader():
    found = {}
    for lib in _native_libraries():
        data = lib.read_bytes()
        hits = [m.decode() for m in _MARKERS if m in data]
        if hits:
            found[str(lib)] = hits
    assert not found, (
        "this MediaPipe build contains Google's telemetry uploader, which "
        f"breaks Fingerino's no-network promise: {found}. Install mediapipe<=0.10.33."
    )


def test_the_pin_stays_below_the_telemetry_builds():
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    assert '"mediapipe>=0.10.9,<=0.10.33"' in pyproject.read_text(encoding="utf-8")
    # What the release build actually installs (see requirements-build.txt).
    build = pyproject.with_name("requirements-build.txt").read_text(encoding="utf-8")
    assert "
mediapipe==0.10.33
" in build

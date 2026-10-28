"""THIRD-PARTY-NOTICES.md generation.

The licences of what Fingerino redistributes require their text to ship with
the installers. Nothing else in CI runs a real build, so without this a broken
generator would first be noticed at release time — by which point the
installers are already wrong.
"""

import importlib.metadata as md
import importlib.util
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
NOTICES_PY = ROOT / "packaging" / "notices.py"

# The generator reads licence text out of installed distribution metadata, so
# it can only be exercised where the bundled packages are actually installed.
# That is the Windows CI job and any dev machine; the fast Linux job installs
# nothing but the tooling and skips this file.
for _needed in ("mediapipe", "opencv-python", "pynput"):
    try:
        md.distribution(_needed)
    except md.PackageNotFoundError:
        pytest.skip(f"{_needed} is not installed; nothing to read licences from",
                    allow_module_level=True)


def _load():
    spec = importlib.util.spec_from_file_location("notices", NOTICES_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


notices = _load()


@pytest.fixture(scope="module")
def document():
    return notices.render()


def test_the_pinned_set_is_what_gets_documented():
    names = notices._bundled_packages()
    assert "mediapipe" in names
    assert "pynput" in names
    # Build tooling does not ship inside the app, so it is not redistributed.
    assert not any(n.startswith("pyinstaller") for n in names)


@pytest.mark.parametrize("required", [
    "mediapipe",        # Apache-2.0, section 4(d)
    "pynput",           # LGPL-3.0
    "opencv",           # Apache-2.0, and carries FFmpeg's licence
    "Inter",            # SIL OFL
])
def test_every_component_with_an_obligation_appears(document, required):
    assert required.lower() in document.lower()


@pytest.mark.parametrize("text", [
    "LESSER GENERAL PUBLIC LICENSE",     # pynput
    "SIL OPEN FONT LICENSE",             # Inter
    "Apache License",                    # MediaPipe, OpenCV
])
def test_the_licence_text_itself_is_embedded(document, text):
    # A link is not enough — these licences want the text to travel with the
    # thing they cover.
    assert text in document


def test_the_lgpl_relink_position_is_stated(document):
    # The LGPL asks that a user be able to replace the component. Fingerino
    # answers that by being open source and buildable; say so explicitly.
    assert "LGPL" in document
    assert "requirements-build.txt" in document
    assert "github.com/cky-gitHub/fingerino" in document


def test_ffmpeg_is_accounted_for(document):
    # Not a pip package, so it has no section of its own; it rides along in
    # OpenCV's LICENSE-3RD-PARTY.txt and must still be named.
    assert "FFmpeg" in document


def test_code_fences_stay_balanced(document):
    # A licence containing backticks would otherwise break out of its block
    # and spill into the document as markdown.
    assert document.count("```") % 2 == 0


def test_identical_licences_are_quoted_once(document):
    # opencv-python and opencv-contrib-python ship the same 180 KB file.
    assert "is identical to the copy shipped with" in document


def test_write_produces_a_file(tmp_path):
    out = tmp_path / "THIRD-PARTY-NOTICES.md"
    notices.write(str(out))
    assert out.stat().st_size > 10_000

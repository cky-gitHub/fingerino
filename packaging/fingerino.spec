# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — builds the double-clickable Fingerino app.

Windows -> dist/Fingerino/Fingerino.exe   (one folder; fast to start)
macOS   -> dist/Fingerino.app             (bundle, with camera-usage plist)

Driven by packaging/build.py, which prepares the icons and the bundled model
first. Run it rather than invoking pyinstaller directly.

Environment switches (set by build.py):
    FINGERINO_CONSOLE=1   keep a console window attached (debug builds)
"""

import glob
import os
import sys

from PyInstaller.utils.hooks import collect_all

PACKAGING = SPECPATH
ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir))
IS_WIN = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"

sys.path.insert(0, ROOT)
from fingerino import __version__ as VERSION  # noqa: E402

datas, binaries, hiddenimports = [], [], []

# MediaPipe loads graph configs and .tflite blobs from its package directory at
# runtime, and its bindings are a compiled extension — collect_all is the only
# reliable way to catch data, libraries and submodules in one go.
for _pkg in ("mediapipe",):
    _d, _b, _h = collect_all(_pkg)
    datas += _d
    binaries += _b
    hiddenimports += _h

# pynput selects its backend with a runtime __import__, which the analyser
# cannot follow, so the platform backend has to be named explicitly.
if IS_WIN:
    hiddenimports += ["pynput.keyboard._win32", "pynput.mouse._win32"]
elif IS_MAC:
    hiddenimports += ["pynput.keyboard._darwin", "pynput.mouse._darwin"]

# Ship the hand-landmark model inside the bundle: a packaged app has no console
# to show download progress on, and it should work offline on first launch.
# hand_tracker._default_model_path() finds it next to the package.
_model = os.path.join(ROOT, "hand_landmarker.task")
if os.path.exists(_model):
    datas += [(_model, "fingerino")]
else:
    raise SystemExit(
        "hand_landmarker.task is missing — run packaging/build.py, which "
        "fetches it before building."
    )

# Gesture-guide sketches and the bundled UI font, both loaded at runtime by
# ui_overlay._asset_root().
_gesture_icons = glob.glob(os.path.join(ROOT, "assets", "tutorial-gestures", "*.png"))
if not _gesture_icons:
    raise SystemExit("assets/tutorial-gestures/*.png is missing")
datas += [(f, os.path.join("assets", "tutorial-gestures")) for f in _gesture_icons]

_fonts = glob.glob(os.path.join(ROOT, "assets", "fonts", "*.ttf"))
if not _fonts:
    raise SystemExit("assets/fonts/*.ttf is missing")
datas += [(f, os.path.join("assets", "fonts")) for f in _fonts]

# The SIL Open Font License requires its text to accompany the fonts wherever
# they are redistributed, so it ships beside them rather than only living in
# the repository. It is also quoted in full in THIRD-PARTY-NOTICES.md.
_ofl = os.path.join(ROOT, "assets", "fonts", "OFL-LICENSE.txt")
if not os.path.exists(_ofl):
    raise SystemExit("assets/fonts/OFL-LICENSE.txt is missing")
datas += [(_ofl, os.path.join("assets", "fonts"))]

_ico = os.path.join(ROOT, "build", "icons", "fingerino.ico")
_icns = os.path.join(ROOT, "build", "icons", "fingerino.icns")

a = Analysis(
    [os.path.join(PACKAGING, "launcher.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Dev-only and GUI-toolkit packages nothing here imports, plus two of
    # MediaPipe's optional dependencies that collect_all drags in (~15 MB).
    # matplotlib is NOT in this list on purpose: `import mediapipe` pulls in
    # mediapipe.python.solutions, which imports it, so dropping it turns
    # every launch into an ImportError.
    excludes=["tkinter", "PyQt5", "PyQt6", "PySide2", "PySide6",
              "IPython", "pytest", "setuptools", "pip",
              "pandas", "sounddevice"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

_console = bool(os.environ.get("FINGERINO_CONSOLE"))

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Fingerino",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=_console,
    disable_windowed_traceback=False,
    argv_emulation=False,       # keep argv clean; the app takes CLI flags
    target_arch=None,           # build native; CI runs one job per arch
    codesign_identity=None,     # build.py signs the finished bundle
    entitlements_file=None,
    icon=_ico if (IS_WIN and os.path.exists(_ico)) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Fingerino",
)

if IS_MAC:
    app = BUNDLE(
        coll,
        name="Fingerino.app",
        icon=_icns if os.path.exists(_icns) else None,
        bundle_identifier="com.cky.fingerino",
        version=VERSION,
        info_plist={
            "CFBundleName": "Fingerino",
            "CFBundleDisplayName": "Fingerino",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "LSMinimumSystemVersion": "11.0",
            "NSHighResolutionCapable": True,
            "LSApplicationCategoryType": "public.app-category.utilities",
            # Shown verbatim in the macOS camera-permission prompt.
            "NSCameraUsageDescription":
                "Fingerino watches your hand through the camera to move the "
                "cursor and recognise gestures. Video never leaves your Mac.",
            # Controlling the cursor is Accessibility, not Input Monitoring,
            # but the key is harmless and covers future key-listening.
            "NSInputMonitoringUsageDescription":
                "Fingerino sends keyboard shortcuts for the window gestures.",
        },
    )

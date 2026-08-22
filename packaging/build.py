#!/usr/bin/env python3
"""Build the double-clickable Fingerino app and its installer.

    python packaging/build.py            # build for the current platform
    python packaging/build.py --clean    # wipe build/ and dist/ first
    python packaging/build.py --console  # keep a console window (debugging)

Produces, in ``dist/release/``:

    Windows   Fingerino-<ver>-windows-x64-Setup.exe   (if Inno Setup is present)
              Fingerino-<ver>-windows-x64.zip         (portable, always)
    macOS     Fingerino-<ver>-macos-<arch>.dmg        (drag to Applications)

Optional macOS signing — without these the app still runs, but the first
launch needs a trip through System Settings (see README):

    APPLE_DEVELOPER_ID    "Developer ID Application: Name (TEAMID)"
    APPLE_NOTARY_PROFILE  profile from `xcrun notarytool store-credentials`
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGING = os.path.join(ROOT, "packaging")
BUILD = os.path.join(ROOT, "build")
DIST = os.path.join(ROOT, "dist")
RELEASE = os.path.join(DIST, "release")
ICONS = os.path.join(BUILD, "icons")

IS_WIN = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"

sys.path.insert(0, ROOT)
from fingerino import __version__ as VERSION  # noqa: E402

# macOS .iconset wants each size plus its @2x twin, which is the next size up.
ICNS_SIZES = (16, 32, 128, 256, 512)


def log(msg: str) -> None:
    print(f"[build] {msg}", flush=True)


def run(cmd: list[str], **kw) -> None:
    log(" ".join(str(c) for c in cmd))
    subprocess.run(cmd, check=True, **kw)


# ---------------------------------------------------------------------------
# Inputs: the model blob and the icons
# ---------------------------------------------------------------------------

def ensure_model() -> str:
    """Download the hand-landmark model into the repo root if it isn't there.

    It is gitignored (7 MB) but must exist at build time — the spec copies it
    into the bundle so a packaged app never has to download anything.
    """
    from fingerino import config
    from fingerino.hand_tracker import _MODEL_URL

    path = os.path.join(ROOT, config.MODEL_FILENAME)
    if os.path.exists(path):
        log(f"model present ({os.path.getsize(path) / 1e6:.1f} MB)")
        return path
    log(f"downloading model -> {path}")
    tmp = path + ".part"
    urllib.request.urlretrieve(_MODEL_URL, tmp)
    os.replace(tmp, path)
    return path


def build_icons() -> None:
    """Render fingerino.ico (Windows) and fingerino.icns (macOS)."""
    from fingerino import branding

    os.makedirs(ICONS, exist_ok=True)

    ico = os.path.join(ICONS, "fingerino.ico")
    if not os.path.exists(ico):
        # branding names the file by artwork version; copy to a stable name.
        src = branding.icon_path(ICONS)
        if not src:
            raise SystemExit("could not render the .ico")
        shutil.copyfile(src, ico)
    log(f"icon: {ico}")

    if not IS_MAC:
        return

    icns = os.path.join(ICONS, "fingerino.icns")
    if os.path.exists(icns):
        log(f"icon: {icns}")
        return

    iconset = os.path.join(ICONS, "Fingerino.iconset")
    shutil.rmtree(iconset, ignore_errors=True)
    os.makedirs(iconset)
    for size in ICNS_SIZES:
        branding.render(size).save(
            os.path.join(iconset, f"icon_{size}x{size}.png"))
        branding.render(size * 2).save(
            os.path.join(iconset, f"icon_{size}x{size}@2x.png"))
    run(["iconutil", "-c", "icns", iconset, "-o", icns])
    log(f"icon: {icns}")


# ---------------------------------------------------------------------------
# PyInstaller
# ---------------------------------------------------------------------------

def run_pyinstaller(console: bool) -> None:
    env = dict(os.environ)
    if console:
        env["FINGERINO_CONSOLE"] = "1"
    else:
        env.pop("FINGERINO_CONSOLE", None)
    run([sys.executable, "-m", "PyInstaller", "--noconfirm",
         "--distpath", DIST, "--workpath", os.path.join(BUILD, "pyi"),
         os.path.join(PACKAGING, "fingerino.spec")], env=env, cwd=ROOT)


# ---------------------------------------------------------------------------
# Windows packaging
# ---------------------------------------------------------------------------

def _find_iscc() -> str | None:
    found = shutil.which("iscc") or shutil.which("ISCC")
    if found:
        return found
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles")):
        if not base:
            continue
        for ver in ("6", "5"):
            cand = os.path.join(base, f"Inno Setup {ver}", "ISCC.exe")
            if os.path.exists(cand):
                return cand
    return None


def package_windows() -> list[str]:
    app_dir = os.path.join(DIST, "Fingerino")
    if not os.path.isdir(app_dir):
        raise SystemExit(f"expected {app_dir} — PyInstaller did not produce it")
    out: list[str] = []

    base = f"Fingerino-{VERSION}-windows-x64"
    out.append(shutil.make_archive(os.path.join(RELEASE, base), "zip",
                                   root_dir=DIST, base_dir="Fingerino"))

    iscc = _find_iscc()
    if not iscc:
        log("Inno Setup (ISCC.exe) not found — skipping the installer. "
            "Get it from https://jrsoftware.org/isdl.php to build one.")
        return out

    run([iscc,
         f"/DMyAppVersion={VERSION}",
         f"/DMyAppSource={app_dir}",
         f"/DMyOutputDir={RELEASE}",
         f"/DMyIcon={os.path.join(ICONS, 'fingerino.ico')}",
         f"/DMyOutputBase={base}-Setup",
         os.path.join(PACKAGING, "fingerino.iss")])
    out.append(os.path.join(RELEASE, f"{base}-Setup.exe"))
    return out


# ---------------------------------------------------------------------------
# macOS packaging
# ---------------------------------------------------------------------------

def _sign_macos(app: str) -> None:
    """Sign the bundle. Developer ID if configured, otherwise ad-hoc.

    An ad-hoc signature is not optional on Apple Silicon — unsigned code will
    not launch at all — but it does not satisfy Gatekeeper for a download, so
    a real Developer ID is used whenever one is available.
    """
    identity = os.environ.get("APPLE_DEVELOPER_ID")
    entitlements = os.path.join(PACKAGING, "entitlements.plist")
    if identity:
        log(f"signing with {identity}")
        run(["codesign", "--force", "--deep", "--timestamp",
             "--options", "runtime", "--entitlements", entitlements,
             "--sign", identity, app])
    else:
        log("no APPLE_DEVELOPER_ID — ad-hoc signing (users will see Gatekeeper)")
        # No hardened runtime here: ad-hoc plus runtime hardening rejects the
        # unsigned dylibs PyInstaller ships and the app dies on launch.
        run(["codesign", "--force", "--deep", "--sign", "-", app])
    run(["codesign", "--verify", "--strict", "--verbose=1", app])


def _notarize(path: str) -> None:
    profile = os.environ.get("APPLE_NOTARY_PROFILE")
    if not (profile and os.environ.get("APPLE_DEVELOPER_ID")):
        return
    log("submitting to Apple for notarization (this takes a few minutes)")
    run(["xcrun", "notarytool", "submit", path,
         "--keychain-profile", profile, "--wait"])
    run(["xcrun", "stapler", "staple", path])


def package_macos() -> list[str]:
    app = os.path.join(DIST, "Fingerino.app")
    if not os.path.isdir(app):
        raise SystemExit(f"expected {app} — PyInstaller did not produce it")

    _sign_macos(app)

    arch = "arm64" if platform.machine() == "arm64" else "intel"
    dmg = os.path.join(RELEASE, f"Fingerino-{VERSION}-macos-{arch}.dmg")
    stage = os.path.join(BUILD, "dmg")
    shutil.rmtree(stage, ignore_errors=True)
    os.makedirs(stage)
    # symlinks=True: the bundle's Frameworks are symlinked into place and
    # flattening them invalidates the signature.
    shutil.copytree(app, os.path.join(stage, "Fingerino.app"), symlinks=True)
    os.symlink("/Applications", os.path.join(stage, "Applications"))

    if os.path.exists(dmg):
        os.remove(dmg)
    run(["hdiutil", "create", "-volname", "Fingerino", "-srcfolder", stage,
         "-ov", "-format", "UDZO", dmg])

    _notarize(dmg)
    return [dmg]


# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--clean", action="store_true",
                    help="remove build/ and dist/ before building")
    ap.add_argument("--console", action="store_true",
                    help="attach a console window to the app (debug builds)")
    args = ap.parse_args()

    if args.clean:
        log("cleaning build/ and dist/")
        shutil.rmtree(BUILD, ignore_errors=True)
        shutil.rmtree(DIST, ignore_errors=True)

    os.makedirs(RELEASE, exist_ok=True)
    ensure_model()
    build_icons()
    run_pyinstaller(args.console)

    if IS_WIN:
        made = package_windows()
    elif IS_MAC:
        made = package_macos()
    else:
        log("Linux: the app folder is in dist/Fingerino (no installer target)")
        made = []

    log("done:")
    for path in made:
        log(f"  {path}  ({os.path.getsize(path) / 1e6:.0f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

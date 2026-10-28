#!/usr/bin/env python3
"""Generate THIRD-PARTY-NOTICES.md for the packaged app.

Every installer redistributes a lot of other people's code, and most of those
licences require their text to travel with it — Apache-2.0 section 4(d) for
MediaPipe, OpenCV, absl-py and flatbuffers, the LGPL for pynput and for the
FFmpeg DLL inside the OpenCV wheel, the SIL OFL for the Inter font.

Licence text is read from each installed distribution's own metadata rather
than transcribed here, so it stays correct when a version is bumped. Run from
packaging/build.py, which writes the result where each installer will pick it
up.

    python packaging/notices.py            # print to stdout
    python packaging/notices.py out.md     # write to a file
"""

from __future__ import annotations

import hashlib
import importlib.metadata as md
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Shipped inside the app. Taken from requirements-build.txt minus the packages
# that only ever run on the build machine. Over-including is harmless; missing
# something that does ship is the actual failure, so when in doubt, keep it.
BUILD_ONLY = {"pyinstaller", "pyinstaller-hooks-contrib", "altgraph"}

# Filenames in a .dist-info directory worth quoting in full.
LICENCE_NAMES = ("license", "licence", "copying", "notice")


def _bundled_packages() -> list[str]:
    """Package names from the pinned build set, minus build-only tooling."""
    path = os.path.join(ROOT, "requirements-build.txt")
    names = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            name = line.split("==")[0].strip()
            if name.lower().replace("_", "-") not in BUILD_ONLY:
                names.append(name)
    return sorted(names, key=str.lower)


def _licence_texts(dist: md.Distribution) -> list[tuple[str, str]]:
    """(filename, text) for every licence-ish file in the dist-info."""
    out = []
    for entry in dist.files or []:
        as_posix = str(entry).replace(os.sep, "/")
        if ".dist-info" not in as_posix:
            continue
        stem = as_posix.rsplit("/", 1)[-1]
        if not any(k in stem.lower() for k in LICENCE_NAMES):
            continue
        try:
            text = entry.read_text(encoding="utf-8")
        except Exception:
            continue
        if text and text.strip():
            out.append((stem, text.strip()))
    # Deduplicate: numpy ships the same LICENSE.txt under several paths.
    seen, unique = set(), []
    for name, text in sorted(out):
        key = text[:400]
        if key not in seen:
            seen.add(key)
            unique.append((name, text))
    return unique


def _declared_licence(meta) -> str:
    """Best short licence label the metadata offers."""
    for classifier in meta.get_all("Classifier") or []:
        if classifier.startswith("License ::"):
            return classifier.split("::")[-1].strip()
    expression = meta.get("License-Expression") or meta.get("License") or ""
    expression = expression.strip()
    if expression and "\n" not in expression and len(expression) < 60:
        return expression
    return "see the licence text below"


def _homepage(meta) -> str:
    for key in ("Home-page", "Project-URL"):
        for value in meta.get_all(key) or []:
            if "http" in value:
                return value.split(",")[-1].strip()
    return ""


def _fence(text: str) -> str:
    """A code fence longer than any backtick run inside ``text``.

    Licence files do not usually contain backticks, but one that did would
    otherwise close the block early and spill raw licence text into the
    document as markdown.
    """
    longest = max((len(m) for m in re.findall(r"`+", text)), default=0)
    return "`" * max(3, longest + 1)


def _quote(filename: str, text: str) -> list[str]:
    fence = _fence(text)
    return [f"<details>\n<summary>{filename}</summary>", "",
            fence, text, fence, "", "</details>", ""]


def _section(name: str, emitted: dict[str, str]) -> str:
    """One package's entry. ``emitted`` maps licence text -> where it appeared,
    so the same file shipped by two packages is quoted once and referenced
    afterwards — opencv-python and opencv-contrib-python ship an identical
    180 KB LICENSE-3RD-PARTY.txt, which is most of this document otherwise.
    """
    try:
        dist = md.distribution(name)
    except md.PackageNotFoundError:
        return (f"## {name}\n\n"
                "_Not installed on the machine that produced this file; "
                "licence text could not be embedded._\n")

    meta = dist.metadata
    title = meta["Name"] or name
    lines = [f"## {title} {dist.version}", "",
             f"Licence: {_declared_licence(meta)}"]
    url = _homepage(meta)
    if url:
        lines.append(f"Project: {url}")
    lines.append("")

    texts = _licence_texts(dist)
    if not texts:
        lines.append("_This distribution ships no licence file in its "
                     "metadata; see the project page above._\n")
        return "\n".join(lines)

    for filename, text in texts:
        key = hashlib.sha256(text.encode("utf-8")).hexdigest()
        where = emitted.get(key)
        if where:
            lines += [f"`{filename}` is identical to the copy shipped with "
                      f"**{where}**, quoted above.", ""]
            continue
        emitted[key] = f"{title} {dist.version}"
        lines += _quote(filename, text)
    return "\n".join(lines)


def _inter_font() -> str:
    path = os.path.join(ROOT, "assets", "fonts", "OFL-LICENSE.txt")
    lines = ["## Inter (font)", "",
             "Licence: SIL Open Font License 1.1",
             "Project: https://github.com/rsms/inter", ""]
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read().strip()
        lines += _quote("OFL-LICENSE.txt", text)
    except OSError:
        lines.append("_Licence file missing from the source tree._\n")
    return "\n".join(lines)


_HEADER = """# Third-party notices

Fingerino is MIT licensed (see LICENSE). The application you installed also
contains the components below, each under its own licence. Their terms are
reproduced here in full, which is what most of them require of anyone
redistributing them.

Generated automatically at build time from the metadata of the exact package
versions that went into this build — see `packaging/notices.py`.

## A note on the LGPL components

**pynput** (LGPL-3.0) and **FFmpeg** (LGPL-2.1+, shipped inside the OpenCV
wheel as `opencv_videoio_ffmpeg*.dll`) are used unmodified as libraries. The
LGPL asks that you be able to replace them with your own build.

Fingerino is fully open source, so the corresponding source for the whole
application is available at https://github.com/cky-gitHub/fingerino, and
`packaging/build.py` is the supported way to rebuild it — including against a
pynput or FFmpeg of your choosing. The exact versions in this build are listed
below, and `requirements-build.txt` in the repository pins the complete set.

FFmpeg is not a pip package, so it has no section of its own here; its licence
is included in OpenCV's `LICENSE-3RD-PARTY.txt` below.

## The hand-landmark model

`hand_landmarker.task` is Google's MediaPipe hand-landmark model, used under
the Apache License 2.0 and redistributed unmodified. Model card:
https://ai.google.dev/edge/mediapipe/solutions/vision/hand_landmarker

---
"""


def render() -> str:
    parts = [_HEADER]
    emitted: dict[str, str] = {}
    for name in _bundled_packages():
        parts.append(_section(name, emitted))
    parts.append(_inter_font())
    return "\n".join(parts).rstrip() + "\n"


def write(path: str) -> str:
    text = render()
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return path


if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(f"wrote {write(sys.argv[1])}")
    else:
        sys.stdout.write(render())

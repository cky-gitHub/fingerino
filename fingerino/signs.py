"""The user's own signs, and signs.json where they are kept.

A sign is a name and the hand shapes recorded for it (see sign_matcher). What
a sign *does* is not stored here -- that is a binding in actions.json -- so a
sign can be re-recorded without losing its action, and an action edited
without touching the sign.

What is stored is hand geometry only: 21 points per sample, already
normalised to the wrist and to hand size, so not even where in the frame the
hand was. No image is ever written.

The file is plain JSON and meant to be readable, so developers can generate
or edit signs by hand; loading is forgiving the way settings.json's is.
Standard library only.
"""

from __future__ import annotations

import json
import math
import os
import threading
import uuid
from dataclasses import dataclass

from . import config
from . import gesture_detector as gd
from .sign_matcher import Landmarks, Matcher, Point, Sign, canonical, features

FILENAME = "signs.json"
SCHEMA = 1
# Enough to cover the natural wobble of a held sign; more only slows
# matching, which compares a live hand with every sample of every sign.
MAX_SAMPLES = 40
NAME_MAX = 40
# Recorder's wording for built-ins that only exist while the cursor is on.
CURSOR_NOTE = "while the cursor is on"


def thin(samples: list[list[Point]], limit: int = MAX_SAMPLES) -> list[list[Point]]:
    """Keep at most ``limit`` samples, spread evenly over the recording."""
    if len(samples) <= limit:
        return list(samples)
    step = len(samples) / limit
    return [samples[int(i * step)] for i in range(limit)]


def _valid_sample(sample: object) -> list[Point] | None:
    if not isinstance(sample, list) or len(sample) != 21:
        return None
    out: list[Point] = []
    for p in sample:
        if not (isinstance(p, list) and len(p) == 3
                and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                        and math.isfinite(v) for v in p)):
            return None
        out.append((float(p[0]), float(p[1]), float(p[2])))
    return out


def to_json(signs: list[Sign]) -> dict:
    return {"schema": SCHEMA, "signs": [
        {"id": s.id, "name": s.name, "enabled": s.enabled,
         **({"builtin": s.builtin} if s.builtin else {}),
         "samples": [[[round(v, 4) for v in p] for p in sample] for sample in s.samples]}
        for s in signs]}


def from_json(data: object) -> list[Sign]:
    """Every valid sign in ``data``; anything malformed is skipped."""
    if not isinstance(data, dict) or not isinstance(data.get("signs"), list):
        return []
    out: list[Sign] = []
    seen: set[str] = set()
    for item in data["signs"]:
        if not isinstance(item, dict):
            continue
        sign_id, name = item.get("id"), item.get("name")
        if not (isinstance(sign_id, str) and sign_id and isinstance(name, str)
                and name.strip()) or sign_id in seen:
            continue
        raw = item.get("samples")
        valid = [v for v in map(_valid_sample, raw) if v] if isinstance(raw, list) else []
        if not valid:
            continue
        seen.add(sign_id)
        builtin = item.get("builtin")
        out.append(Sign(sign_id, name.strip()[:NAME_MAX], thin(valid),
                        enabled=item.get("enabled") is not False,
                        builtin=builtin[:80] if isinstance(builtin, str) else ""))
    return out


class Library:
    """The user's signs, shared by Home (which edits) and the session (which
    matches). Edits rebuild the matcher and swap it in whole."""

    def __init__(self, signs: list[Sign] | None = None) -> None:
        self._lock = threading.Lock()
        self.signs: list[Sign] = list(signs or [])
        self.matcher = Matcher(self.signs)

    def _changed(self) -> None:
        self.matcher = Matcher(self.signs)

    def get(self, sign_id: str) -> Sign | None:
        return next((s for s in self.signs if s.id == sign_id), None)

    def name(self, sign_id: str) -> str:
        sign = self.get(sign_id)
        return sign.name if sign else ""

    def names(self) -> dict[str, str]:
        return {s.id: s.name for s in self.signs}

    def add(self, name: str, samples: list[list[Point]], builtin: str = "") -> Sign:
        sign = Sign(f"sign-{uuid.uuid4().hex[:10]}", name.strip()[:NAME_MAX] or "My sign",
                    thin(samples), builtin=builtin)
        with self._lock:
            self.signs = [*self.signs, sign]
            self._changed()
        return sign

    def warning(self, sign_id: str, cursor: bool) -> str:
        """A short note for the sign's card when it may never fire, or "".

        Either it looked like a built-in when recorded (checked first, so it
        would never reach the matcher) or it is close to another sign (the
        matcher refuses ambiguous matches). The second is worked out now, so
        it goes away when the other sign is deleted or switched off. Signs
        that are switched off cannot clash, so they carry no note.
        """
        sign = self.get(sign_id)
        if sign is None or not sign.enabled:
            return ""
        if sign.builtin and (cursor or CURSOR_NOTE not in sign.builtin):
            return (f"Looks like {sign.builtin}. Fingerino checks that first, "
                    "so this sign may not be recognised.")
        twin = similar_sign(self, sign.samples, ignore=sign_id)
        if twin:
            return (f"Looks a lot like your sign “{twin}”. Fingerino may "
                    "not be able to tell them apart.")
        return ""

    def rename(self, sign_id: str, name: str) -> None:
        name = name.strip()[:NAME_MAX]
        sign = self.get(sign_id)
        if sign is not None and name:
            with self._lock:
                sign.name = name
                self._changed()          # the session re-reads names on a swap

    def set_enabled(self, sign_id: str, on: bool) -> None:
        sign = self.get(sign_id)
        if sign is not None:
            with self._lock:
                sign.enabled = on
                self._changed()

    def delete(self, sign_id: str) -> None:
        with self._lock:
            self.signs = [s for s in self.signs if s.id != sign_id]
            self._changed()


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------
@dataclass
class Recording:
    samples: list[list[Point]]
    frames: int                     # frames the recording lasted
    seen: int                       # frames with a hand in view
    builtin: str = ""               # a built-in the sign looks like, if any
    error: str = ""                 # why it can't be used, if it can't


class Recorder:
    """Collects a sign's samples from the live hand for ``duration`` seconds.

    Fed from the tracking thread, one frame at a time. Besides the samples,
    it notes how often the hand looked like one of the built-in postures,
    because a sign that is really a shaka or an open palm would never reach
    the matcher -- the built-ins are checked first.
    """

    def __init__(self, start: float, duration: float, cursor: bool) -> None:
        self.start = start
        self.duration = duration
        self.cursor = cursor
        self.frames = 0
        self.samples: list[list[Point]] = []
        self._looks: dict[str, int] = {}

    def progress(self, now: float) -> float:
        return min(1.0, max(0.0, (now - self.start) / max(self.duration, 1e-6)))

    def done(self, now: float) -> bool:
        return now - self.start >= self.duration

    def add(self, lms: Landmarks | None, handedness: str | None) -> None:
        self.frames += 1
        if lms is None:
            return
        self.samples.append(canonical(lms, handedness))
        for name, test in self._builtin_tests():
            if test(lms):
                self._looks[name] = self._looks.get(name, 0) + 1

    def _builtin_tests(self):
        tests = [("crossed fingers, which exits Fingerino", gd.is_crossed_fingers),
                 ("the shaka", gd.is_shaka),
                 ("an open palm, which swipes", gd.is_flat_hand)]
        if self.cursor:
            tests += [(f"pointing, which clicks {CURSOR_NOTE}", gd.is_pointing),
                      (f"two fingers, which scroll {CURSOR_NOTE}", gd.is_two_finger)]
        return tests

    def result(self) -> Recording:
        seen = len(self.samples)
        rec = Recording(self.samples, self.frames, seen)
        if seen < config.SIGN_RECORD_MIN_SAMPLES or \
                seen < config.SIGN_RECORD_MIN_SEEN * max(self.frames, 1):
            rec.error = ("Fingerino couldn't see your hand for most of that. Keep it "
                         "inside the camera's view and try again.")
            return rec
        for name, count in sorted(self._looks.items(), key=lambda kv: -kv[1]):
            if count >= config.SIGN_SIMILAR_SHARE * seen:
                rec.builtin = name
                break
        return rec


def similar_sign(library: Library, samples: list[list[Point]],
                 ignore: str = "") -> str:
    """The name of an existing sign these samples are too close to, or "".

    Two signs that close would make each other ambiguous, and the matcher
    refuses ambiguous matches -- so neither would ever fire.
    """
    matcher = library.matcher
    if not matcher or not samples:
        return ""
    counts: dict[str, int] = {}
    loose = config.SIGN_MATCH_MAX_DIST * config.SIGN_MATCH_MARGIN
    for sample in samples:
        ranked = [r for r in matcher.nearest(features(sample)) if r[1] != ignore]
        if ranked and ranked[0][0] <= loose:
            counts[ranked[0][1]] = counts.get(ranked[0][1], 0) + 1
    for sign_id, count in sorted(counts.items(), key=lambda kv: -kv[1]):
        if count >= config.SIGN_SIMILAR_SHARE * len(samples):
            return library.name(sign_id)
    return ""


def load(folder: str) -> Library:
    try:
        with open(os.path.join(folder, FILENAME), encoding="utf-8") as fh:
            return Library(from_json(json.load(fh)))
    except (OSError, ValueError):
        return Library()


def save(folder: str, library: Library) -> bool:
    """Write signs.json atomically. False if the folder isn't writable."""
    path = os.path.join(folder, FILENAME)
    tmp = path + ".tmp"
    try:
        os.makedirs(folder, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(to_json(library.signs), fh)
        os.replace(tmp, path)
        return True
    except OSError:
        return False

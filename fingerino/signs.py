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

from .sign_matcher import Matcher, Point, Sign

FILENAME = "signs.json"
SCHEMA = 1
# Enough to cover the natural wobble of a held sign; more only slows
# matching, which compares a live hand with every sample of every sign.
MAX_SAMPLES = 40
NAME_MAX = 40


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
        out.append(Sign(sign_id, name.strip()[:NAME_MAX], thin(valid),
                        enabled=item.get("enabled") is not False))
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

    def add(self, name: str, samples: list[list[Point]]) -> Sign:
        sign = Sign(f"sign-{uuid.uuid4().hex[:10]}", name.strip()[:NAME_MAX] or "My sign",
                    thin(samples))
        with self._lock:
            self.signs = [*self.signs, sign]
            self._changed()
        return sign

    def rename(self, sign_id: str, name: str) -> None:
        name = name.strip()[:NAME_MAX]
        sign = self.get(sign_id)
        if sign is not None and name:
            sign.name = name

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

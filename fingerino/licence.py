"""Premium: the licence key, the trial, and what they unlock.

A licence key is one line of text the buyer pastes into Home:

    fingerino1.<payload>.<signature>

``payload`` is base64url-encoded JSON, ``{"v": 1, "id": "<order id>",
"email": "...", "plan": "premium", "issued": "YYYY-MM-DD"}``, and
``signature`` is the base64url Ed25519 signature of exactly those payload
bytes. The public key is below; the private key that makes keys never goes
in this repository or the private one.

Checking a key is entirely offline: Fingerino makes no network request for
it (README, "Privacy"). The flip side is that a key can't be revoked; it
carries the buyer's email so a shared key can be traced. Keys don't expire:
Premium is a one-time purchase.

The trial needs no key: a new install gets ``config.TRIAL_DAYS`` of Premium
from its first launch, remembered in settings.json. Deleting that file starts
a new trial, which was accepted when the free tier was decided.

Under FCL-1.0-MIT this check is licence-key functionality that may not be
removed or got around. Standard library only, except for the signature check,
which imports ``cryptography`` when it runs, so everything else here (and a
build where that import fails) still works as the free version.
"""

from __future__ import annotations

import base64
import binascii
import datetime as dt
import json
import os
from dataclasses import dataclass

from . import config

FILENAME = "licence.key"
PREFIX = "fingerino1"
VERSION = 1
PLAN = "premium"
# Ed25519 public key (raw, 32 bytes) for keys from the official shop.
PUBLIC_KEY = bytes.fromhex(
    "93f7946992808b9f6d1fb59c23da59c17c2ab5d2431047ccce9382bdd590f0af")

INVALID = "This key isn't valid. Check that you copied all of it."
NEWER = "This key is for a newer version of Fingerino. Update Fingerino, then try again."
NO_CHECK = "Fingerino can't check licence keys on this computer. Please report this."


@dataclass(frozen=True)
class Licence:
    id: str
    email: str
    issued: str
    plan: str = PLAN


def _b64decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def parse(text: str, public_key: bytes | None = None) -> Licence | str:
    """The licence in ``text``, or a message saying why it can't be used.

    Whitespace anywhere is ignored, since a key copied out of an email can
    arrive wrapped over several lines.
    """
    key = "".join(text.split())
    parts = key.split(".")
    if len(parts) != 3 or not parts[1] or not parts[2]:
        return INVALID
    prefix, body, sig = parts
    if prefix != PREFIX:
        return NEWER if prefix.startswith("fingerino") else INVALID
    try:
        payload, signature = _b64decode(body), _b64decode(sig)
    except (binascii.Error, ValueError):
        return INVALID
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError:
        return NO_CHECK
    try:
        Ed25519PublicKey.from_public_bytes(public_key or PUBLIC_KEY).verify(
            signature, payload)
    except (InvalidSignature, ValueError):
        return INVALID
    # Signed by us, so what follows is only a guard against our own mistakes.
    try:
        data = json.loads(payload)
    except ValueError:
        return INVALID
    if not isinstance(data, dict):
        return INVALID
    if data.get("v") != VERSION:
        return NEWER
    fields = [data.get(k) for k in ("id", "email", "issued", "plan")]
    if not all(isinstance(f, str) and f for f in fields) or data["plan"] != PLAN:
        return INVALID
    return Licence(data["id"], data["email"], data["issued"], data["plan"])


def make_key(private_key: bytes, order_id: str, email: str,
             issued: dt.date | None = None) -> str:
    """A signed key for one purchase. ``private_key`` is the raw 32-byte
    Ed25519 seed. Used by the shop's key issuer and by the tests; Fingerino
    itself never makes keys."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    if not order_id.strip() or not email.strip():
        raise ValueError("a key needs an order id and an email")
    payload = json.dumps(
        {"v": VERSION, "id": order_id.strip(), "email": email.strip(),
         "plan": PLAN, "issued": (issued or dt.date.today()).isoformat()},
        separators=(",", ":"), sort_keys=True).encode()
    signature = Ed25519PrivateKey.from_private_bytes(private_key).sign(payload)
    return f"{PREFIX}.{_b64encode(payload)}.{_b64encode(signature)}"


def public_key_for(private_key: bytes) -> bytes:
    """The raw public key that checks keys made with ``private_key``."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    return Ed25519PrivateKey.from_private_bytes(private_key).public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)


# ---------------------------------------------------------------------------
# What the user has: Premium, the trial, or the free version
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Status:
    plan: str                       # "premium", "trial" or "free"
    days_left: int = 0              # of the trial; 0 otherwise
    email: str = ""                 # who the key was sold to

    @property
    def premium(self) -> bool:
        """Premium features are unlocked (bought, or in the trial)."""
        return self.plan != "free"

    @property
    def sign_limit(self) -> int:
        return config.PREMIUM_CUSTOM_SIGNS if self.premium else config.FREE_CUSTOM_SIGNS


def trial_days_left(started: str, today: dt.date) -> int:
    """Days of trial left, 0 once it is over or if it never started.

    A clock set back before the start counts as the first day, so it can't
    stretch the trial past ``config.TRIAL_DAYS``.
    """
    try:
        start = dt.date.fromisoformat(started)
    except (TypeError, ValueError):
        return 0
    elapsed = max(0, (today - start).days)
    return max(0, config.TRIAL_DAYS - elapsed)


def trial_start(stored: str, today: dt.date) -> str:
    """When the trial began: ``stored`` if it is a date, else ``today``,
    which starts it. Called on every launch (main.py)."""
    try:
        return dt.date.fromisoformat(stored).isoformat()
    except (TypeError, ValueError):
        return today.isoformat()


def status(licence: Licence | None, trial_started: str, today: dt.date) -> Status:
    if licence is not None:
        return Status("premium", email=licence.email)
    left = trial_days_left(trial_started, today)
    return Status("trial", days_left=left) if left else Status("free")


# ---------------------------------------------------------------------------
# licence.key: the key exactly as pasted, beside settings.json
# ---------------------------------------------------------------------------
def load(folder: str, public_key: bytes | None = None) -> Licence | None:
    """The stored licence, if there is one and it is still valid."""
    try:
        with open(os.path.join(folder, FILENAME), encoding="utf-8") as fh:
            text = fh.read(4096)
    except (OSError, ValueError):
        return None
    found = parse(text, public_key)
    return found if isinstance(found, Licence) else None


def save(folder: str, text: str) -> bool:
    """Store a key (already checked by parse). False if it can't be written."""
    path = os.path.join(folder, FILENAME)
    tmp = path + ".tmp"
    try:
        os.makedirs(folder, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write("".join(text.split()) + "\n")
        os.replace(tmp, path)
        return True
    except OSError:
        return False


def remove(folder: str) -> bool:
    try:
        os.remove(os.path.join(folder, FILENAME))
        return True
    except FileNotFoundError:
        return True
    except OSError:
        return False

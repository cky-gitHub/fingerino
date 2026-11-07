"""Licence keys and the trial (licence.py), checked offline and camera-free.

Keys here are made with a throwaway key pair; only the last test looks at the
public key Fingerino ships.
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import sys

import pytest

pytest.importorskip("cryptography")

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from fingerino import config, licence, settings

TODAY = dt.date(2026, 11, 7)


@pytest.fixture
def seed() -> bytes:
    return Ed25519PrivateKey.generate().private_bytes_raw()


@pytest.fixture
def public(seed) -> bytes:
    return licence.public_key_for(seed)


def _signed(seed: bytes, payload: dict) -> str:
    """A key over any payload, for the cases make_key won't produce."""
    body = json.dumps(payload).encode()
    sig = Ed25519PrivateKey.from_private_bytes(seed).sign(body)
    enc = licence._b64encode
    return f"{licence.PREFIX}.{enc(body)}.{enc(sig)}"


# ---------------------------------------------------------------------------
# Keys
# ---------------------------------------------------------------------------
def test_a_key_round_trips(seed, public):
    key = licence.make_key(seed, "order-1", "a@example.com", TODAY)
    assert key.startswith("fingerino1.")
    found = licence.parse(key, public)
    assert found == licence.Licence("order-1", "a@example.com", "2026-11-07", "premium")


def test_a_key_wrapped_by_an_email_still_works(seed, public):
    key = licence.make_key(seed, "order-1", "a@example.com", TODAY)
    wrapped = "\n  ".join(key[i:i + 60] for i in range(0, len(key), 60)) + "\n"
    assert isinstance(licence.parse(wrapped, public), licence.Licence)


def test_a_changed_payload_is_refused(seed, public):
    key = licence.make_key(seed, "order-1", "a@example.com", TODAY)
    prefix, body, sig = key.split(".")
    data = json.loads(base64.urlsafe_b64decode(body + "=="))
    data["email"] = "someone.else@example.com"
    forged = licence._b64encode(json.dumps(data, separators=(",", ":"),
                                           sort_keys=True).encode())
    assert licence.parse(f"{prefix}.{forged}.{sig}", public) == licence.INVALID


def test_a_key_from_another_signer_is_refused(seed):
    key = licence.make_key(seed, "order-1", "a@example.com", TODAY)
    other = licence.public_key_for(Ed25519PrivateKey.generate().private_bytes_raw())
    assert licence.parse(key, other) == licence.INVALID


@pytest.mark.parametrize("text", [
    "", "hello", "fingerino1.", "fingerino1..", "fingerino1.abc", "a.b.c",
    "fingerino1.!!!.???", "fingerino1.e30.AAAA",
])
def test_garbage_is_refused(text, public):
    assert licence.parse(text, public) == licence.INVALID


def test_a_newer_key_format_asks_for_an_update(seed, public):
    assert licence.parse("fingerino2.abc.def", public) == licence.NEWER
    key = _signed(seed, {"v": 2, "id": "1", "email": "a@example.com",
                         "issued": "2026-11-07", "plan": "premium"})
    assert licence.parse(key, public) == licence.NEWER


@pytest.mark.parametrize("payload", [
    {"v": 1, "email": "a@example.com", "issued": "2026-11-07", "plan": "premium"},
    {"v": 1, "id": "1", "email": "", "issued": "2026-11-07", "plan": "premium"},
    {"v": 1, "id": "1", "email": "a@example.com", "issued": "2026-11-07", "plan": "gold"},
    {"v": 1, "id": 7, "email": "a@example.com", "issued": "2026-11-07", "plan": "premium"},
    ["not", "an", "object"],
])
def test_a_signed_but_malformed_payload_is_refused(seed, public, payload):
    assert licence.parse(_signed(seed, payload), public) == licence.INVALID


def test_keys_need_an_order_and_an_email(seed):
    with pytest.raises(ValueError):
        licence.make_key(seed, " ", "a@example.com")
    with pytest.raises(ValueError):
        licence.make_key(seed, "1", "")


def test_without_the_crypto_library_keys_are_refused_politely(seed, public, monkeypatch):
    key = licence.make_key(seed, "order-1", "a@example.com", TODAY)
    monkeypatch.setitem(sys.modules, "cryptography.hazmat.primitives.asymmetric.ed25519", None)
    assert licence.parse(key, public) == licence.NO_CHECK


def test_the_shipped_public_key_is_a_real_one():
    assert len(licence.PUBLIC_KEY) == 32 and any(licence.PUBLIC_KEY)
    # A forged key against the real public key is refused, like any other.
    forged = licence.make_key(Ed25519PrivateKey.generate().private_bytes_raw(),
                              "1", "a@example.com", TODAY)
    assert licence.parse(forged) == licence.INVALID


# ---------------------------------------------------------------------------
# licence.key
# ---------------------------------------------------------------------------
def test_the_key_is_kept_and_removed(tmp_path, seed, public):
    key = licence.make_key(seed, "order-1", "a@example.com", TODAY)
    assert licence.load(str(tmp_path), public) is None
    assert licence.save(str(tmp_path), key[:50] + "\n" + key[50:])
    stored = (tmp_path / licence.FILENAME).read_text(encoding="utf-8")
    assert stored == key + "\n"
    assert licence.load(str(tmp_path), public) == licence.parse(key, public)
    assert licence.remove(str(tmp_path))
    assert not (tmp_path / licence.FILENAME).exists()
    assert licence.remove(str(tmp_path))                 # already gone: fine


def test_a_spoilt_key_file_means_no_licence(tmp_path, seed, public):
    (tmp_path / licence.FILENAME).write_bytes(b"\xff\xfe not a key")
    assert licence.load(str(tmp_path), public) is None
    key = licence.make_key(seed, "order-1", "a@example.com", TODAY)
    (tmp_path / licence.FILENAME).write_text(key[:-4] + "AAAA", encoding="utf-8")
    assert licence.load(str(tmp_path), public) is None


# ---------------------------------------------------------------------------
# The trial and the plan
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("days_in, left", [
    (0, 14), (1, 13), (13, 1), (14, 0), (400, 0),
    (-30, 14),                       # clock set back: can't stretch the trial
])
def test_trial_days_left(days_in, left):
    assert config.TRIAL_DAYS == 14
    started = (TODAY - dt.timedelta(days=days_in)).isoformat()
    assert licence.trial_days_left(started, TODAY) == left


@pytest.mark.parametrize("stored", ["", "soon", "2026-13-45"])
def test_no_valid_start_means_no_trial(stored):
    assert licence.trial_days_left(stored, TODAY) == 0


def test_the_trial_starts_once():
    assert licence.trial_start("", TODAY) == "2026-11-07"
    assert licence.trial_start("garbage", TODAY) == "2026-11-07"
    assert licence.trial_start("2026-10-01", TODAY) == "2026-10-01"


def test_the_plan():
    key = licence.Licence("1", "a@example.com", "2026-11-07")
    started = TODAY.isoformat()
    over = (TODAY - dt.timedelta(days=30)).isoformat()

    bought = licence.status(key, over, TODAY)
    assert (bought.plan, bought.email, bought.premium) == ("premium", "a@example.com", True)
    assert bought.sign_limit == config.PREMIUM_CUSTOM_SIGNS == 20

    trial = licence.status(None, started, TODAY)
    assert (trial.plan, trial.days_left, trial.premium) == ("trial", 14, True)
    assert trial.sign_limit == 20

    free = licence.status(None, over, TODAY)
    assert (free.plan, free.premium) == ("free", False)
    assert free.sign_limit == config.FREE_CUSTOM_SIGNS == 1


def test_the_trial_start_is_kept_in_settings():
    s = settings.Settings(trial_started="2026-11-07")
    assert settings.Settings.from_json(s.to_json()).trial_started == "2026-11-07"
    assert settings.Settings().trial_started == ""
    for bad in (7, "next week", None):
        assert settings.Settings.from_json({"trial_started": bad}).trial_started == ""

"""Premium in Home: the plan, the sign limit, entering and removing a key.

Needs PySide6 (skipped by the dependency-free CI job). No camera: signs are
added straight to the library, as tests/test_home_design.py does.
"""

from __future__ import annotations

import datetime as dt
import random

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("cryptography")

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from landmarks import peace, recording, thumbs_down, thumbs_up

from fingerino import config, licence, settings, shell
from fingerino.sign_matcher import canonical

TODAY = dt.date.today()
LONG_AGO = (TODAY - dt.timedelta(days=60)).isoformat()


@pytest.fixture(autouse=True)
def on_sale(monkeypatch):
    """Most of these are about Premium once it sells; see the "soon" tests."""
    monkeypatch.setattr(config, "PREMIUM_URL", "https://shop.example/checkout")


@pytest.fixture
def seed(monkeypatch) -> bytes:
    """A throwaway signer standing in for the shop's."""
    s = Ed25519PrivateKey.generate().private_bytes_raw()
    monkeypatch.setattr(licence, "PUBLIC_KEY", licence.public_key_for(s))
    return s


def _shell(tmp_path, trial_started: str) -> shell.Shell:
    return shell.Shell(settings.Settings(trial_started=trial_started), str(tmp_path),
                       None, tray=False, hotkey=False)


@pytest.fixture
def free(tmp_path):
    a = _shell(tmp_path, LONG_AGO)
    for name, make in (("Up", thumbs_up), ("Down", thumbs_down), ("Peace", peace)):
        a.library.add(name, [canonical(lms, "Right")
                             for lms in recording(make, random.Random(1))])
    a.bridge.signsChanged.emit()
    yield a
    a.close()


def _locked(a) -> list[bool]:
    return [s["locked"] for s in a.bridge.property("customSigns")]


def test_a_new_install_is_in_the_trial(tmp_path):
    a = _shell(tmp_path, TODAY.isoformat())
    try:
        assert a.bridge.property("premiumPlan") == "trial"
        assert a.bridge.property("trialDaysLeft") == 14
        assert a.bridge.property("signLimit") == 20
        assert a.library.limit == 20
    finally:
        a.close()


def test_after_the_trial_one_sign_stays_on(free):
    assert free.bridge.property("premiumPlan") == "free"
    assert free.bridge.property("signLimit") == 1
    assert _locked(free) == [False, True, True]
    assert free.bridge.property("atSignLimit") is True


def test_use_this_one_instead_is_saved(free, tmp_path):
    peace_id = free.bridge.property("customSigns")[2]["id"]
    free.bridge.useSignInstead(peace_id)
    cards = free.bridge.property("customSigns")
    assert [c["name"] for c in cards] == ["Peace", "Up", "Down"]
    assert _locked(free) == [False, True, True]
    from fingerino import signs
    assert signs.load(str(tmp_path)).signs[0].id == peace_id


def test_a_licence_key_unlocks_every_sign(free, seed, tmp_path):
    changed = []
    free.bridge.premiumChanged.connect(lambda: changed.append(True))
    key = licence.make_key(seed, "order-9", "buyer@example.com")
    assert free.bridge.enterLicence(key) == ""
    assert changed
    assert free.bridge.property("premiumPlan") == "premium"
    assert free.bridge.property("licensedTo") == "buyer@example.com"
    assert _locked(free) == [False, False, False]
    assert (tmp_path / licence.FILENAME).exists()

    free.bridge.removeLicence()
    assert free.bridge.property("premiumPlan") == "free"
    assert _locked(free) == [False, True, True]
    assert not (tmp_path / licence.FILENAME).exists()


def test_a_bad_key_changes_nothing(free, seed, tmp_path):
    assert free.bridge.enterLicence("fingerino1.nope.nope") == licence.INVALID
    assert free.bridge.property("premiumPlan") == "free"
    assert not (tmp_path / licence.FILENAME).exists()


def test_a_stored_key_is_read_at_start(tmp_path, seed):
    licence.save(str(tmp_path), licence.make_key(seed, "order-9", "buyer@example.com"))
    a = _shell(tmp_path, LONG_AGO)
    try:
        assert a.bridge.property("premiumPlan") == "premium"
    finally:
        a.close()


def test_the_trial_ends_while_fingerino_runs(tmp_path):
    a = _shell(tmp_path, TODAY.isoformat())
    try:
        for name, make in (("Up", thumbs_up), ("Down", thumbs_down)):
            a.library.add(name, [canonical(lms, "Right")
                                 for lms in recording(make, random.Random(1))])
        assert _locked(a) == [False, False]
        a.refresh_premium(TODAY + dt.timedelta(days=13))
        assert a.bridge.property("trialDaysLeft") == 1
        a.refresh_premium(TODAY + dt.timedelta(days=14))
        assert a.bridge.property("premiumPlan") == "free"
        assert _locked(a) == [False, True]
    finally:
        a.close()


def test_without_the_addon_nothing_is_entitled(free):
    assert not free.addon.loaded
    assert free.bridge.property("addonNote") == ""
    assert not free.entitled("wispr_hold")


def test_until_the_shop_opens_nothing_is_limited(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PREMIUM_URL", "")
    a = _shell(tmp_path, LONG_AGO)          # even with a trial long over
    try:
        for name, make in (("Up", thumbs_up), ("Down", thumbs_down), ("Peace", peace)):
            a.library.add(name, [canonical(lms, "Right")
                                 for lms in recording(make, random.Random(1))])
        assert a.bridge.property("premiumPlan") == "soon"
        assert a.bridge.property("onSale") is False
        assert a.bridge.property("signLimit") == 20
        assert _locked(a) == [False, False, False]
        a.bridge.openPremium()                       # does nothing, opens nothing
    finally:
        a.close()


def test_a_key_works_before_the_shop_opens(tmp_path, seed, monkeypatch):
    """The owner's dry run: a hand-made key shows what a buyer sees."""
    monkeypatch.setattr(config, "PREMIUM_URL", "")
    a = _shell(tmp_path, "")
    try:
        key = licence.make_key(seed, "dry-run", "me@example.com")
        assert a.bridge.enterLicence(key) == ""
        assert a.bridge.property("premiumPlan") == "premium"
        assert a.bridge.property("licensedTo") == "me@example.com"
        a.bridge.removeLicence()
        assert a.bridge.property("premiumPlan") == "soon"
    finally:
        a.close()


def test_the_premium_dialogs_load(free):
    from PySide6.QtCore import QObject
    for name in ("premiumDialog", "licenceDialog", "removeLicenceDialog",
                 "premiumCard", "recordLimitNote", "trialLine"):
        assert free.window.findChild(QObject, name) is not None, name

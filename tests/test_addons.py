"""The add-on hook (addons.py): whatever the add-on does, the free app runs."""

from __future__ import annotations

import sys
import types

import pytest

from fingerino import addons

NAME = "fingerino_test_addon"


def _host(allowed=()):
    return addons.Host("9.9.9", lambda feature: feature in allowed)


def _install(monkeypatch, **attrs) -> types.ModuleType:
    mod = types.ModuleType(NAME)
    for key, value in attrs.items():
        setattr(mod, key, value)
    monkeypatch.setitem(sys.modules, NAME, mod)
    return mod


class _Impl:
    def __init__(self, host):
        self.host = host
        self.features = ("wispr_hold", "mcp_server")


def test_not_installed_is_simply_the_free_version():
    found = addons.load(_host(), "fingerino_no_such_addon")
    assert not found.installed and not found.loaded and found.note == ""
    assert found.features == frozenset()


def test_the_real_addon_is_optional():
    found = addons.load(_host())
    assert found.loaded or not found.installed or found.note


def test_a_matching_addon_is_loaded(monkeypatch):
    _install(monkeypatch, ADDON_API=addons.API, __version__="0.1.0", addon=_Impl)
    host = _host({"wispr_hold"})
    found = addons.load(host, NAME)
    assert found.loaded and found.version == "0.1.0" and found.note == ""
    assert found.features == {"wispr_hold", "mcp_server"}
    # The add-on asks Fingerino what is unlocked; it doesn't decide.
    assert found.impl.host.entitled("wispr_hold")
    assert not found.impl.host.entitled("mcp_server")


@pytest.mark.parametrize("api, says", [
    (addons.API + 1, "needs a newer Fingerino"),
    (0, "too old"),
    (None, "too old"),
])
def test_an_addon_for_another_contract_is_left_alone(monkeypatch, api, says):
    attrs = {"addon": _Impl} if api is None else {"ADDON_API": api, "addon": _Impl}
    _install(monkeypatch, **attrs)
    found = addons.load(_host(), NAME)
    assert found.installed and not found.loaded
    assert says in found.note


def test_an_addon_that_fails_to_start_is_left_alone(monkeypatch):
    def broken(host):
        raise RuntimeError("boom")
    _install(monkeypatch, ADDON_API=addons.API, addon=broken)
    found = addons.load(_host(), NAME)
    assert not found.loaded and "boom" in found.note


def test_an_addon_that_fails_to_import_is_left_alone(tmp_path, monkeypatch):
    (tmp_path / f"{NAME}.py").write_text("import fingerino_missing_dependency\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delitem(sys.modules, NAME, raising=False)
    found = addons.load(_host(), NAME)
    assert found.installed and not found.loaded
    assert "couldn't start" in found.note

"""Regression guard for the window-ownership fix.

winui used to find its window with FindWindowW(None, title), which matches on
title alone across every process. Any window called "fingerino" — an Explorer
folder, say — would then be stripped of its title bar, resized, re-iconed and
pinned topmost. These tests exist so that cannot come back unnoticed.
"""

import sys

import pytest

from fingerino import winui

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="Win32 only")


def test_the_title_only_lookup_is_gone():
    # The vulnerable API itself. If a refactor reintroduces a name like this,
    # the fix has probably been undone with it.
    assert not hasattr(winui, "find_window")
    assert hasattr(winui, "find_own_window")


@windows_only
@pytest.mark.parametrize("handle", [None, 0, 1, 123456789, -1, 2**31 - 1])
def test_owned_rejects_anything_that_is_not_ours(handle):
    # 123456789 and friends are either dead, never valid, or somebody else's —
    # including a handle Windows has recycled to another process's window.
    assert winui._owned(handle) is False


@windows_only
def test_mutators_no_op_on_a_handle_we_do_not_own():
    # Every one of these must return quietly rather than touch the window.
    stranger = 123456789
    winui.lock_size(stranger)
    winui.make_borderless(stranger)
    winui.resize_client(stranger, 100, 100)
    winui.raise_above_all(stranger)
    winui.unpin(stranger)
    winui.apply_icon(stranger, "nonexistent.ico")
    assert winui.set_taskbar_icon(stranger, "nonexistent.ico", "x", "y") is False


def test_helpers_are_inert_off_windows():
    if sys.platform == "win32":
        pytest.skip("this is the non-Windows contract")
    assert winui.find_own_window("anything") is None
    assert winui._owned(1) is False

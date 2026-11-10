"""The app icon (branding.py): drawn in code, cached by artwork version."""

from __future__ import annotations

import pytest

pytest.importorskip("PIL")      # not in the dependency-free CI job

from PIL import Image

from fingerino import branding


def test_every_size_is_a_cream_plate_with_a_dark_hand():
    for size in branding.ICON_SIZES:
        im = branding.render(size).convert("RGBA")
        assert im.size == (size, size)
        assert im.getpixel((0, 0))[3] < 16                  # rounded corner
        centre_row = [im.getpixel((x, size // 2))[:3] for x in range(size)]
        assert any(sum(px) < 150 for px in centre_row), size   # ink
        assert any(sum(px) > 650 for px in centre_row), size   # cream


def test_the_ico_holds_each_size_drawn_for_it(tmp_path):
    path = branding.icon_path(str(tmp_path))
    assert path and path.endswith(f"fingerino-v{branding.ICON_VERSION}.ico")
    with Image.open(path) as ico:
        assert {s[0] for s in ico.info["sizes"]} == set(branding.ICON_SIZES)
        ico.size = (16, 16)
        small = ico.convert("RGBA")
    # The 16px frame is the one drawn for 16px (bigger hand),
    # not the 256px one shrunk.
    assert list(small.getdata()) == list(branding.render(16).getdata())
    assert branding.icon_path(str(tmp_path)) == path       # cached


def test_a_new_logo_replaces_the_old_icon(tmp_path):
    old = tmp_path / "fingerino-v1.ico"
    old.write_bytes(b"old artwork")
    assert branding.icon_path(str(tmp_path))
    assert not old.exists()

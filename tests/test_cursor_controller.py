"""Control-zone mapping and the One Euro smoothing filter."""

import pytest

pytest.importorskip("pynput", exc_type=ImportError,
                    reason="not installed, or installed with no display backend to bind to")

from fingerino.cursor_controller import CursorController, _OneEuro

MAP = CursorController._map_zone


def test_zone_edges_map_to_the_full_range():
    assert MAP(0.2, 0.2) == pytest.approx(0.0)
    assert MAP(0.8, 0.2) == pytest.approx(1.0)
    assert MAP(0.5, 0.2) == pytest.approx(0.5)


def test_outside_the_zone_overshoots_before_the_caller_clamps():
    # _map_zone itself does not clamp; update() does. Pinning that split so a
    # later "tidy-up" cannot silently move the clamp and change the feel.
    assert MAP(0.0, 0.2) < 0.0
    assert MAP(1.0, 0.2) > 1.0


def test_a_degenerate_margin_passes_through():
    assert MAP(0.37, 0.5) == 0.37       # hi <= lo
    assert MAP(0.37, 0.9) == 0.37


def test_filter_returns_the_first_sample_untouched():
    f = _OneEuro(1.0, 0.02, 1.0)
    assert f(0.0, 100.0) == 100.0


def test_filter_ignores_a_non_advancing_clock():
    f = _OneEuro(1.0, 0.02, 1.0)
    f(1.0, 100.0)
    assert f(1.0, 999.0) == 100.0       # same timestamp
    assert f(0.5, 999.0) == 100.0       # clock went backwards


def test_filter_damps_a_step_then_converges():
    f = _OneEuro(1.0, 0.02, 1.0)
    f(0.0, 0.0)
    first = f(1 / 30, 100.0)
    assert 0.0 < first < 100.0          # damped, not passed straight through
    last = first
    for i in range(2, 200):
        last = f(i / 30, 100.0)
    assert last == pytest.approx(100.0, abs=1.0)


def test_reset_forgets_history():
    f = _OneEuro(1.0, 0.02, 1.0)
    f(0.0, 0.0)
    f(1 / 30, 100.0)
    f.reset()
    assert f(2 / 30, 500.0) == 500.0    # no lurch from the old position

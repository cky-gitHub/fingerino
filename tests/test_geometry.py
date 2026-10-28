"""Pure geometry behind the two-hand "X" exit. Stdlib only — runs anywhere."""

import math

import pytest

from fingerino.gesture_detector import _cross_angle_deg, _segments_cross


def test_crossing_segments_cross():
    assert _segments_cross((0, 0), (1, 1), (0, 1), (1, 0))


@pytest.mark.parametrize("p3,p4", [
    ((0, 1), (1, 1)),        # parallel
    ((2, 2), (3, 3)),        # collinear, disjoint
    ((2, 0), (3, 1)),        # skew, no overlap
])
def test_non_crossing_segments_do_not(p3, p4):
    assert not _segments_cross((0, 0), (1, 1), p3, p4)


def test_perpendicular_is_ninety_degrees():
    assert _cross_angle_deg((0, 0), (1, 0), (0, 0), (0, 1)) == pytest.approx(90.0)


def test_angle_is_undirected():
    # Two hands laid end to end are aligned, not crossed — 180 deg must read
    # as 0, or EXIT_MIN_ANGLE_DEG would accept a straight line as an X.
    assert _cross_angle_deg((0, 0), (1, 0), (0, 0), (-1, 0)) == pytest.approx(0.0)
    assert _cross_angle_deg((0, 0), (1, 0), (0, 0), (1, 0)) == pytest.approx(0.0)


def test_forty_five_degrees():
    assert _cross_angle_deg((0, 0), (1, 0), (0, 0), (1, 1)) == pytest.approx(45.0)


def test_zero_length_segment_is_not_an_angle():
    assert _cross_angle_deg((0, 0), (0, 0), (0, 0), (1, 1)) == 0.0


def test_angle_never_exceeds_ninety():
    for deg in range(0, 360, 7):
        r = math.radians(deg)
        a = _cross_angle_deg((0, 0), (1, 0), (0, 0), (math.cos(r), math.sin(r)))
        assert 0.0 <= a <= 90.0 + 1e-9

"""fmu.evaluation.torus_shift on small grids: every shift used once, which way the map moves, the
ForestGEO counts and the p-value, and the orientations off unless asked for."""

from __future__ import annotations

import math

import numpy as np
import pytest

from fmu.evaluation.agreement import adjusted_rand_index
from fmu.evaluation.torus_shift import torus_shift_test


def ari(f, s):
    return adjusted_rand_index(f, s)


def test_every_shift_once_and_the_counts_add_up():
    rng = np.random.default_rng(1)
    stands = np.repeat(np.repeat(np.arange(6).reshape(2, 3), 3, axis=0), 3, axis=1)   # 6 x 9, six blocks
    field = (stands % 3) + (rng.random(stands.shape) < 0.1)
    r = torus_shift_test(field, stands, ari)
    assert r.n_maps == 6 * 9 and len(r.null) == 6 * 9 - 1
    assert len(set(r.maps)) == len(r.maps) and ("identity", 0, 0) not in r.maps
    assert r.n_greater + r.n_less + r.n_equal == r.n_maps
    b = int((r.null >= r.observed - 1e-12).sum())
    assert r.p_value == pytest.approx((b + 1) / (len(r.null) + 1))
    # brute force: each null value is the statistic on np.roll of the map
    k = r.maps.index(("identity", 2, 5))
    assert r.null[k] == pytest.approx(ari(field.ravel(), np.roll(np.roll(stands, 2, 0), 5, 1).ravel()))


def test_the_stand_map_moves_and_the_field_stays():
    stands = np.arange(12).reshape(3, 4)
    field = np.zeros((3, 4))
    first = torus_shift_test(field, stands, lambda f, s: float(s[0]))
    # quadrat (0, 0) reads stands[(0 - dr) mod 3, (0 - dc) mod 4]
    for (o, dr, dc), v in zip(first.maps, first.null, strict=True):
        assert o == "identity" and v == stands[(-dr) % 3, (-dc) % 4]
    assert first.observed == 0


def test_a_map_that_matches_the_field_beats_every_shift():
    # irregular stands: no shift turns the map into a relabelling of itself
    stands = np.array([[0, 0, 1, 1, 1],
                       [0, 2, 2, 1, 4],
                       [3, 2, 2, 4, 4],
                       [3, 3, 3, 3, 4]])
    field = stands.copy()
    r = torus_shift_test(field, stands, ari)
    assert r.observed == pytest.approx(1.0)
    assert r.n_greater == r.n_maps - 1 and r.p_value == pytest.approx(1 / r.n_maps)


def test_missing_quadrats_and_no_stand():
    stands = np.array([[0, 0, 1, 1], [0, 0, 1, -1]])
    field = np.array([[1.0, 1.0, 2.0, np.nan], [1.0, 1.0, 2.0, 2.0]])
    r = torus_shift_test(field, stands, ari)
    assert r.n_quadrats_used == 6
    coded = torus_shift_test(np.where(np.isnan(field), -9, field).astype(int), stands, ari, field_missing=-9)
    assert coded.observed == pytest.approx(r.observed) and coded.n_quadrats_used == 6


def test_orientations_are_off_unless_named():
    stands = np.arange(6).reshape(2, 3)
    field = np.arange(6).reshape(2, 3) % 2
    base = torus_shift_test(field, stands, ari)
    more = torus_shift_test(field, stands, ari, orientations=("identity", "rotate_180", "flip_rows", "flip_cols"))
    assert base.n_maps == 6 and more.n_maps == 24
    assert {o for o, _, _ in more.maps} == {"identity", "rotate_180", "flip_rows", "flip_cols"}
    assert more.maps.count(("rotate_180", 0, 0)) == 1
    with pytest.raises(ValueError, match="identity"):
        torus_shift_test(field, stands, ari, orientations=("rotate_180",))
    with pytest.raises(ValueError):
        torus_shift_test(field, stands, ari, orientations=("identity", "spin"))


def test_bad_grids():
    with pytest.raises(ValueError):
        torus_shift_test(np.zeros((2, 3)), np.zeros((3, 2), int), ari)
    with pytest.raises(ValueError):
        torus_shift_test(np.zeros((1, 1)), np.zeros((1, 1), int), ari)
    r = torus_shift_test(np.full((2, 2), np.nan), np.zeros((2, 2), int), ari)
    assert math.isnan(r.observed) and math.isnan(r.p_value)


def test_a_map_with_a_period_reproduces_itself_under_some_shifts():
    """Column stripes: every shift on the torus gives four column stripes again, the same partition
    relabelled, so every map ties with the real one (ARI ignores stand labels) and p is 1."""
    stands = np.tile(np.arange(4), (3, 1))           # 3 x 4, four column stands
    r = torus_shift_test(stands.copy(), stands, ari)
    assert r.n_equal == 3 * 4                         # every shift is a relabelling of the stripes
    assert r.p_value == pytest.approx(1.0)


def test_an_infinite_observed_value_is_not_a_tie_with_every_map():
    """B24 (review of 19 Oct 2026): with the observed statistic infinite, the tie tolerance was inf and
    `observed - tol` NaN, so every map counted as equal. Ties now use permutation_p_value's rule
    (no tolerance for an infinite value), and the counts agree with the p-value."""
    stands = np.arange(12).reshape(3, 4)
    field = np.zeros((3, 4))

    def first_quadrat(inf_at):
        return lambda f, s: math.inf if s[0] in inf_at else float(s[0])

    r = torus_shift_test(field, stands, first_quadrat({0}))
    assert r.observed == math.inf
    assert (r.n_greater, r.n_less, r.n_equal) == (11, 0, 1)
    assert r.p_value == pytest.approx(1 / 12)
    # one shifted map is infinite as well: a tie
    r = torus_shift_test(field, stands, first_quadrat({0, 5}))
    assert (r.n_greater, r.n_less, r.n_equal) == (10, 0, 2)
    assert r.p_value == pytest.approx(2 / 12)
    r = torus_shift_test(field, stands, lambda f, s: -math.inf if s[0] == 0 else float(s[0]), alternative="less")
    assert (r.n_greater, r.n_less, r.n_equal) == (0, 11, 1)
    assert r.p_value == pytest.approx(1 / 12)

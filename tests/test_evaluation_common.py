"""Tests of the shared helpers in `fmu.evaluation._common`.

Every expected value here is worked out by hand or comes from an independent
library (scipy's `pdist` and `squareform`, pandas' quantiles). No site data.
"""

from __future__ import annotations

import importlib
import importlib.util

import numpy as np
import pandas as pd
import pytest
from scipy.spatial.distance import pdist, squareform

from fmu.evaluation import _common as common

# ---------------------------------------------------------------------------
# The package itself
# ---------------------------------------------------------------------------


def test_package_imports_without_its_other_modules():
    pkg = importlib.import_module("fmu.evaluation")
    assert pkg.__doc__
    for module in (
        "agreement",
        "pairs",
        "permutation",
        "spatial_null",
        "segmentation_accuracy",
        "unsupervised",
        "synthetic",
    ):
        assert f"`{module}`" in pkg.__doc__
    # Nothing is imported eagerly: the package file holds a docstring only, so
    # it imports whichever of its modules exist.
    source = importlib.util.find_spec("fmu.evaluation").origin
    with open(source, encoding="utf-8") as fh:
        assert "import " not in fh.read().split('"""')[2]


# ---------------------------------------------------------------------------
# Random numbers
# ---------------------------------------------------------------------------


def test_same_seed_same_numbers():
    a = common.as_generator(7).random(5)
    b = common.as_generator(7).random(5)
    assert np.array_equal(a, b)
    assert not np.array_equal(a, common.as_generator(8).random(5))


def test_a_generator_is_passed_through_and_advanced():
    rng = np.random.default_rng(1)
    assert common.as_generator(rng) is rng


def test_seed_sequence_is_accepted():
    a = common.as_generator(np.random.SeedSequence(3)).random(3)
    assert np.array_equal(a, np.random.default_rng(np.random.SeedSequence(3)).random(3))


@pytest.mark.parametrize("bad", [None, 1.5, "7", True])
def test_unseeded_or_wrong_seed_is_refused(bad):
    with pytest.raises(TypeError):
        common.as_generator(bad)
    with pytest.raises(TypeError):
        common.child_generators(bad, 2)


def test_negative_seed_is_refused():
    with pytest.raises(ValueError):
        common.as_generator(-1)


def test_child_generators_are_independent_of_how_many_are_asked_for():
    three = [g.random(4) for g in common.child_generators(11, 3)]
    five = [g.random(4) for g in common.child_generators(11, 5)]
    for a, b in zip(three, five[:3], strict=True):
        assert np.array_equal(a, b)
    assert not np.array_equal(three[0], three[1])
    assert common.child_generators(11, 0) == []
    with pytest.raises(ValueError):
        common.child_generators(11, -1)


def test_child_generators_from_a_generator_are_new_each_call():
    rng = np.random.default_rng(5)
    first = common.child_generators(rng, 2)[0].random(3)
    second = common.child_generators(rng, 2)[0].random(3)
    assert not np.array_equal(first, second)


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def test_common_length():
    assert common.common_length(a=[1, 2, 3], b=np.zeros((3, 2)), c=None) == 3
    with pytest.raises(ValueError, match="differ in length"):
        common.common_length(a=[1, 2], b=[1, 2, 3])
    with pytest.raises(ValueError):
        common.common_length(a=None)


def test_as_float_matrix():
    assert common.as_float_matrix([1, 2, 3]).shape == (3, 1)
    m = common.as_float_matrix([[1, np.nan], [3, 4]])
    assert m.dtype == np.float64 and np.isnan(m[0, 1])
    with pytest.raises(ValueError, match="NaN"):
        common.as_float_matrix([[1, np.nan]], allow_nan=False)
    with pytest.raises(ValueError, match="infinite"):
        common.as_float_matrix([[1, np.inf]])
    with pytest.raises(ValueError, match="rows"):
        common.as_float_matrix([[1, 2]], n_rows=2)
    with pytest.raises(ValueError):
        common.as_float_matrix(np.zeros((2, 2, 2)))


def test_as_float_matrix_does_not_change_its_input():
    x = np.array([[1.0, 2.0]])
    out = common.as_float_matrix(x)
    out[0, 0] = 99.0
    assert x[0, 0] == 1.0


def test_as_coords():
    assert common.as_coords([[0, 0], [3, 4]]).shape == (2, 2)
    with pytest.raises(ValueError, match="shape"):
        common.as_coords([[0, 0, 0]])
    with pytest.raises(ValueError, match="missing or infinite"):
        common.as_coords([[0, np.nan]])
    with pytest.raises(ValueError, match="rows"):
        common.as_coords([[0, 0]], n_rows=3)


def test_as_codes_accepts_codes_and_whole_floats():
    assert common.as_codes([0, 2, -1]).tolist() == [0, 2, -1]
    out = common.as_codes(np.array([0.0, 3.0, -1.0]))
    assert out.dtype == np.int64 and out.tolist() == [0, 3, -1]


@pytest.mark.parametrize(
    "bad",
    [[0.5, 1.0], [0.0, np.nan], ["a", "b"], [0, -2], [[0, 1]], [True, False]],
)
def test_as_codes_refuses_what_is_not_a_code(bad):
    with pytest.raises(ValueError):
        common.as_codes(bad)


def test_as_codes_length_and_missing():
    with pytest.raises(ValueError, match="expected 3"):
        common.as_codes([0, 1], n=3)
    with pytest.raises(ValueError, match="missing"):
        common.as_codes([0, -1], allow_missing=False)


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------


def test_encode_labels_strings_and_missing():
    codes, classes = common.encode_labels(["b", "a", None, "b"])
    assert codes.tolist() == [1, 0, -1, 1]
    assert classes.tolist() == ["a", "b"]


def test_encode_labels_numbers_with_gaps_and_nan():
    codes, classes = common.encode_labels([30.0, np.nan, 10.0, 30.0])
    assert codes.tolist() == [1, -1, 0, 1]
    assert classes.tolist() == [10.0, 30.0]


def test_encode_labels_extra_missing_value():
    codes, classes = common.encode_labels([5, -1, 7], missing=(-1,))
    assert codes.tolist() == [0, -1, 1]
    assert classes.tolist() == [5, 7]


def test_encode_labels_empty_and_all_missing():
    assert common.encode_labels([])[0].shape == (0,)
    codes, classes = common.encode_labels([None, None])
    assert codes.tolist() == [-1, -1] and len(classes) == 0


def test_encode_labels_refuses_mixed_kinds_and_matrices():
    with pytest.raises(ValueError, match="mix"):
        common.encode_labels(np.array([1, "1", None], dtype=object))
    with pytest.raises(ValueError, match="one-dimensional"):
        common.encode_labels([[1, 2]])


def test_combine_labels_makes_restarting_ids_unique():
    district = ["x", "x", "y", "y", None]
    stand = [5, 6, 5, 5, 5]
    assert common.combine_labels(district, stand).tolist() == [0, 1, 2, 2, -1]
    assert common.combine_labels(stand).tolist() == [0, 1, 0, 0, 0]
    with pytest.raises(ValueError):
        common.combine_labels()
    with pytest.raises(ValueError, match="differ in length"):
        common.combine_labels([1, 2], [1, 2, 3])


def test_check_one_type_per_stand():
    common.check_one_type_per_stand([0, 0, 1, -1, -1], [2, 2, 2, 0, 1])
    common.check_one_type_per_stand([0, 0], [-1, -1])
    common.check_one_type_per_stand([-1, -1], [0, 1])
    with pytest.raises(ValueError, match="more than one type"):
        common.check_one_type_per_stand([0, 0, 1], [2, 3, 2])
    with pytest.raises(ValueError, match="more than one type"):
        common.check_one_type_per_stand([0, 0], [2, -1])


# ---------------------------------------------------------------------------
# Robust scaling
# ---------------------------------------------------------------------------


def test_robust_scale_known_values():
    # 0..4: median 2, quartiles 1 and 3, interquartile range 2.
    out = common.robust_scale([0.0, 1.0, 2.0, 3.0, 4.0])
    assert np.allclose(out[:, 0], [-1.0, -0.5, 0.0, 0.5, 1.0])


def test_robust_scale_matches_pandas_quantiles():
    rng = np.random.default_rng(0)
    df = pd.DataFrame(rng.lognormal(size=(41, 3)))
    expected = (df - df.median()) / (df.quantile(0.75) - df.quantile(0.25))
    assert np.allclose(common.robust_scale(df.to_numpy()), expected.to_numpy())


def test_robust_scale_ignores_units_and_outliers_do_not_set_the_scale():
    x = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
    assert np.allclose(common.robust_scale(x), common.robust_scale(1000.0 * x + 7.0))
    with_outlier = np.array([0.0, 1.0, 2.0, 3.0, 4.0e6])
    assert np.allclose(common.robust_scale(with_outlier)[:4, 0], [-1.0, -0.5, 0.0, 0.5])


def test_zero_interquartile_range_falls_back_to_standard_deviation():
    # Seven zeros and one 8: quartiles are both 0, so the range is 0.
    x = np.array([0.0] * 7 + [8.0])
    center, scale = common.robust_center_scale(x)
    assert center[0] == 0.0
    assert scale[0] == pytest.approx(np.std(x, ddof=1))
    assert common.robust_scale(x)[-1, 0] == pytest.approx(8.0 / np.std(x, ddof=1))


def test_constant_column_scales_to_zeros():
    center, scale = common.robust_center_scale([[3.0], [3.0], [3.0]])
    assert center.tolist() == [3.0] and scale.tolist() == [1.0]
    assert np.array_equal(common.robust_scale([[3.0], [3.0], [3.0]]), np.zeros((3, 1)))
    assert np.array_equal(common.robust_scale([[3.0]]), np.zeros((1, 1)))


def test_robust_scale_missing_values_stay_missing_and_are_left_out():
    x = np.array([0.0, 1.0, 2.0, 3.0, 4.0, np.nan])
    out = common.robust_scale(x)
    assert np.isnan(out[5, 0])
    assert np.allclose(out[:5, 0], [-1.0, -0.5, 0.0, 0.5, 1.0])


def test_robust_scale_refuses_empty_input():
    with pytest.raises(ValueError, match="no rows"):
        common.robust_scale(np.zeros((0, 2)))
    with pytest.raises(ValueError, match="no value at all"):
        common.robust_scale([[1.0, np.nan], [2.0, np.nan]])


# ---------------------------------------------------------------------------
# Pairs
# ---------------------------------------------------------------------------


def test_n_pairs():
    assert [common.n_pairs(n) for n in (0, 1, 2, 4, 267)] == [0, 0, 1, 6, 35511]
    with pytest.raises(ValueError):
        common.n_pairs(-1)


def test_pair_indices_are_in_pdist_order():
    i, j = common.pair_indices(4)
    assert i.tolist() == [0, 0, 0, 1, 1, 2]
    assert j.tolist() == [1, 2, 3, 2, 3, 3]
    pts = np.random.default_rng(1).normal(size=(9, 2))
    i, j = common.pair_indices(9)
    assert np.allclose(pdist(pts), np.hypot(*(pts[i] - pts[j]).T))
    assert common.pair_indices(1)[0].shape == (0,)


def test_condensed_index_agrees_with_squareform():
    n = 7
    square = squareform(np.arange(common.n_pairs(n), dtype=float))
    i, j = common.pair_indices(n)
    assert common.condensed_index(i, j, n).tolist() == list(range(common.n_pairs(n)))
    assert common.condensed_index(j, i, n).tolist() == list(range(common.n_pairs(n)))
    assert common.condensed_index(5, 2, n) == square[5, 2]
    with pytest.raises(ValueError, match="not a pair"):
        common.condensed_index(3, 3, n)
    with pytest.raises(ValueError):
        common.condensed_index(0, 7, n)


def test_as_condensed_distance_takes_both_forms():
    pts = np.random.default_rng(2).normal(size=(6, 3))
    d = pdist(pts)
    assert np.allclose(common.as_condensed_distance(d), d)
    assert np.allclose(common.as_condensed_distance(squareform(d)), d)
    assert np.allclose(common.as_condensed_distance(d, n=6), d)
    assert common.as_condensed_distance(np.zeros(0)).shape == (0,)


def test_as_condensed_distance_refuses_bad_input():
    d = pdist(np.random.default_rng(3).normal(size=(5, 2)))
    square = squareform(d)
    with pytest.raises(ValueError, match="expected 4"):
        common.as_condensed_distance(d, n=4)
    with pytest.raises(ValueError, match="not n"):
        common.as_condensed_distance(np.ones(5))
    lopsided = square.copy()
    lopsided[0, 1] += 1.0
    with pytest.raises(ValueError, match="symmetric"):
        common.as_condensed_distance(lopsided)
    with pytest.raises(ValueError, match="diagonal"):
        common.as_condensed_distance(square + np.eye(5))
    with pytest.raises(ValueError, match="negative"):
        common.as_condensed_distance(-d)
    with pytest.raises(ValueError, match="square"):
        common.as_condensed_distance(np.zeros((2, 3)))
    with_gap = d.copy()
    with_gap[0] = np.nan
    with pytest.raises(ValueError, match="NaN"):
        common.as_condensed_distance(with_gap)
    assert np.isnan(common.as_condensed_distance(with_gap, allow_nan=True)[0])


# ---------------------------------------------------------------------------
# Distance bands
# ---------------------------------------------------------------------------


def test_band_index_half_open_bands():
    edges = [0.0, 100.0, 200.0, np.inf]
    dist = [0.0, 99.9, 100.0, 199.0, 200.0, 5e6, np.nan]
    assert common.band_index(dist, edges).tolist() == [0, 0, 1, 1, 2, 2, -1]


def test_band_index_outside_the_bands_is_missing():
    edges = [50.0, 100.0, 200.0]
    assert common.band_index([10.0, 50.0, 150.0, 200.0, 900.0], edges).tolist() == [-1, 0, 1, -1, -1]


@pytest.mark.parametrize(
    "bad",
    [[0.0], [0.0, 0.0, 10.0], [10.0, 5.0], [-1.0, 5.0], [0.0, np.inf, np.inf], [0.0, np.nan]],
)
def test_bad_band_edges_are_refused(bad):
    with pytest.raises(ValueError):
        common.validate_band_edges(bad)


# ---------------------------------------------------------------------------
# What the map claims about a pair
# ---------------------------------------------------------------------------


def test_pair_claims_the_three_claims():
    stand = np.array([0, 0, 1, 2, -1])
    typ = np.array([5, 5, 5, 6, -1])
    i, j = common.pair_indices(5)
    claims = common.pair_claims(stand, typ, i, j)
    by_pair = dict(zip(zip(i.tolist(), j.tolist(), strict=True), claims.tolist(), strict=True))
    assert by_pair[(0, 1)] == common.CLAIM_SAME_STAND
    assert by_pair[(0, 2)] == common.CLAIM_SAME_TYPE
    assert by_pair[(0, 3)] == common.CLAIM_DIFF_TYPE
    assert by_pair[(2, 3)] == common.CLAIM_DIFF_TYPE
    assert all(by_pair[(k, 4)] == common.CLAIM_NONE for k in range(4))
    assert claims.dtype == np.int8


def test_pair_claims_types_are_not_compared_across_super_groups():
    stand = np.array([0, 1, 2, 3])
    typ = np.array([1, 1, 1, -1])
    district = np.array([0, 0, 1, 1])
    i, j = common.pair_indices(4)
    claims = common.pair_claims(stand, typ, i, j, super_group=district)
    by_pair = dict(zip(zip(i.tolist(), j.tolist(), strict=True), claims.tolist(), strict=True))
    assert by_pair[(0, 1)] == common.CLAIM_SAME_TYPE
    # Same type number, different district: it is not the same forest type.
    assert by_pair[(0, 2)] == common.CLAIM_TYPE_UNKNOWN
    # A stand with no type cannot be compared with anything.
    assert by_pair[(2, 3)] == common.CLAIM_TYPE_UNKNOWN


def test_pair_claims_without_types():
    i, j = common.pair_indices(3)
    claims = common.pair_claims(np.array([0, 0, 1]), None, i, j)
    assert claims.tolist() == [common.CLAIM_SAME_STAND, common.CLAIM_TYPE_UNKNOWN, common.CLAIM_TYPE_UNKNOWN]


def test_pair_claims_same_stand_wins_over_a_missing_type():
    claims = common.pair_claims(np.array([0, 0]), np.array([-1, -1]), [0], [1])
    assert claims.tolist() == [common.CLAIM_SAME_STAND]


# ---------------------------------------------------------------------------
# The permutation p-value
# ---------------------------------------------------------------------------


def test_p_value_counts_the_observed_value():
    null = np.arange(1.0, 100.0)  # 1..99
    # 99 and nothing else is >= 99: (1 + 1) / (99 + 1).
    assert common.permutation_p_value(99.0, null, "greater") == pytest.approx(0.02)
    # Nothing reaches 1000: the smallest possible value, never zero.
    assert common.permutation_p_value(1000.0, null, "greater") == pytest.approx(0.01)
    assert common.permutation_p_value(-5.0, null, "greater") == pytest.approx(1.0)
    assert common.permutation_p_value(1.0, null, "less") == pytest.approx(0.02)


def test_p_value_two_sided_is_twice_the_smaller_tail():
    null = np.arange(1.0, 100.0)
    assert common.permutation_p_value(99.0, null, "two-sided") == pytest.approx(0.04)
    assert common.permutation_p_value(1.0, null, "two-sided") == pytest.approx(0.04)
    assert common.permutation_p_value(50.0, null, "two-sided") == 1.0


def test_p_value_ties_count_as_extreme_within_tolerance():
    null = np.array([0.3, 0.3 - 1e-15, 0.3 + 1e-15, 0.1])
    assert common.permutation_p_value(0.3, null, "greater") == pytest.approx(4 / 5)
    assert common.permutation_p_value(0.3, null, "less") == pytest.approx(5 / 5)


def test_p_value_leaves_out_undefined_permutations():
    null = np.array([1.0, np.nan, 3.0, np.nan])
    assert common.permutation_p_value(2.0, null, "greater") == pytest.approx(2 / 3)


def test_p_value_undefined_cases():
    assert np.isnan(common.permutation_p_value(np.nan, [1.0, 2.0], "greater"))
    assert np.isnan(common.permutation_p_value(1.0, [], "greater"))
    assert np.isnan(common.permutation_p_value(1.0, [np.nan], "greater"))
    with pytest.raises(ValueError):
        common.permutation_p_value(1.0, [1.0], "upper")  # type: ignore[arg-type]


def test_p_value_is_uniform_when_there_is_no_effect():
    # With 19 permutations a test at 0.05 rejects only when the observed value
    # is the largest of the 20, which happens one time in twenty.
    rng = np.random.default_rng(4)
    draws = rng.normal(size=(4000, 20))
    p = np.array([common.permutation_p_value(row[0], row[1:], "greater") for row in draws])
    assert p.min() == pytest.approx(0.05)
    assert abs((p <= 0.05).mean() - 0.05) < 0.015


# ---------------------------------------------------------------------------
# The statistic contract
# ---------------------------------------------------------------------------


def test_statistic_calls_its_function_and_returns_a_float():
    stat = common.Statistic(
        "share_in_stand_0", lambda sid, typ: np.mean(sid == 0), "greater"
    )
    out = stat(np.array([0, 0, 1, 2]))
    assert isinstance(out, float) and out == 0.5
    assert stat.name == "share_in_stand_0" and stat.alternative == "greater"


def test_statistic_passes_types_through():
    seen = {}

    def func(sid, typ):
        seen["typ"] = typ
        return 1.0

    common.Statistic("s", func, "two-sided")(np.array([0]), np.array([3]))
    assert seen["typ"].tolist() == [3]
    common.Statistic("s", func, "two-sided")(np.array([0]))
    assert seen["typ"] is None


def test_statistic_needs_a_name_and_a_declared_tail():
    with pytest.raises(ValueError):
        common.Statistic("", lambda s, t: 0.0, "greater")
    with pytest.raises(ValueError):
        common.Statistic("s", lambda s, t: 0.0, "upper")  # type: ignore[arg-type]


def test_statistic_cannot_be_changed_after_it_is_built():
    stat = common.Statistic("s", lambda s, t: 0.0, "greater")
    with pytest.raises(AttributeError):
        stat.alternative = "less"  # type: ignore[misc]

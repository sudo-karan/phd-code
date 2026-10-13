"""Tests of `fmu.evaluation.agreement`: Rand and adjusted Rand index.

Expected values are worked out by hand, counted pair by pair in the test, or
taken from scikit-learn (`rand_score`, `adjusted_rand_score`). All data is
built here. No site data.
"""

from __future__ import annotations

import itertools
import math

import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import adjusted_rand_score, rand_score

from fmu.evaluation import agreement as ag
from fmu.evaluation._common import Statistic


def brute_counts(a, b):
    """Count the pairs one by one: (n, N, T, P, Q) over plots with both labels."""
    plots = [(x, y) for x, y in zip(a, b, strict=True) if x >= 0 and y >= 0]
    total = both = in_a = in_b = 0
    for (a1, b1), (a2, b2) in itertools.combinations(plots, 2):
        total += 1
        in_a += a1 == a2
        in_b += b1 == b2
        both += (a1 == a2) and (b1 == b2)
    return len(plots), total, both, in_a, in_b


def textbook_ari(total, both, in_a, in_b):
    """(T - E) / (M - E) with E = P Q / N and M = (P + Q) / 2, written out."""
    expected = in_a * in_b / total
    maximum = (in_a + in_b) / 2
    return (both - expected) / (maximum - expected)


def random_groupings(rng, n, k_a, k_b):
    return rng.integers(0, k_a, size=n), rng.integers(0, k_b, size=n)


# ---------------------------------------------------------------------------
# Hand-worked case (spec test 1)
# ---------------------------------------------------------------------------


def test_hand_worked_counts_and_indices():
    a = [0, 0, 1, 1]
    b = [0, 0, 1, 2]
    # Pairs: (0,1) together in both; (2,3) together in a only; the other four
    # apart in both.
    counts = ag.pair_counts(a, b)
    assert counts == ag.PairCounts(n=4, total=6, both=1, a_only=1, b_only=0, neither=4)
    assert counts.both + counts.a_only + counts.b_only + counts.neither == counts.total
    assert ag.rand_index(a, b) == pytest.approx(5 / 6)
    # T = 1, P = 2, Q = 1, N = 6: E = 1/3, M = 3/2, (1 - 1/3) / (3/2 - 1/3) = 4/7.
    assert ag.adjusted_rand_index(a, b) == pytest.approx(4 / 7)
    result = ag.agreement(a, b)
    assert result.rand == pytest.approx(5 / 6)
    assert result.adjusted_rand == pytest.approx(4 / 7)
    assert result.counts == counts
    assert (result.n_groups_a, result.n_groups_b) == (2, 3)
    # Ceiling: T could be at most min(P, Q) = 1, which it is.
    assert result.adjusted_rand_max == pytest.approx(4 / 7)


# ---------------------------------------------------------------------------
# Against scikit-learn and against a pair-by-pair count (spec test 2)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", range(20))
def test_matches_scikit_learn_on_random_groupings(case):
    rng = np.random.default_rng(1000 + case)
    n = int(rng.integers(5, 301))
    k_a, k_b = (int(k) for k in rng.integers(2, 41, size=2))
    a, b = random_groupings(rng, n, k_a, k_b)
    # Keep clear of the two cases where scikit-learn returns 1.0 and we NaN.
    a[:2] = [0, 1]
    b[:2] = [0, 0]
    assert ag.rand_index(a, b) == pytest.approx(rand_score(a, b), abs=1e-12)
    assert ag.adjusted_rand_index(a, b) == pytest.approx(adjusted_rand_score(a, b), abs=1e-12)


@pytest.mark.parametrize(
    ("n", "k_small_groups", "k_large_groups"),
    [(60, 30, 2), (267, 120, 5), (267, 200, 3), (300, 150, 4), (40, 39, 2)],
)
def test_many_small_groups_against_few_large_ones(n, k_small_groups, k_large_groups):
    # The shape of the drawing question: many small stands, few field types.
    rng = np.random.default_rng(n * 1000 + k_small_groups)
    fine = rng.integers(0, k_small_groups, size=n)
    coarse = rng.integers(0, k_large_groups, size=n)
    fine[:2] = 0  # at least one pair shares a small group
    coarse[:2] = [0, 1]
    for a, b in ((fine, coarse), (coarse, fine)):
        assert ag.rand_index(a, b) == pytest.approx(rand_score(a, b), abs=1e-12)
        assert ag.adjusted_rand_index(a, b) == pytest.approx(adjusted_rand_score(a, b), abs=1e-12)
    # A fine grouping nested in the coarse one: every small group is pure.
    nested = coarse * k_small_groups + fine
    assert ag.adjusted_rand_index(coarse, nested) == pytest.approx(
        adjusted_rand_score(coarse, nested), abs=1e-12
    )
    result = ag.agreement(coarse, nested)
    assert result.adjusted_rand == pytest.approx(result.adjusted_rand_max, abs=1e-12)
    assert result.adjusted_rand < 1


@pytest.mark.parametrize("seed", range(8))
def test_matches_a_pair_by_pair_count(seed):
    rng = np.random.default_rng(seed)
    n = int(rng.integers(2, 40))
    a, b = random_groupings(rng, n, int(rng.integers(1, 6)), int(rng.integers(1, 12)))
    a[rng.random(n) < 0.15] = -1
    b[rng.random(n) < 0.15] = -1
    used, total, both, in_a, in_b = brute_counts(a, b)
    counts = ag.pair_counts(a, b)
    assert counts == ag.PairCounts(
        n=used,
        total=total,
        both=both,
        a_only=in_a - both,
        b_only=in_b - both,
        neither=total - in_a - in_b + both,
    )
    if total:
        assert ag.rand_index(a, b) == pytest.approx((total - in_a - in_b + 2 * both) / total)
    expected = in_a * in_b / total if total else 0.0
    if total and (in_a + in_b) / 2 - expected > 0:
        assert ag.adjusted_rand_index(a, b) == pytest.approx(
            textbook_ari(total, both, in_a, in_b), abs=1e-12
        )
    else:
        assert math.isnan(ag.adjusted_rand_index(a, b))


def test_sparse_codes_take_the_same_counts(monkeypatch):
    # Very large code values use the path that does not lay out the full table.
    rng = np.random.default_rng(5)
    a, b = random_groupings(rng, 80, 4, 9)
    dense = ag.agreement(a, b)
    sparse = ag.agreement(a * 3_000_000 + 7, b * 5_000_000 + 11)
    assert sparse == dense
    monkeypatch.setattr(ag, "_MAX_TABLE_CELLS", 0)
    assert ag.agreement(a, b) == dense


# ---------------------------------------------------------------------------
# Properties (spec tests 3 and 4)
# ---------------------------------------------------------------------------


def test_identical_groupings_score_one():
    a = [0, 0, 1, 1, 2, 2, 2]
    result = ag.agreement(a, a)
    assert result.rand == 1.0
    assert result.adjusted_rand == 1.0
    assert result.adjusted_rand_max == 1.0


def test_group_names_do_not_matter_and_the_index_is_symmetric():
    rng = np.random.default_rng(11)
    a, b = random_groupings(rng, 90, 4, 7)
    renamed = np.array([5, 0, 3, 9, 1, 2, 8])[b]
    assert ag.adjusted_rand_index(a, renamed) == ag.adjusted_rand_index(a, b)
    assert ag.rand_index(a, renamed) == ag.rand_index(a, b)
    assert ag.adjusted_rand_index(a, b) == ag.adjusted_rand_index(b, a)
    assert ag.rand_index(a, b) == ag.rand_index(b, a)
    forward, backward = ag.pair_counts(a, b), ag.pair_counts(b, a)
    assert (forward.a_only, forward.b_only) == (backward.b_only, backward.a_only)


def test_plots_with_a_missing_label_are_left_out():
    rng = np.random.default_rng(12)
    a, b = random_groupings(rng, 120, 3, 6)
    a[rng.random(120) < 0.2] = -1
    b[rng.random(120) < 0.2] = -1
    keep = (a >= 0) & (b >= 0)
    assert 0 < keep.sum() < 120
    assert ag.agreement(a, b) == ag.agreement(a[keep], b[keep])
    assert ag.pair_counts(a, b).n == int(keep.sum())
    assert ag.adjusted_rand_index(a, b) == pytest.approx(adjusted_rand_score(a[keep], b[keep]))


def test_inputs_are_not_modified_and_calls_repeat():
    rng = np.random.default_rng(13)
    a, b = random_groupings(rng, 50, 3, 5)
    a_before, b_before = a.copy(), b.copy()
    first = ag.agreement(a, b)
    assert ag.agreement(a, b) == first
    np.testing.assert_array_equal(a, a_before)
    np.testing.assert_array_equal(b, b_before)


# ---------------------------------------------------------------------------
# Degenerate inputs (spec test 5)
# ---------------------------------------------------------------------------


def test_all_plots_in_one_group_in_both_is_not_estimable():
    result = ag.agreement([0, 0, 0, 0], [3, 3, 3, 3])
    assert result.rand == 1.0
    assert math.isnan(result.adjusted_rand)
    assert math.isnan(result.adjusted_rand_max)
    assert math.isnan(ag.adjusted_rand_index([0, 0, 0, 0], [3, 3, 3, 3]))


def test_every_plot_alone_in_both_is_not_estimable():
    assert math.isnan(ag.adjusted_rand_index([0, 1, 2, 3], [3, 2, 1, 0]))
    assert ag.rand_index([0, 1, 2, 3], [3, 2, 1, 0]) == 1.0


@pytest.mark.parametrize(("a", "b"), [([0], [0]), ([], []), ([0, -1], [-1, 0]), ([0, 1], [0, -1])])
def test_fewer_than_two_plots_is_not_estimable(a, b):
    a = np.array(a, dtype=np.int64)
    b = np.array(b, dtype=np.int64)
    assert math.isnan(ag.rand_index(a, b))
    assert math.isnan(ag.adjusted_rand_index(a, b))
    result = ag.agreement(a, b)
    assert math.isnan(result.adjusted_rand_max)
    assert result.counts.total == 0


def test_one_grouping_constant_and_the_other_not_gives_zero():
    assert ag.adjusted_rand_index([0, 0, 0, 0], [0, 0, 1, 1]) == 0.0
    assert ag.adjusted_rand_index([0, 0, 1, 1], [2, 2, 2, 2]) == 0.0
    # Also when the other grouping is all single plots.
    assert ag.adjusted_rand_index([0, 0, 0, 0], [0, 1, 2, 3]) == 0.0
    assert ag.rand_index([0, 0, 0, 0], [0, 1, 2, 3]) == 0.0


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ([0, 1, 2], [0, 1]),  # lengths differ
        ([0, 1.5], [0, 1]),  # not whole numbers
        ([0, -2], [0, 1]),  # below -1
        (["x", "y"], [0, 1]),  # raw labels
        ([[0, 1]], [[0, 1]]),  # not one-dimensional
    ],
)
def test_malformed_input_raises(a, b):
    with pytest.raises(ValueError):
        ag.adjusted_rand_index(a, b)
    with pytest.raises(ValueError):
        ag.pair_counts(a, b)


# ---------------------------------------------------------------------------
# The ceiling (spec test 6)
# ---------------------------------------------------------------------------


def test_ceiling_when_stands_are_nested_in_types():
    field_type = [0, 0, 0, 1, 1, 1]
    stand = [0, 1, 2, 3, 4, 4]  # as fine as stands can be and still hold a pair
    result = ag.agreement(field_type, stand)
    # P = 6 (two types of three plots), Q = 1, T = 1, N = 15.
    counts = result.counts
    assert (counts.total, counts.both, counts.a_only, counts.b_only) == (15, 1, 5, 0)
    # E = 6 / 15 = 0.4, M = 3.5: (1 - 0.4) / (3.5 - 0.4).
    assert result.adjusted_rand == pytest.approx(0.6 / 3.1)
    assert result.adjusted_rand_max == pytest.approx(0.6 / 3.1)
    assert result.adjusted_rand == pytest.approx(adjusted_rand_score(field_type, stand))
    assert result.adjusted_rand_max < 0.25


def test_ceiling_bounds_the_index_and_is_one_for_equal_pair_counts():
    for seed in range(10):
        rng = np.random.default_rng(seed)
        a, b = random_groupings(rng, 60, int(rng.integers(2, 6)), int(rng.integers(2, 25)))
        result = ag.agreement(a, b)
        assert result.adjusted_rand <= result.adjusted_rand_max + 1e-12
        assert result.adjusted_rand_max <= 1 + 1e-12
    # Same group sizes (P == Q) but a different grouping: the ceiling is 1.
    result = ag.agreement([0, 0, 1, 1, 2, 2], [0, 1, 1, 2, 2, 0])
    assert result.adjusted_rand_max == 1.0
    assert result.adjusted_rand < 1.0


# ---------------------------------------------------------------------------
# Stratified (spec test 7)
# ---------------------------------------------------------------------------


def test_one_stratum_equals_the_plain_index():
    rng = np.random.default_rng(21)
    a, b = random_groupings(rng, 100, 4, 6)
    a[rng.random(100) < 0.1] = -1
    result = ag.stratified_agreement(a, b, np.zeros(100, dtype=np.int64))
    plain = ag.agreement(a, b)
    assert result.adjusted_rand == pytest.approx(plain.adjusted_rand, abs=1e-15)
    assert result.rand == pytest.approx(plain.rand, abs=1e-15)
    row = result.per_stratum.iloc[0]
    assert row["adjusted_rand"] == plain.adjusted_rand
    assert row["rand"] == plain.rand
    assert row["n"] == plain.counts.n


def test_type_codes_swapped_between_strata():
    # The district problem in miniature: the same two kinds of forest in both
    # strata, but the type numbers are the other way round in the second.
    a = [0, 0, 1, 1, 0, 0, 1, 1]
    b = [0, 0, 1, 1, 1, 1, 0, 0]
    strata = [0, 0, 0, 0, 1, 1, 1, 1]
    result = ag.stratified_agreement(a, b, strata)
    assert result.adjusted_rand == 1.0
    assert result.rand == 1.0
    assert ag.adjusted_rand_index(a, b) < 1.0
    assert ag.adjusted_rand_index(a, b) == pytest.approx(adjusted_rand_score(a, b))


def test_stratified_by_hand_with_unequal_strata():
    # Stratum 0: the hand-worked case, T=1, P=2, Q=1, N=6: E=1/3, M=3/2.
    # Stratum 1: a=[0,0,0,1,1], b=[0,0,1,1,1]: T=2 (pairs 0-1 and 3-4),
    #            P=3+1=4, Q=1+3=4, N=10: E=1.6, M=4.
    # Stratum 2: a single plot. No pair.
    a = [0, 0, 1, 1, 0, 0, 0, 1, 1, 0]
    b = [0, 0, 1, 2, 0, 0, 1, 1, 1, 0]
    strata = [0, 0, 0, 0, 1, 1, 1, 1, 1, 2]
    result = ag.stratified_agreement(a, b, strata)
    numerator = (1 - 1 / 3) + (2 - 1.6)
    denominator = (1.5 - 1 / 3) + (4 - 1.6)
    assert result.adjusted_rand == pytest.approx(numerator / denominator)
    # Agreeing pairs: 5 of 6, and T + neither = 2 + (10 - 4 - 4 + 2) = 6 of 10.
    assert result.rand == pytest.approx((5 + 6) / (6 + 10))

    table = result.per_stratum
    assert list(table.columns) == ag.PER_STRATUM_COLUMNS
    assert table["stratum"].tolist() == [0, 1, 2]
    assert table["n"].tolist() == [4, 5, 1]
    assert table["total"].tolist() == [6, 10, 0]
    assert table["both"].tolist() == [1, 2, 0]
    assert table["a_only"].tolist() == [1, 2, 0]
    assert table["b_only"].tolist() == [0, 2, 0]
    assert table["neither"].tolist() == [4, 4, 0]
    assert table["n_groups_a"].tolist() == [2, 2, 1]
    assert table["n_groups_b"].tolist() == [3, 2, 1]
    np.testing.assert_allclose(table["rand"].iloc[:2], [5 / 6, 0.6])
    np.testing.assert_allclose(table["adjusted_rand"].iloc[:2], [4 / 7, 0.4 / 2.4])
    np.testing.assert_allclose(table["ari_numerator"], [2 / 3, 0.4, 0.0])
    np.testing.assert_allclose(table["ari_denominator"], [7 / 6, 2.4, 0.0])
    assert math.isnan(table["rand"].iloc[2])
    assert math.isnan(table["adjusted_rand"].iloc[2])
    # The pooled index is the ratio of the summed terms, not a mean of indices.
    assert result.adjusted_rand == pytest.approx(
        table["ari_numerator"].sum() / table["ari_denominator"].sum()
    )
    assert table["stratum"].dtype == np.int64
    assert table["both"].dtype == np.int64
    assert table["rand"].dtype == np.float64


def test_stratified_matches_scikit_learn_stratum_by_stratum():
    rng = np.random.default_rng(22)
    n = 267
    strata = rng.integers(0, 4, size=n)
    a = rng.integers(0, 5, size=n)
    b = rng.integers(0, 5, size=n)
    result = ag.stratified_agreement(a, b, strata)
    numerator = denominator = 0.0
    for s in range(4):
        _, total, both, in_a, in_b = brute_counts(a[strata == s], b[strata == s])
        expected = in_a * in_b / total
        numerator += both - expected
        denominator += (in_a + in_b) / 2 - expected
        row = result.per_stratum.iloc[s]
        assert row["adjusted_rand"] == pytest.approx(
            adjusted_rand_score(a[strata == s], b[strata == s]), abs=1e-12
        )
        assert row["rand"] == pytest.approx(rand_score(a[strata == s], b[strata == s]), abs=1e-12)
    assert result.adjusted_rand == pytest.approx(numerator / denominator, abs=1e-12)


def test_stratum_with_one_field_type_is_kept_and_pulls_the_pooled_index_down():
    # Stratum 0 agrees perfectly. Stratum 1 has one group in `a`: it shows
    # nothing, adds 0 to the numerator and something to the denominator.
    a = [0, 0, 1, 1, 0, 0, 0, 0]
    b = [0, 0, 1, 1, 0, 0, 1, 1]
    strata = [0, 0, 0, 0, 1, 1, 1, 1]
    result = ag.stratified_agreement(a, b, strata)
    table = result.per_stratum
    assert table["adjusted_rand"].tolist() == [1.0, 0.0]
    assert table["ari_numerator"].iloc[1] == 0.0
    assert table["ari_denominator"].iloc[1] > 0.0
    assert 0.0 < result.adjusted_rand < 1.0
    # Stratum 0: T=P=Q=2, N=6: T-E = 4/3 = M-E. Stratum 1: P=6, Q=2, T=2:
    # E=2, M=4: T-E=0, M-E=2.
    assert result.adjusted_rand == pytest.approx((4 / 3) / (4 / 3 + 2))


def test_stratified_leaves_out_missing_strata_and_handles_nothing_usable():
    a = [0, 0, 1, 1, 0, 1]
    b = [0, 0, 1, 1, 1, 0]
    strata = [0, 0, 0, 0, -1, -1]
    result = ag.stratified_agreement(a, b, strata)
    assert result.adjusted_rand == 1.0
    assert result.per_stratum["stratum"].tolist() == [0]

    empty = ag.stratified_agreement([0, 1], [0, 1], [-1, -1])
    assert math.isnan(empty.rand)
    assert math.isnan(empty.adjusted_rand)
    assert list(empty.per_stratum.columns) == ag.PER_STRATUM_COLUMNS
    assert len(empty.per_stratum) == 0

    # A stratum whose plots all lack a label is listed, with no plot used.
    listed = ag.stratified_agreement([0, 0, 1, -1, -1], [0, 0, 1, 0, 1], [0, 0, 0, 1, 1])
    assert listed.per_stratum["stratum"].tolist() == [0, 1]
    assert listed.per_stratum["n"].tolist() == [3, 0]

    with pytest.raises(ValueError):
        ag.stratified_agreement([0, 1], [0, 1], [0])


def test_stratified_does_not_depend_on_plot_order():
    rng = np.random.default_rng(23)
    n = 150
    a, b = random_groupings(rng, n, 4, 5)
    strata = rng.integers(0, 6, size=n)
    order = rng.permutation(n)
    first = ag.stratified_agreement(a, b, strata)
    second = ag.stratified_agreement(a[order], b[order], strata[order])
    assert first.adjusted_rand == second.adjusted_rand
    assert first.rand == second.rand
    pd.testing.assert_frame_equal(first.per_stratum, second.per_stratum)


# ---------------------------------------------------------------------------
# Statistics (spec test 8)
# ---------------------------------------------------------------------------


def make_plots(seed, n=267):
    rng = np.random.default_rng(seed)
    field_type = rng.integers(0, 5, size=n)
    field_type[rng.random(n) < 0.05] = -1
    super_group = rng.integers(0, 4, size=n)
    stand_id = rng.integers(0, 110, size=n)
    stand_id[rng.random(n) < 0.1] = -1
    stand_type = np.where(stand_id >= 0, stand_id % 5, -1)
    return rng, field_type, super_group, stand_id, stand_type


def test_drawing_statistic():
    rng, field_type, _, stand_id, stand_type = make_plots(31)
    stat = ag.drawing_statistic(field_type)
    assert isinstance(stat, Statistic)
    assert stat.name == "ari_drawing"
    assert stat.alternative == "greater"
    assert stat(stand_id) == ag.adjusted_rand_index(field_type, stand_id)
    assert stat(stand_id, stand_type) == stat(stand_id)
    for _ in range(5):
        shuffled = stand_id[rng.permutation(stand_id.shape[0])]
        assert stat(shuffled) == ag.adjusted_rand_index(field_type, shuffled)
    with pytest.raises(ValueError):
        stat(stand_id[:-1])


def test_labelling_statistic():
    rng, field_type, super_group, stand_id, stand_type = make_plots(32)
    stat = ag.labelling_statistic(field_type, super_group)
    assert isinstance(stat, Statistic)
    assert stat.name == "ari_labelling"
    assert stat.alternative == "greater"
    expected = ag.stratified_agreement(field_type, stand_type, super_group).adjusted_rand
    assert stat(stand_id, stand_type) == expected
    for _ in range(5):
        order = rng.permutation(stand_id.shape[0])
        value = stat(stand_id[order], stand_type[order])
        assert value == ag.stratified_agreement(
            field_type, stand_type[order], super_group
        ).adjusted_rand
    with pytest.raises(ValueError, match="stand types"):
        stat(stand_id)
    with pytest.raises(ValueError):
        stat(stand_id, stand_type[:-1])


def test_labelling_statistic_without_super_groups_is_the_plain_index():
    _, field_type, _, stand_id, stand_type = make_plots(33)
    stat = ag.labelling_statistic(field_type)
    assert stat(stand_id, stand_type) == pytest.approx(
        ag.adjusted_rand_index(field_type, stand_type), abs=1e-15
    )
    keep = (field_type >= 0) & (stand_type >= 0)
    assert stat(stand_id, stand_type) == pytest.approx(
        adjusted_rand_score(field_type[keep], stand_type[keep]), abs=1e-12
    )


def test_labelling_statistic_leaves_out_plots_with_no_super_group():
    _, field_type, super_group, stand_id, stand_type = make_plots(34)
    super_group = super_group.copy()
    super_group[:30] = -1
    stat = ag.labelling_statistic(field_type, super_group)
    assert stat(stand_id, stand_type) == ag.stratified_agreement(
        field_type[30:], stand_type[30:], super_group[30:]
    ).adjusted_rand


def test_statistics_are_fixed_when_built_and_leave_their_inputs_alone():
    _, field_type, super_group, stand_id, stand_type = make_plots(35)
    drawing = ag.drawing_statistic(field_type)
    labelling = ag.labelling_statistic(field_type, super_group)
    before = (drawing(stand_id), labelling(stand_id, stand_type))
    sid_copy, typ_copy = stand_id.copy(), stand_type.copy()
    # Changing the caller's arrays afterwards does not change the statistic.
    field_type[:] = 0
    assert (drawing(stand_id), labelling(stand_id, stand_type)) == before
    np.testing.assert_array_equal(stand_id, sid_copy)
    np.testing.assert_array_equal(stand_type, typ_copy)


def test_statistics_are_not_estimable_on_degenerate_labels():
    field_type = np.array([0, 0, 1, 1])
    assert math.isnan(ag.drawing_statistic(field_type)(np.array([-1, -1, -1, 0])))
    assert math.isnan(ag.drawing_statistic(np.zeros(4, dtype=np.int64))(np.zeros(4, dtype=np.int64)))
    labelling = ag.labelling_statistic(field_type, np.array([0, 1, 2, 3]))
    assert math.isnan(labelling(np.arange(4), np.array([0, 0, 1, 1])))


def test_a_planted_grouping_scores_above_shuffled_copies():
    # Determinism under a fixed seed, and the direction of the statistic.
    def run(seed):
        rng = np.random.default_rng(seed)
        stand_id = np.repeat(np.arange(40), 5)
        field_type = (stand_id % 4 + (rng.random(200) < 0.2)) % 4
        stat = ag.drawing_statistic(field_type)
        null = np.array([stat(stand_id[rng.permutation(200)]) for _ in range(50)])
        return stat(stand_id), null

    observed, null = run(7)
    again, null_again = run(7)
    assert observed == again
    np.testing.assert_array_equal(null, null_again)
    assert observed > null.max()
    assert abs(null.mean()) < 0.02

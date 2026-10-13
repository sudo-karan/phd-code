"""Tests of `fmu.evaluation.pairs`: the pair-level comparison.

Expected values are worked out by hand, or recomputed in the test by going
through the pairs one at a time in plain Python, or taken from scipy's
`pdist`. All data is built here. No site data.
"""

from __future__ import annotations

import itertools
import math

import numpy as np
import pandas as pd
import pytest
from scipy.spatial.distance import pdist, squareform

from fmu.evaluation import pairs as pr
from fmu.evaluation._common import Statistic

INF = float("inf")


def line_coords(xs):
    return np.column_stack([np.asarray(xs, dtype=float), np.zeros(len(xs))])


def brute_table(field, coords, edges, stand_id, stand_type, groups, super_group):
    """Go through the pairs one by one. Returns {(group, band): {claim: [d, ...]}}.

    Claims: 0 same stand, 1 same type, 2 different type, 3 type unknown.
    """
    n = len(coords)
    square = squareform(field) if np.ndim(field) == 1 else np.asarray(field)
    strata: dict[tuple[int, int], dict[int, list[float]]] = {}
    for i, j in itertools.combinations(range(n), 2):
        g_i = 0 if groups is None else groups[i]
        g_j = 0 if groups is None else groups[j]
        if g_i != g_j or g_i < 0:
            continue
        geo = math.hypot(coords[i][0] - coords[j][0], coords[i][1] - coords[j][1])
        band = next((b for b in range(len(edges) - 1) if edges[b] <= geo < edges[b + 1]), -1)
        if band < 0 or math.isnan(square[i, j]):
            continue
        cell = strata.setdefault((int(g_i), band), {0: [], 1: [], 2: [], 3: []})
        if stand_id[i] < 0 or stand_id[j] < 0:
            continue
        if stand_id[i] == stand_id[j]:
            claim = 0
        elif (
            stand_type is None
            or stand_type[i] < 0
            or stand_type[j] < 0
            or (
                super_group is not None
                and (super_group[i] != super_group[j] or super_group[i] < 0)
            )
        ):
            claim = 3
        else:
            claim = 1 if stand_type[i] == stand_type[j] else 2
        cell[claim].append(float(square[i, j]))
    return strata


def brute_pooled(strata, contrast, keep=lambda key: True):
    """sum w d / sum w with w = n_lo n_hi / (n_lo + n_hi), written out."""
    lower = [0] if contrast == "stand" else [1]
    upper = [1, 2, 3] if contrast == "stand" else [2]
    top = bottom = 0.0
    used = 0
    for key, cell in strata.items():
        if not keep(key):
            continue
        lo = [d for c in lower for d in cell[c]]
        hi = [d for c in upper for d in cell[c]]
        if lo and hi:
            weight = len(lo) * len(hi) / (len(lo) + len(hi))
            top += weight * (sum(hi) / len(hi) - sum(lo) / len(lo))
            bottom += weight
            used += 1
    return (top / bottom if bottom else float("nan")), used


def random_site(seed, n=90, n_groups=6, missing=True):
    rng = np.random.default_rng(seed)
    groups = rng.integers(0, n_groups, size=n)
    super_group = groups // 3
    coords = rng.uniform(0, 600, size=(n, 2)) + groups[:, None] * 10_000.0
    attributes = rng.normal(size=(n, 4)) * [1.0, 10.0, 100.0, 0.1]
    stand_id = groups * 100 + rng.integers(0, 6, size=n)
    stand_type = (stand_id * 7) % 3
    if missing:
        groups = groups.copy()
        groups[rng.random(n) < 0.05] = -1
        attributes[rng.random(n) < 0.05, 2] = np.nan
        stand_id = np.where(rng.random(n) < 0.08, -1, stand_id)
        stand_type = np.where(stand_id < 0, -1, stand_type)
        untyped = rng.choice(np.unique(stand_id[stand_id >= 0]), size=3, replace=False)
        stand_type = np.where(np.isin(stand_id, untyped), -1, stand_type)
    return rng, attributes, coords, groups, super_group, stand_id, stand_type


# ---------------------------------------------------------------------------
# Distances (spec test 1)
# ---------------------------------------------------------------------------


def test_field_distance_scales_by_the_interquartile_range():
    # Median 2, quartiles 1 and 3: the scale is 2, so distances are |i - j| / 2.
    distance = pr.field_distance([0.0, 1.0, 2.0, 3.0, 4.0])
    expected = [abs(i - j) / 2 for i, j in itertools.combinations(range(5), 2)]
    np.testing.assert_allclose(distance, expected)


def test_field_distance_unscaled_is_pdist():
    values = np.random.default_rng(1).normal(size=(12, 3))
    np.testing.assert_allclose(pr.field_distance(values, scale=False), pdist(values))
    assert pr.field_distance(values, scale=False).shape == (66,)


def test_field_distance_scaled_matches_a_written_out_formula():
    values = np.random.default_rng(2).normal(size=(15, 4)) * [1.0, 5.0, 50.0, 0.2]
    frame = pd.DataFrame(values)
    scaled = (frame - frame.median()) / (frame.quantile(0.75) - frame.quantile(0.25))
    np.testing.assert_allclose(pr.field_distance(values), pdist(scaled.to_numpy()))


def test_field_distance_missing_measurement_gives_nan_in_that_plots_pairs_only():
    values = np.random.default_rng(3).normal(size=(7, 3))
    values[4, 1] = np.nan
    distance = squareform(pr.field_distance(values), checks=False)
    off_diagonal = ~np.eye(7, dtype=bool)
    assert np.isnan(distance[4][off_diagonal[4]]).all()
    assert int(np.isnan(pr.field_distance(values)).sum()) == 6
    others = np.delete(np.arange(7), 4)
    assert not np.isnan(distance[np.ix_(others, others)]).any()
    # The plots that are complete are scaled over all plots, plot 4 included
    # for the measurements it has.
    frame = pd.DataFrame(values)
    scaled = ((frame - frame.median()) / (frame.quantile(0.75) - frame.quantile(0.25))).to_numpy()
    np.testing.assert_allclose(
        distance[np.ix_(others, others)], squareform(pdist(scaled[others]))
    )


def test_field_distance_does_not_depend_on_units():
    values = np.random.default_rng(4).normal(size=(20, 3))
    rescaled = values * [1000.0, 1.0, 1.0] + [5.0, 0.0, -3.0]
    np.testing.assert_allclose(pr.field_distance(rescaled), pr.field_distance(values))
    # Without scaling the units do matter.
    assert not np.allclose(
        pr.field_distance(rescaled, scale=False), pr.field_distance(values, scale=False)
    )


def test_field_distance_degenerate_inputs():
    assert pr.field_distance([[1.0, 2.0]]).shape == (0,)
    # A constant column separates no plots.
    np.testing.assert_allclose(pr.field_distance([3.0, 3.0, 3.0]), [0.0, 0.0, 0.0])
    with pytest.raises(ValueError):
        pr.field_distance([[1.0, np.nan], [2.0, np.nan]])
    with pytest.raises(ValueError):
        pr.field_distance([[1.0, np.inf], [2.0, 0.0]])
    with pytest.raises(ValueError):
        pr.field_distance(np.empty((3, 0)))


def test_geographic_distance():
    coords = [[0.0, 0.0], [3.0, 4.0], [3.0, 0.0]]
    np.testing.assert_allclose(pr.geographic_distance(coords), [5.0, 3.0, 4.0])
    xy = np.random.default_rng(5).uniform(0, 1000, size=(9, 2))
    np.testing.assert_allclose(pr.geographic_distance(xy), pdist(xy))
    assert pr.geographic_distance([[1.0, 2.0]]).shape == (0,)
    with pytest.raises(ValueError):
        pr.geographic_distance([[0.0, np.nan], [1.0, 1.0]])
    with pytest.raises(ValueError):
        pr.geographic_distance([0.0, 1.0, 2.0])


# ---------------------------------------------------------------------------
# Hand-worked comparisons (spec tests 2 to 6)
# ---------------------------------------------------------------------------


def test_four_plots_one_stratum():
    result = pr.pair_comparison(
        [0.0, 0.0, 10.0, 10.0],
        line_coords([0, 1, 2, 3]),
        [0, 0, 1, 1],
        None,
        [0.0, INF],
        scale=False,
    )
    assert len(result.strata) == 1
    row = result.strata.iloc[0]
    assert list(result.strata.columns) == pr.STRATA_COLUMNS
    assert (row["group"], row["band"], row["band_lo"], row["band_hi"]) == (0, 0, 0.0, INF)
    assert (row["n_pairs"], row["n_same_stand"], row["n_type_unknown"]) == (6, 2, 4)
    assert (row["n_same_type"], row["n_diff_type"]) == (0, 0)
    assert row["mean_same_stand"] == 0.0
    assert row["mean_type_unknown"] == 10.0
    assert math.isnan(row["mean_same_type"])
    assert row["effect_stand"] == pytest.approx(10.0)
    assert row["weight_stand"] == pytest.approx(2 * 4 / 6)
    assert math.isnan(row["effect_type"])
    assert row["weight_type"] == 0.0
    assert result.pooled["stand"] == pytest.approx(10.0)
    assert result.crude["stand"] == pytest.approx(10.0)
    assert math.isnan(result.pooled["type"])
    assert math.isnan(result.crude["type"])
    assert result.n_pairs_used == 6
    assert result.n_strata_used == {"stand": 1, "type": 0}


def test_confounding_by_distance_is_removed_by_the_bands():
    # Two near pairs (10 m) with field distance 1, four far pairs with 3. The
    # only same-stand pair is a near pair. Pooled over everything the map
    # looks good; at equal distance it shows nothing.
    coords = line_coords([0, 10, 100, 110])
    geo = pdist(coords)
    field = np.where(geo < 50, 1.0, 3.0)
    comparison = pr.PairComparison(field, coords, [0.0, 50.0, INF])
    result = comparison.table([0, 0, 1, 2])
    near, far = result.strata.iloc[0], result.strata.iloc[1]
    assert (near["band"], near["n_pairs"], near["n_same_stand"]) == (0, 2, 1)
    assert near["effect_stand"] == 0.0
    assert near["weight_stand"] == pytest.approx(0.5)
    assert (far["band"], far["n_pairs"], far["n_same_stand"]) == (1, 4, 0)
    assert math.isnan(far["effect_stand"])
    assert far["weight_stand"] == 0.0
    assert result.pooled["stand"] == 0.0
    assert result.crude["stand"] == pytest.approx(2.6 - 1.0)
    assert result.n_strata_used["stand"] == 1
    assert result.by_band["effect_stand"].iloc[0] == 0.0
    assert math.isnan(result.by_band["effect_stand"].iloc[1])
    assert result.by_band["n_upper_stand"].tolist() == [1, 4]
    assert result.by_band["n_lower_stand"].tolist() == [1, 0]
    assert result.by_band["band_lo"].tolist() == [0.0, 50.0]
    assert result.by_band["band_hi"].tolist() == [50.0, INF]


def test_two_strata_with_different_weights():
    # Group 0, plots 0..3, stands [0,0,0,1]: 3 same-stand pairs, 3 others.
    # Group 1, plots 4..6, stands [2,2,3]: 1 same-stand pair, 2 others.
    field = np.zeros((7, 7))

    def put(i, j, d):
        field[i, j] = field[j, i] = d

    put(0, 1, 1.0), put(0, 2, 2.0), put(1, 2, 3.0)  # same stand: mean 2
    put(0, 3, 4.0), put(1, 3, 6.0), put(2, 3, 8.0)  # different: mean 6
    put(4, 5, 5.0)  # same stand: mean 5
    put(4, 6, 6.0), put(5, 6, 10.0)  # different: mean 8
    for i in range(4):  # pairs across the groups: never used
        for j in range(4, 7):
            put(i, j, 1000.0)
    groups = [0, 0, 0, 0, 1, 1, 1]
    comparison = pr.PairComparison(field, line_coords(range(7)), [0.0, INF], groups=groups)
    result = comparison.table([0, 0, 0, 1, 2, 2, 3])
    assert result.strata["effect_stand"].tolist() == pytest.approx([4.0, 3.0])
    w0, w1 = 3 * 3 / 6, 1 * 2 / 3
    assert result.strata["weight_stand"].tolist() == pytest.approx([w0, w1])
    expected = (w0 * 4.0 + w1 * 3.0) / (w0 + w1)
    assert result.pooled["stand"] == pytest.approx(expected)
    assert comparison.effect([0, 0, 0, 1, 2, 2, 3]) == pytest.approx(expected)
    # Crude: all nine pairs as one stratum.
    assert result.crude["stand"] == pytest.approx((4 + 6 + 8 + 6 + 10) / 5 - (1 + 2 + 3 + 5) / 4)
    assert result.n_pairs_used == 9
    assert result.by_group["group"].tolist() == [0, 1]
    assert result.by_group["effect_stand"].tolist() == pytest.approx([4.0, 3.0])
    assert result.by_group["weight_stand"].tolist() == pytest.approx([w0, w1])
    assert result.by_group["n_strata_stand"].tolist() == [1, 1]
    assert result.by_band["effect_stand"].tolist() == pytest.approx([expected])
    assert result.by_band["n_strata_stand"].tolist() == [2]
    assert result.by_band["n_lower_stand"].tolist() == [4]
    assert result.by_band["n_upper_stand"].tolist() == [5]


def test_type_contrast_and_types_across_super_groups():
    kwargs = {
        "attributes": [0.0, 0.0, 5.0, 5.0],
        "coords": line_coords([0, 1, 2, 3]),
        "stand_id": [0, 1, 2, 3],
        "stand_type": [0, 0, 1, 1],
        "band_edges": [0.0, INF],
        "scale": False,
    }
    result = pr.pair_comparison(**kwargs)
    row = result.strata.iloc[0]
    assert (row["n_same_stand"], row["n_same_type"], row["n_diff_type"]) == (0, 2, 4)
    assert row["effect_type"] == pytest.approx(5.0)
    assert row["weight_type"] == pytest.approx(2 * 4 / 6)
    assert result.pooled["type"] == pytest.approx(5.0)
    assert math.isnan(result.pooled["stand"])  # no same-stand pair

    # A type number means a different forest in each district: the four
    # cross-district pairs cannot be compared, so nothing is left to contrast.
    split = pr.pair_comparison(**kwargs, super_group=[0, 0, 1, 1])
    row = split.strata.iloc[0]
    assert (row["n_same_type"], row["n_diff_type"], row["n_type_unknown"]) == (2, 0, 4)
    assert math.isnan(row["effect_type"])
    assert math.isnan(split.pooled["type"])
    assert split.n_strata_used["type"] == 0


def test_same_stand_pairs_are_not_in_the_type_contrast():
    # Stand 0 holds plots 0 and 1 (field distance 100 between them). If that
    # pair counted as "same type" the type effect would be far below zero.
    field = squareform([100.0, 1.0, 1.0, 9.0, 9.0, 1.0, 1.0, 9.0, 9.0, 1.0, 9.0, 9.0, 9.0, 9.0, 1.0])
    comparison = pr.PairComparison(field, line_coords(range(6)), [0.0, INF])
    stand_id = [0, 0, 1, 2, 3, 4]
    stand_type = [0, 0, 0, 0, 1, 1]
    # Same type, different stand: (0,2) (0,3) (1,2) (1,3) (2,3) (4,5), all 1.
    # Different type: the eight pairs across, all 9.
    assert comparison.effect(stand_id, stand_type, "type") == pytest.approx(8.0)
    row = comparison.table(stand_id, stand_type).strata.iloc[0]
    assert (row["n_same_stand"], row["n_same_type"], row["n_diff_type"]) == (1, 6, 8)
    assert row["mean_same_stand"] == 100.0
    # The stand contrast: 14 other pairs (6 at 1, 8 at 9) against the one at 100.
    assert row["effect_stand"] == pytest.approx((6 * 1 + 8 * 9) / 14 - 100.0)


def test_pairs_across_groups_are_never_used():
    rng = np.random.default_rng(6)
    comparison = pr.PairComparison(
        pdist(rng.normal(size=(6, 2))),
        rng.uniform(0, 100, size=(6, 2)),
        [0.0, INF],
        groups=[0, 0, 0, 1, 1, 1],
    )
    assert comparison.n_candidate_pairs == 6
    result = comparison.table([0, 0, 1, 2, 2, 3])
    assert result.n_pairs_used == 6
    assert result.strata["group"].tolist() == [0, 1]
    assert result.strata["n_pairs"].tolist() == [3, 3]


def test_which_pairs_are_left_out():
    # Six plots on a line 10 m apart, one group, one band [15, 35): pairs 20 m
    # and 30 m apart are in it: 4 + 3 = 7 pairs.
    coords = line_coords(np.arange(6) * 10.0)
    field = squareform(pdist(np.arange(6.0)[:, None]))
    base = pr.PairComparison(field, coords, [15.0, 35.0])
    assert base.n_candidate_pairs == 7
    assert base.table(np.arange(6)).n_pairs_used == 7
    # A distance exactly on an edge belongs to the band that starts there.
    assert pr.PairComparison(field, coords, [20.0, 30.0]).n_candidate_pairs == 4
    # A pair without a field distance is left out.
    holed = field.copy()
    holed[0, 2] = holed[2, 0] = np.nan
    assert pr.PairComparison(holed, coords, [15.0, 35.0]).n_candidate_pairs == 6
    # A plot in no group is in no pair: plot 0 was in (0,2) and (0,3).
    grouped = pr.PairComparison(field, coords, [15.0, 35.0], groups=[-1, 0, 0, 0, 0, 0])
    assert grouped.n_candidate_pairs == 5
    # A plot in no stand: the map makes no claim. Plot 5 was in (2,5), (3,5).
    result = base.table([0, 1, 2, 3, 4, -1])
    assert result.n_pairs_used == 5
    assert result.strata["n_pairs"].tolist() == [5]


def test_empty_bands_and_groups_are_listed_in_the_poolings():
    coords = line_coords([0, 10, 20, 5000])
    comparison = pr.PairComparison(
        pdist(coords), coords, [0.0, 15.0, 100.0, 1000.0], groups=[0, 0, 0, 7]
    )
    result = comparison.table([0, 0, 1, 2])
    assert result.by_band["band"].tolist() == [0, 1, 2]
    assert result.by_band["n_strata_stand"].tolist() == [1, 0, 0]
    assert result.by_band["n_upper_stand"].tolist() == [1, 1, 0]
    assert result.by_group["group"].tolist() == [0, 7]
    assert math.isnan(result.by_group["effect_stand"].iloc[1])
    assert result.by_group["weight_stand"].iloc[1] == 0.0
    assert result.strata[["group", "band"]].to_numpy().tolist() == [[0, 0], [0, 1]]
    assert list(result.by_band.columns) == ["band", "band_lo", "band_hi", *pr._POOLED_COLUMNS]
    assert list(result.by_group.columns) == ["group", *pr._POOLED_COLUMNS]
    assert pr._POOLED_COLUMNS == [
        "n_lower_stand", "n_upper_stand", "effect_stand", "weight_stand", "n_strata_stand",
        "n_lower_type", "n_upper_type", "effect_type", "weight_type", "n_strata_type",
    ]  # fmt: skip


# ---------------------------------------------------------------------------
# Against a pair-by-pair recomputation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seed", range(4))
def test_matches_a_pair_by_pair_recomputation(seed):
    _, attributes, coords, groups, super_group, stand_id, stand_type = random_site(seed)
    edges = [0.0, 150.0, 300.0, 500.0]
    field = pr.field_distance(attributes)
    comparison = pr.PairComparison(field, coords, edges, groups=groups, super_group=super_group)
    result = comparison.table(stand_id, stand_type)
    expected = brute_table(field, coords, edges, stand_id, stand_type, groups, super_group)

    table = result.strata
    assert [tuple(k) for k in table[["group", "band"]].to_numpy().tolist()] == sorted(expected)
    names = ["same_stand", "same_type", "diff_type", "type_unknown"]
    for _, row in table.iterrows():
        cell = expected[(int(row["group"]), int(row["band"]))]
        for claim, name in enumerate(names):
            assert row[f"n_{name}"] == len(cell[claim])
            if cell[claim]:
                assert row[f"mean_{name}"] == pytest.approx(np.mean(cell[claim]))
            else:
                assert math.isnan(row[f"mean_{name}"])
        assert row["n_pairs"] == sum(len(v) for v in cell.values())
        assert row["band_lo"] == edges[int(row["band"])]
        assert row["band_hi"] == edges[int(row["band"]) + 1]
    assert result.n_pairs_used == sum(len(v) for cell in expected.values() for v in cell.values())

    for contrast in ("stand", "type"):
        pooled, used = brute_pooled(expected, contrast)
        assert result.pooled[contrast] == pytest.approx(pooled, abs=1e-12)
        assert result.n_strata_used[contrast] == used
        assert used > 0
        for band, value in enumerate(result.by_band[f"effect_{contrast}"]):
            want, n_strata = brute_pooled(expected, contrast, lambda key, b=band: key[1] == b)
            assert value == pytest.approx(want, abs=1e-12, nan_ok=True)
            assert result.by_band[f"n_strata_{contrast}"].iloc[band] == n_strata
        for position, group in enumerate(result.by_group["group"]):
            want, _ = brute_pooled(expected, contrast, lambda key, g=group: key[0] == g)
            got = result.by_group[f"effect_{contrast}"].iloc[position]
            assert got == pytest.approx(want, abs=1e-12, nan_ok=True)
        # Crude: every used pair in one stratum.
        merged = {(0, 0): {c: [d for cell in expected.values() for d in cell[c]] for c in range(4)}}
        assert result.crude[contrast] == pytest.approx(brute_pooled(merged, contrast)[0])

    # The convenience function gives the same table.
    direct = pr.pair_comparison(
        attributes, coords, stand_id, stand_type, edges, groups=groups, super_group=super_group
    )
    pd.testing.assert_frame_equal(direct.strata, result.strata)
    pd.testing.assert_frame_equal(direct.by_band, result.by_band)
    pd.testing.assert_frame_equal(direct.by_group, result.by_group)
    assert direct.pooled == pytest.approx(result.pooled, nan_ok=True)


def test_no_groups_means_one_group_and_a_square_matrix_is_accepted():
    _, attributes, coords, _, _, stand_id, stand_type = random_site(9, n=40, missing=False)
    coords = coords % 1000.0
    edges = [0.0, 200.0, 400.0, INF]
    field = pr.field_distance(attributes)
    one = pr.PairComparison(field, coords, edges)
    same = pr.PairComparison(squareform(field), coords, edges, groups=np.zeros(40, dtype=int))
    result = one.table(stand_id, stand_type)
    pd.testing.assert_frame_equal(result.strata, same.table(stand_id, stand_type).strata)
    assert set(result.strata["group"]) == {0}
    assert result.by_group["group"].tolist() == [0]
    expected = brute_table(field, coords, edges, stand_id, stand_type, None, None)
    assert result.pooled["stand"] == pytest.approx(brute_pooled(expected, "stand")[0])
    assert result.pooled["type"] == pytest.approx(brute_pooled(expected, "type")[0])


# ---------------------------------------------------------------------------
# effect() and statistic() (spec test 7)
# ---------------------------------------------------------------------------


def test_statistic_effect_and_table_agree_also_after_relabelling():
    rng, attributes, coords, groups, super_group, stand_id, stand_type = random_site(20)
    comparison = pr.PairComparison(
        pr.field_distance(attributes), coords, [0.0, 150.0, 300.0, 500.0],
        groups=groups, super_group=super_group,
    )  # fmt: skip
    stand = comparison.statistic("stand")
    typ = comparison.statistic("type")
    assert isinstance(stand, Statistic)
    assert (stand.name, stand.alternative) == ("pair_stand", "greater")
    assert (typ.name, typ.alternative) == ("pair_type", "greater")
    n = stand_id.shape[0]
    for draw in range(6):
        order = np.arange(n) if draw == 0 else rng.permutation(n)
        sid, st = stand_id[order], stand_type[order]
        table = comparison.table(sid, st)
        assert stand(sid, st) == comparison.effect(sid, st, "stand") == table.pooled["stand"]
        assert typ(sid, st) == comparison.effect(sid, st, "type") == table.pooled["type"]
        assert not math.isnan(stand(sid, st))
        assert not math.isnan(typ(sid, st))
    # The default contrast is the drawing, and types do not change it.
    assert comparison.effect(stand_id) == comparison.effect(stand_id, stand_type, "stand")


def test_type_effect_without_types_is_not_estimable():
    _, attributes, coords, groups, _, stand_id, _ = random_site(21)
    comparison = pr.PairComparison(
        pr.field_distance(attributes), coords, [0.0, 300.0, 600.0], groups=groups
    )
    assert math.isnan(comparison.effect(stand_id, None, "type"))
    assert math.isnan(comparison.statistic("type")(stand_id))
    assert math.isnan(comparison.table(stand_id).pooled["type"])
    assert not math.isnan(comparison.effect(stand_id, None, "stand"))


def test_effect_is_not_estimable_without_a_contrast():
    coords = line_coords([0, 1, 2, 3])
    comparison = pr.PairComparison(pdist(coords), coords, [0.0, INF])
    assert math.isnan(comparison.effect([0, 1, 2, 3]))  # no same-stand pair
    assert math.isnan(comparison.effect([0, 0, 0, 0]))  # no different-stand pair
    assert math.isnan(comparison.effect([-1, -1, -1, 0]))  # no claim at all
    empty = comparison.table([-1, -1, -1, 0])
    assert empty.n_pairs_used == 0
    assert empty.strata["n_pairs"].tolist() == [0]
    assert math.isnan(empty.crude["stand"])
    # No pair falls in any band: no stratum at all.
    nothing = pr.PairComparison(pdist(coords), coords, [100.0, 200.0]).table([0, 0, 1, 1])
    assert len(nothing.strata) == 0
    assert list(nothing.strata.columns) == pr.STRATA_COLUMNS
    assert math.isnan(nothing.pooled["stand"])
    assert nothing.n_strata_used == {"stand": 0, "type": 0}
    assert nothing.by_band["n_strata_stand"].tolist() == [0]


def test_a_single_plot_makes_no_pair():
    comparison = pr.PairComparison(np.empty(0), [[0.0, 0.0]], [0.0, INF])
    assert comparison.n_candidate_pairs == 0
    assert math.isnan(comparison.effect([0]))
    assert comparison.table([0]).n_pairs_used == 0


def test_relabelling_is_deterministic_and_inputs_are_left_alone():
    def run(seed):
        rng, attributes, coords, groups, super_group, stand_id, stand_type = random_site(22)
        field = pr.field_distance(attributes)
        field_before = field.copy()
        comparison = pr.PairComparison(
            field, coords, [0.0, 200.0, 500.0], groups=groups, super_group=super_group
        )
        stat = comparison.statistic("stand")
        draws = np.random.default_rng(seed)
        sid_before, typ_before = stand_id.copy(), stand_type.copy()
        values = []
        for _ in range(20):
            order = draws.permutation(stand_id.shape[0])
            values.append(stat(stand_id[order], stand_type[order]))
        np.testing.assert_array_equal(stand_id, sid_before)
        np.testing.assert_array_equal(stand_type, typ_before)
        np.testing.assert_array_equal(field, field_before)
        return np.array(values), stat(stand_id, stand_type)

    first, observed = run(5)
    second, observed_again = run(5)
    np.testing.assert_array_equal(first, second)
    assert observed == observed_again
    assert not np.array_equal(first, run(6)[0])


def test_a_planted_map_gives_a_positive_effect_and_a_shuffled_one_does_not():
    rng = np.random.default_rng(30)
    n_groups, per_group = 8, 24
    groups = np.repeat(np.arange(n_groups), per_group)
    n = groups.shape[0]
    coords = rng.uniform(0, 400, size=(n, 2)) + groups[:, None] * 10_000.0
    stand_id = groups * 10 + (coords[:, 0] % 10_000.0 // 100).astype(int)  # strips 100 m wide
    stand_type = stand_id % 3
    signal = rng.normal(size=(stand_id.max() + 1, 3))[stand_id]
    attributes = 2.0 * signal + rng.normal(size=(n, 3)) + rng.normal(size=(n_groups, 3))[groups]
    comparison = pr.PairComparison(
        pr.field_distance(attributes), coords, [0.0, 100.0, 200.0, 400.0, INF], groups=groups
    )
    observed = comparison.effect(stand_id, stand_type, "stand")
    null = []
    for _ in range(30):
        order = rng.permutation(n)
        null.append(comparison.effect(stand_id[order], stand_type[order], "stand"))
    assert observed > max(null)
    assert observed > 0.5
    assert abs(float(np.mean(null))) < 0.2


# ---------------------------------------------------------------------------
# Malformed input
# ---------------------------------------------------------------------------


def test_malformed_input_raises():
    coords = line_coords([0, 1, 2, 3])
    field = pdist(coords)
    with pytest.raises(TypeError):
        pr.PairComparison(field, coords)  # the bands have no default
    with pytest.raises(ValueError):
        pr.PairComparison(field, coords, [0.0])
    with pytest.raises(ValueError):
        pr.PairComparison(field, coords, [100.0, 50.0])
    with pytest.raises(ValueError):
        pr.PairComparison(field[:-1], coords, [0.0, INF])
    with pytest.raises(ValueError):
        pr.PairComparison(-field, coords, [0.0, INF])
    with pytest.raises(ValueError):
        pr.PairComparison(field, coords, [0.0, INF], groups=[0, 0, 1])
    with pytest.raises(ValueError, match="super-group"):
        pr.PairComparison(field, coords, [0.0, INF], groups=[0, 0, 1, 1], super_group=[0, 1, 2, 2])
    comparison = pr.PairComparison(field, coords, [0.0, INF])
    with pytest.raises(ValueError):
        comparison.effect([0, 0, 1])
    with pytest.raises(ValueError):
        comparison.effect([0, 0, 1, 1], None, "village")
    with pytest.raises(ValueError):
        comparison.statistic("village")
    with pytest.raises(ValueError):
        comparison.table([0, 0, 1, 1.5])
    with pytest.raises(ValueError, match="more than one type"):
        comparison.table([0, 0, 1, 1], [0, 1, 2, 2])

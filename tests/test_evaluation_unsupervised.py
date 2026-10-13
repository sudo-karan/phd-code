"""Tests of `fmu.evaluation.unsupervised` with known answers.

Every raster is built here. No real site is read.
"""

from __future__ import annotations

import math
import os
import time

import numpy as np
import pytest
from scipy import stats

from fmu.evaluation.unsupervised import (
    EXPLAINED_VARIANCE_COLUMNS,
    GLOBAL_SCORE_COLUMNS,
    MORANS_I_COLUMNS,
    WEIGHTED_VARIANCE_COLUMNS,
    explained_variance,
    global_score,
    morans_i,
    segment_adjacency,
    segment_morans_i,
    weighted_variance,
)


def _blocks(height: int, width: int, size: int) -> np.ndarray:
    """A raster cut into square segments of `size` pixels, numbered row by row."""
    rows = np.arange(height) // size
    cols = np.arange(width) // size
    return rows[:, None] * (int(cols.max()) + 1) + cols[None, :]


def _dense_morans_i(y: np.ndarray, pairs: np.ndarray) -> float:
    """Moran's I from the textbook formula with a full weight matrix."""
    n = len(y)
    w = np.zeros((n, n))
    for a, b in pairs:
        w[a, b] = w[b, a] = 1.0
    dev = y - y.mean()
    return float(n / w.sum() * (dev @ w @ dev) / (dev @ dev))


# ---------------------------------------------------------------------------
# Explained variance and area-weighted variance
# ---------------------------------------------------------------------------


def test_explained_variance_hand_worked():
    labels = np.array([0, 0, 1, 1])
    values = np.array([1.0, 3.0, 5.0, 7.0])
    # mean 4: SS_total = 9 + 1 + 1 + 9; segment means 2 and 6: SS_within = 4 * 1.
    ev = explained_variance(labels, values)
    assert list(ev.columns) == EXPLAINED_VARIANCE_COLUMNS
    row = ev.iloc[0]
    assert row["band"] == "band_0"
    assert row["ss_total"] == pytest.approx(20.0)
    assert row["ss_within"] == pytest.approx(4.0)
    assert row["r2"] == pytest.approx(0.8)
    assert row["n_pixels"] == 4
    assert row["n_segments"] == 2
    wv = weighted_variance(labels, values)
    assert list(wv.columns) == WEIGHTED_VARIANCE_COLUMNS
    assert wv.iloc[0]["weighted_variance"] == pytest.approx(1.0)
    assert wv.iloc[0]["n_pixels"] == 4
    assert wv.iloc[0]["n_segments"] == 2


def test_explained_variance_matches_one_way_anova():
    rng = np.random.default_rng(0)
    for n, k in ((50, 3), (400, 12), (2000, 40)):
        labels = rng.integers(0, k, n)
        values = rng.normal(size=n) + 0.5 * labels
        groups = [values[labels == g] for g in np.unique(labels)]
        f = stats.f_oneway(*groups).statistic
        dfb, dfw = len(groups) - 1, n - len(groups)
        row = explained_variance(labels, values).iloc[0]
        assert row["r2"] == pytest.approx(f * dfb / (f * dfb + dfw), rel=1e-10)
        assert row["n_segments"] == len(groups)
        # the textbook sums, written out
        ss_total = ((values - values.mean()) ** 2).sum()
        ss_within = sum(((g - g.mean()) ** 2).sum() for g in groups)
        assert row["ss_total"] == pytest.approx(ss_total, rel=1e-12)
        assert row["ss_within"] == pytest.approx(ss_within, rel=1e-12)


def test_weighted_variance_is_the_area_weighted_mean_of_segment_variances():
    rng = np.random.default_rng(1)
    labels = rng.integers(0, 9, (30, 40))
    values = rng.normal(size=(2, 30, 40)) * np.array([1.0, 50.0])[:, None, None]
    wv = weighted_variance(labels, values, band_names=["height", "cover"])
    ev = explained_variance(labels, values, band_names=["height", "cover"])
    assert wv["band"].tolist() == ["height", "cover"]
    for b in range(2):
        areas = np.array([(labels == k).sum() for k in range(9)])
        variances = np.array([values[b][labels == k].var(ddof=0) for k in range(9)])
        expected = (areas * variances).sum() / areas.sum()
        assert wv.iloc[b]["weighted_variance"] == pytest.approx(expected, rel=1e-12)
        # the same information as R2: r2 = 1 - wvar / (SS_total / n)
        total_var = values[b].var(ddof=0)
        assert ev.iloc[b]["r2"] == pytest.approx(1 - expected / total_var, rel=1e-10)


def test_every_segment_constant_gives_one():
    labels = _blocks(12, 12, 3)
    values = (labels * 1.7 + 0.3).astype(float)  # one value per segment
    row = explained_variance(labels, values).iloc[0]
    assert row["r2"] == pytest.approx(1.0, abs=1e-12)
    assert row["ss_within"] == pytest.approx(0.0, abs=1e-20)
    assert row["n_segments"] == 16
    assert weighted_variance(labels, values).iloc[0]["weighted_variance"] == pytest.approx(0.0, abs=1e-20)


def test_values_unrelated_to_the_labels_give_about_zero():
    rng = np.random.default_rng(2)
    labels = _blocks(200, 200, 20)  # 100 segments of 400 pixels
    values = rng.normal(size=(200, 200))
    row = explained_variance(labels, values).iloc[0]
    # Under no relation R2 is about (k - 1) / (n - 1) = 99 / 39999 = 0.0025.
    assert 0.0 <= row["r2"] < 0.006
    assert row["n_segments"] == 100
    # ... and it rises with the number of segments on the very same values.
    finer = explained_variance(_blocks(200, 200, 2), values).iloc[0]
    assert finer["n_segments"] == 10_000
    assert 0.2 < finer["r2"] < 0.3  # about 9999 / 39999 = 0.25
    assert weighted_variance(labels, values).iloc[0]["weighted_variance"] == pytest.approx(
        values.var(), rel=0.01
    )


def test_one_segment_one_pixel_segments_and_constant_values():
    rng = np.random.default_rng(3)
    values = rng.normal(size=60)
    one = explained_variance(np.zeros(60, dtype=int), values).iloc[0]
    assert one["r2"] == pytest.approx(0.0, abs=1e-12)
    assert one["n_segments"] == 1
    each = explained_variance(np.arange(60), values).iloc[0]
    assert each["r2"] == pytest.approx(1.0, abs=1e-12)
    assert each["n_segments"] == 60
    assert weighted_variance(np.arange(60), values).iloc[0]["weighted_variance"] == pytest.approx(0.0)
    labels = np.repeat(np.arange(6), 10)
    flat = explained_variance(labels, np.full(60, 0.1)).iloc[0]
    assert math.isnan(flat["r2"])
    assert flat["ss_total"] == 0.0
    assert flat["ss_within"] == 0.0
    assert flat["n_pixels"] == 60
    assert weighted_variance(labels, np.full(60, 0.1)).iloc[0]["weighted_variance"] == 0.0


def test_no_usable_pixel():
    labels = np.array([-1, -1, 0, 0])
    values = np.array([1.0, 2.0, np.nan, np.nan])
    row = explained_variance(labels, values).iloc[0]
    assert math.isnan(row["r2"])
    assert row["n_pixels"] == 0
    assert row["n_segments"] == 0
    assert math.isnan(weighted_variance(labels, values).iloc[0]["weighted_variance"])


def test_masking_is_per_band():
    rng = np.random.default_rng(4)
    labels = rng.integers(0, 5, (20, 25))
    labels[0, :] = -1  # no segment
    labels[1, :3] = -7  # any negative value means no segment
    valid = np.ones((20, 25), dtype=bool)
    valid[:, 0] = False
    values = rng.normal(size=(2, 20, 25)) + labels.clip(0)
    values[0, 5:9, 5:9] = np.nan  # band 0 only
    ev = explained_variance(labels, values, valid=valid)

    for b in range(2):
        use = (labels >= 0) & valid & ~np.isnan(values[b])
        lab, val = labels[use], values[b][use]
        ss_total = ((val - val.mean()) ** 2).sum()
        ss_within = sum(((val[lab == k] - val[lab == k].mean()) ** 2).sum() for k in np.unique(lab))
        assert ev.iloc[b]["n_pixels"] == use.sum()
        assert ev.iloc[b]["ss_total"] == pytest.approx(ss_total, rel=1e-12)
        assert ev.iloc[b]["ss_within"] == pytest.approx(ss_within, rel=1e-12)
        assert ev.iloc[b]["r2"] == pytest.approx(1 - ss_within / ss_total, rel=1e-10)
    # Band 1 kept the 16 pixels that band 0 lost.
    assert ev.iloc[1]["n_pixels"] - ev.iloc[0]["n_pixels"] == 16
    # Band 1 alone gives the same row as band 1 in the stack.
    alone = explained_variance(labels, values[1], valid=valid).iloc[0]
    assert alone["r2"] == ev.iloc[1]["r2"]


def test_label_values_do_not_matter_and_large_offsets_are_safe():
    rng = np.random.default_rng(5)
    labels = rng.integers(0, 7, 500)
    values = rng.normal(size=500) + labels
    base = explained_variance(labels, values).iloc[0]
    # Ids with gaps and very large ids (as a segmenter gives) are the same grouping.
    renamed = explained_variance(labels * 10_000_000_019 + 5, values).iloc[0]
    assert renamed["r2"] == pytest.approx(base["r2"], rel=1e-12)
    assert renamed["n_segments"] == base["n_segments"]
    # Whole-number floats are accepted as labels.
    assert explained_variance(labels.astype(float), values).iloc[0]["r2"] == base["r2"]
    # Adding a constant or changing units does not change R2.
    shifted = explained_variance(labels, values * 3.0 + 1e9).iloc[0]
    assert shifted["r2"] == pytest.approx(base["r2"], rel=1e-6)
    # A plot table: rows are plots, columns are measurements; pass table.T.
    table = np.column_stack([values, values**2])
    both = explained_variance(labels, table.T, band_names=["a", "b"])
    assert both["band"].tolist() == ["a", "b"]
    assert both.iloc[0]["r2"] == base["r2"]
    # Same input, same output, to the last bit.
    assert explained_variance(labels, table.T).equals(explained_variance(labels, table.T))


def test_malformed_inputs_raise():
    labels = np.zeros((4, 5), dtype=int)
    values = np.zeros((4, 5))
    with pytest.raises(ValueError, match="shape"):
        explained_variance(labels, np.zeros((5, 4)))
    with pytest.raises(ValueError, match="shape"):
        explained_variance(labels, np.zeros((2, 5, 4)))
    with pytest.raises(ValueError, match="infinite"):
        explained_variance(labels, np.full((4, 5), np.inf))
    with pytest.raises(ValueError, match="whole numbers"):
        explained_variance(labels + 0.5, values)
    with pytest.raises(ValueError, match="whole numbers"):
        explained_variance(np.full((4, 5), np.nan), values)
    with pytest.raises(ValueError, match="integer"):
        explained_variance(np.full((4, 5), "a"), values)
    with pytest.raises(ValueError, match="valid"):
        explained_variance(labels, values, valid=np.ones((4, 5)))
    with pytest.raises(ValueError, match="valid"):
        explained_variance(labels, values, valid=np.ones((5, 4), dtype=bool))
    with pytest.raises(ValueError, match="band names"):
        weighted_variance(labels, values, band_names=["a", "b"])
    with pytest.raises(ValueError, match="distinct"):
        weighted_variance(labels, np.zeros((2, 4, 5)), band_names=["a", "a"])


# ---------------------------------------------------------------------------
# Adjacency
# ---------------------------------------------------------------------------


def test_adjacency_hand_worked():
    adj = segment_adjacency(np.array([[0, 0, 1], [2, 2, 1]]))
    assert adj.dtype == np.int64
    assert adj.tolist() == [[0, 1], [0, 2], [1, 2]]
    quad = np.array([[0, 1], [2, 3]])
    assert segment_adjacency(quad).tolist() == [[0, 1], [0, 2], [1, 3], [2, 3]]
    assert segment_adjacency(quad, connectivity=8).tolist() == [
        [0, 1],
        [0, 2],
        [0, 3],
        [1, 2],
        [1, 3],
        [2, 3],
    ]


def test_adjacency_ignores_unlabelled_pixels_and_keeps_label_values():
    lab = np.array([[5, -1, 9], [5, -1, 9], [5, 70, 70]])
    # 5 and 9 are separated by pixels with no segment; both touch 70.
    assert segment_adjacency(lab).tolist() == [[5, 70], [9, 70]]
    assert segment_adjacency(lab, connectivity=8).tolist() == [[5, 70], [9, 70]]
    huge = np.array([[3, 2**40], [3, 2**40 + 1]])
    assert segment_adjacency(huge).tolist() == [[3, 2**40], [3, 2**40 + 1], [2**40, 2**40 + 1]]


def test_adjacency_degenerate_and_malformed():
    assert segment_adjacency(np.zeros((3, 3), dtype=int)).shape == (0, 2)
    assert segment_adjacency(np.full((3, 3), -1)).shape == (0, 2)
    assert segment_adjacency(np.array([[4]])).shape == (0, 2)
    with pytest.raises(ValueError, match="two-dimensional"):
        segment_adjacency(np.arange(5))
    with pytest.raises(ValueError, match="connectivity"):
        segment_adjacency(np.zeros((2, 2), dtype=int), connectivity=6)  # type: ignore[arg-type]


def test_adjacency_against_a_pixel_loop():
    rng = np.random.default_rng(6)
    lab = rng.integers(-1, 12, (15, 17))
    for connectivity, steps in ((4, [(0, 1), (1, 0)]), (8, [(0, 1), (1, 0), (1, 1), (1, -1)])):
        expected = set()
        for r in range(15):
            for c in range(17):
                for dr, dc in steps:
                    rr, cc = r + dr, c + dc
                    if 0 <= rr < 15 and 0 <= cc < 17:
                        a, b = int(lab[r, c]), int(lab[rr, cc])
                        if a >= 0 and b >= 0 and a != b:
                            expected.add((min(a, b), max(a, b)))
        got = segment_adjacency(lab, connectivity=connectivity)  # type: ignore[arg-type]
        assert [tuple(p) for p in got.tolist()] == sorted(expected)


# ---------------------------------------------------------------------------
# Moran's I
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("size", [2, 4, 10])
def test_morans_i_of_a_checkerboard_is_minus_one(size):
    labels = np.arange(size * size).reshape(size, size)  # one segment per cell
    rows, cols = np.indices((size, size))
    values = np.where((rows + cols) % 2 == 0, 1.0, -1.0)
    adj = segment_adjacency(labels)
    assert len(adj) == 2 * size * (size - 1)
    assert morans_i(values.ravel(), adj) == pytest.approx(-1.0)
    table = segment_morans_i(labels, values)
    assert list(table.columns) == MORANS_I_COLUMNS
    assert table.iloc[0]["morans_i"] == pytest.approx(-1.0)
    assert table.iloc[0]["n_segments"] == size * size
    assert table.iloc[0]["n_adjacent_pairs"] == 2 * size * (size - 1)
    # The same board in blocks of 3 x 3 pixels: segment MEANS are what count.
    big_labels = np.kron(labels, np.ones((3, 3), dtype=int))
    big_values = np.kron(values, np.ones((3, 3)))
    assert segment_morans_i(big_labels, big_values).iloc[0]["morans_i"] == pytest.approx(-1.0)


def test_morans_i_chains_by_hand():
    # Deviations -1.5, -0.5, 0.5, 1.5: the three neighbour products sum to
    # 0.75 - 0.25 + 0.75 = 1.25; I = (4 / 6) * (2 * 1.25) / 5 = 1/3.
    assert morans_i([1, 2, 3, 4], [[0, 1], [1, 2], [2, 3]]) == pytest.approx(1 / 3)
    # Deviations -1, 0, 1: both products are 0.
    assert morans_i([1, 2, 3], [[0, 1], [1, 2]]) == pytest.approx(0.0)
    # Two segments always contrast: I = (2 / 2) * (2 * -0.25) / 0.5 = -1.
    assert morans_i([0.0, 1.0], [[0, 1]]) == pytest.approx(-1.0)
    # The same through a raster of four columns.
    labels = np.array([[0, 1, 2, 3]] * 2)
    values = np.array([[1.0, 2.0, 3.0, 4.0]] * 2)
    assert segment_morans_i(labels, values).iloc[0]["morans_i"] == pytest.approx(1 / 3)


def test_morans_i_of_a_smooth_gradient():
    # 6 x 8 segments, value = column number: neighbours are alike.
    n_rows, n_cols = 6, 8
    labels = np.arange(n_rows * n_cols).reshape(n_rows, n_cols)
    values = np.tile(np.arange(n_cols, dtype=float), (n_rows, 1))
    adj = segment_adjacency(labels)
    # By hand: deviations d_j = j - 3.5. Left-right pairs (6 per column step)
    # give sum_j d_j d_(j+1) = 26.25 per row; up-down pairs (5 per column) give
    # sum_j d_j^2 = 42 per row pair. n = 48, m = 6 * 7 + 5 * 8 = 82.
    dev = np.arange(n_cols) - 3.5
    cross = n_rows * (dev[:-1] * dev[1:]).sum() + (n_rows - 1) * (dev**2).sum()
    assert cross == pytest.approx(6 * 26.25 + 5 * 42.0)
    expected = 48 * cross / (82 * n_rows * (dev**2).sum())
    got = morans_i(values.ravel(), adj)
    assert got == pytest.approx(expected)
    assert got == pytest.approx(_dense_morans_i(values.ravel(), adj))
    assert got == pytest.approx(0.8537, abs=1e-4)  # 48 * 367.5 / (82 * 252)
    assert segment_morans_i(labels, values).iloc[0]["morans_i"] == pytest.approx(expected)
    # A finer gradient is closer to 1.
    fine_labels = np.arange(40 * 40).reshape(40, 40)
    fine_values = np.add.outer(np.arange(40.0), np.arange(40.0))
    assert segment_morans_i(fine_labels, fine_values).iloc[0]["morans_i"] > 0.97


def test_morans_i_against_the_weight_matrix_formula():
    rng = np.random.default_rng(8)
    labels = _blocks(24, 30, 3) % 37  # 37 segments, most in several patches
    labels = labels[rng.permutation(24)][:, rng.permutation(30)]
    values = rng.normal(size=(3, 24, 30))
    for connectivity in (4, 8):
        adj = segment_adjacency(labels, connectivity=connectivity)  # type: ignore[arg-type]
        table = segment_morans_i(labels, values, connectivity=connectivity)  # type: ignore[arg-type]
        for b in range(3):
            means = np.array([values[b][labels == k].mean() for k in range(37)])
            assert table.iloc[b]["morans_i"] == pytest.approx(_dense_morans_i(means, adj), rel=1e-10)
            assert table.iloc[b]["n_adjacent_pairs"] == len(adj)
    # Unrelated values: I is near its chance level -1 / (n - 1), far from 1.
    assert abs(table["morans_i"]).max() < 0.3


def test_morans_i_degenerate_and_malformed():
    chain = [[0, 1], [1, 2]]
    assert math.isnan(morans_i([2.0, 2.0, 2.0], chain))  # constant
    assert math.isnan(morans_i([1.0, 2.0, 3.0], np.zeros((0, 2), dtype=int)))  # no pair
    assert math.isnan(morans_i([1.0, 2.0, 3.0], []))
    assert math.isnan(morans_i([1.0], []))
    assert math.isnan(morans_i([], []))
    # A segment without a value is left out, with its pairs: what remains is
    # the two-segment case.
    assert morans_i([0.0, 1.0, np.nan], chain) == pytest.approx(-1.0)
    assert math.isnan(morans_i([0.0, np.nan, 1.0], chain))  # no pair left
    # A pair given twice or in both orders counts once.
    assert morans_i([1, 2, 3, 4], [[0, 1], [1, 0], [1, 2], [2, 3], [2, 3]]) == pytest.approx(1 / 3)
    # An isolated segment counts in n and in the mean, as the formula says.
    y = np.array([1.0, 2.0, 3.0, 10.0])
    assert morans_i(y, chain) == pytest.approx(_dense_morans_i(y, np.array(chain)))
    with pytest.raises(ValueError, match="outside"):
        morans_i([1.0, 2.0], [[0, 2]])
    with pytest.raises(ValueError, match="outside"):
        morans_i([1.0, 2.0], [[-1, 1]])
    with pytest.raises(ValueError, match="itself"):
        morans_i([1.0, 2.0], [[1, 1]])
    with pytest.raises(ValueError, match="shape"):
        morans_i([1.0, 2.0], [0, 1])
    with pytest.raises(ValueError, match="integer"):
        morans_i([1.0, 2.0], [[0.0, 1.0]])
    with pytest.raises(ValueError, match="one-dimensional"):
        morans_i([[1.0, 2.0]], [[0, 1]])
    with pytest.raises(ValueError, match="infinite"):
        morans_i([1.0, np.inf], [[0, 1]])


def test_segment_morans_i_masks_and_degenerate_rasters():
    labels = np.array([[0, 0, 1, 1, 2, 2]] * 2)
    values = np.array([[0.0, 0.0, 1.0, 1.0, 5.0, 5.0]] * 2)
    full = segment_morans_i(labels, values).iloc[0]
    assert full["n_segments"] == 3 and full["n_adjacent_pairs"] == 2
    assert full["morans_i"] == pytest.approx(morans_i([0.0, 1.0, 5.0], [[0, 1], [1, 2]]))
    # Masking segment 2 out leaves two segments, which always contrast.
    valid = labels != 2
    cut = segment_morans_i(labels, values, valid=valid).iloc[0]
    assert cut["n_segments"] == 2 and cut["n_adjacent_pairs"] == 1
    assert cut["morans_i"] == pytest.approx(-1.0)
    # A band with no value in a segment drops that segment in that band only.
    two = np.stack([values, values])
    two[1][labels == 2] = np.nan
    table = segment_morans_i(labels, two, band_names=["a", "b"])
    assert table["band"].tolist() == ["a", "b"]
    assert table.iloc[0]["morans_i"] == pytest.approx(full["morans_i"])
    assert table.iloc[1]["morans_i"] == pytest.approx(-1.0)
    assert table.iloc[1]["n_segments"] == 2
    # One segment, or equal means: not estimable.
    assert math.isnan(segment_morans_i(np.zeros((3, 3), dtype=int), np.eye(3)).iloc[0]["morans_i"])
    assert math.isnan(segment_morans_i(labels, np.ones((2, 6))).iloc[0]["morans_i"])
    with pytest.raises(ValueError, match="two-dimensional"):
        segment_morans_i(np.arange(4), np.arange(4.0))


# ---------------------------------------------------------------------------
# Global Score
# ---------------------------------------------------------------------------


def _image(seed: int) -> np.ndarray:
    """Two bands on 24 x 24 pixels: 6 x 6-pixel patches of different levels plus noise."""
    rng = np.random.default_rng(seed)
    truth = _blocks(24, 24, 6)
    levels = rng.normal(0, 3, (2, 16))
    return levels[:, truth] + rng.normal(0, 1, (2, 24, 24))


def test_global_score_against_the_formula():
    values = _image(9)
    candidates = {"fine": _blocks(24, 24, 2), "true": _blocks(24, 24, 6), "coarse": _blocks(24, 24, 12)}
    gs = global_score(candidates, values, band_names=["b1", "b2"])
    assert list(gs.columns) == GLOBAL_SCORE_COLUMNS
    # Candidates in the order given; for each, the bands and then the mean row.
    assert gs["segmentation"].tolist() == ["fine"] * 3 + ["true"] * 3 + ["coarse"] * 3
    assert gs["band"].tolist() == ["b1", "b2", "mean"] * 3

    names = list(candidates)
    for b, band in enumerate(["b1", "b2"]):
        wvar = np.array(
            [weighted_variance(candidates[n], values[b]).iloc[0]["weighted_variance"] for n in names]
        )
        moran = np.array(
            [segment_morans_i(candidates[n], values[b]).iloc[0]["morans_i"] for n in names]
        )
        wvar_norm = (wvar - wvar.min()) / (wvar.max() - wvar.min())
        moran_norm = (moran - moran.min()) / (moran.max() - moran.min())
        rows = gs[gs["band"] == band].set_index("segmentation").loc[names]
        assert rows["weighted_variance"].to_numpy() == pytest.approx(wvar, rel=1e-12)
        assert rows["morans_i"].to_numpy() == pytest.approx(moran, rel=1e-12)
        assert rows["weighted_variance_norm"].to_numpy() == pytest.approx(wvar_norm, abs=1e-12)
        assert rows["morans_i_norm"].to_numpy() == pytest.approx(moran_norm, abs=1e-12)
        assert rows["global_score"].to_numpy() == pytest.approx(wvar_norm + moran_norm, abs=1e-12)
        assert rows["n_segments"].tolist() == [144, 16, 4]
        # Best and worst on each component get 0 and 1. Variance inside
        # segments falls as segments get smaller; likeness of neighbours rises.
        assert rows.loc["fine", "weighted_variance_norm"] == 0.0
        assert rows.loc["coarse", "weighted_variance_norm"] == 1.0
        assert rows.loc["fine", "morans_i_norm"] == 1.0
        assert sorted(rows["morans_i_norm"])[0] == 0.0
        assert ((rows["global_score"] >= 0) & (rows["global_score"] <= 2)).all()
        # The planted segmentation has the lowest (best) score.
        assert rows["global_score"].idxmin() == "true"

    numeric = GLOBAL_SCORE_COLUMNS[2:]
    for name in names:
        mine = gs[gs["segmentation"] == name]
        mean_row = mine[mine["band"] == "mean"].iloc[0]
        per_band = mine[mine["band"] != "mean"]
        for col in numeric:
            assert mean_row[col] == pytest.approx(per_band[col].mean(), rel=1e-12)

    # A sequence is the same set under the names "0", "1", "2".
    listed = global_score(list(candidates.values()), values, band_names=["b1", "b2"])
    assert listed["segmentation"].tolist() == ["0"] * 3 + ["1"] * 3 + ["2"] * 3
    assert listed[numeric].equals(gs[numeric])
    # Same input, same output, to the last bit.
    assert global_score(candidates, values, band_names=["b1", "b2"]).equals(gs)


def test_global_score_depends_on_the_candidate_set():
    values = _image(10)[0]
    fine, true, coarse = _blocks(24, 24, 2), _blocks(24, 24, 6), _blocks(24, 24, 12)
    three = global_score({"fine": fine, "true": true, "coarse": coarse}, values)
    two = global_score({"fine": fine, "true": true}, values)

    def pick(frame, name, col):
        return frame[(frame["segmentation"] == name) & (frame["band"] == "band_0")].iloc[0][col]

    # The raw components of a candidate do not change with the set ...
    for col in ("weighted_variance", "morans_i"):
        assert pick(two, "true", col) == pytest.approx(pick(three, "true", col), rel=1e-12)
    # ... but its score does: with two candidates each is best on one
    # component and worst on the other, so both score exactly 1.
    assert pick(two, "true", "global_score") == pytest.approx(1.0)
    assert pick(two, "fine", "global_score") == pytest.approx(1.0)
    assert pick(three, "true", "global_score") < 0.9


def test_global_score_one_candidate():
    values = _image(11)
    labels = _blocks(24, 24, 6)
    gs = global_score([labels], values)
    assert gs["segmentation"].tolist() == ["0", "0", "0"]
    assert gs["band"].tolist() == ["band_0", "band_1", "mean"]
    assert gs[["weighted_variance_norm", "morans_i_norm", "global_score"]].isna().all().all()
    assert gs[["weighted_variance", "morans_i", "n_segments"]].notna().all().all()
    wv = weighted_variance(labels, values)["weighted_variance"].to_numpy()
    mi = segment_morans_i(labels, values)["morans_i"].to_numpy()
    assert gs["weighted_variance"].to_numpy()[:2] == pytest.approx(wv)
    assert gs["morans_i"].to_numpy()[:2] == pytest.approx(mi)
    assert gs["weighted_variance"].to_numpy()[2] == pytest.approx(wv.mean())


def test_global_score_uses_the_same_pixels_for_every_candidate():
    values = _image(12)[0]
    a = _blocks(24, 24, 6)
    b = _blocks(24, 24, 4).copy()
    b[:5, :] = -1  # candidate b has no segment in the top rows
    valid = np.ones((24, 24), dtype=bool)
    valid[:, -3:] = False
    gs = global_score({"a": a, "b": b}, values, valid=valid)
    common = (b >= 0) & valid
    row_a = gs[(gs["segmentation"] == "a") & (gs["band"] == "band_0")].iloc[0]
    expected = weighted_variance(a, values, valid=common).iloc[0]
    assert row_a["weighted_variance"] == pytest.approx(expected["weighted_variance"], rel=1e-12)
    assert row_a["n_segments"] == expected["n_segments"]
    assert row_a["morans_i"] == pytest.approx(
        segment_morans_i(a, values, valid=common).iloc[0]["morans_i"], rel=1e-12
    )


def test_global_score_degenerate_components():
    values = _image(13)[0]
    a, b = _blocks(24, 24, 6), _blocks(24, 24, 4)
    # The same candidate twice: both components are equal, so both are 0.
    same = global_score([a, a], values)
    assert (same[["weighted_variance_norm", "morans_i_norm", "global_score"]] == 0.0).all().all()
    # A single segment has no neighbour: Moran's I and its score are NaN, and
    # it is left out of the range the others are scaled over.
    whole = np.zeros((24, 24), dtype=int)
    gs = global_score({"a": a, "b": b, "whole": whole}, values)
    rows = gs[gs["band"] == "band_0"].set_index("segmentation")
    assert math.isnan(rows.loc["whole", "morans_i"])
    assert math.isnan(rows.loc["whole", "global_score"])
    assert rows.loc["whole", "weighted_variance_norm"] == 1.0
    assert sorted(rows.loc[["a", "b"], "morans_i_norm"]) == [0.0, 1.0]
    assert math.isnan(gs[(gs["segmentation"] == "whole") & (gs["band"] == "mean")].iloc[0]["global_score"])
    # Only one candidate has a Moran's I: it cannot be placed in a range.
    lone = global_score({"a": a, "whole": whole}, values)
    assert lone["morans_i_norm"].isna().all()
    assert lone["global_score"].isna().all()
    assert lone["weighted_variance_norm"].notna().all()


def test_global_score_malformed_inputs():
    values = np.zeros((4, 4))
    lab = np.zeros((4, 4), dtype=int)
    with pytest.raises(ValueError, match="no candidate"):
        global_score([], values)
    with pytest.raises(ValueError, match="wrap a single raster"):
        global_score(lab, values)
    with pytest.raises(ValueError, match="shape"):
        global_score([lab, np.zeros((4, 5), dtype=int)], values)
    with pytest.raises(ValueError, match="two-dimensional"):
        global_score([np.zeros(16, dtype=int)], np.zeros(16))
    with pytest.raises(ValueError, match="mean"):
        global_score([lab], values, band_names=["mean"])
    with pytest.raises(ValueError, match="connectivity"):
        global_score([lab], values, connectivity=5)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Speed
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    os.environ.get("FMU_SKIP_TIMING_TESTS") == "1",
    reason="timing test switched off with FMU_SKIP_TIMING_TESTS=1",
)
def test_large_raster_is_fast():
    rng = np.random.default_rng(14)
    labels = _blocks(2000, 2000, 28)  # 72 x 72 = 5,184 segments
    noise = rng.standard_normal((2000, 2000), dtype=np.float32).astype(np.float64)
    values = np.stack([noise, noise + labels % 7])
    # Processor time, not wall time: a busy machine does not fail the test.
    start = time.process_time()
    ev = explained_variance(labels, values)
    mi = segment_morans_i(labels, values)
    used = time.process_time() - start
    assert ev["n_segments"].tolist() == [5184, 5184]
    assert ev["n_pixels"].tolist() == [4_000_000, 4_000_000]
    assert ev.iloc[0]["r2"] < 0.01  # noise
    assert ev.iloc[1]["r2"] == pytest.approx(4.0 / 5.0, abs=0.01)  # variance 4 between, 1 within
    assert mi.iloc[0]["n_adjacent_pairs"] == 2 * 72 * 71
    assert used < 3.0

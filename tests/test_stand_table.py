"""fmu.utils.stand_table: the stand table off Earth Engine, its preprocessing and k-means (round 14).

Pure Python, no Earth Engine. The skewness is checked against what Earth Engine's Reducer.skew
gave on 26 Oct 2026 for three lists (a read-only call, recorded in
docs/handoff/2026-10-26-round14.md); the starts against scikit-learn's own KMeans.
"""

from __future__ import annotations

import csv
import io
import math

import numpy as np
import pytest
from sklearn.cluster import KMeans
from threadpoolctl import threadpool_limits

from fmu.utils import stand_table as st

# ---------------------------------------------------------------- the skewness


@pytest.mark.parametrize(
    "values, ee_skew",
    [
        ([1.0, 2.0, 3.0, 10.0], 1.0182337649086284),
        ([0.5, 0.7, 0.1, 4.0, 2.2, 9.5, 0.3], 1.4438591652297939),
    ],
)
def test_the_skewness_is_earth_engines(values, ee_skew):
    """Reducer.skew on Earth Engine gave these (26 Oct 2026); g1, not the adjusted G1."""
    assert st.skewness(np.array(values)) == pytest.approx(ee_skew, rel=1e-12)


def test_a_band_with_no_spread_has_no_skew():
    assert st.skewness(np.full(5, 3.0)) == 0.0


# ---------------------------------------------------------------- the table


def _table(bands, values, labels=None, left_out=()):
    labels = list(range(len(values))) if labels is None else labels
    rows = [[lbl, *v] for lbl, v in zip(labels, values, strict=True)]
    return st.stand_table_from_columns(rows, bands=bands, left_out=set(left_out))


def test_the_rows_are_sorted_by_label_and_the_left_out_are_marked():
    t = _table(["a"], [[1.0], [2.0], [3.0]], labels=[30.0, 10, 20], left_out={20})
    assert t.labels.tolist() == [10, 20, 30]
    assert t.values[:, 0].tolist() == [2.0, 3.0, 1.0]
    assert t.in_fit.tolist() == [True, False, True]


@pytest.mark.parametrize(
    "rows, match",
    [
        ([[1, 0.5], [1, 0.7]], "twice"),
        ([[1, None]], "missing"),
        ([[1.5, 0.5]], "whole number"),
        ([[1, 0.5, 0.6]], "values"),
    ],
)
def test_a_bad_table_is_refused(rows, match):
    with pytest.raises(ValueError, match=match):
        st.stand_table_from_columns(rows, bands=["a"])


# ---------------------------------------------------------------- the default rule


def _rng(seed=0):
    return np.random.default_rng(seed)


def _hand_table(n=60, left_out=()):
    rng = _rng(1)
    right = rng.lognormal(0, 1.0, n)  # right-skewed
    left = -rng.lognormal(0, 1.0, n)  # left-skewed
    flat = np.full(n, 7.0)  # constant
    plain = rng.normal(0, 1, n)
    phase = rng.uniform(-math.pi, math.pi, n)
    aspect = np.where(rng.random(n) < 0.2, 0.0, rng.uniform(0, 2 * math.pi, n))  # some flat
    cols = {
        "right": right,
        "left": left,
        "flat": flat,
        "plain": plain,
        "ndvi_phase_annual_sin": np.sin(phase) ** 3,  # skewed on purpose
        "ndvi_phase_annual_cos": np.cos(phase),
        "aspect_sin": np.sin(aspect) * (aspect > 0),
        "aspect_cos": np.cos(aspect) * (aspect > 0),
    }
    bands = list(cols)
    values = np.column_stack([cols[b] for b in bands])
    return _table(bands, values.tolist(), left_out=left_out)


DECOMPOSED = ["ndvi_phase_annual", "aspect"]


def test_the_default_rule_logs_by_absolute_skew_with_the_old_offset():
    t = _hand_table()
    pre = st.preprocess(t, rule="abs_skew", threshold=1.0, decomposed=DECOMPOSED)
    r = pre.record
    assert "right" in r["log_transformed_bands"] and "left" in r["log_transformed_bands"]
    assert "ndvi_phase_annual_sin" not in r["log_transformed_bands"]  # review B13
    col = st._column(t, "right")
    assert r["log_offsets"]["right"] == pytest.approx(-col.min() + 1e-3)
    assert "flat" in r["dropped_constant_bands"] and "flat" not in pre.bands


def test_the_default_rule_still_tests_aspects_pair():
    """The default rule tests aspect's pair, as the Earth Engine path does."""
    t = _hand_table()
    pre = st.preprocess(t, rule="abs_skew", threshold=0.0, decomposed=DECOMPOSED)
    assert {"aspect_sin", "aspect_cos"} <= set(pre.record["log_transformed_bands"])


# ---------------------------------------------------------------- k-means


def _blobs(n=150, seed=5):
    rng = _rng(seed)
    centres = np.array([[0, 0, 0], [4, 0, 1], [0, 5, -1], [3, 3, 3]], dtype=float)
    return np.vstack([c + rng.normal(0, 0.8, (n // 4, 3)) for c in centres])


@pytest.mark.parametrize("k", [2, 3, 5, 8])
def test_the_starts_are_scikit_learns_and_the_best_is_the_one_it_keeps(k):
    x = _blobs()
    starts = st.kmeans_starts(x, k, n_starts=25, seed=42)
    best = starts[st.best_start(starts)]
    with threadpool_limits(limits=1):
        ref = KMeans(n_clusters=k, n_init=25, random_state=42).fit(x)
    assert best.wcss == pytest.approx(ref.inertia_, rel=1e-12)
    assert st.same_clustering(best.labels, ref.labels_)


def test_the_starts_repeat_exactly():
    x = _blobs()
    a = st.kmeans_starts(x, 4, n_starts=25, seed=42)
    b = st.kmeans_starts(x, 4, n_starts=25, seed=42)
    assert [s.wcss for s in a] == [s.wcss for s in b]
    assert all((s.labels == t.labels).all() for s, t in zip(a, b, strict=True))


def test_the_agreement_is_over_every_pair_of_starts():
    x = _blobs()
    starts = st.kmeans_starts(x, 4, n_starts=25, seed=42)
    agreement = st.starts_agreement(starts)
    assert agreement["n_pairs"] == 300
    assert 0.0 <= agreement["ari_min"] <= agreement["ari_median"] <= 1.0
    same = st.starts_agreement([starts[0], starts[0]])
    assert same == {"ari_median": 1.0, "ari_min": 1.0, "n_pairs": 1}


def test_a_later_start_replaces_the_best_only_if_lower_and_different():
    labels = np.array([0, 0, 1, 1])
    starts = [
        st.Start(labels=labels, centres=np.zeros((2, 1)), wcss=2.0, n_iter=1),
        st.Start(labels=1 - labels, centres=np.zeros((2, 1)), wcss=1.0, n_iter=1),  # same partition
        st.Start(labels=np.array([0, 1, 0, 1]), centres=np.zeros((2, 1)), wcss=1.5, n_iter=1),
    ]
    assert st.best_start(starts) == 2


def test_the_rows_left_out_are_typed_by_the_nearest_fitted_centre():
    x = _blobs()
    in_fit = np.ones(len(x), dtype=bool)
    in_fit[::7] = False
    pre = st.Preprocessed(bands=["a", "b", "c"], values=x)
    fit = st.fit_types(pre, in_fit, k=4, n_starts=25, seed=42)
    starts = st.kmeans_starts(x[in_fit], 4, n_starts=25, seed=42)
    best = starts[st.best_start(starts)]
    assert (fit.types[in_fit] == best.labels).all()
    d = ((x[~in_fit][:, None, :] - best.centres[None]) ** 2).sum(axis=2)
    assert (fit.types[~in_fit] == d.argmin(axis=1)).all()
    assert fit.wcss == best.wcss and len(fit.wcss_of_each_start) == 25


def test_too_few_rows_for_k_is_refused():
    with pytest.raises(ValueError, match="cannot hold"):
        st.kmeans_starts(np.zeros((3, 2)), 4, n_starts=2, seed=42)


# ---------------------------------------------------------------- the files


def test_the_files_hold_the_rows_keyed_by_label():
    t = _hand_table(n=12, left_out={3})
    pre = st.preprocess(t, rule="abs_skew", threshold=1.0, decomposed=DECOMPOSED)
    raw = list(csv.reader(io.StringIO(st.table_csv(t))))
    assert raw[0] == ["stand_lbl", "in_fit", *t.bands]
    assert raw[4][:2] == ["3", "0"]
    assert float(raw[1][2]) == t.values[0, 0]  # 17 significant digits: exact
    rows = list(csv.reader(io.StringIO(st.rows_csv(t, pre, types=np.arange(12) % 3))))
    assert rows[0] == ["stand_lbl", "in_fit", "type", *pre.bands]
    assert len(rows) == 13 and rows[2][2] == "1"


def test_an_unknown_rule_or_a_missing_pair_is_refused():
    t = _hand_table()
    with pytest.raises(ValueError, match="unknown rule"):
        st.preprocess(t, rule="log_everything", threshold=1.0, decomposed=DECOMPOSED)
    with pytest.raises(ValueError, match="angle pair"):
        st.preprocess(t, rule="abs_skew", threshold=1.0, decomposed=["ndvi_phase_semi"])

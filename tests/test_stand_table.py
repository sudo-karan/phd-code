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
    """Only the new rule keeps aspect's pair out of the test (round 13's question 8)."""
    t = _hand_table()
    pre = st.preprocess(t, rule="abs_skew", threshold=0.0, decomposed=DECOMPOSED)
    assert {"aspect_sin", "aspect_cos"} <= set(pre.record["log_transformed_bands"])


# ---------------------------------------------------------------- the new rule


def test_only_right_skewed_bands_are_logged_as_log1p_over_the_iqr():
    t = _hand_table()
    pre = st.preprocess(t, rule="right_skew", threshold=1.0, decomposed=DECOMPOSED)
    r = pre.record
    assert r["log_transformed_bands"] == ["right"]
    raw = st._column(t, "right")
    q25, _, q75 = st.exact_quartiles(raw)
    assert r["log1p_params"]["right"] == {"min": raw.min(), "iqr": q75 - q25}
    logged = np.log1p((raw - raw.min()) / (q75 - q25))
    l25, l50, l75 = st.exact_quartiles(logged)
    assert pre.values[:, pre.bands.index("right")] == pytest.approx((logged - l50) / (l75 - l25))
    # A left-skewed band is not transformed: only centred and scaled.
    left = st._column(t, "left")
    p25, p50, p75 = st.exact_quartiles(left)
    assert pre.values[:, pre.bands.index("left")] == pytest.approx((left - p50) / (p75 - p25))


def test_the_minimum_is_over_every_row_so_the_log_holds_for_the_rows_left_out():
    """The lowest value sits on a row left out of the fit; its log is still defined."""
    t = _hand_table()
    lowest = int(np.argmin(st._column(t, "right")))
    t = _hand_table(left_out={int(t.labels[lowest])})
    pre = st.preprocess(t, rule="right_skew", threshold=1.0, decomposed=DECOMPOSED)
    assert not t.in_fit[lowest]
    assert np.all(np.isfinite(pre.values))
    assert pre.record["log1p_params"]["right"]["min"] == st._column(t, "right").min()


def test_a_constant_band_is_dropped_before_the_skew_test():
    t = _hand_table()
    pre = st.preprocess(t, rule="right_skew", threshold=1.0, decomposed=DECOMPOSED)
    assert "flat" in pre.record["dropped_constant_bands"]
    assert "flat" not in pre.record["skew_before"]
    assert "flat" not in pre.bands


def test_no_angle_component_is_skew_tested_or_logged():
    t = _hand_table()
    pre = st.preprocess(t, rule="right_skew", threshold=0.0, decomposed=DECOMPOSED)
    r = pre.record
    for comp in ("ndvi_phase_annual_sin", "ndvi_phase_annual_cos", "aspect_sin", "aspect_cos"):
        assert comp not in r["skew_before"] and comp not in r["log_transformed_bands"], comp


def test_an_angles_pair_shares_one_spread_so_the_circle_is_not_stretched():
    t = _hand_table()
    pre = st.preprocess(t, rule="right_skew", threshold=1.0, decomposed=DECOMPOSED)
    raw_s, raw_c = st._column(t, "aspect_sin"), st._column(t, "aspect_cos")
    iqr = [st.exact_quartiles(v)[2] - st.exact_quartiles(v)[0] for v in (raw_s, raw_c)]
    shared = math.sqrt((iqr[0] ** 2 + iqr[1] ** 2) / 2)
    (pair,) = [p for p in pre.record["angle_pairs"] if p["bands"] == ["aspect_sin", "aspect_cos"]]
    assert pair["shared_spread"] == pytest.approx(shared)
    s = pre.values[:, pre.bands.index("aspect_sin")]
    c = pre.values[:, pre.bands.index("aspect_cos")]
    # One factor along both axes: the scaled differences are the raw ones over one spread.
    assert np.diff(s) == pytest.approx(np.diff(raw_s) / shared)
    assert np.diff(c) == pytest.approx(np.diff(raw_c) / shared)
    assert pre.record["scaling"]["aspect_sin"]["center"] == st.exact_quartiles(raw_s)[1]


def test_an_angle_pair_with_one_constant_component_is_kept_and_with_two_is_dropped():
    n = 20
    rng = _rng(3)
    base = rng.normal(0, 1, n)
    one = _table(
        ["x", "aspect_sin", "aspect_cos"],
        np.column_stack([base, np.zeros(n), rng.normal(0, 1, n)]).tolist(),
    )
    pre = st.preprocess(one, rule="right_skew", threshold=1.0, decomposed=["aspect"])
    assert {"aspect_sin", "aspect_cos"} <= set(pre.bands)
    both = _table(
        ["x", "aspect_sin", "aspect_cos"], np.column_stack([base, np.zeros(n), np.zeros(n)]).tolist()
    )
    pre = st.preprocess(both, rule="right_skew", threshold=1.0, decomposed=["aspect"])
    assert pre.bands == ["x"]
    assert pre.record["dropped_constant_bands"] == ["aspect_cos", "aspect_sin"]


def test_the_skew_is_recorded_before_and_after():
    t = _hand_table()
    pre = st.preprocess(t, rule="right_skew", threshold=1.0, decomposed=DECOMPOSED)
    r = pre.record
    raw = st._column(t, "right")
    assert r["skew_before"]["right"] == pytest.approx(st.skewness(raw))
    q25, _, q75 = st.exact_quartiles(raw)
    assert r["skew_after"]["right"] == pytest.approx(
        st.skewness(np.log1p((raw - raw.min()) / (q75 - q25)))
    )
    assert r["skew_after"]["left"] == r["skew_before"]["left"]


def test_an_unknown_rule_or_a_missing_pair_is_refused():
    t = _hand_table()
    with pytest.raises(ValueError, match="unknown rule"):
        st.preprocess(t, rule="log_everything", threshold=1.0, decomposed=DECOMPOSED)
    with pytest.raises(ValueError, match="angle pair"):
        st.preprocess(t, rule="right_skew", threshold=1.0, decomposed=["ndvi_phase_semi"])


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
    pre = st.preprocess(t, rule="right_skew", threshold=1.0, decomposed=DECOMPOSED)
    raw = list(csv.reader(io.StringIO(st.table_csv(t))))
    assert raw[0] == ["stand_lbl", "in_fit", *t.bands]
    assert raw[4][:2] == ["3", "0"]
    assert float(raw[1][2]) == t.values[0, 0]  # 17 significant digits: exact
    rows = list(csv.reader(io.StringIO(st.rows_csv(t, pre, types=np.arange(12) % 3))))
    assert rows[0] == ["stand_lbl", "in_fit", "type", *pre.bands]
    assert len(rows) == 13 and rows[2][2] == "1"

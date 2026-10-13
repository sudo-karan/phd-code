"""Tests of `fmu.evaluation.permutation` with known answers.

All data is built here. Nothing from any real site is read.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd
import pytest
from scipy import stats
from scipy.spatial.distance import pdist, squareform

from fmu.evaluation import permutation as pm
from fmu.evaluation._common import Statistic, pair_indices

# ---------------------------------------------------------------------------
# Mantel and partial Mantel
# ---------------------------------------------------------------------------


def test_mantel_is_the_same_to_the_last_bit_wherever_the_arrays_sit_in_memory():
    # A BLAS dot product can change in its last binary digit with the memory
    # offset of its inputs. The same numbers must give the same correlation.
    rng = np.random.default_rng(0)
    x, y, z = rng.random(300), rng.random(300), rng.random(300)
    seen = set()
    for kx in range(8):
        for ky in range(8):
            a, b, c = np.empty(308), np.empty(308), np.empty(308)
            a[kx : kx + 300], b[ky : ky + 300], c[kx : kx + 300] = x, y, z
            av, bv, cv = a[kx : kx + 300], b[ky : ky + 300], c[kx : kx + 300]
            seen.add((pm.mantel_r(av, bv), pm.partial_mantel_r(av, bv, cv)))
    assert len(seen) == 1


def test_mantel_equals_pearson_and_spearman_of_the_condensed_vectors():
    rng = np.random.default_rng(1)
    for n in (5, 12, 30):
        x = pdist(rng.normal(size=(n, 2)))
        y = x + rng.normal(scale=0.5, size=x.shape) ** 2
        r = pm.mantel_r(x, y)
        assert r == pytest.approx(np.corrcoef(x, y)[0, 1], abs=1e-12)
        assert r == pytest.approx(stats.pearsonr(x, y).statistic, abs=1e-12)
        assert pm.mantel_r(x, y, method="spearman") == pytest.approx(
            stats.spearmanr(x, y).statistic, abs=1e-12
        )


def test_mantel_identity_sign_constant_and_missing():
    x = np.array([1.0, 2.0, 4.0, 7.0, 11.0, 16.0])
    assert pm.mantel_r(x, x) == pytest.approx(1.0, abs=1e-15)
    assert pm.mantel_r(x, -x) == pytest.approx(-1.0, abs=1e-15)
    assert np.isnan(pm.mantel_r(x, np.full(6, 0.1)))
    assert np.isnan(pm.mantel_r(np.full(6, 3.0), x))
    # NaN pairs are dropped: the result is the correlation of the others.
    y = np.array([2.0, 1.0, 5.0, 6.0, 9.0, 20.0])
    xm, ym = x.copy(), y.copy()
    xm[1] = np.nan
    ym[4] = np.nan
    keep = [0, 2, 3, 5]
    assert pm.mantel_r(xm, ym) == pytest.approx(np.corrcoef(x[keep], y[keep])[0, 1])
    assert pm.mantel_r(xm, ym, method="spearman") == pytest.approx(
        stats.spearmanr(x[keep], y[keep]).statistic
    )
    # fewer than 3 pairs left
    assert np.isnan(pm.mantel_r([1.0, 2.0, np.nan], [2.0, 1.0, 3.0]))
    with pytest.raises(ValueError):
        pm.mantel_r(x, x[:3])
    with pytest.raises(ValueError):
        pm.mantel_r(x, x, method="kendall")  # type: ignore[arg-type]


def _residuals(a: np.ndarray, z: np.ndarray) -> np.ndarray:
    design = np.column_stack([np.ones_like(z), z])
    coef, *_ = np.linalg.lstsq(design, a, rcond=None)
    return a - design @ coef


def test_partial_mantel_equals_correlation_of_residuals():
    rng = np.random.default_rng(2)
    for _ in range(5):
        z = rng.gamma(2.0, size=66)
        x = 0.7 * z + rng.normal(size=66)
        y = -0.4 * z + 0.5 * x + rng.normal(size=66)
        expected = np.corrcoef(_residuals(x, z), _residuals(y, z))[0, 1]
        assert pm.partial_mantel_r(x, y, z) == pytest.approx(expected, abs=1e-10)
        rx, ry, rz = (stats.rankdata(v) for v in (x, y, z))
        expected_s = np.corrcoef(_residuals(rx, rz), _residuals(ry, rz))[0, 1]
        assert pm.partial_mantel_r(x, y, z, method="spearman") == pytest.approx(
            expected_s, abs=1e-10
        )


def test_partial_mantel_with_unrelated_third_matrix_equals_mantel():
    # z is made orthogonal to x, to y and to the constant, so r_xz = r_yz = 0.
    x = np.array([1.0, 1.0, -1.0, -1.0, 1.0, 1.0, -1.0, -1.0])
    y = np.array([2.0, 1.0, -1.0, -3.0, 1.5, 1.0, 0.5, -2.0])
    z = np.array([1.0, -1.0, 2.0, -1.0, -3.0, 1.0, -1.0, 4.0])
    basis = np.linalg.qr(np.column_stack([np.ones(8), x, y]))[0]
    z = z - basis @ (basis.T @ z)
    assert abs(np.corrcoef(z, x)[0, 1]) < 1e-12
    assert abs(np.corrcoef(z, y)[0, 1]) < 1e-12
    assert pm.partial_mantel_r(x, y, z) == pytest.approx(pm.mantel_r(x, y), abs=1e-12)


def test_partial_mantel_degenerate():
    x = np.array([1.0, 2.0, 4.0, 7.0, 11.0, 16.0])
    y = np.array([2.0, 1.0, 5.0, 6.0, 9.0, 20.0])
    assert np.isnan(pm.partial_mantel_r(x, y, x))  # z explains x completely
    assert np.isnan(pm.partial_mantel_r(x, y, np.ones(6)))  # constant z
    z = np.array([3.0, 1.0, 4.0, 1.0, 5.0, 9.0])
    zm = z.copy()
    zm[0] = np.nan
    assert pm.partial_mantel_r(x, y, zm) == pytest.approx(
        pm.partial_mantel_r(x[1:], y[1:], z[1:])
    )


def test_claim_dissimilarity_by_hand():
    stand = pm.claim_dissimilarity([0, 0, 1, -1])
    np.testing.assert_array_equal(stand, [0, 1, np.nan, 1, np.nan, np.nan])
    typ = pm.claim_dissimilarity([0, 0, 1, 2], [0, 0, 0, 1], kind="type")
    np.testing.assert_array_equal(typ, [0, 0, 1, 0, 1, 1])
    # types are not compared across super-groups, nor for an untyped stand
    across = pm.claim_dissimilarity(
        [0, 1, 2, 3], [0, 1, 0, -1], kind="type", super_group=[0, 0, 1, 1]
    )
    np.testing.assert_array_equal(across, [1, np.nan, np.nan, np.nan, np.nan, np.nan])
    with pytest.raises(ValueError):
        pm.claim_dissimilarity([0, 0, 1], kind="type")


def _toy(seed: int, n: int = 40, n_groups: int = 4):
    rng = np.random.default_rng(seed)
    coords = rng.uniform(0, 1000, size=(n, 2))
    attrs = rng.normal(size=(n, 3))
    groups = np.sort(rng.integers(0, n_groups, n))
    stand_id = groups * 10 + rng.integers(0, 4, n)  # stands nested in groups
    types_of_stand = rng.integers(0, 3, stand_id.max() + 1)
    stand_type = types_of_stand[stand_id]
    return coords, attrs, groups, stand_id, stand_type


def test_mantel_statistic_equals_the_plain_functions():
    coords, attrs, groups, sid, typ = _toy(3)
    field = pdist(attrs)
    geo = pdist(coords)
    i, j = pair_indices(len(sid))
    within = groups[i] == groups[j]
    rng = np.random.default_rng(0)
    sid_missing = sid.copy()
    sid_missing[[2, 17]] = -1
    for labels in (sid, rng.permutation(sid), sid_missing):
        claim = pm.claim_dissimilarity(labels)
        stat = pm.mantel_statistic(field)
        assert stat.name == "mantel_stand" and stat.alternative == "greater"
        assert stat(labels) == pytest.approx(pm.mantel_r(claim, field), abs=1e-12)
        grouped = pm.mantel_statistic(field, groups=groups)
        assert grouped(labels) == pytest.approx(pm.mantel_r(claim[within], field[within]), abs=1e-12)
        for method in ("pearson", "spearman"):
            partial = pm.mantel_statistic(field, groups=groups, geo_dist=geo, method=method)
            assert partial.name == "partial_mantel_stand"
            assert partial(labels) == pytest.approx(
                pm.partial_mantel_r(claim[within], field[within], geo[within], method=method),
                abs=1e-10,
            )
    sup = groups // 2
    claim_t = pm.claim_dissimilarity(sid, typ, kind="type", super_group=sup)
    stat_t = pm.mantel_statistic(field, kind="type", groups=groups, super_group=sup)
    assert stat_t.name == "mantel_type"
    assert stat_t(sid, typ) == pytest.approx(pm.mantel_r(claim_t[within], field[within]), abs=1e-12)
    with pytest.raises(ValueError):
        stat_t(sid, None)
    spear = pm.mantel_statistic(field, method="spearman")
    assert spear(sid) == pytest.approx(
        pm.mantel_r(pm.claim_dissimilarity(sid), field, method="spearman"), abs=1e-12
    )


def test_mantel_statistic_is_one_for_a_map_that_explains_the_field():
    sid = np.array([0, 0, 0, 1, 1, 2, 2, 2])
    field = pm.claim_dissimilarity(sid)  # 0 inside a stand, 1 across
    assert pm.mantel_statistic(field)(sid) == pytest.approx(1.0)
    # pairs with a missing field distance are left out when the statistic is built
    field[0] = np.nan
    assert pm.mantel_statistic(field)(sid) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# ANOSIM
# ---------------------------------------------------------------------------

_D4 = np.array([1.0, 3.0, 4.0, 5.0, 6.0, 2.0])  # d01 d02 d03 d12 d13 d23


def test_anosim_by_hand():
    res = pm.anosim(_D4, [0, 0, 1, 1])
    assert res.r == pytest.approx(1.0)
    row = res.per_stratum.iloc[0]
    assert (row["n_within"], row["n_between"]) == (2, 4)
    assert row["mean_rank_within"] == pytest.approx(1.5)
    assert row["mean_rank_between"] == pytest.approx(4.5)
    assert (res.n, res.n_groups) == (4, 2)
    assert list(res.per_stratum.columns) == [
        "stratum",
        "n",
        "n_within",
        "n_between",
        "mean_rank_within",
        "mean_rank_between",
        "r",
        "weight",
    ]
    assert pm.anosim(_D4, [0, 1, 0, 1]).r == pytest.approx(-0.5)
    assert pm.anosim(squareform(_D4), [0, 0, 1, 1]).r == pytest.approx(1.0)


def test_anosim_separated_random_and_degenerate():
    rng = np.random.default_rng(4)
    x = np.concatenate([rng.normal(0, 0.1, (8, 2)), rng.normal(50, 0.1, (5, 2))])
    g = np.array([0] * 8 + [1] * 5)
    assert pm.anosim(pdist(x), g).r == pytest.approx(1.0)
    # random groups: R is near 0
    values = [
        pm.anosim(pdist(rng.normal(size=(60, 3))), rng.integers(0, 4, 60)).r for _ in range(30)
    ]
    assert abs(float(np.mean(values))) < 0.03
    assert max(abs(v) for v in values) < 0.3
    assert pm.anosim(np.full(15, 2.0), [0, 0, 0, 1, 1, 1]).r == pytest.approx(0.0)  # all tied
    assert np.isnan(pm.anosim(_D4, [0, 1, 2, 3]).r)  # every plot its own group
    assert np.isnan(pm.anosim(_D4, [0, 0, 0, 0]).r)  # one group
    # a plot with no group is left out: same answer as without it
    d5 = pdist(np.array([[0.0], [1.0], [5.0], [7.0], [100.0]]))
    assert pm.anosim(d5, [0, 0, 1, 1, -1]).r == pytest.approx(
        pm.anosim(pdist(np.array([[0.0], [1.0], [5.0], [7.0]])), [0, 0, 1, 1]).r
    )
    bad = d5.copy()
    bad[0] = np.nan
    with pytest.raises(ValueError):
        pm.anosim(bad, [0, 0, 1, 1, 1])
    bad = d5.copy()
    bad[3] = np.nan  # pair (0, 4); plot 4 is left out, so this is ignored
    assert np.isfinite(pm.anosim(bad, [0, 0, 1, 1, -1]).r)


def test_anosim_strata():
    rng = np.random.default_rng(5)
    x = rng.normal(size=(30, 2))
    g = rng.integers(0, 3, 30)
    d = pdist(x)
    assert pm.anosim(d, g, strata=np.zeros(30, int)).r == pytest.approx(pm.anosim(d, g).r)
    # two strata, each perfectly separated, with group codes reused across strata
    pts = np.array([0.0, 0.1, 5.0, 5.1, 5.2, 300.0, 300.2, 320.0, 320.1])
    grp = np.array([0, 0, 1, 1, 1, 1, 1, 0, 0])
    strata = np.array([0, 0, 0, 0, 0, 1, 1, 1, 1])
    dd = pdist(pts[:, None])
    for w in ("pairs", "equal"):
        assert pm.anosim(dd, grp, strata=strata, stratum_weights=w).r == pytest.approx(1.0)
    # unequal strata by hand: "equal" is the plain mean, "pairs" the weighted mean
    strata = np.repeat([0, 1, 2], [12, 10, 8])
    per = [pm.anosim(pdist(x[strata == s]), g[strata == s]) for s in range(3)]
    r_s = np.array([p.r for p in per])
    n_w = np.array([p.per_stratum["n_within"][0] for p in per], dtype=float)
    n_b = np.array([p.per_stratum["n_between"][0] for p in per], dtype=float)
    equal = pm.anosim(d, g, strata=strata, stratum_weights="equal")
    np.testing.assert_allclose(equal.per_stratum["r"], r_s)
    assert equal.r == pytest.approx(r_s.mean())
    weights = n_w * n_b / (n_w + n_b)
    pooled = pm.anosim(d, g, strata=strata)
    assert pooled.r == pytest.approx((weights * r_s).sum() / weights.sum())
    np.testing.assert_allclose(pooled.per_stratum["weight"], weights)
    # a stratum where R is not defined (one group) gets no weight
    g2 = g.copy()
    g2[strata == 2] = 0
    part = pm.anosim(d, g2, strata=strata)
    assert np.isnan(part.per_stratum["r"][2]) and part.per_stratum["weight"][2] == 0
    assert part.r == pytest.approx((weights[:2] * r_s[:2]).sum() / weights[:2].sum())


def test_anosim_statistic_equals_anosim():
    coords, attrs, groups, sid, typ = _toy(6)
    field = pdist(attrs)
    rng = np.random.default_rng(1)
    missing = sid.copy()
    missing[[0, 5, 30]] = -1
    for w in ("pairs", "equal"):
        stat = pm.anosim_statistic(field, strata=groups, stratum_weights=w)
        assert stat.name == "anosim_stand" and stat.alternative == "greater"
        for labels in (sid, rng.permutation(sid), missing, rng.permutation(missing), sid):
            expected = pm.anosim(field, labels, strata=groups, stratum_weights=w).r
            assert stat(labels) == pytest.approx(expected, abs=1e-12, nan_ok=True)
    by_type = pm.anosim_statistic(field, by="type")
    assert by_type.name == "anosim_type"
    assert by_type(sid, typ) == pytest.approx(pm.anosim(field, typ).r)
    with pytest.raises(ValueError):
        by_type(sid, None)
    bad = field.copy()
    bad[0] = np.nan
    with pytest.raises(ValueError):
        pm.anosim_statistic(bad)
    strata = np.zeros(len(sid), int)
    strata[0] = -1  # plot 0 has no measurements: left out through its stratum
    stat = pm.anosim_statistic(squareform(_nan_plot(field, 0)), strata=strata)
    assert stat(sid) == pytest.approx(pm.anosim(pdist(attrs[1:]), sid[1:]).r)


def _nan_plot(condensed: np.ndarray, plot: int) -> np.ndarray:
    square = squareform(condensed)
    square[plot, :] = np.nan
    square[:, plot] = np.nan
    square[plot, plot] = 0.0
    return square[np.triu_indices(square.shape[0], k=1)]


# ---------------------------------------------------------------------------
# PERMANOVA
# ---------------------------------------------------------------------------


def test_permanova_one_variable_equals_one_way_anova():
    rng = np.random.default_rng(7)
    samples = [rng.normal(0, 1, 7), rng.normal(0.8, 1, 12), rng.normal(-0.5, 1, 4)]
    x = np.concatenate(samples)
    g = np.repeat([0, 1, 2], [7, 12, 4])
    order = rng.permutation(len(x))
    x, g = x[order], g[order]
    res = pm.permanova(pdist(x[:, None]), g)
    assert res.f == pytest.approx(stats.f_oneway(*samples).statistic, rel=1e-9)
    ss_total = ((x - x.mean()) ** 2).sum()
    ss_between = sum(len(s) * (s.mean() - x.mean()) ** 2 for s in samples)
    assert res.r2 == pytest.approx(ss_between / ss_total, rel=1e-9)
    assert res.ss_total == pytest.approx(ss_total)
    assert (res.df_among, res.df_within, res.n, res.n_groups, res.n_strata) == (2, 20, 23, 3, 1)


def test_permanova_several_variables():
    rng = np.random.default_rng(8)
    x = rng.normal(size=(25, 4)) * np.array([1.0, 3.0, 0.5, 2.0])
    g = rng.integers(0, 4, 25)
    res = pm.permanova(squareform(pdist(x)), g)
    ss_total = ((x - x.mean(axis=0)) ** 2).sum()
    ss_within = sum(((x[g == k] - x[g == k].mean(axis=0)) ** 2).sum() for k in np.unique(g))
    a = len(np.unique(g))
    assert res.ss_total == pytest.approx(ss_total)
    assert res.ss_within == pytest.approx(ss_within)
    assert res.f == pytest.approx(((ss_total - ss_within) / (a - 1)) / (ss_within / (25 - a)))


def test_permanova_strata_equal_nested_anova():
    rng = np.random.default_rng(9)
    n = 40
    x = rng.normal(size=n)
    strata = rng.integers(0, 3, n)
    g = rng.integers(0, 3, n)  # codes reused in every stratum: the cell is (stratum, group)
    x = x + 5.0 * strata  # a large stratum difference that must not count
    res = pm.permanova(pdist(x[:, None]), g, strata=strata)
    ss_t = sum(((x[strata == s] - x[strata == s].mean()) ** 2).sum() for s in np.unique(strata))
    cells = {(s, k) for s, k in zip(strata, g, strict=True)}
    ss_w = 0.0
    for s, k in cells:
        v = x[(strata == s) & (g == k)]
        ss_w += ((v - v.mean()) ** 2).sum()
    a, k_strata = len(cells), len(np.unique(strata))
    assert res.ss_total == pytest.approx(ss_t)
    assert res.ss_within == pytest.approx(ss_w)
    assert (res.df_among, res.df_within) == (a - k_strata, n - a)
    assert res.f == pytest.approx(((ss_t - ss_w) / (a - k_strata)) / (ss_w / (n - a)))
    assert res.r2 == pytest.approx((ss_t - ss_w) / ss_t)
    assert (res.n_groups, res.n_strata) == (a, k_strata)
    one = pm.permanova(pdist(x[:, None]), g, strata=np.zeros(n, int))
    plain = pm.permanova(pdist(x[:, None]), g)
    assert one == plain
    # plots with a missing group or stratum are left out
    g_missing = g.copy()
    g_missing[:3] = -1
    assert pm.permanova(pdist(x[:, None]), g_missing).f == pytest.approx(
        pm.permanova(pdist(x[3:, None]), g[3:]).f
    )


def test_permanova_degenerate():
    x = np.array([1.0, 1.0, 1.0, 4.0, 4.0, 9.0, 9.0])
    g = np.array([0, 0, 0, 1, 1, 2, 2])
    d = pdist(x[:, None])
    res = pm.permanova(d, g)
    assert res.f == float("inf") and res.r2 == pytest.approx(1.0)
    assert np.isnan(pm.permanova(d, np.zeros(7, int)).f)  # one group
    assert np.isnan(pm.permanova(d, np.arange(7)).f)  # every plot its own group
    flat = pm.permanova(np.zeros(21), g)  # no variation at all
    assert np.isnan(flat.f) and np.isnan(flat.r2)
    empty = pm.permanova(d, np.full(7, -1))
    assert empty.n == 0 and np.isnan(empty.f)
    bad = d.copy()
    bad[0] = np.nan
    with pytest.raises(ValueError):
        pm.permanova(bad, g)


def test_permanova_statistic_equals_permanova():
    coords, attrs, groups, sid, typ = _toy(10)
    field = pdist(attrs)
    rng = np.random.default_rng(2)
    missing = sid.copy()
    missing[[1, 8]] = -1
    stat = pm.permanova_statistic(field, strata=groups)
    assert stat.name == "permanova_stand" and stat.alternative == "greater"
    for labels in (sid, rng.permutation(sid), missing):
        assert stat(labels) == pytest.approx(
            pm.permanova(field, labels, strata=groups).f, rel=1e-12, nan_ok=True
        )
    by_type = pm.permanova_statistic(field, by="type", strata=groups)
    assert by_type.name == "permanova_type"
    perm = rng.permutation(len(sid))
    assert by_type(sid[perm], typ[perm]) == pytest.approx(
        pm.permanova(field, typ[perm], strata=groups).f
    )
    assert pm.permanova_statistic(field)(sid) == pytest.approx(pm.permanova(field, sid).f)
    with pytest.raises(ValueError):
        by_type(sid, None)
    with pytest.raises(ValueError):
        pm.permanova_statistic(_nan_plot(field, 0))


# ---------------------------------------------------------------------------
# Null models
# ---------------------------------------------------------------------------


def _pairs_sorted(ids: np.ndarray, types: np.ndarray) -> list[tuple[int, int]]:
    return sorted(zip(ids.tolist(), types.tolist(), strict=True))


def test_free_permutation_rearranges_and_is_seeded():
    sid = np.array([0, 0, 1, 1, 2, -1, 3, 3, 3])
    typ = np.array([5, 5, 6, 6, 7, -1, 8, 8, 8])
    draws = pm.free_permutation(sid, typ, 50, seed=11)
    assert draws.name == "free_permutation" and draws.info == {"n_plots": 9}
    assert draws.ids.shape == (50, 9) and draws.types is not None
    np.testing.assert_array_equal(draws.observed_id, sid)
    for r in range(50):
        assert sorted(draws.ids[r]) == sorted(sid)
        assert _pairs_sorted(draws.ids[r], draws.types[r]) == _pairs_sorted(sid, typ)
    again = pm.free_permutation(sid, typ, 50, seed=11)
    np.testing.assert_array_equal(draws.ids, again.ids)
    np.testing.assert_array_equal(draws.types, again.types)
    other = pm.free_permutation(sid, typ, 50, seed=12)
    assert not np.array_equal(draws.ids, other.ids)
    assert pm.free_permutation(sid, None, 3, seed=1).types is None
    # every plot is equally likely to receive a given label
    many = pm.free_permutation(np.arange(4), None, 4000, seed=3)
    share = (many.ids == 0).mean(axis=0)
    np.testing.assert_allclose(share, 0.25, atol=0.03)
    with pytest.raises(ValueError):
        pm.free_permutation(sid, typ, 0, seed=1)
    with pytest.raises(TypeError):
        pm.free_permutation(sid, typ, 5, seed=None)  # type: ignore[arg-type]
    assert not hasattr(draws, "score") and "p_value" not in draws.info


def test_within_group_permutation_never_moves_a_plot_out_of_its_group():
    rng = np.random.default_rng(13)
    groups = np.array([0, 0, 0, 0, 1, 2, 2, 2, -1, -1, 4, 4])
    sid = np.arange(12)  # all different, so every move can be seen
    typ = sid + 100
    draws = pm.within_group_permutation(sid, typ, groups, 300, seed=rng)
    assert draws.name == "within_group_permutation"
    assert draws.info == {"n_groups": 4, "group_sizes": [4, 1, 3, 2]}
    assert draws.types is not None
    for code in (0, 1, 2, 4):
        members = groups == code
        block = draws.ids[:, members]
        assert (np.sort(block, axis=1) == np.sort(sid[members])).all()
        assert np.isin(block, sid[members]).all()
    np.testing.assert_array_equal(draws.ids[:, groups == 1], np.full((300, 1), 4))  # group of one
    np.testing.assert_array_equal(draws.ids[:, groups == -1], np.tile([8, 9], (300, 1)))
    np.testing.assert_array_equal(draws.types, draws.ids + 100)  # stand and type move together
    assert (draws.ids[:, :4] != sid[:4]).any()  # and plots do move inside a group
    a = pm.within_group_permutation(sid, typ, groups, 20, seed=5)
    b = pm.within_group_permutation(sid, typ, groups, 20, seed=5)
    np.testing.assert_array_equal(a.ids, b.ids)
    assert not np.array_equal(a.ids, pm.within_group_permutation(sid, typ, groups, 20, seed=6).ids)


# ---------------------------------------------------------------------------
# The driver
# ---------------------------------------------------------------------------


def _sum_over_stand_zero(vector: np.ndarray, how: str = "sum") -> Statistic:
    def func(stand_id, stand_type):
        chosen = stand_id == 0
        total = float(vector @ chosen)
        return total if how == "sum" else total / int(chosen.sum())

    return Statistic("toy", func, "greater")


def test_run_test_constant_statistic_and_smallest_p():
    sid = np.array([0, 0, 1, 1, 2, 2])
    draws = pm.free_permutation(sid, None, 19, seed=1)
    res = pm.run_test(Statistic("constant", lambda s, t: 3.0, "greater"), draws)
    assert res.p_value == 1.0 and res.observed == 3.0
    assert (res.statistic, res.null, res.alternative) == ("constant", "free_permutation", "greater")
    assert (res.n_draws, res.n_valid) == (19, 19)
    assert res.null_sd == 0.0 and res.null_mean == 3.0
    # a statistic that is larger on the observed labels than on any relabelling
    best = Statistic("best", lambda s, t: float(np.array_equal(s, sid)) + 0.0, "greater")
    fixed = dataclasses.replace(draws, ids=np.tile(sid[::-1], (19, 1)))
    assert pm.run_test(best, fixed).p_value == pytest.approx(1 / 20)
    assert not pm.TestResult.__test__
    with pytest.raises(TypeError):
        pm.run_test(lambda s, t: 0.0, draws)  # type: ignore[arg-type]


def test_run_test_exact_small_case():
    sid = np.array([0, 0, 1, 1])
    stat = _sum_over_stand_zero(np.array([4.0, 3.0, 2.0, 1.0]))
    draws = pm.free_permutation(sid, None, 6000, seed=21)
    res = pm.run_test(stat, draws)
    assert res.observed == 7.0  # the largest of the 6 possible values
    reached = int((res.null_values >= 7.0).sum())
    assert res.p_value == pytest.approx((reached + 1) / 6001)
    assert res.p_value == pytest.approx(1 / 6, abs=0.02)
    assert res.null_q50 == pytest.approx(5.0)
    assert res.null_mean == pytest.approx(5.0, abs=0.05)
    again = pm.run_test(stat, pm.free_permutation(sid, None, 6000, seed=21))
    np.testing.assert_array_equal(res.null_values, again.null_values)
    assert res.p_value == again.p_value


def test_run_test_has_the_right_size_when_nothing_is_there():
    rng = np.random.default_rng(31)
    rejections = 0
    n_sets = 400
    for _ in range(n_sets):
        vector = rng.normal(size=20)
        sid = rng.integers(0, 4, 20)
        sid[0] = 0
        draws = pm.free_permutation(sid, None, 99, seed=rng)
        rejections += pm.run_test(_sum_over_stand_zero(vector, "mean"), draws).p_value <= 0.05
    assert 0.02 <= rejections / n_sets <= 0.09


def test_run_test_undefined_draws():
    sid = np.array([0, 0, 1, 1, 2, 2, 3, 3])
    draws = pm.free_permutation(sid, None, 40, seed=2)
    calls = {"k": 0}

    def sometimes(stand_id, stand_type):
        calls["k"] += 1
        # call 1 is the observed value; every fourth relabelling is undefined
        return float("nan") if calls["k"] > 1 and (calls["k"] - 1) % 4 == 0 else 1.0

    res = pm.run_test(Statistic("gaps", sometimes, "greater"), draws)
    assert res.n_valid == 30 and int(np.isnan(res.null_values).sum()) == 10
    assert np.isnan(res.p_value)  # 25% undefined is more than the 10% allowed
    calls["k"] = 0
    lenient = pm.run_test(Statistic("gaps", sometimes, "greater"), draws, min_valid_fraction=0.5)
    assert lenient.p_value == 1.0
    nan_obs = pm.run_test(Statistic("nan", lambda s, t: float("nan"), "greater"), draws)
    assert np.isnan(nan_obs.p_value) and nan_obs.n_valid == 0 and np.isnan(nan_obs.null_mean)


def test_run_tests_table_and_holm():
    np.testing.assert_allclose(pm.holm_adjust([0.01, 0.04, 0.03]), [0.03, 0.06, 0.06])
    np.testing.assert_allclose(pm.holm_adjust([0.5, np.nan, 0.01]), [0.5, np.nan, 0.02])
    np.testing.assert_allclose(pm.holm_adjust([0.6, 0.7]), [1.0, 1.0])
    assert pm.holm_adjust([]).shape == (0,)
    with pytest.raises(ValueError):
        pm.holm_adjust([1.2])
    coords, attrs, groups, sid, typ = _toy(14)
    field = pdist(attrs)
    statistics = [
        pm.mantel_statistic(field, groups=groups),
        pm.anosim_statistic(field, strata=groups),
        pm.permanova_statistic(field, by="type", strata=groups),
    ]
    draws = pm.within_group_permutation(sid, typ, groups, 49, seed=8)
    table = pm.run_tests(statistics, draws)
    assert isinstance(table, pd.DataFrame)
    assert list(table.columns) == [
        "statistic",
        "null",
        "alternative",
        "observed",
        "p_value",
        "n_draws",
        "n_valid",
        "null_mean",
        "null_sd",
        "null_q05",
        "null_q50",
        "null_q95",
        "p_holm",
    ]
    assert list(table["statistic"]) == ["mantel_stand", "anosim_stand", "permanova_type"]
    assert (table["null"] == "within_group_permutation").all()
    np.testing.assert_allclose(table["p_holm"], pm.holm_adjust(table["p_value"]))
    single = pm.run_test(statistics[1], draws)
    assert table["p_value"][1] == single.p_value and table["observed"][1] == single.observed
    same = pm.run_tests(statistics, pm.within_group_permutation(sid, typ, groups, 49, seed=8))
    pd.testing.assert_frame_equal(table, same)
    assert pm.run_tests([], draws).shape == (0, 13)


def test_planted_map_is_detected_by_every_statistic():
    # Stands that set the field values exactly are found by every statistic.
    rng = np.random.default_rng(15)
    groups = np.repeat(np.arange(4), 10)
    sid = groups * 3 + rng.integers(0, 3, 40)
    attrs = rng.normal(size=(sid.max() + 1, 2))[sid] + rng.normal(scale=0.05, size=(40, 2))
    field = pdist(attrs)
    draws = pm.within_group_permutation(sid, None, groups, 199, seed=4)
    table = pm.run_tests(
        [
            pm.mantel_statistic(field, groups=groups),
            pm.anosim_statistic(field, strata=groups),
            pm.permanova_statistic(field, strata=groups),
        ],
        draws,
    )
    assert (table["p_value"] == 1 / 200).all()
    assert (table["observed"] > table["null_q95"]).all()


def test_null_draws_validation():
    with pytest.raises(ValueError):
        pm.NullDraws("my_score", np.arange(3), None, np.zeros((2, 3), int), None, {})
    with pytest.raises(ValueError):
        pm.NullDraws("rotation", np.arange(3), None, np.zeros((2, 4), int), None, {})
    with pytest.raises(ValueError):
        pm.NullDraws("rotation", np.arange(3), np.arange(3), np.zeros((2, 3), int), None, {})

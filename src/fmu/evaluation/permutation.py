"""Established matrix tests and the significance test that stands behind them.

Three things live here.

  - **Statistics** (established, each from a paper): the Mantel and partial
    Mantel correlations, ANOSIM's R and PERMANOVA's pseudo-F. Each compares
    what the map says about the plots with how different the plots are in the
    field.
  - **Null models that relabel plots**: free permutation, and permutation
    inside groups (villages). A null model returns relabelled plots
    (`NullDraws`) and nothing else. It returns no number about agreement.
  - **The driver**: `run_test(statistic, draws)` computes a named statistic on
    the observed labels and on every relabelling and returns the permutation
    p-value. This is the only place a p-value is made, and it always belongs
    to a named, established statistic.

Chance is always simulated by relabelling PLOTS. Pairs of plots are never
permuted: 267 plots make 35,511 pairs, but there are still only 267 plots.

Nothing here knows about any site. Inputs are arrays of integer codes
(`_common.encode_labels`) and distances.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, fields
from typing import Any, ClassVar, Literal, get_args

import numpy as np
import numpy.typing as npt
import pandas as pd
from scipy.stats import rankdata

from ._common import (
    CLAIM_DIFF_TYPE,
    CLAIM_NONE,
    CLAIM_SAME_STAND,
    CLAIM_SAME_TYPE,
    CLAIM_TYPE_UNKNOWN,
    Alternative,
    BoolArray,
    FloatArray,
    IntArray,
    Seed,
    Statistic,
    as_codes,
    as_condensed_distance,
    as_generator,
    pair_claims,
    pair_indices,
    permutation_p_value,
)

MantelMethod = Literal["pearson", "spearman"]
ClaimKind = Literal["stand", "type"]
StratumWeights = Literal["pairs", "equal"]

#: The four null models of the package (the last two are in `spatial_null`).
NULL_NAMES = ("free_permutation", "within_group_permutation", "rotation", "torus_translation")

# A partial correlation divides by sqrt((1 - r_xz^2)(1 - r_yz^2)). Below this
# the third matrix explains one of the others completely and nothing is left.
_PARTIAL_EPS = 1e-12


# ---------------------------------------------------------------------------
# Small internal helpers
# ---------------------------------------------------------------------------


def _check_choice(value: str, choices: tuple[str, ...], name: str) -> None:
    if value not in choices:
        raise ValueError(f"{name} must be one of {choices}, got {value!r}")


def _as_pair_vector(values: npt.ArrayLike, name: str) -> FloatArray:
    """A one-dimensional float vector, one value per pair; `NaN` allowed."""
    arr = np.array(values, dtype=np.float64)
    if arr.ndim != 1:
        raise ValueError(f"{name} must be a one-dimensional (condensed) vector, got shape {arr.shape}")
    if np.isinf(arr).any():
        raise ValueError(f"{name} holds an infinite value")
    return arr


def _n_from_condensed(length: int) -> int:
    return int(round((1 + np.sqrt(1 + 8 * length)) / 2))


def _pearson(x: FloatArray, y: FloatArray) -> float:
    """Pearson correlation of two complete vectors; `NaN` if not estimable."""
    if x.shape[0] < 3 or np.ptp(x) == 0 or np.ptp(y) == 0:
        return float("nan")
    xc = x - x.mean()
    yc = y - y.mean()
    den = float(np.sqrt((xc @ xc) * (yc @ yc)))
    if not den > 0:
        return float("nan")
    return float(min(1.0, max(-1.0, float(xc @ yc) / den)))


def _partial(r_xy: float, r_xz: float, r_yz: float) -> float:
    """First-order partial correlation from three correlations."""
    if np.isnan(r_xy) or np.isnan(r_xz) or np.isnan(r_yz):
        return float("nan")
    den_sq = (1.0 - r_xz * r_xz) * (1.0 - r_yz * r_yz)
    if not den_sq > _PARTIAL_EPS:
        return float("nan")
    return float(min(1.0, max(-1.0, (r_xy - r_xz * r_yz) / np.sqrt(den_sq))))


def _ranks(x: FloatArray) -> FloatArray:
    return np.asarray(rankdata(x, method="average"), dtype=np.float64)


# ---------------------------------------------------------------------------
# A3: Mantel and partial Mantel
# ---------------------------------------------------------------------------


def mantel_r(x: npt.ArrayLike, y: npt.ArrayLike, *, method: MantelMethod = "pearson") -> float:
    """Mantel correlation of two distance matrices.

    Formula: the Pearson correlation of the two matrices read as two long
    vectors, one value per pair of plots,
    `r = sum (x - xbar)(y - ybar) / sqrt(sum (x - xbar)^2 * sum (y - ybar)^2)`.
    With `method="spearman"` each vector is first replaced by its ranks
    (average ranks for ties), which makes it a rank correlation.
    Reference: Mantel (1967).

    `x` and `y` are condensed vectors of equal length (the order of
    `_common.pair_indices`). Returns one number in `[-1, 1]`.

    Degenerate inputs: a pair where either value is `NaN` is dropped (ranks are
    taken after dropping). The result is `NaN` when fewer than 3 pairs remain
    or when either vector is constant. Vectors of different length raise
    `ValueError`.

    The number is only a description. Its p-value must come from relabelling
    plots (`run_test`), never from treating the pairs as a sample.
    """
    _check_choice(method, get_args(MantelMethod), "method")
    a = _as_pair_vector(x, "x")
    b = _as_pair_vector(y, "y")
    if a.shape[0] != b.shape[0]:
        raise ValueError(f"x and y differ in length: {a.shape[0]} and {b.shape[0]}")
    keep = ~(np.isnan(a) | np.isnan(b))
    a, b = a[keep], b[keep]
    if a.shape[0] < 3:
        return float("nan")
    if method == "spearman":
        a, b = _ranks(a), _ranks(b)
    return _pearson(a, b)


def partial_mantel_r(
    x: npt.ArrayLike, y: npt.ArrayLike, z: npt.ArrayLike, *, method: MantelMethod = "pearson"
) -> float:
    """Partial Mantel correlation of `x` and `y` with `z` held fixed.

    Formula: with the three Mantel correlations `r_xy`, `r_xz`, `r_yz` taken on
    the same pairs,
    `r_xy.z = (r_xy - r_xz r_yz) / sqrt((1 - r_xz^2)(1 - r_yz^2))`.
    It equals the correlation between what is left of `x` and what is left of
    `y` after a straight-line fit of each on `z`. Here `z` is usually the
    geographic distance: "do pairs the map calls different differ more in the
    field than their distance apart already explains?"
    Reference: Smouse, Long and Sokal (1986).

    Returns one number in `[-1, 1]`.

    Degenerate inputs: a pair where any of the three values is `NaN` is
    dropped. `NaN` when fewer than 3 pairs remain, when any vector is constant,
    or when `z` explains `x` or `y` completely (the denominator is 0).

    Holding distance fixed does not make the pairs independent, so the p-value
    still comes from relabelling plots (`run_test`).
    """
    _check_choice(method, get_args(MantelMethod), "method")
    a = _as_pair_vector(x, "x")
    b = _as_pair_vector(y, "y")
    c = _as_pair_vector(z, "z")
    if not a.shape[0] == b.shape[0] == c.shape[0]:
        raise ValueError(
            f"x, y and z differ in length: {a.shape[0]}, {b.shape[0]} and {c.shape[0]}"
        )
    keep = ~(np.isnan(a) | np.isnan(b) | np.isnan(c))
    a, b, c = a[keep], b[keep], c[keep]
    if a.shape[0] < 3:
        return float("nan")
    if method == "spearman":
        a, b, c = _ranks(a), _ranks(b), _ranks(c)
    return _partial(_pearson(a, b), _pearson(a, c), _pearson(b, c))


# Claim code (-1..3) + 1 -> dissimilarity the map claims for the pair.
_CLAIM_TO_DISSIMILARITY: dict[str, FloatArray] = {
    "stand": np.array([np.nan, 0.0, 1.0, 1.0, 1.0]),
    "type": np.array([np.nan, 0.0, 0.0, 1.0, np.nan]),
}
assert (CLAIM_NONE, CLAIM_SAME_STAND, CLAIM_SAME_TYPE, CLAIM_DIFF_TYPE, CLAIM_TYPE_UNKNOWN) == (
    -1,
    0,
    1,
    2,
    3,
)


def claim_dissimilarity(
    stand_id: npt.ArrayLike,
    stand_type: npt.ArrayLike | None = None,
    *,
    kind: ClaimKind = "stand",
    super_group: npt.ArrayLike | None = None,
) -> FloatArray:
    """What the map claims about every pair of plots, as a 0/1 distance.

    Formula, per pair:

      - `kind="stand"`: 0 if the two plots are in the same stand, 1 if they are
        in different stands;
      - `kind="type"`: 0 if they are in the same stand or in stands of the same
        type, 1 if their stands have different types.

    This is the "model matrix" of a Mantel test (Mantel 1967): the map turned
    into a distance matrix so that it can be correlated with the field
    distances.

    Arguments are integer codes, one per plot, `-1` for missing. Types are
    compared only inside one `super_group` (district), because a type number
    means a different forest in each one.

    Returns a condensed float vector (the order of `_common.pair_indices`).

    Degenerate inputs: `NaN` where the map makes no claim: either plot is in no
    stand; and, for `"type"`, where the two types cannot be compared (a stand
    without a type, or plots in different super-groups). `kind="type"` without
    `stand_type` raises `ValueError`.
    """
    _check_choice(kind, get_args(ClaimKind), "kind")
    sid = as_codes(stand_id, "stand_id")
    n = sid.shape[0]
    if kind == "type" and stand_type is None:
        raise ValueError('kind="type" needs stand_type')
    typ = None if stand_type is None or kind == "stand" else as_codes(stand_type, "stand_type", n=n)
    sup = (
        None
        if super_group is None or kind == "stand"
        else as_codes(super_group, "super_group", n=n)
    )
    i, j = pair_indices(n)
    claims = pair_claims(sid, typ, i, j, super_group=sup)
    return np.asarray(_CLAIM_TO_DISSIMILARITY[kind][claims.astype(np.int64) + 1], dtype=np.float64)


def mantel_statistic(
    field_dist: npt.ArrayLike,
    *,
    kind: ClaimKind = "stand",
    groups: npt.ArrayLike | None = None,
    super_group: npt.ArrayLike | None = None,
    geo_dist: npt.ArrayLike | None = None,
    method: MantelMethod = "pearson",
) -> Statistic:
    """The Mantel (or partial Mantel) correlation as a testable `Statistic`.

    Formula: `mantel_r(claim, field)`, or `partial_mantel_r(claim, field, geo)`
    when `geo_dist` is given, where `claim` is `claim_dissimilarity` of the
    map (`kind="stand"` tests the drawing, `kind="type"` the labelling). The
    claim takes two values, so the Pearson form is a point-biserial
    correlation: the standardised difference between the mean field distance
    of pairs the map calls different and of pairs it calls the same.
    References: Mantel (1967); Smouse, Long and Sokal (1986).

    The pair set is fixed when the statistic is built: pairs whose field
    distance (and geographic distance) is not `NaN`, and, when `groups` is
    given, only pairs inside one group. Two plots in different villages are
    always in different stands, so those pairs say nothing about the drawing,
    and they carry the between-village differences that must not be pooled.
    `groups=None` gives the classical all-pairs Mantel test.

    Returns a `Statistic` named `"mantel_<kind>"` or
    `"partial_mantel_<kind>"`, with `alternative="greater"`: a positive value
    means pairs the map calls different are more different in the field.

    Degenerate inputs: the call returns `NaN` when fewer than 3 pairs carry a
    claim, when the claim is the same for all of them, or (partial) when
    distance explains the claim or the field completely. A call for
    `kind="type"` without stand types raises `ValueError`.
    """
    _check_choice(kind, get_args(ClaimKind), "kind")
    _check_choice(method, get_args(MantelMethod), "method")
    y_all = as_condensed_distance(field_dist, name="field_dist", allow_nan=True)
    n = _n_from_condensed(y_all.shape[0])
    pi, pj = pair_indices(n)
    keep = ~np.isnan(y_all)
    z_all: FloatArray | None = None
    if geo_dist is not None:
        z_all = as_condensed_distance(geo_dist, n=n, name="geo_dist", allow_nan=True)
        keep &= ~np.isnan(z_all)
    if groups is not None:
        grp = as_codes(groups, "groups", n=n)
        keep &= (grp[pi] == grp[pj]) & (grp[pi] >= 0)
    sup = (
        None
        if super_group is None or kind == "stand"
        else as_codes(super_group, "super_group", n=n)
    )
    i = pi[keep]
    j = pj[keep]
    y = y_all[keep]
    z = None if z_all is None else z_all[keep]
    lookup = _CLAIM_TO_DISSIMILARITY[kind]

    # Used when every pair carries a claim. The claim takes two values, so its
    # ranks are a straight-line function of it and need not be computed.
    y_fast = _ranks(y) if method == "spearman" else y
    z_fast = None if z is None else (_ranks(z) if method == "spearman" else z)
    r_yz_fast = float("nan") if z_fast is None else _pearson(y_fast, z_fast)

    def func(stand_id: IntArray, stand_type: IntArray | None) -> float:
        if kind == "type" and stand_type is None:
            raise ValueError(f"the statistic mantel_{kind} needs stand types")
        claims = pair_claims(
            stand_id, stand_type if kind == "type" else None, i, j, super_group=sup
        )
        x = lookup[claims.astype(np.int64) + 1]
        has_claim = ~np.isnan(x)
        if has_claim.all():
            r_xy = _pearson(x, y_fast)
            if z_fast is None:
                return r_xy
            return _partial(r_xy, _pearson(x, z_fast), r_yz_fast)
        if z is None:
            return mantel_r(x[has_claim], y[has_claim], method=method)
        return partial_mantel_r(x[has_claim], y[has_claim], z[has_claim], method=method)

    name = f"mantel_{kind}" if geo_dist is None else f"partial_mantel_{kind}"
    return Statistic(name, func, "greater")


# ---------------------------------------------------------------------------
# A4: ANOSIM
# ---------------------------------------------------------------------------


@dataclass(frozen=True, eq=False)
class AnosimResult:
    """Result of `anosim`.

    `r` is the statistic (pooled over strata when strata are given), `n` the
    number of plots used, `n_groups` the number of groups among them (with
    strata: the number of stratum-by-group cells). `per_stratum` has one row
    per stratum with columns `stratum, n, n_within, n_between,
    mean_rank_within, mean_rank_between, r, weight`; without strata it has one
    row with `stratum = 0`.
    """

    r: float
    n: int
    n_groups: int
    per_stratum: pd.DataFrame


@dataclass(frozen=True)
class _StratifiedPairs:
    """The pairs inside strata among a fixed set of plots, ranked per stratum."""

    i: IntArray
    j: IntArray
    stratum_of_pair: IntArray  # compact index 0..k-1
    rank: FloatArray  # rank of the pair's distance inside its stratum
    n_pairs: FloatArray  # (k,) M_s
    rank_sum: FloatArray  # (k,) sum of ranks in the stratum
    stratum_codes: IntArray  # (k,) the caller's stratum code
    n_plots: IntArray  # (k,) plots used in the stratum
    plot_stratum: IntArray  # (n,) compact stratum of each plot, -1 if not used


def _stratified_pairs(
    dist: FloatArray, strata: IntArray, used: BoolArray, *, rank: bool
) -> _StratifiedPairs:
    """Collect the pairs of used plots that share a stratum.

    Raises `ValueError` if one of those pairs has no distance (`NaN`).
    """
    n = strata.shape[0]
    codes, compact = np.unique(strata[used], return_inverse=True)
    plot_stratum = np.full(n, -1, dtype=np.int64)
    plot_stratum[used] = compact
    k = codes.shape[0]
    pi, pj = pair_indices(n)
    inside = (plot_stratum[pi] == plot_stratum[pj]) & (plot_stratum[pi] >= 0)
    i, j, d = pi[inside], pj[inside], dist[inside]
    if np.isnan(d).any():
        raise ValueError(
            "a pair of plots that is used has no distance (NaN); leave such plots out by "
            "giving them the stratum (or grouping) code -1"
        )
    s = plot_stratum[i]
    ranks = np.zeros(d.shape[0], dtype=np.float64)
    if rank:
        order = np.argsort(s, kind="stable")
        bounds = np.searchsorted(s[order], np.arange(k + 1))
        for b in range(k):
            members = order[bounds[b] : bounds[b + 1]]
            if members.shape[0]:
                ranks[members] = _ranks(d[members])
    return _StratifiedPairs(
        i=i,
        j=j,
        stratum_of_pair=s,
        rank=ranks,
        n_pairs=np.bincount(s, minlength=k).astype(np.float64),
        rank_sum=np.bincount(s, weights=ranks, minlength=k).astype(np.float64),
        stratum_codes=codes.astype(np.int64),
        n_plots=np.bincount(compact, minlength=k).astype(np.int64),
        plot_stratum=plot_stratum,
    )


def _anosim_parts(
    pairs: _StratifiedPairs, grouping: IntArray, weights: StratumWeights
) -> tuple[float, FloatArray, FloatArray, FloatArray, FloatArray, FloatArray, FloatArray]:
    """ANOSIM R and its per-stratum parts for one grouping of the plots.

    Returns `(r, n_within, n_between, mean_rank_within, mean_rank_between,
    r_per_stratum, weight)`.
    """
    k = pairs.n_pairs.shape[0]
    same = grouping[pairs.i] == grouping[pairs.j]
    n_w = np.bincount(pairs.stratum_of_pair[same], minlength=k).astype(np.float64)
    sum_w = np.bincount(pairs.stratum_of_pair[same], weights=pairs.rank[same], minlength=k)
    n_b = pairs.n_pairs - n_w
    sum_b = pairs.rank_sum - sum_w
    defined = (n_w > 0) & (n_b > 0)
    mean_w = np.full(k, np.nan)
    mean_b = np.full(k, np.nan)
    mean_w[n_w > 0] = sum_w[n_w > 0] / n_w[n_w > 0]
    mean_b[n_b > 0] = sum_b[n_b > 0] / n_b[n_b > 0]
    r_s = np.full(k, np.nan)
    r_s[defined] = (mean_b[defined] - mean_w[defined]) / (pairs.n_pairs[defined] / 2.0)
    weight = np.zeros(k, dtype=np.float64)
    if weights == "pairs":
        weight[defined] = n_w[defined] * n_b[defined] / (n_w[defined] + n_b[defined])
    else:
        weight[defined] = 1.0
    total = float(weight.sum())
    r = float((weight[defined] * r_s[defined]).sum() / total) if total > 0 else float("nan")
    return r, n_w, n_b, mean_w, mean_b, r_s, weight


def _strata_or_zeros(strata: npt.ArrayLike | None, n: int) -> IntArray:
    if strata is None:
        return np.zeros(n, dtype=np.int64)
    return as_codes(strata, "strata", n=n)


def _n_cells(plot_stratum: IntArray, grouping: IntArray, used: BoolArray) -> int:
    if not used.any():
        return 0
    width = int(grouping.max()) + 1
    return int(np.unique(plot_stratum[used] * width + grouping[used]).shape[0])


def anosim(
    distance: npt.ArrayLike,
    grouping: npt.ArrayLike,
    *,
    strata: npt.ArrayLike | None = None,
    stratum_weights: StratumWeights = "pairs",
) -> AnosimResult:
    """ANOSIM: are plots of one group closer to each other than to other plots?

    Formula, without strata: rank the `M = n (n - 1) / 2` distances among the
    plots used (rank 1 = smallest, average ranks for ties). With `rbar_W` the
    mean rank of pairs in the same group and `rbar_B` the mean rank of pairs in
    different groups, `R = (rbar_B - rbar_W) / (M / 2)`. `R` lies in
    `[-1, 1]`: 1 when every within-group distance is smaller than every
    between-group distance, about 0 when groups make no difference.
    Reference: Clarke (1993).

    With `strata` (blocks, for example villages) only pairs inside one stratum
    are used, the distances are ranked inside each stratum on its own `M_s`
    pairs, `R_s` is computed per stratum as above, and the result is the
    weighted mean `R = sum w_s R_s / sum w_s` over the strata where `R_s` is
    defined. `stratum_weights="pairs"` (the default) uses
    `w_s = n_W n_B / (n_W + n_B)`, the numbers of within and between pairs, so
    a stratum with one within-group pair counts little. `"equal"` uses
    `w_s = 1`, the plain average over blocks. The default is a declared
    choice, not a tuned one.

    `distance` is a condensed vector or a square matrix; `grouping` and
    `strata` are integer codes, one per plot, `-1` for missing.

    Returns an `AnosimResult` (see there).

    Degenerate inputs: plots with `grouping == -1` or `strata == -1` are left
    out. `R` (or `R_s`) is `NaN` when there is no within-group pair or no
    between-group pair (every plot its own group, or one group). All distances
    equal gives 0. A `NaN` distance between two plots that are both used
    raises `ValueError`; a `NaN` that touches only left-out plots is ignored.
    """
    _check_choice(stratum_weights, get_args(StratumWeights), "stratum_weights")
    dist = as_condensed_distance(distance, allow_nan=True)
    n = _n_from_condensed(dist.shape[0])
    grp = as_codes(grouping, "grouping", n=n)
    stra = _strata_or_zeros(strata, n)
    used = (grp >= 0) & (stra >= 0)
    pairs = _stratified_pairs(dist, stra, used, rank=True)
    r, n_w, n_b, mean_w, mean_b, r_s, weight = _anosim_parts(pairs, grp, stratum_weights)
    table = pd.DataFrame(
        {
            "stratum": pairs.stratum_codes,
            "n": pairs.n_plots,
            "n_within": n_w.astype(np.int64),
            "n_between": n_b.astype(np.int64),
            "mean_rank_within": mean_w,
            "mean_rank_between": mean_b,
            "r": r_s,
            "weight": weight,
        }
    )
    return AnosimResult(
        r=r,
        n=int(used.sum()),
        n_groups=_n_cells(pairs.plot_stratum, grp, used),
        per_stratum=table,
    )


def _by_labels(by: ClaimKind, name: str) -> Callable[[IntArray, IntArray | None], IntArray]:
    """Pick the grouping a statistic uses: the stand, or the stand's type."""

    def pick(stand_id: IntArray, stand_type: IntArray | None) -> IntArray:
        if by == "stand":
            return stand_id
        if stand_type is None:
            raise ValueError(f"the statistic {name} needs stand types")
        return stand_type

    return pick


def _check_field_dist_for_statistic(dist: FloatArray, stra: IntArray) -> None:
    """Refuse a `NaN` distance between two plots that a relabelling could use."""
    try:
        _stratified_pairs(dist, stra, stra >= 0, rank=False)
    except ValueError as exc:
        raise ValueError(
            "field_dist has no value (NaN) for a pair of plots inside one stratum. Give the "
            "plots without measurements the stratum code -1 (with no strata: pass strata of "
            "zeros with -1 for those plots), so that no relabelling can use them."
        ) from exc


def anosim_statistic(
    field_dist: npt.ArrayLike,
    *,
    by: ClaimKind = "stand",
    strata: npt.ArrayLike | None = None,
    stratum_weights: StratumWeights = "pairs",
) -> Statistic:
    """ANOSIM's R as a testable `Statistic`.

    Formula: `anosim(field_dist, grouping, strata=strata,
    stratum_weights=stratum_weights).r`, where the grouping is the stand of
    each plot (`by="stand"`, tests the drawing) or the type of its stand
    (`by="type"`, tests the labelling). Reference: Clarke (1993).

    The ranks depend only on the distances, the strata and which plots are
    used, so they are computed when the statistic is built and reused; they
    are recomputed only when a relabelling changes which plots have a label.

    Returns a `Statistic` named `"anosim_<by>"` with `alternative="greater"`
    (larger R: plots the map puts together are more alike in the field).

    Degenerate inputs: as `anosim` (`NaN` when a relabelling leaves no
    within-group pair or no between-group pair). `field_dist` must have a
    value for every pair of plots inside one stratum; plots without
    measurements are left out by giving them the stratum code `-1`, otherwise
    `ValueError`. A call for `by="type"` without stand types raises
    `ValueError`.
    """
    _check_choice(by, get_args(ClaimKind), "by")
    _check_choice(stratum_weights, get_args(StratumWeights), "stratum_weights")
    name = f"anosim_{by}"
    dist = as_condensed_distance(field_dist, name="field_dist", allow_nan=True)
    n = _n_from_condensed(dist.shape[0])
    stra = _strata_or_zeros(strata, n)
    _check_field_dist_for_statistic(dist, stra)
    in_stratum = stra >= 0
    pick = _by_labels(by, name)
    # Ranks for "every plot of a stratum has a label", and for the last other
    # set of labelled plots seen (a spatial null keeps that set fixed).
    cache: dict[bytes, _StratifiedPairs] = {
        in_stratum.tobytes(): _stratified_pairs(dist, stra, in_stratum, rank=True)
    }
    full_key = in_stratum.tobytes()

    def func(stand_id: IntArray, stand_type: IntArray | None) -> float:
        grouping = pick(stand_id, stand_type)
        used = in_stratum & (grouping >= 0)
        key = used.tobytes()
        pairs = cache.get(key)
        if pairs is None:
            pairs = _stratified_pairs(dist, stra, used, rank=True)
            for stale in [old for old in cache if old != full_key]:
                del cache[stale]
            cache[key] = pairs
        return _anosim_parts(pairs, grouping, stratum_weights)[0]

    return Statistic(name, func, "greater")


# ---------------------------------------------------------------------------
# A4: PERMANOVA
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PermanovaResult:
    """Result of `permanova`.

    `f` is the pseudo-F, `r2 = ss_among / ss_total` the share of the variation
    (inside strata, when strata are given) that the grouping accounts for.
    `n` is the number of plots used, `n_groups` the number of cells (stratum
    by group combinations that hold a plot; without strata, the groups) and
    `n_strata` the number of strata (1 without strata).
    """

    f: float
    r2: float
    ss_among: float
    ss_within: float
    ss_total: float
    df_among: int
    df_within: int
    n: int
    n_groups: int
    n_strata: int


def _permanova_core(
    i: IntArray, j: IntArray, d2: FloatArray, plot_stratum: IntArray, grouping: IntArray
) -> PermanovaResult:
    """PERMANOVA from the squared distances of the pairs inside strata.

    `i`, `j`, `d2` describe every pair of plots that share a stratum;
    `plot_stratum` is the compact stratum of each plot (`-1`: not in one).
    """
    used = (grouping >= 0) & (plot_stratum >= 0)
    n = int(used.sum())
    nan = float("nan")
    if n == 0:
        return PermanovaResult(nan, nan, nan, nan, nan, 0, 0, 0, 0, 0)
    both = used[i] & used[j]
    pi, pj, pd2 = i[both], j[both], d2[both]
    if np.isnan(pd2).any():
        raise ValueError(
            "a pair of plots that is used has no distance (NaN); leave such plots out by "
            "giving them the stratum (or grouping) code -1"
        )
    k_all = int(plot_stratum.max()) + 1
    n_s = np.bincount(plot_stratum[used], minlength=k_all).astype(np.float64)
    sum_s = np.bincount(plot_stratum[pi], weights=pd2, minlength=k_all)
    present = n_s > 0
    ss_total = float((sum_s[present] / n_s[present]).sum())
    # One code per (stratum, group) combination that holds a plot.
    cell = np.full(grouping.shape[0], -1, dtype=np.int64)
    width = int(grouping.max()) + 1
    cells, inverse = np.unique(
        plot_stratum[used] * width + grouping[used], return_inverse=True
    )
    cell[used] = inverse
    a = int(cells.shape[0])
    same = cell[pi] == cell[pj]
    n_c = np.bincount(cell[used], minlength=a).astype(np.float64)
    sum_c = np.bincount(cell[pi][same], weights=pd2[same], minlength=a)
    ss_within = float((sum_c / n_c).sum())
    ss_among = ss_total - ss_within
    k = int(present.sum())
    df_among = a - k
    df_within = n - a
    if df_among <= 0 or df_within <= 0 or (ss_within == 0 and ss_among == 0):
        f = nan
    elif ss_within == 0:
        f = float("inf") if ss_among > 0 else nan
    else:
        f = (ss_among / df_among) / (ss_within / df_within)
    r2 = ss_among / ss_total if ss_total > 0 else nan
    return PermanovaResult(
        f=float(f),
        r2=float(r2),
        ss_among=ss_among,
        ss_within=ss_within,
        ss_total=ss_total,
        df_among=df_among,
        df_within=df_within,
        n=n,
        n_groups=a,
        n_strata=k,
    )


def _pairs_inside_strata(
    dist: FloatArray, stra: IntArray
) -> tuple[IntArray, IntArray, FloatArray, IntArray]:
    """Pairs of plots that share a stratum, with squared distances."""
    n = stra.shape[0]
    in_stratum = stra >= 0
    plot_stratum = np.full(n, -1, dtype=np.int64)
    plot_stratum[in_stratum] = np.unique(stra[in_stratum], return_inverse=True)[1]
    pi, pj = pair_indices(n)
    inside = (plot_stratum[pi] == plot_stratum[pj]) & (plot_stratum[pi] >= 0)
    return pi[inside], pj[inside], dist[inside] ** 2, plot_stratum


def permanova(
    distance: npt.ArrayLike, grouping: npt.ArrayLike, *, strata: npt.ArrayLike | None = None
) -> PermanovaResult:
    """PERMANOVA: analysis of variance worked out from a distance matrix.

    Formula, without strata, for `n` plots in `a` groups:

      - `SS_T = (1 / n) * sum of d_ij^2 over all pairs`;
      - `SS_W = sum over groups of (1 / n_g) * sum of d_ij^2 over the pairs in
        the group`;
      - `SS_A = SS_T - SS_W`;
      - pseudo-F `= (SS_A / (a - 1)) / (SS_W / (n - a))`, `R2 = SS_A / SS_T`.

    With Euclidean distances on one measurement this is exactly the F of a
    one-way analysis of variance. Reference: Anderson (2001).

    With `strata` (for example villages) the stratum is fitted first and the
    groups are nested in strata: a cell is a (stratum, group) combination,
    `SS_T = sum over strata of (1 / n_s) * sum of d_ij^2 over the pairs in the
    stratum` (the variation inside strata), `SS_W` is the same sum over cells,
    and with `a` cells and `k` strata `df_among = a - k`, `df_within = n - a`,
    `F = (SS_A / df_among) / (SS_W / df_within)`. So a difference between
    villages is never counted as a difference between stands or types.

    `distance` is a condensed vector or a square matrix; `grouping` and
    `strata` are integer codes, one per plot, `-1` for missing.

    Returns a `PermanovaResult` (see there).

    Degenerate inputs: plots with a missing grouping or stratum are left out.
    `f` is `NaN` when `df_among <= 0` (one group per stratum), when
    `df_within <= 0` (every plot its own group), or when both sums of squares
    are 0; it is `inf` when `SS_W == 0 < SS_A` (plots identical inside every
    group, groups different). `r2` is `NaN` when `SS_T == 0`. With no plot
    used every number is `NaN`. A `NaN` distance between two plots that are
    both used raises `ValueError`. The F is a description; its p-value comes
    from relabelling plots (`run_test`), not from the F distribution.
    """
    dist = as_condensed_distance(distance, allow_nan=True)
    n = _n_from_condensed(dist.shape[0])
    grp = as_codes(grouping, "grouping", n=n)
    stra = _strata_or_zeros(strata, n)
    i, j, d2, plot_stratum = _pairs_inside_strata(dist, stra)
    return _permanova_core(i, j, d2, plot_stratum, grp)


def permanova_statistic(
    field_dist: npt.ArrayLike, *, by: ClaimKind = "stand", strata: npt.ArrayLike | None = None
) -> Statistic:
    """PERMANOVA's pseudo-F as a testable `Statistic`.

    Formula: `permanova(field_dist, grouping, strata=strata).f`, where the
    grouping is the stand of each plot (`by="stand"`) or the type of its stand
    (`by="type"`). With strata and `by="type"` the cell is (stratum, type):
    the type effect is estimated inside each stratum. Reference: Anderson
    (2001).

    Returns a `Statistic` named `"permanova_<by>"` with
    `alternative="greater"`.

    Degenerate inputs: as `permanova` (`NaN` or `inf`). `field_dist` must have
    a value for every pair of plots inside one stratum; plots without
    measurements are left out by giving them the stratum code `-1`, otherwise
    `ValueError`. A call for `by="type"` without stand types raises
    `ValueError`.
    """
    _check_choice(by, get_args(ClaimKind), "by")
    name = f"permanova_{by}"
    dist = as_condensed_distance(field_dist, name="field_dist", allow_nan=True)
    n = _n_from_condensed(dist.shape[0])
    stra = _strata_or_zeros(strata, n)
    _check_field_dist_for_statistic(dist, stra)
    i, j, d2, plot_stratum = _pairs_inside_strata(dist, stra)
    pick = _by_labels(by, name)

    def func(stand_id: IntArray, stand_type: IntArray | None) -> float:
        return _permanova_core(i, j, d2, plot_stratum, pick(stand_id, stand_type)).f

    return Statistic(name, func, "greater")


# ---------------------------------------------------------------------------
# A5: null models that relabel plots
# ---------------------------------------------------------------------------


@dataclass(frozen=True, eq=False)
class NullDraws:
    """Relabelled plots from a null model. It holds no score.

    `ids[r, i]` is the stand that plot `i` gets in relabelling `r`, and
    `types[r, i]` the type of that stand (`types` is `None` for a map without
    types). Stand and type always move together. `observed_id` and
    `observed_type` are the real labels. `name` is one of `NULL_NAMES`.
    `info` says how the draws were made (counts, acceptance rates); it never
    holds anything about agreement with the field.

    A number only appears when a named, established statistic is computed on
    these draws with `run_test`.
    """

    name: str
    observed_id: IntArray
    observed_type: IntArray | None
    ids: IntArray
    types: IntArray | None
    info: dict[str, Any]

    def __post_init__(self) -> None:
        if self.name not in NULL_NAMES:
            raise ValueError(f"name must be one of {NULL_NAMES}, got {self.name!r}")
        n = self.observed_id.shape[0]
        if self.observed_id.ndim != 1 or self.ids.ndim != 2 or self.ids.shape[1] != n:
            raise ValueError(
                f"ids must have shape (n_draws, {n}) to match observed_id, got {self.ids.shape}"
            )
        if (self.observed_type is None) != (self.types is None):
            raise ValueError("observed_type and types must both be given or both be None")
        if self.types is not None and self.observed_type is not None:
            if self.observed_type.shape != self.observed_id.shape:
                raise ValueError("observed_type must have the shape of observed_id")
            if self.types.shape != self.ids.shape:
                raise ValueError("types must have the shape of ids")

    @property
    def n_draws(self) -> int:
        """Number of relabellings."""
        return int(self.ids.shape[0])


def _check_n_draws(n_draws: int) -> int:
    if isinstance(n_draws, (bool, np.bool_)) or not isinstance(n_draws, (int, np.integer)):
        raise ValueError(f"n_draws must be a whole number, got {n_draws!r}")
    if n_draws < 1:
        raise ValueError(f"n_draws must be at least 1, got {n_draws}")
    return int(n_draws)


def _labels(
    stand_id: npt.ArrayLike, stand_type: npt.ArrayLike | None
) -> tuple[IntArray, IntArray | None]:
    sid = as_codes(stand_id, "stand_id")
    typ = None if stand_type is None else as_codes(stand_type, "stand_type", n=sid.shape[0])
    return sid, typ


def free_permutation(
    stand_id: npt.ArrayLike, stand_type: npt.ArrayLike | None, n_draws: int, seed: Seed
) -> NullDraws:
    """Relabel the plots by shuffling the map's labels over all plots.

    Each relabelling is one uniform random permutation of the plots: plot `i`
    gets the stand AND the type of plot `perm[i]`. The standard permutation
    null of the Mantel, ANOSIM and PERMANOVA tests (Mantel 1967; Clarke 1993;
    Anderson 2001).

    It assumes that any plot could have had any other plot's label. That is
    not true when plots lie in villages that differ, or when nearby plots are
    alike, and then tests built on it reject too often. It is offered to show
    what it does, not as the basis of a claim.

    Returns `NullDraws` named `"free_permutation"` with
    `info = {"n_plots": n}`. It returns no score.

    Degenerate inputs: `n_draws < 1` or malformed codes raise `ValueError`.
    With one plot every draw equals the observed labels. The same seed gives
    the same draws.
    """
    sid, typ = _labels(stand_id, stand_type)
    n_draws = _check_n_draws(n_draws)
    rng = as_generator(seed)
    n = sid.shape[0]
    perm = np.argsort(rng.random((n_draws, n)), axis=1)
    return NullDraws(
        name="free_permutation",
        observed_id=sid,
        observed_type=typ,
        ids=sid[perm],
        types=None if typ is None else typ[perm],
        info={"n_plots": int(n)},
    )


def within_group_permutation(
    stand_id: npt.ArrayLike,
    stand_type: npt.ArrayLike | None,
    groups: npt.ArrayLike,
    n_draws: int,
    seed: Seed,
) -> NullDraws:
    """Relabel the plots by shuffling the map's labels inside each group.

    Each relabelling permutes the plots of every group (village) among
    themselves, uniformly at random and independently between groups: a plot
    gets the stand and the type of a plot of its own group, never of another.
    This is the restricted permutation used with blocked designs (Clarke
    1993; Anderson 2001). It removes differences between villages from the
    null, but it still ignores that nearby plots inside a village are alike.

    Returns `NullDraws` named `"within_group_permutation"` with
    `info = {"n_groups": ..., "group_sizes": [...]}` (sizes in increasing
    group-code order). It returns no score.

    Degenerate inputs: plots with `groups == -1` keep their own labels in
    every draw, and so does the plot of a one-plot group. `n_draws < 1` or
    malformed codes raise `ValueError`. The same seed gives the same draws.
    """
    sid, typ = _labels(stand_id, stand_type)
    n = sid.shape[0]
    grp = as_codes(groups, "groups", n=n)
    n_draws = _check_n_draws(n_draws)
    rng = as_generator(seed)
    source = np.tile(np.arange(n, dtype=np.int64), (n_draws, 1))
    codes = np.unique(grp[grp >= 0])
    sizes: list[int] = []
    for code in codes:
        members = np.flatnonzero(grp == code)
        sizes.append(int(members.shape[0]))
        perm = np.argsort(rng.random((n_draws, members.shape[0])), axis=1)
        source[:, members] = members[perm]
    return NullDraws(
        name="within_group_permutation",
        observed_id=sid,
        observed_type=typ,
        ids=sid[source],
        types=None if typ is None else typ[source],
        info={"n_groups": int(codes.shape[0]), "group_sizes": sizes},
    )


# ---------------------------------------------------------------------------
# A5: the driver
# ---------------------------------------------------------------------------


@dataclass(frozen=True, eq=False)
class TestResult:
    """One established statistic tested against one null model.

    `statistic` and `null` are the two names. `observed` is the statistic on
    the real labels and `p_value` its permutation p-value
    `(b + 1) / (n_valid + 1)`. `n_draws` relabellings were tried and the
    statistic was defined in `n_valid` of them. `null_mean`, `null_sd`
    (n - 1), `null_q05`, `null_q50`, `null_q95` summarise the defined null
    values, and `null_values` holds all of them (`NaN` where not defined).
    """

    __test__: ClassVar[bool] = False  # not a pytest class

    statistic: str
    null: str
    alternative: Alternative
    observed: float
    p_value: float
    n_draws: int
    n_valid: int
    null_mean: float
    null_sd: float
    null_q05: float
    null_q50: float
    null_q95: float
    null_values: FloatArray


def run_test(
    statistic: Statistic, draws: NullDraws, *, min_valid_fraction: float = 0.9
) -> TestResult:
    """Test one named statistic against the relabellings of one null model.

    Formula: the statistic is computed on the observed labels and on each of
    the `R` relabellings in `draws`. With `b` the number of relabellings whose
    value is at least as extreme as the observed one (ties count), in the tail
    the statistic declared when it was built, `p = (b + 1) / (R + 1)`: the
    observed labelling is counted as one of the relabellings, so `p` is never
    0. This is the usual permutation test (as in Mantel 1967, Clarke 1993 and
    Anderson 2001); the null model decides what "chance" keeps fixed.

    Returns a `TestResult`.

    Degenerate inputs: a relabelling where the statistic cannot be computed
    gives `NaN` and is left out of `b` and of `R`. If fewer than
    `min_valid_fraction` of the relabellings are defined, or the observed
    value is `NaN`, no p-value is given (`NaN`): a test that could only be
    run on a selected part of the null is not reported. The summary fields are
    `NaN` when no value is defined (`null_sd` also with fewer than 2).
    """
    if not isinstance(statistic, Statistic):
        raise TypeError("statistic must be a _common.Statistic (a named, established statistic)")
    if not 0.0 <= min_valid_fraction <= 1.0:
        raise ValueError(f"min_valid_fraction must lie in [0, 1], got {min_valid_fraction}")
    observed = statistic(draws.observed_id, draws.observed_type)
    n_draws = draws.n_draws
    null_values = np.full(n_draws, np.nan, dtype=np.float64)
    types = draws.types
    for r in range(n_draws):
        null_values[r] = statistic(draws.ids[r], None if types is None else types[r])
    valid = null_values[~np.isnan(null_values)]
    n_valid = int(valid.shape[0])
    if np.isnan(observed) or n_valid < min_valid_fraction * n_draws:
        p_value = float("nan")
    else:
        p_value = permutation_p_value(observed, null_values, statistic.alternative)
    nan = float("nan")
    with np.errstate(invalid="ignore"):
        mean = float(valid.mean()) if n_valid else nan
        sd = float(valid.std(ddof=1)) if n_valid > 1 else nan
        q05, q50, q95 = (
            (float(q) for q in np.quantile(valid, [0.05, 0.5, 0.95])) if n_valid else (nan,) * 3
        )
    return TestResult(
        statistic=statistic.name,
        null=draws.name,
        alternative=statistic.alternative,
        observed=float(observed),
        p_value=float(p_value),
        n_draws=n_draws,
        n_valid=n_valid,
        null_mean=mean,
        null_sd=sd,
        null_q05=q05,
        null_q50=q50,
        null_q95=q95,
        null_values=null_values,
    )


def run_tests(
    statistics: Sequence[Statistic], draws: NullDraws, *, min_valid_fraction: float = 0.9
) -> pd.DataFrame:
    """Test several statistics against the same relabellings.

    Each statistic goes through `run_test` with the same `draws`. Returns a
    table with one row per statistic, in the order given, holding every field
    of `TestResult` except `null_values`, plus `p_holm`: the p-values of these
    rows after Holm's correction for testing several things at once
    (`holm_adjust`).

    Degenerate inputs: an empty list gives an empty table with the same
    columns. A statistic without a p-value has `p_holm = NaN` and is not
    counted among the tests corrected for.
    """
    columns = [f.name for f in fields(TestResult) if f.name != "null_values"]
    rows = []
    for statistic in statistics:
        result = run_test(statistic, draws, min_valid_fraction=min_valid_fraction)
        rows.append({name: getattr(result, name) for name in columns})
    table = pd.DataFrame(rows, columns=columns)
    table["p_holm"] = holm_adjust(table["p_value"].to_numpy(dtype=np.float64))
    return table


def holm_adjust(p_values: npt.ArrayLike) -> FloatArray:
    """Holm's step-down correction for several tests reported together.

    Formula: sort the `m` p-values in increasing order, multiply the `k`-th
    smallest by `m - k + 1`, make the sequence non-decreasing (running
    maximum) and cap it at 1. A corrected value at or below 0.05 can be
    reported with a family-wise error rate of 0.05, whatever the dependence
    between the tests. Reference: Holm (1979); no Crossref record was found
    for it, so it is UNVERIFIED until the document checks it. It is a
    correction of p-values, not a metric.

    Returns the corrected values in the order of the input.

    Degenerate inputs: `NaN` entries stay `NaN` and are not counted in `m`.
    An empty input gives an empty output. A p-value outside `[0, 1]` raises
    `ValueError`.
    """
    p = np.array(p_values, dtype=np.float64).ravel()
    out = np.full(p.shape[0], np.nan, dtype=np.float64)
    present = ~np.isnan(p)
    values = p[present]
    if ((values < 0) | (values > 1)).any():
        raise ValueError("p-values must lie in [0, 1]")
    m = values.shape[0]
    if m == 0:
        return out
    order = np.argsort(values, kind="stable")
    stepped = values[order] * (m - np.arange(m))
    adjusted = np.minimum(1.0, np.maximum.accumulate(stepped))
    restored = np.empty(m, dtype=np.float64)
    restored[order] = adjusted
    out[present] = restored
    return out

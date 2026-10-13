"""The pair-level comparison of a stand map with field measurements.

For every pair of field plots the map makes one of three claims:

  - the two plots are in the **same stand**;
  - they are in different stands of the **same type**;
  - they are in stands of **different types**.

If the map is useful, two plots it puts together should be more alike in the
field than two plots it keeps apart. "How different in the field" is the
distance between the two plots on their measurements, each measurement first
put on a common scale (`field_distance`).

Two things other than the map make plots alike, and both are held fixed here:

  - **distance**: nearby plots are alike whatever the map says, and plots in
    the same stand are nearly always nearby. So pairs are compared only with
    pairs in the same **distance band**.
  - **village**: villages differ from each other as wholes. Pooling them
    creates differences that vanish inside each one. So pairs are compared
    only inside one **group** (village forest); a pair of plots from two
    groups is never used.

A **stratum** is one group and one distance band. The comparison is made in
every stratum, each stratum is reported, and the strata are pooled with a
declared weight. The distance bands have no default: the caller declares them
before looking at any result.

This module gives the estimate only. Pairs of plots are not independent (267
plots make 35,511 pairs but are still 267 plots), so no p-value is taken from
the pairs. `PairComparison.statistic` hands the estimate to the significance
tests of the package, which relabel plots and recompute it.

Label arguments are integer codes, one per plot, `>= 0`, with `-1` for missing
(see `_common.encode_labels`). Nothing here knows about any site.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, get_args

import numpy as np
import numpy.typing as npt
import pandas as pd
from scipy.spatial.distance import pdist

from fmu.evaluation._common import (
    CLAIM_DIFF_TYPE,
    CLAIM_SAME_STAND,
    CLAIM_SAME_TYPE,
    CLAIM_TYPE_UNKNOWN,
    FloatArray,
    IntArray,
    Statistic,
    as_codes,
    as_condensed_distance,
    as_coords,
    as_float_matrix,
    band_index,
    check_one_type_per_stand,
    pair_claims,
    pair_indices,
    robust_scale,
    validate_band_edges,
)

__all__ = [
    "Contrast",
    "PairComparison",
    "PairComparisonResult",
    "field_distance",
    "geographic_distance",
    "pair_comparison",
]

Contrast = Literal["stand", "type"]

_CONTRASTS: tuple[Contrast, ...] = get_args(Contrast)
_N_CLAIMS = 4  # same stand, same type, different type, type unknown
_CLAIM_NAMES = {
    CLAIM_SAME_STAND: "same_stand",
    CLAIM_SAME_TYPE: "same_type",
    CLAIM_DIFF_TYPE: "diff_type",
    CLAIM_TYPE_UNKNOWN: "type_unknown",
}
STRATA_COLUMNS = [
    "group",
    "band",
    "band_lo",
    "band_hi",
    "n_pairs",
    "n_same_stand",
    "n_same_type",
    "n_diff_type",
    "n_type_unknown",
    "mean_same_stand",
    "mean_same_type",
    "mean_diff_type",
    "mean_type_unknown",
    "effect_stand",
    "weight_stand",
    "effect_type",
    "weight_type",
]
_POOLED_COLUMNS = [
    f"{field}_{c}"
    for c in _CONTRASTS
    for field in ("n_lower", "n_upper", "effect", "weight", "n_strata")
]


# ---------------------------------------------------------------------------
# Distances
# ---------------------------------------------------------------------------


def field_distance(attributes: npt.ArrayLike, *, scale: bool = True) -> FloatArray:
    """How different two plots are in the field, for every pair of plots.

    Formula: each column of `attributes` (one measurement) is centred on its
    median and divided by its interquartile range, `(x - median) / IQR`
    (`_common.robust_scale`, taken over all plots), so that no measurement
    dominates because of its units and a few extreme plots do not set the
    scale. The distance between two plots is then the Euclidean distance
    between their rows, `sqrt(sum_k (x_ik - x_jk)^2)`. One unit is one
    interquartile range on one measurement. This is ordinary practice, not a
    method of one paper; no reference is claimed for it.

    `attributes` has shape `(n, k)`, `k >= 1` (a one-dimensional input is one
    column). `scale=False` skips the scaling, for data that is scaled already.

    Returns a condensed vector of length `n (n - 1) / 2` in the order of
    `scipy.spatial.distance.pdist`.

    Degenerate inputs: a plot with ANY missing measurement (`NaN`) has a `NaN`
    distance to every other plot; no distance is made from the measurements
    that happen to be present. A column whose interquartile range is zero is
    scaled by its standard deviation, and a constant column becomes zeros
    (see `_common.robust_center_scale`). A column with no value at all raises
    `ValueError` when scaling. Fewer than two plots give an empty vector.
    """
    values = as_float_matrix(attributes, "attributes")
    n = values.shape[0]
    if values.shape[1] < 1:
        raise ValueError("attributes needs at least one column")
    if n < 2:
        return np.empty(0, dtype=np.float64)
    if scale:
        values = robust_scale(values)
    incomplete = np.isnan(values).any(axis=1)
    distance = np.asarray(pdist(np.where(incomplete[:, None], 0.0, values)), dtype=np.float64)
    if incomplete.any():
        i, j = pair_indices(n)
        distance[incomplete[i] | incomplete[j]] = np.nan
    return distance


def geographic_distance(coords: npt.ArrayLike) -> FloatArray:
    """Straight-line distance between every pair of plots, in metres.

    Formula: `sqrt((x_i - x_j)^2 + (y_i - y_j)^2)`. `coords` has shape
    `(n, 2)`, x then y, in metres in a projected coordinate system (degrees
    must be projected first).

    Returns a condensed vector in the order of `scipy.spatial.distance.pdist`.
    A missing or infinite coordinate raises `ValueError`. Fewer than two plots
    give an empty vector.
    """
    xy = as_coords(coords)
    if xy.shape[0] < 2:
        return np.empty(0, dtype=np.float64)
    return np.asarray(pdist(xy), dtype=np.float64)


# ---------------------------------------------------------------------------
# The estimator, on per-stratum counts and sums
# ---------------------------------------------------------------------------


def _contrast_terms(
    counts: npt.NDArray[np.int64], sums: FloatArray
) -> tuple[npt.NDArray[np.int64], npt.NDArray[np.int64], FloatArray, FloatArray]:
    """Per stratum: pairs in the lower and upper set, the effect and the weight.

    `counts` and `sums` have shape `(strata, 2)`: the number of pairs and the
    sum of their field distances in the lower set (column 0) and the upper set
    (column 1) of one contrast. The effect is the mean field distance of the
    upper set minus that of the lower set (`NaN` when either set is empty),
    and the weight is `n_lo n_hi / (n_lo + n_hi)` (0 when the effect is not
    defined).
    """
    n_lo, n_hi = counts[:, 0], counts[:, 1]
    defined = (n_lo > 0) & (n_hi > 0)
    effect = np.full(counts.shape[0], np.nan, dtype=np.float64)
    effect[defined] = sums[defined, 1] / n_hi[defined] - sums[defined, 0] / n_lo[defined]
    weight = np.zeros(counts.shape[0], dtype=np.float64)
    weight[defined] = n_lo[defined] * n_hi[defined] / (n_lo[defined] + n_hi[defined])
    return n_lo, n_hi, effect, weight


def _weighted_mean(effect: FloatArray, weight: FloatArray) -> float:
    """`sum_s w_s d_s / sum_s w_s` over the strata where the effect is defined."""
    defined = weight > 0
    if not defined.any():
        return float("nan")
    return float((weight[defined] * effect[defined]).sum() / weight[defined].sum())


def _pooled_effect(counts: npt.NDArray[np.int64], sums: FloatArray) -> float:
    _, _, effect, weight = _contrast_terms(counts, sums)
    return _weighted_mean(effect, weight)


def _pooled_by(
    sets: Mapping[str, tuple[npt.NDArray[np.int64], FloatArray]], index: IntArray, size: int
) -> pd.DataFrame:
    """Pool the strata that share `index` (a band, or a group): one row each.

    `sets[c]` holds the `(counts, sums)` of contrast `c`, as `_contrast_terms`
    takes them.
    """
    columns: dict[str, npt.NDArray] = {}
    for c in _CONTRASTS:
        n_lo, n_hi, effect, weight = _contrast_terms(*sets[c])
        defined = weight > 0
        total_weight = np.bincount(index, weights=weight, minlength=size)
        weighted = np.bincount(
            index[defined], weights=weight[defined] * effect[defined], minlength=size
        )
        pooled = np.full(size, np.nan, dtype=np.float64)
        has = total_weight > 0
        pooled[has] = weighted[has] / total_weight[has]
        columns[f"n_lower_{c}"] = np.bincount(index, weights=n_lo, minlength=size).astype(np.int64)
        columns[f"n_upper_{c}"] = np.bincount(index, weights=n_hi, minlength=size).astype(np.int64)
        columns[f"effect_{c}"] = pooled
        columns[f"weight_{c}"] = total_weight
        columns[f"n_strata_{c}"] = np.bincount(index[defined], minlength=size).astype(np.int64)
    return pd.DataFrame(columns, columns=_POOLED_COLUMNS)


# ---------------------------------------------------------------------------
# The comparison
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PairComparisonResult:
    """The pair table: every stratum, the two poolings, and the pooled effects.

    An effect is the mean field distance of the pairs the map claims to be
    less alike minus that of the pairs it claims to be more alike. Positive
    means the map's claim goes the way the field does. The unit is that of the
    field distance (with `field_distance`: one interquartile range on one
    measurement).
    """

    strata: pd.DataFrame  #: one row per (group, band) that holds a usable pair
    by_band: pd.DataFrame  #: pooled over groups, one row per declared band
    by_group: pd.DataFrame  #: pooled over bands, one row per group
    pooled: dict[str, float]  #: `{"stand": ..., "type": ...}` over all strata
    crude: dict[str, float]  #: the same two contrasts with NO stratification
    n_pairs_used: int  #: pairs that entered the table
    n_strata_used: dict[str, int]  #: strata in which each contrast was estimable


class PairComparison:
    """The map's claim about each pair of plots against their field distance.

    Built once from what the field gives (field distances, coordinates,
    groups, super-groups) and the declared distance bands; then asked about
    any labelling of the plots by the map (`table`, `effect`, `statistic`).

    **Pairs used.** Fixed when the object is built, the same for every
    labelling: pairs `i < j` of plots in the same group (all pairs if `groups`
    is `None`; a plot with group `-1` is in no pair), whose geographic
    distance falls in a declared band, and whose field distance is not `NaN`.
    Of these, a labelling leaves out the pairs in which a plot is in no stand
    (the map makes no claim about them).

    **Strata.** One group and one distance band. Band `b` is the half-open
    range `[band_edges[b], band_edges[b + 1])` in metres.

    **Contrasts.** Two, declared; there are no others.

      - `"stand"`: pairs in the same stand (lower set) against pairs in
        different stands, whatever their types (upper set). "Are two plots in
        the same stand more alike than two plots in different stands, at the
        same distance, in the same village?" This reads the drawing.
      - `"type"`: among pairs in DIFFERENT stands, pairs of the same type
        (lower set) against pairs of different types (upper set). Same-stand
        pairs are not in it, so it reads the labelling and not the drawing a
        second time. Pairs whose types cannot be compared (no types, a stand
        without a type, two super-groups) are in neither set.

    **Estimator.** In stratum `s`, with `n_lo`, `n_hi` the numbers of pairs
    and `m_lo`, `m_hi` the mean field distances of the two sets:

      - effect `d_s = m_hi - m_lo`, defined when both sets hold a pair;
      - weight `w_s = n_lo n_hi / (n_lo + n_hi)`;
      - pooled effect `= sum_s w_s d_s / sum_s w_s` over the strata where the
        effect is defined.

    The weight is the precision of a difference of two means when all pairs
    have the same variance (the usual weight for pooling a difference of means
    over strata), so a stratum with one same-stand pair counts little and a
    balanced stratum counts most. It is a weighting rule, not a variance
    claim: pairs are not independent, which is why significance comes from
    relabelling plots and not from the pairs. No single paper is followed for
    this estimator; it is a stratified difference of means.

    Parameters
    ----------
    field_dist
        Field distance of every pair: a condensed vector in the order of
        `scipy.spatial.distance.pdist`, or a square symmetric matrix. `NaN`
        marks a pair with no distance.
    coords
        Plot coordinates, shape `(n, 2)`, metres, projected.
    band_edges
        Edges of the distance bands in metres, increasing, at least two
        values; only the last may be infinite. Required: there is no default.
    groups
        Code of the group (village forest) of each plot, or `None` for one
        group. In the tables the group is then 0.
    super_group
        Code of the super-group (district) of each plot, or `None`. Stand
        types are compared only inside one super-group. When `groups` is given
        too, each group must lie in one super-group.

    Raises `ValueError` for malformed input (lengths that differ, bad band
    edges, a negative distance, a group that spans two super-groups).
    """

    def __init__(
        self,
        field_dist: npt.ArrayLike,
        coords: npt.ArrayLike,
        band_edges: npt.ArrayLike,
        *,
        groups: npt.ArrayLike | None = None,
        super_group: npt.ArrayLike | None = None,
    ) -> None:
        xy = as_coords(coords)
        n = int(xy.shape[0])
        field = as_condensed_distance(field_dist, n=n, name="field_dist", allow_nan=True)
        edges = validate_band_edges(band_edges)
        group_codes = (
            np.zeros(n, dtype=np.int64) if groups is None else as_codes(groups, "groups", n=n)
        )
        super_codes = None if super_group is None else as_codes(super_group, "super_group", n=n)
        if groups is not None and super_codes is not None:
            in_group = group_codes >= 0
            combos = np.unique(np.stack([group_codes[in_group], super_codes[in_group]]), axis=1)
            spans, n_super = np.unique(combos[0], return_counts=True)
            if (n_super > 1).any():
                raise ValueError(
                    f"{int((n_super > 1).sum())} group(s) lie in more than one super-group "
                    f"(first group code: {int(spans[n_super > 1][0])}); "
                    "each group must lie in one super-group"
                )

        i, j = pair_indices(n)
        band = band_index(geographic_distance(xy), edges) if n >= 2 else np.empty(0, np.int64)
        usable = (band >= 0) & ~np.isnan(field)
        usable &= (group_codes[i] == group_codes[j]) & (group_codes[i] >= 0)

        n_bands = int(edges.shape[0]) - 1
        key = group_codes[i[usable]] * n_bands + band[usable]
        stratum_keys, stratum = np.unique(key, return_inverse=True)

        self.n_plots: int = n
        self.band_edges: FloatArray = edges
        self.n_bands: int = n_bands
        #: Pairs fixed at construction (before any labelling drops "no stand").
        self.n_candidate_pairs: int = int(usable.sum())
        self._i: IntArray = i[usable]
        self._j: IntArray = j[usable]
        self._field: FloatArray = field[usable]
        self._stratum: IntArray = np.asarray(stratum, dtype=np.int64).ravel()
        self._n_strata: int = int(stratum_keys.shape[0])
        self._stratum_group: IntArray = (stratum_keys // n_bands).astype(np.int64)
        self._stratum_band: IntArray = (stratum_keys % n_bands).astype(np.int64)
        self._group_codes: IntArray = np.unique(group_codes[group_codes >= 0])
        self._super: IntArray | None = super_codes

    # -- the inner steps: counts and sums of field distance by stratum

    def _claims(self, stand_id: IntArray, stand_type: IntArray | None) -> npt.NDArray[np.int8]:
        return pair_claims(stand_id, stand_type, self._i, self._j, super_group=self._super)

    def _tabulate(
        self, member: npt.NDArray[np.bool_], column: npt.NDArray, n_columns: int
    ) -> tuple[npt.NDArray[np.int64], FloatArray]:
        """Pairs and summed field distance of the `member` pairs, by stratum and column."""
        key = self._stratum[member] * n_columns + column[member]
        size = self._n_strata * n_columns
        counts = np.bincount(key, minlength=size).reshape(self._n_strata, n_columns)
        sums = np.bincount(key, weights=self._field[member], minlength=size).reshape(
            self._n_strata, n_columns
        )
        return counts.astype(np.int64), sums.astype(np.float64)

    def _contrast_sets(
        self, claims: npt.NDArray[np.int8], contrast: str
    ) -> tuple[npt.NDArray[np.int64], FloatArray]:
        """Per stratum, the lower set (column 0) and the upper set (column 1).

        Each set is summed on its own, in pair order. So the `"stand"` effect
        is the same to the last bit whether or not types are given, and two
        relabellings that make the same sets give the same number.
        """
        if contrast == "stand":
            # Lower: same stand. Upper: every other claim (different stands).
            member = claims >= 0
            upper = claims != CLAIM_SAME_STAND
        else:
            # Lower: different stands of the same type. Upper: of different
            # types. Same-stand pairs and pairs whose types cannot be compared
            # are in neither.
            upper = claims == CLAIM_DIFF_TYPE
            member = upper | (claims == CLAIM_SAME_TYPE)
        return self._tabulate(member, upper, 2)

    def _check_labels(
        self, stand_id: npt.ArrayLike, stand_type: npt.ArrayLike | None
    ) -> tuple[IntArray, IntArray | None]:
        sid = as_codes(stand_id, "stand_id", n=self.n_plots)
        typ = None if stand_type is None else as_codes(stand_type, "stand_type", n=self.n_plots)
        return sid, typ

    def _effect(self, stand_id: IntArray, stand_type: IntArray | None, contrast: str) -> float:
        claims = self._claims(stand_id, stand_type)
        return _pooled_effect(*self._contrast_sets(claims, contrast))

    # -- public

    def effect(
        self,
        stand_id: npt.ArrayLike,
        stand_type: npt.ArrayLike | None = None,
        contrast: Contrast = "stand",
    ) -> float:
        """The pooled effect of one contrast, without building the tables.

        Formula: `sum_s w_s d_s / sum_s w_s` over strata (group x distance
        band), `d_s` the mean field distance of the upper set minus that of
        the lower set and `w_s = n_lo n_hi / (n_lo + n_hi)`; see the class
        docstring for the two contrasts. Equal to
        `table(stand_id, stand_type).pooled[contrast]`.

        `stand_id` and `stand_type` are integer codes, one per plot, `-1` for
        "in no stand" and "no type". Stand codes must be unique over the whole
        data set.

        Returns `NaN` when no stratum holds a pair in both sets: for `"type"`
        that includes `stand_type=None`. Raises `ValueError` for an unknown
        contrast or malformed codes.
        """
        if contrast not in _CONTRASTS:
            raise ValueError(f"contrast must be one of {_CONTRASTS}, got {contrast!r}")
        sid, typ = self._check_labels(stand_id, stand_type)
        return self._effect(sid, typ, contrast)

    def statistic(self, contrast: Contrast) -> Statistic:
        """The pooled effect as a `Statistic` for the significance tests.

        Named `"pair_stand"` or `"pair_type"`, declared tail `"greater"`
        (a useful map makes the pairs it puts together more alike). Its value
        for a relabelling of the plots is `effect(stand_id, stand_type,
        contrast)`, `NaN` where that is not estimable. The relabelled codes
        are taken as already checked and are not modified.

        Raises `ValueError` for an unknown contrast.
        """
        if contrast not in _CONTRASTS:
            raise ValueError(f"contrast must be one of {_CONTRASTS}, got {contrast!r}")

        def func(stand_id: IntArray, stand_type: IntArray | None) -> float:
            return self._effect(stand_id, stand_type, contrast)

        return Statistic(f"pair_{contrast}", func, "greater")

    def table(
        self, stand_id: npt.ArrayLike, stand_type: npt.ArrayLike | None = None
    ) -> PairComparisonResult:
        """The full pair table for one labelling of the plots by the map.

        Formula: see the class docstring (effect `d_s = m_hi - m_lo` per
        stratum, weight `w_s = n_lo n_hi / (n_lo + n_hi)`, pooled effect
        `sum w_s d_s / sum w_s`).

        Returns a `PairComparisonResult`:

          - `strata`: one row per (group, band) that holds at least one of the
            pairs fixed when the object was built, sorted by group then band,
            so the rows are the same for every labelling. Columns: `group,
            band, band_lo, band_hi, n_pairs, n_same_stand, n_same_type,
            n_diff_type, n_type_unknown, mean_same_stand, mean_same_type,
            mean_diff_type, mean_type_unknown, effect_stand, weight_stand,
            effect_type, weight_type`. `n_pairs` counts the pairs the map
            makes a claim about; a mean is `NaN` where its count is 0.
          - `by_band`: one row per declared band, pooled over groups with the
            same weights: `band, band_lo, band_hi`, then for each contrast `c`
            `n_lower_c, n_upper_c` (pairs in the two sets, all strata of the
            band), `effect_c`, `weight_c` (summed weight) and `n_strata_c`
            (strata where the effect is defined).
          - `by_group`: one row per group code, pooled over bands: `group` and
            the same columns.
          - `pooled`: the pooled effect of each contrast over all strata.
          - `crude`: mean of the upper set minus mean of the lower set over
            all used pairs taken as ONE stratum. Shown beside `pooled` so a
            reader sees what holding distance and village fixed removed.
          - `n_pairs_used`: pairs with a claim (the sum of `n_pairs`).
          - `n_strata_used`: strata in which each contrast was estimable.

        Degenerate inputs: an effect is `NaN` and its weight 0 where either
        set is empty; a pooled value is `NaN` when no stratum is estimable.
        `stand_type=None` gives `NaN` for everything about `"type"`. Raises
        `ValueError` for malformed codes or a stand that carries two types.
        """
        sid, typ = self._check_labels(stand_id, stand_type)
        if typ is not None:
            check_one_type_per_stand(sid, typ)
        claims = self._claims(sid, typ)
        counts, sums = self._tabulate(claims >= 0, claims, _N_CLAIMS)
        sets: dict[str, tuple[npt.NDArray[np.int64], FloatArray]] = {
            c: self._contrast_sets(claims, c) for c in _CONTRASTS
        }

        strata = pd.DataFrame(
            {
                "group": self._stratum_group,
                "band": self._stratum_band,
                "band_lo": self.band_edges[self._stratum_band],
                "band_hi": self.band_edges[self._stratum_band + 1],
                "n_pairs": counts.sum(axis=1),
            }
        )
        means = np.where(counts > 0, sums / np.where(counts > 0, counts, 1), np.nan)
        for claim, name in _CLAIM_NAMES.items():
            strata[f"n_{name}"] = counts[:, claim]
        for claim, name in _CLAIM_NAMES.items():
            strata[f"mean_{name}"] = means[:, claim]
        n_strata_used: dict[str, int] = {}
        pooled: dict[str, float] = {}
        crude: dict[str, float] = {}
        for c in _CONTRASTS:
            set_counts, set_sums = sets[c]
            _, _, effect, weight = _contrast_terms(set_counts, set_sums)
            strata[f"effect_{c}"] = effect
            strata[f"weight_{c}"] = weight
            n_strata_used[c] = int((weight > 0).sum())
            pooled[c] = _weighted_mean(effect, weight)
            # All used pairs as one stratum.
            crude[c] = float(
                _contrast_terms(
                    set_counts.sum(axis=0, keepdims=True), set_sums.sum(axis=0, keepdims=True)
                )[2][0]
            )
        strata = strata[STRATA_COLUMNS]

        bands = np.arange(self.n_bands, dtype=np.int64)
        by_band = _pooled_by(sets, self._stratum_band, self.n_bands)
        by_band.insert(0, "band_hi", self.band_edges[bands + 1])
        by_band.insert(0, "band_lo", self.band_edges[bands])
        by_band.insert(0, "band", bands)

        group_position = np.searchsorted(self._group_codes, self._stratum_group)
        by_group = _pooled_by(
            sets, group_position.astype(np.int64), int(self._group_codes.shape[0])
        )
        by_group.insert(0, "group", self._group_codes)

        return PairComparisonResult(
            strata=strata,
            by_band=by_band,
            by_group=by_group,
            pooled=pooled,
            crude=crude,
            n_pairs_used=int(counts.sum()),
            n_strata_used=n_strata_used,
        )


def pair_comparison(
    attributes: npt.ArrayLike,
    coords: npt.ArrayLike,
    stand_id: npt.ArrayLike,
    stand_type: npt.ArrayLike | None,
    band_edges: npt.ArrayLike,
    *,
    groups: npt.ArrayLike | None = None,
    super_group: npt.ArrayLike | None = None,
    scale: bool = True,
) -> PairComparisonResult:
    """The pair table straight from measurements, coordinates and the map.

    A convenience for one labelling: `field_distance(attributes, scale=scale)`
    (robust-scaled Euclidean distance between plots), then
    `PairComparison(field distance, coords, band_edges, groups=groups,
    super_group=super_group).table(stand_id, stand_type)`. The formulas, the
    two contrasts and the returned tables are described there. To test an
    effect against chance, build a `PairComparison` and use its `statistic`.

    `attributes` is `(n, k)`; `coords` is `(n, 2)` in projected metres;
    `stand_id`, `stand_type` (or `None`), `groups` and `super_group` are
    integer codes, one per plot, `-1` for missing. `band_edges` is required.

    Degenerate inputs: a plot with a missing measurement is in no pair; a plot
    in no stand is in no pair; effects that cannot be estimated are `NaN`.
    Malformed input raises `ValueError`.
    """
    comparison = PairComparison(
        field_distance(attributes, scale=scale),
        coords,
        band_edges,
        groups=groups,
        super_group=super_group,
    )
    return comparison.table(stand_id, stand_type)

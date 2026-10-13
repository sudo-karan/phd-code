"""Shared helpers for `fmu.evaluation`.

Small, dependency-light pieces that every module of the package needs, kept in
one place so that the modules agree on them:

  - **random numbers**: every random procedure takes an explicit seed or numpy
    `Generator`. There is no global random state anywhere in the package.
  - **labels**: any kind of label (numbers, strings, with gaps) becomes integer
    codes `0..k-1`, and a missing label is always `-1` (`MISSING`). Every other
    function of the package takes these codes, never raw labels, so the caller
    encodes once with `encode_labels` and "missing" means one thing everywhere.
  - **robust scaling**: centre on the median, scale by the interquartile range,
    with a stated behaviour when the interquartile range is zero.
  - **pairs**: one ordering of the `n (n - 1) / 2` pairs of plots, the same as
    `scipy.spatial.distance.pdist`, so a "condensed" vector means the same thing
    in every module.
  - **distance bands**: half-open bands `[lo, hi)` in metres.
  - **pair claims**: what the map says about a pair of plots (same stand;
    different stand but same type; different type).
  - **the permutation p-value**: `(b + 1) / (n + 1)`, the observed value counted
    among the permutations.
  - **`Statistic`**: the one contract between a statistic and the code that
    tests it. A statistic reads the map's labels of the plots and returns a
    number. Chance is always simulated by relabelling plots, never pairs.

Nothing here knows about any site. Inputs are arrays.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Literal, get_args

import numpy as np
import numpy.typing as npt
import pandas as pd

IntArray = npt.NDArray[np.int64]
FloatArray = npt.NDArray[np.float64]
BoolArray = npt.NDArray[np.bool_]

Alternative = Literal["greater", "less", "two-sided"]
Seed = int | np.integer | np.random.Generator | np.random.SeedSequence

#: Integer code of a missing label (a plot in no stand, a stand with no type).
MISSING = -1

# What the map claims about a pair of plots. The order 0 < 1 < 2 is the order of
# the claim: from "the same piece of forest" to "a different kind of forest".
CLAIM_NONE = -1  #: no claim: at least one of the two plots is in no stand
CLAIM_SAME_STAND = 0  #: both plots are in the same stand
CLAIM_SAME_TYPE = 1  #: different stands of the same type
CLAIM_DIFF_TYPE = 2  #: different stands of different types
CLAIM_TYPE_UNKNOWN = 3  #: different stands whose types cannot be compared

# Two values closer than this count as tied when a p-value is counted. Without
# it a relabelling that reproduces the observed grouping can differ from the
# observed value in the last bit and be counted as "less extreme".
P_VALUE_ATOL = 1e-12
P_VALUE_RTOL = 1e-9


# ---------------------------------------------------------------------------
# Random numbers
# ---------------------------------------------------------------------------


def as_generator(seed: Seed) -> np.random.Generator:
    """Return a numpy `Generator` for an explicit seed.

    An existing `Generator` is returned as it is (and will be advanced by the
    caller's draws). `None` is refused on purpose: an unseeded run cannot be
    repeated.
    """
    if isinstance(seed, np.random.Generator):
        return seed
    if isinstance(seed, np.random.SeedSequence):
        return np.random.default_rng(seed)
    if isinstance(seed, (bool, np.bool_)) or not isinstance(seed, (int, np.integer)):
        raise TypeError(
            "seed must be an int, a numpy Generator or a SeedSequence; "
            f"got {type(seed).__name__}. None (an unseeded run) is not allowed."
        )
    if seed < 0:
        raise ValueError(f"seed must be non-negative, got {seed}")
    return np.random.default_rng(int(seed))


def child_generators(seed: Seed, n: int) -> list[np.random.Generator]:
    """Return `n` independent generators derived from one seed.

    Use one child per unit of work (a replicate, a group of plots), so that the
    numbers a unit draws do not depend on how many other units there are or on
    the order they run in. With an int seed, child `k` is the same whatever `n`
    is. With a `Generator` or a `SeedSequence` the children are spawned from it,
    so a second call returns new children.
    """
    if isinstance(n, (bool, np.bool_)) or not isinstance(n, (int, np.integer)) or n < 0:
        raise ValueError(f"n must be a non-negative integer, got {n!r}")
    if isinstance(seed, np.random.Generator):
        return list(seed.spawn(int(n)))
    if isinstance(seed, np.random.SeedSequence):
        return [np.random.default_rng(s) for s in seed.spawn(int(n))]
    if isinstance(seed, (bool, np.bool_)) or not isinstance(seed, (int, np.integer)):
        raise TypeError(
            "seed must be an int, a numpy Generator or a SeedSequence; "
            f"got {type(seed).__name__}. None (an unseeded run) is not allowed."
        )
    if seed < 0:
        raise ValueError(f"seed must be non-negative, got {seed}")
    return [np.random.default_rng(s) for s in np.random.SeedSequence(int(seed)).spawn(int(n))]


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def common_length(**arrays: Any) -> int:
    """Return the shared first-axis length of the named arrays.

    Entries that are `None` are skipped. Raises `ValueError`, naming the
    arguments, when two lengths differ or when nothing was given.
    """
    lengths = {name: len(a) for name, a in arrays.items() if a is not None}
    if not lengths:
        raise ValueError("no array was given")
    if len(set(lengths.values())) > 1:
        raise ValueError(f"arrays differ in length: {lengths}")
    return next(iter(lengths.values()))


def as_float_matrix(
    values: npt.ArrayLike,
    name: str = "values",
    *,
    n_rows: int | None = None,
    allow_nan: bool = True,
) -> FloatArray:
    """Return `values` as a float64 array of shape `(n, k)`.

    A one-dimensional input becomes one column. Infinite values are refused.
    `NaN` marks a missing value and is refused when `allow_nan` is false.
    """
    arr = np.array(values, dtype=np.float64)
    if arr.ndim == 1:
        arr = arr.reshape(-1, 1)
    if arr.ndim != 2:
        raise ValueError(f"{name} must have one or two dimensions, got shape {arr.shape}")
    if n_rows is not None and arr.shape[0] != n_rows:
        raise ValueError(f"{name} has {arr.shape[0]} rows, expected {n_rows}")
    if np.isinf(arr).any():
        raise ValueError(f"{name} holds an infinite value")
    if not allow_nan and np.isnan(arr).any():
        raise ValueError(f"{name} holds a missing value (NaN)")
    return arr


def as_coords(coords: npt.ArrayLike, name: str = "coords", *, n_rows: int | None = None) -> FloatArray:
    """Return plot coordinates as a finite float64 array of shape `(n, 2)`.

    Coordinates are x then y, in metres, in a projected coordinate system.
    Distances and rotations are only meaningful in metres, so degrees must be
    projected by the caller first.
    """
    arr = np.array(coords, dtype=np.float64)
    if arr.ndim != 2 or arr.shape[1] != 2:
        raise ValueError(f"{name} must have shape (n, 2), got {arr.shape}")
    if n_rows is not None and arr.shape[0] != n_rows:
        raise ValueError(f"{name} has {arr.shape[0]} rows, expected {n_rows}")
    if not np.isfinite(arr).all():
        raise ValueError(f"{name} holds a missing or infinite coordinate")
    return arr


def as_codes(
    codes: npt.ArrayLike, name: str = "codes", *, n: int | None = None, allow_missing: bool = True
) -> IntArray:
    """Return label codes as a one-dimensional int64 array, checked.

    Codes are whole numbers `>= 0`, with `-1` for a missing label, as
    `encode_labels` returns them. Floats that are whole numbers are accepted
    (a column read from a table); anything else raises `ValueError`: `NaN`,
    fractions, strings, a value below `-1`, a wrong length, or a `-1` when
    `allow_missing` is false. Raw labels go through `encode_labels` first.
    """
    arr = np.asarray(codes)
    if arr.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional, got shape {arr.shape}")
    if arr.dtype == np.bool_ or not (
        np.issubdtype(arr.dtype, np.integer) or np.issubdtype(arr.dtype, np.floating)
    ):
        raise ValueError(
            f"{name} must hold integer codes (see encode_labels), got dtype {arr.dtype}"
        )
    if np.issubdtype(arr.dtype, np.floating) and not (
        np.isfinite(arr).all() and (arr == np.floor(arr)).all()
    ):
        raise ValueError(f"{name} must hold whole numbers; use encode_labels for raw labels")
    out = arr.astype(np.int64)
    if n is not None and out.shape[0] != n:
        raise ValueError(f"{name} has {out.shape[0]} values, expected {n}")
    if (out < MISSING).any():
        raise ValueError(f"{name} holds a code below -1")
    if not allow_missing and (out == MISSING).any():
        raise ValueError(f"{name} holds a missing label (-1)")
    return out


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------


def encode_labels(labels: npt.ArrayLike, *, missing: Iterable[Any] = ()) -> tuple[IntArray, np.ndarray]:
    """Turn labels of any kind into integer codes.

    Returns `(codes, classes)`. `codes[i]` is the position of `labels[i]` in
    `classes`, which holds the distinct labels in sorted order, so the codes run
    `0..k-1`. A missing label gets the code `-1`: `None`, `NaN`, and any value
    listed in `missing` (for example `missing=(-1,)` for a table that writes
    "no stand" as -1). Labels must be of one kind, all numbers or all strings;
    a mix raises `ValueError`, because `1` and `"1"` would become two groups.
    """
    arr = np.asarray(labels)
    if arr.ndim != 1:
        raise ValueError(f"labels must be one-dimensional, got shape {arr.shape}")
    is_missing = np.asarray(pd.isna(arr), dtype=bool)
    extra = list(missing)
    if extra:
        is_missing |= np.isin(arr, extra)
    present = arr[~is_missing]
    if present.dtype == object and len({isinstance(v, str) for v in present.tolist()}) > 1:
        raise ValueError("labels mix strings with other kinds; make them one kind first")
    try:
        present_codes, classes = pd.factorize(present, sort=True)
    except TypeError as exc:
        raise ValueError("labels cannot be put in order; make them one kind first") from exc
    codes = np.full(arr.shape[0], MISSING, dtype=np.int64)
    codes[~is_missing] = present_codes
    return codes, np.asarray(classes)


def combine_labels(*labels: npt.ArrayLike) -> IntArray:
    """Codes for the combination of several label arrays.

    Two plots get the same code only when they agree on every array, and a plot
    with a missing label in any array is missing (`-1`). Codes run `0..k-1` in
    the sorted order of the combinations (first array first).

    Use it wherever a number means a different thing in each larger unit: stand
    ids that restart in each district become unique with
    `combine_labels(district, stand_id)`, and a stratum crossed with a group is
    `combine_labels(stratum, group)`.
    """
    if not labels:
        raise ValueError("at least one label array is needed")
    encoded = [encode_labels(a)[0] for a in labels]
    common_length(**{f"labels[{k}]": c for k, c in enumerate(encoded)})
    present = np.ones(encoded[0].shape[0], dtype=bool)
    for c in encoded:
        present &= c >= 0
    key = np.zeros(encoded[0].shape[0], dtype=np.int64)
    for c in encoded:
        key = key * (int(c.max(initial=0)) + 1) + np.where(present, c, 0)
    codes = np.full(key.shape[0], MISSING, dtype=np.int64)
    codes[present] = np.unique(key[present], return_inverse=True)[1]
    return codes


def check_one_type_per_stand(stand_id: npt.ArrayLike, stand_type: npt.ArrayLike) -> None:
    """Raise `ValueError` if plots of one stand carry different types.

    Both arguments are integer codes with `-1` for missing. A stand has one
    type, so two plots that share a stand must share its type (or both have
    none). Plots in no stand are ignored.
    """
    sid = as_codes(stand_id, "stand_id")
    typ = as_codes(stand_type, "stand_type", n=sid.shape[0])
    in_stand = sid >= 0
    combos = np.unique(np.stack([sid[in_stand], typ[in_stand]]), axis=1)
    stands, n_types = np.unique(combos[0], return_counts=True)
    if (n_types > 1).any():
        raise ValueError(
            f"{int((n_types > 1).sum())} stand(s) carry more than one type among their plots "
            f"(first stand code: {int(stands[n_types > 1][0])}); a stand has one type"
        )


# ---------------------------------------------------------------------------
# Robust scaling
# ---------------------------------------------------------------------------


def robust_center_scale(values: npt.ArrayLike) -> tuple[FloatArray, FloatArray]:
    """Median and spread of each column, as used by `robust_scale`.

    Returns `(center, scale)`, each of shape `(k,)`. The centre is the median.
    The scale is the interquartile range (75th minus 25th percentile, linear
    interpolation). Missing values (`NaN`) are left out of both.

    When the interquartile range of a column is zero (more than half of the
    values are equal, for example a count that is mostly 0), dividing by it is
    impossible, so the scale falls back to the standard deviation (n - 1 in the
    denominator). When that is zero too (a constant column) the scale is 1, and
    the scaled column is all zeros: a constant measurement separates no plots.
    """
    arr = as_float_matrix(values, "values")
    if arr.shape[0] == 0:
        raise ValueError("values has no rows")
    finite = ~np.isnan(arr)
    if not finite.any(axis=0).all():
        empty = np.flatnonzero(~finite.any(axis=0))
        raise ValueError(f"column(s) {empty.tolist()} of values hold no value at all")
    center = np.nanmedian(arr, axis=0)
    q75, q25 = np.nanpercentile(arr, [75.0, 25.0], axis=0)
    scale = np.asarray(q75 - q25, dtype=np.float64)
    spread = np.zeros(arr.shape[1], dtype=np.float64)
    several = finite.sum(axis=0) > 1
    if several.any():
        spread[several] = np.nanstd(arr[:, several], axis=0, ddof=1)
    use_spread = ~(scale > 0)
    scale = np.where(use_spread, spread, scale)
    scale = np.where(scale > 0, scale, 1.0)
    return np.asarray(center, dtype=np.float64), scale


def robust_scale(values: npt.ArrayLike) -> FloatArray:
    """Centre each column on its median and divide by its interquartile range.

    `(x - median) / IQR`, column by column, so that no measurement dominates a
    distance because of its units and a few extreme plots do not set the scale.
    Returns an array of shape `(n, k)`; a missing value stays missing. See
    `robust_center_scale` for the zero-range rule.
    """
    arr = as_float_matrix(values, "values")
    center, scale = robust_center_scale(arr)
    return (arr - center) / scale


# ---------------------------------------------------------------------------
# Pairs
# ---------------------------------------------------------------------------


def n_pairs(n: int) -> int:
    """Number of unordered pairs among `n` items: `n (n - 1) / 2`."""
    if n < 0:
        raise ValueError(f"n must be non-negative, got {n}")
    return n * (n - 1) // 2


def pair_indices(n: int) -> tuple[IntArray, IntArray]:
    """Indices `(i, j)`, `i < j`, of every pair among `n` items.

    The order is that of `scipy.spatial.distance.pdist`: (0, 1), (0, 2), ...,
    (0, n-1), (1, 2), ... Every "condensed" vector in the package uses it.
    """
    if n < 0:
        raise ValueError(f"n must be non-negative, got {n}")
    i, j = np.triu_indices(n, k=1)
    return i.astype(np.int64), j.astype(np.int64)


def condensed_index(i: npt.ArrayLike, j: npt.ArrayLike, n: int) -> IntArray:
    """Position of the pair `(i, j)` in a condensed vector of `n` items.

    The order of `i` and `j` does not matter. `i == j` is not a pair and raises.
    """
    a = np.asarray(i, dtype=np.int64)
    b = np.asarray(j, dtype=np.int64)
    lo, hi = np.minimum(a, b), np.maximum(a, b)
    if (lo < 0).any() or (hi >= n).any():
        raise ValueError(f"indices must lie in 0..{n - 1}")
    if (lo == hi).any():
        raise ValueError("i == j is not a pair")
    return np.asarray(n * lo - lo * (lo + 1) // 2 + (hi - lo - 1), dtype=np.int64)


def as_condensed_distance(
    distance: npt.ArrayLike,
    *,
    n: int | None = None,
    name: str = "distance",
    allow_nan: bool = False,
) -> FloatArray:
    """Return a distance matrix as a condensed float64 vector.

    Accepts either a condensed vector (length `n (n - 1) / 2`, the order of
    `pair_indices`) or a square symmetric matrix with a zero diagonal. Distances
    must be non-negative and finite. `NaN` (a pair with no distance) is refused
    unless `allow_nan` is true.
    """
    arr = np.array(distance, dtype=np.float64)
    if arr.ndim == 2:
        if arr.shape[0] != arr.shape[1]:
            raise ValueError(f"{name} is two-dimensional but not square: {arr.shape}")
        size = arr.shape[0]
        scale = float(np.nanmax(np.abs(arr))) if arr.size and not np.isnan(arr).all() else 0.0
        tol = 1e-9 * max(scale, 1.0)
        if not np.allclose(arr, arr.T, rtol=0.0, atol=tol, equal_nan=True):
            raise ValueError(f"{name} is not symmetric")
        if (np.abs(np.nan_to_num(np.diag(arr))) > tol).any():
            raise ValueError(f"{name} has a non-zero diagonal")
        arr = arr[np.triu_indices(size, k=1)]
    elif arr.ndim == 1:
        size = int(round((1 + np.sqrt(1 + 8 * arr.shape[0])) / 2))
        if n_pairs(size) != arr.shape[0]:
            raise ValueError(f"{name} has {arr.shape[0]} values, which is not n (n - 1) / 2 for any n")
    else:
        raise ValueError(f"{name} must be a condensed vector or a square matrix, got shape {arr.shape}")
    if n is not None and size != n:
        raise ValueError(f"{name} is for {size} items, expected {n}")
    if np.isinf(arr).any():
        raise ValueError(f"{name} holds an infinite value")
    if not allow_nan and np.isnan(arr).any():
        raise ValueError(f"{name} holds a missing value (NaN)")
    if (arr < 0).any():
        raise ValueError(f"{name} holds a negative value")
    return arr


# ---------------------------------------------------------------------------
# Distance bands
# ---------------------------------------------------------------------------


def validate_band_edges(edges: npt.ArrayLike) -> FloatArray:
    """Check and return the edges of distance bands, in metres.

    `edges` holds at least two values, starts at 0 or above and increases
    strictly. Band `b` is the half-open range `[edges[b], edges[b + 1])`. Only
    the last edge may be infinite, which makes the last band open-ended.
    """
    arr = np.array(edges, dtype=np.float64)
    if arr.ndim != 1 or arr.shape[0] < 2:
        raise ValueError("band edges must be a one-dimensional sequence of at least two values")
    if np.isnan(arr).any() or np.isinf(arr[:-1]).any():
        raise ValueError("band edges must be numbers; only the last may be infinite")
    if arr[0] < 0:
        raise ValueError("band edges must start at 0 or above")
    if (np.diff(arr) <= 0).any():
        raise ValueError("band edges must increase strictly")
    return arr


def band_index(distance: npt.ArrayLike, edges: npt.ArrayLike) -> IntArray:
    """Band of each distance: `b` such that `edges[b] <= distance < edges[b + 1]`.

    Returns `-1` for a distance below the first edge, at or above the last
    edge, or missing (`NaN`). A distance exactly on an edge belongs to the band
    that starts there.
    """
    arr = validate_band_edges(edges)
    dist = np.asarray(distance, dtype=np.float64)
    band = np.asarray(np.searchsorted(arr, dist, side="right") - 1, dtype=np.int64)
    outside = np.isnan(dist) | (dist < arr[0]) | (dist >= arr[-1])
    return np.where(outside, MISSING, band).astype(np.int64)


# ---------------------------------------------------------------------------
# What the map claims about a pair of plots
# ---------------------------------------------------------------------------


def pair_claims(
    stand_id: npt.ArrayLike,
    stand_type: npt.ArrayLike | None,
    i: npt.ArrayLike,
    j: npt.ArrayLike,
    *,
    super_group: npt.ArrayLike | None = None,
) -> npt.NDArray[np.int8]:
    """The map's claim about each pair of plots `(i[k], j[k])`.

    `stand_id`, `stand_type` and `super_group` are integer codes, one per plot,
    with `-1` for missing. Stand codes must be unique over the whole data set.

    Returns one code per pair:

      - `CLAIM_NONE` (-1): at least one plot is in no stand. No claim is made.
      - `CLAIM_SAME_STAND` (0): the two plots are in the same stand.
      - `CLAIM_SAME_TYPE` (1): different stands that have the same type.
      - `CLAIM_DIFF_TYPE` (2): different stands that have different types.
      - `CLAIM_TYPE_UNKNOWN` (3): different stands whose types cannot be
        compared: `stand_type` is `None`, one of the two stands has no type, or
        the plots are in different super-groups. Stand types are fitted
        separately in each super-group (district), so a type number means a
        different forest in each one.
    """
    sid = np.asarray(stand_id, dtype=np.int64)
    a = np.asarray(i, dtype=np.int64)
    b = np.asarray(j, dtype=np.int64)
    sa, sb = sid[a], sid[b]
    claims = np.full(a.shape, CLAIM_TYPE_UNKNOWN, dtype=np.int8)
    if stand_type is not None:
        typ = np.asarray(stand_type, dtype=np.int64)
        common_length(stand_id=sid, stand_type=typ)
        ta, tb = typ[a], typ[b]
        comparable = (ta >= 0) & (tb >= 0)
        if super_group is not None:
            sup = np.asarray(super_group, dtype=np.int64)
            common_length(stand_id=sid, super_group=sup)
            comparable &= (sup[a] == sup[b]) & (sup[a] >= 0)
        claims[comparable & (ta == tb)] = CLAIM_SAME_TYPE
        claims[comparable & (ta != tb)] = CLAIM_DIFF_TYPE
    claims[sa == sb] = CLAIM_SAME_STAND
    claims[(sa < 0) | (sb < 0)] = CLAIM_NONE
    return claims


# ---------------------------------------------------------------------------
# Significance
# ---------------------------------------------------------------------------


def permutation_p_value(observed: float, null_values: npt.ArrayLike, alternative: Alternative) -> float:
    """Permutation p-value with the observed value counted among the permutations.

    `p = (b + 1) / (n + 1)`, where `n` is the number of null values that are
    defined (not `NaN`) and `b` is how many of them are at least as extreme as
    the observed value:

      - `"greater"`: `b` counts null values `>= observed`;
      - `"less"`: `b` counts null values `<= observed`;
      - `"two-sided"`: twice the smaller of the two one-sided p-values, capped
        at 1. It does not assume that chance is centred on zero, which matters
        here because a map that knows nothing about the forest can still score
        above zero.

    Ties count as "at least as extreme", with a small tolerance
    (`P_VALUE_ATOL + P_VALUE_RTOL * |observed|`). The smallest possible value is
    `1 / (n + 1)`, never zero. Returns `NaN` when the observed value is `NaN`
    or when no null value is defined.
    """
    if alternative not in get_args(Alternative):
        raise ValueError(f"alternative must be one of {get_args(Alternative)}, got {alternative!r}")
    obs = float(observed)
    null = np.asarray(null_values, dtype=np.float64).ravel()
    null = null[~np.isnan(null)]
    if np.isnan(obs) or null.size == 0:
        return float("nan")
    tol = 0.0 if np.isinf(obs) else P_VALUE_ATOL + P_VALUE_RTOL * abs(obs)
    p_greater = (int((null >= obs - tol).sum()) + 1) / (null.size + 1)
    p_less = (int((null <= obs + tol).sum()) + 1) / (null.size + 1)
    if alternative == "greater":
        return p_greater
    if alternative == "less":
        return p_less
    return min(1.0, 2.0 * min(p_greater, p_less))


@dataclass(frozen=True)
class Statistic:
    """An established statistic, ready to be tested against chance.

    `func(stand_id, stand_type)` reads what the map says about each plot and
    returns one number. Everything from the field (types, measurements,
    coordinates, villages) is fixed inside `func` when the statistic is built.
    `stand_id` and `stand_type` are integer codes, one per plot in the caller's
    plot order, with `-1` for "no stand" and "no type"; `stand_type` is `None`
    for a map without types.

    This is the only thing a significance test accepts. A test relabels the
    PLOTS (by permuting them, or by moving them over the map) and calls the
    statistic again, so pairs of plots are never treated as independent, and a
    p-value always belongs to a named statistic. No null model returns a score
    of its own.

    `alternative` is the tail declared for this statistic, fixed when it is
    built and not chosen after seeing a result.
    """

    name: str
    func: Callable[[IntArray, IntArray | None], float]
    alternative: Alternative

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("a statistic needs a name")
        if self.alternative not in get_args(Alternative):
            raise ValueError(
                f"alternative must be one of {get_args(Alternative)}, got {self.alternative!r}"
            )

    def __call__(self, stand_id: IntArray, stand_type: IntArray | None = None) -> float:
        return float(self.func(stand_id, stand_type))

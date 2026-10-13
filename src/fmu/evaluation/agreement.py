"""Rand index and adjusted Rand index between two groupings of the same plots.

Two groupings of the plots are compared by looking at every PAIR of plots and
asking whether the two groupings agree about it: both put the two plots
together, or both keep them apart. The Rand index is the share of pairs on
which they agree (Rand 1971). The adjusted Rand index subtracts the agreement
that two unrelated groupings with the same group sizes would reach by chance
(Hubert and Arabie 1985): 0 means "no better than chance", 1 means "the same
grouping".

Used here for two questions about a stand map, with field plots:

  - **the drawing**: field type against stand (`drawing_statistic`);
  - **the labelling**: field type against stand type, worked out inside each
    district and pooled over districts by pair counts (`stratified_agreement`,
    `labelling_statistic`). Stand types are fitted separately in each district,
    so a type number means a different forest in each one and plots of two
    districts are never compared.

Every grouping argument is an array of integer codes, one per plot, `>= 0`,
with `-1` for a missing label (see `_common.encode_labels`). A plot with a
missing label in either grouping is left out. Label values do not matter, only
which plots share one.

Notation used in the docstrings. Among the `n` plots used there are
`N = n (n - 1) / 2` pairs, of which

  - `T` are together in both groupings,
  - `P` are together in the first grouping (`a`),
  - `Q` are together in the second grouping (`b`).

All counts are exact whole numbers; no pair matrix is built.

Nothing here knows about any site. Inputs are arrays.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

import numpy as np
import numpy.typing as npt
import pandas as pd

from fmu.evaluation._common import IntArray, Statistic, as_codes

__all__ = [
    "AgreementResult",
    "PairCounts",
    "StratifiedAgreement",
    "adjusted_rand_index",
    "agreement",
    "drawing_statistic",
    "labelling_statistic",
    "pair_counts",
    "rand_index",
    "stratified_agreement",
]

# Above this many cells the cross-table of two groupings is not laid out in
# full; the occupied cells are counted instead. A memory guard only: the counts
# are the same either way.
_MAX_TABLE_CELLS = 1 << 22

_NAN = float("nan")

PER_STRATUM_COLUMNS = [
    "stratum",
    "n",
    "n_groups_a",
    "n_groups_b",
    "total",
    "both",
    "a_only",
    "b_only",
    "neither",
    "rand",
    "adjusted_rand",
    "ari_numerator",
    "ari_denominator",
]


# ---------------------------------------------------------------------------
# Counting
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Tally:
    """Exact pair counts of two groupings on the plots used (see module notes)."""

    n: int  # plots used
    total: int  # N
    both: int  # T
    in_a: int  # P
    in_b: int  # Q
    n_groups_a: int
    n_groups_b: int


_EMPTY = _Tally(0, 0, 0, 0, 0, 0, 0)


def _choose_two(counts: npt.NDArray[np.int64]) -> int:
    """Sum over groups of the number of pairs inside a group of that size."""
    c = np.asarray(counts, dtype=np.int64).ravel()
    return int(c @ (c - 1)) // 2


def _tally(a: IntArray, b: IntArray) -> _Tally:
    """Pair counts of two code arrays that hold no missing label.

    `a` and `b` are int64, equal in length, all `>= 0`. Not validated: this is
    the inner step of statistics that run once per relabelling.
    """
    n = int(a.shape[0])
    if n == 0:
        return _EMPTY
    height = int(a.max()) + 1
    width = int(b.max()) + 1
    if height * width > _MAX_TABLE_CELLS:
        # Sparse codes: number the groups 0..k-1 first, so that no count array
        # is longer than the number of groups and the key cannot overflow.
        a = np.unique(a, return_inverse=True)[1].astype(np.int64).ravel()
        b = np.unique(b, return_inverse=True)[1].astype(np.int64).ravel()
        height = int(a.max()) + 1
        width = int(b.max()) + 1
    rows = np.bincount(a)
    cols = np.bincount(b)
    if height * width <= _MAX_TABLE_CELLS:
        cells = np.bincount(a * width + b)
    else:
        # Still too many cells to lay out: count only the cells that hold a plot.
        cells = np.unique(a * width + b, return_counts=True)[1]
    return _Tally(
        n=n,
        total=n * (n - 1) // 2,
        both=_choose_two(cells),
        in_a=_choose_two(rows),
        in_b=_choose_two(cols),
        n_groups_a=int(np.count_nonzero(rows)),
        n_groups_b=int(np.count_nonzero(cols)),
    )


def _used(a: npt.ArrayLike, b: npt.ArrayLike) -> tuple[IntArray, IntArray]:
    """Validate two groupings and keep the plots that have a label in both."""
    codes_a = as_codes(a, "a")
    codes_b = as_codes(b, "b", n=codes_a.shape[0])
    keep = (codes_a >= 0) & (codes_b >= 0)
    return codes_a[keep], codes_b[keep]


# The adjusted Rand index is (T - E) / (M - E) with E = P Q / N and
# M = (P + Q) / 2. Multiplying top and bottom by 2 N gives whole numbers:
#     2 (T N - P Q) / (N (P + Q) - 2 P Q)
# which Python computes exactly, so "the denominator is zero" is an exact test.


def _ari_parts(t: _Tally) -> tuple[int, int]:
    """Whole-number numerator and denominator of the adjusted Rand index."""
    return (
        2 * (t.both * t.total - t.in_a * t.in_b),
        t.total * (t.in_a + t.in_b) - 2 * t.in_a * t.in_b,
    )


def _rand(t: _Tally) -> float:
    if t.total == 0:
        return _NAN
    return (t.total - t.in_a - t.in_b + 2 * t.both) / t.total


def _adjusted_rand(t: _Tally) -> float:
    numerator, denominator = _ari_parts(t)
    if t.total == 0 or denominator <= 0:
        return _NAN
    return numerator / denominator


def _adjusted_rand_max(t: _Tally) -> float:
    _, denominator = _ari_parts(t)
    if t.total == 0 or denominator <= 0:
        return _NAN
    return 2 * (min(t.in_a, t.in_b) * t.total - t.in_a * t.in_b) / denominator


def _pooled_adjusted_rand(tallies: list[_Tally]) -> float:
    """`sum_s (T_s - E_s) / sum_s (M_s - E_s)` over strata, in exact fractions.

    Exact arithmetic makes the result independent of the order of the strata,
    and makes two relabellings with the same counts give the same number to
    the last bit.
    """
    numerator = Fraction(0)
    denominator = Fraction(0)
    for t in tallies:
        if t.total == 0:
            continue
        num, den = _ari_parts(t)
        numerator += Fraction(num, 2 * t.total)
        denominator += Fraction(den, 2 * t.total)
    if denominator <= 0:
        return _NAN
    return float(numerator / denominator)


def _pooled_rand(tallies: list[_Tally]) -> float:
    total = sum(t.total for t in tallies)
    if total == 0:
        return _NAN
    agree = sum(t.total - t.in_a - t.in_b + 2 * t.both for t in tallies)
    return agree / total


# ---------------------------------------------------------------------------
# Plain indices
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PairCounts:
    """The four-way count of the pairs of plots, for two groupings `a` and `b`.

    `total = both + a_only + b_only + neither`.
    """

    n: int  #: plots used (a label in both groupings)
    total: int  #: pairs of those plots, `N = n (n - 1) / 2`
    both: int  #: together in both groupings (`T`)
    a_only: int  #: together in `a`, apart in `b` (`P - T`)
    b_only: int  #: together in `b`, apart in `a` (`Q - T`)
    neither: int  #: apart in both (`N - P - Q + T`)


def _as_pair_counts(t: _Tally) -> PairCounts:
    return PairCounts(
        n=t.n,
        total=t.total,
        both=t.both,
        a_only=t.in_a - t.both,
        b_only=t.in_b - t.both,
        neither=t.total - t.in_a - t.in_b + t.both,
    )


def pair_counts(a: npt.ArrayLike, b: npt.ArrayLike) -> PairCounts:
    """Count the pairs of plots by what two groupings say about them.

    Formula: with `n_ij` the number of plots in group `i` of `a` and group `j`
    of `b`, and `a_i`, `b_j` the group sizes, the pairs together in both are
    `T = sum_ij n_ij (n_ij - 1) / 2`, together in `a` `P = sum_i a_i (a_i - 1) / 2`
    and together in `b` `Q = sum_j b_j (b_j - 1) / 2`. These are the counts the
    Rand index is built from (Rand 1971).

    `a` and `b` are integer codes, one per plot, `-1` for missing. A plot with
    a missing label in either is left out.

    Returns a `PairCounts`. With no plot or one plot used, every pair count is
    0. Raises `ValueError` if the inputs are not code arrays of equal length.
    """
    return _as_pair_counts(_tally(*_used(a, b)))


def rand_index(a: npt.ArrayLike, b: npt.ArrayLike) -> float:
    """Share of the pairs of plots on which two groupings agree (Rand 1971).

    Formula: `(T + (N - P - Q + T)) / N`: the pairs together in both groupings
    plus the pairs apart in both, over all pairs. It lies between 0 and 1.

    It is not corrected for chance: two unrelated groupings with many small
    groups agree on almost every pair (both keep them apart), so the index is
    near 1. Read it beside `adjusted_rand_index`.

    Plots with `-1` in either grouping are left out. Returns `NaN` when fewer
    than two plots are used (there is no pair).
    """
    return _rand(_tally(*_used(a, b)))


def adjusted_rand_index(a: npt.ArrayLike, b: npt.ArrayLike) -> float:
    """Rand index corrected for chance (Hubert and Arabie 1985).

    Formula: `(T - E) / (M - E)`, where `E = P Q / N` is the number of pairs
    together in both groupings expected when the groupings are unrelated but
    keep their group sizes, and `M = (P + Q) / 2` is the most `T` could be
    worth. 1 means the two groupings are the same; 0 means no better than
    chance; below 0 means worse than chance.

    Plots with `-1` in either grouping are left out. Returns `NaN` ("not
    estimable") when fewer than two plots are used, or when `M - E` is zero:
    both groupings put all plots in one group, or both put every plot in a
    group of its own. scikit-learn returns 1.0 in those cases; `NaN` is
    returned here on purpose, because nothing was tested. When one grouping is
    a single group and the other is not, the index is 0.
    """
    return _adjusted_rand(_tally(*_used(a, b)))


@dataclass(frozen=True)
class AgreementResult:
    """Both indices, the ceiling of the adjusted index, and the counts behind them."""

    rand: float
    adjusted_rand: float
    #: The adjusted Rand index these group sizes would give if every pair that
    #: is together in the finer grouping were together in the other as well.
    adjusted_rand_max: float
    counts: PairCounts
    n_groups_a: int
    n_groups_b: int


def agreement(a: npt.ArrayLike, b: npt.ArrayLike) -> AgreementResult:
    """Rand index, adjusted Rand index, its ceiling and the pair counts.

    `rand` and `adjusted_rand` are as in `rand_index` (Rand 1971) and
    `adjusted_rand_index` (Hubert and Arabie 1985).

    `adjusted_rand_max = (min(P, Q) - E) / (M - E)`: the adjusted index if `T`
    were as large as these group sizes allow, which is `min(P, Q)`. `T` cannot
    exceed either `P` or `Q`, so this is an upper bound for groupings with
    these group sizes. It is 1 only when `P == Q`. When one grouping is much
    finer than the other (many small stands against a few field types,
    `P << Q` or the reverse) the ceiling is close to `2 min(P, Q) / max(P, Q)`,
    far below 1, even if every small group is pure. A low index beside a low
    ceiling says "one grouping is finer than the other", not "they disagree".

    `n_groups_a` and `n_groups_b` count the groups that hold at least one plot
    used. Plots with `-1` in either grouping are left out.

    Degenerate inputs: `rand` is `NaN` with fewer than two plots used;
    `adjusted_rand` and `adjusted_rand_max` are `NaN` then and when both
    groupings are one group or both are all single plots.
    """
    t = _tally(*_used(a, b))
    return AgreementResult(
        rand=_rand(t),
        adjusted_rand=_adjusted_rand(t),
        adjusted_rand_max=_adjusted_rand_max(t),
        counts=_as_pair_counts(t),
        n_groups_a=t.n_groups_a,
        n_groups_b=t.n_groups_b,
    )


# ---------------------------------------------------------------------------
# Inside strata, pooled by pair counts
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StratifiedAgreement:
    """Agreement worked out inside each stratum and pooled over strata."""

    rand: float  #: pooled over strata
    adjusted_rand: float  #: pooled over strata
    per_stratum: pd.DataFrame  #: one row per stratum code, sorted by code


def _stratum_members(strata: IntArray, usable: npt.NDArray[np.bool_]) -> list[tuple[int, IntArray]]:
    """`(code, plot indices)` of each stratum, in increasing code order.

    Every stratum code present in `strata` is listed, also one whose plots are
    all unusable (its index array is then empty).
    """
    codes = np.unique(strata[strata >= 0])
    order = np.argsort(strata, kind="stable")
    starts = np.searchsorted(strata[order], codes, side="left")
    stops = np.searchsorted(strata[order], codes, side="right")
    members = []
    for code, lo, hi in zip(codes.tolist(), starts.tolist(), stops.tolist(), strict=True):
        index = order[lo:hi]
        members.append((int(code), index[usable[index]].astype(np.int64)))
    return members


def stratified_agreement(
    a: npt.ArrayLike, b: npt.ArrayLike, strata: npt.ArrayLike
) -> StratifiedAgreement:
    """Rand and adjusted Rand index inside strata, pooled by pair counts.

    Only pairs of plots in the SAME stratum are counted, and chance is worked
    out inside each stratum. So a group code of `a` or `b` never has to mean
    the same thing in two strata. This is what a stand type needs: types are
    fitted separately in each district, so the strata are the districts.

    Formula: for each stratum `s`, on its plots only, count `T_s`, `P_s`,
    `Q_s`, `N_s` as in `pair_counts`, and set `E_s = P_s Q_s / N_s`,
    `M_s = (P_s + Q_s) / 2`. Then

      - pooled Rand `= sum_s (T_s + N_s - P_s - Q_s + T_s) / sum_s N_s`
        (Rand 1971, pairs restricted to within strata);
      - pooled adjusted Rand `= sum_s (T_s - E_s) / sum_s (M_s - E_s)`
        (Hubert and Arabie 1985, with the chance term taken per stratum).

    This is the adjusted Rand index of all within-stratum pairs taken as one
    set, not an average of per-stratum indices: a stratum counts in proportion
    to the pairs it holds. With one stratum it equals the plain index.

    A stratum in which one grouping is a single group is not skipped. It adds
    0 to the numerator and a positive amount to the denominator, which is the
    honest reading: nothing was shown there.

    `a`, `b` and `strata` are integer codes, one per plot, `-1` for missing. A
    plot with `-1` in any of the three is left out.

    Returns a `StratifiedAgreement`. `per_stratum` has one row per stratum
    code present in `strata`, sorted by code, with the columns `stratum, n,
    n_groups_a, n_groups_b, total, both, a_only, b_only, neither, rand,
    adjusted_rand, ari_numerator, ari_denominator` (`ari_numerator = T_s - E_s`,
    `ari_denominator = M_s - E_s`, the two terms the pooled index sums).

    Degenerate inputs: a stratum with fewer than two plots used has no pair;
    its indices are `NaN`, its two terms are 0, and it adds nothing to the
    pooled values. The pooled Rand index is `NaN` when no stratum has a pair;
    the pooled adjusted index is `NaN` when the summed denominator is zero.
    """
    codes_a = as_codes(a, "a")
    codes_b = as_codes(b, "b", n=codes_a.shape[0])
    codes_s = as_codes(strata, "strata", n=codes_a.shape[0])
    usable = (codes_a >= 0) & (codes_b >= 0)
    tallies = []
    rows = []
    for code, index in _stratum_members(codes_s, usable):
        t = _tally(codes_a[index], codes_b[index])
        tallies.append(t)
        counts = _as_pair_counts(t)
        numerator, denominator = _ari_parts(t)
        rows.append(
            {
                "stratum": code,
                "n": t.n,
                "n_groups_a": t.n_groups_a,
                "n_groups_b": t.n_groups_b,
                "total": counts.total,
                "both": counts.both,
                "a_only": counts.a_only,
                "b_only": counts.b_only,
                "neither": counts.neither,
                "rand": _rand(t),
                "adjusted_rand": _adjusted_rand(t),
                "ari_numerator": numerator / (2 * t.total) if t.total else 0.0,
                "ari_denominator": denominator / (2 * t.total) if t.total else 0.0,
            }
        )
    table = pd.DataFrame(rows, columns=PER_STRATUM_COLUMNS)
    integer_columns = PER_STRATUM_COLUMNS[:9]
    float_columns = PER_STRATUM_COLUMNS[9:]
    table = table.astype(
        dict.fromkeys(integer_columns, "int64") | dict.fromkeys(float_columns, "float64")
    )
    return StratifiedAgreement(
        rand=_pooled_rand(tallies),
        adjusted_rand=_pooled_adjusted_rand(tallies),
        per_stratum=table,
    )


# ---------------------------------------------------------------------------
# Statistics for the significance tests
# ---------------------------------------------------------------------------


def drawing_statistic(field_type: npt.ArrayLike) -> Statistic:
    """The drawing statistic: adjusted Rand index of field type against stand.

    Returns a `Statistic` named `"ari_drawing"` whose value for a relabelling
    of the plots is `adjusted_rand_index(field_type, stand_id)` (Hubert and
    Arabie 1985). The stand type is not used. Larger means the stands follow
    the field types better, so the declared tail is `"greater"`.

    `field_type` holds integer codes, one per plot, `-1` for missing; it is
    checked and copied here, once. The statistic receives `stand_id` codes in
    the same plot order and does not modify them.

    Degenerate inputs: the value is `NaN` whenever `adjusted_rand_index` is
    (fewer than two plots with both a field type and a stand; both groupings
    one group; both all single plots). A wrong-length `stand_id` raises
    `ValueError`.
    """
    field = as_codes(field_type, "field_type").copy()
    has_field = field >= 0
    n = int(field.shape[0])

    def func(stand_id: IntArray, stand_type: IntArray | None) -> float:
        sid = np.asarray(stand_id, dtype=np.int64)
        if sid.shape != (n,):
            raise ValueError(f"stand_id has shape {sid.shape}, expected ({n},)")
        keep = has_field & (sid >= 0)
        return _adjusted_rand(_tally(field[keep], sid[keep]))

    return Statistic("ari_drawing", func, "greater")


def labelling_statistic(
    field_type: npt.ArrayLike, super_group: npt.ArrayLike | None = None
) -> Statistic:
    """The labelling statistic: field type against stand type, inside districts.

    Returns a `Statistic` named `"ari_labelling"` whose value for a relabelling
    of the plots is `stratified_agreement(field_type, stand_type,
    super_group).adjusted_rand`: the adjusted Rand index (Hubert and Arabie
    1985) of field type against stand type, counted over pairs of plots inside
    one super-group (district) and pooled over super-groups by pair counts.
    It is computed from the counts alone, without building the per-stratum
    table. The stand id is not used. Declared tail: `"greater"`.

    `super_group=None` means all plots form one stratum, and the value is the
    plain `adjusted_rand_index(field_type, stand_type)`.

    `field_type` and `super_group` hold integer codes, one per plot, `-1` for
    missing; they are checked and copied here, once. A plot with no field
    type, no super-group or (in a given relabelling) no stand type is left
    out.

    Degenerate inputs: `NaN` when the pooled index is not estimable (see
    `stratified_agreement`). The statistic raises `ValueError` when called
    without stand types, or with a wrong-length array.
    """
    field = as_codes(field_type, "field_type").copy()
    n = int(field.shape[0])
    if super_group is None:
        strata = np.zeros(n, dtype=np.int64)
    else:
        strata = as_codes(super_group, "super_group", n=n)
    # Fixed for every relabelling: the plots that have a field type and a
    # stratum, the position of their stratum among the strata, and their field
    # types.
    plots = np.flatnonzero((field >= 0) & (strata >= 0))
    stratum_of = np.unique(strata[plots], return_inverse=True)[1].astype(np.int64).ravel()
    field_of = field[plots]
    n_strata = int(stratum_of.max()) + 1 if plots.shape[0] else 0
    n_field = int(field_of.max()) + 1 if plots.shape[0] else 0
    cell_of = stratum_of * n_field + field_of

    def func(stand_id: IntArray, stand_type: IntArray | None) -> float:
        if stand_type is None:
            raise ValueError("ari_labelling needs stand types; stand_type is None")
        typ = np.asarray(stand_type, dtype=np.int64)
        if typ.shape != (n,):
            raise ValueError(f"stand_type has shape {typ.shape}, expected ({n},)")
        typ_of = typ[plots]
        keep = typ_of >= 0
        if not keep.any():
            return _NAN
        typ_of = typ_of[keep]
        n_type = int(typ_of.max()) + 1
        size = n_strata * n_field * n_type
        if size > _MAX_TABLE_CELLS:
            # Sparse type codes: number them 0..k-1 first.
            typ_of = np.unique(typ_of, return_inverse=True)[1].astype(np.int64).ravel()
            n_type = int(typ_of.max()) + 1
            size = n_strata * n_field * n_type
        # One cross-table per stratum, all counted at once: plots by
        # (stratum, field type, stand type).
        cells = np.bincount(cell_of[keep] * n_type + typ_of, minlength=size).reshape(
            n_strata, n_field, n_type
        )
        rows = cells.sum(axis=2)
        cols = cells.sum(axis=1)
        used = rows.sum(axis=1).tolist()
        both = ((cells * (cells - 1)).sum(axis=(1, 2)) // 2).tolist()
        in_a = ((rows * (rows - 1)).sum(axis=1) // 2).tolist()
        in_b = ((cols * (cols - 1)).sum(axis=1) // 2).tolist()
        tallies = [
            _Tally(m, m * (m - 1) // 2, t, p, q, 0, 0)
            for m, t, p, q in zip(used, both, in_a, in_b, strict=True)
        ]
        return _pooled_adjusted_rand(tallies)

    return Statistic("ari_labelling", func, "greater")

"""The stand table off Earth Engine: its preprocessing and the k-means fit (round 14).

With `clustering.fit_outside_earth_engine` on, the clustering stage reads the table of its
units back from Earth Engine (one row per unit: the unit's label and its mean in every
candidate band, after the cyclic decomposition and the habitat mask) and does the rest here,
in plain Python: the declared preprocessing, k-means with scikit-learn, and the type of every
unit. Nothing here calls Earth Engine; tests/test_stand_table.py tests it.

The rows. One per unit with a habitat pixel whose centre is inside the ROI and data in every
candidate band (the clustering stage's one-pixel sample with dropNulls, the rows its
preprocessing statistics have used since round 9), sorted by unit label, so that the fit does
not depend on the order Earth Engine returns them in (k-means++ does depend on row order).
`in_fit` is False for the stands that clustering.fit_excludes_stands_below_min_area leaves out
of the fit; they are preprocessed with the other rows and typed by the nearest fitted centre.

The two preprocessing rules (`clustering.log_rule`):

  "abs_skew" (the default, DEC-004 as the clustering stage has built it since round 13):
    a band whose |skew| is above the threshold is logged as log(x - min + 0.001), min over
    every row; the sin and cos of a harmonic phase are not skew-tested (review B13), aspect's
    are; then each band is scaled by its own median and IQR, exact quartiles (DEC-003, review
    B16), and a band whose IQR is at most 1e-9 is dropped as constant.

  "right_skew" (round 14, Task 2.2; reviews A3, B12, round 13's question 8):
    a band whose IQR is at most 1e-9 is dropped as constant first; then only a right-skewed
    band (skew above the threshold) is logged, as log1p((x - min) / IQR), with min over every
    row and IQR the band's own before the log, so that the log is defined for every row; a
    left-skewed band is not transformed. The sin and cos of an angle (a harmonic phase,
    aspect) are never skew-tested or logged. Each band is then centred by its median and
    divided by its IQR (exact quartiles), except that the two components of an angle are each
    centred by their own median and divided by one shared spread, the root mean square of
    their two IQRs, so that the circle is scaled the same way along both axes and not
    stretched. An angle pair is dropped only when that shared spread is at most 1e-9. Each
    band's skew is recorded before and after the log.

The skew is the moment coefficient g1 = m3 / m2^1.5, which is what Earth Engine's
Reducer.skew computes (read on Earth Engine on 26 Oct 2026 on three small lists, matching g1
to 15 digits and not the adjusted G1), so that the default rule here decides as the Earth
Engine path does. A band with no spread has a skew of 0.

k-means. `kmeans_starts` makes `n_starts` k-means++ starts from one random state seeded with
`seed`, each refined by Lloyd's algorithm (scikit-learn's KMeans with n_init=1): the starts
`KMeans(n_clusters=k, n_init=n_starts, random_state=seed)` makes, one by one, so that every
start's labels are kept and the starts' agreement can be measured (adjusted Rand index of
every pair). `best_start` takes the start scikit-learn keeps: the lowest within-cluster sum of
squares, a later start replacing an earlier one only when its sum is lower and its clustering
differs. The fits run on one thread, so that a run repeats bit for bit (with several threads
scikit-learn's sums can differ in the last digits).
"""

from __future__ import annotations

import csv
import io
import json
import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

# What a spread must exceed for a band not to be dropped as constant (as the Earth Engine
# path's _apply_scaling).
SPREAD_EPSILON = 1e-9
# The offset of the default rule's log, log(x - min + 0.001) (DEC-004).
LOG_EPSILON = 1e-3
RULES = ("abs_skew", "right_skew")


@dataclass
class StandTable:
    """One row per unit: its label, its mean in each band, and whether it is a row of the fit."""

    labels: np.ndarray  # int64, ascending
    bands: list[str]
    values: np.ndarray  # float64, len(labels) x len(bands)
    in_fit: np.ndarray  # bool, len(labels)

    def __post_init__(self) -> None:
        if self.values.shape != (len(self.labels), len(self.bands)):
            raise ValueError(
                f"stand table: {self.values.shape} values for {len(self.labels)} rows and "
                f"{len(self.bands)} bands"
            )
        if len(set(self.labels.tolist())) != len(self.labels):
            raise ValueError("stand table: a unit label appears twice")
        if np.any(np.diff(self.labels) < 0):
            raise ValueError("stand table: rows are not sorted by unit label")


def stand_table_from_columns(
    columns: Sequence[Sequence[Any]],
    *,
    bands: Sequence[str],
    left_out: set[int] | None = None,
) -> StandTable:
    """The table from its columns as Earth Engine gives them: the label first, then each band.

    `columns` is a list of rows, each [label, value of bands[0], value of bands[1], ...] (what
    `reduceColumns(ee.Reducer.toList(1 + len(bands)), [label, *bands])` returns). The rows are
    sorted by label. A missing value cannot come from a sample that drops nulls, so it is an
    error rather than something to fill. `left_out` are the unit labels left out of the fit.
    """
    n_bands = len(bands)
    rows = [list(r) for r in columns]
    for i, r in enumerate(rows):
        if len(r) != 1 + n_bands:
            raise ValueError(f"stand table: row {i} has {len(r)} values, not {1 + n_bands}")
        if any(v is None for v in r):
            raise ValueError(f"stand table: row {i} (label {r[0]}) has a missing value")
    labels = np.array([_label(r[0]) for r in rows], dtype=np.int64)
    order = np.argsort(labels, kind="stable")
    values = np.array([[float(v) for v in r[1:]] for r in rows], dtype=float).reshape(len(rows), n_bands)
    left = left_out or set()
    sorted_labels = labels[order]
    return StandTable(
        labels=sorted_labels,
        bands=list(bands),
        values=values[order],
        in_fit=np.array([int(lbl) not in left for lbl in sorted_labels], dtype=bool),
    )


def _label(value: Any) -> int:
    """A unit label read back from Earth Engine (a whole number, perhaps as a float)."""
    f = float(value)
    if f != math.floor(f):
        raise ValueError(f"stand table: unit label {value!r} is not a whole number")
    return int(f)


def skewness(values: np.ndarray) -> float:
    """The moment coefficient of skewness g1 = m3 / m2^1.5 (Earth Engine's Reducer.skew); 0
    for values with no spread."""
    v = np.asarray(values, dtype=float)
    d = v - v.mean()
    m2 = float(np.mean(d * d))
    if m2 <= 0.0:
        return 0.0
    m3 = float(np.mean(d * d * d))
    return m3 / m2**1.5


def exact_quartiles(values: np.ndarray) -> tuple[float, float, float]:
    """25th, 50th and 75th percentiles, numpy's linear interpolation between order statistics
    (the Earth Engine path's _exact_quartiles, review B16)."""
    p25, p50, p75 = np.percentile(np.asarray(values, dtype=float), [25, 50, 75])
    return float(p25), float(p50), float(p75)


@dataclass
class Preprocessed:
    """The table's rows after the preprocessing: the active bands, in table order."""

    bands: list[str]
    values: np.ndarray  # len(table.labels) x len(bands)
    record: dict[str, Any] = field(default_factory=dict)


def angle_pairs(decomposed: Sequence[str]) -> list[tuple[str, str]]:
    """The sin and cos bands made of each band the cyclic decomposition decomposed."""
    return [(f"{b}_sin", f"{b}_cos") for b in decomposed]


def preprocess(
    table: StandTable,
    *,
    rule: str,
    threshold: float,
    decomposed: Sequence[str],
) -> Preprocessed:
    """The declared preprocessing of `rule` (module docstring) over every row of `table`.

    `decomposed` are the bands the cyclic decomposition made sin/cos pairs of (aspect, and any
    band with "_phase_" in its name). Every statistic is taken over every row, the rows left
    out of the fit included, as the Earth Engine path takes them.
    """
    if rule not in RULES:
        raise ValueError(f"preprocess: unknown rule {rule!r}; one of {RULES}")
    pairs = angle_pairs(decomposed)
    for a, b in pairs:
        if a not in table.bands or b not in table.bands:
            raise ValueError(f"preprocess: the angle pair {a}, {b} is not in the table")
    if rule == "abs_skew":
        return _abs_skew(table, threshold=threshold, decomposed=decomposed)
    return _right_skew(table, threshold=threshold, pairs=pairs)


def _column(table: StandTable, band: str) -> np.ndarray:
    return table.values[:, table.bands.index(band)]


def _abs_skew(table: StandTable, *, threshold: float, decomposed: Sequence[str]) -> Preprocessed:
    phase = {c for b in decomposed if "_phase_" in b for c in (f"{b}_sin", f"{b}_cos")}
    columns = {b: _column(table, b).copy() for b in table.bands}
    skewed = [b for b in table.bands if b not in phase and abs(skewness(columns[b])) > threshold]
    offsets: dict[str, float] = {}
    for b in skewed:
        offsets[b] = -float(columns[b].min()) + LOG_EPSILON
        columns[b] = np.log(columns[b] + offsets[b])
    scaling: dict[str, dict[str, float]] = {}
    active: list[str] = []
    for b in table.bands:
        p25, p50, p75 = exact_quartiles(columns[b])
        scaling[b] = {"center": p50, "spread": p75 - p25}
        if p75 - p25 > SPREAD_EPSILON:
            active.append(b)
    if not active:
        raise ValueError("All feature bands have zero spread; nothing left to cluster on.")
    values = np.column_stack(
        [(columns[b] - scaling[b]["center"]) / scaling[b]["spread"] for b in active]
    )
    record = {
        "log_rule": "abs_skew",
        "skewness_threshold": threshold,
        "log_transformed_bands": skewed,
        "log_offsets": offsets,
        "scaling": scaling,
        "active_bands": active,
        "dropped_constant_bands": sorted(set(table.bands) - set(active)),
    }
    return Preprocessed(bands=active, values=values, record=record)


def _right_skew(
    table: StandTable, *, threshold: float, pairs: list[tuple[str, str]]
) -> Preprocessed:
    in_pair = {c for pair in pairs for c in pair}
    raw = {b: _column(table, b) for b in table.bands}
    raw_q = {b: exact_quartiles(raw[b]) for b in table.bands}
    raw_iqr = {b: raw_q[b][2] - raw_q[b][0] for b in table.bands}
    # 1. Constant bands first: a band, or an angle pair, with no spread.
    shared_raw = {pair: _rms(raw_iqr[pair[0]], raw_iqr[pair[1]]) for pair in pairs}
    dropped = {b for b in table.bands if b not in in_pair and raw_iqr[b] <= SPREAD_EPSILON}
    dropped |= {c for pair, s in shared_raw.items() if s <= SPREAD_EPSILON for c in pair}
    # 2. Only right-skewed bands are logged, never an angle's sin or cos.
    tested = [b for b in table.bands if b not in in_pair and b not in dropped]
    columns = {b: raw[b].copy() for b in table.bands}
    skew_before = {b: skewness(raw[b]) for b in tested}
    logged: dict[str, dict[str, float]] = {}
    for b in tested:
        if skew_before[b] > threshold:
            low, iqr = float(raw[b].min()), raw_iqr[b]
            logged[b] = {"min": low, "iqr": iqr}
            columns[b] = np.log1p((raw[b] - low) / iqr)
    skew_after = {b: (skewness(columns[b]) if b in logged else skew_before[b]) for b in tested}
    # 3. The scaling: median and IQR, one shared spread for the two components of an angle.
    scaling: dict[str, dict[str, float]] = {}
    for b in table.bands:
        if b in in_pair:
            continue
        p25, p50, p75 = exact_quartiles(columns[b])
        scaling[b] = {"center": p50, "spread": p75 - p25}
        if b not in dropped and p75 - p25 <= SPREAD_EPSILON:
            dropped.add(b)
    pair_record = []
    for (a, c), s in shared_raw.items():
        for comp in (a, c):
            scaling[comp] = {"center": raw_q[comp][1], "spread": s}
        pair_record.append(
            {"bands": [a, c], "iqr": [raw_iqr[a], raw_iqr[c]], "shared_spread": s}
        )
    active = [b for b in table.bands if b not in dropped]
    if not active:
        raise ValueError("All feature bands have zero spread; nothing left to cluster on.")
    values = np.column_stack(
        [(columns[b] - scaling[b]["center"]) / scaling[b]["spread"] for b in active]
    )
    record = {
        "log_rule": "right_skew",
        "skewness_threshold": threshold,
        "log_transformed_bands": [b for b in table.bands if b in logged],
        "log1p_params": logged,
        "skew_before": skew_before,
        "skew_after": skew_after,
        "angle_pairs": pair_record,
        "scaling": {b: scaling[b] for b in table.bands},
        "active_bands": active,
        "dropped_constant_bands": sorted(dropped),
    }
    return Preprocessed(bands=active, values=values, record=record)


def _rms(a: float, b: float) -> float:
    """Root mean square of two spreads: the shared spread of an angle's sin and cos."""
    return math.sqrt((a * a + b * b) / 2.0)


# ---------------------------------------------------------------------
# k-means
# ---------------------------------------------------------------------


@dataclass
class Start:
    """One k-means++ start, refined: its labels, centres and within-cluster sum of squares."""

    labels: np.ndarray
    centres: np.ndarray
    wcss: float
    n_iter: int


def kmeans_starts(rows: np.ndarray, k: int, *, n_starts: int, seed: int) -> list[Start]:
    """The `n_starts` starts of `KMeans(n_clusters=k, n_init=n_starts, random_state=seed)`.

    As scikit-learn makes them (`KMeans._fit`): the rows centred on their mean, k-means++
    centres drawn for each start in turn from one random state, each start refined by Lloyd's
    algorithm. The centres k-means++ draws are rows, so each start is handed to KMeans as the
    rows it chose, and KMeans centres them as it centres the data. One thread.
    """
    from sklearn.cluster import KMeans, kmeans_plusplus
    from sklearn.utils import check_random_state
    from sklearn.utils.extmath import row_norms
    from threadpoolctl import threadpool_limits

    x = np.ascontiguousarray(rows, dtype=float)
    if k > len(x):
        raise ValueError(f"k-means: {len(x)} rows cannot hold k = {k} clusters")
    random_state = check_random_state(seed)
    centred = x - x.mean(axis=0)
    norms = row_norms(centred, squared=True)
    starts: list[Start] = []
    with threadpool_limits(limits=1):
        for _ in range(n_starts):
            _, chosen = kmeans_plusplus(
                centred, k, x_squared_norms=norms, random_state=random_state
            )
            fit = KMeans(n_clusters=k, init=x[chosen], n_init=1).fit(x)
            starts.append(
                Start(
                    labels=fit.labels_.astype(np.int64).copy(),
                    centres=fit.cluster_centers_.copy(),
                    wcss=float(fit.inertia_),
                    n_iter=int(fit.n_iter_),
                )
            )
    return starts


def same_clustering(a: np.ndarray, b: np.ndarray) -> bool:
    """Whether two labellings are the same partition, whatever the label numbers."""
    pairs = set(zip(a.tolist(), b.tolist(), strict=True))
    return len(pairs) == len(set(a.tolist())) == len(set(b.tolist()))


def best_start(starts: Sequence[Start]) -> int:
    """The index of the start scikit-learn keeps (module docstring)."""
    best = 0
    for i in range(1, len(starts)):
        if starts[i].wcss < starts[best].wcss and not same_clustering(
            starts[i].labels, starts[best].labels
        ):
            best = i
    return best


def starts_agreement(starts: Sequence[Start]) -> dict[str, float]:
    """How much the starts agree: the median and lowest adjusted Rand index over every pair.

    A diagnostic of the clustering, not a field score.
    """
    from sklearn.metrics import adjusted_rand_score

    scores = [
        float(adjusted_rand_score(starts[i].labels, starts[j].labels))
        for i in range(len(starts))
        for j in range(i + 1, len(starts))
    ]
    if not scores:
        return {"ari_median": 1.0, "ari_min": 1.0, "n_pairs": 0}
    return {
        "ari_median": float(np.median(scores)),
        "ari_min": float(min(scores)),
        "n_pairs": len(scores),
    }


def nearest_centre(rows: np.ndarray, centres: np.ndarray) -> np.ndarray:
    """The index of the nearest centre for each row (squared Euclidean distance; the lowest
    index on a tie)."""
    d = ((rows[:, None, :] - centres[None, :, :]) ** 2).sum(axis=2)
    return np.argmin(d, axis=1).astype(np.int64)


@dataclass
class Fit:
    """A k-means fit at one k: the best start, every unit's type, and the starts' agreement."""

    k: int
    best: int
    wcss: float
    types: np.ndarray  # one per row of the table
    centres: np.ndarray
    agreement: dict[str, float]
    wcss_of_each_start: list[float]


def fit_types(
    pre: Preprocessed, in_fit: np.ndarray, *, k: int, n_starts: int, seed: int
) -> Fit:
    """k-means on the rows of the fit; every row of the table typed by the nearest centre."""
    rows = pre.values[in_fit]
    starts = kmeans_starts(rows, k, n_starts=n_starts, seed=seed)
    best = best_start(starts)
    types = nearest_centre(pre.values, starts[best].centres)
    return Fit(
        k=k,
        best=best,
        wcss=starts[best].wcss,
        types=types,
        centres=starts[best].centres,
        agreement=starts_agreement(starts),
        wcss_of_each_start=[s.wcss for s in starts],
    )


# ---------------------------------------------------------------------
# Files (results only: no dates, no times)
# ---------------------------------------------------------------------


def _num(v: float) -> str:
    return format(float(v), ".17g")


def table_csv(table: StandTable, *, label_name: str = "stand_lbl") -> str:
    """The table before the preprocessing: label, in_fit, then each band."""
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow([label_name, "in_fit", *table.bands])
    for lbl, fit, vals in zip(table.labels, table.in_fit, table.values, strict=True):
        w.writerow([int(lbl), int(bool(fit)), *(_num(v) for v in vals)])
    return out.getvalue()


def rows_csv(
    table: StandTable,
    pre: Preprocessed,
    *,
    types: np.ndarray | None = None,
    label_name: str = "stand_lbl",
) -> str:
    """The rows after the preprocessing: label, in_fit, [type,] then each active band."""
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow([label_name, "in_fit", *(["type"] if types is not None else []), *pre.bands])
    for i, (lbl, fit) in enumerate(zip(table.labels, table.in_fit, strict=True)):
        extra = [int(types[i])] if types is not None else []
        w.writerow([int(lbl), int(bool(fit)), *extra, *(_num(v) for v in pre.values[i])])
    return out.getvalue()


def json_text(obj: Any) -> str:
    """JSON with sorted keys, for a results file."""
    return json.dumps(obj, indent=1, sort_keys=True) + "\n"

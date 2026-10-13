"""Segmentation quality when a site has no reference data.

The only question that can be asked without a reference is whether places
inside one segment (a stand) are more alike than places in different segments,
on some layer of values. To mean anything the layer should be one the pipeline
did NOT use to draw the segments. Four measures:

  - `explained_variance`: the share of a layer's variation that lies between
    segments, `R2 = 1 - SS_within / SS_total`, at pixel level. The same
    definition as `fmu.utils.components.explained_variance_r2`, which
    `stages/metrics.py` reports, on plain arrays.
  - `weighted_variance`: the area-weighted variance inside segments.
  - `morans_i` and `segment_morans_i`: Moran's I of the segment means between
    adjacent segments (are neighbouring segments alike?).
  - `global_score`: the Global Score of Johnson and Xie 2011, which ranks a SET
    of candidate segmentations by the two measures above.

**Inputs.** `labels` is an integer array of any shape: a raster `(H, W)`, or
`(n,)` for a table of plots or pixels. A value below 0 means "no segment".
`values` has the shape of `labels` (one layer) or `(B,) + labels.shape`
(several layers, band first, as rasterio reads; for a plot table with one
column per measurement pass `table.T`). `NaN` in `values` means no data.
`valid` is an optional boolean array of the shape of `labels` that masks
pixels out as well. A pixel is used for a band if its label is `>= 0`, it is
valid, and that band's value is not `NaN`: the mask is taken band by band.

A segment is a label value. Two separate patches with one label are one
segment; pass connected-component labels if that is not wanted.

Every one of these measures moves with the NUMBER of segments whatever the
layer is (more segments, less variance inside each), so every table carries
`n_segments` and no value should be read without it. Nothing here knows about
any site, and nothing is tuned.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
import numpy.typing as npt
import pandas as pd

from fmu.evaluation._common import BoolArray, FloatArray, IntArray

EXPLAINED_VARIANCE_COLUMNS = ["band", "r2", "ss_within", "ss_total", "n_pixels", "n_segments"]
WEIGHTED_VARIANCE_COLUMNS = ["band", "weighted_variance", "n_pixels", "n_segments"]
MORANS_I_COLUMNS = ["band", "morans_i", "n_segments", "n_adjacent_pairs"]
GLOBAL_SCORE_COLUMNS = [
    "segmentation",
    "band",
    "n_segments",
    "weighted_variance",
    "morans_i",
    "weighted_variance_norm",
    "morans_i_norm",
    "global_score",
]
MEAN_ROW = "mean"

_NAN = float("nan")


# ---------------------------------------------------------------------------
# Input handling
# ---------------------------------------------------------------------------


def _as_labels(labels: npt.ArrayLike, name: str = "labels") -> IntArray:
    """Return segment labels as an int64 array of the same shape.

    Integer arrays pass as they are. A float array is accepted when every
    value is a finite whole number (a raster read as float); `NaN`, fractions,
    booleans and strings raise `ValueError`. "No segment" is any value below 0.
    """
    arr = np.asarray(labels)
    if arr.ndim == 0:
        raise ValueError(f"{name} must be an array, not a single value")
    if np.issubdtype(arr.dtype, np.integer):
        return arr.astype(np.int64, copy=False)
    if np.issubdtype(arr.dtype, np.floating):
        if not (np.isfinite(arr).all() and (arr == np.floor(arr)).all()):
            raise ValueError(
                f"{name} must hold whole numbers; mark 'no segment' with a negative value, not NaN"
            )
        return arr.astype(np.int64)
    raise ValueError(f"{name} must hold integer segment labels, got dtype {arr.dtype}")


def _prepare(
    labels: npt.ArrayLike,
    values: npt.ArrayLike,
    valid: npt.ArrayLike | None,
    band_names: Sequence[str] | None,
) -> tuple[IntArray, FloatArray, list[str]]:
    """Check the inputs and return `(labels, values, band_names)`.

    `labels` comes back in its own shape with `-1` wherever a pixel has no
    segment or is masked out by `valid`. `values` comes back as float64 of
    shape `(B, number of pixels)`.
    """
    lab = _as_labels(labels)
    vals = np.asarray(values, dtype=np.float64)
    if vals.shape == lab.shape:
        vals = vals.reshape(1, -1)
    elif vals.ndim == lab.ndim + 1 and vals.shape[1:] == lab.shape:
        vals = vals.reshape(vals.shape[0], -1)
    else:
        raise ValueError(
            f"values has shape {vals.shape}; expected the shape of labels {lab.shape} "
            f"or (bands,) + {lab.shape}"
        )
    if np.isinf(vals).any():
        raise ValueError("values holds an infinite value")
    if valid is not None:
        mask = np.asarray(valid)
        if mask.dtype != np.bool_ or mask.shape != lab.shape:
            raise ValueError(
                f"valid must be a boolean array of shape {lab.shape}, "
                f"got dtype {mask.dtype} and shape {mask.shape}"
            )
        lab = np.where(mask, lab, -1)
    n_bands = vals.shape[0]
    if band_names is None:
        names = [f"band_{b}" for b in range(n_bands)]
    else:
        names = [str(b) for b in band_names]
        if len(names) != n_bands:
            raise ValueError(f"{len(names)} band names were given for {n_bands} band(s)")
        if len(set(names)) != len(names):
            raise ValueError("band names must be distinct")
    return lab, vals, names


def _compact(flat_labels: IntArray) -> tuple[IntArray, IntArray]:
    """Renumber labels `0..K-1`.

    Returns `(codes, classes)`: `codes` has `-1` where the label is below 0 and
    otherwise the position of the label in `classes`, the sorted distinct
    labels. Labels may be any non-negative integers (ids with gaps, very large
    ids), so nothing downstream allocates by the largest label.
    """
    used = flat_labels >= 0
    codes = np.full(flat_labels.shape[0], -1, dtype=np.int64)
    if not used.any():
        return codes, np.zeros(0, dtype=np.int64)
    largest = int(flat_labels.max())
    if largest <= 4 * flat_labels.shape[0] + 1024:
        # A lookup table is several times faster than sorting the pixels.
        present = np.zeros(largest + 1, dtype=bool)
        present[flat_labels[used]] = True
        classes = np.flatnonzero(present).astype(np.int64)
        lookup = np.cumsum(present) - 1
        codes[used] = lookup[flat_labels[used]]
    else:
        classes, inverse = np.unique(flat_labels[used], return_inverse=True)
        codes[used] = inverse.reshape(-1)
    return codes, classes.astype(np.int64)


@dataclass(frozen=True)
class _BandSums:
    """Pixel-level sums of one band over one segmentation."""

    n_pixels: int
    n_segments: int
    ss_within: float
    ss_total: float
    means: FloatArray  # (K,), NaN for a segment with no used pixel in this band


def _band_sums(codes: IntArray, n_codes: int, x: FloatArray) -> _BandSums:
    """Sums of squares of one band, over the pixels that have a segment and a value.

    Values are centred on their overall mean before anything is summed, so a
    layer with a large offset (an elevation, say) loses no precision. A band
    whose used pixels are all equal returns exactly 0 for both sums.
    """
    use = (codes >= 0) & ~np.isnan(x)
    means = np.full(n_codes, np.nan, dtype=np.float64)
    if use.all():
        c, v = codes, x
    else:
        c, v = codes[use], x[use]
    n = int(v.shape[0])
    if n == 0:
        return _BandSums(0, 0, 0.0, 0.0, means)
    counts = np.bincount(c, minlength=n_codes)
    has = counts > 0
    lo = float(v.min())
    if lo == float(v.max()):
        means[has] = lo
        return _BandSums(n, int(has.sum()), 0.0, 0.0, means)
    centre = float(v.mean())
    dev = v - centre
    shift = float(dev.mean())  # what is left of the mean after the first pass
    dev -= shift
    # np.sum of products, not np.dot: a BLAS dot product can change in its last
    # binary digit with where the array sits in memory.
    ss_total = float(np.sum(dev * dev))
    seg_dev = np.zeros(n_codes, dtype=np.float64)
    seg_dev[has] = np.bincount(c, weights=dev, minlength=n_codes)[has] / counts[has]
    resid = dev - seg_dev[c]
    ss_within = float(np.sum(resid * resid))
    means[has] = seg_dev[has] + (centre + shift)
    return _BandSums(n, int(has.sum()), ss_within, ss_total, means)


# ---------------------------------------------------------------------------
# Explained variance and area-weighted variance
# ---------------------------------------------------------------------------


def explained_variance(
    labels: npt.ArrayLike,
    values: npt.ArrayLike,
    *,
    valid: npt.ArrayLike | None = None,
    band_names: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Share of each band's variation that lies between segments, at pixel level.

    Per band, over the pixels used for that band (see the module docstring):

      - `SS_total` = sum of `(x - mean)^2`, with the mean of those same pixels;
      - `SS_within` = sum of `(x - mean of the pixel's segment)^2`;
      - `r2 = 1 - SS_within / SS_total`.

    1 means every segment is uniform; 0 means the segments explain nothing.
    This is the explained variance of Xiong et al. 2024, with the definition of
    `fmu.utils.components.explained_variance_r2`: computed from pixels, never
    from segment means alone (that would give 1 for any map), and with both
    sums taken over exactly the same pixels.

    Returns one row per band: `band, r2, ss_within, ss_total, n_pixels,
    n_segments`. `band` is the name given in `band_names`, or `band_0`,
    `band_1`, ... `n_segments` counts the segments with at least one used
    pixel in that band. It is in the same row on purpose: `r2` rises with the
    number of segments for any layer at all, and reaches 1 at one segment per
    pixel, so two maps with different numbers of segments are not compared by
    `r2` alone.

    Degenerate inputs: `r2` is `NaN` when no pixel is used or when the used
    pixels are all equal (`SS_total = 0`: there is no variation to explain);
    the sums are then 0. One segment gives 0. Shapes that do not match, an
    infinite value or labels that are not whole numbers raise `ValueError`.
    """
    lab, vals, names = _prepare(labels, values, valid, band_names)
    codes, classes = _compact(lab.reshape(-1))
    rows = []
    for name, x in zip(names, vals, strict=True):
        s = _band_sums(codes, classes.shape[0], x)
        r2 = 1.0 - s.ss_within / s.ss_total if s.ss_total > 0 else _NAN
        rows.append((name, r2, s.ss_within, s.ss_total, s.n_pixels, s.n_segments))
    return pd.DataFrame(rows, columns=EXPLAINED_VARIANCE_COLUMNS)


def weighted_variance(
    labels: npt.ArrayLike,
    values: npt.ArrayLike,
    *,
    valid: npt.ArrayLike | None = None,
    band_names: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Area-weighted variance inside segments (the within-segment term of Johnson and Xie 2011).

    Per band, `wvar = sum_k a_k v_k / sum_k a_k`, where `a_k` is the number of
    used pixels of segment `k` and `v_k` the variance of the band inside it
    (divisor `a_k`, so a one-pixel segment has variance 0). Large segments
    count in proportion to their area. This equals `SS_within / n_pixels`, so
    `r2 = 1 - wvar / (SS_total / n_pixels)`: it is the same information as
    `explained_variance`, in the units of the band squared and not divided by
    the band's overall variance. LOWER is better (more alike inside).

    Returns one row per band: `band, weighted_variance, n_pixels, n_segments`.

    Degenerate inputs: `NaN` when no pixel is used for the band; 0 when the
    used pixels are all equal. Like `r2`, it falls as the number of segments
    rises whatever the layer is; read it with `n_segments`.
    """
    lab, vals, names = _prepare(labels, values, valid, band_names)
    codes, classes = _compact(lab.reshape(-1))
    rows = []
    for name, x in zip(names, vals, strict=True):
        s = _band_sums(codes, classes.shape[0], x)
        wvar = s.ss_within / s.n_pixels if s.n_pixels > 0 else _NAN
        rows.append((name, wvar, s.n_pixels, s.n_segments))
    return pd.DataFrame(rows, columns=WEIGHTED_VARIANCE_COLUMNS)


# ---------------------------------------------------------------------------
# Adjacency and Moran's I
# ---------------------------------------------------------------------------


def _check_connectivity(connectivity: int) -> None:
    if connectivity not in (4, 8):
        raise ValueError(f"connectivity must be 4 or 8, got {connectivity!r}")


def _adjacent_pairs(lab: IntArray, connectivity: int) -> IntArray:
    """Unique adjacent pairs of the non-negative values of a 2-D array (no checks)."""
    slices = [
        (lab[:, :-1], lab[:, 1:]),  # left-right
        (lab[:-1, :], lab[1:, :]),  # up-down
    ]
    if connectivity == 8:
        slices.append((lab[:-1, :-1], lab[1:, 1:]))  # the two diagonals
        slices.append((lab[:-1, 1:], lab[1:, :-1]))
    lows, highs = [], []
    for a, b in slices:
        differ = (a != b) & (a >= 0) & (b >= 0)
        pa, pb = a[differ], b[differ]
        lows.append(np.minimum(pa, pb))
        highs.append(np.maximum(pa, pb))
    lo = np.concatenate(lows)
    hi = np.concatenate(highs)
    if lo.size == 0:
        return np.zeros((0, 2), dtype=np.int64)
    base = int(hi.max()) + 1
    if base < 2**31:
        keys = np.unique(lo * base + hi)
        return np.stack([keys // base, keys % base], axis=1).astype(np.int64)
    return np.unique(np.stack([lo, hi], axis=1), axis=0).astype(np.int64)


def segment_adjacency(labels: npt.ArrayLike, *, connectivity: Literal[4, 8] = 4) -> IntArray:
    """Which segments of a label raster are next to each other.

    Two segments are adjacent if a pixel of one is next to a pixel of the
    other. `connectivity=4` counts the four neighbours that share an edge with
    a pixel; `connectivity=8` also counts the four that touch it at a corner.
    Pixels with a label below 0 belong to no segment and make no adjacency, so
    two segments separated by a strip of such pixels are not adjacent.

    Returns an int64 array of shape `(m, 2)`: every adjacent pair `(a, b)` of
    label values once, with `a < b`, sorted by `a` then `b`. A raster with
    fewer than two segments, or with no two segments touching, returns shape
    `(0, 2)`. `labels` must be two-dimensional, else `ValueError`.
    """
    _check_connectivity(connectivity)
    lab = _as_labels(labels)
    if lab.ndim != 2:
        raise ValueError(f"labels must be a two-dimensional raster, got shape {lab.shape}")
    return _adjacent_pairs(lab, connectivity)


def _as_adjacency(adjacency: npt.ArrayLike, n_segments: int) -> IntArray:
    """Check a list of adjacent pairs and return it with each pair once, `a < b`."""
    adj = np.asarray(adjacency)
    if adj.size == 0:
        return np.zeros((0, 2), dtype=np.int64)
    if adj.ndim != 2 or adj.shape[1] != 2:
        raise ValueError(f"adjacency must have shape (m, 2), got {adj.shape}")
    if not np.issubdtype(adj.dtype, np.integer):
        raise ValueError(f"adjacency must hold integer segment codes, got dtype {adj.dtype}")
    adj = adj.astype(np.int64)
    if (adj < 0).any() or (adj >= n_segments).any():
        raise ValueError(f"adjacency names a segment outside 0..{n_segments - 1}")
    if (adj[:, 0] == adj[:, 1]).any():
        raise ValueError("adjacency holds a segment paired with itself")
    return np.unique(np.sort(adj, axis=1), axis=0)


def _morans_i(y: FloatArray, adj: IntArray) -> tuple[float, int, int]:
    """Moran's I with `(I, segments with a value, adjacent pairs used)`; no checks."""
    has = ~np.isnan(y)
    n = int(has.sum())
    if adj.shape[0]:
        adj = adj[has[adj[:, 0]] & has[adj[:, 1]]]
    m = int(adj.shape[0])
    if m == 0 or n < 2:
        return _NAN, n, m
    vals = y[has]
    if float(vals.min()) == float(vals.max()):
        return _NAN, n, m
    dev = y - float(vals.mean())
    denom = float(np.sum(dev[has] * dev[has]))
    if not denom > 0:
        return _NAN, n, m
    cross = float(np.sum(dev[adj[:, 0]] * dev[adj[:, 1]]))
    # (n / S0) * (2 * cross) / denom with S0 = 2 m: each pair counts in both directions.
    return n * cross / (m * denom), n, m


def morans_i(segment_values: npt.ArrayLike, adjacency: npt.ArrayLike) -> float:
    """Moran's I of one value per segment, between adjacent segments.

    `segment_values[k]` is the value of segment `k` (for a segmentation, the
    mean of a band inside the segment), `NaN` for a segment with no value.
    `adjacency` lists the adjacent pairs `(a, b)` of segment positions, as
    `segment_adjacency` returns for labels `0..K-1`. Weights are binary: 1 for
    an adjacent pair, 0 otherwise. Then (Moran 1950)

        I = (n / S0) * sum_{k != l} w_kl (y_k - ybar) (y_l - ybar) / sum_k (y_k - ybar)^2

    with `n` the number of segments that have a value, `ybar` their plain mean
    (every segment counts once, whatever its area) and `S0` the sum of the
    weights, which is twice the number of adjacent pairs because each pair
    counts in both directions.

    Reading it: near 1 when neighbouring segments are alike, which for a
    segmentation means one patch of forest was cut into several segments
    (over-segmentation); about 0 (exactly, `-1 / (n - 1)` on average) when
    neighbours are unrelated; negative when neighbours contrast. For a
    segmentation LOWER is better.

    Degenerate inputs: `NaN` when no adjacent pair has two values, when fewer
    than two segments have a value, or when the values are all equal. A pair
    given twice or in both orders counts once; pairs with a `NaN` segment are
    left out. A pair that names a segment outside the values, or a segment
    paired with itself, raises `ValueError`.
    """
    y = np.asarray(segment_values, dtype=np.float64)
    if y.ndim != 1:
        raise ValueError(f"segment_values must be one-dimensional, got shape {y.shape}")
    if np.isinf(y).any():
        raise ValueError("segment_values holds an infinite value")
    adj = _as_adjacency(adjacency, y.shape[0])
    return _morans_i(y, adj)[0]


@dataclass(frozen=True)
class _BandComponents:
    """The two components of the Global Score for one band of one segmentation."""

    n_pixels: int
    n_segments: int
    weighted_variance: float
    morans_i: float
    n_valued_segments: int
    n_adjacent_pairs: int


def _components(lab: IntArray, vals: FloatArray, connectivity: int) -> list[_BandComponents]:
    """Weighted variance and Moran's I of every band for one 2-D label raster."""
    codes, classes = _compact(lab.reshape(-1))
    adj = _adjacent_pairs(codes.reshape(lab.shape), connectivity)
    out = []
    for x in vals:
        s = _band_sums(codes, classes.shape[0], x)
        i_value, n_valued, n_adj = _morans_i(s.means, adj)
        wvar = s.ss_within / s.n_pixels if s.n_pixels > 0 else _NAN
        out.append(_BandComponents(s.n_pixels, s.n_segments, wvar, i_value, n_valued, n_adj))
    return out


def segment_morans_i(
    labels: npt.ArrayLike,
    values: npt.ArrayLike,
    *,
    valid: npt.ArrayLike | None = None,
    connectivity: Literal[4, 8] = 4,
    band_names: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Moran's I of the segment means of each band, between adjacent segments.

    For each band: the mean of the band inside every segment (over the pixels
    used for that band), then `morans_i` of those means with the adjacency of
    `segment_adjacency`. This is the between-segment term of Johnson and Xie
    2011. `labels` must be a two-dimensional raster. Pixels masked out by
    `valid` belong to no segment, for the means and for the adjacency alike.

    Returns one row per band: `band, morans_i, n_segments, n_adjacent_pairs`,
    where `n_segments` counts the segments that have a mean in that band and
    `n_adjacent_pairs` the adjacent pairs among them.

    Degenerate inputs: `morans_i` is `NaN` when there is no adjacent pair, one
    segment only, or all segment means are equal. A segment with no value in a
    band is left out of that band only.
    """
    _check_connectivity(connectivity)
    lab, vals, names = _prepare(labels, values, valid, band_names)
    if lab.ndim != 2:
        raise ValueError(f"labels must be a two-dimensional raster, got shape {lab.shape}")
    rows = [
        (name, c.morans_i, c.n_valued_segments, c.n_adjacent_pairs)
        for name, c in zip(names, _components(lab, vals, connectivity), strict=True)
    ]
    return pd.DataFrame(rows, columns=MORANS_I_COLUMNS)


# ---------------------------------------------------------------------------
# Global Score
# ---------------------------------------------------------------------------


# Two values of a component closer than this are the same value: the difference
# is rounding, not a difference between maps. A rounding allowance, not a setting.
_EQUAL_RTOL = 1e-9
_EQUAL_ATOL = 1e-12


def _min_max(x: FloatArray) -> FloatArray:
    """`(x - min) / (max - min)` over the values that are not `NaN`.

    All 0 when the values are equal. All `NaN` when fewer than two values are
    defined: one value cannot be placed between a best and a worst.

    "Equal" means equal up to rounding (`_EQUAL_RTOL`, `_EQUAL_ATOL`). Without
    that, two candidates that are the same map with its segments numbered
    differently can differ in the last binary digit of a component, and the
    rescaling would stretch that digit to the full range from 0 to 1.
    """
    out = np.full(x.shape, np.nan, dtype=np.float64)
    ok = ~np.isnan(x)
    if int(ok.sum()) < 2:
        return out
    lo, hi = float(x[ok].min()), float(x[ok].max())
    if hi - lo <= _EQUAL_RTOL * max(abs(lo), abs(hi)) + _EQUAL_ATOL:
        out[ok] = 0.0
    else:
        out[ok] = np.clip((x[ok] - lo) / (hi - lo), 0.0, 1.0)
    return out


def global_score(
    segmentations: Mapping[str, Any] | Sequence[Any],
    values: npt.ArrayLike,
    *,
    valid: npt.ArrayLike | None = None,
    connectivity: Literal[4, 8] = 4,
    band_names: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Global Score of each of a SET of candidate segmentations (Johnson and Xie 2011).

    The score ranks candidate segmentations of the same area against each
    other. It has no meaning for one segmentation alone. For each band `b` and
    candidate `c`:

      - `weighted_variance` (see `weighted_variance`): low when segments are
        uniform inside, which favours many small segments;
      - `morans_i` (see `segment_morans_i`): low when neighbouring segments
        differ, which favours few large segments;
      - each is rescaled over the candidates to run from 0 (the best candidate
        on that component) to 1 (the worst):
        `x_norm = (x - min over candidates) / (max over candidates - min)`;
      - `global_score = weighted_variance_norm + morans_i_norm`.

    LOWER is better; the range is 0 to 2.

    **The score depends on which candidates are in the set** (Böck et al.
    2017): adding or removing one candidate moves the minimum or maximum and so
    changes every score, and can change the order. So the set must be declared
    before it is scored, and the raw `weighted_variance` and `morans_i` are
    returned beside the score and should be reported with it.

    Parameters
    ----------
    segmentations
        A mapping name -> 2-D label raster, or a sequence of rasters (named
        `"0"`, `"1"`, ...), all of one shape.
    values, valid, band_names
        As in the module docstring. All candidates are scored on the same
        pixels: a pixel is used only if it is valid and has a segment in EVERY
        candidate.

    Returns
    -------
    pandas.DataFrame
        Columns `segmentation, band, n_segments, weighted_variance, morans_i,
        weighted_variance_norm, morans_i_norm, global_score`. Candidates are
        in the order given. Each candidate has one row per band, in band
        order, followed by one row with `band = "mean"`: the plain mean of its
        per-band rows (of every numeric column), which gives each band the
        same say because the normalised columns have no units.

    Degenerate inputs
    -----------------
    With one candidate the raw columns are filled and the three normalised
    columns are `NaN`. A component that is equal for all candidates is
    normalised to 0 for all. A candidate whose component is not defined (for
    example Moran's I of a single segment) has `NaN` there and a `NaN` score,
    and is left out of the minimum and maximum; if fewer than two candidates
    have the component, its normalised value is `NaN` for all. A `"mean"` row
    is `NaN` wherever one of its bands is. An empty set, rasters of different
    shapes, rasters that are not 2-D, or a band named `"mean"` raise
    `ValueError`.
    """
    _check_connectivity(connectivity)
    if isinstance(segmentations, Mapping):
        names = [str(k) for k in segmentations]
        rasters = list(segmentations.values())
    else:
        if isinstance(segmentations, np.ndarray) and segmentations.ndim < 3:
            raise ValueError(
                "segmentations must be a mapping or a sequence of 2-D label rasters; "
                "wrap a single raster in a list"
            )
        rasters = list(segmentations)
        names = [str(k) for k in range(len(rasters))]
    if not rasters:
        raise ValueError("no candidate segmentation was given")
    if len(set(names)) != len(names):
        raise ValueError("segmentation names must be distinct")
    labs = [_as_labels(r, f"segmentations[{name!r}]") for name, r in zip(names, rasters, strict=True)]
    shape = labs[0].shape
    if len(shape) != 2:
        raise ValueError(f"each segmentation must be a two-dimensional raster, got shape {shape}")
    for name, lab in zip(names, labs, strict=True):
        if lab.shape != shape:
            raise ValueError(
                f"segmentation {name!r} has shape {lab.shape}; the first has shape {shape}"
            )

    # One set of pixels for every candidate.
    common: BoolArray = np.ones(shape, dtype=bool)
    for lab in labs:
        common &= lab >= 0
    first, vals, bands = _prepare(labs[0], values, valid, band_names)
    if MEAN_ROW in bands:
        raise ValueError(f"a band may not be named {MEAN_ROW!r}; that name is used for the mean row")
    common &= first >= 0  # brings in `valid`

    n_cand, n_bands = len(labs), len(bands)
    n_seg = np.zeros((n_cand, n_bands), dtype=np.float64)
    wvar = np.full((n_cand, n_bands), np.nan, dtype=np.float64)
    moran = np.full((n_cand, n_bands), np.nan, dtype=np.float64)
    for c, lab in enumerate(labs):
        for b, comp in enumerate(_components(np.where(common, lab, -1), vals, connectivity)):
            n_seg[c, b] = comp.n_segments
            wvar[c, b] = comp.weighted_variance
            moran[c, b] = comp.morans_i

    wvar_norm = np.full((n_cand, n_bands), np.nan, dtype=np.float64)
    moran_norm = np.full((n_cand, n_bands), np.nan, dtype=np.float64)
    if n_cand > 1:
        for b in range(n_bands):
            wvar_norm[:, b] = _min_max(wvar[:, b])
            moran_norm[:, b] = _min_max(moran[:, b])
    score = wvar_norm + moran_norm

    columns = (n_seg, wvar, moran, wvar_norm, moran_norm, score)
    rows: list[tuple[Any, ...]] = []
    for c, name in enumerate(names):
        for b, band in enumerate(bands):
            rows.append((name, band, *(float(col[c, b]) for col in columns)))
        rows.append((name, MEAN_ROW, *(float(col[c].mean()) for col in columns)))
    return pd.DataFrame(rows, columns=GLOBAL_SCORE_COLUMNS)

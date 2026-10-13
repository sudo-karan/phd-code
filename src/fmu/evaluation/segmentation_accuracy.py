"""Stand maps against reference polygons (compartment maps and the like).

Two questions, both answered with geometry only:

  - **Do the stands have the right size and place?** `segmentation_accuracy`
    gives over-segmentation (a reference polygon is cut into several stands),
    under-segmentation (a stand runs across the edge of a reference polygon)
    and their combination `d`, for every matched pair of a reference polygon
    and a stand, per reference polygon, and summarised (Clinton et al. 2010).
  - **Do the stand boundaries lie where the reference boundaries lie?**
    `boundary_match` gives boundary precision, recall and F within a distance
    tolerance declared by the caller (the measures of Martin et al. 2004, in a
    buffer form for vector boundaries).

Inputs are sequences of shapely polygons or multipolygons in ONE projected
coordinate system (metres). Nothing here knows about any site, and nothing is
tuned: the tolerance has no default, and the sliver threshold defaults to 0.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import shapely
from shapely.geometry.base import BaseGeometry

from fmu.evaluation._common import FloatArray, IntArray

_POLYGON_TYPE_IDS = (3, 6)  # shapely type ids of Polygon and MultiPolygon

PAIR_COLUMNS = [
    "reference",
    "stand",
    "intersection_area",
    "reference_area",
    "stand_area",
    "over",
    "under",
    "d",
]
PER_REFERENCE_COLUMNS = ["reference", "reference_area", "n_matched", "over", "under", "d"]
SUMMARY_KEYS = [
    "over",
    "under",
    "d",
    "over_per_reference",
    "under_per_reference",
    "d_per_reference",
    "over_area_weighted",
    "under_area_weighted",
    "d_area_weighted",
    "n_references",
    "n_stands",
    "n_pairs",
    "n_unmatched_references",
]


# ---------------------------------------------------------------------------
# Input handling
# ---------------------------------------------------------------------------


def _as_polygons(geometries: Any, name: str) -> tuple[np.ndarray, IntArray]:
    """Return `(polygons, positions)` for a sequence of shapely geometries.

    `polygons` is an object array of the geometries that are not empty, and
    `positions[k]` is the place of `polygons[k]` in the input sequence, so that
    results can name a polygon by where the caller put it. Empty geometries are
    dropped. Anything that is not a shapely polygon or multipolygon, and any
    invalid geometry (self-crossing rings and the like), raises `ValueError`:
    areas and intersections of an invalid polygon are not defined.
    """
    if isinstance(geometries, BaseGeometry):
        raise ValueError(f"{name} must be a sequence of polygons, not a single geometry")
    items = list(geometries)
    for k, g in enumerate(items):
        if not isinstance(g, BaseGeometry):
            raise ValueError(
                f"{name}[{k}] is not a shapely geometry (got {type(g).__name__})"
            )
    arr = np.empty(len(items), dtype=object)
    arr[:] = items
    if arr.size == 0:
        return arr, np.zeros(0, dtype=np.int64)
    keep = ~np.asarray(shapely.is_empty(arr), dtype=bool)
    positions = np.flatnonzero(keep).astype(np.int64)
    arr = arr[keep]
    if arr.size == 0:
        return arr, positions
    type_ids = np.asarray(shapely.get_type_id(arr))
    wrong = ~np.isin(type_ids, _POLYGON_TYPE_IDS)
    if wrong.any():
        first = int(positions[np.flatnonzero(wrong)[0]])
        raise ValueError(
            f"{name}[{first}] is a {arr[np.flatnonzero(wrong)[0]].geom_type}; "
            "only polygons and multipolygons have an area to compare"
        )
    invalid = ~np.asarray(shapely.is_valid(arr), dtype=bool)
    if invalid.any():
        first_local = int(np.flatnonzero(invalid)[0])
        raise ValueError(
            f"{int(invalid.sum())} invalid geometr{'y' if invalid.sum() == 1 else 'ies'} in "
            f"{name} (first: {name}[{int(positions[first_local])}], "
            f"{shapely.is_valid_reason(arr[first_local])}); repair them before comparing"
        )
    return arr, positions


def _nanmean(values: FloatArray) -> float:
    """Mean of the values that are not `NaN`; `NaN` if there is none."""
    ok = ~np.isnan(values)
    return float(values[ok].mean()) if ok.any() else float("nan")


def _weighted_nanmean(values: FloatArray, weights: FloatArray) -> float:
    """Weighted mean over the values that are not `NaN`; `NaN` if the weights sum to 0."""
    ok = ~np.isnan(values)
    total = float(weights[ok].sum())
    if total <= 0:
        return float("nan")
    return float((values[ok] * weights[ok]).sum() / total)


# ---------------------------------------------------------------------------
# Over- and under-segmentation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SegmentationAccuracy:
    """Over- and under-segmentation of a stand map against reference polygons.

    `pairs`: one row per matched (reference, stand) pair. `per_reference`: one
    row per reference polygon. `summary`: the numbers to report, with the
    counts they rest on. See `segmentation_accuracy` for every column and key.
    Results only: no run times, dates or machine names.
    """

    pairs: pd.DataFrame
    per_reference: pd.DataFrame
    summary: dict[str, float]


def segmentation_accuracy(
    stands: Any, references: Any, *, min_overlap_fraction: float = 0.0
) -> SegmentationAccuracy:
    """Over-segmentation, under-segmentation and their combination (Clinton et al. 2010).

    For a reference polygon `x` and a stand `y` that overlap with intersection
    area `A > 0`:

      - `over = 1 - A / area(x)`: the share of the reference polygon that this
        stand does NOT cover. High when the reference is cut into many stands.
      - `under = 1 - A / area(y)`: the share of the stand that lies OUTSIDE the
        reference polygon. High when a stand runs across the reference edge.
      - `d = sqrt((over^2 + under^2) / 2)`: the two combined.

    All three are 0 for a stand identical to the reference polygon, lie in
    `[0, 1)`, and LOWER is better.

    **Which stands are compared with a reference polygon.** A stand is matched
    to a reference polygon when they overlap (`A > 0`; touching along an edge
    is not overlap) and at least one of these holds: the centroid of the
    reference lies in the stand; the centroid of the stand lies in the
    reference; the overlap is more than half of the stand; the overlap is more
    than half of the reference. A stand can be matched to several reference
    polygons and a reference polygon to several stands.

    `min_overlap_fraction` (default 0, which changes nothing) also requires
    `A / min(area(x), area(y)) > min_overlap_fraction`. It exists to drop
    slivers left by digitising. It must be declared before the comparison is
    run, never tuned on a result.

    Parameters
    ----------
    stands, references
        Sequences of shapely polygons or multipolygons, in one projected
        coordinate system (areas in square metres).

    Returns
    -------
    SegmentationAccuracy
        `pairs`, sorted by reference then stand, with columns `reference,
        stand, intersection_area, reference_area, stand_area, over, under, d`.
        `reference` and `stand` are positions in the input sequences.

        `per_reference`, one row per (non-empty) reference polygon in input
        order: `reference, reference_area, n_matched, over, under, d`, the
        three being plain means over that polygon's matched pairs.

        `summary`:

          - `over, under, d`: means over ALL matched pairs. A reference polygon
            cut into ten stands counts ten times.
          - `over_per_reference, under_per_reference, d_per_reference`: means
            of the per-reference values, so each reference polygon counts once.
          - `over_area_weighted, under_area_weighted, d_area_weighted`: the
            per-reference values weighted by reference area.
          - `n_references, n_stands` (polygons used, empty ones left out),
            `n_pairs`, `n_unmatched_references`.

    Degenerate inputs
    -----------------
    A reference polygon with no matched stand has `n_matched = 0`, `over = 1`
    (none of it is covered by a matching stand) and `under = d = NaN` (there is
    no stand to measure). It enters `over_per_reference` and
    `over_area_weighted` as 1 and is left out of the `under` and `d` means, so
    read those two beside `n_unmatched_references`. If no pair is matched at
    all, the nine measures are all `NaN` (nothing was compared: check that the
    two layers are in the same coordinate system) and the counts are still
    given. Empty geometries are dropped. An invalid geometry, or one that is
    not a polygon, raises `ValueError`.
    """
    frac = float(min_overlap_fraction)
    if not (0.0 <= frac < 1.0):
        raise ValueError(f"min_overlap_fraction must lie in [0, 1), got {min_overlap_fraction!r}")
    stand_geoms, stand_pos = _as_polygons(stands, "stands")
    ref_geoms, ref_pos = _as_polygons(references, "references")
    n_ref, n_stand = int(ref_geoms.size), int(stand_geoms.size)
    ref_area = np.asarray(shapely.area(ref_geoms), dtype=np.float64).reshape(n_ref)
    stand_area = np.asarray(shapely.area(stand_geoms), dtype=np.float64).reshape(n_stand)

    ri = np.zeros(0, dtype=np.int64)
    si = np.zeros(0, dtype=np.int64)
    inter = np.zeros(0, dtype=np.float64)
    if n_ref and n_stand:
        tree = shapely.STRtree(stand_geoms)
        cand_ref, cand_stand = tree.query(ref_geoms, predicate="intersects")
        cand_ref = np.asarray(cand_ref, dtype=np.int64)
        cand_stand = np.asarray(cand_stand, dtype=np.int64)
        order = np.lexsort((cand_stand, cand_ref))
        cand_ref, cand_stand = cand_ref[order], cand_stand[order]
        x, y = ref_geoms[cand_ref], stand_geoms[cand_stand]
        area = np.asarray(shapely.area(shapely.intersection(x, y)), dtype=np.float64)
        ax, ay = ref_area[cand_ref], stand_area[cand_stand]
        with np.errstate(divide="ignore", invalid="ignore"):
            share_ref = area / ax
            share_stand = area / ay
            share_min = area / np.minimum(ax, ay)
        matched = (area > 0) & (
            np.asarray(shapely.covers(y, shapely.centroid(x)), dtype=bool)
            | np.asarray(shapely.covers(x, shapely.centroid(y)), dtype=bool)
            | (share_stand > 0.5)
            | (share_ref > 0.5)
        )
        matched &= share_min > frac
        ri, si, inter = cand_ref[matched], cand_stand[matched], area[matched]

    # Clipped because an intersection can exceed its parent's area in the last bit.
    over = np.clip(1.0 - inter / ref_area[ri], 0.0, 1.0)
    under = np.clip(1.0 - inter / stand_area[si], 0.0, 1.0)
    d = np.sqrt((over**2 + under**2) / 2.0)
    pairs = pd.DataFrame(
        {
            "reference": ref_pos[ri],
            "stand": stand_pos[si],
            "intersection_area": inter,
            "reference_area": ref_area[ri],
            "stand_area": stand_area[si],
            "over": over,
            "under": under,
            "d": d,
        },
        columns=PAIR_COLUMNS,
    )

    n_matched = np.bincount(ri, minlength=n_ref).astype(np.int64)
    has = n_matched > 0
    per_ref_values: dict[str, FloatArray] = {}
    for key, col in (("over", over), ("under", under), ("d", d)):
        sums = np.bincount(ri, weights=col, minlength=n_ref)
        mean = np.full(n_ref, np.nan, dtype=np.float64)
        mean[has] = sums[has] / n_matched[has]
        per_ref_values[key] = mean
    per_ref_values["over"][~has] = 1.0
    per_reference = pd.DataFrame(
        {
            "reference": ref_pos,
            "reference_area": ref_area,
            "n_matched": n_matched,
            "over": per_ref_values["over"],
            "under": per_ref_values["under"],
            "d": per_ref_values["d"],
        },
        columns=PER_REFERENCE_COLUMNS,
    )

    summary = {key: float("nan") for key in SUMMARY_KEYS}
    if ri.size:
        for key, col in (("over", over), ("under", under), ("d", d)):
            summary[key] = float(col.mean())
            summary[f"{key}_per_reference"] = _nanmean(per_ref_values[key])
            summary[f"{key}_area_weighted"] = _weighted_nanmean(per_ref_values[key], ref_area)
    summary["n_references"] = float(n_ref)
    summary["n_stands"] = float(n_stand)
    summary["n_pairs"] = float(ri.size)
    summary["n_unmatched_references"] = float(int((~has).sum()))
    return SegmentationAccuracy(pairs=pairs, per_reference=per_reference, summary=summary)


# ---------------------------------------------------------------------------
# Boundary match
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BoundaryMatch:
    """Boundary precision, recall and F within a distance tolerance.

    Lengths are in the units of the coordinate system (metres), after `ignore`
    was taken out. `matched_stand_length` is the length of stand boundary that
    lies within `tolerance` of a reference boundary, and
    `matched_reference_length` the reverse. See `boundary_match`.
    """

    precision: float
    recall: float
    f: float
    tolerance: float
    stand_boundary_length: float
    reference_boundary_length: float
    matched_stand_length: float
    matched_reference_length: float


def _boundary_lines(polygons: np.ndarray, ignore: BaseGeometry | None) -> BaseGeometry:
    """All boundaries of the polygons as one line geometry, each edge once."""
    if polygons.size == 0:
        return shapely.LineString()
    lines = shapely.union_all(shapely.boundary(polygons))
    if ignore is not None:
        lines = shapely.difference(lines, ignore)
    return lines


def boundary_match(
    stands: Any, references: Any, tolerance: float, *, ignore: Any = None
) -> BoundaryMatch:
    """Share of boundary length that the two maps have in common, within a tolerance.

    `B_s` is the set of all stand boundaries and `B_r` the set of all reference
    boundaries. An edge shared by two neighbouring polygons counts once. Then

      - precision = length of `B_s` within `tolerance` of `B_r`, over the
        length of `B_s`: how much of what the map draws is also in the
        reference;
      - recall = length of `B_r` within `tolerance` of `B_s`, over the length
        of `B_r`: how much of the reference the map found;
      - `f = 2 * precision * recall / (precision + recall)`, 0 if both are 0.

    "Within tolerance" is computed with a buffer: the part of `B_s` inside
    `buffer(B_r, tolerance)`, and the reverse (buffers with 16 segments per
    quarter circle, so a matched length at a corner is short by well under
    1 per cent of the tolerance). HIGHER is better; all three lie in `[0, 1]`.

    Precision, recall and F for boundaries follow Martin et al. 2004, who
    define them for boundary pixels of images and match each detected pixel to
    at most one reference pixel. This buffer form for vector boundaries is an
    adaptation, and it has no one-to-one matching: two stand boundaries
    running side by side inside the tolerance of one reference boundary both
    count as matched. So a map with many more boundaries than the reference
    can keep a high recall, and precision is the number that shows it. Read
    the two together.

    Parameters
    ----------
    stands, references
        Sequences of shapely polygons or multipolygons, one projected
        coordinate system.
    tolerance
        Distance in metres, greater than 0. Required, with no default: the
        caller declares it before the comparison (for example the positional
        accuracy of the reference map). It is never chosen by what scores best.
    ignore
        Optional geometry (or sequence of geometries) whose area is taken out
        of both boundary sets first. Usually a thin buffer round the outer
        edge of the study area: both maps share that edge, so it would count
        as a perfect match and raise every score.

    Degenerate inputs
    -----------------
    Precision is `NaN` if there is no stand boundary left, recall is `NaN` if
    there is no reference boundary left, and `f` is `NaN` if either is. With
    stand boundaries but no reference boundary, precision is 0 (nothing the
    map draws is in the reference). Empty geometries are dropped; an invalid
    or non-polygon geometry, or a tolerance that is not a positive finite
    number, raises `ValueError`.
    """
    tol = float(tolerance)
    if not (math.isfinite(tol) and tol > 0):
        raise ValueError(f"tolerance must be a positive, finite distance, got {tolerance!r}")
    stand_geoms, _ = _as_polygons(stands, "stands")
    ref_geoms, _ = _as_polygons(references, "references")

    ignore_geom: BaseGeometry | None = None
    if ignore is not None:
        if isinstance(ignore, BaseGeometry):
            ignore_geom = ignore
        else:
            parts = list(ignore)
            if not all(isinstance(g, BaseGeometry) for g in parts):
                raise ValueError("ignore must be a shapely geometry or a sequence of them")
            holder = np.empty(len(parts), dtype=object)
            holder[:] = parts
            ignore_geom = shapely.union_all(holder)
        if not bool(shapely.is_valid(ignore_geom)):
            raise ValueError("ignore is not a valid geometry")

    b_s = _boundary_lines(stand_geoms, ignore_geom)
    b_r = _boundary_lines(ref_geoms, ignore_geom)
    len_s = float(shapely.length(b_s))
    len_r = float(shapely.length(b_r))

    matched_s = 0.0
    matched_r = 0.0
    if len_s > 0 and len_r > 0:
        near_r = shapely.buffer(b_r, tol, quad_segs=16)
        near_s = shapely.buffer(b_s, tol, quad_segs=16)
        matched_s = min(float(shapely.length(shapely.intersection(b_s, near_r))), len_s)
        matched_r = min(float(shapely.length(shapely.intersection(b_r, near_s))), len_r)

    precision = matched_s / len_s if len_s > 0 else float("nan")
    recall = matched_r / len_r if len_r > 0 else float("nan")
    if math.isnan(precision) or math.isnan(recall):
        f = float("nan")
    elif precision + recall == 0:
        f = 0.0
    else:
        f = 2.0 * precision * recall / (precision + recall)
    return BoundaryMatch(
        precision=precision,
        recall=recall,
        f=f,
        tolerance=tol,
        stand_boundary_length=len_s,
        reference_boundary_length=len_r,
        matched_stand_length=matched_s,
        matched_reference_length=matched_r,
    )

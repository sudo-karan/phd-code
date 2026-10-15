"""Small raster and vector helpers shared by the scripts that prepare the demo data.

A library, not a tool: there is no command line. Two kinds of script import it:

  - the re-merge of superpixels into stands, which has to turn a raster of stand ids into
    stand polygons and to say how two stand maps differ;
  - the export of map layers for the static explorer page (Leaflet), which needs PNGs in
    web-map projection with their corner coordinates, and small GeoJSON files.

Import it the way the scripts import each other, through sys.path:

    sys.path.insert(0, str(REPO / "scripts"))
    import raster_vector_tools as rvt

READS AND WRITES. Only what the caller names: read_raster reads one GeoTIFF, write_web_png
writes one PNG and write_geojson one GeoJSON file. Everything else works on arrays and
geometries in memory. Nothing written here carries a date or a run time, and the same input
gives the same bytes.

EARTH ENGINE IS NOT USED, and nothing here opens a network connection. Importing this module
does import scripts/transparency_masking.py (for its display stretch) and
scripts/compare_stand_runs.py (for its polygon repair), and with the first the fmu package;
neither starts Earth Engine. matplotlib is not used. Pillow is needed by write_web_png only
and is imported there.

Nothing here is specific to a site.

THE RASTERS these functions expect
  One GeoTIFF per part of a ROI. Stand ids and superpixel labels are int32 on a UTM grid at
  10 m. Stand ids start at 0 and their no-data value is -1. Superpixel labels are arbitrary
  signed int32 values, so no value is free to mean "no data": they come with a separate
  validity array. That is why every function below takes `valid` (True where the pixel
  counts) instead of a no-data value. Feature and mask rasters are on EPSG:4326.
  An array is [rows, cols], row 0 at the top; `transform` is the affine transform of the
  raster (pixel corner to map coordinate), as rasterio returns it.

WHAT IS HERE
  Reading       read_raster
  Polygons      vectorise_labels, pixel_counts, to_lonlat
  Comparing     partition_report (are two label rasters the same partition?),
                change_report (what changed between two stand maps), changed_mask
  Several parts stack_parts, labels_in_several_parts, change_report_parts,
                merge_part_reports, mosaic_parts
  Sampling      sample_at_xy, sample_at_lonlat
  Display       outline_mask, categorical_rgba, continuous_rgba, rgb_rgba
  Writing       web_canvas, write_web_png, round_geometry, write_geojson

  Already in scripts/transparency_masking.py, and not repeated here: stretch_limits (the
  percentiles for a true-colour stretch), inside_mask (pixel centre inside a polygon),
  pixel_size_deg and snapped_bounds (the EPSG:4326 download grid).
"""

from __future__ import annotations

import json
import math
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any, NamedTuple

import numpy as np
import rasterio
import shapely
from affine import Affine
from pyproj import CRS, Transformer
from rasterio import crs as rio_crs
from rasterio import features as rio_features
from rasterio import warp as rio_warp
from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compare_stand_runs import _polygonal as polygonal_part  # noqa: E402
from transparency_masking import stretch_rgb  # noqa: E402

WEB_MERCATOR = "EPSG:3857"
LONLAT = "EPSG:4326"
# partition_report lists at most this many mismatching pairs of labels
MAX_EXAMPLES = 20
# A polygon traced along pixel edges must have exactly the area of its pixels. Coordinates are
# floats, so "exactly" means to this relative tolerance.
AREA_REL_TOL = 1e-6
# Parts of one ROI lie on one grid: their origins differ by whole pixels. Read back from
# files, "whole" means to within this fraction of a pixel.
GRID_TOL_PIXELS = 1e-3

_HEX = re.compile(r"#?([0-9a-fA-F]{6})")


# --------------------------------------------------------------------------- reading
class Raster(NamedTuple):
    """What read_raster returns. Unpacks as (array, transform, crs, nodata, descriptions)."""

    array: np.ndarray  # [rows, cols] for one band, [bands, rows, cols] for several
    transform: Affine
    crs: Any  # a rasterio CRS, or None if the file has none
    nodata: float | None
    descriptions: tuple[str | None, ...]  # one per band, None where the band has no name


def read_raster(path: Path | str) -> Raster:
    """Read a whole GeoTIFF. One band comes back as [rows, cols], several as [bands, rows, cols].

    The values are returned as stored: no-data pixels keep the no-data value, nothing is
    masked or scaled."""
    with rasterio.open(path) as src:
        array = src.read()
        if src.count == 1:
            array = array[0]
        return Raster(array, src.transform, src.crs, src.nodata, tuple(src.descriptions))


# --------------------------------------------------------------------------- small checks
def _as_valid(valid: Any, shape_hw: tuple[int, ...]) -> np.ndarray:
    """`valid` as a bool array of the given shape. None means every pixel counts."""
    if valid is None:
        return np.ones(shape_hw, dtype=bool)
    out = np.asarray(valid)
    if out.dtype != bool:
        raise TypeError(f"valid must be a bool array, got {out.dtype}.")
    if out.shape != tuple(shape_hw):
        raise ValueError(f"valid has shape {out.shape}, the raster has {tuple(shape_hw)}.")
    return out


def _as_labels(labels: Any, name: str = "labels") -> np.ndarray:
    out = np.asarray(labels)
    if not np.issubdtype(out.dtype, np.integer):
        raise TypeError(f"{name} must be whole numbers, got {out.dtype}.")
    return out


def _rio_crs(crs: Any) -> rio_crs.CRS:
    return crs if isinstance(crs, rio_crs.CRS) else rio_crs.CRS.from_user_input(crs)


def _crs_wkt(crs: Any) -> str:
    """A CRS given as a rasterio or pyproj object, an EPSG number or a string, as WKT."""
    if isinstance(crs, rio_crs.CRS):
        return crs.to_wkt()
    return CRS.from_user_input(crs).to_wkt()


@lru_cache(maxsize=32)
def _transformer(from_wkt: str, to_wkt: str) -> Transformer:
    return Transformer.from_crs(CRS.from_wkt(from_wkt), CRS.from_wkt(to_wkt), always_xy=True)


def _pixel_area(transform: Affine) -> float:
    """Area of one pixel in the square of the raster's map unit (square metres on UTM)."""
    return abs(transform.a * transform.e - transform.b * transform.d)


# --------------------------------------------------------------------------- polygons
def pixel_counts(labels: np.ndarray, valid: np.ndarray | None) -> dict[int, int]:
    """Number of valid pixels under each label, in label order."""
    labels = _as_labels(labels)
    values, counts = np.unique(labels[_as_valid(valid, labels.shape)], return_counts=True)
    return {int(v): int(n) for v, n in zip(values, counts, strict=True)}


def vectorise_labels(
    labels: np.ndarray,
    transform: Affine,
    crs: Any = None,
    *,
    valid: np.ndarray | None,
    connectivity: int = 8,
) -> dict[int, BaseGeometry]:
    """One geometry per label: the outline of its valid pixels, along the pixel edges.

    Returns {label: Polygon or MultiPolygon}, in label order, in the raster's own coordinates
    (`transform` decides them; `crs` is not needed for the tracing and is accepted only so
    that the call reads like the others: pass the same value on to to_lonlat). Nothing is
    simplified or smoothed, so a geometry covers exactly its pixels: its area is the pixel
    count times the pixel area. This is checked for every label, and a ValueError says which
    label fails.

    Every piece of a label goes into the one geometry of that label, however far apart the
    pieces lie. Pieces that share an edge become one polygon; pieces that only touch at a
    corner, or do not touch, become the parts of a MultiPolygon. Every geometry is valid.

    `connectivity` (4 or 8) is how the pieces are traced: with 8, pixels touching at a corner
    are traced as one ring that touches itself, which is then repaired into valid parts.
    The result covers the same pixels either way.
    """
    if connectivity not in (4, 8):
        raise ValueError("connectivity must be 4 or 8.")
    labels = _as_labels(labels)
    if labels.ndim != 2:
        raise ValueError(f"labels must be [rows, cols], got shape {labels.shape}.")
    valid = _as_valid(valid, labels.shape)
    if labels.dtype != np.int32:
        inside = labels[valid]
        info = np.iinfo(np.int32)
        if inside.size and (inside.min() < info.min or inside.max() > info.max):
            raise ValueError("labels do not fit in int32, which is what the tracing reads.")
        labels = np.where(valid, labels, 0).astype(np.int32)

    pieces: dict[int, list[BaseGeometry]] = {}
    traced = rio_features.shapes(
        np.ascontiguousarray(labels), mask=valid, connectivity=connectivity, transform=transform
    )
    for geom_json, value in traced:
        piece = polygonal_part(shape(geom_json))
        if piece is not None:
            pieces.setdefault(int(value), []).append(piece)

    counts = pixel_counts(labels, valid)
    area = _pixel_area(transform)
    out: dict[int, BaseGeometry] = {}
    for label in sorted(counts):
        parts = pieces.get(label, [])
        geom = polygonal_part(shapely.union_all(parts)) if parts else None
        expected = counts[label] * area
        got = 0.0 if geom is None else float(geom.area)
        if geom is None or not math.isclose(got, expected, rel_tol=AREA_REL_TOL):
            raise ValueError(
                f"label {label}: the traced outline has area {got!r}, its {counts[label]} "
                f"pixels have {expected!r}."
            )
        out[label] = geom
    return out


def to_lonlat(geometry: BaseGeometry, crs: Any) -> BaseGeometry:
    """A geometry in `crs` as longitude and latitude (EPSG:4326, x is longitude).

    Every vertex is converted, none is added or dropped, and nothing is rounded: rounding is
    write_geojson's job. Pixel edges are short, so the straight line between two converted
    vertices is the converted edge to well under a millimetre."""
    tr = _transformer(_crs_wkt(crs), _crs_wkt(LONLAT))

    def convert(xy: np.ndarray) -> np.ndarray:
        lon, lat = tr.transform(xy[:, 0], xy[:, 1])
        return np.column_stack([lon, lat])

    return shapely.transform(geometry, convert)


# --------------------------------------------------------------------------- comparing
class _Overlay(NamedTuple):
    """Two label arrays laid over each other, on the valid pixels only.

    A "pair" is one combination (label of a, label of b) that occurs on at least one pixel."""

    labels_a: np.ndarray  # the distinct labels of a, ascending
    labels_b: np.ndarray
    size_a: np.ndarray  # pixels under each label of a
    size_b: np.ndarray
    pair_a: np.ndarray  # per pair: index into labels_a
    pair_b: np.ndarray  # per pair: index into labels_b
    pair_n: np.ndarray  # per pair: pixels carrying this pair
    pixel_pair: np.ndarray  # per valid pixel: index of its pair
    same_values: bool  # a and b hold the same value at every valid pixel


def _overlay(a: np.ndarray, b: np.ndarray, valid: np.ndarray | None) -> _Overlay:
    a, b = _as_labels(a, "a"), _as_labels(b, "b")
    if a.shape != b.shape:
        raise ValueError(f"the two label arrays differ in shape: {a.shape} and {b.shape}.")
    valid = _as_valid(valid, a.shape)
    va, vb = a[valid], b[valid]
    labels_a, ia = np.unique(va, return_inverse=True)
    labels_b, ib = np.unique(vb, return_inverse=True)
    n_b = max(len(labels_b), 1)
    code = ia.astype(np.int64) * n_b + ib.astype(np.int64)
    pairs, pixel_pair, pair_n = np.unique(code, return_inverse=True, return_counts=True)
    return _Overlay(
        labels_a=labels_a,
        labels_b=labels_b,
        size_a=np.bincount(ia, minlength=len(labels_a)),
        size_b=np.bincount(ib, minlength=len(labels_b)),
        pair_a=pairs // n_b,
        pair_b=pairs % n_b,
        pair_n=pair_n,
        pixel_pair=pixel_pair.reshape(-1),
        same_values=bool(np.array_equal(va, vb)),
    )


def _same_set(ov: _Overlay) -> np.ndarray:
    """Per pair: do the label of a and the label of b cover exactly the same pixels?"""
    return (ov.pair_n == ov.size_a[ov.pair_a]) & (ov.pair_n == ov.size_b[ov.pair_b])


def partition_report(a: np.ndarray, b: np.ndarray, valid: np.ndarray | None) -> dict[str, Any]:
    """Do two label arrays cut the valid pixels into the same sets?

    Label values are arbitrary, so two arrays can describe the same sets under other numbers.
    Returns:

      n_pixels                     valid pixels
      n_labels_a, n_labels_b       distinct labels on them
      identical_labels             the same value at every valid pixel
      same_partition               every label of a covers exactly the pixels of one label of
                                   b and the other way round (the same sets, renumbered or not)
      pixels_not_in_matching_sets  pixels whose set in a is not, pixel for pixel, their set in b
      n_mismatches                 pairs (label of a, label of b) that share pixels without
                                   covering the same pixels
      examples                     up to 20 of those pairs as [label_a, label_b, pixels they
                                   share], the largest first
    """
    ov = _overlay(a, b, valid)
    same = _same_set(ov)
    bad = np.flatnonzero(~same)
    order = bad[np.lexsort((ov.pair_b[bad], ov.pair_a[bad], -ov.pair_n[bad]))]
    return {
        "n_pixels": int(ov.pair_n.sum()),
        "n_labels_a": int(len(ov.labels_a)),
        "n_labels_b": int(len(ov.labels_b)),
        "identical_labels": ov.same_values,
        "same_partition": bool(same.all()),
        "pixels_not_in_matching_sets": int(ov.pair_n[bad].sum()),
        "n_mismatches": int(len(bad)),
        "examples": [
            [int(ov.labels_a[ov.pair_a[k]]), int(ov.labels_b[ov.pair_b[k]]), int(ov.pair_n[k])]
            for k in order[:MAX_EXAMPLES]
        ],
    }


def changed_mask(old: np.ndarray, new: np.ndarray, valid: np.ndarray | None) -> np.ndarray:
    """True on the valid pixels whose stand is not the same set of pixels in both maps.

    A stand that was only renumbered has not changed. A stand that gained or lost a single
    pixel has changed as a whole, and so has the stand on the other side of that pixel."""
    old = _as_labels(old, "old")
    valid = _as_valid(valid, old.shape)
    ov = _overlay(old, new, valid)
    out = np.zeros(old.shape, dtype=bool)
    out[valid] = ~_same_set(ov)[ov.pixel_pair]
    return out


def _weighted_iou(
    size_a: np.ndarray, size_b: np.ndarray, pair_a: np.ndarray, pair_b: np.ndarray,
    pair_n: np.ndarray,
) -> float | None:
    """Area-weighted intersection over union of the stands of a with their best match in b.

    The definition of scripts/compare_stand_runs.py, on pixel sets: the best match of a stand
    is the stand of b sharing most pixels with it (on a tie, the one with the smaller id)."""
    total = int(size_a.sum())
    if total == 0:
        return None
    order = np.lexsort((pair_b, -pair_n, pair_a))
    first = np.ones(len(order), dtype=bool)
    first[1:] = pair_a[order][1:] != pair_a[order][:-1]
    best = order[first]  # one pair per stand of a, in the order of its stands
    common = pair_n[best].astype(float)
    together = size_a[pair_a[best]] + size_b[pair_b[best]] - common
    return float((common / together * size_a[pair_a[best]]).sum() / total)


def change_report(
    old: np.ndarray, new: np.ndarray, valid: np.ndarray | None, pixel_area_ha: float
) -> dict[str, Any]:
    """What changed between two stand maps of the same pixels.

    `valid` marks the pixels that carry a stand in BOTH maps; `pixel_area_ha` is the area of
    one pixel in hectares (0.01 on a 10 m grid). Stand ids are arbitrary: a stand is the set
    of its pixels, and a renumbered stand is unchanged. Returns:

      n_old, n_new          stands in each map
      n_unchanged           stands that are exactly the same set of pixels in both
      n_pixels              valid pixels
      n_pixels_changed      pixels whose stand is not the same set of pixels in the other map
      area_ha_total         n_pixels * pixel_area_ha
      area_ha_changed       n_pixels_changed * pixel_area_ha
      share_area_changed    area_ha_changed / area_ha_total
      area_weighted_iou_old_to_new, area_weighted_iou_new_to_old
          as in the header of scripts/compare_stand_runs.py, on pixel sets in place of
          polygons. Old to new: for every old stand A take the new stand B that shares most
          pixels with it; IoU(A) = pixels in both / pixels in either; the figure is the mean
          of IoU(A) over the old stands, each weighted by its area. New to old is the same
          with the maps swapped. An old stand cut in two halves scores 0.5 old to new, and
          each half scores 0.5 new to old.

    The shares and the two IoU figures are None when there is no valid pixel.
    """
    ov = _overlay(old, new, valid)
    same = _same_set(ov)
    n_pixels = int(ov.pair_n.sum())
    n_changed = int(ov.pair_n[~same].sum())
    return {
        "n_old": int(len(ov.labels_a)),
        "n_new": int(len(ov.labels_b)),
        "n_unchanged": int(same.sum()),
        "n_pixels": n_pixels,
        "n_pixels_changed": n_changed,
        "area_ha_total": n_pixels * float(pixel_area_ha),
        "area_ha_changed": n_changed * float(pixel_area_ha),
        "share_area_changed": n_changed / n_pixels if n_pixels else None,
        "area_weighted_iou_old_to_new": _weighted_iou(
            ov.size_a, ov.size_b, ov.pair_a, ov.pair_b, ov.pair_n
        ),
        "area_weighted_iou_new_to_old": _weighted_iou(
            ov.size_b, ov.size_a, ov.pair_b, ov.pair_a, ov.pair_n
        ),
    }


# --------------------------------------------------------------------------- several parts
def stack_parts(
    parts: Sequence[tuple[np.ndarray, np.ndarray, np.ndarray | None]],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The valid pixels of several parts of one ROI as one long row of pixels.

    `parts` holds one (a, b, valid) per part. Returns (a, b, valid) with valid all True,
    ready for partition_report or change_report. Those two look at sets of pixels and never
    at where a pixel lies, so they give the answer for the whole ROI on the stacked pixels,
    whether or not a label occurs in more than one part. This assumes what holds for one
    run over one ROI: the same label means the same stand in every part, and no pixel is
    counted in two parts."""
    stacked_a, stacked_b = [], []
    for a, b, valid in parts:
        a, b = _as_labels(a, "a"), _as_labels(b, "b")
        if a.shape != b.shape:
            raise ValueError(f"the two label arrays differ in shape: {a.shape} and {b.shape}.")
        valid = _as_valid(valid, a.shape)
        stacked_a.append(a[valid].astype(np.int64))
        stacked_b.append(b[valid].astype(np.int64))
    out_a = np.concatenate(stacked_a) if stacked_a else np.zeros(0, dtype=np.int64)
    out_b = np.concatenate(stacked_b) if stacked_b else np.zeros(0, dtype=np.int64)
    return out_a, out_b, np.ones(out_a.shape, dtype=bool)


def labels_in_several_parts(
    label_arrays: Sequence[np.ndarray], valids: Sequence[np.ndarray | None]
) -> dict[int, list[int]]:
    """The labels that occur on valid pixels of more than one part: {label: [part indexes]}.

    Empty when every label stays inside one part, which is what merge_part_reports needs."""
    if len(label_arrays) != len(valids):
        raise ValueError("one validity array per label array is needed.")
    seen: dict[int, list[int]] = {}
    for index, (labels, valid) in enumerate(zip(label_arrays, valids, strict=True)):
        for label in pixel_counts(labels, valid):
            seen.setdefault(label, []).append(index)
    return {label: where for label, where in sorted(seen.items()) if len(where) > 1}


def merge_part_reports(reports: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Add up the change_report of each part of one ROI into the report for the ROI.

    Counts, pixels and areas are added. The two IoU figures are means weighted by stand
    area, so they are combined weighted by each part's pixels.

    THIS IS ONLY RIGHT WHEN NO STAND ID OCCURS IN TWO PARTS, in the old map and in the new
    one. A stand lying in two parts would be counted twice and compared half at a time.
    The reports do not hold the ids, so this function cannot check it: check with
    labels_in_several_parts, or use change_report_parts, which works from the arrays, makes
    no such assumption and says how many ids span parts."""
    if not reports:
        raise ValueError("there is no report to merge.")
    added = ("n_old", "n_new", "n_unchanged", "n_pixels", "n_pixels_changed")
    out: dict[str, Any] = {key: int(sum(r[key] for r in reports)) for key in added}
    for key in ("area_ha_total", "area_ha_changed"):
        out[key] = float(math.fsum(r[key] for r in reports))
    n_pixels = out["n_pixels"]
    out["share_area_changed"] = out["n_pixels_changed"] / n_pixels if n_pixels else None
    for key in ("area_weighted_iou_old_to_new", "area_weighted_iou_new_to_old"):
        weighted = [r[key] * r["n_pixels"] for r in reports if r["n_pixels"]]
        out[key] = float(math.fsum(weighted) / n_pixels) if n_pixels else None
    return out


def change_report_parts(
    parts: Sequence[tuple[np.ndarray, np.ndarray, np.ndarray | None]], pixel_area_ha: float
) -> dict[str, Any]:
    """change_report for a ROI saved in several parts: one (old, new, valid) per part.

    Computed on the pixels of all parts together (see stack_parts), so it is right whether
    or not a stand lies in two parts. Three keys are added: n_parts, and
    n_old_in_several_parts and n_new_in_several_parts, the number of stand ids found in more
    than one part. Where both are 0, merge_part_reports over the per-part reports gives the
    same numbers."""
    report = change_report(*stack_parts(parts), pixel_area_ha)
    valids = [valid for _, _, valid in parts]
    report["n_parts"] = len(parts)
    report["n_old_in_several_parts"] = len(
        labels_in_several_parts([old for old, _, _ in parts], valids)
    )
    report["n_new_in_several_parts"] = len(
        labels_in_several_parts([new for _, new, _ in parts], valids)
    )
    return report


def _north_up(transform: Affine) -> bool:
    return transform.b == 0 and transform.d == 0 and transform.a > 0 and transform.e < 0


def mosaic_parts(
    arrays: Sequence[np.ndarray],
    transforms: Sequence[Affine],
    valids: Sequence[np.ndarray | None] | None = None,
    *,
    fill: float = 0,
) -> tuple[np.ndarray, Affine, np.ndarray]:
    """Put the part rasters of one ROI on one canvas, without resampling.

    Each array is [rows, cols] or [rows, cols, n] (an RGBA image has n = 4); all share one
    dtype and one n. The parts must lie on one grid: north-up, the same pixel size, origins
    a whole number of pixels apart. That holds for the parts of one ROI (one UTM zone, or
    the origin-anchored EPSG:4326 grid); a ValueError says so where it does not. Each part's
    valid pixels are copied to their place. Where two parts are valid on the same pixel the
    later one is kept.

    Returns (canvas, transform of the canvas, valid of the canvas). The canvas is the
    smallest rectangle holding all parts; it holds `fill` where no part is valid."""
    if not arrays or len(arrays) != len(transforms):
        raise ValueError("one transform per array is needed, and at least one array.")
    if valids is None:
        valids = [None] * len(arrays)
    if len(valids) != len(arrays):
        raise ValueError("one validity array per array is needed.")
    first = transforms[0]
    dx, dy = first.a, -first.e
    left = min(t.c for t in transforms)
    top = max(t.f for t in transforms)
    offsets = []
    for array, tr in zip(arrays, transforms, strict=True):
        same_size = math.isclose(tr.a, dx, rel_tol=1e-9) and math.isclose(-tr.e, dy, rel_tol=1e-9)
        if not (_north_up(tr) and same_size):
            raise ValueError("the parts are not north-up rasters with one pixel size.")
        col, row = (tr.c - left) / dx, (top - tr.f) / dy
        if abs(col - round(col)) > GRID_TOL_PIXELS or abs(row - round(row)) > GRID_TOL_PIXELS:
            raise ValueError("the parts are not on one grid: an origin is off by part of a pixel.")
        if array.shape[2:] != arrays[0].shape[2:] or array.dtype != arrays[0].dtype:
            raise ValueError("the parts differ in dtype or in the number of values per pixel.")
        offsets.append((int(round(row)), int(round(col))))
    height = max(r + a.shape[0] for (r, _), a in zip(offsets, arrays, strict=True))
    width = max(c + a.shape[1] for (_, c), a in zip(offsets, arrays, strict=True))
    canvas = np.full((height, width, *arrays[0].shape[2:]), fill, dtype=arrays[0].dtype)
    canvas_valid = np.zeros((height, width), dtype=bool)
    for array, valid, (r, c) in zip(arrays, valids, offsets, strict=True):
        ok = _as_valid(valid, array.shape[:2])
        rows, cols = slice(r, r + array.shape[0]), slice(c, c + array.shape[1])
        canvas[rows, cols][ok] = array[ok]
        canvas_valid[rows, cols] |= ok
    return canvas, Affine(dx, 0.0, left, 0.0, -dy, top), canvas_valid


# --------------------------------------------------------------------------- sampling
def sample_at_xy(
    array: np.ndarray,
    transform: Affine,
    xs: Sequence[float],
    ys: Sequence[float],
    *,
    valid: np.ndarray | None = None,
) -> list[Any]:
    """The value of the pixel containing each point, the points given in the raster's CRS.

    One entry per point: the value as a plain Python number ([rows, cols] array), or a list
    with one number per band ([bands, rows, cols] array), or None where the point is outside
    the raster or its pixel is not valid. A value that is NaN comes back as None too, band by
    band where there are several, as in the colour functions below; so what is returned can
    go into JSON as it is, unless the raster holds infinity. A pixel owns its left and its
    top edge: a point on the line between two pixels belongs to the one to the right, or
    below. The right and the bottom edge of the raster are outside it."""
    array = np.asarray(array)
    if array.ndim not in (2, 3):
        raise ValueError(f"array must be [rows, cols] or [bands, rows, cols], got {array.shape}.")
    height, width = array.shape[-2:]
    valid = _as_valid(valid, (height, width))
    x, y = np.asarray(xs, dtype=float).reshape(-1), np.asarray(ys, dtype=float).reshape(-1)
    if x.shape != y.shape:
        raise ValueError("xs and ys must have one length.")
    if transform.b == 0 and transform.d == 0:
        # subtracting the origin first keeps a point that is exactly on a pixel edge on it
        cols, rows = (x - transform.c) / transform.a, (y - transform.f) / transform.e
    else:
        inverse = ~transform
        cols = inverse.a * x + inverse.b * y + inverse.c
        rows = inverse.d * x + inverse.e * y + inverse.f
    out: list[Any] = []
    for col, row in zip(cols, rows, strict=True):
        if not (math.isfinite(col) and math.isfinite(row)):
            out.append(None)
            continue
        c, r = math.floor(col), math.floor(row)
        if not (0 <= r < height and 0 <= c < width) or not valid[r, c]:
            out.append(None)
        elif array.ndim == 2:
            out.append(_none_if_nan(array[r, c].item()))
        else:
            out.append([_none_if_nan(v) for v in array[:, r, c].tolist()])
    return out


def _none_if_nan(value: Any) -> Any:
    return None if isinstance(value, float) and math.isnan(value) else value


def sample_at_lonlat(
    array: np.ndarray,
    transform: Affine,
    crs: Any,
    lons: Sequence[float],
    lats: Sequence[float],
    *,
    valid: np.ndarray | None = None,
) -> list[Any]:
    """The value of the pixel containing each point, the points given as longitude, latitude.

    The points are converted to the raster's CRS and read with sample_at_xy (see there for
    what comes back and which pixel owns an edge). A point within about a nanometre of a
    pixel edge can fall on either side of it: the conversion is not exact to the last bit."""
    tr = _transformer(_crs_wkt(LONLAT), _crs_wkt(crs))
    xs, ys = tr.transform(np.asarray(lons, dtype=float), np.asarray(lats, dtype=float))
    return sample_at_xy(array, transform, np.atleast_1d(xs), np.atleast_1d(ys), valid=valid)


# --------------------------------------------------------------------------- display
def outline_mask(
    labels: np.ndarray, valid: np.ndarray | None, *, edge_is_boundary: bool = False
) -> np.ndarray:
    """The lines between labels, one pixel wide, as a bool array.

    True on a valid pixel
      - whose label differs from that of its right or of its lower neighbour, both valid
        (so a line between two labels is drawn once, on its left or upper side), or
      - that has a pixel that is not valid directly left, right, above or below it (the rim
        of the valid area, drawn on the valid side).
    The edge of the array is not a rim unless `edge_is_boundary` is set.

    Draw this on the raster's own grid and reproject the result: finding edges after
    reprojecting doubles the lines."""
    labels = np.asarray(labels)
    if labels.ndim != 2:
        raise ValueError(f"labels must be [rows, cols], got shape {labels.shape}.")
    valid = _as_valid(valid, labels.shape)
    out = np.zeros(labels.shape, dtype=bool)
    out[:, :-1] |= valid[:, :-1] & valid[:, 1:] & (labels[:, :-1] != labels[:, 1:])
    out[:-1, :] |= valid[:-1, :] & valid[1:, :] & (labels[:-1, :] != labels[1:, :])
    beside_invalid = np.zeros(labels.shape, dtype=bool)
    beside_invalid[:, :-1] |= ~valid[:, 1:]
    beside_invalid[:, 1:] |= ~valid[:, :-1]
    beside_invalid[:-1, :] |= ~valid[1:, :]
    beside_invalid[1:, :] |= ~valid[:-1, :]
    if edge_is_boundary:
        beside_invalid[[0, -1], :] = True
        beside_invalid[:, [0, -1]] = True
    return out | (valid & beside_invalid)


def _hex_rgb(colour: str) -> tuple[int, int, int]:
    """"#rrggbb" (the # may be left out) as three numbers 0..255."""
    match = _HEX.fullmatch(str(colour).strip())
    if match is None:
        raise ValueError(f"not a colour of the form #rrggbb: {colour!r}")
    h = match.group(1)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _not_nan(values: np.ndarray) -> np.ndarray:
    if np.issubdtype(values.dtype, np.floating):
        return ~np.isnan(values)
    return np.ones(values.shape, dtype=bool)


def _rgba(rgb: np.ndarray, shown: np.ndarray) -> np.ndarray:
    """uint8 [rows, cols, 4] from [rows, cols, 3] in 0..255; clear (all 0) where not shown."""
    out = np.zeros((*shown.shape, 4), dtype=np.uint8)
    out[..., :3][shown] = np.rint(rgb[shown]).astype(np.uint8)
    out[..., 3][shown] = 255
    return out


def categorical_rgba(
    codes: np.ndarray, colours: Mapping[int, str], valid: np.ndarray | None
) -> np.ndarray:
    """An RGBA image (uint8 [rows, cols, 4]) of a raster of class codes.

    `colours` gives "#rrggbb" per code. A pixel is clear (alpha 0) where `valid` is False,
    where the code is NaN, and where the code has no colour in `colours`; it is fully opaque
    (alpha 255) elsewhere."""
    codes = np.asarray(codes)
    valid = _as_valid(valid, codes.shape) & _not_nan(codes)
    rgb = np.zeros((*codes.shape, 3), dtype=float)
    shown = np.zeros(codes.shape, dtype=bool)
    for code, colour in colours.items():
        here = valid & (codes == code)
        rgb[here] = _hex_rgb(colour)
        shown |= here
    return _rgba(rgb, shown)


def continuous_rgba(
    values: np.ndarray,
    vmin: float,
    vmax: float,
    palette: Sequence[str],
    valid: np.ndarray | None,
) -> np.ndarray:
    """An RGBA image (uint8 [rows, cols, 4]) of a raster of numbers along a colour ramp.

    `palette` lists "#rrggbb" colours, evenly spaced from vmin (the first) to vmax (the
    last); colours in between are interpolated linearly, each channel on its own. Values
    below vmin get the first colour and values above vmax the last, infinity included. A
    pixel is clear (alpha 0) where `valid` is False or the value is NaN, opaque elsewhere."""
    if not vmax > vmin:
        raise ValueError(f"vmax ({vmax}) must be above vmin ({vmin}).")
    if not palette:
        raise ValueError("the palette is empty.")
    values = np.asarray(values, dtype=float)
    shown = _as_valid(valid, values.shape) & ~np.isnan(values)
    position = np.clip((np.where(shown, values, vmin) - vmin) / (vmax - vmin), 0.0, 1.0)
    stops = np.array([_hex_rgb(c) for c in palette], dtype=float)
    at = np.linspace(0.0, 1.0, len(stops)) if len(stops) > 1 else np.array([0.0])
    rgb = np.stack([np.interp(position, at, stops[:, k]) for k in range(3)], axis=-1)
    return _rgba(rgb, shown)


def rgb_rgba(
    red: np.ndarray,
    green: np.ndarray,
    blue: np.ndarray,
    limits: Sequence[tuple[float, float]],
    valid: np.ndarray | None,
    gamma: float = 1.0,
) -> np.ndarray:
    """An RGBA image (uint8 [rows, cols, 4]) from three bands.

    `limits` holds one (low, high) per band, in the order red, green, blue. Each band is
    scaled linearly from low..high to 0..1, clipped, raised to `gamma`, and written as
    0..255: the stretch of scripts/transparency_masking.py (stretch_rgb), band by band. Give
    the same pair three times to keep the colour balance of the image. A pixel is clear
    (alpha 0) where `valid` is False or any of the three bands is NaN, opaque elsewhere;
    infinity is clipped like any value beyond the limits."""
    bands = [np.asarray(band, dtype=float) for band in (red, green, blue)]
    if not (bands[0].shape == bands[1].shape == bands[2].shape):
        raise ValueError("red, green and blue must have one shape.")
    if len(limits) != 3:
        raise ValueError("limits must hold one (low, high) per band: three of them.")
    shown = _as_valid(valid, bands[0].shape)
    for band in bands:
        shown = shown & ~np.isnan(band)
    scaled = []
    for band, (low, high) in zip(bands, limits, strict=True):
        if not high > low:
            raise ValueError(f"a stretch needs high above low, got ({low}, {high}).")
        scaled.append(stretch_rgb(np.where(shown, band, low), low, high, gamma) * 255.0)
    return _rgba(np.stack(scaled, axis=-1), shown)


# --------------------------------------------------------------------------- writing
def web_canvas(
    transform: Affine, crs: Any, shape_hw: tuple[int, int]
) -> tuple[Affine, int, int]:
    """The EPSG:3857 grid a raster is drawn on for the web map: (transform, width, height).

    The canvas is north-up and covers the raster's whole extent. Its pixels are as wide and
    as tall as one pixel of the raster is in EPSG:3857 at the middle of the raster, so the
    picture has about as many pixels as the raster. They need not be square: a "10 m" pixel
    of an EPSG:4326 raster is wider than tall in web-map units away from the equator, and
    the canvas keeps that, so that every pixel of the raster gets a pixel of the picture.
    Leaflet stretches an image over its bounds, so pixels that are not square are drawn
    right. A raster that is already north-up in EPSG:3857 gets its own grid back."""
    height, width = int(shape_hw[0]), int(shape_hw[1])
    if height < 1 or width < 1:
        raise ValueError("the raster has no pixels.")
    src_crs = _rio_crs(crs)
    if src_crs == rio_crs.CRS.from_user_input(WEB_MERCATOR) and _north_up(transform):
        return transform, width, height
    corners = [transform * (c, r) for c, r in ((0, 0), (width, 0), (width, height), (0, height))]
    xs, ys = [p[0] for p in corners], [p[1] for p in corners]
    west, south, east, north = rio_warp.transform_bounds(
        src_crs, WEB_MERCATOR, min(xs), min(ys), max(xs), max(ys), densify_pts=21
    )
    # one pixel step along the columns and one along the rows, at the middle of the raster
    c, r = width / 2.0, height / 2.0
    here, right, below = transform * (c, r), transform * (c + 1, r), transform * (c, r + 1)
    mx, my = rio_warp.transform(
        src_crs, WEB_MERCATOR, [here[0], right[0], below[0]], [here[1], right[1], below[1]]
    )
    xres = math.hypot(mx[1] - mx[0], my[1] - my[0])
    yres = math.hypot(mx[2] - mx[0], my[2] - my[0])
    if not (xres > 0 and yres > 0 and math.isfinite(xres) and math.isfinite(yres)):
        raise ValueError("the raster's pixel size could not be measured in EPSG:3857.")
    # a hair's breadth short of a whole pixel must not add an empty row or column
    out_width = max(1, math.ceil((east - west) / xres - 1e-6))
    out_height = max(1, math.ceil((north - south) / yres - 1e-6))
    return Affine(xres, 0.0, west, 0.0, -yres, north), out_width, out_height


def write_web_png(rgba: np.ndarray, transform: Affine, crs: Any, path: Path | str) -> list[float]:
    """Write an RGBA image as a PNG for a Leaflet imageOverlay; return where to put it.

    `rgba` is uint8 [rows, cols, 4] on the grid given by `transform` and `crs` (what the
    colour functions above return). It is redrawn on the canvas of web_canvas, in EPSG:3857,
    by nearest neighbour: every pixel of the PNG takes the colour of the one source pixel
    its centre falls in, so no colour is mixed and no edge is blurred, and nothing moves by
    more than half a pixel. Pixels of the canvas outside the raster are clear. The position
    of every pixel is computed exactly (tolerance 0): the warp's default is to interpolate
    positions along each row to within an eighth of a pixel, which on a wide UTM raster
    hands some pixels the colour of a neighbour.

    Returns [west, south, east, north] in degrees: the corners of the PNG canvas, which is
    what imageOverlay needs. These are not the bounds of the ROI, and not exactly those of
    the source raster: the canvas is the upright rectangle around it, at most a pixel larger.

    The PNG holds no date. The folder is created if it is missing."""
    from PIL import Image  # only this function needs Pillow

    rgba = np.asarray(rgba)
    if rgba.ndim != 3 or rgba.shape[2] != 4 or rgba.dtype != np.uint8:
        raise ValueError(
            f"rgba must be uint8 [rows, cols, 4], got {rgba.dtype} {rgba.shape}."
        )
    dst_transform, width, height = web_canvas(transform, crs, rgba.shape[:2])
    if dst_transform == transform and (height, width) == rgba.shape[:2]:
        image = rgba  # already on the web-map grid: written as it is
    else:
        warped = np.zeros((4, height, width), dtype=np.uint8)
        rio_warp.reproject(
            source=np.ascontiguousarray(np.moveaxis(rgba, 2, 0)),
            destination=warped,
            src_transform=transform,
            src_crs=_rio_crs(crs),
            dst_transform=dst_transform,
            dst_crs=WEB_MERCATOR,
            resampling=rio_warp.Resampling.nearest,
            tolerance=0.0,
        )
        image = np.moveaxis(warped, 0, 2)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # a uint8 array with four values per pixel is read as RGBA
    Image.fromarray(np.ascontiguousarray(image)).save(path, format="PNG", optimize=True)

    left, top = dst_transform.c, dst_transform.f
    right, bottom = left + width * dst_transform.a, top + height * dst_transform.e
    lons, lats = rio_warp.transform(WEB_MERCATOR, LONLAT, [left, right], [bottom, top])
    return [float(lons[0]), float(lats[0]), float(lons[1]), float(lats[1])]


def round_geometry(geometry: BaseGeometry, decimals: int) -> BaseGeometry:
    """A geometry with every coordinate rounded to `decimals` places, and still valid.

    Rounding moves each vertex on its own, which can make a narrow polygon touch or cross
    itself. Where that happens the geometry is rebuilt on the grid of rounded coordinates
    (shapely.set_precision), which keeps it valid and may drop a part that has collapsed to
    a line. The result can therefore be empty for something smaller than the rounding.

    A polygon that comes in invalid (a ring that touches or crosses itself) is repaired the
    way compare_stand_runs does it: the polygons of the repair are kept, and the lines and
    points it leaves beside them, which have no area, are dropped."""
    def rounded(xy: np.ndarray) -> np.ndarray:
        return np.round(xy, decimals)

    geometry = shapely.force_2d(geometry)
    out = shapely.transform(geometry, rounded)
    if out.is_valid:
        return out
    if geometry.is_valid:
        start = geometry
    elif geometry.geom_type in ("Polygon", "MultiPolygon"):
        start = polygonal_part(geometry)
        if start is None:  # nothing with an area is left
            return shapely.Polygon()
    else:
        start = shapely.make_valid(geometry)
    # set_precision can leave a coordinate one bit off the rounded number: round once more
    out = shapely.transform(shapely.set_precision(start, 10.0**-decimals), rounded)
    if not out.is_valid:
        raise ValueError(f"the geometry could not be kept valid at {decimals} decimal places.")
    return out


def _json_value(value: Any) -> Any:
    """A property value as something json can write: numpy types converted, NaN to None."""
    if isinstance(value, np.generic):
        value = value.item()
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, np.ndarray):
        return [_json_value(v) for v in value.tolist()]
    if isinstance(value, Mapping):
        return {str(k): _json_value(value[k]) for k in sorted(value, key=str)}
    if isinstance(value, list | tuple):
        return [_json_value(v) for v in value]
    raise TypeError(f"a property of type {type(value).__name__} cannot be written to GeoJSON.")


def _coordinates(value: Any, convert: Callable[[float], float]) -> Any:
    if isinstance(value, list | tuple):
        return [_coordinates(v, convert) for v in value]
    return convert(float(value))


def _geometry_json(geometry: Any, decimals: int | None) -> dict[str, Any] | None:
    if geometry is None:
        return None
    geom = geometry if isinstance(geometry, BaseGeometry) else shape(geometry)
    if decimals is not None:
        geom = round_geometry(geom, decimals)
    if geom.is_empty:
        return None
    as_json = mapping(geom)
    if as_json["type"] == "GeometryCollection":
        raise ValueError("a GeometryCollection cannot be written: give polygons, lines or points.")

    def convert(x: float) -> float:
        return x if decimals is None else round(x, decimals)

    return {"type": as_json["type"], "coordinates": _coordinates(as_json["coordinates"], convert)}


def write_geojson(
    features: Sequence[Mapping[str, Any]], path: Path | str, *, decimals: int | None = 6
) -> int:
    """Write features as a compact GeoJSON FeatureCollection; return the file size in bytes.

    Each feature is a dict with "geometry" (a shapely geometry, a GeoJSON geometry dict, or
    None) and "properties" (a dict), and optionally "id". Coordinates are taken to be
    longitude and latitude: convert with to_lonlat first.

      - Coordinates are rounded to `decimals` places (6 is about 0.1 m); None keeps them as
        they are. A geometry that rounding makes invalid is repaired (round_geometry); one
        that rounding leaves empty is written as null. Each geometry is rounded on its
        own, so polygons that shared an edge can overlap or leave a gap of up to about the
        rounding step: they no longer tile exactly. Take areas from pixel counts, never
        from the geometry in the file.
      - Properties are passed through. numpy numbers and arrays become plain ones, NaN and
        infinity become null. Property names are written in alphabetical order, so the order
        in which a caller filled the dict does not change the file.
      - No whitespace, no date, features in the order given: the same input gives the same
        bytes. There is no newline at the end.
    """
    out_features = []
    for feature in features:
        entry: dict[str, Any] = {"type": "Feature"}
        if feature.get("id") is not None:
            entry["id"] = _json_value(feature["id"])
        entry["properties"] = _json_value(feature.get("properties") or {})
        entry["geometry"] = _geometry_json(feature.get("geometry"), decimals)
        out_features.append(entry)
    text = json.dumps(
        {"type": "FeatureCollection", "features": out_features},
        separators=(",", ":"), ensure_ascii=False, allow_nan=False,
    )
    data = text.encode("utf-8")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return len(data)

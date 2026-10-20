"""The land-cover masked output of one config: maps, rasters and the numbers.

For a config this script shows what the masking stage did and why:

  docs/transparency/<config>/     (committed)
      habitat_mask.png            true colour beside the mask coloured by reason,
                                  one panel pair per part of the ROI; a ROI with
                                  many parts is split over habitat_mask_sheet*.png
      summary.md                  the numbers, in plain words. No date in it, so
                                  `git diff` after a re-run shows only real changes
      run_record.json             which code and which cached assets produced
                                  them, the date and the command line; --redraw
                                  adds an entry to it instead of replacing it
  outputs/transparency/<config>/  (ignored by git)
      <part>_mask_provenance.tif  reason and source bands; 255 outside the part
      <part>_habitat_mask.tif     the mask the rest of the pipeline uses; 255 outside
      <part>_landcover_summary.tif  255 outside the part
      <part>_true_colour.tif      red, green, blue of the pipeline's own composite;
                                  0 outside the part
      roi_outline.geojson, points.geojson, masking_transparency.json

EARTH ENGINE: READ-ONLY. The stages run through
`Pipeline(..., use_cache=True, submit_exports=False)`: cached assets are read,
whatever is not cached is computed live, and no export task is submitted and no
asset is written. The rasters come down through interactive download requests,
one part of the ROI at a time. (`scripts/inspect_masking.py` is the script that
fills the cache; this one never does.)

The colours, labels and the sentence about what "habitat" means are not typed
here: they are read from the masking stage's own display-layer declaration, as
the run manifest records it. The summary numbers for the whole ROI are likewise
taken from the manifest. The per-part numbers are tabulated from the saved
rasters with the stage's own arithmetic (`tabulate_mask_provenance`).

Usage (from the repo root, the pipeline reads .env from the working directory):

    python scripts/transparency_masking.py --config configs/sanjay_van_baseline.yaml
    python scripts/transparency_masking.py --config configs/<config>.yaml \
        --points plots.csv --id-col plot_id --lon-col lon --lat-col lat

    # redraw the maps and summary.md from the saved rasters, without Earth Engine
    python scripts/transparency_masking.py --config configs/<config>.yaml --redraw
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import re
import shlex
import sys
import textwrap
import time
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from pyproj import Geod
from rasterio.features import geometry_mask
from shapely.geometry import Point, mapping, shape
from shapely.geometry.base import BaseGeometry

from fmu.stages.masking import (
    REASON_KEPT,
    REASON_NAMES,
    SOURCE_NAMES,
    tabulate_mask_provenance,
)

# Value written where a raster has no pixel: outside the ROI, or (habitat_mask
# only) where neither land-cover map has data. No legend uses it.
NODATA = 255

# Side, in pixels, of the window around a point in which kept pixels are
# counted, to say whether a dropped point sits in a removed patch or on a
# stray removed pixel inside a kept one.
POINT_WINDOW = 5

# Metres per degree that Earth Engine uses to turn a scale in metres into a
# pixel size in EPSG:4326. A cache export of the legacy layout at 10 m lands on
# the grid this gives, anchored at (0, 0), so a download on the same grid reads
# such an asset pixel for pixel instead of resampling it. An asset of the
# per-step layout (every run since round 9) is on the ROI's UTM grid, and a
# download on this grid resamples it (review C31).
_EE_METRES_PER_DEGREE = 111319.49079327357

_GEOD = Geod(ellps="WGS84")

# True-colour display: one linear stretch for all three bands, so the colour
# balance is the image's own, between these two percentiles of the pixels
# inside the ROI, then a gamma below 1 to lift the dark forest tones.
STRETCH_PERCENTILES = (1.0, 99.0)
STRETCH_GAMMA = 0.75

PARTS_PER_SHEET = 4
# A part whose panel would be less than this tall for its width is drawn across
# the whole sheet, its panels stacked, instead of side by side as a sliver.
WIDE_PART_RATIO = 0.4
MAP_DPI = 130

MAP_NAME = "habitat_mask"

# How the points are drawn. Chosen to stand apart from every legend colour. A
# dropped point is an open diamond, so the pixels under it stay visible.
_KEPT_STYLE = {"marker": "o", "s": 34, "facecolor": "white", "edgecolor": "black", "linewidth": 1.1}
_DROPPED_COLOUR = "#ff00ff"
_DROPPED_STYLE = {"marker": "D", "s": 120, "facecolor": "none", "edgecolor": _DROPPED_COLOUR,
                  "linewidth": 2.0}
_DROPPED_HALO = {"marker": "D", "s": 120, "facecolor": "none", "edgecolor": "white",
                 "linewidth": 4.0}


# ---------------------------------------------------------------------------
# Parts of the ROI
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RoiPart:
    """One polygon of the ROI, with the name it is reported under."""

    index: int  # 0-based position in the ROI file
    name: str
    slug: str  # file-name stem, unique within the ROI
    geometry: BaseGeometry


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _as_name(value: Any) -> str | None:
    """A name out of a property value: a string, or a list of strings joined."""
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, list | tuple) and value and all(isinstance(v, str) for v in value):
        return " + ".join(v.strip() for v in value)
    return None


def roi_parts(roi_geojson: dict[str, Any], name_key: str = "name") -> list[RoiPart]:
    """Split a ROI GeoJSON into its polygons and name each one.

    A part is named from the ROI file when the file carries a name for it:

      - a feature holding one polygon takes `properties[name_key]`, else
        `properties["name"]`;
      - a feature holding a MultiPolygon takes, for its i-th polygon,
        `properties["parts"][i][name_key]` when `parts` is a list with one entry
        per polygon (a string, or a list of strings, which are joined).

    Any part left without a name is called "part N" (N counted from 1 over the
    whole file). Names that repeat get their number appended.
    """
    gtype = roi_geojson.get("type")
    if gtype == "FeatureCollection":
        features = roi_geojson.get("features", [])
    elif gtype == "Feature":
        features = [roi_geojson]
    else:
        features = [{"type": "Feature", "properties": {}, "geometry": roi_geojson}]
    if not features:
        raise ValueError("ROI has no features.")

    found: list[tuple[BaseGeometry, str | None]] = []
    for feature in features:
        props = feature.get("properties") or {}
        geom = shape(feature["geometry"])
        if geom.geom_type == "Polygon":
            found.append((geom, _as_name(props.get(name_key)) or _as_name(props.get("name"))))
        elif geom.geom_type == "MultiPolygon":
            polygons = list(geom.geoms)
            listed = props.get("parts")
            for i, polygon in enumerate(polygons):
                name = None
                if isinstance(listed, list) and len(listed) == len(polygons):
                    entry = listed[i]
                    name = _as_name(entry.get(name_key)) if isinstance(entry, dict) else None
                found.append((polygon, name))
        else:
            raise ValueError(f"ROI geometry must be polygonal, got {geom.geom_type}.")

    names = [name or f"part {i + 1}" for i, (_, name) in enumerate(found)]
    repeated = {n for n in names if names.count(n) > 1}
    names = [f"{n} ({i + 1})" if n in repeated else n for i, n in enumerate(names)]
    width = max(2, len(str(len(found))))
    return [
        RoiPart(i, name, f"part{i + 1:0{width}d}_{_slugify(name)}".rstrip("_"), geom)
        for i, ((geom, _), name) in enumerate(zip(found, names, strict=True))
    ]


def roi_file_notes(roi_geojson: dict[str, Any]) -> list[str]:
    """What the ROI file says about itself: the `note` property of its features."""
    if roi_geojson.get("type") == "FeatureCollection":
        features = roi_geojson.get("features", [])
    elif roi_geojson.get("type") == "Feature":
        features = [roi_geojson]
    else:
        return []
    notes: list[str] = []
    for feature in features:
        note = (feature.get("properties") or {}).get("note")
        if isinstance(note, str) and note.strip() and note.strip() not in notes:
            notes.append(note.strip())
    return notes


def roi_outline_geojson(parts: Sequence[RoiPart]) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"part": p.name, "part_index": p.index + 1, "file_stem": p.slug},
                "geometry": mapping(p.geometry),
            }
            for p in parts
        ],
    }


# ---------------------------------------------------------------------------
# The download grid
# ---------------------------------------------------------------------------
def pixel_size_deg(scale_m: float) -> float:
    return scale_m / _EE_METRES_PER_DEGREE


def snapped_bounds(
    bounds: tuple[float, float, float, float], scale_m: float, pad_pixels: int = 3
) -> tuple[float, float, float, float]:
    """Bounds grown outward to whole pixels of the origin-anchored grid, plus a margin."""
    d = pixel_size_deg(scale_m)
    minx, miny, maxx, maxy = bounds
    return (
        (math.floor(minx / d) - pad_pixels) * d,
        (math.floor(miny / d) - pad_pixels) * d,
        (math.ceil(maxx / d) + pad_pixels) * d,
        (math.ceil(maxy / d) + pad_pixels) * d,
    )


# ---------------------------------------------------------------------------
# Tabulating a saved raster
# ---------------------------------------------------------------------------
def row_pixel_area_m2(transform: Any, height: int) -> np.ndarray:
    """Ground area of one pixel in each row of a north-up EPSG:4326 raster.

    A "10 m" pixel in this grid is 10 m tall and 10 m x cos(latitude) wide, so
    areas are measured on the ellipsoid, not taken as scale squared.
    """
    dx, dy = transform.a, transform.e
    areas = np.empty(height, dtype=float)
    for row in range(height):
        top = transform.f + row * dy
        lons = [0.0, dx, dx, 0.0]
        lats = [top, top, top + dy, top + dy]
        area, _ = _GEOD.polygon_area_perimeter(lons, lats)
        areas[row] = abs(area)
    return areas


def area_by_key(
    reason: np.ndarray,
    source: np.ndarray,
    habitat: np.ndarray,
    inside: np.ndarray,
    row_area_m2: np.ndarray,
) -> dict[int, float]:
    """Square metres under each (disagrees, source, reason), from arrays.

    The key is `disagrees * 100 + source * 10 + reason`, the one
    `fmu.stages.masking.mask_provenance_areas` returns, so the result goes
    through the stage's own `tabulate_mask_provenance`. `inside` marks the
    pixels to count (pixel centre inside the part). `habitat` counts as kept
    only where it is 1, as the stage counts it.
    """
    if not (reason.shape == source.shape == habitat.shape == inside.shape):
        raise ValueError("reason, source, habitat and inside must have one shape.")
    if row_area_m2.shape != (reason.shape[0],):
        raise ValueError("row_area_m2 must hold one area per raster row.")
    count = inside & (reason != NODATA) & (source != NODATA)
    disagrees = (reason == REASON_KEPT) != (habitat == 1)
    key = disagrees.astype(np.int64) * 100 + source.astype(np.int64) * 10 + reason.astype(np.int64)
    area = np.broadcast_to(row_area_m2[:, None], reason.shape)
    out: dict[int, float] = {}
    for k in np.unique(key[count]):
        out[int(k)] = float(area[count & (key == k)].sum())
    return out


def inside_mask(geometry: BaseGeometry, transform: Any, shape_hw: tuple[int, int]) -> np.ndarray:
    """True for the pixels whose centre lies inside `geometry`."""
    return geometry_mask([mapping(geometry)], out_shape=shape_hw, transform=transform, invert=True)


def blank_untouched(
    array: np.ndarray, geometry: BaseGeometry, transform: Any, fill: float
) -> np.ndarray:
    """A copy of a (bands, rows, cols) array with `fill` on every pixel the part does not touch.

    A download of a clipped image comes back with 0 outside the clip, and 0 is
    a legend value of every layer here (no data, not habitat). So what lies
    outside the part is set to the no-data value before the file is written.
    Pixels the outline crosses keep what Earth Engine returned for them.
    """
    touched = geometry_mask(
        [mapping(geometry)], out_shape=array.shape[-2:], transform=transform, invert=True,
        all_touched=True,
    )
    out = array.copy()
    out[..., ~touched] = fill
    return out


def tabulate_part(
    provenance_tif: Path, habitat_tif: Path, geometry: BaseGeometry
) -> dict[str, Any]:
    """Summary numbers of one part, from its saved rasters."""
    with rasterio.open(provenance_tif) as ds:
        reason, source = ds.read(1), ds.read(2)
        transform, hw = ds.transform, (ds.height, ds.width)
    with rasterio.open(habitat_tif) as ds:
        habitat = ds.read(1)
        if ds.transform != transform or (ds.height, ds.width) != hw:
            raise ValueError(f"{habitat_tif.name} is not on the grid of {provenance_tif.name}.")
    inside = inside_mask(geometry, transform, hw)
    areas = area_by_key(reason, source, habitat, inside, row_pixel_area_m2(transform, hw[0]))
    return tabulate_mask_provenance(areas)


def pooled(tables: Sequence[dict[str, Any]]) -> dict[str, float]:
    """Area and share kept over several parts' tables, for the cross-check."""
    area = sum(t["area_ha"] for t in tables)
    kept = sum(t["area_ha"] * t["share_kept"] for t in tables)
    return {"area_ha": round(area, 4), "share_kept": round(kept / area, 6) if area else 0.0}


# ---------------------------------------------------------------------------
# Points
# ---------------------------------------------------------------------------
def read_points(path: Path, id_col: str, lon_col: str, lat_col: str) -> list[dict[str, Any]]:
    """Read points from a CSV. Every other column is carried along as text."""
    points: list[dict[str, Any]] = []
    with Path(path).open(newline="") as f:
        reader = csv.DictReader(f)
        missing = {id_col, lon_col, lat_col} - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path}: no column(s) {sorted(missing)}; has {reader.fieldnames}.")
        for row in reader:
            extra = {k: v for k, v in row.items() if k not in (id_col, lon_col, lat_col)}
            points.append(
                {"id": row[id_col], "lon": float(row[lon_col]), "lat": float(row[lat_col]),
                 "attributes": extra}
            )
    ids = [p["id"] for p in points]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{path}: values in {id_col!r} are not unique.")
    return points


def legend_labels(layer: dict[str, Any]) -> dict[int, str]:
    return {int(e["value"]): str(e["label"]) for e in layer["legend"]}


def classify_points(
    points: Sequence[dict[str, Any]],
    parts: Sequence[RoiPart],
    provenance_tifs: dict[str, Path],
    habitat_tifs: dict[str, Path],
    reason_labels: dict[int, str],
    source_labels: dict[int, str],
) -> list[dict[str, Any]]:
    """Say, for each point, which part it is in and what the mask did there.

    Read off the saved rasters at the pixel holding the point. `kept` is taken
    from `habitat_mask`, the mask the rest of the pipeline uses; the reason and
    the deciding map come from `mask_provenance`. `window_kept` of
    `window_pixels` is how many of the pixels in the POINT_WINDOW-pixel square
    around the point are kept (pixels outside the part are not counted). A
    point in no part of the ROI is reported as outside it, with no codes.
    """
    opened: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray, Any]] = {}

    def arrays(part: RoiPart) -> tuple[np.ndarray, np.ndarray, np.ndarray, Any]:
        if part.slug not in opened:
            with rasterio.open(provenance_tifs[part.slug]) as ds:
                reason, source, transform = ds.read(1), ds.read(2), ds.transform
            with rasterio.open(habitat_tifs[part.slug]) as ds:
                habitat = ds.read(1)
            opened[part.slug] = (reason, source, habitat, transform)
        return opened[part.slug]

    out: list[dict[str, Any]] = []
    for p in points:
        record: dict[str, Any] = {
            "id": p["id"], "lon": p["lon"], "lat": p["lat"],
            "in_roi": False, "part": None, "kept": None,
            "reason_code": None, "reason_name": None, "reason_label": None,
            "source_code": None, "source_name": None, "source_label": None,
            "window_kept": None, "window_pixels": None,
            "attributes": dict(p.get("attributes") or {}),
        }
        location = Point(p["lon"], p["lat"])
        part = next((q for q in parts if q.geometry.covers(location)), None)
        if part is not None:
            reason, source, habitat, transform = arrays(part)
            col, row = (~transform) * (p["lon"], p["lat"])
            r, c = int(math.floor(row)), int(math.floor(col))
            if not (0 <= r < reason.shape[0] and 0 <= c < reason.shape[1]):
                raise ValueError(f"point {p['id']!r} is in part {part.name!r} but off its raster.")
            rc, sc = int(reason[r, c]), int(source[r, c])
            record["in_roi"] = True
            record["part"] = part.name
            if rc != NODATA and sc != NODATA:
                # NODATA here means the point sits inside the outline but on an
                # edge pixel that Earth Engine returned no value for.
                half = POINT_WINDOW // 2
                rows = slice(max(r - half, 0), r + half + 1)
                cols = slice(max(c - half, 0), c + half + 1)
                valued = reason[rows, cols] != NODATA
                record.update(
                    window_kept=int(((habitat[rows, cols] == 1) & valued).sum()),
                    window_pixels=int(valued.sum()),
                )
                record.update(
                    kept=bool(habitat[r, c] == 1),
                    reason_code=rc, reason_name=REASON_NAMES.get(rc), reason_label=reason_labels.get(rc),
                    source_code=sc, source_name=SOURCE_NAMES.get(sc), source_label=source_labels.get(sc),
                )
        out.append(record)
    return out


def points_geojson(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    features = []
    for r in records:
        props = {k: v for k, v in r.items() if k not in ("lon", "lat", "attributes")}
        props.update({f"attr_{k}": v for k, v in r["attributes"].items()})
        features.append(
            {"type": "Feature", "properties": props,
             "geometry": {"type": "Point", "coordinates": [r["lon"], r["lat"]]}}
        )
    return {"type": "FeatureCollection", "features": features}


def count_points(records: Sequence[dict[str, Any]]) -> dict[str, int]:
    inside = [r for r in records if r["in_roi"]]
    return {
        "given": len(records),
        "in_roi": len(inside),
        "outside_roi": len(records) - len(inside),
        "kept": sum(1 for r in inside if r["kept"] is True),
        "dropped": sum(1 for r in inside if r["kept"] is False),
        "no_value": sum(1 for r in inside if r["kept"] is None),
    }


# ---------------------------------------------------------------------------
# Reading the manifest's transparency record
# ---------------------------------------------------------------------------
def summary_values(transparency: dict[str, Any]) -> dict[str, Any]:
    """`{name: value}` of a stage's summary numbers, or an error if they are missing."""
    if transparency.get("summary_error"):
        raise RuntimeError(f"the stage's summary failed: {transparency['summary_error']}")
    values = {n["name"]: n["value"] for n in transparency.get("summary_numbers", [])}
    if not values:
        raise RuntimeError("the manifest holds no summary numbers for this stage.")
    return values


def display_layer(transparency: dict[str, Any], key: str, band: str) -> dict[str, Any]:
    for layer in transparency.get("display_layers", []):
        if layer["key"] == key and layer["band"] == band:
            return layer
    raise KeyError(f"the stage declares no display layer {key}.{band}.")


def decided_sentence(numbers: dict[str, Any], source_labels: dict[int, str]) -> str:
    """Which map decided how much of the area, in the stage's own words."""
    shares = numbers["share_decided_by_source"]
    pieces = [
        f"{source_labels[code]}: {shares[name]:.1%} of the area"
        for code, name in sorted(SOURCE_NAMES.items(), key=lambda kv: (kv[0] == 0, kv[0]))
        if shares.get(name, 0.0) > 0 or code == 1
    ]
    return "Which map decided. " + "; ".join(pieces) + "."


# ---------------------------------------------------------------------------
# summary.md
# ---------------------------------------------------------------------------
def _pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def _ha(x: float) -> str:
    return f"{x:,.1f} ha"


def _md_row(cells: Sequence[Any]) -> str:
    return "| " + " | ".join(str(c) for c in cells) + " |"


def _md_table(header: Sequence[str], rows: Sequence[Sequence[Any]]) -> list[str]:
    return [_md_row(header), _md_row(["---"] * len(header)), *(_md_row(r) for r in rows)]


def _short_reason(label: str) -> str:
    """A legend label cut down to the land cover it names, for a sentence or a column head."""
    return label.replace("Removed: ", "").replace(" (not habitat)", "")


def one_source_decided(numbers: dict[str, Any]) -> bool:
    """True when a single land-cover map decided every pixel that was tabulated."""
    shares = numbers["share_decided_by_source"]
    return sum(1 for v in shares.values() if v > 0) <= 1


def plural(noun: str, n: int) -> str:
    return noun if n == 1 else f"{noun}s"


def lead_sentences(
    numbers: dict[str, Any],
    reason_labels: dict[int, str],
    points: Sequence[dict[str, Any]] | None,
    point_noun: str = "point",
) -> list[str]:
    """The result in two or three plain sentences: area, share kept, why the rest went, the points."""
    by_reason = numbers["share_by_reason"]
    removed = sorted(
        ((by_reason[REASON_NAMES[c]], _short_reason(reason_labels[c]))
         for c in REASON_NAMES if c != REASON_KEPT and by_reason[REASON_NAMES[c]] >= 0.0005),
        reverse=True,
    )
    out = [
        f"The ROI is {_ha(numbers['area_ha'])}. The land-cover mask keeps "
        f"{_pct(numbers['share_kept'])} of it as habitat and removes the rest"
        + (": " + ", ".join(f"{name} {_pct(share)}" for share, name in removed) + "."
           if removed else ".")
    ]
    if points is not None:
        n = count_points(points)
        sentence = (
            f"Of the {n['given']} {plural(point_noun, n['given'])} given, {n['in_roi']} "
            f"{'is' if n['in_roi'] == 1 else 'are'} inside the ROI: {n['kept']} on a kept pixel "
            f"and {n['dropped']} on a removed pixel"
            + (f", {n['no_value']} on an edge pixel with no value" if n["no_value"] else "")
            + "."
        )
        if n["outside_roi"]:
            sentence += (
                f" {n['outside_roi']} {'lies' if n['outside_roi'] == 1 else 'lie'} outside the "
                "ROI and "
                f"{'is' if n['outside_roi'] == 1 else 'are'} not on the map."
            )
        out.append(sentence)
    return out


def summary_markdown(
    *,
    config_name: str,
    config_path: str,
    roi_file: str,
    fingerprint: str,
    numbers: dict[str, Any],
    reason_layer: dict[str, Any],
    source_layer: dict[str, Any],
    layer_status: dict[str, str],
    part_tables: Sequence[tuple[str, dict[str, Any]]],
    points: Sequence[dict[str, Any]] | None,
    map_files: Sequence[str],
    notes: Sequence[str] = (),
    comparisons: Sequence[dict[str, Any]] = (),
    stretch: dict[str, Any] | None = None,
    title: str | None = None,
    point_noun: str = "point",
    roi_notes: Sequence[str] = (),
    scale_m: float | None = None,
) -> str:
    """The numbers of one config's mask, as Markdown. No date, no run time.

    `numbers` are the whole-ROI summary numbers from the manifest.
    `part_tables` holds `(part name, table)` with each table in the shape
    `tabulate_mask_provenance` returns. `layer_status` maps a layer to "hit"
    (read from the cache) or anything else (computed live). `point_noun` is
    what a point is called in the text ("field plot"); `roi_notes` is what the
    ROI file says about itself.
    """
    reason_labels = legend_labels(reason_layer)
    source_labels = legend_labels(source_layer)
    reason_codes = sorted(REASON_NAMES, key=lambda c: (c == 0, c))
    multi = len(part_tables) > 1
    single_source = one_source_decided(numbers)
    cached_mask = layer_status.get("habitat_mask") == "hit"
    nouns = plural(point_noun, 2)
    pixel = f"{scale_m:g} m pixel" if scale_m else "pixel"

    def read_from(key: str) -> str:
        return "read from the cached asset" if layer_status.get(key) == "hit" else "computed live"

    lines: list[str] = [f"# {title or 'Habitat mask: ' + config_name}", ""]
    lines += [" ".join(lead_sentences(numbers, reason_labels, points, point_noun)), ""]
    lines += [reason_layer["legend_note"], ""]
    site_notes = [f"- {n}" for n in notes]
    site_notes += [f"- The ROI file (`{roi_file}`) says of itself: \"{n}\"" for n in roi_notes]
    if site_notes:
        lines += [*site_notes, ""]
    lines += ["Maps: " + ", ".join(f"`{m}`" for m in map_files) + ".", ""]
    lines += ["## Whole ROI", ""]

    by_reason = numbers["share_by_reason"]
    kept_by = numbers["share_kept_by_source"]
    decided_by = numbers["share_decided_by_source"]
    disagree = numbers["area_ha_reason_disagrees_with_habitat_mask"]
    rows: list[list[str]] = [
        ["Area of the ROI", _ha(numbers["area_ha"])],
        ["Kept as habitat (not only forest)", _pct(numbers["share_kept"])],
    ]
    if disagree > 0:
        rows.append(["Kept according to the reason layer computed in this run",
                     _pct(by_reason[REASON_NAMES[REASON_KEPT]])])
    rows += [
        [reason_labels[c], _pct(by_reason[REASON_NAMES[c]])]
        for c in reason_codes if c != REASON_KEPT
    ]
    if not single_source:
        rows += [
            [f"Kept as habitat, where {source_labels[c]}", _pct(kept_by[SOURCE_NAMES[c]])]
            for c in sorted(SOURCE_NAMES) if c != 0
        ]
        rows += [
            [f"Share of the area. {source_labels[c]}", _pct(decided_by[SOURCE_NAMES[c]])]
            for c in sorted(SOURCE_NAMES, key=lambda c: (c == 0, c))
        ]
    lines += _md_table(["Quantity", "Value"], rows)
    lines += ["", decided_sentence(numbers, source_labels)
              + (" So every kept pixel was kept on that map's word." if single_source else "")]
    if cached_mask:
        lines += [
            "",
            f"Check against the cached mask: {_ha(disagree)}. That is the area where the reason "
            "layer, computed in this run from today's land-cover data, says kept and the cached "
            "`habitat_mask` does not, or the reverse. Above zero would mean a land-cover input "
            "has changed since the mask was cached, so the stands were built on a mask today's "
            "data would not reproduce exactly.",
        ]
    else:
        lines += [
            "",
            f"The reason layer and `habitat_mask` disagree over {_ha(disagree)}. Both were "
            "computed in this run, so this is zero by construction; it is a check only when "
            "the mask is read from the cache.",
        ]
    kept_classes = numbers.get("kept_classes") or {}
    if kept_classes:
        lines += [
            "",
            "Classes this run kept as habitat: "
            + "; ".join(f"{name} {classes}" for name, classes in kept_classes.items())
            + ".",
        ]
    if comparisons:
        lines += ["", "Other cached masks compared with the `habitat_mask` above, pixel by pixel:", ""]
        lines += [
            f"- `{c['label']}` differs over {c['area_ha_differs']:,.2f} ha of "
            f"{_ha(c['area_ha'])} ({_pct(c['share_differs'])})."
            for c in comparisons
        ]

    if multi:
        lines += [
            "", "## By part", "",
            "Tabulated from the saved rasters, counting the pixels whose centre is inside "
            "the part. The whole-ROI table above comes from Earth Engine, which weights "
            "edge pixels by how much of them the ROI covers, so the two can differ by a "
            "fraction of a percent.",
            "",
        ]
        # A reason no part has, and the deciding map when one map decided
        # everything, would be columns of one repeated value: left out, and said.
        shown = [c for c in reason_codes if c != REASON_KEPT and (
            c != 0 or any(t["share_by_reason"][REASON_NAMES[c]] > 0 for _, t in part_tables))]
        sources = [] if single_source else [c for c in sorted(SOURCE_NAMES) if c != 0]
        header = ["Part", "Area", "Kept"] + [_short_reason(reason_labels[c]) for c in shown] + [
            source_labels[c] for c in sources]
        part_rows = []
        for name, t in part_tables:
            part_rows.append(
                [name, _ha(t["area_ha"]), _pct(t["share_kept"])]
                + [_pct(t["share_by_reason"][REASON_NAMES[c]]) for c in shown]
                + [_pct(t["share_decided_by_source"][SOURCE_NAMES[c]]) for c in sources]
            )
        lines += _md_table(header, part_rows)
        tail = "Columns after Kept are shares of the part's area removed for each reason"
        tail += ", then the share each map decided." if sources else "."
        if 0 not in shown:
            tail += " No part has a pixel without land-cover data."
        if single_source:
            tail += " One map decided every pixel of every part (see above)."
        lines += ["", tail]

    if points is not None:
        n = count_points(points)
        lines += ["", f"## {nouns[0].upper()}{nouns[1:]}", ""]
        lines.append(
            f"{n['given']} {plural(point_noun, n['given'])} given, {n['in_roi']} inside the ROI: "
            f"{n['kept']} kept, {n['dropped']} dropped"
            + (f", {n['no_value']} on an edge pixel with no value" if n["no_value"] else "")
            + f". {n['outside_roi']} outside the ROI."
            + f" A {point_noun} is kept or dropped by the single {pixel} it falls on, so a "
            f"dropped {point_noun} can sit in a patch that is otherwise kept."
        )
        if multi:
            lines += [""]
            rows_p = []
            for name, _ in part_tables:
                here = [r for r in points if r["part"] == name]
                rows_p.append([name, len(here), sum(1 for r in here if r["kept"] is True),
                               sum(1 for r in here if r["kept"] is False)])
            lines += _md_table(["Part", nouns[0].upper() + nouns[1:], "Kept", "Dropped"], rows_p)
        dropped = sorted((r for r in points if r["kept"] is False), key=lambda r: r["id"])
        if dropped:
            lines += ["", f"Dropped {nouns}:", ""]
            lines += _md_table(
                [point_noun[0].upper() + point_noun[1:], "Part", "Reason", "Decided by",
                 f"Kept pixels in the {POINT_WINDOW} x {POINT_WINDOW} around it"],
                [[f"`{r['id']}`", r["part"], r["reason_label"], r["source_label"],
                  f"{r['window_kept']} of {r['window_pixels']}"
                  if r.get("window_pixels") is not None else ""] for r in dropped],
            )
        no_value = sorted(r["id"] for r in points if r["in_roi"] and r["kept"] is None)
        if no_value:
            lines += ["", "Inside the outline but on an edge pixel with no value: "
                      + ", ".join(f"`{i}`" for i in no_value) + "."]
        outside = sorted(r["id"] for r in points if not r["in_roi"])
        if outside:
            lines += ["", "Outside the ROI, so not on the map and not counted above: "
                      + ", ".join(f"`{i}`" for i in outside) + "."]

    if stretch:
        lines += [
            "", "## How the maps are drawn", "",
            f"True colour is Sentinel-2 red, green and blue ({', '.join(stretch['bands'])}) of "
            f"`s2_composite`, the image the pipeline segments on ({read_from('s2_composite')}). "
            f"All three bands share one linear stretch, from {stretch['low']:.0f} to "
            f"{stretch['high']:.0f} (percentiles {stretch['percentiles'][0]:g} and "
            f"{stretch['percentiles'][1]:g} of the pixels inside the ROI), then "
            f"gamma {stretch['gamma']:g}. Colours and labels of the mask are the masking "
            "stage's own display-layer declaration. North is up. White is outside the ROI.",
        ]
    lines += [
        "", "## For the record", "",
        f"- Config: `{config_path}` (name `{config_name}`, cache fingerprint `{fingerprint}`)",
        f"- ROI file: `{roi_file}`, {len(part_tables)} part{'s' if multi else ''}",
        f"- `habitat_mask`, the mask the rest of the pipeline uses: {read_from('habitat_mask')}",
        f"- `mask_provenance`, the reason and deciding-map layer: {read_from('mask_provenance')}",
        "- The code, the cached asset ids, the date and the command line are in "
        "`run_record.json` beside this file.",
    ]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Small helpers for the maps (no matplotlib)
# ---------------------------------------------------------------------------
def sheet_groups(n_parts: int, per_sheet: int = PARTS_PER_SHEET) -> list[list[int]]:
    """Indices of the parts on each sheet, filling sheets evenly."""
    if n_parts <= 0:
        return []
    n_sheets = math.ceil(n_parts / per_sheet)
    size = math.ceil(n_parts / n_sheets)
    return [list(range(i, min(i + size, n_parts))) for i in range(0, n_parts, size)]


def map_file_names(n_parts: int, per_sheet: int = PARTS_PER_SHEET) -> list[str]:
    n = len(sheet_groups(n_parts, per_sheet))
    if n <= 1:
        return [f"{MAP_NAME}.png"]
    return [f"{MAP_NAME}_sheet{i + 1}of{n}.png" for i in range(n)]


def stretch_limits(
    rgb_inside: np.ndarray, percentiles: tuple[float, float] = STRETCH_PERCENTILES
) -> tuple[float, float]:
    """One (low, high) for all three bands, from the pixels inside the ROI."""
    values = np.asarray(rgb_inside, dtype=float)
    values = values[np.isfinite(values) & (values > 0)]
    if values.size == 0:
        return 0.0, 1.0
    low, high = np.percentile(values, percentiles)
    return float(low), float(max(high, low + 1.0))


def stretch_rgb(rgb: np.ndarray, low: float, high: float, gamma: float = STRETCH_GAMMA) -> np.ndarray:
    """Scale reflectance to 0..1 for display: linear between low and high, then gamma."""
    scaled = np.clip((np.asarray(rgb, dtype=float) - low) / (high - low), 0.0, 1.0)
    return scaled**gamma


def scale_bar_metres(width_m: float) -> int:
    """A round length for a scale bar: the largest of 1-2-5 x 10^n under a third of the width."""
    target = width_m / 3.0
    best = 1
    for exponent in range(0, 7):
        for lead in (1, 2, 5):
            length = lead * 10**exponent
            if length <= target:
                best = length
    return best


def colour_image(codes: np.ndarray, legend: Sequence[dict[str, Any]], inside: np.ndarray) -> np.ndarray:
    """An RGBA image of a categorical raster, coloured from its legend; clear outside."""
    rgba = np.zeros((*codes.shape, 4), dtype=float)
    for entry in legend:
        h = entry["color"]
        colour = [int(h[i : i + 2], 16) / 255.0 for i in (0, 2, 4)]
        rgba[(codes == int(entry["value"])) & inside] = [*colour, 1.0]
    return rgba


# ---------------------------------------------------------------------------
# Earth Engine (read-only)
# ---------------------------------------------------------------------------
def run_stages_read_only(config: Any, roi: Any) -> tuple[Any, dict[str, Any], Path]:
    """Run masking and data_load, reading the cache and submitting nothing."""
    from fmu.pipeline import Pipeline
    from fmu.stages.base import PipelineContext
    from fmu.stages.data_load import DataLoadStage  # noqa: F401  registers the stage
    from fmu.stages.masking import MaskingStage  # noqa: F401  registers the stage
    from fmu.utils.logging import init_logging

    ctx = PipelineContext()
    ctx.set("roi", roi)
    run_dir = init_logging(config_name=config.name)
    result = Pipeline(
        ["masking", "data_load"], use_cache=True, submit_exports=False
    ).run(config=config, run_dir=run_dir, initial_context=ctx)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    if manifest.get("submit_exports") is not False or any(
        s.get("export_tasks") for s in manifest["stages"]
    ):
        raise RuntimeError("the run was not read-only; refusing to go on.")
    return result.context, manifest, run_dir


def download_geotiff(
    image: Any,
    bounds: tuple[float, float, float, float],
    scale_m: float,
    path: Path,
    band_names: Sequence[str],
    dtype: str,
    nodata: float | None,
    attempts: int = 4,
    pause_s: float = 20.0,
    keep: BaseGeometry | None = None,
) -> None:
    """One interactive download of `image` over `bounds`, saved as a GeoTIFF.

    The grid is EPSG:4326 at `scale_m`, anchored at (0, 0): the grid the legacy
    layout's cache exports land on (an asset of the per-step layout is on the
    ROI's UTM grid, and is resampled; review C31). Retries a failed request a
    few times before giving up.
    With `keep`, every pixel that geometry does not touch is written as
    `nodata` (see `blank_untouched`).
    """
    import ee

    d = pixel_size_deg(scale_m)
    params = {
        "region": ee.Geometry.Rectangle(list(bounds), "EPSG:4326", False),
        "crs": "EPSG:4326",
        "crs_transform": [d, 0, 0, 0, -d, 0],
        "format": "GEO_TIFF",
    }
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            url = image.getDownloadURL(params)
            with urllib.request.urlopen(url, timeout=600) as response:  # noqa: S310 - EE url
                data = response.read()
            break
        except Exception as e:  # noqa: BLE001 - retried, then raised
            last = e
            print(f"  download of {path.name} failed (attempt {attempt} of {attempts}): {e}")
            if attempt == attempts:
                raise RuntimeError(f"could not download {path.name}: {e}") from last
            time.sleep(pause_s)

    with rasterio.MemoryFile(data) as mem, mem.open() as src:
        array = src.read().astype(dtype)
        if keep is not None and nodata is not None:
            array = blank_untouched(array, keep, src.transform, nodata)
        profile = {
            "driver": "GTiff", "height": src.height, "width": src.width,
            "count": src.count, "dtype": dtype, "crs": src.crs, "transform": src.transform,
            "compress": "deflate", "nodata": nodata,
        }
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(array)
        for i, name in enumerate(band_names, start=1):
            dst.set_band_description(i, name)


def true_colour_bands(band_names: Sequence[str]) -> list[str]:
    """The composite's red, green and blue bands (B4, B3, B2, with any reducer suffix)."""
    picked = []
    for wanted in ("B4", "B3", "B2"):
        matches = [b for b in band_names if re.fullmatch(rf"{wanted}(_.+)?", b)]
        if len(matches) != 1:
            raise ValueError(f"expected one {wanted} band in the composite, found {matches}.")
        picked.append(matches[0])
    return picked


def download_part(
    ctx: Any, part: RoiPart, scale_m: float, out_dir: Path, rgb_bands: Sequence[str]
) -> dict[str, Path]:
    """Save the four rasters of one part. Returns their paths by product."""
    import ee

    geometry = ee.Geometry(mapping(part.geometry))
    bounds = snapped_bounds(part.geometry.bounds, scale_m)
    files = {
        "mask_provenance": out_dir / f"{part.slug}_mask_provenance.tif",
        "habitat_mask": out_dir / f"{part.slug}_habitat_mask.tif",
        "landcover_summary": out_dir / f"{part.slug}_landcover_summary.tif",
        "true_colour": out_dir / f"{part.slug}_true_colour.tif",
    }
    # unmask(value, False): fill outside the clipped footprint too. With the
    # default (same footprint) the download writes 0 there, which every layer
    # here uses as a legend value. `keep` then sets whatever the part does not
    # touch to the no-data value locally, whatever Earth Engine returned.
    provenance = ctx.get("mask_provenance").select(["reason", "source"]).clip(geometry)
    download_geotiff(provenance.unmask(NODATA, False).toUint8(), bounds, scale_m,
                     files["mask_provenance"], ["reason", "source"], "uint8", NODATA,
                     keep=part.geometry)
    habitat = ctx.get("habitat_mask").select([0]).clip(geometry)
    download_geotiff(habitat.unmask(NODATA, False).toUint8(), bounds, scale_m,
                     files["habitat_mask"], ["habitat_mask"], "uint8", NODATA,
                     keep=part.geometry)
    summary = ctx.get("landcover_summary").select([0]).clip(geometry)
    download_geotiff(summary.unmask(NODATA, False).toUint8(), bounds, scale_m,
                     files["landcover_summary"], ["landcover_summary"], "uint8", NODATA,
                     keep=part.geometry)
    rgb = ctx.get("s2_composite").select(list(rgb_bands)).clip(geometry)
    download_geotiff(rgb.unmask(0, False).clamp(0, 65535).toUint16(), bounds, scale_m,
                     files["true_colour"], list(rgb_bands), "uint16", 0, keep=part.geometry)
    return files


def compare_with_mask_asset(ctx: Any, asset_id: str, scale_m: float) -> dict[str, Any]:
    """Area over which another cached habitat_mask differs from the one in use."""
    import ee

    from fmu.utils.gee import safe_get_info

    used = ctx.get("habitat_mask").select([0]).unmask(0).eq(1)
    other = ee.Image(asset_id).select([0]).unmask(0).eq(1)
    area = ee.Image.pixelArea()
    got = safe_get_info(
        area.rename("total").addBands(area.updateMask(used.neq(other)).rename("differs"))
        .reduceRegion(reducer=ee.Reducer.sum(), geometry=ctx.get("roi"), crs="EPSG:4326",
                      scale=scale_m, maxPixels=int(1e10), tileScale=4),
        context="comparison with another cached habitat_mask",
    )
    total, differs = float(got.get("total") or 0.0), float(got.get("differs") or 0.0)
    return {
        "label": "/".join(asset_id.rsplit("/", 3)[-3:]),
        "asset": asset_id,
        "area_ha": round(total / 1e4, 4),
        "area_ha_differs": round(differs / 1e4, 4),
        "share_differs": round(differs / total, 6) if total else 0.0,
    }


# ---------------------------------------------------------------------------
# Drawing (matplotlib is imported here, not at the top: CI does not install it)
# ---------------------------------------------------------------------------
def _load_part_arrays(files: dict[str, Path], geometry: BaseGeometry) -> dict[str, Any]:
    with rasterio.open(files["mask_provenance"]) as ds:
        reason, source = ds.read(1), ds.read(2)
        transform, hw, bounds = ds.transform, (ds.height, ds.width), ds.bounds
    with rasterio.open(files["true_colour"]) as ds:
        rgb = np.moveaxis(ds.read([1, 2, 3]), 0, -1).astype(float)
    inside = inside_mask(geometry, transform, hw) & (reason != NODATA)
    return {
        "reason": reason, "source": source, "rgb": rgb, "inside": inside,
        "extent": (bounds.left, bounds.right, bounds.bottom, bounds.top),
    }


def _draw_panel(ax: Any, image: np.ndarray, extent: Sequence[float], part: RoiPart,
                points: Sequence[dict[str, Any]], title: str, bar: bool) -> None:
    import matplotlib.patheffects as pe

    lat = part.geometry.centroid.y
    ax.imshow(image, extent=extent, interpolation="nearest", origin="upper", zorder=1)
    ax.set_aspect(1.0 / math.cos(math.radians(lat)))
    rings = [part.geometry.exterior, *part.geometry.interiors]
    for ring in rings:
        xs, ys = ring.xy
        ax.plot(xs, ys, color="white", linewidth=2.6, zorder=3, solid_joinstyle="round")
        ax.plot(xs, ys, color="black", linewidth=1.1, zorder=4, solid_joinstyle="round")
    here = [r for r in points if r["part"] == part.name]
    kept = [r for r in here if r["kept"] is True]
    dropped = [r for r in here if r["kept"] is False]
    if kept:
        ax.scatter([r["lon"] for r in kept], [r["lat"] for r in kept], zorder=6, **_KEPT_STYLE)
    if dropped:
        xs_d, ys_d = [r["lon"] for r in dropped], [r["lat"] for r in dropped]
        ax.scatter(xs_d, ys_d, zorder=7, **_DROPPED_HALO)
        ax.scatter(xs_d, ys_d, zorder=8, **_DROPPED_STYLE)
    minx, miny, maxx, maxy = part.geometry.bounds
    pad_x, pad_y = 0.04 * (maxx - minx), 0.04 * (maxy - miny)
    ax.set_xlim(minx - pad_x, maxx + pad_x)
    ax.set_ylim(miny - 3.2 * pad_y, maxy + pad_y)
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_title(title, fontsize=10.5, color="#1A1A1A", pad=4)
    if bar:
        m_per_deg = _EE_METRES_PER_DEGREE * math.cos(math.radians(lat))
        length_m = scale_bar_metres((maxx - minx) * m_per_deg)
        x0, y0 = minx, miny - 1.9 * pad_y
        ax.plot([x0, x0 + length_m / m_per_deg], [y0, y0], color="black", linewidth=3.0,
                solid_capstyle="butt", zorder=8)
        label = f"{length_m} m" if length_m < 1000 else f"{length_m / 1000:g} km"
        ax.annotate(label, xy=(x0 + length_m / m_per_deg, y0), xytext=(7, 0),
                    textcoords="offset points", va="center", ha="left", fontsize=10,
                    color="black", zorder=8,
                    path_effects=[pe.withStroke(linewidth=2.5, foreground="white")])


def draw_sheet(
    *,
    out_path: Path,
    parts: Sequence[RoiPart],
    arrays: dict[str, dict[str, Any]],
    points: Sequence[dict[str, Any]],
    part_tables: dict[str, dict[str, Any]],
    reason_layer: dict[str, Any],
    source_layer: dict[str, Any],
    stretch: dict[str, Any],
    heading: str,
    caption_lines: Sequence[str],
    show_source: bool,
    subheading: str = "",
    absent_reasons: Sequence[int] = (),
    point_noun: str = "point",
) -> None:
    """Draw one sheet: for each part, true colour beside the mask by reason.

    `absent_reasons` are the reason codes no pixel of the ROI has: their legend
    entries stay (the legend is the stage's own) and say "none in this ROI".
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Calibri", "Carlito", "Arial", "Liberation Sans", "DejaVu Sans"],
        "text.color": "#1A1A1A",
    })
    per_part = 3 if show_source else 2
    single = len(parts) == 1
    label_h = 0.62  # over each part: its name, then the panel titles
    title_h = 0.34  # a panel title, where panels are stacked
    bar_h = 0.12
    margin = 0.25
    fig_w = 15.5
    gap_w = 0.35

    def ratio(part: RoiPart) -> float:
        """Height over width of a part's panel, on the ground."""
        minx, miny, maxx, maxy = part.geometry.bounds
        return (maxy - miny) * 1.16 / (
            (maxx - minx) * 1.08 * math.cos(math.radians(part.geometry.centroid.y))
        )

    # Rows of the sheet. A part much wider than tall gets a row to itself with
    # its panels stacked, each as wide as the sheet; side by side it would be a
    # sliver. Other parts go two to a row, panels side by side.
    rows: list[tuple[str, list[RoiPart]]] = []
    for part in parts:
        if ratio(part) < WIDE_PART_RATIO:
            rows.append(("stacked", [part]))
        elif not single and rows and rows[-1][0] == "beside" and len(rows[-1][1]) < 2:
            rows[-1][1].append(part)
        else:
            rows.append(("beside", [part]))

    panel_w = (fig_w - 2 * margin - gap_w) / (2 * per_part)
    if single and rows[0][0] == "beside":
        # One part: size the sheet to the part, so a tall ROI does not leave
        # two narrow maps in a wide page.
        panel_w = min((fig_w - 2 * margin) / per_part, 7.2 / ratio(parts[0]))
        fig_w = max(12.0, per_part * panel_w + 2 * margin)
        panel_w = (fig_w - 2 * margin) / per_part
    full_w = fig_w - 2 * margin
    image_h: list[float] = []
    row_h: list[float] = []
    for kind, members in rows:
        if kind == "stacked":
            h = min(full_w * ratio(members[0]), 5.5)
            image_h.append(h)
            row_h.append(label_h + per_part * (h + title_h) + bar_h)
        else:
            h = min(max(panel_w * ratio(m) for m in members), 7.2 if single else 5.2)
            image_h.append(h)
            row_h.append(label_h + h + bar_h)
    # The foot: legend, then the caption, sized to the text it has to hold.
    caption_pt = 12.0
    line_h = caption_pt * 1.35 / 72.0
    wrapped: list[str] = []
    for line in [reason_layer["legend_note"], *caption_lines]:
        wrapped += textwrap.wrap(line, width=int(11.2 * fig_w))
    legend_cols = 4 if fig_w >= 14 else 3
    n_handles = len(reason_layer["legend"]) + 1 + (2 if points else 0)
    legend_rows = math.ceil(n_handles / legend_cols)
    legend_h = 0.42 + 0.27 * legend_rows
    foot_h = 0.12 + legend_h + (0.6 if show_source else 0.0) + line_h * len(wrapped) + 0.3
    heading_lines = textwrap.wrap(heading, width=int(7.4 * fig_w)) or [""]
    head_h = 0.3 + 0.27 * len(heading_lines) + (0.3 if subheading else 0.0)
    fig_h = head_h + sum(row_h) + foot_h
    fig = plt.figure(figsize=(fig_w, fig_h), facecolor="white")
    fig.text(0.5, 1 - 0.16 / fig_h, "\n".join(heading_lines), ha="center", va="top",
             fontsize=14, fontweight="bold", linespacing=1.3)
    if subheading:
        fig.text(0.5, 1 - (0.2 + 0.27 * len(heading_lines)) / fig_h, subheading, ha="center",
                 va="top", fontsize=11, color="#444444")

    def panel(x: float, top: float, w: float, h: float) -> Any:
        """An axes with its top-left corner at (x, top), in inches from the top-left."""
        ax = fig.add_axes((x / fig_w, 1 - (top + h) / fig_h, w / fig_w, h / fig_h))
        ax.set_anchor("N")
        return ax

    def draw_part(part: RoiPart, x: float, top: float, w: float, h: float, stacked: bool) -> None:
        data = arrays[part.slug]
        table = part_tables[part.slug]
        here = [r for r in points if r["part"] == part.name]
        label = f"{part.name}: {_ha(table['area_ha'])}, {_pct(table['share_kept'])} kept"
        if points:
            label += (f"; {plural(point_noun, 2)} "
                      f"{sum(1 for r in here if r['kept'] is True)} kept, "
                      f"{sum(1 for r in here if r['kept'] is False)} dropped")
        span = w if stacked else per_part * w
        fig.text((x + span / 2) / fig_w, 1 - (top + 0.06) / fig_h, label, ha="center",
                 va="top", fontsize=11.5, fontweight="bold")
        rgb = stretch_rgb(data["rgb"], stretch["low"], stretch["high"], stretch["gamma"])
        images = [
            (np.dstack([rgb, data["inside"].astype(float)]), "True colour (Sentinel-2)"),
            (colour_image(data["reason"], reason_layer["legend"], data["inside"]),
             reason_layer["title"]),
        ]
        if show_source:
            images.append(
                (colour_image(data["source"], source_layer["legend"], data["inside"]),
                 source_layer["title"])
            )
        for k, (image, title) in enumerate(images):
            if stacked:
                ax = panel(x, top + label_h + k * (h + title_h), w, h)
            else:
                ax = panel(x + k * w, top + label_h, w, h)
            _draw_panel(ax, image, data["extent"], part, points, title, k == 0)

    top = head_h
    for (kind, members), h, total in zip(rows, image_h, row_h, strict=True):
        if kind == "stacked":
            draw_part(members[0], margin, top, full_w, h, True)
        else:
            for slot, part in enumerate(members):
                draw_part(part, margin + slot * (per_part * panel_w + gap_w), top, panel_w, h,
                          False)
        top += total

    def legend_label(entry: dict[str, Any]) -> str:
        none_here = int(entry["value"]) in absent_reasons
        return entry["label"] + (" (none in this ROI)" if none_here else "")

    handles: list[Any] = [
        Patch(facecolor=f"#{e['color']}", edgecolor="#555555", linewidth=0.5,
              label=legend_label(e))
        for e in sorted(reason_layer["legend"], key=lambda e: (e["value"] == 0, e["value"]))
    ]
    handles.append(Line2D([], [], color="black", linewidth=1.3,
                          label="ROI outline (white outside it)"))
    if points:
        noun = point_noun[0].upper() + point_noun[1:]
        handles.append(Line2D([], [], linestyle="none", marker=_KEPT_STYLE["marker"],
                              markersize=7.5, markerfacecolor=_KEPT_STYLE["facecolor"],
                              markeredgecolor=_KEPT_STYLE["edgecolor"],
                              label=f"{noun} kept (on a habitat pixel)"))
        handles.append(Line2D([], [], linestyle="none", marker=_DROPPED_STYLE["marker"],
                              markersize=9, markerfacecolor="none",
                              markeredgecolor=_DROPPED_COLOUR, markeredgewidth=2.0,
                              label=f"{noun} dropped (on a removed pixel)"))
    if len(handles) != n_handles:
        raise RuntimeError("the legend has a different number of entries than was laid out.")
    legend_top = (foot_h - 0.12) / fig_h
    legend = fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, legend_top),
                        ncol=legend_cols, frameon=False, fontsize=11,
                        handlelength=1.5, columnspacing=1.6, title=reason_layer["title"],
                        title_fontproperties={"weight": "bold", "size": 11})
    fig.add_artist(legend)
    text_top = legend_top - legend_h / fig_h
    if show_source:
        source_handles = [
            Patch(facecolor=f"#{e['color']}", edgecolor="#555555", linewidth=0.5, label=e["label"])
            for e in sorted(source_layer["legend"], key=lambda e: (e["value"] == 0, e["value"]))
        ]
        fig.legend(handles=source_handles, loc="upper center", bbox_to_anchor=(0.5, text_top),
                   ncol=3, frameon=False, fontsize=11, handlelength=1.5,
                   title=source_layer["title"],
                   title_fontproperties={"weight": "bold", "size": 11})
        text_top -= 0.6 / fig_h
    fig.text(0.02, text_top, "\n".join(wrapped), ha="left", va="top", fontsize=caption_pt,
             linespacing=1.35, color="#1A1A1A")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=MAP_DPI, facecolor="white")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Putting it together
# ---------------------------------------------------------------------------
def _layer_record(config: Any, manifest: dict[str, Any], fingerprint: str) -> dict[str, Any]:
    """Which layers were read from cached assets and which were computed live."""
    from fmu.utils.caching import cached_asset_path

    layers: dict[str, Any] = {}
    for stage in manifest["stages"]:
        for key, status in sorted(stage.get("cache_status", {}).items()):
            hit = status == "hit"
            layers[key] = {
                "stage": stage["name"],
                "cache_status": status,
                "read_from": "cached asset" if hit else "computed live, not exported",
                # The run's own key for the stage (one per stage in the per-step
                # cache layout); the fingerprint for a manifest made before round 9.
                "asset": cached_asset_path(
                    config.name, stage["name"], key, stage.get("cache_key") or fingerprint
                )
                if hit else None,
            }
    return layers


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + "\n")


def git_blob_id(path: Path) -> str:
    """The id git gives a file's content (what `git hash-object <path>` prints).

    Recorded for the scripts that ran, so a record made before they were
    committed still names them: `git ls-tree <commit> <path>` shows the same id
    for the commit that holds that exact file.
    """
    data = Path(path).read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(data) + data, usedforsecurity=False).hexdigest()


def code_record(code_files: Sequence[Path]) -> dict[str, str]:
    """`{path relative to the repo: git blob id}` of the scripts that ran."""
    repo = Path(__file__).resolve().parent.parent
    out: dict[str, str] = {}
    for path in code_files:
        resolved = Path(path).resolve()
        try:
            name = str(resolved.relative_to(repo))
        except ValueError:
            name = str(resolved)
        out[name] = git_blob_id(resolved)
    return out


def absent_reason_codes(reason_arrays: Sequence[np.ndarray], legend: Sequence[dict[str, Any]]) -> list[int]:
    """Legend codes that none of the given arrays of in-ROI reason codes holds."""
    present: set[int] = set()
    for values in reason_arrays:
        present.update(int(v) for v in np.unique(values))
    return sorted(int(e["value"]) for e in legend if int(e["value"]) not in present)


def build(args: argparse.Namespace, command_line: str, code_files: Sequence[Path] = ()) -> int:
    from fmu.config import load_config
    from fmu.utils.caching import config_fingerprint
    from fmu.utils.provenance import git_state

    config = load_config(args.config)
    fingerprint = config_fingerprint(config)
    docs_dir = Path(args.docs_dir) / config.name
    data_dir = Path(args.data_dir) / config.name
    scale = float(config.export.analysis_scale_m)
    roi_file = Path(config.roi.roi_file)
    roi_json = json.loads(roi_file.read_text())
    parts = roi_parts(roi_json, args.part_name_key)
    noun = args.point_noun
    print(f"{config.name}: fingerprint {fingerprint}, {len(parts)} ROI part(s)")
    saved_path = data_dir / "masking_transparency.json"
    ran = {
        "date": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "command_line": command_line,
        "git": git_state(),
        "code_git_blob_ids": code_record([Path(__file__), *code_files]),
    }

    def part_files(part: RoiPart) -> dict[str, Path]:
        return {k: data_dir / f"{part.slug}_{k}.tif"
                for k in ("mask_provenance", "habitat_mask", "landcover_summary", "true_colour")}

    if args.redraw:
        saved = json.loads(saved_path.read_text())
        if saved["fingerprint"] != fingerprint:
            raise SystemExit(
                f"--redraw: the saved rasters are of fingerprint {saved['fingerprint']}, the "
                f"config is now {fingerprint}. Run without --redraw."
            )
        files = {p.slug: part_files(p) for p in parts}
    else:
        from fmu.utils.gee import init_gee, load_roi_geometry

        init_gee()
        ctx, manifest, run_dir = run_stages_read_only(config, load_roi_geometry(roi_file))
        masking = next(s for s in manifest["stages"] if s["name"] == "masking")
        layers = _layer_record(config, manifest, fingerprint)
        import ee

        rgb_bands = true_colour_bands(ee.Image(ctx.get("s2_composite")).bandNames().getInfo())
        files = {}
        for part in parts:
            print(f"  downloading part {part.index + 1} of {len(parts)}: {part.name}")
            files[part.slug] = download_part(ctx, part, scale, data_dir, rgb_bands)
        comparisons = [
            compare_with_mask_asset(ctx, asset, scale) for asset in args.compare_mask_asset or []
        ]
        saved = {
            "config_name": config.name,
            "fingerprint": fingerprint,
            "transparency": masking["transparency"],
            "layer_status": {k: v["cache_status"] for k, v in layers.items()},
            "rgb_bands": rgb_bands,
            "comparisons": comparisons,
        }
        _write_json(saved_path, saved)
        _write_json(data_dir / "roi_outline.geojson", roi_outline_geojson(parts))

    transparency = saved["transparency"]
    numbers = summary_values(transparency)
    reason_layer = display_layer(transparency, "mask_provenance", "reason")
    source_layer = display_layer(transparency, "mask_provenance", "source")
    source_labels = legend_labels(source_layer)

    tables = {p.slug: tabulate_part(files[p.slug]["mask_provenance"],
                                    files[p.slug]["habitat_mask"], p.geometry) for p in parts}
    check = pooled(list(tables.values()))
    check.update(
        manifest_area_ha=numbers["area_ha"], manifest_share_kept=numbers["share_kept"],
        note="rasters count pixels whose centre is inside a part; the manifest weights edge "
             "pixels by coverage",
    )
    print(f"  manifest: {numbers['area_ha']:.1f} ha, {numbers['share_kept']:.1%} kept;"
          f" rasters: {check['area_ha']:.1f} ha, {check['share_kept']:.1%} kept")

    records: list[dict[str, Any]] | None = None
    counts: dict[str, int] | None = None
    if args.points:
        records = classify_points(
            read_points(Path(args.points), args.id_col, args.lon_col, args.lat_col), parts,
            {s: f["mask_provenance"] for s, f in files.items()},
            {s: f["habitat_mask"] for s, f in files.items()},
            legend_labels(reason_layer), source_labels,
        )
        _write_json(data_dir / "points.geojson", points_geojson(records))
        counts = count_points(records)
        print(f"  points: {counts['given']} given, {counts['in_roi']} in the ROI, "
              f"{counts['kept']} kept, {counts['dropped']} dropped")
    elif (data_dir / "points.geojson").exists():
        (data_dir / "points.geojson").unlink()

    # ---- maps
    arrays = {p.slug: _load_part_arrays(files[p.slug], p.geometry) for p in parts}
    inside_rgb = np.concatenate([a["rgb"][a["inside"]].ravel() for a in arrays.values()])
    low, high = stretch_limits(inside_rgb)
    stretch = {"low": low, "high": high, "gamma": STRETCH_GAMMA,
               "percentiles": list(STRETCH_PERCENTILES), "bands": saved["rgb_bands"]}
    show_source = not one_source_decided(numbers)
    absent = absent_reason_codes([a["reason"][a["inside"]] for a in arrays.values()],
                                 reason_layer["legend"])
    names = map_file_names(len(parts))
    for old in docs_dir.glob(f"{MAP_NAME}*.png"):
        old.unlink()
    status = saved["layer_status"]

    def how(key: str) -> str:
        return "read from the cached asset" if status.get(key) == "hit" else "computed live"

    caption = [
        decided_sentence(numbers, source_labels)
        + f" Whole ROI: {_ha(numbers['area_ha'])}, {_pct(numbers['share_kept'])} kept as habitat."
        + f" habitat_mask {how('habitat_mask')}; reason layer {how('mask_provenance')}.",
    ]
    if counts is not None:
        line = (f"A {noun} is kept or dropped by the single {scale:g} m pixel it falls on, so a "
                f"dropped {noun} can sit in a patch that is otherwise kept.")
        if counts["outside_roi"]:
            line += (f" {counts['outside_roi']} of the {counts['given']} "
                     f"{plural(noun, counts['given'])} given "
                     f"{'lies' if counts['outside_roi'] == 1 else 'lie'} outside the ROI and "
                     f"{'is' if counts['outside_roi'] == 1 else 'are'} not drawn.")
        caption.append(line)
    caption += list(args.map_note or [])
    caption.append(
        f"True colour: {', '.join(stretch['bands'])} of the composite the pipeline segments on "
        f"({how('s2_composite')}), one linear stretch {low:.0f} to {high:.0f} for all three "
        f"bands, gamma {STRETCH_GAMMA:g}. North is up. Numbers: summary.md beside this file."
    )
    groups = sheet_groups(len(parts))
    # A one-part ROI is the whole ROI: label it with the manifest's numbers, so
    # the sheet does not show two roundings of one quantity.
    label_tables = {parts[0].slug: numbers} if len(parts) == 1 else tables
    for sheet, (name, group) in enumerate(zip(names, groups, strict=True), start=1):
        heading = args.title or f"Habitat mask: {config.name}"
        sub = [f"config {config.name}"] if args.title else []
        if len(groups) > 1:
            sub.append(f"sheet {sheet} of {len(groups)}")
        draw_sheet(
            out_path=docs_dir / name, parts=[parts[i] for i in group], arrays=arrays,
            points=records or [], part_tables=label_tables, reason_layer=reason_layer,
            source_layer=source_layer, stretch=stretch, heading=heading,
            subheading=", ".join(sub), caption_lines=caption, show_source=show_source,
            absent_reasons=absent, point_noun=noun,
        )
        print(f"  wrote {docs_dir / name}")

    # ---- summary.md
    text = summary_markdown(
        config_name=config.name, config_path=str(args.config), roi_file=str(roi_file),
        fingerprint=fingerprint, numbers=numbers, reason_layer=reason_layer,
        source_layer=source_layer, layer_status=status,
        part_tables=[(p.name, tables[p.slug]) for p in parts], points=records,
        map_files=names, notes=args.note or [], comparisons=saved.get("comparisons") or [],
        stretch=stretch, title=args.title, point_noun=noun,
        roi_notes=roi_file_notes(roi_json), scale_m=scale,
    )
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "summary.md").write_text(text)
    print(f"  wrote {docs_dir / 'summary.md'}")

    # ---- run_record.json. A run on Earth Engine writes it afresh. --redraw
    # touches no raster, so it keeps the record of the run that made them and
    # adds an entry saying which code redrew the maps and summary.md.
    record_path = docs_dir / "run_record.json"
    if not args.redraw:
        _write_json(record_path, {
            "config_name": config.name,
            "config_path": str(args.config),
            "cache_fingerprint": fingerprint,
            "roi_file": str(roi_file),
            "roi_parts": [p.name for p in parts],
            **ran,
            "earth_engine": {
                "read_only": True,
                "pipeline": "Pipeline(['masking', 'data_load'], use_cache=True, "
                            "submit_exports=False)",
                "export_tasks_submitted": 0,
                "download_grid": f"EPSG:4326 at {scale:g} m, anchored at (0, 0)",
            },
            "layers": layers,
            "comparison_masks": comparisons,
            "raster_check": check,
            "points_file": str(args.points) if args.points else None,
            "pipeline_run_dir": str(run_dir),
            "data_dir": str(data_dir),
            "redraws_since_this_run": [],
        })
        print(f"  wrote {record_path}")
    elif record_path.exists():
        record = json.loads(record_path.read_text())
        record.setdefault("redraws_since_this_run", []).append(ran)
        _write_json(record_path, record)
        print(f"  added this redraw to {record_path}")
    else:
        print(f"  NOTE: no {record_path} to add this redraw to.")
    return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--config", required=True, help="Path to the pipeline config YAML.")
    parser.add_argument("--points", help="CSV of points to mark as kept or dropped.")
    parser.add_argument("--id-col", default="id", help="Column of --points holding the point id.")
    parser.add_argument("--lon-col", default="lon", help="Longitude column (EPSG:4326).")
    parser.add_argument("--lat-col", default="lat", help="Latitude column (EPSG:4326).")
    parser.add_argument("--point-noun", default="point",
                        help="What a point is called on the maps and in summary.md, in the "
                             "singular (for example 'field plot').")
    parser.add_argument("--docs-dir", default="docs/transparency",
                        help="Maps, summary.md and run_record.json go in <docs-dir>/<config>/.")
    parser.add_argument("--data-dir", default="outputs/transparency",
                        help="GeoTIFF and GeoJSON go in <data-dir>/<config>/.")
    parser.add_argument("--part-name-key", default="name",
                        help="Property of the ROI file that names each part (see roi_parts).")
    parser.add_argument("--title",
                        help="Heading of the maps and of summary.md, in plain words. The config "
                             "name is printed under it. Default: 'Habitat mask: <config>'.")
    parser.add_argument("--note", action="append",
                        help="A sentence to add to summary.md. Repeatable.")
    parser.add_argument("--map-note", action="append",
                        help="A sentence to add to the caption of every map. Repeatable.")
    parser.add_argument("--compare-mask-asset", action="append",
                        help="Asset id of another cached habitat_mask to compare with the one "
                             "in use (read only). Repeatable.")
    parser.add_argument("--redraw", action="store_true",
                        help="Redraw the maps and summary.md from the saved rasters. "
                             "No Earth Engine.")
    return parser.parse_args(argv)


def main(
    argv: Sequence[str] | None = None,
    command_line: str | None = None,
    code_files: Sequence[Path] = (),
) -> int:
    """Run for one config. A wrapper passes its own command line and its own file."""
    args = parse_args(argv)
    if command_line is None:
        command_line = " ".join(shlex.quote(a) for a in ["python", *sys.argv])
    return build(args, command_line, code_files)


if __name__ == "__main__":
    sys.exit(main())

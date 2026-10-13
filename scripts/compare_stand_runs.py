"""How much do the stands of two runs differ? An offline comparison of two stand layers.

    python scripts/compare_stand_runs.py OLD.geojson NEW.geojson
        [--id-field stand_lbl] [--new-id-field NAME] [--type-field cluster_id]
        [--out results.txt] [--per-stand-csv stands.csv]

A re-run of the pipeline is not expected to give the same stands to the last vertex: input
datasets get updated and the segmentation can differ between runs. This tool MEASURES the
difference. It assumes neither that there is none nor that it is small.

Both layers are GeoJSON in longitude and latitude (WGS84), read with the json module and
shapely. Nothing here is specific to a site. Earth Engine is not used.
(scripts/compare_cached_assets.py is the other half: it compares the cached Earth Engine
rasters of two runs pixel by pixel and needs Earth Engine. This one compares what was exported.)

WHAT A STAND IS
  A stand is every polygon that carries the same value of the id property (default stand_lbl).
  Earth Engine writes one polygon per connected piece, so a stand can be several polygons. The
  pieces are dissolved into one geometry before anything is measured.

WHAT IS REPORTED
  Counts      polygons and stands in each layer; stands made of more than one piece; invalid
              polygons that had to be repaired; features left out (no geometry, or no id).
  Areas       in hectares, true areas: every geometry is projected to a Lambert azimuthal
              equal-area projection centred on the middle of the two layers before it is
              measured (never square degrees). Total stand area of each layer, the area each
              layer covers (its footprint), and the area covered by both.
  Same outline  how many stands have exactly the same outline in both layers, after snapping
              the coordinates to a grid of 1e-7 degrees (about 1 cm). Outlines are matched by
              geometry, not by id and not by position in the file. The same count for polygons.
  IoU         area-weighted intersection over union, in both directions. For old -> new:

                for every old stand A, take the new stand B that overlaps it most
                (largest area of A and B in common);
                IoU(A) = area(A and B in common) / area(A and B together);
                an old stand that no new stand overlaps has IoU(A) = 0;
                the reported figure is the mean of IoU(A) over old stands, each weighted by
                area(A).

              new -> old is the same with the layers swapped. The two differ when stands were
              split or merged: an old stand cut in two halves scores 0.5 old -> new, and each
              half also scores 0.5 new -> old; two old stands merged into one score their
              share of the merged stand. Also reported: the share of area lying in stands
              whose IoU is at least 0.5, 0.9 and 0.99 (to within 1e-9, so that a stand cut
              exactly in half counts as 0.5), and the stands with no counterpart. An overlap
              below one square millimetre is rounding along a shared edge and is not counted.
  Types       only with --type-field: over the area both layers cover, the share where the
              old and the new stand carry the same type number, and the same share after the
              best one-to-one renumbering of the types (type numbers are arbitrary labels: a
              re-run can give the same grouping under other numbers).

OUTPUT
  A plain text table on the terminal. --out also writes it to a file; --per-stand-csv writes
  one row per stand (both directions) with its best match and IoU. Both hold results only: no
  dates, no run times, no machine names. Neither is written into a folder that holds files
  committed to git, so that a committed result cannot be overwritten: name a new folder.
  The folder is looked up without regard to upper and lower case, because on a file system
  that ignores case (macOS by default) RESULTS/ and results/ are one folder. The check is on
  the folder the file goes into and everything below it: a new, empty subfolder of a folder
  with committed files is accepted, since nothing committed can be overwritten there. This
  tool knows no site, so it cannot know which folders a project wants kept free of new
  files altogether; a caller that does (odisha_script/odisha_repro_compare.py) checks that
  itself.

Exit status 0 when the comparison ran, whatever it found; 2 when it could not run.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import shapely
from pyproj import CRS, Transformer
from scipy.optimize import linear_sum_assignment
from shapely.geometry import shape

GRID_DEG = 1e-7  # outlines are compared after snapping to this grid (about 1 cm)
IOU_LEVELS = (0.5, 0.9, 0.99)
M2_PER_HA = 10_000.0
# Two stands that only share an edge can come out of the overlay with a sliver of "common
# area" far below a square millimetre. That is rounding, not overlap, and is not counted.
MIN_OVERLAP_M2 = 1e-6
# A stand cut exactly in half has IoU 0.5, which the arithmetic can return as 0.49999999999.
# "IoU at least 0.5" therefore means at least 0.5 - IOU_EPS.
IOU_EPS = 1e-9
_POLYGON_TYPE_IDS = (3, 6)  # shapely geometry type ids of Polygon and MultiPolygon


# --------------------------------------------------------------------------- reading
@dataclass
class Layer:
    """One stand layer as read from a file: valid polygons in longitude and latitude."""

    name: str
    id_field: str
    type_field: str | None
    n_features: int = 0
    n_skipped: int = 0  # no geometry, no id, or nothing polygonal left after repair
    n_repaired: int = 0  # invalid polygons made valid
    ids: list[Any] = field(default_factory=list)  # one per kept polygon
    types: list[Any] = field(default_factory=list)  # one per kept polygon, None if absent
    geoms: list[Any] = field(default_factory=list)  # one per kept polygon


def normalise_id(value: Any) -> Any:
    """A stand id as a hashable value. 17, 17.0 and 16.999999999999996 are the same stand:
    Earth Engine writes whole numbers as floats that are not always exact."""
    if value is None or isinstance(value, bool):
        return None if value is None else str(value)
    if isinstance(value, int | float):
        if value != value:  # NaN
            return None
        return int(round(value)) if abs(value - round(value)) < 1e-6 else float(value)
    return str(value)


def _sort_key(value: Any) -> tuple[int, Any]:
    return (0, value) if isinstance(value, int | float) else (1, str(value))


def _polygonal(geom: Any) -> Any:
    """The polygon part of a geometry, valid. None if there is none.

    A self-touching or self-crossing ring is repaired with make_valid, which can return lines
    and points beside the polygons; those have no area and are dropped."""
    if geom is None or geom.is_empty:
        return None
    if not geom.is_valid:
        geom = shapely.make_valid(geom)
    if shapely.get_type_id(geom) not in _POLYGON_TYPE_IDS:
        parts = [g for g in shapely.get_parts(geom) if shapely.get_type_id(g) in _POLYGON_TYPE_IDS]
        if not parts:
            return None
        geom = shapely.union_all(parts)
    if geom.is_empty or geom.area == 0:
        return None
    return geom


def layer_from_features(
    features: list[dict],
    id_field: str = "stand_lbl",
    type_field: str | None = None,
    name: str = "layer",
) -> Layer:
    """Build a Layer from GeoJSON features (dicts with "geometry" and "properties")."""
    layer = Layer(name=name, id_field=id_field, type_field=type_field, n_features=len(features))
    seen_fields: set[str] = set()
    for feat in features:
        props = feat.get("properties") or {}
        seen_fields.update(props)
        sid = normalise_id(props.get(id_field))
        geom_json = feat.get("geometry")
        if sid is None or not geom_json:
            layer.n_skipped += 1
            continue
        raw = shape(geom_json)
        geom = _polygonal(raw)
        if geom is None:
            layer.n_skipped += 1
            continue
        if not raw.is_valid:
            layer.n_repaired += 1
        layer.ids.append(sid)
        layer.types.append(normalise_id(props.get(type_field)) if type_field else None)
        layer.geoms.append(geom)
    if features and not layer.ids and id_field not in seen_fields:
        raise ValueError(
            f"{name}: no feature has the property {id_field!r}; "
            f"the properties present are {sorted(seen_fields)}"
        )
    return layer


def read_layer(path: Path, id_field: str = "stand_lbl", type_field: str | None = None) -> Layer:
    """Read a GeoJSON FeatureCollection in longitude and latitude."""
    path = Path(path)
    data = json.loads(path.read_text())
    if data.get("type") != "FeatureCollection" or "features" not in data:
        raise ValueError(f"{path.name}: not a GeoJSON FeatureCollection")
    return layer_from_features(data["features"], id_field, type_field, name=path.name)


# --------------------------------------------------------------------------- geometry
def equal_area_transformer(lon: float, lat: float) -> Transformer:
    """Longitude and latitude to metres in a Lambert azimuthal equal-area projection centred
    on (lon, lat). Equal-area on the WGS84 ellipsoid, so polygon areas are true areas."""
    crs = CRS.from_proj4(f"+proj=laea +lat_0={lat:.8f} +lon_0={lon:.8f} +datum=WGS84 +units=m")
    return Transformer.from_crs(4326, crs, always_xy=True)


def _project(geoms: list[Any], tr: Transformer) -> np.ndarray:
    arr = np.array(geoms, dtype=object)
    if len(arr) == 0:
        return arr

    def fwd(xy: np.ndarray) -> np.ndarray:
        x, y = tr.transform(xy[:, 0], xy[:, 1])
        return np.column_stack([x, y])

    out = shapely.transform(arr, fwd)
    bad = ~shapely.is_valid(out)
    if bad.any():
        out[bad] = [_polygonal(g) or shapely.Polygon() for g in out[bad]]
    return out


def _outline_key(geom_deg: Any) -> bytes:
    """What two geometries must share to count as the same outline: the same coordinates after
    snapping to GRID_DEG, whatever the ring order, start vertex or order of the pieces."""
    return shapely.to_wkb(shapely.normalize(geom_deg))


@dataclass
class _Stands:
    """The stands of one layer after dissolving: parallel arrays sorted by stand id."""

    ids: list[Any]
    geoms: np.ndarray  # projected, metres
    area_m2: np.ndarray
    n_pieces: np.ndarray
    types: list[Any]  # the type of the largest piece
    mixed_types: int  # stands whose pieces carry different types
    outline: list[bytes]  # per stand
    piece_outline: list[bytes]  # per polygon


def _dissolve(layer: Layer, tr: Transformer) -> _Stands:
    projected = _project(layer.geoms, tr)
    snapped = [shapely.set_precision(g, GRID_DEG) for g in layer.geoms]
    piece_outline = [_outline_key(g) for g in snapped]
    groups: dict[Any, list[int]] = {}
    for k, sid in enumerate(layer.ids):
        groups.setdefault(sid, []).append(k)
    ids = sorted(groups, key=_sort_key)
    geoms, outlines, n_pieces, types = [], [], [], []
    mixed = 0
    for sid in ids:
        idx = groups[sid]
        if len(idx) == 1:
            geoms.append(projected[idx[0]])
            outlines.append(piece_outline[idx[0]])
            types.append(layer.types[idx[0]])
        else:
            geoms.append(shapely.union_all([projected[k] for k in idx]))
            dissolved = shapely.union_all([snapped[k] for k in idx], grid_size=GRID_DEG)
            outlines.append(_outline_key(dissolved))
            largest = max(idx, key=lambda k: float(shapely.area(projected[k])))
            types.append(layer.types[largest])
            mixed += len({layer.types[k] for k in idx}) > 1
        n_pieces.append(len(idx))
    geom_arr = np.array(geoms, dtype=object)
    return _Stands(
        ids=ids,
        geoms=geom_arr,
        area_m2=shapely.area(geom_arr) if len(geom_arr) else np.zeros(0),
        n_pieces=np.array(n_pieces, dtype=int),
        types=types,
        mixed_types=mixed,
        outline=outlines,
        piece_outline=piece_outline,
    )


def _overlaps(a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Every pair (i, j) where a[i] and b[j] share area, and that area in square metres.
    A spatial index finds the candidate pairs, so the cost grows with the number of
    neighbours, not with len(a) * len(b)."""
    empty = (np.zeros(0, dtype=int), np.zeros(0, dtype=int), np.zeros(0))
    if len(a) == 0 or len(b) == 0:
        return empty
    tree = shapely.STRtree(b)
    ia, ib = tree.query(a, predicate="intersects")
    if len(ia) == 0:
        return empty
    try:
        inter = shapely.area(shapely.intersection(a[ia], b[ib]))
    except shapely.errors.GEOSException:
        # one awkward pair must not stop the comparison: redo pair by pair, and for a pair that
        # still fails intersect on a 1 mm grid, which is robust to near-coincident edges
        inter = np.zeros(len(ia))
        for k, (i, j) in enumerate(zip(ia, ib, strict=True)):
            try:
                inter[k] = shapely.intersection(a[i], b[j]).area
            except shapely.errors.GEOSException:
                inter[k] = shapely.intersection(a[i], b[j], grid_size=0.001).area
    keep = inter > MIN_OVERLAP_M2
    return ia[keep], ib[keep], inter[keep]


def _direction(
    area_a: np.ndarray,
    area_b: np.ndarray,
    ia: np.ndarray,
    ib: np.ndarray,
    inter: np.ndarray,
) -> dict[str, Any]:
    """IoU of every stand of layer a with the stand of layer b that overlaps it most."""
    n = len(area_a)
    best = np.full(n, -1, dtype=int)
    best_inter = np.zeros(n)
    # sort so that, within each stand of a, the largest overlap comes first; on a tie the
    # stand of b with the smaller id (stands are stored in id order)
    order = np.lexsort((ib, -inter, ia))
    ia_s, ib_s, inter_s = ia[order], ib[order], inter[order]
    first = np.ones(len(ia_s), dtype=bool)
    first[1:] = ia_s[1:] != ia_s[:-1]
    best[ia_s[first]] = ib_s[first]
    best_inter[ia_s[first]] = inter_s[first]
    matched = best >= 0
    union = area_a.copy()
    union[matched] = area_a[matched] + area_b[best[matched]] - best_inter[matched]
    iou = np.zeros(n)
    ok = matched & (union > 0)
    # an intersection cannot exceed the union; rounding in the overlay can say otherwise by
    # one part in 1e15, so the ratio is capped at 1
    iou[ok] = np.minimum(best_inter[ok] / union[ok], 1.0)
    total = float(area_a.sum())
    counts = np.bincount(best[matched], minlength=len(area_b)) if matched.any() else np.zeros(0)
    return {
        "n_stands": int(n),
        "best": best,
        "best_overlap_m2": best_inter,
        "iou": iou,
        "area_weighted_iou": float((iou * area_a).sum() / total) if total > 0 else float("nan"),
        "mean_iou": float(iou.mean()) if n else float("nan"),
        "median_iou": float(np.median(iou)) if n else float("nan"),
        "min_iou": float(iou.min()) if n else float("nan"),
        "share_area_iou_ge": {
            lv: float(area_a[iou >= lv - IOU_EPS].sum() / total) if total > 0 else float("nan")
            for lv in IOU_LEVELS
        },
        "n_stands_iou_ge": {lv: int((iou >= lv - IOU_EPS).sum()) for lv in IOU_LEVELS},
        "n_no_overlap": int((~matched).sum()),
        "area_no_overlap_ha": float(area_a[~matched].sum() / M2_PER_HA),
        # stands of b that are the best match of two or more stands of a: a sign that stands
        # of a were merged in b (or, read the other way, that a stand of b was split in a)
        "n_shared_best_match": int((counts >= 2).sum()),
    }


def _footprint(geoms: np.ndarray) -> Any:
    return shapely.union_all(geoms) if len(geoms) else shapely.Polygon()


def _type_agreement(
    old: _Stands, new: _Stands, ia: np.ndarray, ib: np.ndarray, inter: np.ndarray
) -> dict[str, Any] | None:
    """Area cross-table of old type against new type over the area both layers cover."""
    told = [old.types[i] for i in ia]
    tnew = [new.types[j] for j in ib]
    both = np.array(
        [a is not None and b is not None for a, b in zip(told, tnew, strict=True)], dtype=bool
    )
    kinds_old = sorted({t for t in old.types if t is not None}, key=_sort_key)
    kinds_new = sorted({t for t in new.types if t is not None}, key=_sort_key)
    if not kinds_old and not kinds_new:
        return None
    table = np.zeros((len(kinds_old), len(kinds_new)))
    for a, b, area, use in zip(told, tnew, inter, both, strict=True):
        if use:
            table[kinds_old.index(a), kinds_new.index(b)] += area
    total = float(table.sum())
    same = sum(
        table[kinds_old.index(t), kinds_new.index(t)] for t in kinds_old if t in kinds_new
    )
    if total > 0:
        rows, cols = linear_sum_assignment(-table)
        best = float(table[rows, cols].sum())
        mapping = {kinds_old[r]: kinds_new[c] for r, c in zip(rows, cols, strict=True)}
    else:
        best, mapping = float("nan"), {}
    return {
        "types_old": kinds_old,
        "types_new": kinds_new,
        "typed_common_area_ha": total / M2_PER_HA,
        "common_area_ha": float(inter.sum() / M2_PER_HA),
        "share_same_number": float(same / total) if total > 0 else float("nan"),
        "share_after_best_renumbering": best / total if total > 0 else float("nan"),
        "best_renumbering": mapping,
        "table_ha": (table / M2_PER_HA).tolist(),
        "untyped_stands_old": sum(t is None for t in old.types),
        "untyped_stands_new": sum(t is None for t in new.types),
        "mixed_type_stands_old": old.mixed_types,
        "mixed_type_stands_new": new.mixed_types,
    }


def compare_layers(old: Layer, new: Layer) -> dict[str, Any]:
    """Compare two stand layers. See the module docstring for what each number means."""
    all_geoms = old.geoms + new.geoms
    if not all_geoms:
        raise ValueError("both layers are empty: there is nothing to compare")
    bounds = shapely.total_bounds(np.array(all_geoms, dtype=object))
    lon0, lat0 = (bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2
    tr = equal_area_transformer(lon0, lat0)
    so, sn = _dissolve(old, tr), _dissolve(new, tr)

    ia, ib, inter = _overlaps(so.geoms, sn.geoms)
    fwd = _direction(so.area_m2, sn.area_m2, ia, ib, inter)
    back = _direction(sn.area_m2, so.area_m2, ib, ia, inter)

    fo, fn = _footprint(so.geoms), _footprint(sn.geoms)
    try:
        common = float(shapely.intersection(fo, fn).area)
    except shapely.errors.GEOSException:
        common = float(shapely.intersection(fo, fn, grid_size=0.001).area)
    either = fo.area + fn.area - common

    new_by_outline: dict[bytes, list[int]] = {}
    for j, key in enumerate(sn.outline):
        new_by_outline.setdefault(key, []).append(j)
    same_idx = [(i, new_by_outline[k]) for i, k in enumerate(so.outline) if k in new_by_outline]
    same_outline = len(same_idx)
    old_outlines = set(so.outline)
    same_outline_new = sum(k in old_outlines for k in sn.outline)
    same_outline_same_id = sum(any(sn.ids[j] == so.ids[i] for j in js) for i, js in same_idx)
    same_outline_same_type = sum(
        any(sn.types[j] == so.types[i] for j in js) for i, js in same_idx
    )
    old_pieces, new_pieces = set(so.piece_outline), set(sn.piece_outline)
    ids_old, ids_new = set(so.ids), set(sn.ids)

    def side(layer: Layer, st: _Stands, foot: Any) -> dict[str, Any]:
        return {
            "name": layer.name,
            "id_field": layer.id_field,
            "n_features": layer.n_features,
            "n_polygons": len(layer.ids),
            "n_skipped": layer.n_skipped,
            "n_repaired": layer.n_repaired,
            "n_stands": len(st.ids),
            "n_multi_piece_stands": int((st.n_pieces > 1).sum()),
            "stand_area_ha": float(st.area_m2.sum() / M2_PER_HA),
            "footprint_ha": float(foot.area / M2_PER_HA),
            "median_stand_ha": float(np.median(st.area_m2) / M2_PER_HA) if len(st.ids) else float("nan"),
            "largest_stand_ha": float(st.area_m2.max() / M2_PER_HA) if len(st.ids) else float("nan"),
        }

    return {
        "projection": {"kind": "Lambert azimuthal equal-area", "lon_0": float(lon0), "lat_0": float(lat0)},
        "grid_deg": GRID_DEG,
        "old": side(old, so, fo),
        "new": side(new, sn, fn),
        "common_footprint_ha": common / M2_PER_HA,
        "footprint_iou": float(common / either) if either > 0 else float("nan"),
        "same_outline_stands": same_outline,
        "same_outline_stands_new": same_outline_new,
        "same_outline_same_id": same_outline_same_id,
        "same_outline_same_type": same_outline_same_type,
        "same_outline_polygons": len(old_pieces & new_pieces),
        "distinct_polygon_outlines_old": len(old_pieces),
        "distinct_polygon_outlines_new": len(new_pieces),
        "ids_in_both": len(ids_old & ids_new),
        "ids_only_old": len(ids_old - ids_new),
        "ids_only_new": len(ids_new - ids_old),
        "old_to_new": fwd,
        "new_to_old": back,
        "types": _type_agreement(so, sn, ia, ib, inter) if (old.type_field or new.type_field) else None,
        "type_field": old.type_field or new.type_field,
        "per_stand": {
            "old": _per_stand_rows("old", so, sn, fwd),
            "new": _per_stand_rows("new", sn, so, back),
        },
    }


def _per_stand_rows(which: str, a: _Stands, b: _Stands, d: dict[str, Any]) -> list[dict[str, Any]]:
    b_outlines = set(b.outline)
    rows = []
    for i, sid in enumerate(a.ids):
        j = int(d["best"][i])
        rows.append({
            "layer": which,
            "stand_id": sid,
            "pieces": int(a.n_pieces[i]),
            "area_ha": round(float(a.area_m2[i]) / M2_PER_HA, 6),
            "type": a.types[i],
            "best_match_id": b.ids[j] if j >= 0 else None,
            "best_match_area_ha": round(float(b.area_m2[j]) / M2_PER_HA, 6) if j >= 0 else None,
            "best_match_type": b.types[j] if j >= 0 else None,
            "overlap_ha": round(float(d["best_overlap_m2"][i]) / M2_PER_HA, 6),
            "iou": round(float(d["iou"][i]), 6),
            "same_outline_in_other_layer": a.outline[i] in b_outlines,
        })
    return rows


def compare_files(
    old_path: Path,
    new_path: Path,
    id_field: str = "stand_lbl",
    new_id_field: str | None = None,
    type_field: str | None = None,
) -> dict[str, Any]:
    """Read two GeoJSON stand layers and compare them."""
    old = read_layer(old_path, id_field, type_field)
    new = read_layer(new_path, new_id_field or id_field, type_field)
    return compare_layers(old, new)


def is_identical(res: dict[str, Any], tol: float = 1e-9) -> bool:
    """True when the two layers hold the same stands: every stand of each has the same outline
    in the other, and every IoU is 1 to within `tol`.

    The number of polygons is not part of it: a stand written as one MultiPolygon feature in
    one file and as two Polygon features with the same id in the other is the same stand."""
    o, n = res["old"], res["new"]
    return bool(
        o["n_stands"] == n["n_stands"] == res["same_outline_stands"] == res["same_outline_stands_new"]
        and o["n_stands"] > 0
        and res["old_to_new"]["min_iou"] >= 1 - tol
        and res["new_to_old"]["min_iou"] >= 1 - tol
    )


# --------------------------------------------------------------------------- report
def _num(x: float, nd: int = 2) -> str:
    if x != x:
        return "n/a"
    return f"{round(x, nd) + 0.0:,.{nd}f}"  # + 0.0 so that a rounded -0.004 prints as 0.00


def format_report(res: dict[str, Any], title: str = "STAND COMPARISON") -> list[str]:
    """The comparison as lines of plain text."""
    o, n, f, b = res["old"], res["new"], res["old_to_new"], res["new_to_old"]
    p = res["projection"]
    out = [
        title,
        f"  old: {o['name']}   (stand id: {o['id_field']})",
        f"  new: {n['name']}   (stand id: {n['id_field']})",
        f"  Areas are in hectares, measured in a {p['kind']} projection centred on the data "
        f"(lat {p['lat_0']:.4f}, lon {p['lon_0']:.4f}).",
        "",
        f"  {'':<38}{'old':>14}{'new':>14}{'new - old':>14}",
    ]

    def row(label: str, a: float, c: float, nd: int = 0, diff: bool = True) -> None:
        d = _num(c - a, nd) if diff and a == a and c == c else ""
        if d and round(c - a, nd) > 0:
            d = "+" + d
        out.append(f"  {label:<38}{_num(a, nd):>14}{_num(c, nd):>14}{d:>14}")

    row("polygons", o["n_polygons"], n["n_polygons"])
    row("stands", o["n_stands"], n["n_stands"])
    row("stands in more than one piece", o["n_multi_piece_stands"], n["n_multi_piece_stands"])
    row("invalid polygons repaired", o["n_repaired"], n["n_repaired"], diff=False)
    row("features left out (no geometry or id)", o["n_skipped"], n["n_skipped"], diff=False)
    row("total stand area", o["stand_area_ha"], n["stand_area_ha"], 2)
    row("area covered (footprint)", o["footprint_ha"], n["footprint_ha"], 2)
    row("median stand area", o["median_stand_ha"], n["median_stand_ha"], 2)
    row("largest stand", o["largest_stand_ha"], n["largest_stand_ha"], 2)
    for s, which in ((o, "old"), (n, "new")):
        gap = s["stand_area_ha"] - s["footprint_ha"]
        if abs(gap) > 1e-4:
            out.append(f"  NOTE: the {which} stands overlap one another by {gap:,.4f} ha "
                       "(total stand area exceeds the area covered).")
    c = res["common_footprint_ha"]
    out += [
        "",
        f"  area covered by both: {_num(c)} ha"
        f" = {_pct(c, o['footprint_ha'])} of the old footprint, {_pct(c, n['footprint_ha'])} of the new;"
        f" footprint IoU {_num(res['footprint_iou'], 6)}",
        f"  covered by the old only: {_num(o['footprint_ha'] - c)} ha;"
        f" by the new only: {_num(n['footprint_ha'] - c)} ha",
        "",
        f"  SAME OUTLINE (after snapping to {res['grid_deg']:g} degrees, about 1 cm)",
        f"    stands:   {res['same_outline_stands']} of {o['n_stands']} old stands have their outline in the new layer"
        f" ({res['same_outline_stands_new']} of {n['n_stands']} new stands have theirs in the old);"
        f" {res['same_outline_same_id']} of them also carry the same id",
        f"    polygons: {res['same_outline_polygons']} outlines in both, of"
        f" {res['distinct_polygon_outlines_old']} old and {res['distinct_polygon_outlines_new']} new",
        f"    stand ids: {res['ids_in_both']} in both, {res['ids_only_old']} only in the old,"
        f" {res['ids_only_new']} only in the new (an id is a label: a re-run may number the same stand differently)",
        "",
        "  INTERSECTION OVER UNION (IoU), each stand against the stand of the other layer that",
        "  overlaps it most; means are weighted by stand area. 1 = the same stands, 0 = no overlap.",
        f"    {'':<44}{'old -> new':>16}{'new -> old':>16}",
    ]

    def two(label: str, x: str, y: str) -> None:
        out.append(f"    {label:<44}{x:>16}{y:>16}")

    two("area-weighted mean IoU", _num(f["area_weighted_iou"], 6), _num(b["area_weighted_iou"], 6))
    two("unweighted mean IoU", _num(f["mean_iou"], 6), _num(b["mean_iou"], 6))
    two("median IoU", _num(f["median_iou"], 6), _num(b["median_iou"], 6))
    two("lowest IoU", _num(f["min_iou"], 6), _num(b["min_iou"], 6))
    for lv in IOU_LEVELS:
        two(f"share of area in stands with IoU >= {lv:g}",
            _share(f["share_area_iou_ge"][lv]), _share(b["share_area_iou_ge"][lv]))
    for lv in IOU_LEVELS:
        two(f"stands with IoU >= {lv:g}",
            f"{f['n_stands_iou_ge'][lv]} of {f['n_stands']}", f"{b['n_stands_iou_ge'][lv]} of {b['n_stands']}")
    two("stands that nothing overlaps", str(f["n_no_overlap"]), str(b["n_no_overlap"]))
    two("  their area (ha)", _num(f["area_no_overlap_ha"]), _num(b["area_no_overlap_ha"]))
    two("stands that are the best match of 2 or more", str(b["n_shared_best_match"]), str(f["n_shared_best_match"]))
    out.append("    (last line: old stands that two or more new stands match best, a sign of splitting;")
    out.append("     new stands that two or more old stands match best, a sign of merging)")

    t = res.get("types")
    if t is not None:
        out += [
            "",
            f"  STAND TYPES ({res['type_field']}), over the area where both layers have a typed stand"
            f" ({_num(t['typed_common_area_ha'])} of {_num(t['common_area_ha'])} ha in common)",
            f"    types in the old layer: {t['types_old']}; in the new: {t['types_new']}",
            f"    stands without a type: {t['untyped_stands_old']} old, {t['untyped_stands_new']} new;"
            f" stands whose pieces carry different types: {t['mixed_type_stands_old']} old,"
            f" {t['mixed_type_stands_new']} new",
            f"    share of that area with the same type number:            {_share(t['share_same_number'])}",
            f"    the same after the best one-to-one renumbering of types: {_share(t['share_after_best_renumbering'])}"
            f"   (old -> new: {t['best_renumbering']})",
            f"    stands with the same outline that also carry the same type number:"
            f" {res['same_outline_same_type']} of {res['same_outline_stands']}",
            "    area in hectares, old type (rows) against new type (columns):",
            "    " + f"{'':>8}" + "".join(f"{str(k):>12}" for k in t["types_new"]),
        ]
        for k, line in zip(t["types_old"], t["table_ha"], strict=True):
            out.append("    " + f"{str(k):>8}" + "".join(f"{v:>12,.2f}" for v in line))
    return out


def _pct(part: float, whole: float) -> str:
    return "n/a" if not whole or whole != whole else f"{100 * part / whole:.4f}%"


def _share(x: float) -> str:
    return "n/a" if x != x else f"{100 * x:.4f}%"


# --------------------------------------------------------------------------- writing
def tracked_files_in(folder: Path) -> list[str]:
    """Files committed to git in `folder` or below it, as paths from the top of the checkout.
    Empty when the folder is not inside a git checkout, when git is not installed, or when
    nothing there is committed.

    Upper and lower case are ignored. On a file system that ignores case, RESULTS/ and
    results/ are the same folder, but neither Path.resolve() nor a plain git pathspec knows
    that, and a check that compared spellings would let a committed file be overwritten
    through a differently spelled path. On a file system that does tell them apart this errs
    on the side of refusing."""
    folder = Path(folder).resolve()
    cwd = folder
    while not cwd.exists() and cwd != cwd.parent:
        cwd = cwd.parent

    def git(*args: str) -> str | None:
        try:
            got = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=False)
        except OSError:
            return None
        return got.stdout if got.returncode == 0 else None

    prefix = git("rev-parse", "--show-prefix")  # the existing part, from the top of the checkout
    if prefix is None:
        return []
    rel = "/".join([*prefix.strip().strip("/").split("/"), *folder.relative_to(cwd).parts]).strip("/")
    # top: from the top of the checkout; icase: ignore case; literal: no wildcard characters
    listed = git("ls-files", "--full-name", "--", f":(top,icase,literal){rel}" if rel else ":(top)")
    return [ln for ln in (listed or "").splitlines() if ln]


def refuse_committed_folder(folder: Path, what: str = "output") -> None:
    """Stop rather than write into a folder that holds committed files: a committed result
    must never be overwritten by a re-run. The caller names a new folder instead."""
    tracked = tracked_files_in(folder)
    if tracked:
        raise SystemExit(
            f"REFUSING to write the {what} into {folder}: it holds {len(tracked)} file(s) committed "
            f"to git (for example {tracked[0]}). Name a new folder."
        )


def write_per_stand_csv(res: dict[str, Any], path: Path) -> None:
    rows = res["per_stand"]["old"] + res["per_stand"]["new"]
    with Path(path).open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]) if rows else ["layer"])
        w.writeheader()
        w.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Measure how much the stands of two runs differ (offline).",
        epilog="See the top of this file for the exact definition of every number.",
    )
    ap.add_argument("old", type=Path, help="the earlier stand layer (GeoJSON, longitude and latitude)")
    ap.add_argument("new", type=Path, help="the later stand layer")
    ap.add_argument("--id-field", default="stand_lbl",
                    help="property holding the stand id (default stand_lbl)")
    ap.add_argument("--new-id-field", default=None,
                    help="the same for the new layer, if it is named differently")
    ap.add_argument("--type-field", default=None,
                    help="property holding the stand type, for example cluster_id (default: types not compared)")
    ap.add_argument("--out", type=Path, default=None, help="also write the table to this file")
    ap.add_argument("--per-stand-csv", type=Path, default=None,
                    help="write one row per stand with its best match and IoU")
    args = ap.parse_args(argv)

    for target in (args.out, args.per_stand_csv):
        if target is not None:
            refuse_committed_folder(Path(target).resolve().parent)
    try:
        res = compare_files(args.old, args.new, args.id_field, args.new_id_field, args.type_field)
    except (OSError, ValueError) as e:
        print(f"could not compare: {e}", file=sys.stderr)
        return 2
    lines = format_report(res)
    print("\n".join(lines))
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text("\n".join(lines) + "\n")
    if args.per_stand_csv is not None:
        args.per_stand_csv.parent.mkdir(parents=True, exist_ok=True)
        write_per_stand_csv(res, args.per_stand_csv)
    return 0


if __name__ == "__main__":
    sys.exit(main())

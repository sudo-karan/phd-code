"""Build an early ui_data/ from the files the 13 Oct re-runs already saved, for the explorer.

    pip install rasterio pillow shapely numpy
    python scripts/build_ui_early_data.py [<outputs dir> [<repo root> [<out dir>]]]

Defaults: outputs/ and ui_data/ of this repo. It reads, for the 14 `_repro` runs of PR #42, the
mask GeoTIFFs and area outlines in outputs/transparency_repro/_mask_data/ and the stand files and
run records in outputs/repro_runs/phase2_vectors/, plus the committed plot tables. It writes the
ui_data/ contract of docs/handoff/2026-10-13-round2.md (task A3, with "Version 2 of the index"),
with three differences from the full export: stands are before the merge fix; feature layers are
stand means, not pixels; the satellite image comes in parts, one per part of the area. Claude
Code's A3 export replaces this folder entirely.

Two encoders here are meant for reuse by that export: `polyline6` (Google's encoded polyline
format at 6 decimals, latitude first) and `superpixel_lines` (each edge between superpixels once,
as encoded lines, so the outlines stay sharp at any zoom). The land-cover mask is written the same
way, as encoded polygons per class (`class_shapes`).
"""
from __future__ import annotations

import csv
import json
import math
import shutil
import sys
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image

from fmu.config import load_config

_ROOT = Path(__file__).resolve().parent.parent
_ARGS = [Path(a) for a in sys.argv[1:4]]
STAGED = _ARGS[0] if len(_ARGS) > 0 else _ROOT / "outputs"
REPO = _ARGS[1] if len(_ARGS) > 1 else _ROOT
OUT = _ARGS[2] if len(_ARGS) > 2 else _ROOT / "ui_data"
MASK = STAGED / "transparency_repro" / "_mask_data"
VEC = STAGED / "repro_runs" / "phase2_vectors"

AREAS = {
    "sanjay_van": {"title": "Sanjay Van", "site": "Sanjay Van", "roi": "rectangle",
                   "mask_from": "sanjay_van_baseline_repro"},
    "angul": {"title": "Angul", "site": "Odisha", "roi": "hulls",
              "mask_from": "odisha_v120_3ha_angul_repro"},
    "dhenkanal": {"title": "Dhenkanal", "site": "Odisha", "roi": "hulls",
                  "mask_from": "odisha_v120_3ha_dhenkanal_repro"},
    "kendujhar": {"title": "Kendujhar", "site": "Odisha", "roi": "hulls",
                  "mask_from": "odisha_v120_3ha_kendujhar_repro"},
    "koraput": {"title": "Koraput", "site": "Odisha", "roi": "hulls",
                "mask_from": "odisha_v120_3ha_koraput_repro"},
}
SANJAY_NOTE = ("Sanjay Van working area: a 1,300 ha rectangle (77.16 to 77.19 E, 28.51 to 28.55 N) "
               "around the park, not the park boundary.")
LABEL = ("Demo set, early build: the Earth Engine re-runs of 13 Oct 2026 (commit df45350), before "
         "the merge fix. Built from the files those runs saved, while Claude Code prepares the full "
         "export. Upstream of the merge it carries the open cache-grid issue (PR #42, question 1). "
         "The final re-run replaces it.")
SHORT_LABEL = ("Test runs from 13 October 2026, before the merge fix. The final runs will "
               "replace them.")

RUNS = []
for area in ("sanjay_van",):
    RUNS += [("sanjay_van_baseline_repro", area, "feature_vector"),
             ("sanjay_van_alphaearth_repro", area, "alphaearth")]
for d in ("angul", "dhenkanal", "kendujhar", "koraput"):
    RUNS += [(f"odisha_v120_3ha_{d}_repro", d, "feature_vector"),
             (f"odisha_v120_handcrafted_{d}_repro", d, "feature_vector"),
             (f"odisha_alphaearth_{d}_repro", d, "alphaearth")]

JOIN_PREFIX = {"odisha_v120_3ha": ("odisha_v120_3ha", "v120_3ha"),
               "odisha_v120_handcrafted": ("odisha_v120_handcrafted", "v120"),
               "odisha_alphaearth": ("odisha_alphaearth", "alphaearth")}

STEP_DECISIONS = {
    "masking": ["dn-masking-indiasat-primary-habitat", "spec-landcover-source-corestack-lulc-v4",
                "dn-masking-majority-vote-recent-year-tie-break",
                "dn-masking-single-phase-no-separate-subtraction", "dn-masking-worldcover-fallback",
                "dn-masking-jrc-water-mask-for-distance-only", "spec-masking-builtup-toggles-removed",
                "night-mask-provenance-layer"],
    "data_load": ["dn-date-windows-one-shared-window", "spec-analysis-grid-utm-from-roi"],
    "features_fv": ["dn-optical-harmonic-regression-derived-bands", "dn-nirv-units-reflectance-0-1",
                    "dn-radar-percentiles-no-harmonic", "dn-radar-vv-minus-vh-in-db",
                    "dn-radar-no-speckle-filter", "dn-structure-eth-canopy-height-input",
                    "sup-eth-canopy-height-stays", "dn-structure-neighbourhood-std-and-max",
                    "dn-static-terrain-bands-from-nasadem",
                    "dn-optical-features-over-whole-roi-mask-at-clustering"],
    "features_ae": ["dn-embedding-arm-controlled-swap", "dn-embedding-stage-source-agnostic",
                    "dn-optical-features-over-whole-roi-mask-at-clustering"],
    "segmentation": ["dn-snic-independent-per-arm", "dn-snic-zscore-per-band",
                     "dn-snic-distance-scale-normalisation", "dn-snic-default-adds-ndvi-amplitude",
                     "dn-snic-canopy-height-std-removed", "dn-snic-compactness-and-bands-not-swept",
                     "spec-snic-reduced-stack-kmeans-full-stack"],
    "merge": ["spec-merge-stage-makes-the-stand", "spec-merge-two-pass-hard-gate",
              "spec-merge-default-criteria", "spec-merge-tolerances-physical-units",
              "spec-merge-hard-area-bounds", "spec-merge-missing-data-rules",
              "dn-merge-criteria-identical-across-arms", "sup-stand-size-3ha",
              "spec-merge-pass2-skip-at-minimum", "field-structural-criterion-unresolved"],
    "clustering": ["spec-kmeans-one-row-per-unit", "dn-median-iqr-scaling-dec-003",
                   "dn-log-transform-skewed-dec-004", "dn-cyclic-sin-cos", "dn-drop-constant-bands",
                   "dn-kmeans-fixed-seed", "field-number-of-types-by-elbow",
                   "field-type-labels-within-district"],
    "fes_plots": ["field-analyses-declared-before-run", "field-all-267-plots",
                  "field-forest-types-from-structure", "field-truth-trees-only",
                  "field-rotation-null-only-null", "field-phase3-primary-analysis-and-checks",
                  "sup-established-methods-first", "sup-new-metrics-await-approval"],
}

# Plain names for the land-cover classes of the mask's "reason" band (masking_transparency.json).
LAND_COVER = {0: ("No land-cover data", "#000000"),
              1: ("Trees or scrub", "#1a9850"),
              2: ("Cropland", "#fdae61"),
              3: ("Built-up", "#d73027"),
              4: ("Water", "#4575b4"),
              5: ("Other land", "#9e9e9e")}
TYPE_COLORS = ["#E69F00", "#56B4E9", "#009E73", "#F0E442", "#0072B2", "#D55E00", "#CC79A7",
               "#999999"]
# Field types of odisha_phase3_0_field_types.csv, described by their typical (median) plot,
# from odisha_script/odisha_phase3_0_results.txt.
FIELD_TYPES = [
    (0, "Type 0: no trees", 18),
    (1, "Type 1: trees ~7 m tall, ~6 per plot", 111),
    (2, "Type 2: trees ~8 m tall, ~14 per plot", 77),
    (3, "Type 3: trees ~15 m tall, ~29 per plot", 15),
    (4, "Type 4: trees ~18 m tall, ~8 per plot", 53),
]
FIELD_COLORS = ["#9e9e9e", "#ffe14d", "#ff9f40", "#e0457b", "#7b2cbf"]
OUTSIDE_REASON = ("Its village has fewer than 5 plots, so no area was mapped around it")
ID_FIELDS = {"area_ha", "centroid_lat", "centroid_lon", "cluster_id", "n_pixels", "perim_m",
             "stand_id", "stand_lbl"}


def r6(x: float) -> float:
    return round(float(x), 6)


def write_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, separators=(",", ":"), ensure_ascii=False))


def bounds_of(src) -> list[float]:
    b = src.bounds
    return [r6(b.left), r6(b.bottom), r6(b.right), r6(b.top)]


def png(path: Path, rgba: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba, "RGBA").save(path, optimize=True)


def parts_of(mask_dir: Path, kind: str) -> list[Path]:
    return sorted(mask_dir.glob(f"part*_{kind}.tif"))


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


# ---------------------------------------------------------------- encoders, for reuse by A3
def _enc(v: int) -> str:
    v = ~(v << 1) if v < 0 else (v << 1)
    out = []
    while v >= 0x20:
        out.append(chr((0x20 | (v & 0x1F)) + 63))
        v >>= 5
    out.append(chr(v + 63))
    return "".join(out)


def polyline6(coords) -> str:
    """Google's encoded polyline at 6 decimals. coords are (lon, lat); output is latitude first."""
    out, plat, plon = [], 0, 0
    for lon, lat in coords:
        ilat, ilon = int(round(lat * 1e6)), int(round(lon * 1e6))
        out.append(_enc(ilat - plat))
        out.append(_enc(ilon - plon))
        plat, plon = ilat, ilon
    return "".join(out)


def superpixel_lines(polygons: list) -> dict:
    """Every edge between superpixels once, merged into chains, as encoded lines."""
    import shapely
    from shapely.ops import linemerge, unary_union

    snapped = [shapely.set_precision(p, 1e-6) for p in polygons]
    net = linemerge(unary_union([p.boundary for p in snapped]))
    lines = list(net.geoms) if hasattr(net, "geoms") else [net]
    return {"encoding": "polyline6", "lines": [polyline6(line.coords) for line in lines]}


def class_shapes(band: np.ndarray, valid: np.ndarray, transform, classes: dict) -> dict:
    """A categorical raster as encoded polygons, grouped by class (rings: outer first)."""
    from rasterio import features as rfeatures

    by_class: dict[int, list] = {}
    for geom, val in rfeatures.shapes(band, mask=valid, transform=transform, connectivity=4):
        v = int(val)
        if v not in classes:
            continue
        by_class.setdefault(v, []).append([polyline6(ring) for ring in geom["coordinates"]])
    return {"encoding": "polyline6",
            "classes": [{"value": v, "polygons": by_class[v]} for v in sorted(by_class)]}


def merge_class_shapes(items: list[dict]) -> dict:
    merged: dict[int, list] = {}
    for it in items:
        for c in it["classes"]:
            merged.setdefault(c["value"], []).extend(c["polygons"])
    return {"encoding": "polyline6",
            "classes": [{"value": v, "polygons": merged[v]} for v in sorted(merged)]}


# ---------------------------------------------------------------- per area (shared by its runs)
def area_layers(area: str) -> dict:
    """Satellite image and land-cover layers for one area (shared by every run on it)."""
    info = AREAS[area]
    mdir = MASK / info["mask_from"]
    tj = json.loads((mdir / "masking_transparency.json").read_text())["transparency"]
    out_dir = OUT / "areas" / area
    # One linear stretch for all three bands, percentiles 1 and 99 of the valid pixels.
    tc = parts_of(mdir, "true_colour")
    vals = []
    for f in tc:
        with rasterio.open(f) as s:
            a = s.read().astype("float32")
            valid = (a > 0).any(axis=0)
            vals.append(a[:, valid].ravel())
    lo, hi = (float(v) for v in np.percentile(np.concatenate(vals), [1, 99]))
    tc_parts = []
    for i, f in enumerate(tc, 1):
        with rasterio.open(f) as s:
            a = s.read().astype("float32")
            b = bounds_of(s)
            valid = (a > 0).any(axis=0)
            rgb = np.clip((a - lo) / (hi - lo) * 255.0, 0, 255).astype("uint8")
            rgba = np.dstack([rgb[0], rgb[1], rgb[2], np.where(valid, 255, 0).astype("uint8")])
            name = f"satellite_part{i:02d}.png"
            png(out_dir / name, rgba)
            tc_parts.append({"file": f"areas/{area}/{name}", "bounds": b})
    shapes = []
    for f in parts_of(mdir, "mask_provenance"):
        with rasterio.open(f) as s:
            reason = s.read(1)
            valid = s.read_masks(1) > 0
            shapes.append(class_shapes(reason, valid, s.transform, LAND_COVER))
    write_json(out_dir / "land_cover.json", merge_class_shapes(shapes))
    roi = json.loads((mdir / "roi_outline.geojson").read_text())
    name_parts(roi, area)
    from shapely.geometry import shape
    from shapely.ops import unary_union

    area_geom = unary_union([shape(f["geometry"]) for f in roi["features"]])
    write_json(out_dir / "area_outline.geojson", roi)
    sn = {s["name"]: s["value"] for s in tj["summary_numbers"]}
    by_reason = sn["share_by_reason"]
    allb = [p["bounds"] for p in tc_parts]
    bbox = [min(b[0] for b in allb), min(b[1] for b in allb), max(b[2] for b in allb),
            max(b[3] for b in allb)]
    facts = {
        "area_ha": round(sn["area_ha"], 1),
        "n_parts": len(roi["features"]),
        "share_kept": round(sn["share_kept"], 4),
        "share_removed": {"cropland": round(by_reason["cropland"], 4),
                          "built_up": round(by_reason["built_up"], 4),
                          "water": round(by_reason["water"], 4),
                          "other": round(by_reason["other_non_habitat"], 4),
                          "no_data": round(by_reason["no_data"], 4)},
        "share_decided_by_worldcover": round(sn["share_decided_by_source"]["worldcover"], 4),
    }
    busiest = max(roi["features"], key=lambda f: f["properties"].get("n_plots", 0))
    return {"bbox": bbox, "tc": tc_parts, "tc_stretch": (lo, hi), "facts": facts,
            "land_cover": f"areas/{area}/land_cover.json", "geom": area_geom,
            "start_bounds": [r6(v) for v in shape(busiest["geometry"]).bounds],
            "roi": f"areas/{area}/area_outline.geojson"}


def name_parts(roi: dict, area: str) -> None:
    """Name each part of the area after the villages whose FES plots fall inside it."""
    from shapely.geometry import Point, shape

    if AREAS[area]["site"] != "Odisha":
        for f in roi["features"]:
            f["properties"]["name"] = AREAS[area]["title"]
            f["properties"]["n_plots"] = 0
        return
    plots = [r for r in read_csv(REPO / "odisha_script" / "odisha_plots_clean.csv")
             if r["district"].lower() == area]
    for f in roi["features"]:
        poly = shape(f["geometry"])
        counts: dict[str, int] = {}
        for r in plots:
            lat, lon = (float(v) for v in r["plot_key"].split("_"))
            if poly.contains(Point(lon, lat)):
                h = r["habitation"].title()
                counts[h] = counts.get(h, 0) + 1
        names = sorted(counts, key=lambda h: (-counts[h], h))
        n = sum(counts.values())
        label = " and ".join(names[:2]) + (f" and {len(names) - 2} more" if len(names) > 2 else "")
        f["properties"]["name"] = (f"{label} ({n} plots)" if names
                                   else f"Part {f['properties'].get('part_index', '')}".strip())
        f["properties"]["n_plots"] = n


def round_coords(c):
    if isinstance(c[0], (int, float)):
        return [r6(c[0]), r6(c[1])]
    out = [round_coords(x) for x in c]
    if out and isinstance(out[0][0], float):  # a ring: drop repeats left by rounding
        dedup = [out[0]]
        for p in out[1:]:
            if p != dedup[-1]:
                dedup.append(p)
        out = dedup
    return out


def pca_rgb(rows: list[list[float]]) -> list[str]:
    x = np.array(rows, dtype="float64")
    x = x - x.mean(axis=0)
    _, _, vt = np.linalg.svd(x, full_matrices=False)
    pcs = x @ vt[:3].T
    cols = []
    lo = np.percentile(pcs, 2, axis=0)
    hi = np.percentile(pcs, 98, axis=0)
    scaled = np.clip((pcs - lo) / np.where(hi > lo, hi - lo, 1), 0, 1)
    for r, g, b in (scaled * 255).astype(int):
        cols.append(f"#{r:02x}{g:02x}{b:02x}")
    return cols


def utm_area_ha(geom) -> float:
    import shapely
    from pyproj import Transformer

    from fmu.utils.grid import utm_epsg_code

    c = geom.centroid
    fwd = Transformer.from_crs(4326, utm_epsg_code(c.x, c.y), always_xy=True).transform
    projected = shapely.transform(geom, lambda xy: np.column_stack(fwd(xy[:, 0], xy[:, 1])))
    return projected.area / 10_000.0


def run_stands(run_id: str, arm: str) -> tuple[dict, dict]:
    g = json.loads((VEC / f"{run_id}_stands_merged.geojson").read_text())
    feats = g["features"]
    n_bands = len([k for k in feats[0]["properties"] if k not in ID_FIELDS])
    emb_cols = None
    if arm == "alphaearth":
        keys = [f"A{i:02d}" for i in range(64)]
        rows = [[f["properties"].get(k) or 0.0 for k in keys] for f in feats]
        emb_cols = pca_rgb(rows)
    keep = {"canopy_height": 1, "canopy_height_std": 2, "ndvi_amplitude_annual": 3,
            "vv_minus_vh_median": 2, "ndvi_mean": 3, "elevation": 0, "slope": 1}
    out = []
    area_by_stand: dict = {}
    for i, f in enumerate(feats):
        p = f["properties"]
        ct = p.get("cluster_id")
        sid = p.get("stand_lbl")
        q = {"stand_id": sid,
             "stand_type": None if ct is None else int(round(float(ct))),
             "area_ha": round(p["area_ha"], 2) if p.get("area_ha") is not None else None}
        for k, nd in keep.items():
            v = p.get(k)
            q[k] = None if v is None or (isinstance(v, float) and math.isnan(v)) else round(v, nd)
        if emb_cols:
            q["emb_rgb"] = emb_cols[i]
        if q["area_ha"] is not None:
            area_by_stand[sid] = area_by_stand.get(sid, 0.0) + q["area_ha"]
        out.append({"type": "Feature", "properties": q,
                    "geometry": {"type": f["geometry"]["type"],
                                 "coordinates": round_coords(f["geometry"]["coordinates"])}})
    fc = {"type": "FeatureCollection", "features": out}
    types = sorted({f["properties"]["stand_type"] for f in out
                    if f["properties"]["stand_type"] is not None})
    areas = sorted(area_by_stand.values())
    untyped = sum(f["properties"]["area_ha"] or 0.0 for f in out
                  if f["properties"]["stand_type"] is None)
    total = sum(area_by_stand.values())
    return fc, {"types": types, "median_area": round(float(np.median(areas)), 2) if areas else None,
                "n_stands": len(area_by_stand), "n_bands": n_bands,
                "n_untyped": len({f["properties"]["stand_id"] for f in out
                                  if f["properties"]["stand_type"] is None}),
                "share_untyped": round(untyped / total, 4) if total else None}


def superpixel_layer(run_id: str) -> tuple[str, float | None]:
    from shapely.geometry import shape

    g = json.loads((VEC / f"{run_id}_stands_snic.geojson").read_text())
    polys = [shape(f["geometry"]) for f in g["features"]]
    name = f"by_run/{run_id}/superpixels.json"
    write_json(OUT / name, superpixel_lines(polys))
    areas = [utm_area_ha(p) for p in polys]
    return name, round(float(np.median(areas)), 2) if areas else None


def plots_for(run_id: str, district: str, area_geom) -> tuple[dict, dict]:
    plots = read_csv(REPO / "odisha_script" / "odisha_plots_clean.csv")
    ftype = {r["plot_key"]: r["field_type"]
             for r in read_csv(REPO / "odisha_script" / "odisha_phase3_0_field_types.csv")}
    ret = {r["plot_key"]: r["habitat"]
           for r in read_csv(REPO / "odisha_script" / "odisha_phase2_1_mask_retention.csv")}
    arm_key = next(k for k in JOIN_PREFIX if run_id.startswith(k + "_"))
    folder, col = JOIN_PREFIX[arm_key]
    join = {r["plot_key"]: r for r in read_csv(
        REPO / "docs" / "reproducibility" / "odisha_repro" / folder
        / "phase2_plots_joined_districts.csv")}
    from shapely.geometry import Point

    feats = []
    n = {"in_district": 0, "inside": 0, "kept": 0, "with_stand": 0}
    for p in plots:
        if p["district"].lower() != district:
            continue
        lat, lon = (float(v) for v in p["plot_key"].split("_"))
        j = join.get(p["plot_key"], {})
        sid = j.get(f"{col}_merged_id") or None
        stype = j.get(f"{col}_merged_cluster") or None
        inside = bool(area_geom.covers(Point(lon, lat)))
        kept = ret.get(p["plot_key"]) == "1"
        n["in_district"] += 1
        n["inside"] += inside
        n["kept"] += kept
        n["with_stand"] += sid is not None
        props = {"plot_key": p["plot_key"], "district": p["district"].title(),
                 "habitation": p["habitation"].title(),
                 "field_type": int(ftype[p["plot_key"]]) if p["plot_key"] in ftype else None,
                 "mask": "kept" if kept else "dropped", "in_mapped_area": inside,
                 "outside_reason": None if inside else OUTSIDE_REASON,
                 "stand_id": int(float(sid)) if sid else None,
                 "stand_type": int(float(stype)) if stype else None}
        feats.append({"type": "Feature", "properties": props,
                      "geometry": {"type": "Point", "coordinates": [r6(lon), r6(lat)]}})
    return {"type": "FeatureCollection", "features": feats}, n


def feature_layers(run_id: str, arm: str, stands_fc: dict) -> list[dict]:
    if arm == "alphaearth":
        return [{
            "layer_id": "embedding_rgb", "title": "AlphaEarth, as colour",
            "kind": "vector", "file": f"by_run/{run_id}/stands.geojson",
            "color_by": "emb_rgb", "color_is_value": True,
            "popup_fields": ["stand_id", "area_ha"], "legend": None, "colormap": None,
            "default_on": False,
            "description": "Each stand is coloured by its average AlphaEarth embedding: the first "
                           "three principal components of the 64 numbers, as red, green and blue. "
                           "Similar colours mean the embedding sees the stands as alike."}]
    layers = []
    for prop, title, pal, units in (
            ("canopy_height", "Canopy height", ["#f7fcf5", "#c7e9c0", "#74c476", "#238b45",
                                                "#00441b"], "m"),
            ("ndvi_amplitude_annual", "Seasonal swing in greenness",
             ["#fff7ec", "#fdd49e", "#fc8d59", "#d7301f", "#7f0000"], "NDVI"),
            ("vv_minus_vh_median", "Radar: VV minus VH",
             ["#f7fbff", "#c6dbef", "#6baed6", "#2171b5", "#08306b"], "dB")):
        vals = [f["properties"][prop] for f in stands_fc["features"]
                if f["properties"].get(prop) is not None]
        if not vals:
            continue
        vmin, vmax = (float(v) for v in np.percentile(vals, [2, 98]))
        layers.append({
            "layer_id": f"feature_{prop}", "title": title,
            "kind": "vector", "file": f"by_run/{run_id}/stands.geojson",
            "color_by": prop, "popup_fields": ["stand_id", prop, "area_ha"], "legend": None,
            "colormap": {"min": round(vmin, 3), "max": round(vmax, 3), "palette": pal,
                         "units": units},
            "default_on": False,
            "description": "Averaged over each stand in this early version."})
    return layers


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    area_cache = {a: area_layers(a) for a in AREAS}
    runs_out = []
    for run_id, area, arm in RUNS:
        cfg = load_config(str(REPO / "configs" / f"{run_id}.yaml"))
        k = cfg.clustering.k
        ceiling = float(cfg.merge.max_area_ha)
        run = json.loads((VEC / f"{run_id}_run.json").read_text())
        md = run["merge_diagnostics"]
        ai = area_cache[area]
        odisha = AREAS[area]["site"] == "Odisha"
        stands_fc, st = run_stands(run_id, arm)
        write_json(OUT / "by_run" / run_id / "stands.geojson", stands_fc)
        sp_file, median_sp = superpixel_layer(run_id)
        seg_bands = [b.band for b in cfg.segmentation.input_bands]
        facts = dict(ai["facts"])
        facts.update({
            "n_feature_bands": 64 if arm == "alphaearth" else st["n_bands"],
            "n_segmentation_bands": 64 if seg_bands == ["*"] else len(seg_bands),
            "segmentation_bands": None if seg_bands == ["*"] else seg_bands,
            "seed_spacing_m": int(cfg.segmentation.size * cfg.export.analysis_scale_m),
            "n_superpixels": md["n_superpixels"], "median_superpixel_ha": median_sp,
            "n_stands": md["n_stands"], "median_stand_ha": st["median_area"],
            "min_stand_ha": float(cfg.merge.min_area_ha), "max_stand_ha": ceiling,
            "merge_criteria": [{"band": c.band, "tolerance": c.tolerance}
                               for c in cfg.merge.criteria],
            "relax_factor": float(cfg.merge.relax_factor),
            "merges_pass1": md.get("pass1_merges"),
            "merges_relaxed": md.get("pass2_merges", 0) - md.get("pass2_fallback_merges", 0),
            "merges_fallback": md.get("pass2_fallback_merges"),
            "stands_below_min": md.get("stands_below_min_area"),
            "below_min_isolated": md.get("orphans_isolated"),
            "below_min_blocked": md.get("orphans_area_blocked"),
            "k": k,
            "n_untyped_stands": st["n_untyped"],
            "share_stand_area_untyped": st["share_untyped"],
        })
        steps = [{
            "step": "masking", "title": "Land cover",
            "decisions": STEP_DECISIONS["masking"],
            "layers": [
                {"layer_id": "habitat_reason", "title": "Land cover", "kind": "shapes",
                 "file": ai["land_cover"],
                 "legend": [{"value": v, "label": lab, "color": col}
                            for v, (lab, col) in LAND_COVER.items()],
                 "colormap": None, "default_on": False},
                {"layer_id": "roi_outline", "title": "Area we mapped", "kind": "vector",
                 "file": ai["roi"], "color_by": None, "popup_fields": [], "style": "outline",
                 "default_on": True},
            ]}, {
            "step": "data_load", "title": "Satellite image",
            "decisions": STEP_DECISIONS["data_load"],
            "layers": [{"layer_id": "true_colour", "title": "Satellite image (Sentinel-2)",
                        "kind": "raster", "parts": ai["tc"], "legend": None, "colormap": None,
                        "smooth": True, "default_on": True}]}, {
            "step": "features", "title": "What we measure",
            "decisions": STEP_DECISIONS["features_fv" if arm == "feature_vector"
                                        else "features_ae"],
            "layers": feature_layers(run_id, arm, stands_fc)}, {
            "step": "segmentation", "title": "Superpixels",
            "decisions": STEP_DECISIONS["segmentation"],
            "layers": [{"layer_id": "superpixels", "title": "Superpixels", "kind": "lines",
                        "encoding": "polyline6", "file": sp_file,
                        "legend": [{"label": "Edge between superpixels", "color": "#ffd400"}],
                        "colormap": None, "default_on": False}]}, {
            "step": "merge", "title": "Stands",
            "decisions": STEP_DECISIONS["merge"],
            "layers": [{"layer_id": "stands", "title": "Stands", "kind": "vector",
                        "file": f"by_run/{run_id}/stands.geojson", "color_by": None,
                        "style": "outline",
                        "popup_fields": ["stand_id", "area_ha", "canopy_height",
                                         "ndvi_amplitude_annual", "stand_type"],
                        "default_on": True}]}, {
            "step": "clustering", "title": "Stand types",
            "decisions": STEP_DECISIONS["clustering"],
            "layers": [{"layer_id": "stand_types", "title": "Stand types", "kind": "vector",
                        "file": f"by_run/{run_id}/stands.geojson", "color_by": "stand_type",
                        "legend": [{"value": int(t), "label": f"Type {t}",
                                    "color": TYPE_COLORS[int(t) % 8]} for t in st["types"]],
                        "popup_fields": ["stand_id", "stand_type", "area_ha"],
                        "default_on": False},
                       {"layer_id": "removed_land", "title": "Land that isn't trees or scrub",
                        "kind": "shapes", "file": ai["land_cover"],
                        "only": [v for v in LAND_COVER if v != 1], "fill": "#3d4540",
                        "legend": None, "colormap": None, "default_on": False,
                        "description": "Cropland, built-up land, water, other land and pixels "
                                       "with no land-cover data, from the land-cover step."}]}]
        if odisha:
            pfc, pn = plots_for(run_id, area, ai["geom"])
            write_json(OUT / "by_run" / run_id / "plots.geojson", pfc)
            facts.update({"plots_in_district": pn["in_district"], "plots_inside": pn["inside"],
                          "plots_on_kept_pixels": pn["kept"], "plots_with_stand": pn["with_stand"]})
            steps.append({
                "step": "fes_plots", "title": "Field check",
                "decisions": STEP_DECISIONS["fes_plots"],
                "layers": [{"layer_id": "plots", "title": "FES plots", "kind": "vector",
                            "file": f"by_run/{run_id}/plots.geojson", "color_by": "field_type",
                            "legend": [{"value": v, "label": lab, "color": FIELD_COLORS[v]}
                                       for v, lab, _ in FIELD_TYPES],
                            "popup_fields": ["plot_key", "habitation", "field_type", "mask",
                                             "in_mapped_area", "outside_reason", "stand_id",
                                             "stand_type"],
                            "default_on": True}]})
        runs_out.append({
            "run_id": run_id, "site": AREAS[area]["site"], "area": AREAS[area]["title"],
            "arm": arm, "stand_ceiling_ha": ceiling, "k": k, "roi": AREAS[area]["roi"],
            "config": f"configs/{run_id}.yaml", "source_commit": "df45350",
            "merge_rule": "before the merge fix", "bounds": ai["bbox"],
            "start_bounds": ai["start_bounds"] if odisha else ai["bbox"],
            "note": SANJAY_NOTE if area == "sanjay_van" else "", "facts": facts,
            "steps": steps})
        print("built", run_id, st["n_stands"], "stands")
    index = {"label": LABEL, "short_label": SHORT_LABEL, "commit": "early build",
             "fes_comparison": "fes_comparison.json", "runs": runs_out}
    write_json(OUT / "index.json", index)
    write_json(OUT / "fes_comparison.json", fes_rows())


def fes_rows() -> dict:
    tests = [
        ("drawing_all_plots", "Plots of the same field type share a stand"),
        ("drawing_multi_plot", "The same, counting only stands that hold two or more plots"),
        ("pair_precision", "Plots that share a stand are the same field type"),
        ("labelling_district", "Plots of the same field type get the same stand type"),
        ("far_apart", "Far-apart plots of the same field type get the same stand type"),
    ]
    committed = {
        10.0: [(0.0121, 93.7, 0.063, 0.630), (0.0257, 77.0, 0.230, 1.0),
               (0.5385, 55.2, 0.451, 1.0), (0.0389, 66.8, 0.332, 1.0),
               (-0.0118, 46.6, 0.534, 1.0)],
        3.0: [(0.0060, 92.1, 0.080, 0.716), (0.0244, 65.7, 0.344, 1.0),
              (0.5575, 71.7, 0.284, 1.0), (0.0793, 83.1, 0.169, 1.0),
              (0.0143, 64.0, 0.360, 1.0)],
    }
    rerun = {10.0: {"drawing_all_plots": 0.0157, "drawing_multi_plot": 0.0364,
                    "labelling_district": 0.0619},
             3.0: {"drawing_all_plots": 0.0057, "drawing_multi_plot": 0.0233,
                   "labelling_district": 0.0478}}
    rows = []
    for ceil, vals in committed.items():
        for (tid, title), (score, pct, p, ph) in zip(tests, vals, strict=True):
            rows.append({"arm": "feature_vector", "stand_ceiling_ha": ceil, "roi": "hulls",
                         "analysis": "primary", "stands": "September 2026 runs (Phase 3)",
                         "test": tid, "title": title, "score": score, "chance_percentile": pct,
                         "p": p, "p_holm": ph, "n_plots": 267})
        for tid, title in tests:
            if tid in rerun[ceil]:
                rows.append({"arm": "feature_vector", "stand_ceiling_ha": ceil, "roi": "hulls",
                             "analysis": "primary", "stands": "13 October 2026 re-runs",
                             "test": tid, "title": title, "score": rerun[ceil][tid],
                             "chance_percentile": None, "p": None, "p_holm": None,
                             "n_plots": 267})
    reading = (
        "At neither stand size can the stands be told apart from a randomly placed copy of the "
        "same stand map, on drawing or on labelling. None of the ten planned tests passes once "
        "corrected for running ten. That does not make the stands wrong: with 267 plots in 20 "
        "villages, a real but modest agreement could go undetected.")
    return {"label": "Phase 3 numbers (September 2026 runs) and the 13 October re-runs' scores. "
                     "Claude Code re-scores the demo set, both arms (brief A4).",
            "reading": reading, "rows": rows}


if __name__ == "__main__":
    main()

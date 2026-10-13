"""Build an early ui_data/ from the files the 13 Oct re-runs already saved, for the explorer.

    pip install rasterio pillow shapely numpy
    python scripts/build_ui_early_data.py [<outputs dir> [<repo root> [<out dir>]]]

Defaults: outputs/ and ui_data/ of this repo. It reads, for the 14 `_repro` runs of PR #42, the
mask GeoTIFFs and ROI outlines in outputs/transparency_repro/_mask_data/ and the stand files and
run records in outputs/repro_runs/phase2_vectors/, plus the committed plot tables. It writes the
ui_data/ contract of docs/handoff/2026-10-13-round2.md (task A3) with three differences from the
full export: stands are before the merge fix; feature layers are stand means, not pixels; rasters
come in parts, one per ROI part. Claude Code's A3 export replaces this folder entirely.
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
from rasterio import features as rfeatures
from rasterio.transform import from_bounds

from fmu.config import load_config

_ROOT = Path(__file__).resolve().parent.parent
_ARGS = [Path(a) for a in sys.argv[1:4]]
STAGED = _ARGS[0] if len(_ARGS) > 0 else _ROOT / "outputs"
REPO = _ARGS[1] if len(_ARGS) > 1 else _ROOT
OUT = _ARGS[2] if len(_ARGS) > 2 else _ROOT / "ui_data"
MASK = STAGED / "transparency_repro" / "_mask_data"
VEC = STAGED / "repro_runs" / "phase2_vectors"

AREAS = {
    "sanjay_van": {"title": "Sanjay Van working area", "site": "Sanjay Van",
                   "mask_from": "sanjay_van_baseline_repro"},
    "angul": {"title": "Angul", "site": "Odisha", "mask_from": "odisha_v120_3ha_angul_repro"},
    "dhenkanal": {"title": "Dhenkanal", "site": "Odisha",
                  "mask_from": "odisha_v120_3ha_dhenkanal_repro"},
    "kendujhar": {"title": "Kendujhar", "site": "Odisha",
                  "mask_from": "odisha_v120_3ha_kendujhar_repro"},
    "koraput": {"title": "Koraput", "site": "Odisha", "mask_from": "odisha_v120_3ha_koraput_repro"},
}
SANJAY_NOTE = ("Sanjay Van working area: a 1,300 ha rectangle (77.16 to 77.19 E, 28.51 to 28.55 N) "
               "around the park, not the park boundary.")
LABEL = ("Demo set, early build: the Earth Engine re-runs of 13 Oct 2026 (commit df45350), before "
         "the merge fix. Built from the files those runs saved, while Claude Code prepares the full "
         "export. Upstream of the merge it carries the open cache-grid issue (PR #42, question 1). "
         "The final re-run replaces it.")

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
              "field-structural-criterion-unresolved"],
    "clustering": ["spec-kmeans-one-row-per-unit", "dn-median-iqr-scaling-dec-003",
                   "dn-log-transform-skewed-dec-004", "dn-cyclic-sin-cos", "dn-drop-constant-bands",
                   "dn-kmeans-fixed-seed", "field-number-of-types-by-elbow",
                   "field-type-labels-within-district"],
    "fes_plots": ["field-analyses-declared-before-run", "field-all-267-plots",
                  "field-forest-types-from-structure", "field-truth-trees-only",
                  "field-rotation-null-only-null", "field-phase3-primary-analysis-and-checks",
                  "sup-established-methods-first", "sup-new-metrics-await-approval"],
}

TYPE_COLORS = ["#E69F00", "#56B4E9", "#009E73", "#F0E442", "#0072B2", "#D55E00", "#CC79A7",
               "#999999"]
FIELD_TYPES = [
    ("0", "Field type 0: no trees or almost none (18 plots)"),
    ("1", "Field type 1: about 7 m, 6 trees (111 plots)"),
    ("2", "Field type 2: about 8 m, 14 trees (77 plots)"),
    ("3", "Field type 3: about 15 m, 29 trees (15 plots)"),
    ("4", "Field type 4: about 18 m, 8 trees (53 plots)"),
]
FIELD_COLORS = ["#8c8c8c", "#a6d96a", "#66bd63", "#1a9850", "#00441b"]
OUTSIDE_REASON = ("From a habitation with fewer than 5 plots, which the Phase 2 mapped area "
                  "leaves out")


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


def hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def parts_of(mask_dir: Path, kind: str) -> list[Path]:
    return sorted(mask_dir.glob(f"part*_{kind}.tif"))


def area_layers(area: str) -> dict:
    """True colour and mask layers for one area (shared by every run on it)."""
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
    allv = np.concatenate(vals)
    lo, hi = (float(v) for v in np.percentile(allv, [1, 99]))
    tc_parts, reason_parts, source_parts = [], [], []
    reason_legend = next(d for d in tj["display_layers"] if d["band"] == "reason")
    source_legend = next(d for d in tj["display_layers"] if d["band"] == "source")
    rpal = {e["value"]: hex_rgb(e["color"]) for e in reason_legend["legend"]}
    spal = {e["value"]: hex_rgb(e["color"]) for e in source_legend["legend"]}
    for i, f in enumerate(tc, 1):
        with rasterio.open(f) as s:
            a = s.read().astype("float32")
            b = bounds_of(s)
            valid = (a > 0).any(axis=0)
            rgb = np.clip((a - lo) / (hi - lo) * 255.0, 0, 255).astype("uint8")
            rgba = np.dstack([rgb[0], rgb[1], rgb[2], np.where(valid, 255, 0).astype("uint8")])
            name = f"true_colour_part{i:02d}.png"
            png(out_dir / name, rgba)
            tc_parts.append({"file": f"areas/{area}/{name}", "bounds": b})
    for i, f in enumerate(parts_of(mdir, "mask_provenance"), 1):
        with rasterio.open(f) as s:
            reason, source = s.read(1), s.read(2)
            b = bounds_of(s)
        for band, pal, bucket, stem in ((reason, rpal, reason_parts, "mask_reason"),
                                        (source, spal, source_parts, "mask_source")):
            rgba = np.zeros(band.shape + (4,), dtype="uint8")
            for v, (r, g, bl) in pal.items():
                sel = band == v
                rgba[sel] = (r, g, bl, 150 if v == 0 else 235)
            name = f"{stem}_part{i:02d}.png"
            png(out_dir / name, rgba)
            bucket.append({"file": f"areas/{area}/{name}", "bounds": b})
    roi = json.loads((mdir / "roi_outline.geojson").read_text())
    name_parts(roi, area)
    write_json(out_dir / "roi_outline.geojson", roi)
    sn = {s["name"]: s for s in tj["summary_numbers"]}
    by_reason = sn["share_by_reason"]["value"]
    summary = {
        "Area of the ROI": f"{sn['area_ha']['value']:,.1f} ha",
        "Kept as habitat": f"{100 * sn['share_kept']['value']:.1f}%",
        "Removed as cropland": f"{100 * by_reason['cropland']:.1f}%",
        "Removed as built-up": f"{100 * by_reason['built_up']:.1f}%",
        "Removed as water": f"{100 * by_reason['water']:.1f}%",
        "Removed as other non-habitat": f"{100 * by_reason['other_non_habitat']:.1f}%",
        "Decided by IndiaSAT": f"{100 * sn['share_decided_by_source']['value']['indiasat']:.0f}%",
    }
    allb = [p["bounds"] for p in tc_parts]
    bbox = [min(b[0] for b in allb), min(b[1] for b in allb), max(b[2] for b in allb),
            max(b[3] for b in allb)]
    return {
        "bbox": bbox, "tc": tc_parts, "tc_stretch": (lo, hi), "reason": reason_parts,
        "source": source_parts, "reason_def": reason_legend, "source_def": source_legend,
        "summary": summary, "roi": f"areas/{area}/roi_outline.geojson",
        "mask_parts": parts_of(mdir, "mask_provenance"),
    }


def name_parts(roi: dict, area: str) -> None:
    """Name each ROI part after the habitations whose FES plots fall inside it."""
    from shapely.geometry import Point, shape

    if AREAS[area]["site"] != "Odisha":
        for f in roi["features"]:
            f["properties"]["name"] = AREAS[area]["title"]
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


def run_stands(run_id: str, arm: str) -> tuple[dict, dict]:
    g = json.loads((VEC / f"{run_id}_stands_merged.geojson").read_text())
    feats = g["features"]
    emb_cols = None
    if arm == "alphaearth":
        keys = [f"A{i:02d}" for i in range(64)]
        rows = [[f["properties"].get(k) or 0.0 for k in keys] for f in feats]
        emb_cols = pca_rgb(rows)
    keep = {"canopy_height": 1, "canopy_height_std": 2, "ndvi_amplitude_annual": 3,
            "vv_minus_vh_median": 2, "ndvi_mean": 3, "elevation": 0, "slope": 1}
    out = []
    for i, f in enumerate(feats):
        p = f["properties"]
        ct = p.get("cluster_id")
        q = {"stand_id": p.get("stand_lbl"),
             "stand_type": None if ct is None else int(round(float(ct))),
             "area_ha": round(p["area_ha"], 2) if p.get("area_ha") is not None else None}
        for k, nd in keep.items():
            v = p.get(k)
            q[k] = None if v is None or (isinstance(v, float) and math.isnan(v)) else round(v, nd)
        if emb_cols:
            q["emb_rgb"] = emb_cols[i]
        out.append({"type": "Feature", "properties": q,
                    "geometry": {"type": f["geometry"]["type"],
                                 "coordinates": round_coords(f["geometry"]["coordinates"])}})
    fc = {"type": "FeatureCollection", "features": out}
    types = sorted({f["properties"]["stand_type"] for f in out
                    if f["properties"]["stand_type"] is not None})
    areas = sorted(f["properties"]["area_ha"] for f in out if f["properties"]["area_ha"])
    n_stands = len({f["properties"]["stand_id"] for f in out})
    return fc, {"types": types, "median_area": areas[len(areas) // 2] if areas else None,
                "n_stands": n_stands}


def superpixel_outlines(run_id: str, area_info: dict) -> list[dict]:
    g = json.loads((VEC / f"{run_id}_stands_snic.geojson").read_text())
    shapes = [(f["geometry"], i + 1) for i, f in enumerate(g["features"])]
    parts = []
    for i, f in enumerate(area_info["mask_parts"], 1):
        with rasterio.open(f) as s:
            w, h = s.width * 2, s.height * 2
            b = s.bounds
        transform = from_bounds(b.left, b.bottom, b.right, b.top, w, h)
        lab = rfeatures.rasterize(shapes, out_shape=(h, w), transform=transform, fill=0,
                                  dtype="int32")
        edge = np.zeros_like(lab, dtype=bool)
        edge[:, :-1] |= lab[:, :-1] != lab[:, 1:]
        edge[:-1, :] |= lab[:-1, :] != lab[1:, :]
        edge &= lab > 0
        rgba = np.zeros((h, w, 4), dtype="uint8")
        rgba[edge] = (255, 212, 0, 255)
        name = f"superpixels_part{i:02d}.png"
        png(OUT / "by_run" / run_id / name, rgba)
        parts.append({"file": f"by_run/{run_id}/{name}",
                      "bounds": [r6(b.left), r6(b.bottom), r6(b.right), r6(b.top)]})
    return parts


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


def plots_for(run_id: str, district: str) -> tuple[dict, dict]:
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
    feats = []
    n = {"in_district": 0, "inside": 0, "kept": 0, "with_stand": 0}
    for p in plots:
        if p["district"].lower() != district:
            continue
        lat, lon = (float(v) for v in p["plot_key"].split("_"))
        j = join.get(p["plot_key"], {})
        sid = j.get(f"{col}_merged_id") or None
        stype = j.get(f"{col}_merged_cluster") or None
        inside = sid is not None
        kept = ret.get(p["plot_key"]) == "1"
        n["in_district"] += 1
        n["inside"] += inside
        n["kept"] += kept
        n["with_stand"] += sid is not None
        props = {"plot_key": p["plot_key"], "habitation": p["habitation"].title(),
                 "field_type": int(ftype[p["plot_key"]]) if p["plot_key"] in ftype else None,
                 "mask": "kept" if kept else "dropped", "in_mapped_area": inside,
                 "outside_reason": None if inside else OUTSIDE_REASON,
                 "stand_id": int(float(sid)) if sid else None,
                 "stand_type": int(float(stype)) if stype else None}
        feats.append({"type": "Feature", "properties": props,
                      "geometry": {"type": "Point", "coordinates": [r6(lon), r6(lat)]}})
    return {"type": "FeatureCollection", "features": feats}, n


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
        stands_fc, st = run_stands(run_id, arm)
        write_json(OUT / "by_run" / run_id / "stands.geojson", stands_fc)
        sp_parts = superpixel_outlines(run_id, ai)
        steps = []
        steps.append({
            "step": "masking", "title": "Land-cover (habitat) mask",
            "decisions": STEP_DECISIONS["masking"], "summary": ai["summary"],
            "layers": [
                {"layer_id": "habitat_reason", "title": "Kept or removed, and why",
                 "kind": "raster", "parts": ai["reason"],
                 "legend": [{"label": e["label"], "color": "#" + e["color"]}
                            for e in ai["reason_def"]["legend"]],
                 "colormap": None, "default_on": False,
                 "description": ai["reason_def"]["description"] + " " +
                 ai["reason_def"].get("legend_note", "")},
                {"layer_id": "habitat_source", "title": "Which map decided each pixel",
                 "kind": "raster", "parts": ai["source"],
                 "legend": [{"label": e["label"], "color": "#" + e["color"]}
                            for e in ai["source_def"]["legend"]],
                 "colormap": None, "default_on": False,
                 "description": ai["source_def"]["description"]},
                {"layer_id": "roi_outline", "title": "Area the pipeline ran on (ROI)",
                 "kind": "vector", "file": ai["roi"], "color_by": None, "popup_fields": [],
                 "style": "outline", "default_on": True},
            ]})
        lo, hi = ai["tc_stretch"]
        steps.append({
            "step": "data_load", "title": "Sentinel-2 composite (true colour)",
            "decisions": STEP_DECISIONS["data_load"],
            "summary": {"Bands shown": "B4, B3, B2 (median composite)",
                        "Stretch": f"{lo:,.0f} to {hi:,.0f} (percentiles 1 and 99)"},
            "layers": [{"layer_id": "true_colour", "title": "True colour", "kind": "raster",
                        "parts": ai["tc"], "legend": None, "colormap": None, "default_on": True}]})
        feat_layers = []
        if arm == "feature_vector":
            for prop, title, pal, units in (
                    ("canopy_height", "Canopy height (ETH 2020)",
                     ["#f7fcf5", "#c7e9c0", "#74c476", "#238b45", "#00441b"], "m"),
                    ("ndvi_amplitude_annual", "NDVI seasonal amplitude",
                     ["#fff7ec", "#fdd49e", "#fc8d59", "#d7301f", "#7f0000"], ""),
                    ("vv_minus_vh_median", "Radar VV minus VH (median)",
                     ["#f7fbff", "#c6dbef", "#6baed6", "#2171b5", "#08306b"], "dB")):
                vals = [f["properties"][prop] for f in stands_fc["features"]
                        if f["properties"].get(prop) is not None]
                if not vals:
                    continue
                vmin, vmax = (float(v) for v in np.percentile(vals, [2, 98]))
                feat_layers.append({
                    "layer_id": f"feature_{prop}", "title": title + ", mean per stand",
                    "kind": "vector", "file": f"by_run/{run_id}/stands.geojson",
                    "color_by": prop, "popup_fields": ["stand_id", prop, "area_ha"],
                    "legend": None,
                    "colormap": {"min": round(vmin, 3), "max": round(vmax, 3), "palette": pal,
                                 "units": units},
                    "default_on": False})
            feat_summary = {"Shown here": "Each band's mean over every stand",
                            "Pixel-level layers": "Coming with Claude Code's export"}
        else:
            feat_layers.append({
                "layer_id": "embedding_rgb",
                "title": "AlphaEarth embedding, first three principal components as colour",
                "kind": "vector", "file": f"by_run/{run_id}/stands.geojson",
                "color_by": "emb_rgb", "color_is_value": True,
                "popup_fields": ["stand_id", "area_ha"], "legend": None, "colormap": None,
                "default_on": False,
                "description": "Stands with similar colours have similar 64-band embeddings. "
                               "The colour axes are the first three principal components of "
                               "the stand means in this run."})
            feat_summary = {"Shown here": "The 64-band embedding, as colour, per stand",
                            "Pixel-level layers": "Coming with Claude Code's export"}
        steps.append({"step": "features", "title": "Features",
                      "decisions": STEP_DECISIONS["features_fv" if arm == "feature_vector"
                                                   else "features_ae"],
                      "summary": feat_summary, "layers": feat_layers})
        steps.append({
            "step": "segmentation", "title": "Superpixels (SNIC)",
            "decisions": STEP_DECISIONS["segmentation"],
            "summary": {"Superpixels": f"{md['n_superpixels']:,}",
                        "Seed spacing": f"{cfg.segmentation.size} pixels"},
            "layers": [{"layer_id": "superpixels", "title": "Superpixel outlines",
                        "kind": "raster", "parts": sp_parts,
                        "legend": [{"label": "Superpixel boundary", "color": "#ffd400"}],
                        "colormap": None, "default_on": False}]})
        merge_summary = {
            "Stands": f"{st['n_stands']:,} from {md['n_superpixels']:,} superpixels",
            "Median stand": f"{st['median_area']:.2f} ha" if st["median_area"] else "n/a",
            "Merges, first pass": f"{md.get('pass1_merges', 0):,}",
            "Merges, relaxed pass": f"{md.get('pass2_merges', 0):,}",
            "of which on shared edge only": f"{md.get('pass2_fallback_merges', 0):,}",
            "Stands below the minimum size": f"{md.get('stands_below_min_area', 0):,}",
            "Size limits": f"{cfg.merge.min_area_ha:g} to {ceiling:g} ha",
        }
        steps.append({
            "step": "merge", "title": "Stands (superpixels merged)",
            "decisions": STEP_DECISIONS["merge"], "summary": merge_summary,
            "layers": [{"layer_id": "stands", "title": "Stand boundaries", "kind": "vector",
                        "file": f"by_run/{run_id}/stands.geojson", "color_by": None,
                        "style": "outline",
                        "popup_fields": ["stand_id", "area_ha", "canopy_height",
                                         "ndvi_amplitude_annual", "stand_type"],
                        "default_on": True}]})
        legend_types = [{"value": int(t), "label": f"Stand type {t}",
                         "color": TYPE_COLORS[int(t) % 8]}
                        for t in st["types"]]
        steps.append({
            "step": "clustering", "title": "Stand types (k-means)",
            "decisions": STEP_DECISIONS["clustering"],
            "summary": {"Types (k)": str(k), "Fitted on": "Every stand, one row each",
                        **({"Type numbers": "Fitted per district, so not comparable across "
                                            "districts"} if AREAS[area]["site"] == "Odisha"
                           else {})},
            "layers": [{"layer_id": "stand_types", "title": "Stands coloured by type",
                        "kind": "vector", "file": f"by_run/{run_id}/stands.geojson",
                        "color_by": "stand_type", "legend": legend_types,
                        "popup_fields": ["stand_id", "stand_type", "area_ha"],
                        "default_on": False}]})
        if AREAS[area]["site"] == "Odisha":
            pfc, pn = plots_for(run_id, area)
            write_json(OUT / "by_run" / run_id / "plots.geojson", pfc)
            steps.append({
                "step": "fes_plots", "title": "FES field plots",
                "decisions": STEP_DECISIONS["fes_plots"],
                "summary": {"Plots in the district": str(pn["in_district"]),
                            "Inside the mapped area": str(pn["inside"]),
                            "On a kept pixel (all plots)": str(pn["kept"]),
                            "In a stand of this run": str(pn["with_stand"])},
                "layers": [{"layer_id": "plots", "title": "Plots, coloured by field type",
                            "kind": "vector", "file": f"by_run/{run_id}/plots.geojson",
                            "color_by": "field_type",
                            "legend": [{"value": int(v), "label": lab, "color": FIELD_COLORS[int(v)]}
                                       for v, lab in FIELD_TYPES],
                            "popup_fields": ["plot_key", "habitation", "field_type", "mask",
                                             "in_mapped_area", "outside_reason", "stand_id",
                                             "stand_type"],
                            "default_on": True}]})
        runs_out.append({
            "run_id": run_id, "site": AREAS[area]["site"], "area": AREAS[area]["title"],
            "arm": arm, "stand_ceiling_ha": ceiling, "k": k,
            "config": f"configs/{run_id}.yaml", "source_commit": "df45350",
            "merge_rule": "before the merge fix", "bounds": ai["bbox"],
            "note": SANJAY_NOTE if area == "sanjay_van" else "", "steps": steps})
        print("built", run_id, st["n_stands"], "stands")
    index = {"label": LABEL, "commit": "fallback", "fes_comparison": "fes_comparison.json",
             "runs": runs_out}
    write_json(OUT / "index.json", index)
    write_json(OUT / "fes_comparison.json", fes_rows())


def fes_rows() -> dict:
    tests = [
        ("drawing_all_plots", "Drawing: plots of the same field type share a stand (all plots)"),
        ("drawing_multi_plot", "Drawing: the same, only stands holding two or more plots"),
        ("pair_precision", "Drawing: same-stand plot pairs that are alike on the ground"),
        ("labelling_district", "Labelling: plots of the same field type get the same stand "
                               "type (within each district)"),
        ("far_apart", "Labelling: far-apart plots that are alike share a type more often"),
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
            rows.append({"arm": "feature_vector", "stand_ceiling_ha": ceil,
                         "analysis": "Committed runs, with the chance test (Phase 3)",
                         "test": tid, "title": title, "score": score, "chance_percentile": pct,
                         "p": p, "p_holm": ph, "n_plots": 267})
        for tid, title in tests:
            if tid in rerun[ceil]:
                rows.append({"arm": "feature_vector", "stand_ceiling_ha": ceil,
                             "analysis": "Re-runs of 13 Oct, score only (chance test pending)",
                             "test": tid, "title": title, "score": rerun[ceil][tid],
                             "chance_percentile": None, "p": None, "p_holm": None,
                             "n_plots": 267})
    reading = (
        "At neither stand size can the stands be shown to group plots that are alike on the "
        "ground better than a randomly placed copy of the same stand map, and at neither size "
        "can the stand types be shown to match the field types better than chance. None of the "
        "ten planned tests survives the correction for running several tests. This says the "
        "stands cannot be told from chance with this field data. It does not say they are "
        "poor: with 20 villages the data could miss a real effect of modest size. AlphaEarth "
        "has not been scored yet; Claude Code scores it, with a declaration written first.")
    return {"label": "Phase 3 numbers (committed runs, Sep 2026) and the re-runs' scores. "
                     "Claude Code re-scores the demo set, both arms (brief A4).",
            "reading": reading, "rows": rows}


if __name__ == "__main__":
    main()

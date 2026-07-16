"""
One-off: run the masking stage, print numeric breakdown, and emit a
JavaScript snippet you can paste into the GEE Code Editor to visualize.

Usage:
    python scripts/inspect_masking.py
    python scripts/inspect_masking.py --config configs/sanjay_van_baseline.yaml
"""

from __future__ import annotations

import argparse

import ee

from fmu.config import load_config
from fmu.pipeline import Pipeline
from fmu.stages.base import PipelineContext
from fmu.stages.masking import MaskingStage  # noqa: F401  # registers the stage
from fmu.utils.gee import init_gee, load_roi_geometry, safe_get_info
from fmu.utils.logging import init_logging


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default="configs/sanjay_van_baseline.yaml",
        help="Path to the pipeline config YAML.",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    init_gee()

    roi = load_roi_geometry(config.roi.roi_file)
    ctx = PipelineContext()
    ctx.set("roi", roi)

    run_dir = init_logging(config_name=config.name)
    result = Pipeline(stage_names=["masking"], use_cache=True).run(
        config=config, run_dir=run_dir, initial_context=ctx
    )

    summary = result.context.get("landcover_summary")
    # Get the actual ROI coordinates from GEE so the JS snippet uses the
    # real geometry (not a buffered centroid).
    roi_coords = safe_get_info(roi.coordinates(), context="roi coordinates for JS")

    # Numeric breakdown
    print()
    print("=" * 70)
    print(f"Numeric breakdown of landcover_summary over {config.roi.name}:")
    print("=" * 70)
    hist = safe_get_info(
        summary.reduceRegion(
            reducer=ee.Reducer.frequencyHistogram(),
            geometry=roi,
            scale=10,
            maxPixels=1e7,
        ),
        context="landcover_summary histogram",
    )
    values = hist.get("landcover_summary", {})
    total = sum(values.values()) or 1
    label_names = {
        "0": "Other (excluded)",
        "6": "Trees (IndiaSAT)",
        "12": "Shrubs/Scrubs (IndiaSAT)",
        "80": "Water (JRC)",
    }
    for code, count in sorted(values.items(), key=lambda kv: -kv[1]):
        name = label_names.get(code, f"Class {code}")
        pct = 100 * count / total
        print(f"  {code:>3} {name:<20s} {count:>10,.0f} px  ({pct:5.1f}%)")

    # JavaScript snippet for the Code Editor
    habitat_classes = config.masking.indiasat_habitat_classes
    habitat_js = ", ".join(str(c) for c in habitat_classes)
    keep = config.masking.keep_worldcover_classes
    keep_js = ", ".join(str(c) for c in keep)
    water_thresh = config.masking.jrc_water_occurrence_threshold
    indiasat_id = config.datasets.indiasat

    import json as _json
    roi_coords_js = _json.dumps(roi_coords)

    # Check what's cached so we emit the right JS.
    from fmu.utils.caching import asset_exists, cached_asset_path
    cached_paths = {}
    for key in ("habitat_mask", "water_mask", "landcover_summary"):
        path = cached_asset_path(config.name, "masking", key)
        if asset_exists(path):
            cached_paths[key] = path

    print()
    print("=" * 70)
    print("VISUALIZE IN GEE CODE EDITOR")
    print("=" * 70)

    if len(cached_paths) == 3:
        # All assets exist; emit JS that reads them directly. No memory
        # error at high zoom because GEE just reads pre-rendered rasters.
        print("All masking outputs are cached as GEE assets. Paste into")
        print("https://code.earthengine.google.com/:")
        print()
        print(f"// --- masking output for {config.name} (from cached assets) ---")
        print(f"var roi = ee.Geometry.Polygon({roi_coords_js});")
        print("Map.centerObject(roi, 13);")
        print()
        print(f"var habitatMask = ee.Image('{cached_paths['habitat_mask']}');")
        print(f"var waterMask = ee.Image('{cached_paths['water_mask']}');")
        print(f"var summary = ee.Image('{cached_paths['landcover_summary']}');")
        print()
        print(
            "Map.addLayer(habitatMask.selfMask(), {palette: ['33aa33']}, "
            "'Habitat mask (green)', true);"
        )
        print(
            "Map.addLayer(waterMask.selfMask(), {palette: ['1f78b4']}, "
            "'Water mask (blue)', true);"
        )
        print(
            "Map.addLayer(summary, "
            "{min: 0, max: 80, palette: "
            "['888888','1d6f1d','85c285','1f78b4']}, "
            "'Landcover summary (0/6/12/80)', true);"
        )
        print(
            "Map.addLayer(roi, {color: 'red', fillColor: '00000000'}, 'ROI boundary');"
        )
        print("// -----------------------------------------------")
    else:
        # Some / all assets missing; assets are being exported in the
        # background. The JS snippet falls back to live computation, which
        # will still hit the memory limit at high zoom, but at least you
        # can see something while exports complete.
        missing = [k for k in ("habitat_mask", "water_mask", "landcover_summary") if k not in cached_paths]
        print(f"Cache miss for: {missing}")
        print(
            "Export tasks for these were submitted (see the log above and "
            "https://code.earthengine.google.com/tasks)."
        )
        print(
            "Once those complete (typically 5-15 minutes for ~13 km²), re-run "
            "this script to get the asset-based JS snippet without the memory issue."
        )
        print()
        print("For now, here's a live-computation snippet that may hit the memory")
        print("limit at high zoom:")
        print()
        print(f"// --- masking output for {config.name} (live, no cache) ---")
        print(f"var roi = ee.Geometry.Polygon({roi_coords_js});")
        print("Map.centerObject(roi, 13);")
        print()
        # LULC_v4 is a FOLDER of per-year images, not an ImageCollection, so
        # list the per-year assets in the configured window and build the
        # collection explicitly. (mode is a viz approximation of the stage's
        # majority-vote habitat logic.)
        from fmu.stages.masking import _hydro_start_year
        _ymin = config.masking.indiasat_year_min
        _ymax = config.masking.indiasat_year_max
        _band = config.masking.indiasat_class_band
        _children = ee.data.listAssets({"parent": indiasat_id}).get("assets", [])
        _year_ids = []
        for _ch in _children:
            if _ch.get("type") not in ("IMAGE", "Image"):
                continue
            _cid = _ch.get("id") or _ch.get("name")
            _yr = _hydro_start_year(_cid)
            if _yr is None:
                continue
            if _ymin is not None and _yr < _ymin:
                continue
            if _ymax is not None and _yr > _ymax:
                continue
            _year_ids.append(_cid)
        _year_ids.sort()
        _sel = f".select('{_band}')" if _band else ".select(0)"
        _imgs_js = ", ".join(f"ee.Image('{cid}'){_sel}" for cid in _year_ids)
        print("// Habitat from CoRE Stack LULC_v4 (per-year images) -> modal class")
        print(f"var lulcYears = [{_imgs_js}];")
        print(
            "var lulc = ee.ImageCollection(lulcYears).reduce(ee.Reducer.mode())"
            ".rename('indiasat_lulc').clip(roi);"
        )
        print(f"var habClasses = [{habitat_js}];")
        print("var vegIndiasat = lulc.eq(habClasses[0]);")
        print("for (var i = 1; i < habClasses.length; i++) {")
        print("  vegIndiasat = vegIndiasat.or(lulc.eq(habClasses[i]));")
        print("}")
        print()
        print("// WorldCover fallback where IndiaSAT has no data")
        print(
            f"var wc = ee.ImageCollection('{config.datasets.worldcover}')"
            ".first().select('Map').clip(roi);"
        )
        print(f"var keepClasses = [{keep_js}];")
        print("var vegWc = wc.eq(keepClasses[0]);")
        print("for (var j = 1; j < keepClasses.length; j++) {")
        print("  vegWc = vegWc.or(wc.eq(keepClasses[j]));")
        print("}")
        print("var habitatMask = vegIndiasat.unmask(vegWc);")
        print()
        print("// JRC water (for distance-to-water feature only, not masking)")
        print(
            f"var gsw = ee.Image('{config.datasets.water}').select('occurrence').clip(roi);"
        )
        print(f"var waterMask = gsw.gte({water_thresh}).unmask(0);")
        print()
        print("var summary = ee.Image(0).int();")
        print(
            "habClasses.forEach(function(c) { summary = summary.where(lulc.eq(c), c); });"
        )
        print("summary = summary.where(waterMask, 80);")
        print()
        print(
            "Map.addLayer(habitatMask.selfMask(), {palette: ['33aa33']}, "
            "'Habitat mask (green)', true);"
        )
        print(
            "Map.addLayer(waterMask.selfMask(), {palette: ['1f78b4']}, "
            "'Water mask (blue)', true);"
        )
        print(
            "Map.addLayer(summary, "
            "{min: 0, max: 80, palette: "
            "['888888','1d6f1d','85c285','1f78b4']}, "
            "'Landcover summary (0/6/12/80)', false);"
        )
        print(
            "Map.addLayer(roi, {color: 'red', fillColor: '00000000'}, 'ROI boundary');"
        )
        print("// -----------------------------------------------")
    print()
    print(f"Run dir: {run_dir}")
    print(f"Manifest: {run_dir / 'manifest.json'}")


if __name__ == "__main__":
    main()

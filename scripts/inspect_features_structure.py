"""Run features_structure end-to-end and emit info / JS for the Code Editor."""

from __future__ import annotations

import argparse
import json

from fmu.config import load_config
from fmu.pipeline import Pipeline
from fmu.stages.base import PipelineContext
from fmu.stages.features_structure import FeaturesStructureStage  # noqa: F401
from fmu.utils.caching import asset_exists, cached_asset_path, config_fingerprint
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
    # Structure only needs roi; no upstream stages required.
    Pipeline(stage_names=["features_structure"], use_cache=True).run(
        config=config, run_dir=run_dir, initial_context=ctx
    )

    features_path = cached_asset_path(
        config.name, "features_structure", "structure_features",
        config_fingerprint(config),
    )
    features_cached = asset_exists(features_path)

    print()
    print("=" * 70)
    print("Structure features summary")
    print("=" * 70)

    if features_cached:
        import ee
        features_img = ee.Image(features_path)
        bands = safe_get_info(features_img.bandNames(), context="structure bands")
        for b in bands:
            stats = safe_get_info(
                features_img.select(b).reduceRegion(
                    reducer=ee.Reducer.mean(), geometry=roi, scale=30, maxPixels=1e7
                ),
                context=f"mean of {b}",
            )
            v = stats.get(b)
            if v is None:
                print(f"  {b:>28s}: <null>")
            else:
                print(f"  {b:>28s}: {v:>10.4f} m")
    else:
        print("  (run again after the export task completes for per-band stats)")

    roi_coords = safe_get_info(roi.coordinates(), context="roi coordinates for JS")
    roi_coords_js = json.dumps(roi_coords)

    print()
    print("=" * 70)
    print("VISUALIZE IN GEE CODE EDITOR")
    print("=" * 70)

    if features_cached:
        print("Structure features cached. Paste into https://code.earthengine.google.com/:")
        print()
        print(f"// --- structure features ({config.name}) ---")
        print(f"var roi = ee.Geometry.Polygon({roi_coords_js});")
        print("Map.centerObject(roi, 13);")
        print()
        print(f"var feats = ee.Image('{features_path}');")
        print()
        # Canopy height; brown (bare) to yellow to green (tall canopy)
        print(
            "Map.addLayer(feats.select('canopy_height'), "
            "{min: 0, max: 25, palette: ['8B4513','D2B48C','9ACD32','228B22','006400']}, "
            "'Canopy height (m)', true);"
        )
        if config.features_structure.include_neighborhood_stats:
            print(
                "Map.addLayer(feats.select('canopy_height_std'), "
                "{min: 0, max: 8, palette: ['000033','3333AA','9999FF','FFFF99','FFCC00']}, "
                "'Canopy height std (local heterogeneity)', false);"
            )
            print(
                "Map.addLayer(feats.select('canopy_height_max'), "
                "{min: 0, max: 30, palette: ['8B4513','D2B48C','9ACD32','228B22','006400']}, "
                "'Canopy height max (local tallest)', false);"
            )
        print(
            "Map.addLayer(roi, {color: 'red', fillColor: '00000000'}, 'ROI boundary');"
        )
        print("// -----------------------------------------------")
    else:
        print(f"Structure features not yet cached (asset path: {features_path})")
        print(
            "Export task was submitted (see log above and "
            "https://code.earthengine.google.com/tasks)."
        )
        print(
            "Re-run this script after the export completes (~3-10 min; "
            "small operation, just reduceNeighborhood)."
        )

    print()
    print(f"Run dir: {run_dir}")
    print(f"Manifest: {run_dir / 'manifest.json'}")


if __name__ == "__main__":
    main()

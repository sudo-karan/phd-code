"""Run masking + features_static and emit info / JS for the Code Editor."""

from __future__ import annotations

import argparse
import json

from fmu.config import load_config
from fmu.pipeline import Pipeline
from fmu.stages.base import PipelineContext
from fmu.stages.features_static import FeaturesStaticStage  # noqa: F401
from fmu.stages.masking import MaskingStage  # noqa: F401
from fmu.utils.caching import asset_exists, cached_asset_path
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
    Pipeline(stage_names=["masking", "features_static"], use_cache=True).run(
        config=config, run_dir=run_dir, initial_context=ctx
    )

    features_path = cached_asset_path(config.name, "features_static", "static_features")
    features_cached = asset_exists(features_path)

    print()
    print("=" * 70)
    print("Static features summary")
    print("=" * 70)

    if features_cached:
        import ee
        features_img = ee.Image(features_path)
        bands = safe_get_info(features_img.bandNames(), context="static bands")
        for b in bands:
            stats = safe_get_info(
                features_img.select(b).reduceRegion(
                    reducer=ee.Reducer.mean(), geometry=roi, scale=30, maxPixels=1e7
                ),
                context=f"mean of {b}",
            )
            v = stats.get(b)
            unit = {
                "elevation": "m",
                "slope": "deg",
                "aspect": "deg",
                "distance_to_water": "m",
                "annual_rainfall": "mm/yr",
            }.get(b, "")
            if v is None:
                print(f"  {b:>28s}: <null>")
            else:
                print(f"  {b:>28s}: {v:>10.4f} {unit}")
    else:
        print("  (run again after the export task completes for per-band stats)")

    roi_coords = safe_get_info(roi.coordinates(), context="roi coordinates for JS")
    roi_coords_js = json.dumps(roi_coords)

    print()
    print("=" * 70)
    print("VISUALIZE IN GEE CODE EDITOR")
    print("=" * 70)

    if features_cached:
        print("Static features cached. Paste into https://code.earthengine.google.com/:")
        print()
        print(f"// --- static features ({config.name}) ---")
        print(f"var roi = ee.Geometry.Polygon({roi_coords_js});")
        print("Map.centerObject(roi, 13);")
        print()
        print(f"var feats = ee.Image('{features_path}');")
        print()
        # Elevation — terrain palette
        print(
            "Map.addLayer(feats.select('elevation'), "
            "{min: 180, max: 280, palette: ['006400','9ACD32','FFFF99','D2B48C','8B4513']}, "
            "'Elevation (m)', true);"
        )
        print(
            "Map.addLayer(feats.select('slope'), "
            "{min: 0, max: 15, palette: ['FFFFFF','F0E68C','FFA500','8B0000']}, "
            "'Slope (deg)', false);"
        )
        # Aspect — cyclic palette (matches phase_annual)
        print(
            "Map.addLayer(feats.select('aspect'), "
            "{min: 0, max: 360, palette: "
            "['FF0000','FF8800','FFFF00','00FF00','0088FF','0000FF','8800FF','FF0088','FF0000']}, "
            "'Aspect (deg, cyclic)', false);"
        )
        # Distance to water
        print(
            "Map.addLayer(feats.select('distance_to_water'), "
            "{min: 0, max: 5000, palette: ['1f78b4','9999FF','FFFF99','D2B48C','8B4513']}, "
            "'Distance to water (m)', false);"
        )
        if config.features_static.include_climate:
            print(
                "Map.addLayer(feats.select('annual_rainfall'), "
                "{min: 400, max: 1000, palette: ['FFFF00','9ACD32','228B22','1f78b4','0000AA']}, "
                "'Annual rainfall (mm/yr, 1991-2020 mean)', false);"
            )
        print(
            "Map.addLayer(roi, {color: 'red', fillColor: '00000000'}, 'ROI boundary');"
        )
        print("// -----------------------------------------------")
    else:
        print(f"Static features not yet cached (asset path: {features_path})")
        print(
            "Export task was submitted (see log above and "
            "https://code.earthengine.google.com/tasks)."
        )
        print(
            "Re-run this script after the export completes (~5-15 min — "
            "distance transform is the slowest part)."
        )

    print()
    print(f"Run dir: {run_dir}")
    print(f"Manifest: {run_dir / 'manifest.json'}")


if __name__ == "__main__":
    main()

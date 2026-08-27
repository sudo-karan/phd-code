"""
Run the pipeline through features_radar and emit info / JS to view the
radar features in the GEE Code Editor.

Stages run: masking to data_load to features_radar, with caching on.
"""

from __future__ import annotations

import argparse
import json

from fmu.config import load_config
from fmu.pipeline import Pipeline
from fmu.stages.base import PipelineContext
from fmu.stages.data_load import DataLoadStage  # noqa: F401  # registers stage
from fmu.stages.features_radar import FeaturesRadarStage  # noqa: F401
from fmu.stages.masking import MaskingStage  # noqa: F401
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
    Pipeline(
        stage_names=["masking", "data_load", "features_radar"], use_cache=True
    ).run(config=config, run_dir=run_dir, initial_context=ctx)

    features_path = cached_asset_path(
        config.name, "features_radar", "radar_features", config_fingerprint(config)
    )
    features_cached = asset_exists(features_path)

    print()
    print("=" * 70)
    print("Radar features summary")
    print("=" * 70)

    if features_cached:
        import ee
        features_img = ee.Image(features_path)
        bands = safe_get_info(features_img.bandNames(), context="radar bands")
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
                print(f"  {b:>28s}: {v:>10.4f} dB")
    else:
        print("  (run again after the export task completes for per-band stats)")

    roi_coords = safe_get_info(roi.coordinates(), context="roi coordinates for JS")
    roi_coords_js = json.dumps(roi_coords)

    print()
    print("=" * 70)
    print("VISUALIZE IN GEE CODE EDITOR")
    print("=" * 70)

    if features_cached:
        print("Radar features cached. Paste into https://code.earthengine.google.com/:")
        print()
        print(f"// --- radar features ({config.name}) ---")
        print(f"var roi = ee.Geometry.Polygon({roi_coords_js});")
        print("Map.centerObject(roi, 13);")
        print()
        print(f"var feats = ee.Image('{features_path}');")
        print()
        # VV median; grayscale, dB range
        print(
            "Map.addLayer(feats.select('vv_p50'), "
            "{min: -25, max: -5, palette: ['000000','555555','AAAAAA','FFFFFF']}, "
            "'VV median (dB)', true);"
        )
        # VH median; grayscale, lower dB range (cross-pol is weaker)
        print(
            "Map.addLayer(feats.select('vh_p50'), "
            "{min: -30, max: -10, palette: ['000000','555555','AAAAAA','FFFFFF']}, "
            "'VH median (dB)', false);"
        )
        # Cross-pol contrast; vegetation has VV-VH ~5-10 dB; urban can be higher
        print(
            "Map.addLayer(feats.select('vv_minus_vh_median'), "
            "{min: 0, max: 15, palette: ['000044','3366CC','99CCFF','FFFF99','FFCC00','CC3300']}, "
            "'VV-VH median (cross-pol contrast)', false);"
        )
        # VV IQR; variability (dark=stable, bright=variable)
        print(
            "Map.addLayer(feats.select('vv_iqr'), "
            "{min: 0, max: 8, palette: ['000033','3333AA','9999FF','FFFF99','FFCC00']}, "
            "'VV IQR (variability)', false);"
        )
        # VH IQR
        print(
            "Map.addLayer(feats.select('vh_iqr'), "
            "{min: 0, max: 8, palette: ['000033','3333AA','9999FF','FFFF99','FFCC00']}, "
            "'VH IQR (variability)', false);"
        )
        # VV p10 (low end; surface roughness floor)
        print(
            "Map.addLayer(feats.select('vv_p10'), "
            "{min: -28, max: -8, palette: ['000000','555555','AAAAAA','FFFFFF']}, "
            "'VV p10 (low end)', false);"
        )
        # VV p90 (high end)
        print(
            "Map.addLayer(feats.select('vv_p90'), "
            "{min: -20, max: 0, palette: ['000000','555555','AAAAAA','FFFFFF']}, "
            "'VV p90 (high end)', false);"
        )
        print(
            "Map.addLayer(roi, {color: 'red', fillColor: '00000000'}, 'ROI boundary');"
        )
        print("// -----------------------------------------------")
    else:
        print(f"Radar features not yet cached (asset path: {features_path})")
        print(
            "Export task was submitted (see log above and "
            "https://code.earthengine.google.com/tasks)."
        )
        print(
            "Re-run this script after the export completes (~5-15 min) "
            "to get the asset-based JS snippet."
        )

    print()
    print(f"Run dir: {run_dir}")
    print(f"Manifest: {run_dir / 'manifest.json'}")


if __name__ == "__main__":
    main()

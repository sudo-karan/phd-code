"""
Run the full pipeline through features_optical and emit info / JS to view
the resulting phenology features in the GEE Code Editor.

Stages run: masking to data_load to features_optical, with caching on.
First run kicks off export tasks for cacheable outputs; second run uses
the cached assets.
"""

from __future__ import annotations

import argparse
import json

from fmu.config import load_config
from fmu.pipeline import Pipeline
from fmu.stages.base import PipelineContext
from fmu.stages.data_load import DataLoadStage  # noqa: F401  # registers stage
from fmu.stages.features_optical import FeaturesOpticalStage  # noqa: F401
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
        stage_names=["masking", "data_load", "features_optical"], use_cache=True
    ).run(config=config, run_dir=run_dir, initial_context=ctx)

    prefix = config.features_optical.index  # "ndvi" or "nirv"

    # Numeric summary; per-band statistics over the ROI
    features_path = cached_asset_path(
        config.name, "features_optical", "optical_features", config_fingerprint(config)
    )
    features_cached = asset_exists(features_path)

    print()
    print("=" * 70)
    print(f"Optical features summary ({prefix.upper()}, "
          f"{config.features_optical.harmonic_mode} harmonic"
          f"{', + trend' if config.features_optical.include_trend else ''})")
    print("=" * 70)

    if features_cached:
        import ee
        features_img = ee.Image(features_path)
        bands = safe_get_info(features_img.bandNames(), context="features bands")
        for b in bands:
            stats = safe_get_info(
                features_img.select(b).reduceRegion(
                    reducer=ee.Reducer.mean(), geometry=roi, scale=30, maxPixels=1e7
                ),
                context=f"mean of {b}",
            )
            v = stats.get(b)
            if v is None:
                print(f"  {b:>32s}: <null>")
            elif isinstance(v, (int, float)):
                print(f"  {b:>32s}: {v:>10.4f}")
            else:
                print(f"  {b:>32s}: {v}")
    else:
        print("  (run again after the export task completes for per-band stats)")

    # JS snippet for visualization
    roi_coords = safe_get_info(roi.coordinates(), context="roi coordinates for JS")
    roi_coords_js = json.dumps(roi_coords)

    print()
    print("=" * 70)
    print("VISUALIZE IN GEE CODE EDITOR")
    print("=" * 70)

    if features_cached:
        print("Optical features cached. Paste into https://code.earthengine.google.com/:")
        print()
        print(f"// --- optical features ({config.name}) ---")
        print(f"var roi = ee.Geometry.Polygon({roi_coords_js});")
        print("Map.centerObject(roi, 13);")
        print()
        print(f"var feats = ee.Image('{features_path}');")
        print()

        # Both NDVI and NIRv live in [0, 1] (NIRv is NDVI × NIR_reflectance,
        # both in 0-1). One palette set works for either.

        # Mean; color ramp brown to yellow to green (low to high vegetation)
        print(
            f"Map.addLayer(feats.select('{prefix}_mean'), "
            "{min: -0.1, max: 0.8, palette: ['8B4513','EDC9AF','F0E68C','9ACD32','228B22']}, "
            f"'Mean ({prefix.upper()})', true);"
        )
        # Amplitude; color ramp dark to bright (low to high seasonality)
        print(
            f"Map.addLayer(feats.select('{prefix}_amplitude_annual'), "
            "{min: 0, max: 0.3, palette: ['000033','3333AA','9999FF','FFFF99','FFCC00']}, "
            "'Amplitude annual', false);"
        )
        # Phase; cyclic palette (red to yellow to green to blue to red)
        print(
            f"Map.addLayer(feats.select('{prefix}_phase_annual'), "
            "{min: -3.14, max: 3.14, palette: "
            "['FF0000','FF8800','FFFF00','00FF00','0088FF','0000FF','8800FF','FF0088','FF0000']}, "
            "'Phase annual (timing of peak)', false);"
        )
        if config.features_optical.harmonic_mode == "dual":
            print(
                f"Map.addLayer(feats.select('{prefix}_amplitude_semi'), "
                "{min: 0, max: 0.2, palette: ['000033','3333AA','9999FF','FFFF99','FFCC00']}, "
                "'Amplitude semi-annual', false);"
            )
        if config.features_optical.include_trend:
            print(
                f"Map.addLayer(feats.select('{prefix}_trend'), "
                "{min: -0.02, max: 0.02, palette: ['8B0000','FF6666','FFFFFF','66CC66','006400']}, "
                "'Trend (per-year change)', false);"
            )
        # Residual variance; high values = poorly-fit pixels
        print(
            f"Map.addLayer(feats.select('{prefix}_residual_variance'), "
            "{min: 0, max: 0.3, palette: ['FFFFFF','FFCCCC','FF6666','990000']}, "
            "'Residual variance (poor harmonic fit)', false);"
        )
        # Obs count; confidence / data density
        print(
            f"Map.addLayer(feats.select('{prefix}_obs_count'), "
            "{min: 50, max: 300, palette: ['000044','3366CC','99CCFF','FFFFCC']}, "
            "'Obs count (per-pixel data density)', false);"
        )
        print(
            "Map.addLayer(roi, {color: 'red', fillColor: '00000000'}, 'ROI boundary');"
        )
        print("// -----------------------------------------------")
    else:
        print(f"Optical features not yet cached (asset path: {features_path})")
        print(
            "Export task was submitted (see log above and "
            "https://code.earthengine.google.com/tasks)."
        )
        print(
            "Re-run this script after the export completes (10-30 min; this is the "
            "biggest export so far) to get the asset-based JS snippet."
        )

    print()
    print(f"Run dir: {run_dir}")
    print(f"Manifest: {run_dir / 'manifest.json'}")


if __name__ == "__main__":
    main()

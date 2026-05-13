"""
One-off: run the data_load stage and emit info / JS for the Code Editor.

Like inspect_masking.py: prints what the stage produced and a JS snippet
to view the s2_composite asset in the Code Editor once it's cached.
"""

from __future__ import annotations

import argparse

from fmu.config import load_config
from fmu.pipeline import Pipeline
from fmu.stages.base import PipelineContext
from fmu.stages.data_load import DataLoadStage  # noqa: F401 — registers the stage
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
    result = Pipeline(stage_names=["data_load"], use_cache=True).run(
        config=config, run_dir=run_dir, initial_context=ctx
    )

    s2_coll = result.context.get("s2_collection")
    s1_coll = result.context.get("s1_collection")
    composite = result.context.get("s2_composite")

    roi_coords = safe_get_info(roi.coordinates(), context="roi coordinates for JS")

    print()
    print("=" * 70)
    print(f"Data load summary for {config.roi.name}:")
    print("=" * 70)
    n_s2 = safe_get_info(s2_coll.size(), context="s2_collection size")
    n_s1 = safe_get_info(s1_coll.size(), context="s1_collection size")
    bands = safe_get_info(composite.bandNames(), context="composite bands")
    print(f"  S2 phenology images:     {n_s2:>6,d}  "
          f"({config.dates.phenology.start} → {config.dates.phenology.end})")
    print(f"  S1 radar images:         {n_s1:>6,d}  "
          f"({config.dates.radar.start} → {config.dates.radar.end}, "
          f"{config.data_load.s1_orbit})")
    print(f"  S2 composite reducer:    {config.data_load.s2_composite_reducer}  "
          f"({config.dates.optical_composite.start} → "
          f"{config.dates.optical_composite.end})")
    print(f"  Composite bands ({len(bands)}):   {', '.join(bands[:6])}"
          f"{'...' if len(bands) > 6 else ''}")

    # JS snippet
    composite_path = cached_asset_path(config.name, "data_load", "s2_composite")
    composite_cached = asset_exists(composite_path)

    import json as _json
    roi_coords_js = _json.dumps(roi_coords)

    print()
    print("=" * 70)
    print("VISUALIZE IN GEE CODE EDITOR")
    print("=" * 70)
    if composite_cached:
        print("S2 composite cached. Paste into https://code.earthengine.google.com/:")
        print()
        print(f"// --- s2 composite for {config.name} (from cached asset) ---")
        print(f"var roi = ee.Geometry.Polygon({roi_coords_js});")
        print("Map.centerObject(roi, 13);")
        print()
        print(f"var composite = ee.Image('{composite_path}');")
        print()
        # True color: B4/B3/B2 → red/green/blue. Reducer suffix is in band names.
        reducer = config.data_load.s2_composite_reducer
        if reducer == "median":
            suffix = "_median"
        elif reducer == "p25":
            suffix = "_p25"
        elif reducer == "p50":
            suffix = "_p50"
        else:
            suffix = "_p75"
        print(
            f"Map.addLayer(composite.select(['B4{suffix}','B3{suffix}','B2{suffix}']), "
            "{min: 0, max: 3000}, 'S2 composite (true color)', true);"
        )
        print(
            f"Map.addLayer(composite.select(['B8{suffix}','B4{suffix}','B3{suffix}']), "
            "{min: 0, max: 3000}, 'S2 composite (false color, NIR-R-G)', false);"
        )
        print(
            "Map.addLayer(roi, {color: 'red', fillColor: '00000000'}, 'ROI boundary');"
        )
        print("// -----------------------------------------------")
    else:
        print(f"S2 composite not yet cached (asset path: {composite_path})")
        print(
            "An export task was submitted (see log above and "
            "https://code.earthengine.google.com/tasks)."
        )
        print(
            "Re-run this script after the export completes (5-15 min) to get the "
            "asset-based JS snippet."
        )

    print()
    print(f"Run dir: {run_dir}")
    print(f"Manifest: {run_dir / 'manifest.json'}")


if __name__ == "__main__":
    main()

"""Run the pipeline through clustering and emit info / JS to view the
k-means cluster labels in the GEE Code Editor.

This is the longest pipeline run yet — all 8 stages upstream of (and
including) clustering, with caching. First run will trigger exports for
any stage that hasn't been cached yet.
"""

from __future__ import annotations

import argparse
import json as json_mod

from fmu.config import load_config
from fmu.pipeline import Pipeline
from fmu.stages.base import PipelineContext
from fmu.stages.clustering import ClusteringStage  # noqa: F401
from fmu.stages.data_load import DataLoadStage  # noqa: F401
from fmu.stages.features_optical import FeaturesOpticalStage  # noqa: F401
from fmu.stages.features_radar import FeaturesRadarStage  # noqa: F401
from fmu.stages.features_static import FeaturesStaticStage  # noqa: F401
from fmu.stages.features_structure import FeaturesStructureStage  # noqa: F401
from fmu.stages.masking import MaskingStage  # noqa: F401
from fmu.stages.segmentation import SegmentationStage  # noqa: F401
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
    Pipeline(
        stage_names=[
            "masking",
            "data_load",
            "features_optical",
            "features_radar",
            "features_structure",
            "features_static",
            "segmentation",
            "clustering",
        ],
        use_cache=True,
    ).run(config=config, run_dir=run_dir, initial_context=ctx)

    labels_path = cached_asset_path(config.name, "clustering", "cluster_labels")
    stack_path = cached_asset_path(config.name, "clustering", "feature_stack")
    labels_cached = asset_exists(labels_path)
    stack_cached = asset_exists(stack_path)

    print()
    print("=" * 70)
    print(f"Clustering summary — k={config.clustering.k}")
    print("=" * 70)

    if labels_cached:
        import ee

        labels_img = ee.Image(labels_path)

        # Per-cluster pixel count gives us composition: which clusters dominate?
        counts = safe_get_info(
            labels_img.reduceRegion(
                reducer=ee.Reducer.frequencyHistogram(),
                geometry=roi,
                scale=config.export.analysis_scale_m,
                maxPixels=1e9,
                bestEffort=True,
            ),
            context="cluster frequency histogram",
        )
        hist = counts.get("cluster_id") or {}
        total = sum(hist.values()) or 1
        print("  cluster_id  pixel count    % of habitat")
        for cid in sorted(hist.keys(), key=int):
            n = hist[cid]
            pct = 100.0 * n / total
            print(f"  {cid:>10}  {int(n):>11d}  {pct:>10.1f}%")

        # Pull and pretty-print the clustering_metadata JSON
        raw_meta = safe_get_info(
            labels_img.get("clustering_metadata"),
            context="clustering_metadata property",
        )
        if raw_meta:
            meta = json_mod.loads(raw_meta)
            print()
            print("Clustering metadata (cached on the asset):")
            print(f"  normalization_method: {meta['normalization_method']}")
            print(f"  active_bands ({len(meta['active_bands'])}):")
            for b in meta["active_bands"]:
                print(f"      {b}")
            if meta["log_transformed_bands"]:
                print(f"  log-transformed: {meta['log_transformed_bands']}")
            if meta["dropped_constant_bands"]:
                print(f"  dropped (constant): {meta['dropped_constant_bands']}")
    else:
        print("  (run again after export task completes for cluster stats)")

    roi_coords = safe_get_info(roi.coordinates(), context="roi coordinates for JS")
    roi_coords_js = json_mod.dumps(roi_coords)

    print()
    print("=" * 70)
    print("VISUALIZE IN GEE CODE EDITOR")
    print("=" * 70)

    if labels_cached:
        print("Cluster labels cached. Paste into https://code.earthengine.google.com/:")
        print()
        print(f"// --- clustering ({config.name}) ---")
        print(f"var roi = ee.Geometry.Polygon({roi_coords_js});")
        print("Map.centerObject(roi, 13);")
        print()
        print(f"var labels = ee.Image('{labels_path}');")
        if stack_cached:
            print(f"var featStack = ee.Image('{stack_path}');")
            print()
        # Discrete palette — one color per cluster (works for k up to ~12).
        # Colors chosen to be ecologically suggestive but distinct.
        palette = [
            "1f78b4",  # 0: dark blue
            "33a02c",  # 1: green
            "e31a1c",  # 2: red
            "ff7f00",  # 3: orange
            "6a3d9a",  # 4: purple
            "b15928",  # 5: brown
            "ffff99",  # 6: pale yellow
            "a6cee3",  # 7: light blue
            "b2df8a",  # 8: light green
            "fb9a99",  # 9: pink
            "fdbf6f",  # 10: peach
            "cab2d6",  # 11: lavender
        ][: config.clustering.k]
        palette_js = json_mod.dumps(palette)
        print(
            f"Map.addLayer(labels, "
            f"{{min: 0, max: {config.clustering.k - 1}, palette: {palette_js}}}, "
            "'Cluster labels', true);"
        )
        # Boundaries between clusters help see the spatial organization
        print(
            "Map.addLayer(labels.focal_mode(1).neq(labels).selfMask(), "
            "{palette: ['000000']}, 'Cluster boundaries', false);"
        )
        print(
            "Map.addLayer(roi, {color: 'red', fillColor: '00000000'}, 'ROI boundary');"
        )
        print("// -----------------------------------------------")
    else:
        print(f"Cluster labels not yet cached: {labels_path}")
        print("Export task submitted. Re-run after it completes.")

    print()
    print(f"Run dir: {run_dir}")
    print(f"Manifest: {run_dir / 'manifest.json'}")


if __name__ == "__main__":
    main()

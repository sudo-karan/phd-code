"""Run the pipeline through segmentation and emit info / JS to view the
SNIC superpixels in the GEE Code Editor."""

from __future__ import annotations

import argparse
import json

from fmu.config import load_config
from fmu.pipeline import Pipeline, segmentation_stage_names
from fmu.stages.base import PipelineContext
from fmu.stages.data_load import DataLoadStage  # noqa: F401
from fmu.stages.features_embedding import FeaturesEmbeddingStage  # noqa: F401
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
    # Derived, not hardcoded: which feature stages SNIC needs depends on
    # `segmentation.input_bands`, so an embedding arm runs a different set.
    Pipeline(
        stage_names=segmentation_stage_names(config),
        use_cache=True,
    ).run(config=config, run_dir=run_dir, initial_context=ctx)

    clusters_path = cached_asset_path(config.name, "segmentation", "snic_clusters")
    means_path = cached_asset_path(config.name, "segmentation", "snic_means")
    clusters_cached = asset_exists(clusters_path)
    means_cached = asset_exists(means_path)

    print()
    print("=" * 70)
    print("SNIC segmentation summary")
    print("=" * 70)

    if clusters_cached:
        import ee
        clusters_img = ee.Image(clusters_path)
        # SNIC numbers clusters with a spatial hash, not 0..N. The proper way to
        # count distinct superpixels is countDistinct (more expensive than max,
        # but actually meaningful).
        count_stats = safe_get_info(
            clusters_img.reduceRegion(
                reducer=ee.Reducer.countDistinct(),
                geometry=roi,
                scale=config.export.analysis_scale_m,
                maxPixels=1e9,
                bestEffort=True,
            ),
            context="distinct cluster count",
        )
        n_clusters = count_stats.get("snic_clusters")
        print(f"  distinct superpixels in ROI: {n_clusters}")
    else:
        print("  (run again after export task completes for cluster-count stats)")

    roi_coords = safe_get_info(roi.coordinates(), context="roi coordinates for JS")
    roi_coords_js = json.dumps(roi_coords)

    print()
    print("=" * 70)
    print("VISUALIZE IN GEE CODE EDITOR")
    print("=" * 70)

    if clusters_cached and means_cached:
        print("SNIC outputs cached. Paste into https://code.earthengine.google.com/:")
        print()
        print(f"// --- SNIC segmentation ({config.name}) ---")
        print(f"var roi = ee.Geometry.Polygon({roi_coords_js});")
        print("Map.centerObject(roi, 13);")
        print()
        print(f"var clusters = ee.Image('{clusters_path}');")
        print(f"var means = ee.Image('{means_path}');")
        print()
        # Random-color visualization of cluster IDs; each superpixel gets a unique hue.
        print("// Random-color visualization (each cluster gets a different hue)")
        print(
            "Map.addLayer(clusters.randomVisualizer(), {}, 'Superpixels (random colors)', true);"
        )
        # Boundaries as a vector overlay derived from the labeled image
        print("// Superpixel boundaries (vector overlay)")
        print(
            "var boundaries = clusters.zeroCrossing();"
        )
        print(
            "Map.addLayer(boundaries.updateMask(boundaries), "
            "{palette: ['000000']}, 'Boundaries', false);"
        )
        # Per-cluster means; useful for sanity-checking that superpixels are
        # sensible. Which bands exist depends on `segmentation.input_bands`, so
        # read them from config instead of naming them here -- an embedding arm
        # has no `canopy_height` band at all. min/max are left to stretch()
        # since an embedding dimension has no meaningful fixed range.
        print("// Per-cluster means of the configured SNIC input bands")
        for band in [b.band for b in config.segmentation.input_bands][:3]:
            if band == "*":
                print(
                    "// (source declared as '*': band names resolve at run time; "
                    "use means.bandNames().getInfo() to list them)"
                )
                print(
                    "Map.addLayer(means.select(0), {}, "
                    "'Per-superpixel band 0', false);"
                )
                continue
            print(
                f"Map.addLayer(means.select('{band}'), "
                f"{{palette: ['8B4513','D2B48C','9ACD32','228B22','006400']}}, "
                f"'Per-superpixel {band}', false);"
            )
        print(
            "Map.addLayer(roi, {color: 'red', fillColor: '00000000'}, 'ROI boundary');"
        )
        print("// -----------------------------------------------")
    else:
        print(f"Clusters not yet cached (asset path: {clusters_path})")
        print(f"Means not yet cached (asset path: {means_path})")
        print(
            "Export tasks submitted (see log above and "
            "https://code.earthengine.google.com/tasks)."
        )
        print(
            "Re-run this script after exports complete (~10-30 min; "
            "SNIC is a heavy operation on a 5-band 10m-resolution ROI)."
        )

    print()
    print(f"Run dir: {run_dir}")
    print(f"Manifest: {run_dir / 'manifest.json'}")


if __name__ == "__main__":
    main()

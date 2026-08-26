"""Run the pipeline through metrics and print the actual research deliverable.

For the variant config, this runs the comparison against the baseline and
prints ARI, NMI, silhouette, the cluster correspondence, and the confusion
matrix. Also saves the metrics as JSON in the run dir and emits Code Editor
JS to visualize the agreement map.
"""

from __future__ import annotations

import argparse
import json

from fmu.config import load_config
from fmu.pipeline import Pipeline, default_stage_names
from fmu.stages.base import PipelineContext
from fmu.stages.clustering import ClusteringStage  # noqa: F401
from fmu.stages.data_load import DataLoadStage  # noqa: F401
from fmu.stages.features_embedding import FeaturesEmbeddingStage  # noqa: F401
from fmu.stages.features_optical import FeaturesOpticalStage  # noqa: F401
from fmu.stages.features_radar import FeaturesRadarStage  # noqa: F401
from fmu.stages.features_static import FeaturesStaticStage  # noqa: F401
from fmu.stages.features_structure import FeaturesStructureStage  # noqa: F401
from fmu.stages.masking import MaskingStage  # noqa: F401
from fmu.stages.metrics import MetricsStage  # noqa: F401
from fmu.stages.segmentation import SegmentationStage  # noqa: F401
from fmu.utils.gee import init_gee, load_roi_geometry, safe_get_info
from fmu.utils.logging import init_logging


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default="configs/sanjay_van_nirv_dual.yaml",
        help="Path to the pipeline config YAML.",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    init_gee()

    roi = load_roi_geometry(config.roi.roi_file)
    ctx = PipelineContext()
    ctx.set("roi", roi)

    run_dir = init_logging(config_name=config.name)
    # Stage list depends on clustering.feature_source (handcrafted vs embedding);
    # default_stage_names picks the right one and keeps SNIC fixed across arms.
    Pipeline(
        stage_names=default_stage_names(config),
        use_cache=True,
    ).run(config=config, run_dir=run_dir, initial_context=ctx)

    # Pull the metrics back from the manifest
    manifest_path = run_dir / "manifest.json"
    with manifest_path.open() as f:
        manifest = json.load(f)
    metrics_stage = next(
        (s for s in manifest["stages"] if s["name"] == "metrics"), None
    )
    if metrics_stage is None or "metrics" not in metrics_stage.get("metadata", {}):
        print("Metrics not found in manifest.")
        return
    metrics = metrics_stage["metadata"]["metrics"]

    # Save standalone metrics JSON
    metrics_path = run_dir / f"metrics_{config.name}.json"
    with metrics_path.open("w") as f:
        json.dump(metrics, f, indent=2, sort_keys=True, default=str)

    # --- Print the table ---
    print()
    print("=" * 78)
    print(f"Clustering metrics; {config.name}")
    print("=" * 78)
    print(f"  current_config:       {metrics['current_config']}")
    if metrics.get("reference_config"):
        print(f"  reference_config:     {metrics['reference_config']}")
        print(f"  n_samples_used:       {metrics['n_samples_used']}")
        print()
        print(f"  ARI:                  {metrics['ari']:.4f}    "
              "(adjusted Rand index; 0=random agreement, 1=identical partitions)")
        print(f"  NMI:                  {metrics['nmi']:.4f}    "
              "(normalized mutual info; 0=independent, 1=fully predictable)")
        print(
            f"  Agreement rate:       {100 * metrics['agreement_rate']:.2f}%  "
            "(% pixels matching after cluster correspondence)"
        )
        print()
        print(f"  silhouette (current):   {metrics.get('silhouette_current', 'N/A'):.4f}")
        if "silhouette_reference" in metrics:
            print(
                f"  silhouette (reference): "
                f"{metrics['silhouette_reference']:.4f}"
            )

        print()
        print("  Cluster correspondence (current to reference):")
        for cur, ref in sorted(metrics["correspondence"].items(), key=lambda x: int(x[0])):
            print(f"    {config.name} cluster {cur}  to  {metrics['reference_config']} cluster {ref}")

        print()
        print("  Confusion matrix (rows=current, cols=reference):")
        cm = metrics["confusion_matrix"]
        # Header
        print("        " + "  ".join(f"ref-{j:>3d}" for j in range(len(cm))))
        for i, row in enumerate(cm):
            print(f"  cur-{i:>2d}  " + "  ".join(f"{val:>6,}" for val in row))
    else:
        print(f"  silhouette (current):   {metrics.get('silhouette_current', 'N/A'):.4f}")
        print()
        print("  No reference config set; only intrinsic metrics computed.")

    # --- Emit Code Editor JS for the agreement map ---
    if metrics.get("reference_config"):
        print()
        print("=" * 78)
        print("VISUALIZE AGREEMENT IN GEE CODE EDITOR")
        print("=" * 78)

        roi_coords = safe_get_info(roi.coordinates(), context="roi coords")
        roi_coords_js = json.dumps(roi_coords)

        # Re-derive the agreement map server-side from the cached labels
        # since we're emitting JS for the Code Editor.
        from fmu.utils.caching import cached_asset_path

        current_path = cached_asset_path(config.name, "clustering", "cluster_labels")
        reference_path = cached_asset_path(
            metrics["reference_config"], "clustering", "cluster_labels"
        )
        snic_path = cached_asset_path(config.name, "segmentation", "snic_clusters")
        max_size = config.max_component_pixels()
        # Build the remap arrays
        correspondence = metrics["correspondence"]
        # JSON keys are strings; convert to int for ordering
        from_values = sorted(correspondence.keys(), key=int)
        to_values = [correspondence[k] for k in from_values]
        from_values_int = [int(k) for k in from_values]

        print()
        print(f"// --- metrics comparison: {config.name} vs {metrics['reference_config']} ---")
        print(f"var roi = ee.Geometry.Polygon({roi_coords_js});")
        print("Map.centerObject(roi, 13);")
        print()
        print(f"var current   = ee.Image('{current_path}');")
        print(f"var reference = ee.Image('{reference_path}');")
        print()
        print(f"// Cluster correspondence; {config.name} to {metrics['reference_config']}")
        print(f"var fromValues = {from_values_int};")
        print(f"var toValues   = {to_values};")
        print()
        print("var remappedCurrent = current.remap(fromValues, toValues);")
        print("var agreement = remappedCurrent.eq(reference).rename('agrees');")
        print()
        # Discrete palette: red = disagree, green = agree
        print("Map.addLayer(agreement,")
        print("  {min: 0, max: 1, palette: ['e31a1c', '33a02c']},")
        print(f"  'Agreement map ({100 * metrics['agreement_rate']:.1f}%%)', true);")
        # Per-stand confidence = agreement rolled up to SNIC superpixels.
        print()
        print("// Per-stand confidence: fraction of each SNIC stand's pixels that agree.")
        print(f"var snic = ee.Image('{snic_path}');")
        print("var confidence = agreement.addBands(snic.rename('snic_label'))")
        print(f"  .reduceConnectedComponents(ee.Reducer.mean(), 'snic_label', {max_size})")
        print("  .select(['agrees'], ['confidence']);")
        print("Map.addLayer(confidence,")
        print("  {min: 0, max: 1, palette: ['e31a1c', 'ffff99', '33a02c']},")
        print("  'Per-stand confidence (red=low, green=high)', true);")
        # Also show both maps for context
        print()
        print("var clusterPalette = ['1f78b4','33a02c','e31a1c','ff7f00','6a3d9a','b15928'];")
        print("Map.addLayer(reference, {min:0, max:5, palette: clusterPalette}, "
              f"'Reference: {metrics['reference_config']}', false);")
        print("Map.addLayer(current, {min:0, max:5, palette: clusterPalette}, "
              f"'Current: {config.name}', false);")
        print("Map.addLayer(roi, {color: 'white', fillColor: '00000000'}, 'ROI');")
        print("// -----------------------------------------------")

    print()
    print(f"Full metrics: {metrics_path}")
    print(f"Pipeline manifest: {manifest_path}")


if __name__ == "__main__":
    main()

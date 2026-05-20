"""Run the pipeline through export and save a standalone export manifest
JSON file in the run directory."""

from __future__ import annotations

import argparse
import json

from fmu.config import load_config
from fmu.pipeline import Pipeline
from fmu.stages.base import PipelineContext
from fmu.stages.clustering import ClusteringStage  # noqa: F401
from fmu.stages.data_load import DataLoadStage  # noqa: F401
from fmu.stages.export import ExportStage  # noqa: F401
from fmu.stages.features_optical import FeaturesOpticalStage  # noqa: F401
from fmu.stages.features_radar import FeaturesRadarStage  # noqa: F401
from fmu.stages.features_static import FeaturesStaticStage  # noqa: F401
from fmu.stages.features_structure import FeaturesStructureStage  # noqa: F401
from fmu.stages.masking import MaskingStage  # noqa: F401
from fmu.stages.profiling import ProfilingStage  # noqa: F401
from fmu.stages.segmentation import SegmentationStage  # noqa: F401
from fmu.utils.gee import init_gee, load_roi_geometry
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
            "profiling",
            "export",
        ],
        use_cache=True,
    ).run(config=config, run_dir=run_dir, initial_context=ctx)

    # Read the manifest back from the pipeline manifest
    manifest_path = run_dir / "manifest.json"
    with manifest_path.open() as f:
        pipeline_manifest = json.load(f)
    export_stage = next(
        (s for s in pipeline_manifest["stages"] if s["name"] == "export"),
        None,
    )
    if export_stage is None or "manifest" not in export_stage.get("metadata", {}):
        print("Export manifest not found in pipeline manifest.")
        return

    export_manifest = export_stage["metadata"]["manifest"]

    # Save the export manifest as a standalone file in the run dir
    standalone_path = run_dir / f"export_manifest_{config.name}.json"
    with standalone_path.open("w") as f:
        json.dump(export_manifest, f, indent=2, sort_keys=True, default=str)

    # Print a human-readable summary
    print()
    print("=" * 70)
    print(f"Export summary; {config.name}")
    print("=" * 70)
    print(f"  pipeline version: {export_manifest['pipeline_version']}")
    print(f"  run timestamp:    {export_manifest['run_timestamp']}")
    print(f"  ROI area:         {export_manifest['roi'].get('area_km2', '?')} km²")
    print()

    print(f"Cluster distribution (k={len(export_manifest['clustering']['cluster_distribution'])}):")
    for c in export_manifest["clustering"]["cluster_distribution"]:
        print(
            f"  cluster {c['cluster_id']}: {c['pixel_count']:>7,} px  "
            f"{c['area_ha']:>7.1f} ha  ({c['percent_of_habitat']:>5.1f}%)"
        )
    print()

    print(f"Cached assets ({len(export_manifest['asset_paths'])}):")
    for key, path in sorted(export_manifest["asset_paths"].items()):
        print(f"  {key:25s} {path}")
    print()

    drive = export_manifest["drive_export"]
    if drive.get("task_submitted"):
        print("Drive export submitted:")
        print(f"  task_id:  {drive['task_id']}")
        print(f"  folder:   '{drive['folder']}' in your Google Drive")
        print(f"  filename: {drive['filename']}")
        print(
            "  Monitor at https://code.earthengine.google.com/tasks "
            "(5-15 min typically)."
        )
    else:
        print("Drive export was not submitted (live test mode?).")
    print()

    print(f"Decisions source: {export_manifest['decisions_source']}")
    print()

    print(f"Full manifest:  {standalone_path}")
    print(f"Pipeline log:   {run_dir / 'manifest.json'}")


if __name__ == "__main__":
    main()

"""Run the pipeline through profiling and print per-cluster feature stats.

Saves the full profile table as CSV and JSON in the run directory for
downstream analysis (e.g., loading into pandas for visualization).
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

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
from fmu.stages.merge import MergeStage  # noqa: F401
from fmu.stages.profiling import ProfilingStage  # noqa: F401
from fmu.stages.segmentation import SegmentationStage  # noqa: F401
from fmu.utils.gee import init_gee, load_roi_geometry
from fmu.utils.logging import init_logging

# A short list of ecologically interesting features to show in the
# terminal preview. The full table is saved to CSV.
_PREVIEW_BANDS = [
    ("ndvi_mean", "NDVI"),
    ("nirv_mean", "NIRv"),
    ("canopy_height", "Canopy(m)"),
    ("vv_p50", "VV_med(dB)"),
    ("vh_p50", "VH_med(dB)"),
    ("vv_minus_vh_median", "VV-VH(dB)"),
    ("elevation", "Elev(m)"),
    ("distance_to_water", "Dist_H2O"),
]


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
    # Feature stages depend on clustering.feature_source (handcrafted vs embedding).
    Pipeline(
        stage_names=default_stage_names(config, through="profiling"),
        use_cache=True,
    ).run(config=config, run_dir=run_dir, initial_context=ctx)

    # Pull the profiles back from the manifest
    manifest_path = run_dir / "manifest.json"
    with manifest_path.open() as f:
        manifest = json.load(f)
    profiling_stage = next(
        (s for s in manifest["stages"] if s["name"] == "profiling"),
        None,
    )
    if profiling_stage is None or "profiles" not in profiling_stage.get("metadata", {}):
        print("Profiles not found in manifest; check the log above.")
        return
    profiles = profiling_stage["metadata"]["profiles"]

    # ---- Print preview to terminal (just the highlighted bands as means) ----
    print()
    print("=" * 90)
    print(f"Cluster profiles; {config.name} (k={config.clustering.k})")
    print("=" * 90)

    if not profiles:
        print("(no profiles)")
        return

    # Pick whichever preview bands are present in this config's profile
    all_keys = set(profiles[0].keys())
    present_preview = [
        (band, label)
        for band, label in _PREVIEW_BANDS
        if f"{band}_mean" in all_keys or band in all_keys
    ]

    # Header
    header_cols = ["Cluster", "Pixels", "Area(ha)"] + [
        label for _, label in present_preview
    ]
    print(_format_row(header_cols, widths=[8, 8, 10] + [10] * len(present_preview)))
    print("-" * 90)

    for profile in profiles:
        row = [
            str(profile["cluster_id"]),
            f"{profile['pixel_count']:,}",
            f"{profile['area_ha']:.1f}",
        ]
        for band, _ in present_preview:
            # GEE reducer puts mean under "{band}_mean"
            key = f"{band}_mean"
            val = profile.get(key)
            if val is None:
                row.append("-")
            else:
                row.append(_fmt_value(val))
        print(_format_row(row, widths=[8, 8, 10] + [10] * len(present_preview)))

    # ---- Save full table to CSV ----
    csv_path = run_dir / "cluster_profiles.csv"
    _write_profiles_csv(profiles, csv_path)
    print()
    print(f"Full profile table (all {len(all_keys)} columns): {csv_path}")
    print(f"JSON profiles (in manifest): {manifest_path}")
    print()
    print(f"Run dir: {run_dir}")


def _format_row(values: list[str], *, widths: list[int]) -> str:
    return "  ".join(v.rjust(w)[:w] for v, w in zip(values, widths, strict=False))


def _fmt_value(v: float) -> str:
    if abs(v) >= 100:
        return f"{v:.0f}"
    if abs(v) >= 10:
        return f"{v:.1f}"
    if abs(v) >= 1:
        return f"{v:.2f}"
    return f"{v:.3f}"


def _write_profiles_csv(profiles: list[dict], path: Path) -> None:
    if not profiles:
        return
    # Collect all keys across all profiles (in case some bands are missing
    # for individual clusters; shouldn't happen but be robust)
    all_keys: list[str] = []
    seen: set[str] = set()
    for p in profiles:
        for k in p:
            if k not in seen:
                seen.add(k)
                all_keys.append(k)

    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=all_keys)
        writer.writeheader()
        for p in profiles:
            writer.writerow(p)


if __name__ == "__main__":
    main()

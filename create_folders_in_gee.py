"""Create the GEE asset folder hierarchy for one or more configs.

The pipeline's caching layer writes assets to:

    {asset_root}/{config_name}/{stage_name}/{output_key}

GEE requires parent folders to exist before assets can be written to them.
This script provisions the hierarchy:

    {asset_root}
    {asset_root}/{config_name}
    {asset_root}/{config_name}/{stage_name}    (one per stage with cacheable outputs)

Idempotent — re-running on a partially-provisioned tree is safe; existing
folders are skipped silently.

Usage:
    python scripts/create_folders_in_gee.py                       # default configs
    python scripts/create_folders_in_gee.py my_config other_cfg   # custom
"""

from __future__ import annotations

import argparse
import sys

import ee

# Pre-import every stage module so the registry is populated when we walk it.
import fmu.stages.clustering  # noqa: F401
import fmu.stages.data_load  # noqa: F401
import fmu.stages.export  # noqa: F401
import fmu.stages.features_optical  # noqa: F401
import fmu.stages.features_radar  # noqa: F401
import fmu.stages.features_static  # noqa: F401
import fmu.stages.features_structure  # noqa: F401
import fmu.stages.masking  # noqa: F401
import fmu.stages.metrics  # noqa: F401
import fmu.stages.profiling  # noqa: F401
import fmu.stages.segmentation  # noqa: F401
from fmu.pipeline import Pipeline
from fmu.settings import get_settings
from fmu.stages.base import get_stage_class, list_registered_stages
from fmu.utils.gee import init_gee

# Default configs to provision. Add yours here if you regularly run others.
DEFAULT_CONFIGS = ["sanjay_van_baseline", "sanjay_van_nirv_dual"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "configs",
        nargs="*",
        default=DEFAULT_CONFIGS,
        help=(
            "Config names to provision folders for. "
            f"Defaults to {DEFAULT_CONFIGS}. "
            "Each name maps to a top-level folder under the asset root."
        ),
    )
    args = parser.parse_args()

    # Initialize GEE using the project from .env / Settings — NOT hardcoded.
    init_gee()
    asset_root = get_settings().resolved_asset_root()
    print(f"Asset root: {asset_root}")
    print(f"Configs to provision: {', '.join(args.configs)}")

    # Discover every stage that produces cacheable outputs. Stages that opt
    # out (cacheable_outputs=set()) get an empty set and contribute no
    # folders — same logic the orchestrator and export inventory use.
    stages_with_cache = []
    for stage_name in list_registered_stages():
        stage = get_stage_class(stage_name)()
        cacheable = Pipeline._resolve_cacheable_outputs(stage)
        if cacheable:
            stages_with_cache.append(stage_name)
    print(f"Stages with cacheable outputs: {', '.join(sorted(stages_with_cache))}")
    print()

    # Build the full list of folders to create, in parent-first order so
    # GEE's create-folder call can find each parent.
    folders: list[str] = [asset_root]
    for config_name in args.configs:
        folders.append(f"{asset_root}/{config_name}")
        for stage_name in stages_with_cache:
            folders.append(f"{asset_root}/{config_name}/{stage_name}")

    created = 0
    existed = 0
    failed = 0
    for folder in folders:
        status = _create_folder_idempotent(folder)
        if status == "created":
            created += 1
        elif status == "exists":
            existed += 1
        else:
            failed += 1

    print()
    print(f"Done. Created: {created}  Already-existed: {existed}  Failed: {failed}")
    return 0 if failed == 0 else 1


def _create_folder_idempotent(path: str) -> str:
    """Create a GEE folder if it doesn't exist. Returns one of:
       "created" / "exists" / "failed".
    """
    try:
        ee.data.createAsset({"type": "FOLDER"}, path)
        print(f"  created: {path}")
        return "created"
    except ee.EEException as e:
        msg = str(e).lower()
        if "already exists" in msg or "cannot overwrite" in msg:
            print(f"  exists:  {path}")
            return "exists"
        print(f"  FAILED:  {path}  ({e})", file=sys.stderr)
        return "failed"


if __name__ == "__main__":
    sys.exit(main())

"""
Invalidate stale cached GEE assets for one or more configs.

The masking logic changed (ee-indiasat -> corestack-trees), but cache keys are
(config, stage, output_key) with no content hash, so pre-existing assets are
served on a hit and the new logic never runs. This deletes every cached asset
under a config's fmu folder so the next pipeline run recomputes from scratch.
Folder structure is left intact (create_folders_in_gee.py already made it).

Dry-run by default. Pass --delete to actually remove.

    .venv/bin/python rebuild_cache.py                       # dry-run, both configs
    .venv/bin/python rebuild_cache.py --delete              # delete, both configs
    .venv/bin/python rebuild_cache.py --delete sanjay_van_baseline
"""

from __future__ import annotations

import argparse
import os

os.chdir("/Users/karan/Desktop/phd-code")

import ee  # noqa: E402

from fmu.settings import get_settings  # noqa: E402
from fmu.utils.gee import init_gee  # noqa: E402

DEFAULT_CONFIGS = ["sanjay_van_baseline", "sanjay_van_nirv_dual"]


def list_assets_recursive(parent: str) -> list[tuple[str, str]]:
    """Return (asset_id, type) for every non-folder asset under parent."""
    found: list[tuple[str, str]] = []
    try:
        res = ee.data.listAssets({"parent": parent})
    except Exception as e:  # noqa: BLE001
        print(f"  (list failed under {parent}: {str(e).splitlines()[0]})")
        return found
    for a in res.get("assets", []):
        aid = a.get("name") or a.get("id")
        atype = a.get("type")
        if atype in ("FOLDER", "IMAGE_COLLECTION"):
            found.extend(list_assets_recursive(aid))
        else:
            found.append((aid, atype))
    return found


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("configs", nargs="*", default=DEFAULT_CONFIGS)
    ap.add_argument("--delete", action="store_true", help="actually delete (default: dry-run)")
    args = ap.parse_args()
    configs = args.configs or DEFAULT_CONFIGS

    init_gee()
    root = get_settings().resolved_asset_root()
    print(f"Asset root: {root}")
    print(f"Configs   : {', '.join(configs)}")
    print(f"Mode      : {'DELETE' if args.delete else 'DRY-RUN (nothing removed)'}")
    print()

    total = 0
    for cfg in configs:
        parent = f"{root}/{cfg}"
        assets = list_assets_recursive(parent)
        print(f"[{cfg}] {len(assets)} cached assets:")
        for aid, atype in assets:
            short = aid.replace(root + "/", "")
            if args.delete:
                try:
                    ee.data.deleteAsset(aid)
                    print(f"  deleted  {atype:6s} {short}")
                except Exception as e:  # noqa: BLE001
                    print(f"  FAILED   {atype:6s} {short}: {str(e).splitlines()[0]}")
            else:
                print(f"  would rm {atype:6s} {short}")
            total += 1
        print()

    print(f"{'Deleted' if args.delete else 'Would delete'} {total} assets.")
    if not args.delete:
        print("Re-run with --delete to actually remove them, then rebuild the pipeline.")


if __name__ == "__main__":
    main()

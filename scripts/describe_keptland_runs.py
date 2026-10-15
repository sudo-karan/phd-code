"""Plain descriptive numbers for the kept-land runs, from their committed files. Offline.

    python scripts/describe_keptland_runs.py [<run_id> ...]

For each run (default: every run with a run record in docs/reproducibility/keptland_runs/), from
docs/reproducibility/keptland_runs/<run>_run.json and <run>_manifest_export.json:
  - stands: how many, the smallest and the largest (ha), how many have no pixel in the merge's
    count and so 0 ha (superpixels on the ROI edge, of pixels the ROI covers only in part), and
    the smallest of the rest;
  - stands over merge.max_area_ha, and by how much each (merge.pass2_soft_ceiling lets a stand
    below the minimum join over it, up to max_area_ha + min_area_ha);
  - stands below merge.min_area_ha after the merge, by cause, and the stands of those left out of
    the k-means fit (clustering.fit_excludes_stands_below_min_area) with their area;
  - how the superpixels cover kept land (merge_diagnostics["kept_land"]).
Numbers only: no score, and no comparison with field data.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
RUNS_DIR = REPO / "docs" / "reproducibility" / "keptland_runs"


def describe(run: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    """The numbers of one run, from its run record and its export-pass manifest. Pure Python."""
    md = run["merge_diagnostics"]
    attrs = run["stand_attributes"].values()
    areas = sorted(float(a["area_ha"]) for a in attrs)
    with_pixels = sorted(float(a["area_ha"]) for a in attrs if a.get("n_pixels"))
    config = manifest["config"]
    ceiling, minimum = float(config["merge"]["max_area_ha"]), float(config["merge"]["min_area_ha"])
    over = sorted((a - ceiling for a in areas if a > ceiling), reverse=True)
    stages = {s["name"]: s for s in manifest["stages"]}
    clustering = stages["export"]["metadata"]["manifest"]["clustering"]
    kept = md.get("kept_land") or {}
    return {
        "stands": len(areas),
        "stands_in_merge_diagnostics": md.get("n_stands"),
        "superpixels": md.get("n_superpixels"),
        "smallest_stand_ha": round(areas[0], 4) if areas else None,
        "largest_stand_ha": round(areas[-1], 4) if areas else None,
        "stands_with_no_pixel": len(areas) - len(with_pixels),
        "smallest_stand_with_a_pixel_ha": round(with_pixels[0], 4) if with_pixels else None,
        "max_area_ha": ceiling,
        "min_area_ha": minimum,
        "stands_over_max_area": len(over),
        "excess_over_max_area_each_ha": [round(e, 4) for e in over],
        "stands_over_max_area_in_merge_diagnostics": md.get("stands_over_max_area"),
        "excess_over_max_area_each_ha_in_merge_diagnostics": md.get("excess_over_max_area_each_ha"),
        "stands_below_min_area": md.get("stands_below_min_area"),
        "below_min_isolated": md.get("orphans_isolated"),
        "below_min_area_blocked": md.get("orphans_area_blocked"),
        "stands_left_out_of_fit": clustering.get("n_stands_left_out_of_fit"),
        "area_ha_left_out_of_fit": clustering.get("area_ha_in_stands_left_out_of_fit"),
        "kept_land_ha": kept.get("kept_land_ha"),
        "kept_land_ha_without_superpixel": kept.get("kept_land_ha_without_superpixel"),
        "superpixel_ha_off_kept_land": kept.get("superpixel_ha_off_kept_land"),
        "small_patches_ha": kept.get("small_patches_ha"),
    }


def main(argv: list[str] | None = None) -> int:
    runs = (argv if argv is not None else sys.argv[1:]) or sorted(
        p.name.removesuffix("_run.json") for p in RUNS_DIR.glob("*_run.json"))
    for run_id in runs:
        run = json.loads((RUNS_DIR / f"{run_id}_run.json").read_text())
        manifest = json.loads((RUNS_DIR / f"{run_id}_manifest_export.json").read_text())
        print(run_id)
        for key, value in describe(run, manifest).items():
            print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

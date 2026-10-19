"""Did a re-run reproduce the cached assets of an earlier run, stage by stage?

    python scripts/compare_cached_assets.py --old configs/<name>.yaml --new configs/<name>_repro.yaml
        [--old-fingerprint <fp>] [--stages masking data_load ...] [--out <file.json>]

READ-ONLY on Earth Engine: it lists assets and runs reductions. It submits no task and
writes no asset.

Cached stage outputs live at {asset_root}/{config}/{stage}/{key}__{fingerprint}. A config
copied under a new name (a `_repro` copy) has the same fingerprint in a fresh namespace,
so running it recomputes every stage from scratch. This script then compares each pair of
assets pixel for pixel over the ROI: how many pixels differ, where the mask differs, and
the largest absolute difference per asset. It answers a question a stand-level comparison
cannot: at WHICH stage a difference enters. If the Sentinel-2 composite differs and the
land-cover mask does not, an input archive changed; if every input matches and the SNIC
labels do not, the segmentation itself is not repeatable.

Label images (SNIC superpixel ids, stand ids, cluster labels) are compared the same way,
but read the result with care: ids are arbitrary, so two identical partitions with
different numbering count as different everywhere. For those, "0 pixels differ" proves
the partition reproduced; anything else needs the vector comparison in
scripts/compare_stand_runs.py to say how far apart the two partitions are.

`--old-fingerprint` is for comparing against assets cached before a config's content
changed (the fingerprint in the asset name is then not the one the config gives today).
When it is given, the old config's assets are always named in the legacy layout under that
fingerprint. Only compare stages whose settings did not change between the two.

Otherwise each config's assets are named in the cache layout it uses
(fmu.pipeline.cache_layout_for): by its fingerprint in the legacy layout, by each stage's key
in the per-step one (round 9).
When both configs are in the per-step layout, their assets are on the analysis grid, and the
pixels are compared on the grid of the old run's asset when the two share it; otherwise on a
geographic grid at the analysis scale, as before round 9.

`--out` writes two files: the rows, which hold results only, and beside them
`<name>_run.json` with the command, the date and the git commit it ran from.

Run from the repo root (fmu reads .env from the working directory).
"""

from __future__ import annotations

import argparse
import datetime
import json
import shlex
import sys
from pathlib import Path
from typing import Any


def run_record_path(out: Path) -> Path:
    """Where the run record of a result file goes: beside it, `<name>_run.json`."""
    return out.with_name(out.stem + "_run.json")


def summarise_rows(rows: list[dict[str, Any]]) -> list[str]:
    """One plain line per compared asset. Pure Python, so it is testable offline."""
    lines = []
    for r in rows:
        name = f"{r['stage']}/{r['key']}"
        if "outcome" in r:
            lines.append(f"{name:45s} {r['outcome']}")
            continue
        differ = r["pixel_bands_that_differ"]
        mask = r["pixels_whose_mask_differs"]
        total = r["pixel_values_compared"]
        if differ == 0 and mask == 0:
            verdict = "reproduced exactly"
        else:
            share = 100.0 * differ / total if total else float("nan")
            verdict = (
                f"differs: {differ} of {total} pixel values ({share:.1f}%), "
                f"largest difference {r['largest_abs_difference']} in band {r['in_band']}"
            )
            if mask:
                verdict += f"; the mask differs at {mask} pixel values"
        grid = "" if r["same_grid"] else "  [the two assets are on different pixel grids]"
        lines.append(f"{name:45s} {r['bands']:3d} band(s)  {verdict}{grid}")
    return lines


def compare(
    old_config: Path,
    new_config: Path,
    old_fingerprint: str | None,
    stages: list[str] | None,
) -> list[dict[str, Any]]:
    import ee

    import fmu.stages.clustering  # noqa: F401  (importing registers the stages)
    import fmu.stages.data_load  # noqa: F401
    import fmu.stages.features_embedding  # noqa: F401
    import fmu.stages.features_optical  # noqa: F401
    import fmu.stages.features_radar  # noqa: F401
    import fmu.stages.features_static  # noqa: F401
    import fmu.stages.features_structure  # noqa: F401
    import fmu.stages.masking  # noqa: F401
    import fmu.stages.merge  # noqa: F401
    import fmu.stages.segmentation  # noqa: F401
    from fmu.config import load_config
    from fmu.pipeline import Pipeline, cache_layout_for, default_stage_names
    from fmu.stages.base import get_stage_class
    from fmu.utils.caching import (
        LEGACY_LAYOUT,
        PER_STEP_LAYOUT,
        asset_exists,
        cache_key,
        cached_asset_path,
    )
    from fmu.utils.gee import init_gee, load_roi_geometry, safe_get_info

    old, new = load_config(old_config), load_config(new_config)
    init_gee()
    roi = load_roi_geometry(new.roi.roi_file)
    # A given old fingerprint names the earlier run's assets: the legacy layout under that
    # fingerprint, whatever cache_layout_for finds under today's (B27, round 13).
    layout_old = LEGACY_LAYOUT if old_fingerprint else cache_layout_for(old)[0]
    layout_new = cache_layout_for(new)[0]
    on_asset_grid = layout_old == layout_new == PER_STEP_LAYOUT
    print(f"cache layouts: old {layout_old}, new {layout_new}", flush=True)

    def key_old(stage: str) -> str:
        return old_fingerprint or cache_key(old, stage, layout_old)

    scale = new.export.analysis_scale_m
    names = stages or default_stage_names(new, through="clustering")
    kw_geographic = {
        "geometry": roi,
        "crs": "EPSG:4326",
        "scale": scale,
        "maxPixels": int(1e10),
        "tileScale": 4,
    }

    rows: list[dict[str, Any]] = []
    for stage in names:
        for key in sorted(Pipeline._resolve_cacheable_outputs(get_stage_class(stage)())):
            pa = cached_asset_path(old.name, stage, key, key_old(stage))
            pb = cached_asset_path(new.name, stage, key, cache_key(new, stage, layout_new))
            have_a, have_b = asset_exists(pa), asset_exists(pb)
            if not (have_a and have_b):
                missing = [n for n, h in ((old.name, have_a), (new.name, have_b)) if not h]
                rows.append(
                    {"stage": stage, "key": key, "outcome": "not cached for " + " and ".join(missing)}
                )
                continue
            a, b = ee.Image(pa), ee.Image(pb)
            bands_a = safe_get_info(a.bandNames(), context=f"{pa} bands")
            bands_b = safe_get_info(b.bandNames(), context=f"{pb} bands")
            if bands_a != bands_b:
                rows.append(
                    {"stage": stage, "key": key, "outcome": f"band lists differ: {bands_a} vs {bands_b}"}
                )
                continue
            proj_a = safe_get_info(a.projection(), context=f"{pa} projection")
            proj_b = safe_get_info(b.projection(), context=f"{pb} projection")
            same_grid = proj_a.get("crs") == proj_b.get("crs") and proj_a.get(
                "transform"
            ) == proj_b.get("transform")
            kw = (
                {
                    "geometry": roi,
                    "crs": proj_a["crs"],
                    "crsTransform": proj_a["transform"],
                    "maxPixels": int(1e10),
                    "tileScale": 4,
                }
                if on_asset_grid and same_grid
                else kw_geographic
            )
            got = safe_get_info(
                ee.Dictionary(
                    {
                        # Unweighted throughout: a pixel counts once if its centre is in
                        # the ROI. The default sum weights edge pixels by the share of
                        # them inside the ROI, and would not be comparable with a count.
                        "max": a.subtract(b).abs().reduceRegion(reducer=ee.Reducer.max(), **kw),
                        "neq": a.neq(b).reduceRegion(reducer=ee.Reducer.sum().unweighted(), **kw),
                        "n": a.neq(b).reduceRegion(reducer=ee.Reducer.count().unweighted(), **kw),
                        "mask": a.mask()
                        .neq(b.mask())
                        .unmask(0)
                        .reduceRegion(reducer=ee.Reducer.sum().unweighted(), **kw),
                    }
                ),
                context=f"{stage}/{key} old against new",
            )
            worst = max(bands_a, key=lambda k: got["max"].get(k) or 0)
            rows.append(
                {
                    "stage": stage,
                    "key": key,
                    "old_asset": pa,
                    "new_asset": pb,
                    "bands": len(bands_a),
                    "same_grid": same_grid,
                    "compared_on": "the assets' own grid" if kw is not kw_geographic
                    else f"EPSG:4326 at {scale} m",
                    # Bands can be masked differently, so the total is summed per band.
                    "pixel_values_compared": int(sum((got["n"].get(k) or 0) for k in bands_a)),
                    "pixel_bands_that_differ": int(sum((got["neq"].get(k) or 0) for k in bands_a)),
                    "pixels_whose_mask_differs": int(sum((got["mask"].get(k) or 0) for k in bands_a)),
                    "largest_abs_difference": got["max"].get(worst),
                    "in_band": worst,
                }
            )
            print(summarise_rows(rows[-1:])[0], flush=True)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--old", type=Path, required=True, help="config of the earlier run")
    ap.add_argument("--new", type=Path, required=True, help="config of the re-run")
    ap.add_argument("--old-fingerprint", default=None,
                    help="fingerprint in the earlier run's asset names, if not today's")
    ap.add_argument("--stages", nargs="+", default=None,
                    help="stages to compare (default: every stage through clustering)")
    ap.add_argument("--out", type=Path, default=None, help="write the rows here as JSON")
    args = ap.parse_args()

    rows = compare(args.old, args.new, args.old_fingerprint, args.stages)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(rows, indent=1) + "\n")
        from fmu.utils.provenance import git_state

        record = {
            "result_file": args.out.name,
            "command_line": "python " + " ".join(shlex.quote(a) for a in sys.argv),
            "date": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
            # Without `root`: the folder the checkout sits in says nothing about the code.
            "git": {k: v for k, v in git_state().items() if k != "root"},
        }
        run_record_path(args.out).write_text(json.dumps(record, indent=1) + "\n")
        print(f"wrote {args.out} and {run_record_path(args.out).name}")


if __name__ == "__main__":
    main()

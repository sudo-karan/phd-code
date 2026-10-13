"""Does SNIC give the same superpixels from cached features as from features computed live?

    python scripts/snic_cached_vs_live.py --config configs/<name>.yaml
        [--also configs/<other>.yaml ...] [--out <file.json>]

READ-ONLY on Earth Engine: it reads cached assets and runs reductions. It submits no task
and writes no asset (`Pipeline(use_cache=True, submit_exports=False)`).

Why this exists. With caching on, a stage that misses the cache runs live, and segmentation
then draws its superpixels on feature images that are still being computed on the fly. On a
later run the same features are read back as assets on the export grid, and segmentation
draws on those. If SNIC is sensitive to the difference, a config's superpixels (and so its
stands) depend on whether its segmentation happened to succeed before or after its features
were cached: on a cold cache a small ROI usually segments at once, a large one fails with a
memory limit and segments on the next pass, from the cache.

What it does. For `--config`, whose upstream features must all be cached:

  1. reads the cached features (every stage before segmentation);
  2. runs the segmentation stage now, on those cached features;
  3. compares the superpixel labels, pixel by pixel over the ROI, with the config's own
     cached `snic_clusters` asset, and with the `snic_clusters` asset of each `--also` config
     (for example the run this one is a from-scratch copy of).

Reading the result. If the config's own SNIC asset was made from cached features, step 3
should find almost no difference (a re-computation of the same thing). If it was made from
live features, the share of pixels that differ measures how much "live or cached" matters.
SNIC labels are ids derived from the seed grid, so the same computation gives the same ids;
"differs" means the pixel belongs to another superpixel.

Run from the repo root (fmu reads .env from the working directory).
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--config", type=Path, required=True,
                    help="config whose cached features SNIC is recomputed from")
    ap.add_argument("--also", type=Path, nargs="*", default=[],
                    help="other configs whose cached snic_clusters asset to compare with as well")
    ap.add_argument("--out", type=Path, default=None, help="write the result here as JSON")
    args = ap.parse_args()

    import ee

    import fmu.stages.data_load  # noqa: F401  (importing registers the stages)
    import fmu.stages.features_embedding  # noqa: F401
    import fmu.stages.features_optical  # noqa: F401
    import fmu.stages.features_radar  # noqa: F401
    import fmu.stages.features_static  # noqa: F401
    import fmu.stages.features_structure  # noqa: F401
    import fmu.stages.masking  # noqa: F401
    import fmu.stages.segmentation  # noqa: F401
    from fmu.config import load_config
    from fmu.pipeline import Pipeline, segmentation_stage_names
    from fmu.stages.base import PipelineContext
    from fmu.stages.segmentation import SegmentationStage
    from fmu.utils.caching import asset_exists, cached_asset_path, config_fingerprint
    from fmu.utils.gee import init_gee, load_roi_geometry, safe_get_info

    cfg = load_config(args.config)
    init_gee()
    roi = load_roi_geometry(cfg.roi.roi_file)
    upstream = segmentation_stage_names(cfg)[:-1]
    ctx = PipelineContext()
    ctx.set("roi", roi)
    run = Pipeline(upstream, use_cache=True, submit_exports=False, summaries=False).run(
        config=cfg, run_dir=Path(tempfile.mkdtemp(prefix="snic_cached_vs_live_")), initial_context=ctx
    )
    status = {s.name: s.cache_status for s in run.stages}
    submitted = sum(len(s.export_tasks) for s in run.stages)
    # mask_provenance feeds nothing; every other upstream output must come from the cache,
    # or "recomputed from cached features" would not be what this measures.
    live_inputs = sorted(
        f"{stage}/{key}"
        for stage, keys in status.items()
        for key, state in keys.items()
        if state != "hit" and key != "mask_provenance"
    )
    if live_inputs:
        raise SystemExit(
            f"{cfg.name}: these upstream outputs are not cached, so segmentation would not be "
            f"running on cached features: {live_inputs}"
        )

    recomputed = SegmentationStage().run(run.context, cfg).outputs["snic_clusters"].rename("x")
    targets = {cfg.name: load_config(args.config)}
    targets.update({load_config(p).name: load_config(p) for p in args.also})
    kw = {
        "geometry": roi,
        "crs": "EPSG:4326",
        "scale": cfg.export.analysis_scale_m,
        "maxPixels": int(1e10),
        "tileScale": 8,
    }
    result: dict[str, Any] = {
        "config": cfg.name,
        "fingerprint": config_fingerprint(cfg),
        "upstream_cache_status": status,
        "export_tasks_submitted": submitted,
        "comparisons": [],
    }
    for name, other in targets.items():
        path = cached_asset_path(name, "segmentation", "snic_clusters", config_fingerprint(other))
        if not asset_exists(path):
            result["comparisons"].append({"against": name, "asset": path, "outcome": "not cached"})
            print(f"against {name}: its snic_clusters asset is not cached")
            continue
        neq = recomputed.neq(ee.Image(path).rename("x"))
        got = safe_get_info(
            ee.Dictionary(
                {
                    "differ": neq.reduceRegion(reducer=ee.Reducer.sum().unweighted(), **kw),
                    "n": neq.reduceRegion(reducer=ee.Reducer.count().unweighted(), **kw),
                }
            ),
            context=f"recomputed SNIC against {name}",
        )
        differ, n = int(got["differ"]["x"]), int(got["n"]["x"])
        result["comparisons"].append(
            {"against": name, "asset": path, "pixels_compared": n, "pixels_with_another_label": differ}
        )
        print(
            f"SNIC recomputed from the cached features of {cfg.name}, against the cached SNIC "
            f"asset of {name}: {differ} of {n} pixels carry another label ({100.0 * differ / n:.1f}%)"
        )
    print(f"export tasks submitted: {submitted}")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=1) + "\n")
        print(f"wrote {args.out}")


if __name__ == "__main__":
    main()

"""Does SNIC give the same superpixels from cached features as from features computed live?

    python scripts/snic_cached_vs_live.py --config configs/<name>.yaml
        [--also configs/<other>.yaml ...] [--inputs cached live live-on-cache-grid]
        [--out <file.json>]

READ-ONLY on Earth Engine: it reads cached assets and runs reductions. It submits no task
and writes no asset (every `Pipeline(...)` here has `submit_exports=False`).

Why this exists. With caching on, a stage that misses the cache runs live, and segmentation
then draws its superpixels on feature images that are still being computed on the fly. On a
later run the same features are read back as assets, and segmentation draws on those. Which
of the two a config gets is not a setting. Before it runs SNIC the segmentation stage
computes statistics of the features over the whole ROI; on live features that request
sometimes fails (a memory limit or a time-out), and the next pass then segments from the
cache. Where it succeeds at once, the superpixels are drawn on live features.
`scripts/segmentation_route.py` reads from the run manifests which of the two a run took.

The two inputs are not the same pixels. The cache export is given no CRS, so a cached
feature asset sits on a geographic grid (EPSG:4326, pixels of 1/11132 of a degree: 10 m
north to south, less than 10 m east to west). Segmentation works on the UTM grid of the ROI,
at 10 m. Read from the cache, the features reach SNIC resampled from the geographic grid;
computed live, they are computed on the UTM grid directly.

What it does. For `--config`, whose upstream features must all be cached:

  1. builds the inputs of segmentation in each way named by `--inputs`:
       cached              the cached feature assets. The default, and the only one
                           unless more are asked for.
       live                the stages before segmentation computed now; nothing is read
                           from the cache.
       live-on-cache-grid  computed now, and each image then evaluated on the pixel grid
                           of its cached asset before segmentation reads it. That is how
                           the cache export computed the asset, so this input should be
                           the cached one again unless the source data have changed since.
  2. runs the segmentation stage on each;
  3. compares the superpixel labels, pixel by pixel over the ROI: each input against the
     config's own cached `snic_clusters` asset and against that of each `--also` config
     (for example the run this one is a from-scratch copy of), and the inputs against
     each other.

Reading the result. If the config's own SNIC asset was made from cached features, "cached"
should find almost no difference from it (a re-computation of the same thing). If it was
made from live features, the share of pixels that differ measures how much "live or cached"
matters, and "live" should find almost no difference instead. "live" and
"live-on-cache-grid" differ in one thing only, the grid the features are evaluated on: if
"live-on-cache-grid" gives the superpixels of "cached" and "live" does not, the grid is
what makes cached and live differ. SNIC labels are ids derived from the seed grid, so the
same computation gives the same ids; "differs" means the pixel belongs to another
superpixel.

The live inputs can fail on a large ROI for the reason the pipeline's first pass does. The
failure is then recorded for that input and the others are still compared. While it runs the
script says on stderr which request it is making, and it gives a request up after seven
minutes: Earth Engine stops an interactive computation after five, so a longer wait means
the connection is gone.

`--out` writes two files: the result, which holds results only, and beside it
`<name>_run.json` with the command, the date and the git commit it ran from.

Run from the repo root (fmu reads .env from the working directory).
"""

from __future__ import annotations

import argparse
import datetime
import json
import shlex
import sys
import tempfile
from pathlib import Path
from typing import Any

INPUTS = ("cached", "live", "live-on-cache-grid")
# Earth Engine stops an interactive computation after five minutes, so a request that has not
# answered after seven has lost its connection (a laptop that changed network, for example)
# and would otherwise wait for ever.
REQUEST_DEADLINE_MS = 7 * 60 * 1000


def run_record_path(out: Path) -> Path:
    """Where the run record of a result file goes: beside it, `<name>_run.json`."""
    return out.with_name(out.stem + "_run.json")


def describe(result: dict[str, Any]) -> list[str]:
    """Plain lines for a result. Pure Python, so it is testable offline."""
    name = result["config"]
    lines = []
    for kind, info in result["inputs"].items():
        if "error" in info:
            lines.append(f"{name}, {kind} features: segmentation could not be run: {info['error']}")
    for row in result["comparisons"]:
        what = f"SNIC from the {row['inputs']} features of {name}, against the cached SNIC asset of {row['against']}"
        lines.append(f"{what}: {_outcome(row)}")
    for row in result["between_inputs"]:
        what = f"SNIC from the {row['a']} features of {name}, against SNIC from its {row['b']} features"
        lines.append(f"{what}: {_outcome(row)}")
    lines.append(f"export tasks submitted: {result['export_tasks_submitted']}")
    return lines


def progress(what: str) -> None:
    """Say on stderr which request is about to be made. A live input can take minutes per
    request, and the results are printed only at the end."""
    print(f"  ... {what}", file=sys.stderr, flush=True)


def _outcome(row: dict[str, Any]) -> str:
    if "outcome" in row:
        return str(row["outcome"])
    differ, n = row["pixels_with_another_label"], row["pixels_compared"]
    return f"{differ} of {n} pixels carry another label ({100.0 * differ / n:.1f}%)"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--config", type=Path, required=True,
                    help="config whose cached features SNIC is recomputed from")
    ap.add_argument("--also", type=Path, nargs="*", default=[],
                    help="other configs whose cached snic_clusters asset to compare with as well")
    ap.add_argument("--inputs", nargs="+", choices=INPUTS, default=["cached"],
                    help="how to build the inputs of segmentation (default: cached)")
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
    from fmu.stages.base import PipelineContext, get_stage_class
    from fmu.stages.segmentation import SegmentationStage
    from fmu.utils.caching import asset_exists, cached_asset_path, config_fingerprint
    from fmu.utils.gee import init_gee, load_roi_geometry, safe_get_info
    from fmu.utils.provenance import git_state

    cfg = load_config(args.config)
    init_gee()
    ee.data.setDeadline(REQUEST_DEADLINE_MS)
    roi = load_roi_geometry(cfg.roi.roi_file)
    fingerprint = config_fingerprint(cfg)
    upstream = segmentation_stage_names(cfg)[:-1]
    kinds = [k for k in INPUTS if k in args.inputs]
    submitted = 0

    def run_upstream(use_cache: bool) -> Any:
        nonlocal submitted
        ctx = PipelineContext()
        ctx.set("roi", roi)
        run = Pipeline(upstream, use_cache=use_cache, submit_exports=False, summaries=False).run(
            config=cfg, run_dir=Path(tempfile.mkdtemp(prefix="snic_cached_vs_live_")), initial_context=ctx
        )
        submitted += sum(len(s.export_tasks) for s in run.stages)
        return run

    # The cached read comes first whatever was asked for: it says whether the upstream
    # features are all cached, which every input here is measured against.
    cached_run = run_upstream(use_cache=True)
    status = {s.name: s.cache_status for s in cached_run.stages}
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

    # The pixel grid of each cached upstream asset, and of the superpixels.
    grids: dict[str, Any] = {}
    asset_grids: dict[str, Any] = {}
    for stage in upstream:
        for key in sorted(Pipeline._resolve_cacheable_outputs(get_stage_class(stage)())):
            path = cached_asset_path(cfg.name, stage, key, fingerprint)
            if key == "mask_provenance" or not asset_exists(path):
                continue
            grids[key] = ee.Image(path).select(0).projection()
            got = safe_get_info(grids[key], context=f"{path} projection")
            asset_grids[f"{stage}/{key}"] = {"crs": got.get("crs"), "transform": got.get("transform")}

    contexts: dict[str, Any] = {}
    if "cached" in kinds:
        contexts["cached"] = cached_run.context
    if "live" in kinds or "live-on-cache-grid" in kinds:
        live_ctx = run_upstream(use_cache=False).context
        if "live" in kinds:
            contexts["live"] = live_ctx
        if "live-on-cache-grid" in kinds:
            on_grid = PipelineContext()
            for key in sorted(live_ctx.keys()):
                value = live_ctx.get(key)
                on_grid.set(key, value.reproject(grids[key]) if key in grids else value)
            contexts["live-on-cache-grid"] = on_grid

    result: dict[str, Any] = {
        "config": cfg.name,
        "fingerprint": fingerprint,
        "upstream_cache_status": status,
        "cached_asset_grids": asset_grids,
        "inputs": {},
        "comparisons": [],
        "between_inputs": [],
    }
    snic: dict[str, Any] = {}
    for kind in kinds:
        progress(f"segmentation on {kind} features")
        try:
            stage_result = SegmentationStage().run(contexts[kind], cfg)
        except Exception as exc:  # a live input on a large ROI: report it and go on
            result["inputs"][kind] = {"error": " ".join(str(exc).split())[:300]}
            continue
        snic[kind] = stage_result.outputs["snic_clusters"].rename("x")
        result["inputs"][kind] = {"distance_scale": stage_result.metadata.get("distance_scale")}

    kw = {
        "geometry": roi,
        "crs": "EPSG:4326",
        "scale": cfg.export.analysis_scale_m,
        "maxPixels": int(1e10),
        "tileScale": 8,
    }

    def share(a: Any, b: Any, context: str) -> dict[str, Any]:
        progress(context)
        neq = a.neq(b)
        try:
            got = safe_get_info(
                ee.Dictionary(
                    {
                        "differ": neq.reduceRegion(reducer=ee.Reducer.sum().unweighted(), **kw),
                        "n": neq.reduceRegion(reducer=ee.Reducer.count().unweighted(), **kw),
                    }
                ),
                context=context,
            )
        except Exception as exc:
            return {"outcome": "could not be compared: " + " ".join(str(exc).split())[:300]}
        return {"pixels_compared": int(got["n"]["x"]), "pixels_with_another_label": int(got["differ"]["x"])}

    targets = {cfg.name: cfg}
    targets.update({load_config(p).name: load_config(p) for p in args.also})
    for name, other in targets.items():
        path = cached_asset_path(name, "segmentation", "snic_clusters", config_fingerprint(other))
        if name == cfg.name and asset_exists(path):
            got = safe_get_info(ee.Image(path).select(0).projection(), context=f"{path} projection")
            result["superpixel_grid"] = {"crs": got.get("crs"), "transform": got.get("transform")}
        for kind in snic:
            row: dict[str, Any] = {"inputs": kind, "against": name, "asset": path}
            if not asset_exists(path):
                row["outcome"] = "its snic_clusters asset is not cached"
            else:
                row.update(share(snic[kind], ee.Image(path).rename("x"), f"SNIC from {kind} features against {name}"))
            result["comparisons"].append(row)
    done = list(snic)
    for i, a in enumerate(done):
        for b in done[i + 1:]:
            result["between_inputs"].append(
                {"a": a, "b": b, **share(snic[a], snic[b], f"SNIC from {a} features against {b}")}
            )
    result["export_tasks_submitted"] = submitted

    print("\n".join(describe(result)))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=1) + "\n")
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

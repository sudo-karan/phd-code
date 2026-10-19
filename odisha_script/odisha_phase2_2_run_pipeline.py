"""
Phase 2, step 2 — run the real pipeline over an Odisha AOI and pull the stand layers down.

NEEDS LIVE EARTH ENGINE. Submits cache exports to assets, and in the final pass the export
stage's own Drive tasks. Everything after this script is offline.

WHY FOUR PASSES
---------------
With `use_cache: true`, a stage that misses the cache runs live and submits an export of what it
just computed. An export task re-evaluates its image graph in batch, independently of the
interactive run. That is harmless for the feature images, but not for the chain
SNIC -> merge -> clustering: the merge is computed client-side from the SNIC labels the
interactive run saw, and applied as `snic_clusters.remap(raw_labels, stand_ids)`. If the cached
`cluster_labels` asset were evaluated against a different SNIC realisation than the cached
`snic_clusters` asset, the remap would be silently wrong. So each pass consumes the assets the
previous one cached, and refuses to start (exit 3) while any of them is missing:

  --through features       caches masking, the S2 composite and EVERY feature image the config
                           needs (segmentation's, the merge criteria's and clustering's alike:
                           fmu.pipeline.feature_stage_names). Round 9, issue #44 item 2: no later
                           pass computes a feature image live that another pass reads from the
                           cache, so SNIC, the merge and the fit all see the cached features
  --through segmentation   every feature asset is a HIT; caches snic_*
  --through clustering     SNIC is now a cache HIT, so the merge runs on the cached SNIC asset;
                           caches cluster_labels and feature_stack
  --through export         every cacheable output must be a HIT; runs profiling + export, then
                           reads the three vector layers back with the export stage's own
                           builders, one ROI part at a time and in pages (round 9, issue #44
                           item 11), numbered 1..N over all parts as the stage numbers the
                           layer it sends to Drive

Asset paths follow the config's cache layout (fmu.pipeline.cache_layout_for): the legacy one for
a config run before round 9, the per-step one otherwise.

`--wait` polls the tasks the pass submitted and returns when they finish.

WHAT IT WRITES (export pass only), under odisha_script/phase2_vectors/:
  <config>_stands_merged.geojson     the deliverable; stand identity is `stand_lbl`
  <config>_stands_snic.geojson       pre-merge superpixels; identity is `snic_label`
  <config>_stands_dissolved.geojson  connected same-cluster regions; identity is `unit_id`
  <config>_raster_at_plots.csv       stand_clusters / snic_clusters / cluster_labels sampled at
                                     the plot points -- a cross-check on the vector join, which
                                     is done by geometry in the next script
  <config>_run.json                  merge diagnostics, stand attributes, SNIC distance scale,
                                     export stage vector-layer counts, asset fingerprint. The
                                     scale is the segmentation pass's, read from its manifest in
                                     the run folders (this pass reads segmentation from the
                                     cache); `snic_distance_scale_from` says where. Until round
                                     13 it was null in every record (review C36)

The vector layers are the export stage's `_build_*_feature_collection` functions evaluated with
getInfo, i.e. the same FeatureCollections the stage submits to Drive, without needing Drive
credentials to read them back.

Run from the repo root (fmu reads .env from the working directory):
      python odisha_script/odisha_phase2_2_run_pipeline.py --config configs/odisha_v120_handcrafted.yaml --through segmentation --wait
      python odisha_script/odisha_phase2_2_run_pipeline.py --config ... --through clustering --wait
      python odisha_script/odisha_phase2_2_run_pipeline.py --config ... --through export
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import ee
import pandas as pd

import fmu.stages.clustering  # noqa: F401  (registers the stage)
import fmu.stages.data_load  # noqa: F401
import fmu.stages.export  # noqa: F401
import fmu.stages.features_embedding  # noqa: F401
import fmu.stages.features_optical  # noqa: F401
import fmu.stages.features_radar  # noqa: F401
import fmu.stages.features_static  # noqa: F401
import fmu.stages.features_structure  # noqa: F401
import fmu.stages.masking  # noqa: F401
import fmu.stages.merge  # noqa: F401
import fmu.stages.profiling  # noqa: F401
import fmu.stages.segmentation  # noqa: F401
from fmu.config import Config, load_config
from fmu.pipeline import (
    Pipeline,
    cache_asset_path_for,
    cache_layout_for,
    default_stage_names,
    feature_stage_names,
    segmentation_stage_names,
)
from fmu.stages.base import PipelineContext, get_stage_class
from fmu.stages.export import (
    _SORT_LAT_MULT,
    _build_dissolved_feature_collection,
    _build_merged_feature_collection,
    _build_snic_feature_collection,
    _roi_parts,
)
from fmu.utils.caching import asset_exists, config_fingerprint, step_keys
from fmu.utils.gee import init_gee, load_roi_geometry, safe_get_info
from fmu.utils.logging import init_logging
from fmu.utils.provenance import environment_state, git_state

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from odisha_phase2_0_aois import load_plot_points  # noqa: E402
from odisha_read_back_export import (  # noqa: E402
    read_layer,
    renumber,
    run_manifests,
    segmentation_distance_scale,
)

VECTOR_DIR = HERE / "phase2_vectors"
POLL_S = 30


PASSES = ("features", "segmentation", "clustering", "export")


def stage_names(cfg: Config, through: str) -> list[str]:
    if through == "features":
        return feature_stage_names(cfg)
    if through == "segmentation":
        return segmentation_stage_names(cfg)
    return default_stage_names(cfg, through=through)


def prerequisites(cfg: Config, through: str) -> list[str]:
    """The stages whose every cacheable output must exist before a pass starts.

    Every feature stage before segmentation, and before each pass after it: a
    pass never computes a feature image live (round 9, issue #44 item 2).
    """
    features = feature_stage_names(cfg)
    if through == "features":
        return []
    if through == "segmentation":
        return features
    if through == "clustering":
        return [*features, "segmentation"]
    return [*features, *[n for n in default_stage_names(cfg, through="clustering")
                         if n not in features]]


def missing_cache(cfg: Config, names: list[str], layout: str | None = None) -> list[str]:
    """Cacheable outputs of `names` that do not exist as assets yet, in the config's layout."""
    if layout is None:
        layout = cache_layout_for(cfg)[0]
    out = []
    for name in names:
        stage = get_stage_class(name)()
        for key in sorted(Pipeline._resolve_cacheable_outputs(stage)):
            path = cache_asset_path_for(cfg, name, key, layout)
            if not asset_exists(path):
                out.append(path)
    return out


def wait_for(task_ids: list[str]) -> bool:
    if not task_ids:
        print("  no export tasks submitted by this pass")
        return True
    print(f"  waiting on {len(task_ids)} task(s)")
    # The pipeline run is finished by now, so a deadline here bounds only these polls. Without
    # one, a poll issued during a network drop never returns and the pass hangs indefinitely.
    ee.data.setDeadline(120_000)
    while True:
        try:
            states = {s["id"]: s for s in ee.data.getTaskStatus(task_ids)}
        except Exception as e:  # noqa: BLE001 - a failed poll is retried, not fatal
            print(f"  {time.strftime('%H:%M:%S')} task-status poll failed ({str(e)[:100]}); retrying",
                  flush=True)
            time.sleep(POLL_S)
            continue
        counts: dict[str, int] = {}
        for s in states.values():
            counts[s["state"]] = counts.get(s["state"], 0) + 1
        print(f"  {time.strftime('%H:%M:%S')} {counts}", flush=True)
        if all(s["state"] in ("COMPLETED", "FAILED", "CANCELLED") for s in states.values()):
            bad = [s for s in states.values() if s["state"] != "COMPLETED"]
            for s in bad:
                print(f"  {s['state']}: {s.get('description')} -- {s.get('error_message', '')}")
            return not bad
        time.sleep(POLL_S)


def to_wgs84(fc: ee.FeatureCollection) -> ee.FeatureCollection:
    return fc.map(lambda f: f.setGeometry(f.geometry().transform("EPSG:4326", 0.1)))


# Layer -> (builder, the property numbered 1..N).
LAYER_BUILDERS = {
    "stands_merged": (_build_merged_feature_collection, "stand_id"),
    "stands_snic": (_build_snic_feature_collection, "stand_id"),
    "stands_dissolved": (_build_dissolved_feature_collection, "unit_id"),
}


def read_layer_by_part(cfg: Config, ctx: PipelineContext, layer: str) -> dict:
    """A layer as the export stage builds it, read back one ROI part at a time, in pages.

    The parts are the export stage's own (`_roi_parts`), so this is the layer the
    stage counted and sent to Drive. With one part and at most one page it is the
    one request this script always made, and the file is what it always was. With
    more, the parts' polygons are numbered 1..N over all parts with the stage's
    sort key (`renumber`), as the stage numbers the layer it sends.
    """
    scale = cfg.export.analysis_scale_m
    build, id_field = LAYER_BUILDERS[layer]
    parts = _roi_parts(ctx.get("roi"), scale)
    if len(parts) == 1:
        fc = to_wgs84(build(ctx=ctx, config=cfg, scale=scale, region=parts[0]))
        n = int(safe_get_info(fc.size(), context=f"{cfg.name} {layer}: count"))
        if n <= 2500:
            return safe_get_info(fc, context=f"{cfg.name} {layer}")
    features: list[dict] = []
    for i, part in enumerate(parts):
        fc = to_wgs84(build(ctx=ctx, config=cfg, scale=scale, region=part))
        features.extend(read_layer(fc, f"{cfg.name} {layer} part {i + 1} of {len(parts)}"))
    return {"type": "FeatureCollection", "columns": [],
            "features": renumber(features, id_field, _SORT_LAT_MULT)}


def pull_vectors(cfg: Config, ctx: PipelineContext) -> dict:
    VECTOR_DIR.mkdir(exist_ok=True)
    counts = {}
    for layer in LAYER_BUILDERS:
        gj = read_layer_by_part(cfg, ctx, layer)
        path = VECTOR_DIR / f"{cfg.name}_{layer}.geojson"
        path.write_text(json.dumps(gj))
        counts[layer] = len(gj["features"])
        print(f"  wrote {path.name}: {counts[layer]} polygons")
    return counts


def sample_rasters_at_plots(cfg: Config, ctx: PipelineContext) -> None:
    df = load_plot_points()
    fc = ee.FeatureCollection([
        ee.Feature(ee.Geometry.Point([float(lo), float(la)]), {"plot_key": k})
        for k, lo, la in zip(df.plot_key, df.lon6, df.lat6)
    ])
    roi = ctx.get("roi")
    fc = fc.filterBounds(roi)
    stack = (ctx.get("stand_clusters").rename("stand_clusters")
             .addBands(ctx.get("snic_clusters").rename("snic_clusters"))
             .addBands(ctx.get("cluster_labels").rename("cluster_labels"))
             .addBands(ctx.get("habitat_mask").rename("habitat_mask")))
    got = safe_get_info(
        stack.reduceRegions(collection=fc, reducer=ee.Reducer.first(),
                            scale=cfg.export.analysis_scale_m,
                            crs=ctx.get("snic_clusters").projection().crs()),
        context=f"{cfg.name} rasters at plots",
    )
    out = pd.DataFrame([f["properties"] for f in got["features"]])
    path = VECTOR_DIR / f"{cfg.name}_raster_at_plots.csv"
    out.to_csv(path, index=False)
    print(f"  wrote {path.name}: {len(out)} plots inside the ROI")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--through", choices=list(PASSES), required=True)
    ap.add_argument("--wait", action="store_true")
    args = ap.parse_args()

    cfg = load_config(args.config)
    init_gee()
    names = stage_names(cfg, args.through)
    layout, why = cache_layout_for(cfg)
    print(f"{cfg.name} fingerprint={config_fingerprint(cfg)} through={args.through}")
    print(f"  cache layout: {layout} ({why})")
    print(f"  stages: {' -> '.join(names)}")

    # Pre-flight: a pass may only run on top of the assets the previous passes cached.
    gaps = missing_cache(cfg, prerequisites(cfg, args.through), layout)
    if gaps:
        print(f"  REFUSING: {len(gaps)} upstream cache asset(s) missing; run the earlier pass first:")
        for g in gaps:
            print(f"    {g}")
        return 3

    roi = load_roi_geometry(cfg.roi.roi_file)
    ctx = PipelineContext()
    ctx.set("roi", roi)
    run_dir = init_logging(config_name=cfg.name)
    result = Pipeline(stage_names=names, use_cache=True, cache_layout=layout).run(
        config=cfg, run_dir=run_dir, initial_context=ctx)

    tasks = [t["task_id"] for s in result.stages for t in s.export_tasks]
    status = {s.name: s.cache_status for s in result.stages if s.cache_status}
    print(f"  run dir: {run_dir}")
    print(f"  cache status: {json.dumps(status)}")

    if args.through == "export":
        ctx = result.context
        counts = pull_vectors(cfg, ctx)
        sample_rasters_at_plots(cfg, ctx)
        by_name = {s.name: s for s in result.stages}
        export_meta = by_name["export"].metadata["manifest"]
        # This pass read segmentation from the cache, so the scale is the pass's that drew the
        # superpixels, from its manifest in the run folders beside this one (review C36).
        scale, scale_from = segmentation_distance_scale(
            by_name["segmentation"], run_manifests(Path(run_dir).parent, cfg.name), cfg.name)
        run = {
            "config": cfg.name,
            "fingerprint": config_fingerprint(cfg),
            "cache_layout": layout,
            "step_keys": step_keys(cfg) if layout == "per_step" else None,
            "git": git_state(),
            "environment": environment_state(),
            "run_dir": str(run_dir),
            "cache_status": status,
            "pulled_polygon_counts": counts,
            "export_vector_layers": {k: {kk: v.get(kk) for kk in ("n_features", "n_stands",
                                                                  "n_stands_split_into_pieces")}
                                     for k, v in export_meta["vector_layers"].items()},
            "drive_exports": export_meta["drive_exports"],
            "snic_distance_scale": scale,
            "snic_distance_scale_from": scale_from,
            "merge_diagnostics": ctx.get("merge_diagnostics"),
            "stand_attributes": ctx.get("stand_attributes"),
            # Per stand: superpixels, merges by kind, and whether and why it ended below the minimum size.
            "stand_provenance": ctx.get("stand_provenance"),
        }
        path = VECTOR_DIR / f"{cfg.name}_run.json"
        path.write_text(json.dumps(run, indent=1, default=str))
        print(f"  wrote {path.name}")

    if args.wait:
        return 0 if wait_for(tasks) else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

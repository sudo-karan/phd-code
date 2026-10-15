"""Read back the local files of a run's export pass from its saved assets, without the export stage.

    python odisha_script/odisha_read_back_export.py --config configs/<name>.yaml
        [--vectors-dir odisha_script/phase2_vectors] [--runs-dir runs] [--check]
        [--layers stands_merged ...] [--keep-read-back DIR]

READ-ONLY on Earth Engine. It reads cached assets, runs reductions and reads small results. It
submits no task and writes, changes or deletes no asset: `ee_read_only.forbid_writes()` makes any
such call raise before it is sent, and it refuses to start if a cached asset is missing (a
missing asset is what would make the pipeline start a cache export).

Why this exists. The export pass of `odisha_phase2_2_run_pipeline.py` does two things: the
pipeline's export stage sends files to Drive, and the script then reads the three stand layers
back (`<config>_stands_merged.geojson`, `_stands_snic.geojson`, `_stands_dissolved.geojson`),
samples the rasters at the field plots and writes the run record. On a large area that pass
can end early: the export stage counts the stand polygons of the whole area in one request,
which can time out, and reading a layer back in one request fails above 5,000 polygons. The
cached assets are complete by then, and running the pass again would send the Drive files a
second time.

What it does. It rebuilds the context exactly as the export pass does (every cached stage read
from the cache, the merge and the profiling run live), and then calls the export stage's own
three layer builders ONE PART OF THE ROI AT A TIME, reads each result back, and puts the parts
together. The builders number the polygons 1..N by centroid over what they are given; the
numbering is redone here over all parts, with the stage's own sort key. Nothing is sent to
Drive. It writes the files the export pass writes, but only those that are missing: a file the
run itself wrote is never replaced; what was read back is compared with it and the result goes
in the record. The run record it writes says it was read back.

`--check` writes nothing. It reads the layers back and compares them with the files already in
`--vectors-dir`: for a run whose export pass did finish, this shows that reading back gives the
run's own files.

Run from the repo root (fmu reads .env from the working directory).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "scripts"))

# Layer name -> (the property that identifies a polygon's unit, the property numbered 1..N).
LAYERS = {
    "stands_merged": ("stand_lbl", "stand_id"),
    "stands_snic": ("snic_label", "stand_id"),
    "stands_dissolved": (None, "unit_id"),
}
PAGE = 2500           # polygons read per request; Earth Engine stops a request at 5,000
DRIVE_LINE = re.compile(r"submitted (raster|vector) Drive export: task_id=(\S+), folder='([^']+)',\s*file='([^']+)'")


# ---------------------------------------------------------------------------
# Pure helpers (no Earth Engine): tested in tests/test_read_back_export.py
# ---------------------------------------------------------------------------


def renumber(features: list[dict[str, Any]], id_field: str, lat_mult: int) -> list[dict[str, Any]]:
    """Number the polygons 1..N by centroid, as the export stage does (north first, then west).

    The stage sorts on `-centroid_lat * lat_mult + centroid_lon`. Python's sort is stable, so two
    polygons with the same key keep the order they came in.
    """
    def key(f: dict[str, Any]) -> float:
        p = f["properties"]
        return -float(p["centroid_lat"]) * lat_mult + float(p["centroid_lon"])

    out = sorted(features, key=key)
    for i, f in enumerate(out, start=1):
        f["properties"][id_field] = i
    return out


def layer_counts(features: list[dict[str, Any]], unit_field: str | None) -> dict[str, Any]:
    """Polygons, units, and units in more than one piece: the three counts of the run record."""
    if unit_field is None:
        return {"n_features": len(features), "n_stands": None, "n_stands_split_into_pieces": None}
    pieces: dict[Any, int] = {}
    for f in features:
        unit = f["properties"][unit_field]
        pieces[unit] = pieces.get(unit, 0) + 1
    return {"n_features": len(features), "n_stands": len(pieces),
            "n_stands_split_into_pieces": sum(n > 1 for n in pieces.values())}


def compare_layer(mine: list[dict[str, Any]], theirs: list[dict[str, Any]], id_field: str,
                  *, tolerance: float = 1e-6) -> dict[str, Any]:
    """Two versions of one layer, polygon by polygon, matched on the 1..N number.

    Numbers are equal within `tolerance` (relative, or absolute below 1); outlines are compared
    as the area of the symmetric difference over the area of the union.
    """
    from shapely.geometry import shape

    def same(a: Any, b: Any) -> bool:
        if isinstance(a, bool) or isinstance(b, bool) or not isinstance(a, int | float) or not isinstance(b, int | float):
            return a == b
        return abs(float(a) - float(b)) <= tolerance * max(1.0, abs(float(a)), abs(float(b)))

    a = {f["properties"][id_field]: f for f in mine}
    b = {f["properties"][id_field]: f for f in theirs}
    properties, outlines, examples = 0, 0, []
    for i in sorted(set(a) & set(b)):
        pa, pb = a[i]["properties"], b[i]["properties"]
        differing = sorted(k for k in set(pa) | set(pb) if not same(pa.get(k), pb.get(k)))
        if differing:
            properties += 1
            if len(examples) < 5:
                examples.append([i, differing[:4]])
        ga, gb = shape(a[i]["geometry"]), shape(b[i]["geometry"])
        union = ga.union(gb).area
        if union > 0 and ga.symmetric_difference(gb).area / union > tolerance:
            outlines += 1
    return {
        "polygons": {"read_back": len(mine), "in_the_file": len(theirs)},
        "numbers_only_in_one": len(set(a) ^ set(b)),
        "polygons_with_a_property_that_differs": properties,
        "polygons_whose_outline_differs": outlines,
        "examples": examples,
        "equal": len(mine) == len(theirs) and not (set(a) ^ set(b)) and properties == 0 and outlines == 0,
    }


def drive_exports_in_log(text: str) -> dict[str, dict[str, str]]:
    """The Drive exports a run's log says the export stage submitted (file name -> folder, task)."""
    flat = re.sub(r"\s*\n\s+", " ", text)
    return {name: {"folder": folder, "task_id": task, "kind": kind}
            for kind, task, folder, name in DRIVE_LINE.findall(flat)}


# ---------------------------------------------------------------------------
# Earth Engine side
# ---------------------------------------------------------------------------


def read_layer(fc: Any, context: str) -> list[dict[str, Any]]:
    """Every polygon of a layer, read a page at a time."""
    import ee

    from fmu.utils.gee import safe_get_info

    n = int(safe_get_info(fc.size(), context=f"{context}: count"))
    if n <= PAGE:
        return safe_get_info(fc, context=context)["features"] if n else []
    features: list[dict[str, Any]] = []
    for start in range(0, n, PAGE):
        page = ee.FeatureCollection(fc.toList(PAGE, start))
        features.extend(safe_get_info(page, context=f"{context}: polygons {start} to {start + PAGE}")["features"])
    return features


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--vectors-dir", type=Path, default=HERE / "phase2_vectors",
                    help="where the run's local files are, and where the missing ones are written")
    ap.add_argument("--runs-dir", type=Path, default=REPO / "runs",
                    help="the folder of run folders, to read what the export stage submitted to Drive")
    ap.add_argument("--check", action="store_true",
                    help="write nothing: read the layers back and compare them with the files already there")
    ap.add_argument("--layers", nargs="+", choices=list(LAYERS), default=list(LAYERS),
                    help="with --check: only these layers (default all three)")
    ap.add_argument("--keep-read-back", type=Path, default=None,
                    help="with --check: also save what was read back in this folder, to look at a difference")
    args = ap.parse_args()
    if not args.check and (args.layers != list(LAYERS) or args.keep_read_back):
        ap.error("--layers and --keep-read-back go with --check")

    import ee
    import ee_read_only
    import odisha_phase2_2_run_pipeline as runner
    from shapely.geometry import mapping
    from transparency_masking import roi_parts

    from fmu.config import load_config
    from fmu.pipeline import Pipeline, default_stage_names
    from fmu.stages import export as export_stage
    from fmu.stages.base import PipelineContext
    from fmu.utils.caching import config_fingerprint
    from fmu.utils.gee import init_gee, load_roi_geometry
    from fmu.utils.logging import init_logging
    from fmu.utils.provenance import git_state

    cfg = load_config(args.config)
    init_gee()
    ee.data.setDeadline(7 * 60 * 1000)
    ee_read_only.forbid_writes()
    fingerprint = config_fingerprint(cfg)
    print(f"{cfg.name} fingerprint={fingerprint}")

    gaps = runner.missing_cache(cfg, default_stage_names(cfg, through="clustering"))
    if gaps:
        print(f"  REFUSING: {len(gaps)} cached asset(s) missing, so the run did not get this far:")
        for gap in gaps:
            print(f"    {gap}")
        return 3

    # The context of the export pass: every cached stage from the cache, merge and profiling live.
    names = [n for n in runner.stage_names(cfg, "export") if n != "export"]
    ctx = PipelineContext()
    ctx.set("roi", load_roi_geometry(cfg.roi.roi_file))
    run_dir = init_logging(config_name=cfg.name)
    result = Pipeline(stage_names=names, use_cache=True, summaries=False).run(
        config=cfg, run_dir=run_dir, initial_context=ctx)
    status = {s.name: s.cache_status for s in result.stages if s.cache_status}
    not_hit = {f"{stage}/{key}": state for stage, keys in status.items() for key, state in keys.items() if state != "hit"}
    if not_hit:
        raise SystemExit(f"not every cached output was read from the cache: {not_hit}")
    ctx = result.context
    scale = cfg.export.analysis_scale_m
    whole_roi = ctx.get("roi")

    parts = roi_parts(json.loads((REPO / cfg.roi.roi_file).read_text()), name_key="habitations")
    builders = {
        "stands_merged": export_stage._build_merged_feature_collection,
        "stands_snic": export_stage._build_snic_feature_collection,
        "stands_dissolved": export_stage._build_dissolved_feature_collection,
    }
    builders = {name: build for name, build in builders.items() if name in args.layers}
    layers: dict[str, list[dict[str, Any]]] = {name: [] for name in builders}
    try:
        for part in parts:
            # The part exactly as it is in the ROI file: the same outline, so the same pixels
            # as when the whole ROI is given at once. (Widening it adds edge pixels that the
            # cached assets hold but the ROI leaves out, and the polygons then differ.)
            ctx._data["roi"] = ee.Geometry(mapping(part.geometry))  # the builders read the ROI from the context
            for name, build in builders.items():
                print(f"  ... {name}, part {part.index + 1} of {len(parts)} ({part.name})", file=sys.stderr, flush=True)
                fc = runner.to_wgs84(build(ctx=ctx, config=cfg, scale=scale))
                layers[name].extend(read_layer(fc, f"{cfg.name} {name} part {part.index + 1}"))
    finally:
        ctx._data["roi"] = whole_roi
    for name in layers:
        layers[name] = renumber(layers[name], LAYERS[name][1], export_stage._SORT_LAT_MULT)

    if args.check:
        ok = True
        for name in layers:
            id_field = LAYERS[name][1]
            if args.keep_read_back:
                args.keep_read_back.mkdir(parents=True, exist_ok=True)
                (args.keep_read_back / f"{cfg.name}_{name}.geojson").write_text(
                    json.dumps({"type": "FeatureCollection", "features": layers[name]}))
            path = args.vectors_dir / f"{cfg.name}_{name}.geojson"
            if not path.exists():
                print(f"  {name}: no file to compare with ({len(layers[name])} polygons read back)")
                continue
            report = compare_layer(layers[name], json.loads(path.read_text())["features"], id_field)
            ok = ok and report["equal"]
            print(f"  {name}: {'EQUAL to the file the run wrote' if report['equal'] else 'DIFFERS'}  {json.dumps(report)}")
        print("export tasks submitted: 0")
        return 0 if ok else 1

    args.vectors_dir.mkdir(parents=True, exist_ok=True)
    written, kept, agreement = [], [], {}
    for name, (_unit, id_field) in LAYERS.items():
        path = args.vectors_dir / f"{cfg.name}_{name}.geojson"
        if path.exists():
            # The run wrote this one. It is kept, and what was read back is compared with it.
            kept.append(name)
            report = compare_layer(layers[name], json.loads(path.read_text())["features"], id_field)
            agreement[name] = report
            print(f"  kept {path.name}; read back {'EQUAL' if report['equal'] else 'DIFFERS'}: {json.dumps(report)}")
            continue
        path.write_text(json.dumps({"type": "FeatureCollection", "features": layers[name]}))
        written.append(name)
        print(f"  wrote {path.name}: {len(layers[name])} polygons (read back)")
    plots_path = args.vectors_dir / f"{cfg.name}_raster_at_plots.csv"
    if not plots_path.exists():
        runner.VECTOR_DIR = args.vectors_dir
        runner.sample_rasters_at_plots(cfg, ctx)

    record_path = args.vectors_dir / f"{cfg.name}_run.json"
    if record_path.exists():
        print(f"  kept {record_path.name}: the run wrote it")
    else:
        # What the export stage submitted to Drive, from the logs of the run's own folders.
        submitted: dict[str, dict[str, str]] = {}
        # Run folders are <config>_<YYYYMMDD_HHMMSS>: "_2*" leaves out the folders of another config
        # whose name starts with this one (<config>_repro_..., <config>_keptland_...).
        for log in sorted(args.runs_dir.glob(f"{cfg.name}_2*/fmu.log")):
            submitted.update(drive_exports_in_log(log.read_text(errors="replace")))
        by_name = {s.name: s for s in result.stages}
        record = {
            "config": cfg.name,
            "fingerprint": fingerprint,
            "git": git_state(),
            "read_back": {
                "by": "odisha_script/odisha_read_back_export.py",
                "why": "the run's export pass ended before it wrote this record",
                "layers_read_back": written,
                "layers_the_run_wrote": kept,
                "read_back_against_the_layers_the_run_wrote": agreement,
                "drive_exports_from": "the logs of the run's folders: what the export stage had submitted",
            },
            "cache_status": status,
            "pulled_polygon_counts": {name: len(layers[name]) for name in LAYERS},
            "export_vector_layers": {name: layer_counts(layers[name], unit) for name, (unit, _id) in LAYERS.items()},
            "drive_exports": submitted,
            "snic_distance_scale": by_name["segmentation"].metadata.get("distance_scale"),
            "merge_diagnostics": ctx.get("merge_diagnostics"),
            "stand_attributes": ctx.get("stand_attributes"),
            "stand_provenance": ctx.get("stand_provenance"),
        }
        record_path.write_text(json.dumps(record, indent=1, default=str))
        print(f"  wrote {record_path.name} (read back)")
    print("export tasks submitted: 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())

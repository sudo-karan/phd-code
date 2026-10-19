"""Record the demo set: the 14 Earth Engine re-runs of 13 October 2026 and everything they saved.

    python scripts/build_demo_set.py                       # lists the assets on Earth Engine, then writes
    python scripts/build_demo_set.py --from-listing FILE   # offline, from a listing saved earlier
    python scripts/build_demo_set.py --set boxes           # the four box runs of 14 Oct, to demo_set_boxes.json

Writes docs/demo/demo_set.json. One entry per `configs/*_repro.yaml`: the site, the arm, the
stand ceiling, k, the commit the run came from, every asset the run saved with the fingerprint
in its name, the files it sent to Drive, the folders on the Mac that hold its local outputs, and
whether its superpixels were drawn on cached or on live features.

Why the asset paths are written down. Later tools read the saved assets by the paths in this
file, never by recomputing a fingerprint from a config. A config that turns a new setting on
gets a new fingerprint, and would otherwise look for assets that do not exist.

READ-ONLY on Earth Engine: it lists the asset folders (`ee.data.listAssets`). It submits no
task and writes, changes or deletes no asset. `--from-listing` needs no Earth Engine at all.

It reads, besides the configs: docs/reproducibility/segmentation_route.json, and on the Mac
the git-ignored outputs/repro_runs/ (the run records, the batch state files, the run folders)
and outputs/transparency_repro/. Where a local file is missing the entry says so and the
script goes on, so the committed file can be checked on a machine without those folders
(tests/test_demo_set.py).

The box runs (`--set boxes`) are the hand-crafted 3 ha arm run again on a box around each
village's plots (configs/odisha_v120_3ha_squares_<district>.yaml, brief task A0). They are recorded
in a second file, docs/demo/demo_set_boxes.json, in the same form, with `"roi": "boxes"` and, per
run, how its export pass ended. Their local files are under outputs/squares_runs/.

Run from the repo root (fmu reads .env from the working directory).
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "docs" / "demo" / "demo_set.json"
# The asset root of the runs, written out: this file must be readable without .env.
ASSET_ROOT = "projects/replicating-paper/assets/fmu"
SUFFIX = "_repro"
# The id of the register entry (docs/decisions.yaml) for the rule the stands are re-merged under.
MERGE_RULE_ID = "spec-merge-pass2-skip-at-minimum"
LABEL = (
    "Demo set: Earth Engine runs of 13 Oct 2026 (commit df45350), stands re-merged under "
    f"`{MERGE_RULE_ID}`. Upstream of the merge it carries the open cache-grid issue "
    "(PR #42, question 1). The final re-run replaces it."
)
ROUTES = REPO / "docs" / "reproducibility" / "segmentation_route.json"
RUNS = REPO / "outputs" / "repro_runs"
MASKS = REPO / "outputs" / "transparency_repro"
# The second set: the four box runs. Same record, other folders.
def box_config_paths() -> list[Path]:
    """The four box configs: configs/odisha_v120_3ha_squares_<district>.yaml. The kept-land configs
    match the same glob but are configs of their own, not box runs: round 3's *_keptland.yaml and
    every later one with _keptland in its name (_keptland_s1desc, _r9, _r9_check). Until round 13
    only *_keptland.yaml was left out, so `--set boxes` took 13 configs and stopped (review C42)."""
    return sorted(p for p in (REPO / "configs").glob(BOXES["glob"]) if "_keptland" not in p.stem)


BOXES = {
    "glob": "odisha_v120_3ha_squares_*.yaml",
    "out": REPO / "docs" / "demo" / "demo_set_boxes.json",
    "routes": REPO / "docs" / "reproducibility" / "segmentation_route_squares.json",
    "runs": REPO / "outputs" / "squares_runs",
    "mask_data": REPO / "outputs" / "transparency_squares",
    "mask_docs": REPO / "outputs" / "transparency_squares_docs",
    "listing": REPO / "outputs" / "squares_runs" / "assets_listing.json",
    "label": (
        "Box runs: Earth Engine runs of 13 and 14 Oct 2026 (commit 4795358), the hand-crafted 3 ha arm on a "
        f"box around each village's plots, merged under `{MERGE_RULE_ID}`. Upstream of the merge they "
        "carry the open cache-grid issue (PR #42, question 1). The final re-run replaces them."
    ),
}
# A masking output today's code would cache, added after these runs were made.
NOT_CACHED = ["masking/mask_provenance"]


def list_assets(run_ids: list[str]) -> dict[str, list[str]]:
    """Every image under each run's asset folder, by reading Earth Engine. Read-only."""
    import ee

    from fmu.utils.gee import init_gee

    init_gee()
    ee.data.setDeadline(7 * 60 * 1000)

    def walk(parent: str) -> list[str]:
        found: list[str] = []
        token = None
        while True:
            params = {"parent": parent, **({"pageToken": token} if token else {})}
            resp = ee.data.listAssets(params)
            for asset in resp.get("assets", []):
                if asset["type"] == "FOLDER":
                    found.extend(walk(asset["name"]))
                else:
                    found.append(asset["name"])
            token = resp.get("nextPageToken")
            if not token:
                return sorted(found)

    return {run_id: walk(f"{ASSET_ROOT}/{run_id}") for run_id in run_ids}


def parse_asset(run_id: str, asset: str) -> dict[str, str]:
    """Stage, key and fingerprint from an asset id of the form the cache writes."""
    found = re.fullmatch(rf"{re.escape(ASSET_ROOT)}/{re.escape(run_id)}/([^/]+)/(.+)__([0-9a-f]+)", asset)
    if not found:
        raise ValueError(f"{asset}: not of the form {ASSET_ROOT}/{run_id}/<stage>/<key>__<fingerprint>")
    stage, key, fingerprint = found.groups()
    return {"stage": stage, "key": key, "fingerprint": fingerprint, "asset": asset}


def describe_config(path: Path) -> dict[str, Any]:
    """What the config itself says about the run. Offline."""
    from fmu.config import load_config

    cfg = load_config(path)
    run_id = cfg.name
    boxes = "_squares_" in run_id
    place = (run_id if boxes else run_id[: -len(SUFFIX)]).rsplit("_", 1)[-1]
    odisha = run_id.startswith("odisha_")
    embedding = cfg.clustering.feature_source == "embedding"
    return {
        "run_id": run_id,
        "config": str(path.relative_to(REPO)),
        "site": "Odisha" if odisha else "Sanjay Van",
        "district": place.capitalize() if odisha else None,
        "area": place.capitalize() if odisha else "Sanjay Van working area",
        # What the run's ROI is: a box around each village's plots, the hull of the plots, or the
        # Sanjay Van working rectangle.
        "roi": "boxes" if boxes else ("hulls" if odisha else "rectangle"),
        "arm": "alphaearth" if embedding else "feature_vector",
        "feature_source": cfg.clustering.feature_source,
        # The ceiling is the loaded value: the Sanjay Van configs have no merge block and take the default.
        "stand_ceiling_ha": cfg.merge.max_area_ha,
        "stand_minimum_ha": cfg.merge.min_area_ha,
        "segmentation_size": cfg.segmentation.size,
        "k": cfg.clustering.k,
        "roi_file": str(cfg.roi.roi_file),
        "drive_folder": cfg.export.drive_folder,
    }


def local_record(run_id: str, runs: Path = RUNS, mask_data: Path = MASKS / "_mask_data",
                 mask_docs: Path = MASKS / "_mask_docs") -> dict[str, Any]:
    """What the run left on this Mac. Every path is relative to the repo; a missing one is named."""
    vectors = runs / "phase2_vectors"
    rel = lambda p: str(p.relative_to(REPO))  # noqa: E731
    files = {
        "run_record": vectors / f"{run_id}_run.json",
        "stands_merged": vectors / f"{run_id}_stands_merged.geojson",
        "stands_snic": vectors / f"{run_id}_stands_snic.geojson",
        "stands_dissolved": vectors / f"{run_id}_stands_dissolved.geojson",
        "raster_at_plots": vectors / f"{run_id}_raster_at_plots.csv",
        "mask_data": mask_data / run_id,
        "mask_docs": mask_docs / run_id,
    }
    local: dict[str, Any] = {name: rel(path) for name, path in files.items()}
    local["run_folders"] = sorted(rel(p) for p in (runs / "runs").glob(f"{run_id}_2*") if p.is_dir())
    local["missing_here"] = sorted(name for name, path in files.items() if not path.exists())
    out: dict[str, Any] = {"local": local}

    record_path = files["run_record"]
    if record_path.exists():
        record = json.loads(record_path.read_text())
        diag = record["merge_diagnostics"]
        folders = sorted({e["folder"] for e in record["drive_exports"].values()})
        if len(folders) != 1:
            raise SystemExit(f"{run_id}: its Drive exports went to more than one folder: {folders}")
        read_back = record.get("read_back")
        out["drive"] = {
            "folder": folders[0],
            # As the export stage named them. A shapefile export arrives on Drive as its parts
            # (.shp, .shx, .dbf, .prj, .cpg) under the same stem. A record that was read back
            # holds them by file name, from the run's log.
            "files": sorted(record["drive_exports"] if read_back
                            else (e["filename"] for e in record["drive_exports"].values())),
            "checked": ("the export tasks the run's log says were submitted; not looked up on Drive" if read_back or runs != RUNS
                        else "every export task succeeded (Earth Engine task list); on Drive the files were "
                        "looked up for one run only, sanjay_van_baseline_repro"),
        }
        if read_back:
            # The run's export pass ended early; odisha_script/odisha_read_back_export.py wrote
            # the local files that were missing, from the run's cached assets.
            out["read_back"] = {k: read_back[k] for k in ("by", "why", "layers_read_back", "layers_the_run_wrote")}
        out["counts"] = {
            "superpixels_in_merge": diag["n_superpixels"],
            "stands": diag["n_stands"],
            "stand_polygons_exported": record["export_vector_layers"]["stands_merged"]["n_features"],
            "superpixel_polygons_exported": record["export_vector_layers"]["stands_snic"]["n_features"],
        }
        out["run_record_fingerprint"] = record["fingerprint"]
    for state_path in sorted((runs / "logs").glob("*.state.json")):
        state = json.loads(state_path.read_text())
        # Two shapes of state file: the batch script of 13 Oct, and run_passes_safely.py.
        git = state.get("git") or {"commit": state.get("commit"), "dirty": state.get("tree_dirty")}
        if run_id in state.get("done", []) or run_id in state.get("needs_attention", {}):
            out["source_commit"] = git["commit"]
            out["source_tree_dirty"] = git["dirty"]
            out["batch_state_file"] = rel(state_path)
            if runs != RUNS:
                out["export_pass"] = ("finished" if run_id in state.get("done", [])
                                      else state["needs_attention"][run_id])
    return out


def build_boxes(listing: dict[str, list[str]]) -> dict[str, Any]:
    """The record of the four box runs, in the form of the demo set."""
    routes = {r["config"]: r for r in json.loads(BOXES["routes"].read_text())}
    runs = []
    for path in box_config_paths():
        entry = describe_config(path)
        run_id = entry["run_id"]
        assets = [parse_asset(run_id, a) for a in listing[run_id]]
        fingerprints = sorted({a["fingerprint"] for a in assets})
        if len(fingerprints) != 1:
            raise SystemExit(f"{run_id}: its asset folder holds more than one fingerprint: {fingerprints}")
        route = routes[run_id]
        entry.update({
            "fingerprint": fingerprints[0],
            "assets": assets,
            "not_cached": [],
            "segmentation_route": route["route"],
            "segmentation_run": route["runs"][-1]["run"] if route["runs"] else None,
        })
        entry.update(local_record(run_id, BOXES["runs"], BOXES["mask_data"], BOXES["mask_docs"]))
        runs.append(entry)
    commits = sorted({r.get("source_commit") for r in runs if r.get("source_commit")})
    return {
        "label": BOXES["label"],
        "merge_rule": MERGE_RULE_ID,
        "what": "The four box runs of task A0 (docs/handoff/2026-10-13-round2.md): one batch, started once on "
        "13 Oct 2026 and ended on 14 Oct. Two finished their export pass; for the other two the local files "
        "the export pass did not write were read back from the cached assets (each entry says which).",
        "source_commit": commits[0] if len(commits) == 1 else commits,
        "source_commit_recorded_in": "outputs/squares_runs/logs/odisha_squares_3ha.state.json (git-ignored)",
        "asset_root": ASSET_ROOT,
        "assets_listed": "ee.data.listAssets on each run's asset folder, read-only",
        "n_assets": sum(len(r["assets"]) for r in runs),
        "open_issue": "As for the demo set: cached features sit on a geographic grid and segmentation works on "
        "the UTM grid (PR #42, question 1). The route each run took is in segmentation_route.",
        "runs": runs,
    }


def build(listing: dict[str, list[str]]) -> dict[str, Any]:
    routes = {r["config"]: r for r in json.loads(ROUTES.read_text())}
    runs = []
    for path in sorted((REPO / "configs").glob(f"*{SUFFIX}.yaml")):
        entry = describe_config(path)
        run_id = entry["run_id"]
        assets = [parse_asset(run_id, a) for a in listing[run_id]]
        fingerprints = sorted({a["fingerprint"] for a in assets})
        if len(fingerprints) != 1:
            raise SystemExit(f"{run_id}: its asset folder holds more than one fingerprint: {fingerprints}")
        route = routes[run_id]
        entry.update(
            {
                "fingerprint": fingerprints[0],
                "assets": assets,
                "not_cached": NOT_CACHED,
                "segmentation_route": route["route"],
                "segmentation_run": route["runs"][-1]["run"] if route["runs"] else None,
                "committed": {
                    "merge_provenance": f"docs/reproducibility/repro_runs/{run_id}/merge_provenance.csv",
                    "mask_summary": f"docs/reproducibility/repro_runs/{run_id}/mask_summary.md",
                    "snic_cached_vs_live": f"docs/reproducibility/snic_cached_vs_live_{run_id[: -len(SUFFIX)]}.json",
                },
            }
        )
        entry.update(local_record(run_id))
        runs.append(entry)
    commits = sorted({r.get("source_commit") for r in runs if r.get("source_commit")})
    return {
        "label": LABEL,
        "merge_rule": MERGE_RULE_ID,
        "what": "The 14 from-scratch re-runs of 13 Oct 2026 (PR #42), one per configs/*_repro.yaml. "
        "Tools read the saved assets by the paths given here, never by recomputing a fingerprint.",
        "source_commit": commits[0] if len(commits) == 1 else commits,
        "source_commit_recorded_in": "outputs/repro_runs/logs/*.state.json (git-ignored) and docs/reproducibility.md",
        "asset_root": ASSET_ROOT,
        "assets_listed": "ee.data.listAssets on each run's asset folder, read-only",
        "n_assets": sum(len(r["assets"]) for r in runs),
        "open_issue": "Cached features sit on a geographic grid and segmentation works on the UTM grid, so a "
        "run's superpixels depend on whether its features were cached when it segmented "
        "(docs/reproducibility.md, 'Superpixels depend on whether the features were cached when SNIC ran'; "
        "PR #42, question 1). The route each run took is in segmentation_route.",
        "runs": runs,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--from-listing", type=Path, default=None,
                    help="a JSON file {run_id: [asset id, ...]} saved by an earlier run; no Earth Engine")
    ap.add_argument("--save-listing", type=Path, default=REPO / "outputs" / "demo" / "assets_listing.json",
                    help="where the listing read from Earth Engine is kept (git-ignored)")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--set", choices=["hulls", "boxes"], default="hulls",
                    help="hulls: the 14 re-runs of 13 Oct (default). boxes: the four box runs, to demo_set_boxes.json")
    args = ap.parse_args()
    boxes = args.set == "boxes"
    if args.out is None:
        args.out = BOXES["out"] if boxes else OUT
    if boxes and args.save_listing == REPO / "outputs" / "demo" / "assets_listing.json":
        args.save_listing = BOXES["listing"]

    paths = box_config_paths() if boxes else sorted((REPO / "configs").glob(f"*{SUFFIX}.yaml"))
    run_ids = sorted(p.stem for p in paths)
    if args.from_listing:
        listing = json.loads(args.from_listing.read_text())
    else:
        listing = list_assets(run_ids)
        args.save_listing.parent.mkdir(parents=True, exist_ok=True)
        args.save_listing.write_text(json.dumps(listing, indent=1) + "\n")
    missing = sorted(set(run_ids) - set(listing))
    if missing:
        raise SystemExit(f"the listing has no entry for {missing}")

    demo = build_boxes(listing) if boxes else build(listing)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(demo, indent=1) + "\n")
    print(f"wrote {args.out.relative_to(REPO)}: {len(demo['runs'])} runs, {demo['n_assets']} assets")
    for run in demo["runs"]:
        gone = run["local"]["missing_here"]
        print(f"  {run['run_id']:42s} {run['arm']:14s} {run['stand_ceiling_ha']:>4} ha  k={run['k']}  "
              f"{len(run['assets'])} assets  {run['segmentation_route']:6s}" + (f"  missing here: {gone}" if gone else ""))


if __name__ == "__main__":
    main()

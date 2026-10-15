"""Write the record of the four round-6 box kept-land runs' cached assets, from their committed files.

    python scripts/record_keptland_assets.py [--out docs/reproducibility/keptland_boxes_assets.json]

Offline. scripts/reuse_upstream_assets.py takes a source run's assets from a record that lists
them by path (docs/demo/demo_set_boxes.json for the box runs, made by listing their asset folders
in Earth Engine). The four round-6 kept-land runs (configs/odisha_v120_3ha_squares_<district>_
keptland.yaml), the sources of round 7's descending-orbit configs, have no such record. This
writes one from what the repo already holds about them:

  - the fingerprint each run saved its assets under: its run record,
    docs/reproducibility/keptland_runs/<run>_run.json;
  - the assets the run found as copies: the copy record of round 6,
    docs/reproducibility/keptland_reuse_odisha.json, by destination;
  - the assets the run computed and cached: the cache exports in the manifests of its three
    passes, docs/reproducibility/keptland_runs/<run>_manifest_{segmentation,clustering,export}.json,
    by asset path.

Every path is checked against the cache layout, {asset_root}/{run}/{stage}/{key}__{fingerprint},
under the run's own fingerprint. Whether each asset exists is for
`scripts/reuse_upstream_assets.py --check` to ask Earth Engine, read-only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
RUNS = REPO / "docs" / "reproducibility" / "keptland_runs"
COPIES = REPO / "docs" / "reproducibility" / "keptland_reuse_odisha.json"
OUT = REPO / "docs" / "reproducibility" / "keptland_boxes_assets.json"
DISTRICTS = ("angul", "dhenkanal", "kendujhar", "koraput")
PASSES = ("segmentation", "clustering", "export")


def run_assets(run_id: str, runs_dir: Path, copies: list[dict[str, Any]]) -> dict[str, Any]:
    """One run's entry: its fingerprint and every asset it cached or found copied, by path."""
    run = json.loads((runs_dir / f"{run_id}_run.json").read_text())
    fp = run["fingerprint"]
    assets: dict[tuple[str, str], dict[str, Any]] = {}
    for c in copies:
        if c["config"] == run_id:
            assets[(c["stage"], c["key"])] = {"stage": c["stage"], "key": c["key"],
                                              "fingerprint": fp, "asset": c["destination"],
                                              "how": "copied (round 6)"}
    for kind in PASSES:
        manifest = json.loads((runs_dir / f"{run_id}_manifest_{kind}.json").read_text())
        for stage in manifest["stages"]:
            for task in stage.get("export_tasks") or []:
                path = task.get("asset_path")
                if not path:
                    continue
                key = path.rsplit("/", 1)[1].rsplit("__", 1)[0]
                assets.setdefault((stage["name"], key), {
                    "stage": stage["name"], "key": key, "fingerprint": fp, "asset": path,
                    "how": f"computed by the run ({kind} pass)"})
    root = None
    for (stage, key), a in assets.items():
        head, sep, tail = a["asset"].partition(f"/{run_id}/")
        if not sep or tail != f"{stage}/{key}__{fp}":
            raise SystemExit(f"{run_id}: {a['asset']} is not at the cache layout's path for "
                             f"{stage}/{key} under {fp}")
        if root not in (None, head):
            raise SystemExit(f"{run_id}: assets under two roots, {root} and {head}")
        root = head
    return {"run_id": run_id, "config": f"configs/{run_id}.yaml", "fingerprint": fp,
            "asset_root": root, "assets": [assets[k] for k in sorted(assets)]}


def build(runs_dir: Path = RUNS, copies_path: Path = COPIES) -> dict[str, Any]:
    copies = json.loads(copies_path.read_text())["copies"]
    runs = [run_assets(f"odisha_v120_3ha_squares_{d}_keptland", runs_dir, copies)
            for d in DISTRICTS]
    roots = {r.pop("asset_root") for r in runs}
    if len(roots) != 1:
        raise SystemExit(f"the runs' assets are under several roots: {sorted(roots)}")
    return {
        "what": "The cached assets of the four round-6 box kept-land runs "
                "(configs/odisha_v120_3ha_squares_<district>_keptland.yaml, run on 15 Oct 2026 "
                "from a run tree at d180cb8), the sources of round 7's descending-orbit configs.",
        "assets_listed": "from the committed files by scripts/record_keptland_assets.py: the "
                         "copies in docs/reproducibility/keptland_reuse_odisha.json and the cache "
                         "exports in each run's three pass manifests; each path checked against "
                         "the cache layout under the run's fingerprint (its run record); whether "
                         "each exists is asked by scripts/reuse_upstream_assets.py --check",
        "asset_root": roots.pop(),
        "n_assets": sum(len(r["assets"]) for r in runs),
        "runs": runs,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)
    record = build()
    args.out.write_text(json.dumps(record, indent=1) + "\n")
    print(f"wrote {args.out}: {len(record['runs'])} runs, {record['n_assets']} assets")
    return 0


if __name__ == "__main__":
    sys.exit(main())

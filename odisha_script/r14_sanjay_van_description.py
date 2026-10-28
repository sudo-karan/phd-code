"""Sanjay Van in R3 (round 14, Task 8): stand counts, sizes, k and the types' shares, arm by arm.

    python odisha_script/r14_sanjay_van_description.py \
        [--records docs/reproducibility/r14_runs/second_half] \
        [--runs sanjay_van_baseline_keptland_r14 sanjay_van_alphaearth_keptland_r14] [--label R3] \
        [--beside-records docs/reproducibility/r9_runs] \
        [--beside-runs sanjay_van_baseline_keptland_r9 sanjay_van_alphaearth_keptland_r9] \
        [--beside-label _r9] [--out-dir odisha_script/keptland_scores] [--stem sanjay_van_r14_description]

Offline; reads committed files only. Sanjay Van has no field plots, so no field score: the
declaration gives it "stand counts, sizes, k and the types' shares only"
(odisha_script/PHASE_KEPTLAND_PREDECLARED.md, R3, side by side; the round 14 brief, Task 8). For each
run, from <run>_run.json, <run>_manifest_export.json and <run>_stands_merged.geojson in its records
folder (the layer from where <run>_files_off_git.json says, if it is off git, checked by its
SHA-256, as odisha_script/odisha_keptland_score.py reads it):
  - the counts: the stand counts of scripts/describe_keptland_runs.py's describe(), unchanged (the
    stands of the merge, those with no pixel, those over merge.max_area_ha, those below
    merge.min_area_ha by cause, those left out of the k-means fit), and the merged layer's: its
    stands (each stand by its stand_lbl, which a stand split into pieces carries on every piece),
    its polygons, its stands split into pieces, and the merge's stands with no polygon in it;
  - the sizes: the stands' areas, ha, as describe() takes them (the merge's stand_attributes): the
    smallest, the 10th, 25th, 50th, 75th and 90th percentiles (numpy's linear rule), the largest, the
    mean and the total, of all the stands and of those at or above merge.min_area_ha;
  - k: the clustering's, as the export pass recorded it;
  - the types' shares: for each type (the clustering's cluster_id, 0 to k - 1), its stands in the
    merged layer and their share of the layer's stands, and its area and share of the habitat as the
    export pass recorded them (cluster_distribution, from the type raster's pixels; a type it does
    not list has no pixel, 0 ha and 0 %). A stand whose pieces carry two types stops the script.
The runs named by --beside-runs (the _r9 runs) are given beside, by the same rules. Numbers only:
no difference is tested and none is read. Writes <stem>.md and <stem>.json (results only, no dates)
and <stem>_run.json (the command, the date, the git state, the inputs' SHA-256), and refuses to
write over a file that exists.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SCORES = HERE / "keptland_scores"
STEM = "sanjay_van_r14_description"
RUNS = ("sanjay_van_baseline_keptland_r14", "sanjay_van_alphaearth_keptland_r14")
BESIDE = ("sanjay_van_baseline_keptland_r9", "sanjay_van_alphaearth_keptland_r9")
ARMS = {"handcrafted": "hand-crafted", "embedding": "AlphaEarth"}
PERCENTILES = (10, 25, 50, 75, 90)
# The stand counts of describe() that the declaration allows ("stand counts, sizes, k and the types'
# shares only"); the rest of its output (superpixels, kept land, each stand's excess) is left out.
DESCRIBE_COUNTS = ("stands", "stands_with_no_pixel", "min_area_ha", "stands_below_min_area",
                   "below_min_isolated", "below_min_area_blocked", "stands_left_out_of_fit",
                   "area_ha_left_out_of_fit", "max_area_ha", "stands_over_max_area")


def _describe_module() -> Any:
    spec = importlib.util.spec_from_file_location("describe_keptland_runs",
                                                  REPO / "scripts" / "describe_keptland_runs.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def stand_layer(run: str, records: Path) -> Path:
    """The run's merged stand layer: in records, or where its off-git record says, checked."""
    path = records / f"{run}_stands_merged.geojson"
    if path.exists():
        return path
    record = records / f"{run}_files_off_git.json"
    if not record.exists():
        raise SystemExit(f"{run}: no stand layer in {records} and no off-git record")
    entries = {f["file"]: f for f in json.loads(record.read_text())["files"]}
    if path.name not in entries:
        raise SystemExit(f"{run}: no stand layer in {records}, and its off-git record {record.name} does "
                         f"not name {path.name}")
    entry = entries[path.name]
    where = Path(entry["where"])
    if not where.exists():
        raise SystemExit(f"{run}: {path.name} is off git at {where}, which is not here")
    if sha256(where) != entry["sha256"]:
        raise SystemExit(f"{run}: {where} is not the file its record names (SHA-256 differs)")
    return where


def sizes(areas: list[float]) -> dict[str, Any]:
    """How many, the percentiles, the mean and the total of some stands' areas (ha)."""
    if not areas:
        return {"stands": 0}
    a = np.asarray(areas, dtype=float)
    out: dict[str, Any] = {"stands": int(a.size), "smallest_ha": round(float(a.min()), 4)}
    out.update({f"p{p}_ha": round(float(np.percentile(a, p)), 4) for p in PERCENTILES})
    out.update({"largest_ha": round(float(a.max()), 4), "mean_ha": round(float(a.mean()), 4),
                "total_ha": round(float(a.sum()), 4)})
    return out


def describe_run(run_record: dict[str, Any], manifest: dict[str, Any], layer: dict[str, Any],
                 describe: Any) -> dict[str, Any]:
    """The numbers of one run, from its run record, export manifest and merged stand layer."""
    stages = {s["name"]: s for s in manifest["stages"]}
    clustering = stages["export"]["metadata"]["manifest"]["clustering"]
    k = int(clustering["k"])
    minimum = float(manifest["config"]["merge"]["min_area_ha"])
    areas = [float(a["area_ha"]) for a in run_record["stand_attributes"].values()]
    # Each stand by its label: the export writes one polygon per piece, each piece with its stand's
    # stand_lbl and cluster_id.
    type_of: dict[int, set[Any]] = {}
    pieces: dict[int, int] = {}
    for f in layer["features"]:
        lbl = int(f["properties"]["stand_lbl"])
        type_of.setdefault(lbl, set()).add(f["properties"].get("cluster_id"))
        pieces[lbl] = pieces.get(lbl, 0) + 1
    two = sorted(lbl for lbl, ts in type_of.items() if len(ts) > 1)
    if two:
        raise SystemExit(f"stands whose pieces carry two types in the merged layer: {two[:10]}")
    types = {lbl: next(iter(ts)) for lbl, ts in type_of.items()}
    unknown = sorted({t for t in types.values() if t is not None and t not in range(k)})
    if unknown:
        raise SystemExit(f"types outside 0 to k - 1 = {k - 1} in the merged layer: {unknown}")
    by_type = {t: sum(1 for v in types.values() if v == t) for t in range(k)}
    if not clustering.get("cluster_distribution"):
        raise SystemExit("the export manifest records no cluster_distribution")
    distribution = {int(d["cluster_id"]): d for d in clustering["cluster_distribution"]}
    n = len(types)
    shares = []
    for t in range(k):
        d = distribution.get(t) or {"area_ha": 0.0, "percent_of_habitat": 0.0}  # not listed: no pixel
        shares.append({"type": t, "stands": by_type[t],
                       "share_of_stands_percent": round(100 * by_type[t] / n, 2) if n else None,
                       "area_ha": d.get("area_ha"), "share_of_habitat_percent": d.get("percent_of_habitat")})
    counts = describe(run_record, manifest)
    merge_labels = {int(lbl) for lbl in run_record["stand_attributes"]}
    return {"arm": ARMS.get(str(clustering.get("feature_source")), str(clustering.get("feature_source"))),
            "k": k,
            "counts": {**{key: counts.get(key) for key in DESCRIBE_COUNTS},
                       "stands_in_merged_layer": n,
                       "stand_polygons_in_merged_layer": len(layer["features"]),
                       "stands_split_into_pieces": sum(1 for v in pieces.values() if v > 1),
                       "stands_of_the_merge_with_no_polygon": len(merge_labels - set(types)),
                       "stands_in_merged_layer_without_a_type": sum(1 for v in types.values() if v is None)},
            "sizes_all_stands": sizes(areas),
            "sizes_at_or_above_min_area": sizes([a for a in areas if a >= minimum]),
            "types": shares}


COUNT_ROWS = (("stands", "stands (the merge)"),
              ("stands_with_no_pixel", "of them with no pixel (0 ha)"),
              ("stands_of_the_merge_with_no_polygon", "of them with no polygon in the merged layer"),
              ("stands_in_merged_layer", "stands in the merged layer"),
              ("stand_polygons_in_merged_layer", "their polygons"),
              ("stands_split_into_pieces", "stands split into pieces"),
              ("stands_in_merged_layer_without_a_type", "stands without a type"),
              ("min_area_ha", "the minimum size, ha (merge.min_area_ha)"),
              ("stands_below_min_area", "stands below the minimum size"),
              ("below_min_isolated", "of them isolated"),
              ("below_min_area_blocked", "of them blocked by area"),
              ("stands_left_out_of_fit", "stands left out of the k-means fit"),
              ("area_ha_left_out_of_fit", "their area, ha"),
              ("max_area_ha", "the maximum size, ha (merge.max_area_ha)"),
              ("stands_over_max_area", "stands over the maximum size"))
SIZE_ROWS = (("stands", "stands"), ("smallest_ha", "smallest"), *((f"p{p}_ha", f"{p}th percentile")
             for p in PERCENTILES), ("largest_ha", "largest"), ("mean_ha", "mean"), ("total_ha", "total"))


def cell(v: Any) -> str:
    if v is None:
        return "n/a"
    if isinstance(v, float):
        return f"{v:,.4f}".rstrip("0").rstrip(".") if v != int(v) else f"{v:,.0f}"
    if isinstance(v, int):
        return f"{v:,}"
    return str(v)


def markdown(results: dict[str, Any], columns: list[tuple[str, str]]) -> str:
    """The description as Markdown: one column per run (label, run)."""
    head = "| | " + " | ".join(label for label, _ in columns) + " |"
    rule = "|---|" + "---:|" * len(columns)
    runs = [results[run] for _, run in columns]
    lines = ["# Sanjay Van: stand counts, sizes, k and the types' shares", "",
             "Written by `odisha_script/r14_sanjay_van_description.py` from the runs' committed files. Sanjay",
             "Van has no field plots: as declared, its runs get stand counts, sizes, k and the types' shares",
             "only (`odisha_script/PHASE_KEPTLAND_PREDECLARED.md`). Numbers only: no difference is tested.",
             "", "## The runs, k and the stand counts", "",
             "The stands of the merge are those of each run record's `stand_attributes`; the merged layer's",
             "are counted by their `stand_lbl`, a stand split into pieces once.", "", head, rule,
             "| run | " + " | ".join(f"`{run}`" for _, run in columns) + " |",
             "| k | " + " | ".join(cell(r["k"]) for r in runs) + " |"]
    lines += [f"| {name} | " + " | ".join(cell(r["counts"].get(key)) for r in runs) + " |"
              for key, name in COUNT_ROWS]
    for block, title in (("sizes_all_stands", "all the stands of the merge"),
                         ("sizes_at_or_above_min_area", "the stands at or above the minimum size")):
        lines += ["", f"## Sizes, ha: {title}", "",
                  "The stands' areas from the merge (each run record's `stand_attributes`); percentiles by",
                  "numpy's linear rule.", "", head, rule]
        lines += [f"| {name} | " + " | ".join(cell(r[block].get(key)) for r in runs) + " |"
                  for key, name in SIZE_ROWS]
    lines += ["", "## The types' shares", "",
              "Each type's stands in the merged layer and their share of its stands, and the type's area and",
              "share of the habitat as the export pass recorded them (`cluster_distribution`, from the type",
              "raster's pixels; a type it does not list has no pixel). The type numbers are the clustering's",
              "labels; a type number in one run names no type in another."]
    for label, run in columns:
        r = results[run]
        lines += ["", f"### {label}: `{run}`, k = {r['k']}", "",
                  "| type | stands | share of the stands, % | area, ha | share of the habitat, % |",
                  "|---:|---:|---:|---:|---:|"]
        lines += [f"| {t['type']} | {cell(t['stands'])} | {cell(t['share_of_stands_percent'])} | "
                  f"{cell(t['area_ha'])} | {cell(t['share_of_habitat_percent'])} |" for t in r["types"]]
    return "\n".join(lines) + "\n"


def git_block(now: bool = False) -> dict[str, Any]:
    """This checkout's git state as a run record holds it (odisha_keptland_score.py's rule)."""
    sys.path.insert(0, str(REPO / "src"))
    from fmu.utils.provenance import git_state, git_state_now

    state = git_state_now(HERE) if now else git_state(HERE)
    return {k: v for k, v in state.items() if k != "root"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--records", type=Path, default=REPO / "docs" / "reproducibility" / "r14_runs" / "second_half")
    ap.add_argument("--runs", nargs="+", default=list(RUNS))
    ap.add_argument("--label", default="R3")
    ap.add_argument("--beside-records", type=Path, default=REPO / "docs" / "reproducibility" / "r9_runs")
    ap.add_argument("--beside-runs", nargs="*", default=list(BESIDE))
    ap.add_argument("--beside-label", default="_r9")
    ap.add_argument("--out-dir", type=Path, default=SCORES)
    ap.add_argument("--stem", default=STEM)
    args = ap.parse_args(argv)
    git = git_block()
    outs = [args.out_dir / f"{args.stem}{s}" for s in (".md", ".json", "_run.json")]
    there = [str(p) for p in outs if p.exists()]
    if there:
        raise SystemExit(f"refusing to write over {there}")
    describe = _describe_module().describe
    results: dict[str, Any] = {}
    inputs: dict[str, str] = {}
    columns: list[tuple[str, str]] = []
    for records, runs, label in ((args.records, args.runs, args.label),
                                 (args.beside_records, args.beside_runs, args.beside_label)):
        for run in runs:
            files = [records / f"{run}_run.json", records / f"{run}_manifest_export.json", stand_layer(run, records)]
            run_record, manifest, layer = (json.loads(p.read_text()) for p in files)
            inputs.update({p.name: sha256(p) for p in files})
            results[run] = describe_run(run_record, manifest, layer, describe)
            columns.append((f"{results[run]['arm']} ({label})", run))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    outs[0].write_text(markdown(results, columns))
    outs[1].write_text(json.dumps({"runs": results}, indent=1) + "\n")
    import datetime
    import shlex

    from fmu.utils.provenance import environment_state

    run = {"result_files": [outs[0].name, outs[1].name],
           "command_line": "python " + " ".join(shlex.quote(a) for a in
                                                ["odisha_script/r14_sanjay_van_description.py",
                                                 *(argv if argv is not None else sys.argv[1:])]),
           "date": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
           "inputs_sha256": inputs, "git": git, "git_at_end": git_block(now=True),
           "environment": environment_state()}
    outs[2].write_text(json.dumps(run, indent=1) + "\n")
    print(f"wrote {', '.join(str(p) for p in outs)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

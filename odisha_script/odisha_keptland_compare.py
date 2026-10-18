"""Two sets of kept-land field-check results side by side: the five scores and the stand counts.

    python odisha_script/odisha_keptland_compare.py --old-stem keptland_s1desc --new-stem keptland_s1desc_r9 \
        --old-runs odisha_v120_3ha_squares_{district}_keptland_s1desc --old-records docs/reproducibility/keptland_runs \
        --new-runs odisha_v120_3ha_squares_{district}_keptland_s1desc_r9 --new-records docs/reproducibility/r9_runs \
        --pair sanjay_van_baseline_keptland sanjay_van_baseline_keptland_r9 \
        --pair sanjay_van_alphaearth_keptland sanjay_van_alphaearth_keptland_r9 \
        --out odisha_script/keptland_scores/keptland_s1desc_r9_vs_s1desc.md

Offline; reads committed files only: the two scores files written by odisha_keptland_score.py
(<stem>_scores.json in odisha_script/keptland_scores/) and each run's record (<run>_run.json).
Writes one Markdown file of results: the scores of every analysis, old, new and new minus old;
how the plots join, per district; and per district the superpixels, the stands, the stand
polygons and the stands below the minimum size, and the same counts for each run named by
--pair (runs that are not scored, such as Sanjay Van's). No test of any difference is made, as
the declaration makes none (odisha_script/PHASE_KEPTLAND_PREDECLARED.md). No dates.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SCORES = HERE / "keptland_scores"
DISTRICTS = ("angul", "dhenkanal", "kendujhar", "koraput")
STATS = (("delin_all", "1 drawing: ARI, all plots"),
         ("delin_multi", "2 drawing: ARI, stands of 2+ plots"),
         ("prec", "3 drawing: same-stand pair precision"),
         ("lab_wmean", "4 labelling: ARI, district mean"),
         ("far_gap", "5 labelling: far-apart gap"))


def fmt(v: Any, signed: bool = True) -> str:
    if v is None or (isinstance(v, float) and v != v):
        return "n/a"
    return f"{v:+.4f}" if signed else f"{v:.4f}"


def run_counts(records: Path, run: str) -> dict[str, Any]:
    r = json.loads((records / f"{run}_run.json").read_text())
    md = r.get("merge_diagnostics") or {}
    layers = r.get("export_vector_layers") or {}
    merged = layers.get("stands_merged") or {}
    return {"superpixels": md.get("n_superpixels"), "stands": md.get("n_stands"),
            "stand_polygons": merged.get("n_features"), "stands_with_a_polygon": merged.get("n_stands"),
            "below_min": md.get("stands_below_min_area"),
            "superpixel_polygons": (layers.get("stands_snic") or {}).get("n_features"),
            "regions": (layers.get("stands_dissolved") or {}).get("n_features")}


def compare(old: dict[str, Any], new: dict[str, Any], old_counts: dict[str, dict], new_counts: dict[str, dict],
            labels: tuple[str, str]) -> str:
    """The Markdown text. The count dicts are keyed by district, then by any other run compared."""
    lo, ln = labels
    lines = [f"# The kept-land field check: {ln} against {lo}", "",
             "Written by `odisha_script/odisha_keptland_compare.py` from the committed scores files and run",
             "records. Numbers only: as the declaration fixes, no chance test is run and no difference is",
             "tested (`odisha_script/PHASE_KEPTLAND_PREDECLARED.md`).", "",
             "## The five scores", "",
             "| Analysis | Score | " + lo + " | " + ln + " | new minus old |", "|---|---|---|---|---|"]
    by_old = {a["analysis"]: a for a in old["analyses"]}
    for a in new["analyses"]:
        o = by_old.get(a["analysis"])
        for key, label in STATS:
            ov = o[key] if o else None
            nv = a[key]
            d = (nv - ov) if (ov is not None and nv == nv and ov == ov) else None
            lines.append(f"| {a['analysis']} | {label} | {fmt(ov)} | {fmt(nv)} | {fmt(d)} |")
        if o:
            lines.append(f"| {a['analysis']} | plots scored | {o['counts']['plots']} | {a['counts']['plots']} | "
                         f"{a['counts']['plots'] - o['counts']['plots']:+d} |")
    lines += ["", "## How the plots join", "",
              "| District | Inside the boxes | On a stand (old, new) | By the 30 m rule (old, new) | Left out (old, new) |",
              "|---|---|---|---|---|"]
    for dist in (*DISTRICTS, "all"):
        oj, nj = old["join"].get(dist), new["join"].get(dist)
        if not oj or not nj:
            continue
        lines.append(f"| {dist} | {nj['inside_the_boxes']} | {oj['on_a_stand']}, {nj['on_a_stand']} | "
                     f"{oj['by_the_30_m_rule']}, {nj['by_the_30_m_rule']} | {oj['left_out']}, {nj['left_out']} |")
    lines += ["", "## Stand counts, from the run records", "",
              "| Run | Superpixels (old, new) | Stands (old, new) | Stand polygons (old, new) | "
              "Stands below the minimum area (old, new) | Superpixel polygons (old, new) | Same-type regions (old, new) |",
              "|---|---|---|---|---|---|---|"]
    for dist in old_counts:
        o, n = old_counts[dist], new_counts[dist]
        lines.append(f"| {dist} | {o['superpixels']}, {n['superpixels']} | {o['stands']}, {n['stands']} | "
                     f"{o['stand_polygons']}, {n['stand_polygons']} | {o['below_min']}, {n['below_min']} | "
                     f"{o['superpixel_polygons']}, {n['superpixel_polygons']} | {o['regions']}, {n['regions']} |")
    lines += ["", "## Labelling ARI by district (primary analysis)", "",
              "| District | " + lo + " (n) | " + ln + " (n) |", "|---|---|---|"]
    op = by_old.get("primary", {}).get("labelling_by_district", {})
    np_ = next(a for a in new["analyses"] if a["analysis"] == "primary")["labelling_by_district"]
    for dist in sorted(set(op) | set(np_)):
        o, n = op.get(dist, {}), np_.get(dist, {})
        lines.append(f"| {dist} | {fmt(o.get('ari'))} ({o.get('n')}) | {fmt(n.get('ari'))} ({n.get('n')}) |")
    lines += ["", "## Inputs: each scores file's stand layers, by SHA-256", "",
              "| Scores file | Run | SHA-256 |", "|---|---|---|"]
    for label, scores in ((lo, old), (ln, new)):
        for run, sha in sorted(scores["inputs_sha256"].items()):
            lines.append(f"| {label} | `{run}` | `{sha}` |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--old-stem", required=True)
    ap.add_argument("--new-stem", required=True)
    ap.add_argument("--old-runs", required=True, help="pattern with {district}")
    ap.add_argument("--new-runs", required=True, help="pattern with {district}")
    ap.add_argument("--old-records", type=Path, required=True)
    ap.add_argument("--new-records", type=Path, required=True)
    ap.add_argument("--old-label", default="old")
    ap.add_argument("--new-label", default="new")
    ap.add_argument("--pair", nargs=2, action="append", default=[], metavar=("OLD_RUN", "NEW_RUN"),
                    help="another run whose stand counts are compared (not scored); repeatable")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    old = json.loads((SCORES / f"{args.old_stem}_scores.json").read_text())
    new = json.loads((SCORES / f"{args.new_stem}_scores.json").read_text())
    oc = {d: run_counts(args.old_records, args.old_runs.format(district=d)) for d in DISTRICTS}
    nc = {d: run_counts(args.new_records, args.new_runs.format(district=d)) for d in DISTRICTS}
    for old_run, new_run in args.pair:
        oc[old_run] = run_counts(args.old_records, old_run)
        nc[old_run] = run_counts(args.new_records, new_run)
    text = compare(old, new, oc, nc, (args.old_label, args.new_label))
    if args.out.exists():
        raise SystemExit(f"{args.out} exists: write a new file, never over an old one")
    args.out.write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())

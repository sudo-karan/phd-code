"""The kept-land chance test, set beside set: observed scores, chance medians, percentiles, Holm p.

    python odisha_script/odisha_keptland_chance_compare.py \\
        --set "hand-crafted (_r9)=keptland_s1desc_r9_chance" \\
        --set "AlphaEarth (_r9)=keptland_alphaearth_r9_chance" \\
        --set "rehearsal, pre-fix stands=keptland_s1desc_chance_rehearsal" \\
        --out odisha_script/keptland_scores/keptland_chance_r9_both_arms.md

Offline; reads the chance test's result files (<stem>.json in odisha_script/keptland_scores/,
written by odisha_keptland_chance.py) and writes one Markdown file of results: for each analysis
(primary, S1, S2) the five scores, each set's observed value, chance median, percentile in the
null and Holm-corrected p side by side, and how many tests pass; check C1 the same way (outside
Holm, so its own p); then what each set ran on. Numbers only: nothing is tested across sets, as
the declaration and its AlphaEarth amendment test no difference between arms
(odisha_script/PHASE_KEPTLAND_PREDECLARED.md). No dates. It never writes over a file.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SCORES = HERE / "keptland_scores"
STATS = (("delin_all", "1 drawing: ARI, all plots"),
         ("delin_multi", "2 drawing: ARI, stands of 2+ plots"),
         ("prec", "3 drawing: same-stand pair precision"),
         ("lab_wmean", "4 labelling: ARI, district mean"),
         ("far_gap", "5 labelling: far-apart gap"))
ANALYSES = ("primary", "S1", "S2")


def num(v: Any, nd: int = 4, sign: bool = True) -> str:
    if v is None:
        return "n/a"
    return f"{v:+.{nd}f}" if sign else f"{v:.{nd}f}"


def cells(row: dict[str, Any], holm: bool = True) -> list[str]:
    if row.get("p") is None:
        return [num(row.get("observed")), "not estimable", "", ""]
    p = row.get("holm_p") if holm else row["p"]
    mark = " (passes)" if holm and row.get("passes") else ""
    return [num(row["observed"]), num(row["null_median"]), f"{row['pctile']:.1f}", f"{p:.3f}{mark}"]


def compare(sets: list[tuple[str, dict[str, Any]]]) -> str:
    labels = [lab for lab, _ in sets]
    head = "| Score | " + " | ".join(f"{lab}: observed | chance median | percentile | Holm p" for lab in labels) + " |"
    rule = "|---|" + "---|---|---|---|" * len(sets)
    lines = ["# The kept-land chance test: " + " beside ".join(labels), "",
             "Written by `odisha_script/odisha_keptland_chance_compare.py` from the chance test's result files",
             "(`odisha_script/odisha_keptland_chance.py`). For each score: the observed value, the median of the",
             "rotation null, the observed value's percentile in it, and the one-sided p after Holm over the five",
             "tests of that analysis and set; a test passes at a Holm p of at most 0.05. The three drawing scores",
             "are read against the unconditional null, the two labelling scores against the conditional one.",
             "Numbers only: nothing is tested across sets.", ""]
    for a in ANALYSES:
        what = sets[0][1]["analyses"][a]["what"]
        lines += [f"## {a}: {what}", "", head, rule]
        for key, label in STATS:
            row = [label]
            for _, res in sets:
                row += cells(res["analyses"][a]["scores"][key])
            lines.append("| " + " | ".join(row) + " |")
        passes = []
        for lab, res in sets:
            sc = res["analyses"][a]["scores"]
            est = [k for k, _ in STATS if "holm_p" in sc[k]]
            passes.append(f"{lab} {sum(bool(sc[k]['passes']) for k in est)} of {len(est)}")
        lines += ["", "Tests that pass after Holm: " + "; ".join(passes) + ".", ""]
    lines += ["## Check C1: the labelling mean without Kendujhar, on both sides", "",
              "Beside the primary's score 4, outside the Holm correction, no pass or fail "
              "(`odisha_script/PHASE_KEPTLAND_AMENDMENT_chance_checks.md`); its p is the one-sided p.", "",
              "| Check | " + " | ".join(f"{lab}: observed | chance median | percentile | p" for lab in labels) + " |",
              rule]
    row = ["C1: labelling ARI, district mean, Kendujhar left out"]
    for _, res in sets:
        row += cells(res["checks"]["C1"], holm=False)
    lines += ["| " + " | ".join(row) + " |", "", "## What each set ran on", "",
              "| Set | Runs | Declared or rehearsal | Realisations | Seed name | Null built | Plots scored "
              "(primary, C1) | Realisations with fewer districts in the labelling mean |",
              "|---|---|---|---|---|---|---|---|"]
    for lab, res in sets:
        dl = res["analyses"]["primary"]["districts_in_labelling_mean"]
        fewer = sum(n for c, n in dl["realisations_by_count"].items() if int(c) < dl["observed"])
        kind = "rehearsal" if res["rehearsal"] else "declared"
        lines.append(f"| {lab} | {', '.join(f'`{r}`' for r in res['runs'])} | {kind} | {res['rotations']} | "
                     f"`{res['arm_seed_name']}` | {'yes' if res['null_built'] else 'NO'} | "
                     f"{res['analyses']['primary']['plots_scored_observed']}, {res['checks']['C1']['plots_scored_observed']} | "
                     f"{fewer} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--set", action="append", required=True, metavar="LABEL=STEM",
                    help="a chance test's result file, <STEM>.json in odisha_script/keptland_scores/; repeatable, in order")
    ap.add_argument("--scores-dir", type=Path, default=SCORES)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    sets = []
    for spec in args.set:
        label, sep, stem = spec.partition("=")
        if not sep or not label or not stem:
            ap.error(f"--set takes LABEL=STEM, got {spec!r}")
        sets.append((label, json.loads((args.scores_dir / f"{stem}.json").read_text())))
    text = compare(sets)
    if args.out.exists():
        raise SystemExit(f"{args.out} exists: write a new file, never over an old one")
    args.out.write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())

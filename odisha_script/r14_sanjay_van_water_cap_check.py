"""Sanjay Van's distance to water capped at 10 km, checked offline on R3's committed table of stands
(round 14), with the check's limit: it caps the stands' means, where the setting caps pixels.

    python odisha_script/r14_sanjay_van_water_cap_check.py
        [--records docs/reproducibility/r14_runs/first_half] [--run sanjay_van_baseline_keptland_r14]
        [--cap-m 10000] [--k 5] [--out-dir odisha_script/keptland_scores]
        [--stem sanjay_van_r14_water_cap_check]

Jaskaran's check of 28 Oct 2026, reproduced as a results file, as he asked (the round 14 record, Done,
k for the 10 ha boxes, and Sanjay Van's distance to water; register
field-r3-sanjay-van-no-distance-to-water-cap). R3's Sanjay Van configs run without
features_static.cap_distance_to_water, and this says what capping the band at --cap-m in the
hand-crafted run's table of stands changes. Offline, from committed files, by the round's own code:
  1. the run's three k elbow records are read and checked against each other, and its elbow is made
     again from its table of stands and preprocessing record and must be its own in every number
     (odisha_script/r14_elbow_report.py's load_run and check_run); the types at --k by the best
     start's nearest centre (fmu.stages.k_elbow.fit_space_sweep) must be its <run>_k_elbow_types.csv's;
  2. the table with each stand's mean of distance_to_water capped at --cap-m (min()) is preprocessed by
     the run's rule and swept by the same code: which bands are dropped as constant, the elbow and the
     knee;
  3. the types of every stand at --k, capped against not: the adjusted Rand index, over every stand
     and over the stands in the fit, and the stands whose type differs once the capped types are
     matched to the others by greatest overlap (scipy's linear_sum_assignment on the counts).
THE LIMIT, which the results file states first: the setting caps each pixel before a stand's mean is
taken; this caps each stand's mean, which is all a committed table allows. A stand with pixels on both
sides of the cap reads below it under the setting and at it here. The band's lower quartile (numpy's
linear rule, as the preprocessing takes it) stays at the cap only while at most floor((n - 1) / 4)
stands read below it; the file gives how many do here, and how many stand means lie just above the
cap. Numbers only. Writes <stem>.md, <stem>.json (results only) and <stem>_run.json (the command, the
date, the git state, the inputs with their SHA-256), and refuses to write over a file that exists.
"""

from __future__ import annotations

import argparse
import datetime
import json
import shlex
import sys
from pathlib import Path
from typing import Any

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
for path in (HERE, REPO / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import r14_elbow_report as R  # noqa: E402, N812

from fmu.stages.k_elbow import fit_space_sweep  # noqa: E402
from fmu.utils import stand_table as st  # noqa: E402

BAND = "distance_to_water"
RECORDS = REPO / "docs" / "reproducibility" / "r14_runs" / "first_half"
RUN = "sanjay_van_baseline_keptland_r14"
STEM = "sanjay_van_r14_water_cap_check"
# Jaskaran's words of 28 Oct 2026, the reason (with the round's check) and the correction he asked to be
# put beside it, as the round 14 record quotes them.
REASON = ("capping at 10 km drops the band as constant (373 of 490 stands at the cap) but changes the type of "
          "only 5 of 490 stands at k = 5 (ARI 0.974), and the knee stays 5. This was checked offline on R3’s "
          "committed stand table, with the round’s own preprocessing and sweep, which reproduce the recorded "
          "elbow exactly.")
CORRECTION = ("the check capped stand means, but the setting caps pixels, so at Sanjay Van the band would likely "
              "be kept with a very small IQR (9 stand means lie between 10,000 and 10,100 m), which the median/IQR "
              "scaling would magnify. So capping there would likely be worse, not just negligible.")


def capped(table: st.StandTable, band: str, cap: float) -> st.StandTable:
    """The table with each stand's value of `band` capped at `cap` (min()), the rest as it is."""
    values = table.values.copy()
    j = table.bands.index(band)
    values[:, j] = np.minimum(values[:, j], cap)
    return st.StandTable(labels=table.labels, bands=list(table.bands), values=values, in_fit=table.in_fit)


def most_below_with_quartile_at_cap(n: int) -> int:
    """The most of n values that can lie below a cap, the rest at it, with the lower quartile (numpy's
    linear rule) still at the cap: the quartile reads the order statistic at floor((n - 1) / 4) and
    the next one."""
    return int(np.floor(0.25 * (n - 1)))


def band_numbers(values: np.ndarray, cap: float) -> dict[str, Any]:
    """The band's stand means against the cap."""
    v = np.asarray(values, dtype=float)
    q25, q50, q75 = st.exact_quartiles(v)
    return {"stands": int(v.size), "smallest_m": round(float(v.min()), 1), "p25_m": round(q25, 1),
            "median_m": round(q50, 1), "p75_m": round(q75, 1), "largest_m": round(float(v.max()), 1),
            "below_cap": int((v < cap).sum()), "at_or_past_cap": int((v >= cap).sum()),
            "from_cap_to_cap_plus_100_m": int(((v >= cap) & (v <= cap + 100)).sum()),
            "from_cap_to_cap_plus_200_m": int(((v >= cap) & (v <= cap + 200)).sum()),
            "most_below_cap_with_lower_quartile_at_cap": most_below_with_quartile_at_cap(int(v.size))}


def changed_after_matching(a: np.ndarray, b: np.ndarray, k: int) -> int:
    """The stands whose type differs once b's types are matched to a's by greatest overlap."""
    from scipy.optimize import linear_sum_assignment

    counts = np.zeros((k, k), dtype=int)
    for x, y in zip(a, b, strict=True):
        counts[int(x), int(y)] += 1
    rows, cols = linear_sum_assignment(-counts)
    return int(len(a) - counts[rows, cols].sum())


def sweep(table: st.StandTable, record: dict[str, Any]) -> tuple[st.Preprocessed, dict[str, Any]]:
    """The table preprocessed by the run's rule, threshold and angle pairs, and the fit's sweep on its
    rows in the fit, every row typed at each k (as the k elbow step does)."""
    pre = st.preprocess(table, rule=str(record["log_rule"]), threshold=float(record["skewness_threshold"]),
                        decomposed=list(record["cyclic_decomposition_log"]))
    return pre, fit_space_sweep(pre.values[table.in_fit], pre.values, k_min=R.K_MIN, k_max=R.K_MAX,
                                seed=R.SEED, n_starts=R.N_STARTS)


def recorded_types(records: Path, run: str, k: int, reads: list[R.Read]) -> np.ndarray:
    """The run's types at k, as its k elbow step wrote them (<run>_k_elbow_types.csv)."""
    data = R.read_input(records, run, f"{run}_k_elbow_types.csv", reads)
    if data is None:
        raise SystemExit(f"{run}: no {run}_k_elbow_types.csv in {records}")
    lines = data.decode("utf-8").strip().split("\n")
    header = lines[0].split(",")
    col = header.index(f"type_k{k}")
    return np.array([int(line.split(",")[col]) for line in lines[1:]], dtype=int)


def markdown(res: dict[str, Any]) -> str:
    b, a, c = res["band_numbers"], res["not_capped"], res["capped"]
    cap = f"{res['cap_m']:,.0f} m"
    lines = [
        "# Sanjay Van, R3: distance to water capped at 10 km, checked on the stands' means", "",
        "Written by `odisha_script/r14_sanjay_van_water_cap_check.py` from R3's committed records of the "
        f"hand-crafted Sanjay Van run, `{res['run']}` (`docs/reproducibility/r14_runs/first_half/`), by the "
        "round's own code. Jaskaran's check of 28 Oct 2026, reproduced as he asked: R3 runs without the cap "
        "(`features_static.cap_distance_to_water` off, its default), and this says what capping the band "
        "would change. Numbers only.", "",
        "**The limit of this check.** It caps each stand's mean of `distance_to_water`, which is all a "
        "committed table of stands allows. The setting caps each pixel before a stand's mean is taken, so a "
        "stand with pixels on both sides of the cap reads below it under the setting and at it here. The "
        f"band's lower quartile stays at the cap only while at most "
        f"{b['most_below_cap_with_lower_quartile_at_cap']} of the {b['stands']} stands read below it: "
        f"{b['below_cap']} do here, and {b['from_cap_to_cap_plus_100_m']} stand means lie from {cap} to "
        f"{res['cap_m'] + 100:,.0f} m ({b['from_cap_to_cap_plus_200_m']} to {res['cap_m'] + 200:,.0f} m). "
        "Jaskaran's correction, 28 Oct 2026, beside his reason: \"" + CORRECTION + "\" So this check does not "
        "show what the setting would do at Sanjay Van; it shows what capping the stands' means does.", "",
        "His reason for no cap in R3, as he gave it: \"" + REASON + "\"", "",
        "## The run's elbow made again", "",
        f"- Its elbow made again from its table of stands and preprocessing record "
        f"(`odisha_script/r14_elbow_report.py`'s check): {res['run_elbow_made_again']}.",
        f"- Its types at k = {res['k']} by the best start's nearest centre: {res['types_as_recorded']} of "
        f"{b['stands']} stands as in its `_k_elbow_types.csv`.", "",
        "## `distance_to_water` in the table: each stand's mean, m", "",
        "| | |", "|---|---:|",
        f"| stands | {b['stands']:,} |",
        f"| smallest | {b['smallest_m']:,} |", f"| 25th percentile | {b['p25_m']:,} |",
        f"| median | {b['median_m']:,} |", f"| 75th percentile | {b['p75_m']:,} |",
        f"| largest | {b['largest_m']:,} |",
        f"| below {cap} | {b['below_cap']:,} |", f"| at or past {cap} | {b['at_or_past_cap']:,} |",
        f"| from {cap} to {res['cap_m'] + 100:,.0f} m | {b['from_cap_to_cap_plus_100_m']:,} |",
        f"| from {cap} to {res['cap_m'] + 200:,.0f} m | {b['from_cap_to_cap_plus_200_m']:,} |",
        f"| the most below {cap} with the lower quartile still at it | "
        f"{b['most_below_cap_with_lower_quartile_at_cap']:,} |", "",
        "## The stands' means capped, against not capped", "",
        "| | not capped (the run's) | capped |", "|---|---:|---:|",
        f"| bands dropped as constant | {', '.join(a['dropped_constant_bands']) or 'none'} | "
        f"{', '.join(c['dropped_constant_bands']) or 'none'} |",
        f"| bands in the fit | {a['n_active_bands']} | {c['n_active_bands']} |",
        f"| knee | {a['knee']} | {c['knee']} |", "",
        f"At k = {res['k']}, the types of every stand, capped against not: adjusted Rand index "
        f"{res['ari_every_stand']:.4f} over the {b['stands']} stands ({res['ari_stands_in_fit']:.4f} over the "
        f"{res['stands_in_fit']} in the fit); {res['stands_whose_type_differs']} of the {b['stands']} stands "
        "change type once the capped types are matched to the others by greatest overlap.", "",
        "| k | sum of squares, not capped | median ARI | sum of squares, capped | median ARI |",
        "|---:|---:|---:|---:|---:|"]
    lines += [f"| {k} | {w0:,.2f} | {m0:.4f} | {w1:,.2f} | {m1:.4f} |" for k, w0, m0, w1, m1 in
              zip(a["ks"], a["wcss"], a["ari_median"], c["wcss"], c["ari_median"], strict=True)]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--records", type=Path, default=RECORDS)
    ap.add_argument("--run", default=RUN)
    ap.add_argument("--cap-m", type=float, default=10_000.0)
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--out-dir", type=Path, default=HERE / "keptland_scores")
    ap.add_argument("--stem", default=STEM)
    args = ap.parse_args(argv)
    started = R.git_block()
    outs = [args.out_dir / f"{args.stem}{s}" for s in (".md", ".json", "_run.json")]
    there = [str(p) for p in outs if p.exists()]
    if there:
        raise SystemExit(f"refusing to write over {there}")
    env = R.environment()
    reads: list[R.Read] = []
    run = R.load_run(args.records, args.run, reads)
    if run is None:
        raise SystemExit(f"{args.run}: no k elbow records in {args.records}")
    if BAND not in run.table.bands:
        raise SystemExit(f"{args.run}: no {BAND} in its table of stands")
    R.check_run(run)  # stops unless the elbow made again is the run's own in every number
    pre0, s0 = sweep(run.table, run.record)
    if s0["ks"] != run.elbow.ks or s0["inertia"] != run.elbow.wcss:
        raise SystemExit(f"{args.run}: the sweep here is not the run's elbow")
    i = s0["ks"].index(args.k)
    types0 = np.array(s0["types"][i], dtype=int)
    same = int((types0 == recorded_types(args.records, args.run, args.k, reads)).sum())
    if same != len(types0):
        raise SystemExit(f"{args.run}: the types at k = {args.k} here differ from its _k_elbow_types.csv "
                         f"for {len(types0) - same} stands")
    pre1, s1 = sweep(capped(run.table, BAND, args.cap_m), run.record)
    types1 = np.array(s1["types"][s1["ks"].index(args.k)], dtype=int)
    from sklearn.metrics import adjusted_rand_score

    fit = run.table.in_fit
    side = {name: {"dropped_constant_bands": list(pre.record["dropped_constant_bands"]),
                   "n_active_bands": len(pre.bands), "ks": list(s["ks"]), "wcss": list(s["inertia"]),
                   "ari_median": list(s["ari_median"]), "knee": s["elbow_k"]}
            for name, pre, s in (("not_capped", pre0, s0), ("capped", pre1, s1))}
    res = {"run": args.run, "band": BAND, "cap_m": args.cap_m, "k": args.k,
           "run_elbow_made_again": "the same in every number",
           "types_as_recorded": same,
           "band_numbers": band_numbers(run.table.values[:, run.table.bands.index(BAND)], args.cap_m),
           **side,
           "ari_every_stand": round(float(adjusted_rand_score(types0, types1)), 4),
           "ari_stands_in_fit": round(float(adjusted_rand_score(types0[fit], types1[fit])), 4),
           "stands_in_fit": int(fit.sum()),
           "stands_whose_type_differs": changed_after_matching(types0, types1, args.k)}
    args.out_dir.mkdir(parents=True, exist_ok=True)
    outs[0].write_text(markdown(res))
    outs[1].write_text(json.dumps(res, indent=1) + "\n")
    record = {"result_files": [outs[0].name, outs[1].name],
              "command_line": "python " + " ".join(shlex.quote(a) for a in
                                                   ["odisha_script/r14_sanjay_van_water_cap_check.py",
                                                    *(argv if argv is not None else sys.argv[1:])]),
              "date": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
              "git": started, "git_at_end": R.git_block(now=True),
              "environment": env["environment"], "packages": env["packages"],
              "inputs": [{"run": r.run, "file": r.file, "path": R.shown(r.path), "off_git": r.off_git,
                          "bytes": r.n_bytes, "sha256": r.sha256} for r in reads]}
    outs[2].write_text(json.dumps(record, indent=1) + "\n")
    print(f"wrote {', '.join(str(p) for p in outs)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

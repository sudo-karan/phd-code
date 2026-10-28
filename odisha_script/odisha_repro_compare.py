"""Compare a from-scratch re-run of one Odisha arm with the committed outputs. Offline.

    python odisha_script/odisha_repro_compare.py --arm odisha_v120_3ha \\
        --rerun-dir FOLDER_WITH_THE_REPRO_FILES --out-dir A_NEW_FOLDER [--checks] [--expect-identical]

A re-run reads its cached Earth Engine assets back unless the config is copied under a new
name (CLAUDE.md, "Earth Engine"). The copies are named <config>_repro, and
odisha_phase2_2_run_pipeline.py writes their outputs as <config>_repro_stands_merged.geojson,
_stands_snic.geojson, _stands_dissolved.geojson, _raster_at_plots.csv and _run.json. This
script takes the folder holding those files and, for the four districts of one arm, MEASURES
how the re-run differs from what is committed. It assumes neither that nothing changed nor
that the change is small.

WHAT IT DOES, per arm
  (a) Stands. scripts/compare_stand_runs.py on the committed
      odisha_script/phase2_vectors/<config>_stands_merged.geojson against the re-run's file,
      and the same for stands_snic: counts, areas, identical outlines, area-weighted
      intersection over union in both directions, stand types. The definitions are at the
      top of scripts/compare_stand_runs.py.
  (b) Run records. <config>_run.json old against new: cache fingerprint (the copy has the
      same content, so it must be equal: if it is not, the config changed since the committed
      run), polygon and stand counts, every merge diagnostic. What differs is listed.
  (c) Plots. The plots are joined to the NEW stands by running odisha_phase2_3_join.py itself
      (--set districts --arms <arm>), on a temporary folder that presents the re-run's files
      under the names that script looks for. The new plot table is written into --out-dir and
      compared with the committed one.
  (d) Scores. odisha_phase3_1_pairwise_score.py itself is run on the new plot table with the
      options of the "Reproducing" section of PHASE3_STATUS.md for that arm:
          10 hectare stands   --arm v120
          3 hectare stands    --arm v120_3ha --tag _3ha
      plus --joined and --out-dir, which only say where to read and write. Nothing is
      re-implemented and no setting is chosen here. By default the primary analysis only;
      --checks also runs the three declared checks (S1 --exclude-types 0, S2 the four-type
      field typology, S3 the all-rows typology), each against its committed file.
      The AlphaEarth arm has no Phase 3 score: Phase 3 scored the 10 and the 3 hectare
      stands only. For it (a) to (c) are done and (d) and (e) say so.
  (e) Scores side by side: every number of the committed score file beside the new one, and
      the difference.

WHAT IT WRITES, all in --out-dir
  odisha_repro_compare_<arm>.txt           the results file: all of the above
  odisha_repro_compare_<arm>_manifest.json which files were compared (sha256), from which git
                                           commit, with which options
  phase2_plots_joined_districts.csv        the new plot table        (written by the join)
  odisha_phase2_3_results_districts.txt    the join's own report     (written by the join)
  odisha_phase3_1_score_<...>.txt          the new score file(s)     (written by the scoring)
  per_stand/<config>_<layer>.csv           one row per stand: best match in the other run, IoU

It never writes anywhere else. A second run for the same arm into the same folder first removes
the files listed above that the earlier run left, so that the folder never holds a plot table
or a score file the new results file does not describe. It refuses an --out-dir that is odisha_script/ itself, that
lies in odisha_script/phase2_vectors/ or odisha_script/phase3_3ha/, that holds any file
committed to git (however the folder name is spelled in upper and lower case), that is the
re-run folder, or that already holds another arm's results
(two arms write a plot table of the same name). The results file holds results only: no
dates, no run times, no machine names.

Exit status: 0 when the comparison ran, whatever it found. With --expect-identical, 1 unless
the re-run is identical to the committed outputs in every respect measured (used to check
this script on copies of the committed files). 2 when it could not run.

No Earth Engine. Run from the repo root.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import adjusted_rand_score

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "scripts"))
import compare_stand_runs as csr  # noqa: E402

JOIN_SCRIPT = HERE / "odisha_phase2_3_join.py"
SCORE_SCRIPT = HERE / "odisha_phase3_1_pairwise_score.py"
COMMITTED_VECTORS = HERE / "phase2_vectors"
DISTRICTS = ["angul", "dhenkanal", "kendujhar", "koraput"]  # as odisha_phase2_3_join.DISTRICTS
FILE_SUFFIXES = ["stands_merged.geojson", "stands_snic.geojson", "stands_dissolved.geojson",
                 "raster_at_plots.csv", "run.json"]
# layer -> (property holding the stand id, as odisha_phase2_3_join.LAYERS)
COMPARED_LAYERS = {"stands_merged": "stand_lbl", "stands_snic": "snic_label"}
TYPE_FIELD = "cluster_id"
JOINED_NAME = "phase2_plots_joined_districts.csv"
JOIN_RESULTS_NAME = "odisha_phase2_3_results_districts.txt"
PROTECTED = [COMMITTED_VECTORS, HERE / "phase3_3ha", HERE / "phase3_before_regroup"]

# One entry per arm: the pipeline config prefix, the arm's short name in the join and the
# scoring scripts, and where its committed plot table and scores are. "score_args" are the
# options the "Reproducing" section of PHASE3_STATUS.md gives for the arm; None where Phase 3
# did not score the arm.
ARMS: dict[str, dict[str, Any]] = {
    "odisha_v120_handcrafted": {
        "short": "v120", "what": "10 hectare stands",
        "committed_joined": HERE / JOINED_NAME,
        "score_args": ["--arm", "v120"], "tag": "",
    },
    "odisha_v120_3ha": {
        "short": "v120_3ha", "what": "3 hectare stands",
        "committed_joined": HERE / "phase3_3ha" / JOINED_NAME,
        "score_args": ["--arm", "v120_3ha", "--tag", "_3ha"], "tag": "_3ha",
    },
    "odisha_alphaearth": {
        "short": "alphaearth", "what": "AlphaEarth stands",
        "committed_joined": HERE / JOINED_NAME,
        "score_args": None, "tag": "",
    },
}
# The primary analysis and the three checks of PHASE3_PREDECLARED.md, as the "Reproducing"
# section runs them: (name, extra options, the suffix the scoring script adds to its file).
ANALYSES = [
    ("primary", [], ""),
    ("check S1 (field type 0 left out)", ["--exclude-types", "0"], "_excl0"),
    ("check S2 (four field types)",
     ["--field-types", str(HERE / "odisha_phase3_0_field_types_k4.csv")], "_ft-k4"),
    ("check S3 (all-rows field types)",
     ["--field-types", str(HERE / "odisha_phase3_0_field_types_allrows.csv")], "_ft-allrows"),
]

_lines: list[str] = []


def say(s: str = "") -> None:
    print(s)
    _lines.append(s)


def rule(title: str) -> None:
    say("")
    say("=" * 100)
    say(title)
    say("=" * 100)


def shown(path: Path) -> str:
    """A path as it is written in the results file: relative to the repository when it is in
    it, otherwise the file or folder name alone (no machine-specific folders)."""
    path = Path(path).resolve()
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return path.name


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


# --------------------------------------------------------------------------- where to write
def _same_folder(a: Path, b: Path) -> bool:
    """True when a and b are one folder on disk, however each is spelled. Spellings are not
    compared: on a file system that ignores case (macOS by default) ODISHA_SCRIPT and
    odisha_script are the same folder, and Path.resolve() leaves the case as typed."""
    try:
        return a.exists() and b.exists() and os.path.samefile(a, b)
    except OSError:
        return False


def _is_or_inside(path: Path, folder: Path) -> bool:
    """True when path is folder or lies below it (path itself need not exist yet)."""
    return any(_same_folder(p, folder) for p in (path, *path.parents))


def check_out_dir(out_dir: Path, rerun_dir: Path, arm: str) -> None:
    """Stop unless out_dir is a place where nothing committed can be overwritten."""
    out = out_dir.resolve()
    if _is_or_inside(HERE, out):  # odisha_script/ itself, the repository, or a folder above it
        raise SystemExit(f"REFUSING --out-dir {out}: the committed score files and plot table are in "
                         f"{HERE}, and this script writes files of the same names. Name a new folder.")
    for prot in PROTECTED:
        if _is_or_inside(out, prot):
            raise SystemExit(f"REFUSING --out-dir {out}: it is inside {shown(prot)}/, which holds committed "
                             "results. Name a new folder.")
    if out == rerun_dir.resolve() or _same_folder(out, rerun_dir):
        raise SystemExit("REFUSING --out-dir: it is the re-run folder. Outputs go to a folder of their own.")
    csr.refuse_committed_folder(out, what="comparison")
    if out.exists():
        other = [p.name for p in out.glob("odisha_repro_compare_*.txt")
                 if p.name != f"odisha_repro_compare_{arm}.txt"]
        if other:
            raise SystemExit(f"REFUSING --out-dir {out}: it holds another arm's results ({other[0]}). Two arms "
                             f"write a plot table of the same name ({JOINED_NAME}); use one folder per arm.")


# --------------------------------------------------------------------------- (b) run records
# Differ by construction between any two runs, so they are not evidence of anything:
RUN_KEYS_NOT_COMPARED = ("config", "run_dir", "drive_exports", "git")


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k in value:
            out.update(_flatten(value[k], f"{prefix}.{k}" if prefix else str(k)))
        return out
    return {prefix: value}


def _same(a: Any, b: Any) -> bool:
    if isinstance(a, float) and isinstance(b, float) and a != a and b != b:
        return True
    return bool(a == b)


def compare_run_records(old: dict, new: dict) -> dict[str, Any]:
    """What differs between two <config>_run.json records."""
    res: dict[str, Any] = {"fingerprint_old": old.get("fingerprint"), "fingerprint_new": new.get("fingerprint")}
    flat_old = _flatten({k: v for k, v in old.items()
                         if k not in RUN_KEYS_NOT_COMPARED and k != "stand_attributes"})
    flat_new = _flatten({k: v for k, v in new.items()
                         if k not in RUN_KEYS_NOT_COMPARED and k != "stand_attributes"})
    keys = list(flat_old) + [k for k in flat_new if k not in flat_old]
    res["n_compared"] = len(keys)
    res["differences"] = [(k, flat_old.get(k, "(absent)"), flat_new.get(k, "(absent)")) for k in keys
                          if not _same(flat_old.get(k, "(absent)"), flat_new.get(k, "(absent)"))]
    sa_old, sa_new = old.get("stand_attributes") or {}, new.get("stand_attributes") or {}

    def total(sa: dict, key: str) -> float:
        return float(sum((v or {}).get(key) or 0 for v in sa.values()))

    common = set(sa_old) & set(sa_new)
    res["stand_attributes"] = {
        "n_old": len(sa_old), "n_new": len(sa_new),
        "pixels_old": total(sa_old, "n_pixels"), "pixels_new": total(sa_new, "n_pixels"),
        "area_old": total(sa_old, "area_ha"), "area_new": total(sa_new, "area_ha"),
        "ids_in_both": len(common),
        "ids_in_both_identical": sum(sa_old[k] == sa_new[k] for k in common),
    }
    git = new.get("git") or {}
    res["git_new"] = {"commit": git.get("commit"), "dirty": git.get("dirty")} if git else None
    return res


def report_run_records(res: dict[str, Any]) -> bool:
    """Print the comparison; True when nothing compared differs."""
    fo, fn = res["fingerprint_old"], res["fingerprint_new"]
    say(f"    cache fingerprint: committed {fo}, re-run {fn}: "
        + ("the same, so the re-run used the same cache-relevant settings as the committed run "
           "(the fingerprint covers the config, not the version of the code)"
           if fo == fn else
           "DIFFERENT, so the config was not the same as for the committed run and the two runs "
           "are not a like-for-like pair"))
    g = res["git_new"]
    say("    the re-run's record names git commit "
        + (f"{g['commit']} (uncommitted changes to tracked files, or since round 14 untracked code "
           f"under src/, scripts/, odisha_script/ or configs/: {g['dirty']})" if g
           else "nothing (the record has no git entry)"))
    diffs = res["differences"]
    say(f"    {res['n_compared']} recorded values compared, {len(diffs)} differ"
        + (":" if diffs else "."))
    for key, a, b in diffs:
        say(f"      {key}: {_short(a)} -> {_short(b)}")
    sa = res["stand_attributes"]
    say(f"    stand attributes: {sa['n_old']} stands -> {sa['n_new']}; pixels {sa['pixels_old']:,.0f} -> "
        f"{sa['pixels_new']:,.0f}; area {sa['area_old']:,.2f} -> {sa['area_new']:,.2f} ha; "
        f"{sa['ids_in_both_identical']} of the {sa['ids_in_both']} stand numbers present in both carry "
        "identical attributes")
    say(f"    not compared, because they differ between any two runs: {', '.join(RUN_KEYS_NOT_COMPARED)}")
    return (not diffs and sa["n_old"] == sa["n_new"] == sa["ids_in_both"] == sa["ids_in_both_identical"])


def _short(value: Any, width: int = 110) -> str:
    text = json.dumps(value, default=str) if not isinstance(value, str) else value
    return text if len(text) <= width else text[: width - 3] + "..."


# --------------------------------------------------------------------------- (c) plot tables
def compare_plot_tables(old: pd.DataFrame, new: pd.DataFrame, short: str) -> dict[str, Any]:
    """The committed plot table against the new one, on the columns both have."""
    res: dict[str, Any] = {"rows_old": len(old), "rows_new": len(new)}
    res["plots_only_old"] = sorted(set(old.plot_key) - set(new.plot_key))
    res["plots_only_new"] = sorted(set(new.plot_key) - set(old.plot_key))
    both = old.merge(new, on="plot_key", suffixes=("__old", "__new"), validate="1:1")
    shared = [c for c in old.columns if c in new.columns and c != "plot_key"]
    res["columns_shared"] = len(shared) + 1
    res["columns_only_old"] = [c for c in old.columns if c not in new.columns]
    res["columns_only_new"] = [c for c in new.columns if c not in old.columns]
    arm_cols = [c for c in shared if c.startswith(f"{short}_")]
    res["arm_columns"] = arm_cols
    differing: dict[str, dict[str, Any]] = {}
    for c in shared:
        a, b = both[f"{c}__old"], both[f"{c}__new"]
        ne = ~((a == b) | (a.isna() & b.isna()))
        if ne.any():
            entry: dict[str, Any] = {"plots": int(ne.sum())}
            if pd.api.types.is_numeric_dtype(a) and pd.api.types.is_numeric_dtype(b):
                # an infinite value on one side only is a difference and is shown as "inf";
                # infinite on both sides is no difference (inf - inf is NaN and drops out)
                d = (a - b).abs()
                entry["max_abs_diff"] = float(d.max()) if d.notna().any() else float("nan")
                entry["one_side_missing"] = int((a.isna() ^ b.isna()).sum())
                entry["one_side_infinite"] = int((np.isinf(a) ^ np.isinf(b)).sum())
            differing[c] = entry
    res["differing"] = differing
    res["field_columns_differing"] = [c for c in differing if c not in arm_cols]
    res["identical_on_shared_columns"] = (not differing and not res["plots_only_old"]
                                          and not res["plots_only_new"])

    # Stand numbers are labels: a re-run may number the same stand differently, so a changed
    # number is not by itself a changed stand. What matters is which plots share a stand.
    for layer in ("merged", "snic"):
        idc = f"{short}_{layer}_id"
        if f"{idc}__old" not in both.columns:
            continue
        a, b = both[f"{idc}__old"], both[f"{idc}__new"]
        has_a, has_b = a.notna(), b.notna()
        m = both[has_a & has_b]
        dist = both["district__old"] if "district__old" in both.columns else both["district"]
        dist = dist[has_a & has_b].astype(str)
        ka = (dist + ":" + m[f"{idc}__old"].round().astype(int).astype(str)).to_numpy()
        kb = (dist + ":" + m[f"{idc}__new"].round().astype(int).astype(str)).to_numpy()
        ii, jj = np.triu_indices(len(m), k=1)
        pa, pb = ka[ii] == ka[jj], kb[ii] == kb[jj]
        res[f"{layer}_partition"] = {
            "with_stand_old": int(has_a.sum()), "with_stand_new": int(has_b.sum()),
            "with_stand_both": int((has_a & has_b).sum()),
            "only_old": int((has_a & ~has_b).sum()), "only_new": int((~has_a & has_b).sum()),
            "stands_old": int(len(set(ka))), "stands_new": int(len(set(kb))),
            "pairs_together_old": int(pa.sum()), "pairs_together_new": int(pb.sum()),
            "pairs_together_both": int((pa & pb).sum()),
            "ari": float(adjusted_rand_score(ka, kb)) if len(m) >= 2 else float("nan"),
        }
    tc = f"{short}_merged_cluster"
    if f"{tc}__old" in both.columns:
        a, b = both[f"{tc}__old"], both[f"{tc}__new"]
        ok = a.notna() & b.notna()
        dist = (both["district__old"] if "district__old" in both.columns else both["district"]).astype(str)
        per = []
        for name, g in both[ok].groupby(dist[ok]):
            ga, gb = np.rint(g[f"{tc}__old"]), np.rint(g[f"{tc}__new"])
            per.append((str(name), len(g), float(adjusted_rand_score(ga, gb)) if len(g) >= 2 else float("nan"),
                        int((ga == gb).sum())))
        res["type_agreement"] = {"typed_old": int(a.notna().sum()), "typed_new": int(b.notna().sum()),
                                 "typed_both": int(ok.sum()), "per_district": per}
    return res


def report_plot_tables(res: dict[str, Any], short: str) -> None:
    say(f"    plots: {res['rows_old']} committed, {res['rows_new']} new"
        + (f"; only in the committed table {len(res['plots_only_old'])}, only in the new "
           f"{len(res['plots_only_new'])}" if res["plots_only_old"] or res["plots_only_new"] else
           "; the same plots in both"))
    say(f"    columns in both: {res['columns_shared']}"
        + (f"; only in the committed table: {len(res['columns_only_old'])} (the other arms it was joined "
           "with; this run joins one arm)" if res["columns_only_old"] else "")
        + (f"; only in the new table: {res['columns_only_new']}" if res["columns_only_new"] else ""))
    if res["identical_on_shared_columns"]:
        say("    every value in the columns both tables have is IDENTICAL")
    else:
        say(f"    columns with at least one differing plot: {len(res['differing'])} of {res['columns_shared']}"
            f" (of them field-data columns, which no re-run should change: {len(res['field_columns_differing'])}"
            f"{' ' + str(res['field_columns_differing']) if res['field_columns_differing'] else ''})")
        say(f"      {'column':<28}{'plots differing':>16}{'one side empty':>16}{'largest |difference|':>22}")
        for c, e in res["differing"].items():
            mx = e.get("max_abs_diff")
            say(f"      {c:<28}{e['plots']:>16}{e.get('one_side_missing', ''):>16}"
                f"{'' if mx is None else ('n/a' if mx != mx else f'{mx:.6g}'):>22}")
        n_inf = sum(e.get("one_side_infinite", 0) for e in res["differing"].values())
        if n_inf:
            say(f"      (inf: the value is infinite in one table and finite in the other, for {n_inf} plot "
                "value(s) in all; the largest finite difference is then not shown)")
        say("      (a stand number is a label: a re-run may give the same stand another number, so a")
        say("       differing _id column alone does not mean a plot changed stand; see the lines below)")
    for layer in ("merged", "snic"):
        p = res.get(f"{layer}_partition")
        if not p:
            continue
        say(f"    {short} {layer}: plots with a stand {p['with_stand_old']} -> {p['with_stand_new']} "
            f"({p['with_stand_both']} in both, {p['only_old']} lost theirs, {p['only_new']} gained one); "
            f"stands holding them {p['stands_old']} -> {p['stands_new']}")
        say(f"      pairs of plots sharing a stand: {p['pairs_together_old']} committed, "
            f"{p['pairs_together_new']} new, {p['pairs_together_both']} in both; adjusted Rand index of the "
            f"old grouping of plots against the new {p['ari']:.4f} (1 = the same grouping)")
    t = res.get("type_agreement")
    if t:
        say(f"    {short} stand type of the plot's stand: plots with a type {t['typed_old']} -> {t['typed_new']} "
            f"({t['typed_both']} in both). Type numbers are refitted per run and per district, so they are")
        say("      compared as groupings (adjusted Rand index, 1 = the same grouping), with the count of")
        say("      plots keeping the same number beside it:")
        for name, n, ari, same in t["per_district"]:
            say(f"        {name:<11} n={n:>4}   adjusted Rand index {ari:.4f}   same type number {same} of {n}")


# --------------------------------------------------------------------------- (e) score files
_NUM = r"[+-]?(?:\d[\d,]*\.?\d*|nan)"


def parse_score_file(text: str) -> list[tuple[str, str]]:
    """Every number of an odisha_phase3_1 score file, in order, as (what it is, as printed)."""
    out: list[tuple[str, str]] = []
    section = ""
    lines = text.splitlines()
    block = ""
    for k, line in enumerate(lines):
        if line.startswith("A. "):
            section = "A delineation"
        elif line.startswith("B. "):
            section = "B labelling"
        if m := re.match(r"\s+plots with a stand: (\d+)", line):
            out.append(("plots with a stand", m[1]))
        elif m := re.match(r"\s+stands holding them: (\d+)\s+multi-plot stands: (\d+) holding (\d+) plots", line):
            out += [("stands holding them", m[1]), ("multi-plot stands", m[2]),
                    ("plots in multi-plot stands", m[3])]
        elif m := re.match(r"\s+EXCLUDED field type\(s\): .*-> (\d+) of (\d+) plots", line):
            out.append(("plots dropped by the exclusion", m[1]))
        elif m := re.match(rf"\s+(\w+)\s+n=\s*(\d+)\s+ARI ({_NUM})", line):
            out += [(f"{section}, {m[1]}: plots", m[2]), (f"{section}, {m[1]}: ARI", m[3])]
        elif m := re.match(r"\s+pairs ([\d,]+)\s+field-alike ([\d.]+)%\s+grouped-together ([\d.]+)%", line):
            block = f"{section}, {lines[k - 1].strip().split('  (')[0]}"
            out += [(f"{block}: pairs", m[1]), (f"{block}: field-alike %", m[2]),
                    (f"{block}: grouped-together %", m[3])]
        elif m := re.match(r"\s+field alike\s+([\d,]+)\s+([\d,]+)\s*$", line):
            out += [(f"{block}: alike, same group", m[1]), (f"{block}: alike, different", m[2])]
        elif m := re.match(r"\s+field differs\s+([\d,]+)\s+([\d,]+)\s*$", line):
            out += [(f"{block}: differs, same group", m[1]), (f"{block}: differs, different", m[2])]
        elif m := re.match(rf"\s+accuracy ({_NUM})\s+precision ({_NUM})\s+recall ({_NUM})\s+F1 ({_NUM})", line):
            out += [(f"{block}: accuracy", m[1]), (f"{block}: precision", m[2]),
                    (f"{block}: recall", m[3]), (f"{block}: F1", m[4])]
        elif (m := re.match(rf"\s+>>> ARI ({_NUM}|n/a)", line)) and m[1] != "n/a":
            out.append((f"{block}: ARI", m[1]))
    return out


def _value(text: str) -> float:
    return float(text.replace(",", ""))


def report_scores(old_text: str, new_text: str) -> tuple[bool, int]:
    """Print committed and new side by side. Returns (files identical, numbers that differ)."""
    old, new = parse_score_file(old_text), parse_score_file(new_text)
    keys = [k for k, _ in old] + [k for k, _ in new if k not in dict(old)]
    do, dn = dict(old), dict(new)
    n_diff = 0
    say(f"    {'':<3}{'quantity':<76}{'committed':>11}{'new':>11}{'new - committed':>17}")
    for k in keys:
        a, b = do.get(k), dn.get(k)
        if a is None or b is None:
            diff, mark = "(absent in one)", "*"
        else:
            d = _value(b) - _value(a)
            nd = max(len(x.split(".")[1]) if "." in x else 0 for x in (a, b))
            same = a == b or (d != d and _value(a) != _value(a) and _value(b) != _value(b))
            diff, mark = ("0" if same else f"{d:+,.{nd}f}"), (" " if same else "*")
        n_diff += mark == "*"
        head = ">>>" if k.endswith(": ARI") else ""
        say(f"    {head:<3}{k:<76}{a or '':>11}{b or '':>11}{diff:>17} {mark}")
    say(f"    {len(keys)} numbers read from the score files; {n_diff} differ (marked *). "
        "Lines marked >>> are the headline scores (ARI).")
    identical = old_text == new_text
    say("    the new score file is " + ("IDENTICAL to the committed one, byte for byte"
                                        if identical else "NOT identical to the committed one"))
    return identical, n_diff


# --------------------------------------------------------------------------- running Phase 2/3
def stage_rerun(rerun_dir: Path, arm: str, suffix: str, districts: list[str], into: Path) -> None:
    """Present the re-run's files under the names odisha_phase2_3_join.py looks for:
    <config><suffix>_<file> becomes <config>_<file>. Links, or copies where links are refused."""
    for d in districts:
        for tail in FILE_SUFFIXES:
            src = (rerun_dir / f"{arm}_{d}{suffix}_{tail}").resolve()
            if not src.exists():
                continue  # run.json and raster_at_plots.csv are optional for the join
            dst = into / f"{arm}_{d}_{tail}"
            try:
                os.symlink(src, dst)
            except OSError:
                shutil.copyfile(src, dst)


def run_script(script: Path, args: list[str]) -> subprocess.CompletedProcess:
    """Run a Phase 2 or Phase 3 script exactly as from the command line, from the repo root."""
    return subprocess.run([sys.executable, str(script), *args], cwd=REPO, capture_output=True, text=True)


def git_of_this_checkout() -> dict[str, Any]:
    def git(*args: str) -> str | None:
        try:
            got = subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True, check=False)
        except OSError:
            return None
        return got.stdout if got.returncode == 0 else None

    commit = git("rev-parse", "HEAD")
    status = git("status", "--porcelain", "--untracked-files=no")
    return {"commit": commit.strip() if commit else None,
            "dirty": None if status is None else bool(status.strip()),
            "modified": [] if not status else sorted(ln[3:] for ln in status.splitlines())}


def own_output_names(arm: str, short: str, tag: str) -> list[str]:
    """Every file this script, the join and the scoring can write for one arm, by name."""
    return [f"odisha_repro_compare_{arm}.txt", f"odisha_repro_compare_{arm}_manifest.json",
            JOINED_NAME, JOIN_RESULTS_NAME,
            *(f"odisha_phase3_1_score_{short}_merged_districts{tag}{sens}.txt" for _, _, sens in ANALYSES)]


def clear_earlier_outputs(out_dir: Path, arm: str, short: str, tag: str) -> list[str]:
    """Remove what an earlier run of this script for the same arm left in out_dir, so that the
    folder never holds a plot table or a score file that the new results file does not describe
    (an earlier complete run followed by an incomplete one, or by one without --checks).
    Only files this script writes are touched, and only after check_out_dir has established
    that nothing in out_dir is committed. Returns the names removed."""
    gone = []
    for name in own_output_names(arm, short, tag):
        if (out_dir / name).is_file() or (out_dir / name).is_symlink():
            (out_dir / name).unlink()
            gone.append(name)
    for p in sorted((out_dir / "per_stand").glob(f"{arm}_*.csv")):
        p.unlink()
        gone.append(f"per_stand/{p.name}")
    for p in out_dir.glob("staged_vectors_*"):  # the temporary folder of a run that was killed
        if p.is_dir() and not p.is_symlink():
            shutil.rmtree(p)
    return gone


# --------------------------------------------------------------------------- main
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0],
                                 epilog="See the top of this file for what is compared and written.")
    ap.add_argument("--arm", required=True,
                    help=f"one of {', '.join(ARMS)} (or the short name: "
                         f"{', '.join(a['short'] for a in ARMS.values())})")
    ap.add_argument("--rerun-dir", type=Path, required=True,
                    help="folder holding the re-run's <config>_repro_* files")
    ap.add_argument("--out-dir", type=Path, required=True,
                    help="a new folder for everything this script writes; one folder per arm")
    ap.add_argument("--suffix", default="_repro",
                    help="what the re-run's config names end in (default _repro)")
    ap.add_argument("--checks", action="store_true",
                    help="also run the three declared checks S1, S2, S3 (default: primary analysis only)")
    ap.add_argument("--expect-identical", action="store_true",
                    help="exit 1 unless the re-run equals the committed outputs in everything measured")
    args = ap.parse_args(argv)

    by_short = {a["short"]: name for name, a in ARMS.items()}
    arm = by_short.get(args.arm, args.arm)
    if arm not in ARMS:
        raise SystemExit(f"--arm: unknown {args.arm!r}; known: {sorted(ARMS)} or {sorted(by_short)}")
    spec = ARMS[arm]
    short = spec["short"]
    rerun_dir = args.rerun_dir.resolve()
    if not rerun_dir.is_dir():
        raise SystemExit(f"--rerun-dir {args.rerun_dir} is not a folder")
    out_dir = args.out_dir.resolve()
    check_out_dir(out_dir, rerun_dir, arm)
    out_dir.mkdir(parents=True, exist_ok=True)
    replaced = clear_earlier_outputs(out_dir, arm, short, spec["tag"])
    if replaced:  # to the terminal only: the results file describes this run, not the folder's past
        print(f"replacing {len(replaced)} file(s) left in {out_dir} by an earlier run of this script")
    (out_dir / "per_stand").mkdir(exist_ok=True)

    manifest: dict[str, Any] = {
        "tool": shown(Path(__file__)), "arm": arm, "suffix": args.suffix, "checks": bool(args.checks),
        "git": git_of_this_checkout(), "committed_files": {}, "rerun_files": {}, "written": {},
    }
    identical: dict[str, bool] = {}

    rule(f"RE-RUN AGAINST COMMITTED OUTPUTS -- {arm} ({spec['what']})")
    say(f"  committed files: {shown(COMMITTED_VECTORS)}/{arm}_<district>_*")
    say(f"  re-run files:    {arm}_<district>{args.suffix}_*   in the folder {shown(rerun_dir)}")
    say("  'old' below is always the committed output, 'new' the re-run.")

    # which districts does the re-run hold completely?
    present, absent = [], {}
    for d in DISTRICTS:
        gone = [t for t in FILE_SUFFIXES if not (rerun_dir / f"{arm}_{d}{args.suffix}_{t}").exists()]
        if gone:
            absent[d] = gone
        else:
            present.append(d)
    for d, gone in absent.items():
        say(f"  NOT RUN or incomplete: {d} -- missing {', '.join(gone)}")

    # ---------------------------------------------------------------- (a) stands, (b) run records
    summary: list[tuple[str, str, dict[str, Any]]] = []
    details: list[str] = []
    records: dict[str, dict[str, Any]] = {}
    for d in DISTRICTS:
        cfg = f"{arm}_{d}"
        for layer, id_field in COMPARED_LAYERS.items():
            old_path = COMMITTED_VECTORS / f"{cfg}_{layer}.geojson"
            new_path = rerun_dir / f"{cfg}{args.suffix}_{layer}.geojson"
            if not old_path.exists() or not new_path.exists():
                continue
            manifest["committed_files"][old_path.name] = sha256(old_path)
            manifest["rerun_files"][new_path.name] = sha256(new_path)
            res = csr.compare_files(old_path, new_path, id_field=id_field, type_field=TYPE_FIELD)
            summary.append((d, layer, res))
            identical[f"stands {d} {layer}"] = csr.is_identical(res)
            details += ["", *csr.format_report(res, title=f"{d} -- {layer}")]
            csr.write_per_stand_csv(res, out_dir / "per_stand" / f"{cfg}_{layer}.csv")
        old_run, new_run = COMMITTED_VECTORS / f"{cfg}_run.json", rerun_dir / f"{cfg}{args.suffix}_run.json"
        if old_run.exists() and new_run.exists():
            manifest["committed_files"][old_run.name] = sha256(old_run)
            manifest["rerun_files"][new_run.name] = sha256(new_run)
            records[d] = compare_run_records(json.loads(old_run.read_text()), json.loads(new_run.read_text()))

    rule("(a) STANDS -- summary; the full table for each district and layer is at the end")
    say("  IoU = area-weighted intersection over union, each stand against the stand of the other run that")
    say("  overlaps it most (1 = the same stands). 'same outline' = stands whose outline is in both runs.")
    say(f"  {'district':<11}{'layer':<15}{'stands':>13}{'polygons':>13}{'same outline':>14}"
        f"{'IoU old->new':>14}{'IoU new->old':>14}{'area IoU>=0.9':>15}{'footprint IoU':>15}")
    for d, layer, res in summary:
        o, n = res["old"], res["new"]
        say(f"  {d:<11}{layer:<15}{str(o['n_stands']) + ' -> ' + str(n['n_stands']):>13}"
            f"{str(o['n_polygons']) + ' -> ' + str(n['n_polygons']):>13}"
            f"{res['same_outline_stands']:>14}"
            f"{res['old_to_new']['area_weighted_iou']:>14.6f}{res['new_to_old']['area_weighted_iou']:>14.6f}"
            f"{100 * res['old_to_new']['share_area_iou_ge'][0.9]:>14.2f}%{res['footprint_iou']:>15.6f}")
    if not summary:
        say("  nothing to compare: no district has both a committed and a re-run stand file")

    rule("(b) RUN RECORDS -- <config>_run.json, committed against re-run")
    for d in DISTRICTS:
        say(f"  {d}")
        if d in records:
            identical[f"run record {d}"] = report_run_records(records[d])
        else:
            say("    no pair of run records to compare")

    # ---------------------------------------------------------------- (c) join
    rule(f"(c) PLOTS JOINED TO THE NEW STANDS -- {shown(JOIN_SCRIPT)} --set districts --arms {short}")
    joined_new = out_dir / JOINED_NAME
    join_ok = False
    if absent:
        say(f"  NOT DONE: the re-run is incomplete ({', '.join(absent)}). A plot table without those districts")
        say("  would give scores on fewer plots than the committed ones, which could not be compared.")
    else:
        with tempfile.TemporaryDirectory(prefix="staged_vectors_", dir=out_dir) as tmp:
            stage_rerun(rerun_dir, arm, args.suffix, DISTRICTS, Path(tmp))
            got = run_script(JOIN_SCRIPT, ["--set", "districts", "--arms", short,
                                           "--vectors-dir", tmp, "--out-dir", str(out_dir)])
        join_ok = got.returncode == 0 and joined_new.exists()
        if not join_ok:
            say(f"  THE JOIN FAILED (exit status {got.returncode}). Its last lines:")
            for ln in (got.stderr or got.stdout).strip().splitlines()[-12:]:
                say(f"    | {ln}")
    if join_ok:
        say("  the re-run's files were presented to the join under the committed names in a temporary folder;")
        say("  nothing else differs from the committed join.")
        say(f"  committed plot table: {shown(spec['committed_joined'])}")
        say(f"  new plot table:       {JOINED_NAME} in the output folder")
        manifest["committed_files"][shown(spec["committed_joined"])] = sha256(spec["committed_joined"])
        manifest["written"][JOINED_NAME] = sha256(joined_new)
        bytes_same = sha256(joined_new) == sha256(spec["committed_joined"])
        pt = compare_plot_tables(pd.read_csv(spec["committed_joined"]), pd.read_csv(joined_new), short)
        say("  the two files are " + (
            "IDENTICAL byte for byte" if bytes_same else
            "not identical byte for byte (they cannot be: the committed table also holds other arms' columns)"
            if pt["columns_only_old"] else "not identical byte for byte"))
        report_plot_tables(pt, short)
        identical["plot table (columns in both)"] = pt["identical_on_shared_columns"]

    # ---------------------------------------------------------------- (d), (e) scores
    rule(f"(d), (e) PHASE 3 SCORES FROM THE NEW PLOT TABLE -- {shown(SCORE_SCRIPT)}")
    if spec["score_args"] is None:
        say("  NO COMMITTED PHASE 3 SCORE FOR THIS ARM. Phase 3 scored the 10 hectare and the 3 hectare stands")
        say(f"  only (there is no {shown(HERE)}/odisha_phase3_1_score_{short}_*.txt), so there is nothing to")
        say("  compare a new score with, and none is computed here: scoring this arm now would be a new")
        say("  analysis, which has to be declared first (PHASE3_PREDECLARED.md).")
    elif not join_ok:
        say("  NOT DONE: there is no new plot table (see (c)).")
    else:
        for name, extra, sens in (ANALYSES if args.checks else ANALYSES[:1]):
            fname = f"odisha_phase3_1_score_{short}_merged_districts{spec['tag']}{sens}.txt"
            committed, new_file = HERE / fname, out_dir / fname
            opts = [*spec["score_args"], *extra]
            say("")
            say(f"  {name}: options {' '.join(shown(Path(o)) if o.endswith('.csv') else o for o in opts)}"
                f"   (plus --joined and --out-dir, which only say where to read and write)")
            got = run_script(SCORE_SCRIPT, [*opts, "--joined", str(joined_new), "--out-dir", str(out_dir)])
            if got.returncode != 0 or not new_file.exists():
                say(f"    THE SCORING FAILED (exit status {got.returncode}). Its last lines:")
                for ln in (got.stderr or got.stdout).strip().splitlines()[-12:]:
                    say(f"    | {ln}")
                identical[f"scores, {name}"] = False
                continue
            manifest["written"][fname] = sha256(new_file)
            if not committed.exists():
                say(f"    no committed file {shown(committed)} to compare with; the new one is {fname}")
                identical[f"scores, {name}"] = False
                continue
            manifest["committed_files"][shown(committed)] = sha256(committed)
            say(f"    committed: {shown(committed)}      new: {fname} in the output folder")
            same, _ = report_scores(committed.read_text(), new_file.read_text())
            identical[f"scores, {name}"] = same
        if not args.checks:
            say("")
            say("  The three declared checks (S1, S2, S3) were not run. To run them and compare each with its")
            say("  committed file, add --checks to the command.")

    # ---------------------------------------------------------------- verdict
    rule("IN SHORT")
    if absent:
        say(f"  districts not compared because the re-run has no complete set of files: {', '.join(absent)}")
    for what, same in identical.items():
        say(f"  {what:<42} {'identical' if same else 'DIFFERS'}")
    all_same = bool(identical) and all(identical.values()) and not absent
    say("")
    if all_same:
        say("  Everything measured is identical to the committed outputs.")
    elif identical and all(identical.values()):
        say("  Everything that could be compared is identical to the committed outputs, but the re-run is")
        say("  incomplete: the districts named above, the plot table and the scores were not compared.")
    else:
        say("  The re-run is not identical to the committed outputs; the sections above say by how much.")
    if spec["score_args"] is None:
        say("  (No Phase 3 score exists for this arm, so none was compared.)")

    rule("STANDS IN FULL -- one table per district and layer")
    for ln in details:
        say(ln)

    results = out_dir / f"odisha_repro_compare_{arm}.txt"
    results.write_text("\n".join(_lines) + "\n")
    manifest["written"][results.name] = sha256(results)
    manifest["identical"] = identical
    (out_dir / f"odisha_repro_compare_{arm}_manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    print(f"\nwrote {results.name} and its manifest in {out_dir}")
    if args.expect_identical and not all_same:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

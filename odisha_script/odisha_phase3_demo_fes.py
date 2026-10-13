"""The comparison with the FES field plots, on a folder of NEW stand files, for three arms.

    python odisha_script/odisha_phase3_demo_fes.py --stands-dir DIR --merge-rule TEXT \\
        [--suffix _repro] [--out-dir odisha_script/phase3_demo] [--arms v120,v120_3ha,alphaearth] \\
        [--rotations 1999] [--boot 4000] [--jobs 4] [--steps join,score,significance] [--dry-run]

    python odisha_script/odisha_phase3_demo_fes.py --collect --out-dir odisha_script/phase3_demo \\
        --json ui_data_fes.json --markdown fes_table.md

It runs the existing Phase 2 join, Phase 3 scores and Phase 3 chance test on stand files that
are not the committed ones (the demo set: the re-runs of 13 Oct 2026, re-merged). It computes
nothing itself: every number comes from odisha_phase2_3_join.py,
odisha_phase3_1_pairwise_score.py and odisha_phase3_3_significance.py, run as they stand.

THE ARMS (the short names of odisha_phase2_3_join.py)
  v120        hand-crafted features, stands of at most 10 ha    configs odisha_v120_handcrafted_<district>
  v120_3ha    hand-crafted features, stands of at most 3 ha     configs odisha_v120_3ha_<district>
  alphaearth  AlphaEarth embedding, stands of at most 10 ha     configs odisha_alphaearth_<district>

WHAT IT DOES
  staging       DIR holds <config>_<district><suffix>_stands_merged.geojson for each config of
                the arms asked for. The join also wants the _stands_snic and _stands_dissolved
                files: they are taken from DIR if present, else from --fallback-vectors (same
                suffix), and the manifest says which file came from where. The files are
                linked into a temporary folder under the names the join looks for. A _run.json
                or _raster_at_plots.csv is never staged: beside new stands the join would print
                a cross-check against the run they did not come from.
  join          once, for the arms asked for, into --out-dir.
  score         for each arm the primary analysis and the checks S1, S2 and S3, with the
                options of PHASE3_STATUS.md, "Reproducing", plus --joined and --out-dir.
  significance  the chance test, through odisha_phase3_demo_sigwrap.py (which runs the script
                unmodified on the staged files). Hand-crafted: one run of both stand sizes per
                analysis, Holm over its 10 tests, exactly as Phase 3. AlphaEarth: one run of
                that arm alone per analysis, Holm over its own 5. The runs go in parallel
                processes (--jobs).
  AlphaEarth    is scored and tested only if PHASE3_ALPHAEARTH_PREDECLARED.md is committed,
                unmodified, is on the remote branch, and its line "- Merge rule: ..." is the
                --merge-rule text. The join may be made before that: it relates no field
                measurement to a stand.
                If the declaration is not in place the hand-crafted arms still run, the
                AlphaEarth arm is skipped with the reason, and the exit status is 3.
  --dry-run     stages, checks every input and prints the commands. Runs and writes nothing.
  --collect     reads the result files in --out-dir and writes the rows for the UI (--json)
                and a table per arm and stand size (--markdown). See collect().

WHAT IT READS
  the stand files (above); odisha_script/Odisha_samples.csv, odisha_plots_clean.csv and the
  three odisha_phase3_0_field_types*.csv; aois/odisha_habitations_<district>.geojson.
WHAT IT WRITES, all in --out-dir
  phase2_plots_joined_districts.csv, odisha_phase2_3_results_districts.txt     (the join)
  odisha_phase3_1_score_<arm>_merged_districts[_3ha][_excl0|_ft-k4|_ft-allrows].txt (the scores)
  odisha_phase3_3_results[_excl0|_ft-k4|_ft-allrows][_alphaearth].txt          (the chance test)
  fes_manifest.json    the git commit and dirty flag, the command line, the merge rule, the
                       sha256 and source of every staged file, the result files written
  *.log                run times and the scripts' terminal output; git ignores them
It refuses an --out-dir that is odisha_script/ itself, phase2_vectors/, phase3_3ha/ or
phase3_before_regroup/, that is a folder the stands are read from, or that holds committed
files of another analysis. It overwrites a committed result of its own only with
--replace-committed. fes_manifest.json is the record of the runs, not a result: every run
rewrites it, committed or not, and its list of result files is what the folder holds after
the run. Result files hold results only; the one date is in the manifest.

A run with the join step makes every earlier result in --out-dir a result on another plot
table. They are set aside in <out-dir>/.fes_earlier while the join runs, removed when it has
succeeded, and put back as they were if it fails.

Exit status: 0 done; 1 a step failed (the log is named); 2 the inputs or the folder were refused
(a message says why); 3 everything asked for ran except the AlphaEarth arm, which is not
declared.

No Earth Engine. No network. Run from the repo root.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parent

JOIN_SCRIPT = HERE / "odisha_phase2_3_join.py"
SCORE_SCRIPT = HERE / "odisha_phase3_1_pairwise_score.py"
SIGNIFICANCE_WRAPPER = HERE / "odisha_phase3_demo_sigwrap.py"
DECLARATION = HERE / "PHASE3_ALPHAEARTH_PREDECLARED.md"
MERGE_RULE_PLACEHOLDER = "<MERGE RULE>"

DISTRICTS = ["angul", "dhenkanal", "kendujhar", "koraput"]       # as odisha_phase2_3_join.DISTRICTS
# layer file -> the property holding the stand id (as odisha_phase2_3_join.LAYERS)
LAYER_ID = {"stands_merged": "stand_lbl", "stands_snic": "snic_label", "stands_dissolved": "unit_id"}
NEVER_STAGED = ("run.json", "raster_at_plots.csv")
JOINED_NAME = "phase2_plots_joined_districts.csv"
JOIN_RESULTS_NAME = "odisha_phase2_3_results_districts.txt"
MANIFEST_NAME = "fes_manifest.json"
HELD_NAME = ".fes_earlier"          # where a run with the join step keeps the earlier results until the join is done
N_ROT, N_BOOT = 1999, 4000          # the declared draw counts (odisha_phase3_3_significance.py)

# One entry per arm, in reporting order: the pipeline config prefix, the options the
# "Reproducing" section of PHASE3_STATUS.md gives the scorer for it, and how the UI names it.
ARMS: dict[str, dict[str, Any]] = {
    "v120": {"config": "odisha_v120_handcrafted", "score_args": ["--arm", "v120"], "score_tag": "",
             "ui_arm": "feature_vector", "ceiling_ha": 10, "what": "hand-crafted features, stands of at most 10 ha"},
    "v120_3ha": {"config": "odisha_v120_3ha", "score_args": ["--arm", "v120_3ha", "--tag", "_3ha"],
                 "score_tag": "_3ha",
                 "ui_arm": "feature_vector", "ceiling_ha": 3, "what": "hand-crafted features, stands of at most 3 ha"},
    "alphaearth": {"config": "odisha_alphaearth", "score_args": ["--arm", "alphaearth"], "score_tag": "",
                   "ui_arm": "alphaearth", "ceiling_ha": 10, "what": "AlphaEarth embedding, stands of at most 10 ha"},
}
HANDCRAFTED = ["v120", "v120_3ha"]     # tested together, Holm over both (PHASE3_PREDECLARED.md)
GUARDED = "alphaearth"                 # tested alone, and only once declared

# The primary analysis and the three checks of PHASE3_PREDECLARED.md, as "Reproducing" runs
# them: (name, extra options, the suffix the scripts add to their file names).
ANALYSES: list[tuple[str, list[str], str]] = [
    ("primary", [], ""),
    ("S1", ["--exclude-types", "0"], "_excl0"),
    ("S2", ["--field-types", str(HERE / "odisha_phase3_0_field_types_k4.csv")], "_ft-k4"),
    ("S3", ["--field-types", str(HERE / "odisha_phase3_0_field_types_allrows.csv")], "_ft-allrows"),
]
STEPS = ["join", "score", "significance"]

# Folders that hold committed results of other analyses (as odisha_repro_compare.PROTECTED).
PROTECTED = [HERE / "phase2_vectors", HERE / "phase3_3ha", HERE / "phase3_before_regroup"]
# What this script and the scripts it runs write into --out-dir. A committed file there that
# matches none of these (and is not the folder's README) belongs to another analysis.
OWN_PATTERNS = [JOINED_NAME, JOIN_RESULTS_NAME, MANIFEST_NAME, "fes_*.log",
                "odisha_phase3_1_score_*_merged_districts*.txt",
                "odisha_phase3_3_results*.txt", "odisha_phase3_3_results*.log"]
KEPT_BESIDE = ["README.md"]


class Refused(SystemExit):
    """The inputs, the folder or the declaration were refused: exit status 2, reason printed."""

    def __init__(self, why: str):
        print(f"REFUSED: {why}", file=sys.stderr)
        super().__init__(2)
        self.why = why


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def shown(path: Path) -> str:
    """A path as the manifest writes it: from the top of the repository when it is in it."""
    path = Path(path).resolve()
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)


def _git(repo: Path, *args: str) -> tuple[int, str]:
    try:
        got = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)
    except OSError as e:
        return 127, str(e)
    return got.returncode, (got.stdout if got.returncode == 0 else got.stderr).strip()


# --------------------------------------------------------------------------- the AlphaEarth guard
def declared_merge_rule(text: str) -> tuple[str | None, str]:
    """The merge rule a declaration names: the text of its one list item "- Merge rule: ...",
    with the item's indented continuation lines, spaces and line breaks made single spaces.
    Returns (rule, "") or (None, why): no such item, more than one, or an empty one."""
    lines = text.splitlines()
    at = [i for i, ln in enumerate(lines) if re.match(r"\s*[-*]\s+Merge rule:", ln)]
    if len(at) != 1:
        return None, f'{len(at)} list items start "- Merge rule:"; there must be exactly one'
    parts = [lines[at[0]].split("Merge rule:", 1)[1]]
    for ln in lines[at[0] + 1:]:
        if not ln.strip() or not ln[0].isspace() or re.match(r"\s*[-*]\s", ln):
            break                     # a blank line, an unindented line or the next item ends this one
        parts.append(ln)
    rule = " ".join(" ".join(parts).split())
    return (rule, "") if rule else (None, 'the item "- Merge rule:" names no rule')


def alphaearth_declaration_state(repo: Path = REPO, merge_rule: str | None = None) -> dict[str, Any]:
    """Is the AlphaEarth declaration in place? Returns {"ok", "why", "commit", "branch",
    "sha256", "merge_rule"}.

    In place means all of:
      - odisha_script/PHASE3_ALPHAEARTH_PREDECLARED.md exists in the checkout `repo`;
      - it is committed (git ls-files) and the file on disk is the committed one: its blob
        is compared with the one in HEAD, so a file git was told to assume unchanged does
        not pass;
      - it no longer holds the placeholder <MERGE RULE>, and it has exactly one list item
        "- Merge rule: ..." (declared_merge_rule);
      - when merge_rule is given, it is that item's text, spaces and line breaks aside: the
        stands scored are the stands declared. Text from elsewhere in the file does not pass;
      - the last commit that changed it is an ancestor of origin/<current branch>, as the
        checkout knows that branch. Nothing is fetched here: the caller fetches first.
    Only reads; never raises for a missing file, a missing remote or a missing git."""
    rel = DECLARATION.relative_to(REPO).as_posix()
    path = Path(repo) / rel
    state: dict[str, Any] = {"ok": False, "why": "", "commit": None, "branch": None, "sha256": None,
                             "merge_rule": None}

    def no(why: str) -> dict[str, Any]:
        state["why"] = why
        return state

    if not path.is_file():
        return no(f"{rel} does not exist. The AlphaEarth analysis is declared in that file before any "
                  "AlphaEarth score is computed.")
    rc, _ = _git(repo, "ls-files", "--error-unmatch", "--", rel)
    if rc != 0:
        return no(f"{rel} is not committed to git. Commit it and push it before scoring.")
    # the blobs, not `git status`: status says nothing about a file marked assume-unchanged or skip-worktree
    rc_head, in_head = _git(repo, "rev-parse", "--verify", "--quiet", f"HEAD:./{rel}")
    rc_disk, on_disk = _git(repo, "hash-object", "--", rel)
    if rc_head != 0 or rc_disk != 0 or not in_head or in_head != on_disk:
        return no(f"{rel} differs from its committed version. Commit the change and push it, or restore the file.")
    text = path.read_text()
    state["sha256"] = sha256(path)
    if MERGE_RULE_PLACEHOLDER in text:
        return no(f"{rel} still holds the placeholder {MERGE_RULE_PLACEHOLDER}. Write the stands it will be run "
                  "on in its place, commit and push.")
    declared, why = declared_merge_rule(text)
    if declared is None:
        return no(f"{rel}: {why}. The stands it will be run on are named on that one line.")
    state["merge_rule"] = declared
    if merge_rule is not None and " ".join(merge_rule.split()) != declared:
        return no(f"the --merge-rule text {merge_rule!r} is not the merge rule {rel} declares ({declared!r}). "
                  "The stands that are scored must be the stands the declaration names: give --merge-rule "
                  "exactly as its line 'Merge rule:' writes it.")
    rc, commit = _git(repo, "log", "-1", "--format=%H", "--", rel)
    if rc != 0 or not commit:
        return no(f"git names no commit for {rel}.")
    state["commit"] = commit
    rc, branch = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    if rc != 0 or branch in ("", "HEAD"):
        return no("the checkout is not on a branch, so there is no remote branch to find the declaration on.")
    state["branch"] = branch
    rc, _ = _git(repo, "rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{branch}")
    if rc != 0:
        return no(f"there is no origin/{branch} in this checkout. Push the branch (and `git fetch origin`) first.")
    rc, _ = _git(repo, "merge-base", "--is-ancestor", commit, f"origin/{branch}")
    if rc != 0:
        return no(f"the commit that last changed {rel} ({commit[:10]}) is not on origin/{branch}. "
                  "Push it (then `git fetch origin`) before scoring.")
    state["ok"] = True
    return state


def require_alphaearth_declared(repo: Path = REPO, merge_rule: str | None = None) -> dict[str, Any]:
    """Stop unless the AlphaEarth declaration is in place (alphaearth_declaration_state)."""
    state = alphaearth_declaration_state(repo, merge_rule)
    if not state["ok"]:
        raise Refused("no AlphaEarth score or test before its declaration is committed and pushed: " + state["why"])
    return state


# --------------------------------------------------------------------------- where to write
def _same_folder(a: Path, b: Path) -> bool:
    """True when a and b are one folder on disk, however each is spelled (macOS ignores case)."""
    try:
        return a.exists() and b.exists() and os.path.samefile(a, b)
    except OSError:
        return False


def _is_or_inside(path: Path, folder: Path) -> bool:
    """True when path is folder or lies below it (path itself need not exist yet)."""
    return any(_same_folder(p, folder) for p in (path, *path.parents))


def tracked_names(folder: Path) -> list[str]:
    """Files committed to git directly in `folder`, by name. Empty when the folder does not
    exist, is not in a git checkout, or holds nothing committed."""
    if not folder.is_dir():
        return []
    rc, out = _git(folder, "ls-files", "--", ".")
    return sorted(ln for ln in out.splitlines() if ln) if rc == 0 else []


def is_own(name: str) -> bool:
    return any(Path(name).match(p) for p in OWN_PATTERNS)


def check_out_dir(out_dir: Path, source_dirs: list[Path]) -> None:
    """Stop unless out_dir is a place where no result of another analysis can be overwritten."""
    out = out_dir.resolve()
    if out.exists() and not out.is_dir():
        raise Refused(f"--out-dir {out} is a file.")
    if _is_or_inside(HERE, out):      # odisha_script/ itself, the repository, or a folder above it
        raise Refused(f"--out-dir {out}: the committed Phase 3 results and plot table are in {HERE}, and this "
                      "script writes files of the same names. Name a folder of its own, for example "
                      "odisha_script/phase3_demo.")
    for prot in PROTECTED:
        if _is_or_inside(out, prot):
            raise Refused(f"--out-dir {out}: it is inside {shown(prot)}/, which holds committed results. "
                          "Name a folder of its own.")
    for src in source_dirs:
        if _is_or_inside(out, src) or _is_or_inside(src, out):
            raise Refused(f"--out-dir {out}: the stand files are read from {src}. Results go to a folder of their own.")
    foreign = [n for n in tracked_names(out) if not is_own(n) and n not in KEPT_BESIDE]
    if foreign:
        raise Refused(f"--out-dir {out}: it holds {len(foreign)} committed file(s) of another analysis "
                      f"(for example {foreign[0]}). Name a folder of its own.")


# --------------------------------------------------------------------------- staging
def plan_staging(stands_dir: Path, suffix: str, fallback_dir: Path, arms: list[str]) -> list[dict[str, Any]]:
    """Which file is presented to the join under which name, for every arm, district and
    layer. The merged layer must be in stands_dir: it is what is being compared. The snic and
    dissolved layers come from stands_dir if they are there, else from fallback_dir. Stops
    with the full list if any file is in neither place."""
    plan, missing = [], []
    for arm in arms:
        cfg = ARMS[arm]["config"]
        for d in DISTRICTS:
            for layer in LAYER_ID:
                name = f"{cfg}_{d}{suffix}_{layer}.geojson"
                places = [("stands-dir", stands_dir / name)]
                if layer != "stands_merged":
                    places.append(("fallback-vectors", fallback_dir / name))
                found = next(((origin, p) for origin, p in places if p.is_file()), None)
                if found is None:
                    missing.append(name + " (looked in " + " and ".join(str(p.parent) for _, p in places) + ")")
                    continue
                plan.append({"arm": arm, "district": d, "layer": layer, "from": found[0],
                             "source": found[1].resolve(), "staged_as": f"{cfg}_{d}_{layer}.geojson"})
    if missing:
        raise Refused(f"{len(missing)} stand file(s) not found:\n  " + "\n  ".join(missing))
    return plan


def check_stand_file(path: Path, layer: str) -> None:
    """Stop unless the file is what the join reads: a GeoJSON FeatureCollection of polygons,
    each with the layer's stand id (stand_lbl, snic_label or unit_id), and for the merged layer
    a cluster_id. The stand files written for the UI are not: they name the type stand_type,
    carry no stand_lbl and have rounded coordinates."""
    id_field = LAYER_ID[layer]
    try:
        gj = json.loads(path.read_text())
    except (OSError, ValueError) as e:
        raise Refused(f"{path} cannot be read as GeoJSON: {e}") from None
    feats = gj.get("features") if isinstance(gj, dict) else None
    if not feats:
        raise Refused(f"{path} holds no features.")
    for f in feats:
        props = f.get("properties") or {}
        if props.get(id_field) is None:
            raise Refused(f"{path}: a polygon has no {id_field!r}. The join needs the analysis stand files "
                          f"(with {id_field} and cluster_id), not the files written for the UI.")
        if (f.get("geometry") or {}).get("type") not in ("Polygon", "MultiPolygon"):
            raise Refused(f"{path}: a feature is not a Polygon or MultiPolygon.")
    if layer == "stands_merged" and not any("cluster_id" in (f.get("properties") or {}) for f in feats):
        raise Refused(f"{path}: no polygon has a cluster_id, so no stand has a type and labelling cannot be scored.")


def stage(plan: list[dict[str, Any]], into: Path) -> None:
    """Present the planned files under the names odisha_phase2_3_join.py looks for. Links, or
    copies where links are refused. Nothing else is put in the folder."""
    for item in plan:
        dst = into / item["staged_as"]
        try:
            os.symlink(item["source"], dst)
        except OSError:
            shutil.copyfile(item["source"], dst)
    stray = [p.name for p in into.iterdir() if p.name.endswith(NEVER_STAGED)]
    if stray:       # cannot happen from a plan; kept so that a later change cannot stage one unnoticed
        raise Refused(f"the staging folder holds {stray}; a run record or raster sample must not sit beside new stands.")


def check_fixed_inputs() -> dict[str, str]:
    """The files the three scripts read besides the stands. Returns {path: sha256}."""
    need = [HERE / "Odisha_samples.csv", HERE / "odisha_plots_clean.csv",
            HERE / "odisha_phase3_0_field_types.csv", HERE / "odisha_phase3_0_field_types_k4.csv",
            HERE / "odisha_phase3_0_field_types_allrows.csv",
            *(REPO / "aois" / f"odisha_habitations_{d}.geojson" for d in DISTRICTS),
            JOIN_SCRIPT, SCORE_SCRIPT, SIGNIFICANCE_WRAPPER, HERE / "odisha_phase3_3_significance.py"]
    gone = [shown(p) for p in need if not p.is_file()]
    if gone:
        raise Refused("missing input file(s): " + ", ".join(gone))
    return {shown(p): sha256(p) for p in need}


# --------------------------------------------------------------------------- the commands
def significance_name(sens: str, arms: list[str], rotations: int, boot: int) -> str:
    """The results file odisha_phase3_3_significance.py writes for these options: its own
    rule (sensitivity_tag), repeated here to know which file to wait for. A test checks the
    two agree."""
    tag = sens
    if arms != HANDCRAFTED:
        tag += "_" + "-".join(arms)
    if rotations != N_ROT:
        tag += f"_rot{rotations}"
    if boot != N_BOOT and len(arms) == 2:
        tag += f"_boot{boot}"
    return f"odisha_phase3_3_results{tag}.txt"


def score_name(arm: str, sens: str) -> str:
    return f"odisha_phase3_1_score_{arm}_merged_districts{ARMS[arm]['score_tag']}{sens}.txt"


def build_jobs(arms: list[str], steps: list[str], staged: Path, out_dir: Path, rotations: int, boot: int,
               skip_guarded: bool) -> list[dict[str, Any]]:
    """Every command of the run, in order. Each job names the files it writes and its log."""
    py = sys.executable
    joined = out_dir / JOINED_NAME
    jobs: list[dict[str, Any]] = []
    if "join" in steps:
        jobs.append({"step": "join", "name": "join", "writes": [JOINED_NAME, JOIN_RESULTS_NAME],
                     "argv": [py, str(JOIN_SCRIPT), "--set", "districts", "--arms", ",".join(arms),
                              "--vectors-dir", str(staged), "--out-dir", str(out_dir)]})
    scored = [a for a in arms if not (a == GUARDED and skip_guarded)]
    if "score" in steps:
        for arm in scored:
            for name, extra, sens in ANALYSES:
                jobs.append({"step": "score", "name": f"score_{arm}_{name}", "writes": [score_name(arm, sens)],
                             "argv": [py, str(SCORE_SCRIPT), *ARMS[arm]["score_args"], *extra,
                                      "--joined", str(joined), "--out-dir", str(out_dir)]})
    if "significance" in steps:
        # hand-crafted: the arms asked for in ONE run per analysis (both of them: Holm over 10,
        # as Phase 3). AlphaEarth: alone, through the wrapper's --single-arm (Holm over its 5).
        groups = [g for g in ([a for a in HANDCRAFTED if a in scored], [GUARDED] if GUARDED in scored else []) if g]
        for group in groups:
            single = ["--single-arm", GUARDED] if group == [GUARDED] else []
            for name, extra, sens in ANALYSES:
                out_name = significance_name(sens, group, rotations, boot)
                jobs.append({"step": "significance", "name": f"significance_{'-'.join(group)}_{name}",
                             "writes": [out_name],
                             "argv": [py, str(SIGNIFICANCE_WRAPPER), "--vectors-dir", str(staged),
                                      "--joined", str(joined), *single, "--",
                                      "--arms", ",".join(group), "--rotations", str(rotations),
                                      "--boot", str(boot), "--out-dir", str(out_dir), *extra]})
    for j in jobs:
        j["log"] = f"fes_{j['name']}.log"
    return jobs


def run_job(job: dict[str, Any], out_dir: Path) -> bool:
    """Run one command from the repo root, its terminal output into its log. True when it
    ended with status 0 and every file it should write is there."""
    for name in job["writes"]:        # a file left by an earlier run must not pass for this run's
        (out_dir / name).unlink(missing_ok=True)
        if job["step"] == "significance":
            (out_dir / name).with_suffix(".log").unlink(missing_ok=True)   # the script appends its run times
    with (out_dir / job["log"]).open("w") as log:
        got = subprocess.run(job["argv"], cwd=REPO, stdout=log, stderr=subprocess.STDOUT, check=False)
    ok = got.returncode == 0 and all((out_dir / n).is_file() for n in job["writes"])
    job["status"] = "done" if ok else f"FAILED (exit status {got.returncode})"
    print(f"  {job['name']:<44} {job['status']}", flush=True)
    if not ok:
        tail = (out_dir / job["log"]).read_text(errors="replace").strip().splitlines()[-12:]
        print("\n".join(f"    | {ln}" for ln in tail), flush=True)
        print(f"    the full output is in {out_dir / job['log']}", flush=True)
    return ok


def joined_arms(joined: Path) -> list[str]:
    """The arms a plot table holds, read from its header."""
    with joined.open() as fh:
        header = fh.readline().strip().split(",")
    return [a for a in ARMS if f"{a}_merged_id" in header]


def staged_record(plan: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    return {i["staged_as"]: {"source": shown(i["source"]), "from": i["from"], "sha256": sha256(i["source"])}
            for i in plan}


def git_state_here() -> dict[str, Any]:
    """The commit this checkout is at and whether it has uncommitted changes
    (fmu.utils.provenance.git_state, asked about this script's checkout)."""
    try:
        from fmu.utils.provenance import git_state
    except ImportError:               # run without the package installed: take it from this checkout
        sys.path.insert(0, str(REPO / "src"))
        from fmu.utils.provenance import git_state
    return git_state(HERE)


# --------------------------------------------------------------------------- the run
def run(args: argparse.Namespace, argv: list[str]) -> int:
    arms = [a for a in ARMS if a in {x.strip() for x in args.arms.split(",") if x.strip()}]
    unknown = sorted({x.strip() for x in args.arms.split(",") if x.strip()} - set(ARMS))
    if unknown or not arms:
        raise Refused(f"--arms: unknown or empty {unknown}; known: {', '.join(ARMS)}")
    steps = [s for s in STEPS if s in {x.strip() for x in args.steps.split(",") if x.strip()}]
    bad = sorted({x.strip() for x in args.steps.split(",") if x.strip()} - set(STEPS))
    if bad or not steps:
        raise Refused(f"--steps: unknown or empty {bad}; known: {', '.join(STEPS)}")
    if args.stands_dir is None or not args.merge_rule or not args.merge_rule.strip():
        raise Refused("--stands-dir and --merge-rule are both needed (the merge rule is written into the manifest: "
                      "the register id of the rule the stands were merged under, or 'before the merge fix').")
    if args.rotations < 1 or args.boot < 1 or args.jobs < 1:
        raise Refused("--rotations, --boot and --jobs must be at least 1.")
    merge_rule = " ".join(args.merge_rule.split())
    stands_dir = args.stands_dir.resolve()
    fallback = (args.fallback_vectors if args.fallback_vectors.is_absolute() else REPO / args.fallback_vectors).resolve()
    out_dir = (args.out_dir if args.out_dir.is_absolute() else Path.cwd() / args.out_dir).resolve()
    if not stands_dir.is_dir():
        raise Refused(f"--stands-dir {stands_dir} is not a folder.")
    check_out_dir(out_dir, [stands_dir, fallback])

    print(f"FES comparison on the stands in {stands_dir}")
    print(f"  merge rule: {merge_rule}")
    print(f"  arms: {', '.join(arms)}   steps: {', '.join(steps)}   out: {out_dir}")
    fixed = check_fixed_inputs()
    plan = plan_staging(stands_dir, args.suffix, fallback, arms)
    for item in plan:
        check_stand_file(item["source"], item["layer"])
    n_fb = sum(i["from"] == "fallback-vectors" for i in plan)
    print(f"  {len(plan)} stand files found and checked; {n_fb} taken from the fallback folder {fallback}")
    for item in plan:
        if item["from"] == "fallback-vectors":
            print(f"    fallback: {item['staged_as']}  <-  {item['source']}")
    if any(i["from"] == "fallback-vectors" and i["layer"] == "stands_dissolved" for i in plan):
        print("    A dissolved layer from the fallback folder was made from the stands before the re-merge. The join")
        print("    needs the file to be there; no Phase 3 score reads it. Its columns in the plot table are stale.")
    staged = staged_record(plan)

    # AlphaEarth: declared first, or not scored
    declaration: dict[str, Any] | None = None
    skip_guarded = False
    if GUARDED in arms and ("score" in steps or "significance" in steps):
        declaration = alphaearth_declaration_state(REPO, merge_rule)
        if not declaration["ok"]:
            skip_guarded = True
            print("")
            print("  THE ALPHAEARTH ARM WILL NOT BE SCORED OR TESTED: " + declaration["why"])
            print("  (analyses are declared before they are run: CLAUDE.md, 'Results'.)")

    # the plot table this run scores: made now, or made by an earlier run from the same stands
    joined = out_dir / JOINED_NAME
    manifest_path = out_dir / MANIFEST_NAME
    manifest: dict[str, Any] = {}
    if "join" in steps:
        if joined.is_file():
            there = joined_arms(joined)
            dropped = [a for a in there if a not in arms]
            if dropped:
                every = ",".join(a for a in ARMS if a in there or a in arms)
                raise Refused(f"{joined} holds the arm(s) {dropped}, which this run was not asked for. A new join "
                              "would drop them and leave their results without a plot table. Name every arm "
                              f"(--arms {every}), or keep the table and add --steps score,significance.")
    else:
        if not joined.is_file() or not manifest_path.is_file():
            raise Refused(f"--steps has no join, and {out_dir} holds no {JOINED_NAME} with its {MANIFEST_NAME}. "
                          "Run the join first.")
        manifest = json.loads(manifest_path.read_text())
        absent = [a for a in arms if a not in joined_arms(joined)]
        if absent:
            raise Refused(f"{joined} has no columns for the arm(s) {absent}: the join was not run for them.")
        if manifest.get("merge_rule") != merge_rule:
            raise Refused(f"the plot table in {out_dir} was joined under the merge rule {manifest.get('merge_rule')!r}, "
                          f"not {merge_rule!r}.")
        if manifest.get("result_files", {}).get(JOINED_NAME) != sha256(joined):
            raise Refused(f"{joined} is not the plot table {MANIFEST_NAME} records. Run the join again.")
        differ = [n for n, rec in staged.items() if manifest.get("staged", {}).get(n, {}).get("sha256") != rec["sha256"]]
        if differ:
            raise Refused(f"{len(differ)} stand file(s) are not the ones the plot table in {out_dir} was joined to "
                          f"(for example {differ[0]}). Run the join again on these stands.")

    with tempfile.TemporaryDirectory(prefix="fes_staged_vectors_") as tmp:
        stage(plan, Path(tmp))
        jobs = build_jobs(arms, steps, Path(tmp), out_dir, args.rotations, args.boot, skip_guarded)
        if not jobs:                  # only the AlphaEarth arm was asked for, and it is not declared
            return 3
        will_write = sorted({n for j in jobs for n in j["writes"]})
        # a new join makes every earlier result in the folder a result on another plot table
        stale = (sorted(p.name for p in out_dir.iterdir() if p.is_file() and is_own(p.name) and p.name != MANIFEST_NAME)
                 if "join" in steps and out_dir.is_dir() else [])
        committed = [n for n in tracked_names(out_dir) if n in will_write or n in stale]
        if committed and not args.replace_committed:
            raise Refused(f"this run would replace {len(committed)} result file(s) committed to git in {out_dir} "
                          f"(for example {committed[0]}). A committed result is not overwritten silently: name "
                          "another --out-dir, or add --replace-committed and say in the commit what the comparison showed.")

        held = out_dir / HELD_NAME
        if held.exists():
            raise Refused(f"{held} exists: a run with the join step was interrupted and the earlier results are "
                          f"still set aside there. Move them back into {out_dir}, or delete the folder, and run again.")

        print("")
        print(f"  {len(jobs)} command(s), run from {REPO}:")
        for j in jobs:
            print("    " + " ".join(shlex.quote(a) for a in j["argv"]))
        if args.rotations != N_ROT or args.boot != N_BOOT:
            print(f"  NOT THE DECLARED DRAWS ({N_ROT} rotations, {N_BOOT} bootstrap draws): a test run. Its files carry")
            print("  _rot / _boot in their names and --collect leaves them out.")
        if "significance" in steps and len([a for a in HANDCRAFTED if a in arms]) == 1:
            print("  ONE HAND-CRAFTED ARM ONLY: its Holm correction is over 5 tests, not the 10 of Phase 3.")
        if args.dry_run:
            print("")
            print("  --dry-run: every input was found and checked; nothing was run or written. The staging folder")
            print(f"  in the commands ({tmp}) is temporary and is removed now.")
            return 3 if skip_guarded else 0

        out_dir.mkdir(parents=True, exist_ok=True)
        if committed:
            print(f"  --replace-committed: replacing {len(committed)} committed file(s): {', '.join(committed)}")
        # Set aside, not deleted: if the join fails the folder must be as it was, with the
        # earlier results (hours of chance tests) still beside the plot table they came from.
        earlier_manifest = json.loads(manifest_path.read_text()) if manifest_path.is_file() else None
        if stale:
            held.mkdir()
            for name in stale:
                os.replace(out_dir / name, held / name)
            print(f"  set aside {len(stale)} file(s) an earlier run left in {out_dir}: they describe another join. "
                  "They are removed once the join has succeeded and put back if it fails.")
        if "join" in steps:
            manifest = {}
        manifest.update({"tool": shown(Path(__file__)), "merge_rule": merge_rule, "suffix": args.suffix,
                         "stands_dir": shown(stands_dir), "fallback_vectors": shown(fallback)})
        manifest["staged"] = {**manifest.get("staged", {}), **staged}
        manifest["fixed_inputs"] = fixed
        this_run: dict[str, Any] = {
            "date": datetime.date.today().isoformat(), "git": git_state_here(),
            "command": " ".join(shlex.quote(a) for a in [Path(sys.argv[0]).name, *argv]),
            "arms": arms, "steps": steps, "rotations": args.rotations, "boot": args.boot,
            "alphaearth_declaration": None if declaration is None else
            {k: declaration[k] for k in ("ok", "why", "commit", "branch", "sha256", "merge_rule")},
        }

        print("")
        failed: list[str] = []
        first = [j for j in jobs if j["step"] == "join"]
        if first and not run_job(first[0], out_dir):
            failed.append("join")
        elif first and [a for a in arms if a not in joined_arms(joined)]:
            failed.append("join")
            print(f"  the join wrote no columns for {[a for a in arms if a not in joined_arms(joined)]}; see {first[0]['log']}")
        restored = False
        if first and failed:          # the folder as it was: nothing of the failed join but its log
            for name in first[0]["writes"]:
                (out_dir / name).unlink(missing_ok=True)
            for name in stale:
                if name != first[0]["log"]:
                    os.replace(held / name, out_dir / name)
            restored = bool(stale)
            if restored:
                print(f"  put back the {len(stale)} file(s) of the earlier run: {out_dir} holds its results again")
        if held.is_dir():
            shutil.rmtree(held)
        if not failed:
            for j in (j for j in jobs if j["step"] == "score"):
                if not run_job(j, out_dir):
                    failed.append(j["name"])
            sig = [j for j in jobs if j["step"] == "significance"]
            if sig:
                print(f"  chance tests: {len(sig)} run(s), {min(args.jobs, len(sig))} at a time "
                      "(one alone takes about six minutes at 1,999 rotations)", flush=True)
                with ThreadPoolExecutor(max_workers=args.jobs) as pool:
                    for j, ok in zip(sig, pool.map(lambda j: run_job(j, out_dir), sig), strict=True):
                        if not ok:
                            failed.append(j["name"])

        # the manifest: what is in the folder now, whatever happened. A job deletes the files
        # it is about to write, so one that failed leaves no file: its names go from the list.
        written = {n: sha256(out_dir / n) for j in jobs for n in j["writes"]
                   if j.get("status") == "done" and (out_dir / n).is_file()}
        this_run["written"] = written
        this_run["failed"] = failed
        this_run["not_run"] = [j["name"] for j in jobs if "status" not in j]
        if restored and earlier_manifest is not None:
            # the earlier results are back, so the earlier record still describes the folder:
            # it is kept whole and this run is added to it as a run that failed
            manifest = earlier_manifest
        else:
            gone = {n for j in jobs if "status" in j for n in j["writes"]} - set(written)
            kept = {n: h for n, h in manifest.get("result_files", {}).items()
                    if n not in gone and (out_dir / n).is_file()}
            manifest["result_files"] = dict(sorted({**kept, **written}.items()))
        manifest["runs"] = [*manifest.get("runs", []), this_run]
        if not restored or earlier_manifest is not None:      # earlier results with no manifest: left as found
            manifest_path.write_text(json.dumps(manifest, indent=1) + "\n")

    print("")
    print(f"  wrote {len(written)} result file(s) in {out_dir}; {MANIFEST_NAME} there lists what the folder holds")
    if failed:
        print(f"  FAILED: {', '.join(failed)}. A failed chance test (an identity check, a null that cannot be built) "
              "is reported as it is, not worked around.")
        return 1
    if skip_guarded:
        print("  THE ALPHAEARTH ARM WAS NOT SCORED OR TESTED: " + (declaration or {}).get("why", ""))
        print(f"  Once the declaration is pushed: the same command with --arms {GUARDED} --steps score,significance")
        return 3
    return 0


# --------------------------------------------------------------------------- reading the result files
# test name for the UI -> (the label in odisha_phase3_3_results*.txt, the name PHASE3_STATUS.md
# gives the score in its tables, the same in plain words)
TESTS: dict[str, tuple[str, str, str]] = {
    "drawing_all_plots": ("delineation ARI, all plots", "Drawing, all plots",
                          "Drawing, all plots: do plots of the same field type share a stand?"),
    "drawing_shared_stands": ("delineation ARI, multi-plot stands", "Drawing, shared stands",
                              "Drawing, only stands that hold two or more plots"),
    "same_stand_precision": ("same-stand pair precision", "Same-stand precision",
                             "Same-stand precision: of the pairs of plots that share a stand, the share with the "
                             "same field type"),
    "labelling": ("labelling ARI, per-district wmean", "Labelling",
                  "Labelling: do plots of the same field type get the same stand type?"),
    "labelling_far_apart": ("far-apart same-label rate, alike - differ", "Far-apart labelling",
                            "Far-apart labelling: among plots more than 2 km apart, how much more often plots of "
                            "the same field type get the same stand type than plots of different field types"),
}
N_PLOTS_NOTE = (
    "n_plots is the number of plots that enter the measure, read from the same results file: for "
    "drawing_all_plots the plots that have a stand; for drawing_shared_stands and same_stand_precision the "
    "plots in stands that hold two or more scored plots (only those form same-stand pairs); for labelling and "
    "labelling_far_apart the plots whose stand has a stand type (the far-apart measure uses the pairs of them "
    "more than 2 km apart in one district). Under S1 the counts are those left after field type 0 is taken out."
)
ROW_NOTES = {
    "n_plots": N_PLOTS_NOTE,
    "score": "the observed value, as printed in the results file (4 decimal places)",
    "chance_percentile": "where the observed value falls among the randomly placed maps (rotation null), 0 to 100",
    "p": "one-sided: the share of randomly placed maps that score at least as high (3 decimal places, as printed)",
    "p_holm": "p after the Holm correction over the tests of its own results file. holm_family says how many tests "
              "that file declares: 10 for the two hand-crafted stand sizes tested together, 5 for AlphaEarth "
              "tested alone. Holm values from families of different size are not comparable.",
    "holm_tests_corrected": "the number of tests the Holm values of that results file were in fact computed over: "
                            "the rows of its Holm table. It equals holm_family unless a test of the file is NOT "
                            "ESTIMABLE or has no defined score; the script then corrects over the tests that "
                            "remain, and p_holm is over this smaller number, not over holm_family.",
    "null": "score is null when the measure is not defined; chance_percentile, p and p_holm are null when the "
            "results file says NOT ESTIMABLE (fewer than 100 usable realisations). Such a test does not survive.",
    "analysis": "primary, or one of the three checks declared in advance: S1 without field type 0, S2 four field "
                "types, S3 the all-rows field types",
}
_FIELD_TYPE_FILES = {"odisha_phase3_0_field_types.csv": "", "odisha_phase3_0_field_types_k4.csv": "S2",
                     "odisha_phase3_0_field_types_allrows.csv": "S3"}
_NUM = r"[+-]?(?:\d+\.\d+|nan)"


def _num(text: str) -> float | None:
    v = float(text)
    return None if v != v else v


def _analysis(field_types_file: str, excluded: str, path: Path) -> str:
    """primary, S1, S2 or S3, from what the file says it ran on; stops on anything else."""
    which = _FIELD_TYPE_FILES.get(field_types_file)
    if which == "" and excluded == "":
        return "primary"
    if which == "" and excluded == "0":
        return "S1"
    if which in ("S2", "S3") and excluded == "":
        return which
    raise Refused(f"{path}: field types {field_types_file!r} with excluded type(s) {excluded or 'none'!r} is "
                  "none of the declared analyses (primary, S1, S2, S3).")


def parse_significance(path: Path) -> list[dict[str, Any]]:
    """The headline tests of one odisha_phase3_3_results*.txt, one row per arm and test:
    arm, stand_ceiling_ha, analysis, test, title, score, chance_percentile, p, p_holm,
    holm_family, holm_tests_corrected, n_plots. holm_family is the number of tests the file
    declares in its heading; holm_tests_corrected is the number of rows of its Holm table,
    which is smaller when a test could not be made. Only the five headline rows of each arm are read; the per-district
    rows and the arm comparison are descriptive and are left where they are."""
    path = Path(path)
    lines = path.read_text().splitlines()
    text = "\n".join(lines)
    m = re.search(r"^  \* field types file: (\S+)", text, re.M)
    if not m:
        raise Refused(f"{path} is not a results file of odisha_phase3_3_significance.py.")
    ex = re.search(r"^  \* EXCLUDED field type\(s\): ([\d, ]+?)\s+->", text, re.M)
    analysis = _analysis(m[1], ex[1].replace(" ", "") if ex else "", path)
    fam = re.search(r"^MULTIPLE COMPARISONS -- Holm over the (\d+) headline tests", text, re.M)
    if not fam:
        raise Refused(f"{path} has no Holm table: the run did not finish.")
    holm_family = int(fam[1])

    # plot counts per arm label, from the lines printed before the nulls are drawn
    counts: dict[str, dict[str, int]] = {}
    for ln in lines:
        if c := re.match(r"  \[(.+?)\] plots with a stand (\d+), with a stand type (\d+)(.*)", ln):
            d = counts.setdefault(c[1].lower(), {})
            d["stand"], d["typed"] = int(c[2]), int(c[3])
            if s := re.search(r"SCORED after the exclusion: (\d+) and (\d+)", c[4]):
                d["stand"], d["typed"] = int(s[1]), int(s[2])
            if s := re.search(r"multi-plot stands \d+ holding (\d+) plots", c[4]):
                d["multi"] = int(s[1])
        elif c := re.match(r"  \[(.+?)\] multi-plot stands \d+ holding (\d+) scored plots", ln):
            counts.setdefault(c[1].lower(), {})["multi"] = int(c[2])

    # the Holm table, keyed "<arm label>: <statistic label>" as the script prints it
    holm: dict[str, float] = {}
    at = next(i for i, ln in enumerate(lines) if ln.startswith("MULTIPLE COMPARISONS -- Holm"))
    for ln in lines[at:]:
        if ln.startswith("WHAT THIS SAYS"):
            break
        if h := re.match(rf"    (\S.*?: .*?\S)\s+({_NUM})\s+({_NUM})(?:  <- survives)?\s*$", ln):
            holm[h[1].lower()] = float(h[3])

    by_label = {label: test for test, (label, _, _) in TESTS.items()}
    rows: list[dict[str, Any]] = []
    arm = arm_label = None
    for ln in lines:
        if h := re.match(r"(.+) ARM \((\w+), merged layer\) -- observed vs rotation null$", ln):
            arm_label, arm = h[1].lower(), h[2]
            if arm not in ARMS:
                raise Refused(f"{path}: unknown arm {arm!r}.")
            if arm_label not in counts or len(counts[arm_label]) != 3:
                raise Refused(f"{path}: no plot counts found for the {h[1]} arm.")
            continue
        if ln.startswith("ARM COMPARISON") or ln.startswith("MULTIPLE COMPARISONS"):
            arm = None
        # a headline row: exactly four spaces, then one of the five labels (district rows have six)
        r = re.match(rf"    (\S.*?\S)\s+({_NUM}) \| (.*)$", ln)
        if arm is None or not r or r[1] not in by_label:
            continue
        test = by_label[r[1]]
        est = re.match(rf"{_NUM} \[{_NUM}, {_NUM}\]\s+({_NUM})\s+({_NUM})\s+\d+\s*$", r[3])
        if not est and "NOT ESTIMABLE" not in r[3]:
            raise Refused(f"{path}: cannot read the row {ln.strip()!r}.")
        n = counts[arm_label]
        key = f"{arm_label}: {r[1]}".lower()
        if est and _num(r[2]) is not None and key not in holm:
            raise Refused(f"{path}: the Holm table has no row for {key!r}.")
        rows.append({
            "arm": ARMS[arm]["ui_arm"], "stand_ceiling_ha": ARMS[arm]["ceiling_ha"], "analysis": analysis,
            "test": test, "title": TESTS[test][2], "score": _num(r[2]),
            "chance_percentile": _num(est[1]) if est else None, "p": _num(est[2]) if est else None,
            "p_holm": holm.get(key) if est else None,
            "holm_family": holm_family, "holm_tests_corrected": len(holm),
            "n_plots": {"drawing_all_plots": n["stand"], "drawing_shared_stands": n["multi"],
                        "same_stand_precision": n["multi"]}.get(test, n["typed"]),
        })
    per_arm = {(r["arm"], r["stand_ceiling_ha"]) for r in rows}
    if not rows or len(rows) != len(TESTS) * len(per_arm) or holm_family != len(rows):
        raise Refused(f"{path}: expected the five headline rows of each arm and a Holm family of that size; found "
                      f"{len(rows)} row(s) for {len(per_arm)} arm(s) and a family of {holm_family}.")
    if sum(r["p_holm"] is not None for r in rows) != len(holm):
        raise Refused(f"{path}: the Holm table has {len(holm)} row(s), and "
                      f"{sum(r['p_holm'] is not None for r in rows)} of them belong to a headline test read above.")
    return rows


def parse_score(path: Path) -> list[dict[str, Any]]:
    """The five measures as one odisha_phase3_1_score_*.txt gives them, one row per test: arm,
    stand_ceiling_ha, analysis, test, title, score, n_plots. No chance level: that file has none.
    The two drawing scores and labelling are the printed ARIs. Same-stand precision and the
    far-apart gap are worked out from the printed pair counts (the file prints the first to
    3 decimals and the second not at all), so that each can be set beside the chance test's
    value. A measure the file does not report is given with score null."""
    path = Path(path)
    lines = path.read_text().splitlines()
    text = "\n".join(lines)
    head = re.search(r"^PHASE 3 STEP 1 -- pairwise score, arm=(\w+) layer=merged set=districts$", text, re.M)
    ft = re.search(r"^  field types file: (\S+)", text, re.M)
    if not head or not ft or head[1] not in ARMS:
        raise Refused(f"{path} is not a merged-layer score file of odisha_phase3_1_pairwise_score.py for a known arm.")
    arm = head[1]
    ex = re.search(r"^  EXCLUDED field type\(s\): ([\d, ]+?)\s+->", text, re.M)
    analysis = _analysis(ft[1], ex[1].replace(" ", "") if ex else "", path)
    n_stand = re.search(r"^  plots with a stand: (\d+)", text, re.M)
    if not n_stand:
        raise Refused(f"{path}: no 'plots with a stand' line; the arm is not in the plot table it was scored from.")
    with_stand = int(n_stand[1])
    multi = re.search(r"multi-plot stands: \d+ holding (\d+) plots", text)
    untyped = re.search(r"^  (\d+) assigned plot\(s\) carry no type label", text, re.M)
    typed = with_stand - (int(untyped[1]) if untyped else 0)

    # each block: its title line, then the 2x2 pair counts, then its ARI
    blocks: dict[str, dict[str, Any]] = {}
    title = ""
    for k, ln in enumerate(lines):
        if re.match(r"\s+pairs [\d,]+\s+field-alike", ln):
            title = lines[k - 1].strip().split("  (")[0]
            blocks[title] = {}
        elif title and (c := re.match(r"\s+field (alike|differs)\s+([\d,]+)\s+([\d,]+)\s*$", ln)):
            blocks[title][c[1]] = (int(c[2].replace(",", "")), int(c[3].replace(",", "")))
        elif title and (a := re.match(rf"\s+>>> ARI ({_NUM}|n/a)", ln)):
            blocks[title]["ari"] = None if a[1] == "n/a" else _num(a[1])
            title = ""

    everyone = blocks.get("all pairs", {})
    shared = blocks.get("restricted to plots in multi-plot stands", {})
    lab = blocks.get("same-district pairs", {})
    far = next((b for t, b in blocks.items() if t.startswith("same-district pairs more than")), {})
    prec = gap = None
    if "alike" in everyone and (same := everyone["alike"][0] + everyone["differs"][0]):
        prec = everyone["alike"][0] / same
    if "alike" in far and sum(far["alike"]) and sum(far["differs"]):
        gap = far["alike"][0] / sum(far["alike"]) - far["differs"][0] / sum(far["differs"])
    scores = {"drawing_all_plots": (everyone.get("ari"), with_stand),
              "drawing_shared_stands": (shared.get("ari"), int(multi[1]) if multi else 0),
              "same_stand_precision": (prec, int(multi[1]) if multi else 0),
              "labelling": (lab.get("ari"), typed), "labelling_far_apart": (gap, typed)}
    return [{"arm": ARMS[arm]["ui_arm"], "stand_ceiling_ha": ARMS[arm]["ceiling_ha"], "analysis": analysis,
             "test": test, "title": TESTS[test][2], "score": scores[test][0], "n_plots": scores[test][1]}
            for test in TESTS]


def _cell(v: float | None, fmt: str, none: str = "not estimable") -> str:
    return none if v is None else format(v, fmt).replace("-", "−")


def markdown_tables(rows: list[dict[str, Any]]) -> str:
    """One table per arm and stand size: every analysis and test with its score, percentile of
    chance, p and Holm-corrected p. Tables only; the prose around them is written elsewhere."""
    names = {"feature_vector": "Hand-crafted features", "alphaearth": "AlphaEarth"}
    short = {t: name for t, (_, name, _) in TESTS.items()}
    out: list[str] = []
    for arm, ceiling in dict.fromkeys((r["arm"], r["stand_ceiling_ha"]) for r in rows):
        mine = [r for r in rows if (r["arm"], r["stand_ceiling_ha"]) == (arm, ceiling)]
        fam = sorted({r["holm_family"] for r in mine})
        # a file with a test that could not be made corrects over fewer tests than it declares:
        # the heading then says so, and each Holm value of such a file carries its own number
        fewer = any(r["holm_tests_corrected"] != r["holm_family"] for r in mine)
        over = f"over {' or '.join(map(str, fam))} tests" + (", or over the number in the cell" if fewer else "")
        out += [f"### {names[arm]}, stands of at most {ceiling} hectares", "",
                f"| Analysis | Score | Real stand map | Percentile of chance | p | p after Holm ({over}) | Plots |",
                "|---|---|---|---|---|---|---|"]
        for r in mine:
            holm = _cell(r["p_holm"], ".3f")
            if r["p_holm"] is not None and r["holm_tests_corrected"] != r["holm_family"]:
                holm += f" (over {r['holm_tests_corrected']} tests)"
            out.append(f"| {r['analysis']} | {short[r['test']]} | {_cell(r['score'], '.4f', 'not defined')} | "
                       f"{_cell(r['chance_percentile'], '.1f')} | {_cell(r['p'], '.3f')} | "
                       f"{holm} | {r['n_plots']} |")
        out.append("")
    return "\n".join(out)


def collect(out_dir: Path, json_path: Path | None, markdown_path: Path | None) -> int:
    """Read every chance-test results file of the declared draws in out_dir and write the rows.

    --json      {"notes": {...}, "sources": [...], "rows": [...]}; each row is
                {"arm": "feature_vector" | "alphaearth", "stand_ceiling_ha": 3 | 10,
                 "analysis": "primary" | "S1" | "S2" | "S3", "test", "title", "score",
                 "chance_percentile", "p", "p_holm", "holm_family": 10 | 5,
                 "holm_tests_corrected", "n_plots"}.
                Someone else adds the label and the reading for ui_data/fes_comparison.json.
    --markdown  a table per arm and stand size, for docs/demo/fes_comparison.md.
    Files with _rot or _boot in their name are test runs and are left out, by name. Where the
    scorer's own file for the same arm and analysis is in the folder, each score must agree
    with it to the 4 decimals printed, or nothing is written: the two files would then come
    from different plot tables."""
    out_dir = out_dir.resolve()
    files = sorted(out_dir.glob("odisha_phase3_3_results*.txt"))
    test_runs = [p.name for p in files if re.search(r"_(rot|boot)\d", p.name)]
    files = [p for p in files if p.name not in test_runs]
    if not files:
        raise Refused(f"{out_dir} holds no odisha_phase3_3_results*.txt of the declared draws.")
    rows: list[dict[str, Any]] = []
    source: dict[tuple, str] = {}
    for p in files:
        for r in parse_significance(p):
            key = (r["arm"], r["stand_ceiling_ha"], r["analysis"], r["test"])
            if key in source:
                raise Refused(f"{p.name} and {source[key]} both test {key[:3]}: one arm and analysis, two Holm "
                              "families. Remove the file that is not the declared run.")
            source[key] = p.name
            rows.append(r)
    order = {(a["ui_arm"], a["ceiling_ha"]): i for i, a in enumerate(ARMS.values())}
    rows.sort(key=lambda r: (order[(r["arm"], r["stand_ceiling_ha"])], [n for n, _, _ in ANALYSES].index(r["analysis"]),
                             list(TESTS).index(r["test"])))

    checked = 0
    for p in sorted(out_dir.glob("odisha_phase3_1_score_*_merged_districts*.txt")):
        for s in parse_score(p):
            key = (s["arm"], s["stand_ceiling_ha"], s["analysis"], s["test"])
            mine = next((r for r in rows if (r["arm"], r["stand_ceiling_ha"], r["analysis"], r["test"]) == key), None)
            if mine is None or s["score"] is None or mine["score"] is None:
                continue
            checked += 1
            if abs(s["score"] - mine["score"]) > 0.00006:      # both sides rounded to 4 decimals
                raise Refused(f"{p.name} gives {s['score']:+.4f} for {key}, and {source[key]} gives "
                              f"{mine['score']:+.4f}. The two files do not come from the same plot table.")

    print(f"read {len(rows)} rows from {len(files)} results file(s) in {out_dir}; "
          f"{checked} score(s) agree with the scorer's own files")
    for name in test_runs:
        print(f"  left out (a test run, not the declared draws): {name}")
    if json_path is not None:
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps({"notes": ROW_NOTES, "sources": [p.name for p in files], "rows": rows},
                                        indent=1) + "\n")
        print(f"  wrote {json_path}")
    if markdown_path is not None:
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(markdown_tables(rows))
        print(f"  wrote {markdown_path}")
    return 0


# --------------------------------------------------------------------------- main
def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0],
                                 epilog="See the top of this file for what is read, run and written.")
    ap.add_argument("--stands-dir", type=Path, default=None,
                    help="folder holding <config>_<district><suffix>_stands_merged.geojson for the arms asked for")
    ap.add_argument("--suffix", default="_repro", help="what the stand files' config names end in (default _repro)")
    ap.add_argument("--fallback-vectors", type=Path, default=Path("outputs/repro_runs/phase2_vectors"),
                    help="where a _stands_snic or _stands_dissolved file is taken from when --stands-dir has none "
                         "(default outputs/repro_runs/phase2_vectors, same suffix)")
    ap.add_argument("--out-dir", type=Path, default=HERE / "phase3_demo",
                    help="where everything is written (default odisha_script/phase3_demo)")
    ap.add_argument("--merge-rule", default=None,
                    help="the rule the stands were merged under, as the AlphaEarth declaration writes it: the "
                         "register id, or 'before the merge fix'. Written into the manifest")
    ap.add_argument("--arms", default=",".join(ARMS), help=f"comma-separated subset of {','.join(ARMS)} (default all)")
    ap.add_argument("--rotations", type=int, default=N_ROT, help=f"rotation-null realisations (default {N_ROT}, as declared)")
    ap.add_argument("--boot", type=int, default=N_BOOT, help=f"bootstrap draws of the arm comparison (default {N_BOOT})")
    ap.add_argument("--jobs", type=int, default=4, help="chance tests run at the same time (default 4)")
    ap.add_argument("--steps", default=",".join(STEPS), help=f"comma-separated subset of {','.join(STEPS)} (default all)")
    ap.add_argument("--dry-run", action="store_true",
                    help="stage, check every input and print the commands; run and write nothing")
    ap.add_argument("--replace-committed", action="store_true",
                    help="allow this run to replace result files of its own that are committed to git")
    ap.add_argument("--collect", action="store_true",
                    help="do not run anything: read the result files in --out-dir and write --json and --markdown")
    ap.add_argument("--json", type=Path, default=None, help="with --collect: where the rows for the UI go")
    ap.add_argument("--markdown", type=Path, default=None, help="with --collect: where the tables go")
    args = ap.parse_args(argv)
    if args.collect:
        if args.json is None and args.markdown is None:
            raise Refused("--collect needs --json, --markdown or both.")
        return collect(args.out_dir, args.json, args.markdown)
    if args.json is not None or args.markdown is not None:
        raise Refused("--json and --markdown go with --collect.")
    return run(args, argv)


if __name__ == "__main__":
    sys.exit(main())

"""Score each R3 set as soon as its four runs are exported (Jaskaran, 28 Oct 2026: "Score each set
(each arm at each stand size) as soon as its runs are exported, without waiting for the others, and
run the chance tests of different sets in parallel (offline)."; register
process-r14-score-each-set-as-exported; the round 14 record, Done, the plan changed to finish today).

It reads R3's second half's batch log (label r14_second_half) from the given byte on, every 30
seconds. When the export passes of all four runs of a set have ended with exit 0 ("--- PASS<n> <run>
export exit=0 ---"), it does for that set, in order, each step only if the one before it worked:
  1. each run's records copied from the run tree (scripts/copy_run_results.py, export mode, run from
     the run tree as every copy of the round) into docs/reproducibility/r14_runs/second_half/, files
     over 5 MB into outputs/round14/results/second_half/; then each run's eight stage files and the
     elbow's run record looked for there (the record's rule after each export-mode copy: a missing
     one is copied in by hand by that rule, and the set scored then);
  2. the declared field check, odisha_script/odisha_keptland_score.py --runs <the set's runs>
     --stem keptland_<set>_r14 --stands-dir docs/reproducibility/r14_runs/second_half;
  3. the declared chance test, started in a process of its own and not waited on before the next
     set: odisha_script/odisha_keptland_chance.py --stands-from geojson --stands-dir
     docs/reproducibility/r14_runs/second_half --runs <the set's runs> --scored-stem
     keptland_<set>_r14 --declared.
Steps 2 and 3 are the _r9 sets' commands (their run records in odisha_script/keptland_scores/) with
_r14 in place of _r9 and the second half's records in place of the _r9 ones; they run from the main
repo, as those did (the field check's box runs are read from its outputs/), once it has no modified
tracked file (so that their run records are clean), and write into odisha_script/keptland_scores/.
Sanjay Van's two runs (no plots, no score) are copied as soon as both are exported. A step that
fails is logged and the set's later steps are not run; the other sets go on. It ends once the batch
has ended (its "batch r14_second_half ended" line) and every chance test it started has ended,
naming the sets not exported. Each step, its command, its exit code and the time go to --out (the
chance tests' own output to outputs/round14/logs/<stem>_chance_console.log; each writes its log and
results beside the _r9 ones). It never calls Earth Engine. --dry-run logs each command and runs none,
to try the triggers on a made-up log.

    python odisha_script/r14_second_half/score_as_exported.py --batch-log <logs>/r14_second_half.log
        --from-byte N --out <logs>/r14_second_half_scorer.log
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path("/Users/karan/Desktop/phd-code")
RT = REPO / "outputs" / "round14" / "run_tree_5"
PY = str(REPO / ".venv" / "bin" / "python")
DEST = REPO / "docs" / "reproducibility" / "r14_runs" / "second_half"
OFF = REPO / "outputs" / "round14" / "results" / "second_half"
LOGS = REPO / "outputs" / "round14" / "logs"
DISTRICTS = ("angul", "dhenkanal", "kendujhar", "koraput")
LABEL = "r14_second_half"
POLL_S = 30
CLEAN_WAIT_S = 600
STAGE_FILES = ("k_elbow.csv", "k_elbow_stand_table.csv", "k_elbow_fit_rows.csv", "k_elbow_types.csv",
               "k_elbow_preprocessing.json", "clustering_stand_table.csv", "clustering_fit_rows.csv",
               "clustering_kmeans.json", "k_elbow_run.json")
# Each set: its stem, the pattern of its runs (as the _r9 set's, with _r14), and whether it is scored.
SETS = {
    "keptland_s1desc_r14": ("odisha_v120_3ha_squares_{district}_keptland_s1desc_r14", True),
    "keptland_alphaearth_r14": ("odisha_alphaearth_3ha_squares_{district}_keptland_r14", True),
    "keptland_alphaearth_10ha_r14": ("odisha_alphaearth_10ha_squares_{district}_keptland_r14", True),
    "keptland_s1desc_10ha_r14": ("odisha_v120_10ha_squares_{district}_keptland_s1desc_r14", True),
    "sanjay_van_r14": ("", False),
}
SANJAY_VAN = ("sanjay_van_baseline_keptland_r14", "sanjay_van_alphaearth_keptland_r14")

ap = argparse.ArgumentParser()
ap.add_argument("--batch-log", type=Path, required=True)
ap.add_argument("--from-byte", type=int, required=True)
ap.add_argument("--out", type=Path, required=True)
ap.add_argument("--dry-run", action="store_true", help="log each command and run none (to try the triggers)")
args = ap.parse_args()
exported = re.compile(r"^--- PASS\d+ (\S+) export exit=0 ---$")
ended = f"] batch {LABEL} ended:"


def say(msg: str) -> None:
    with args.out.open("a") as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S %Z')}] {msg}\n")


def runs_of(stem: str) -> list[str]:
    pattern, _ = SETS[stem]
    return [pattern.format(district=d) for d in DISTRICTS] if pattern else list(SANJAY_VAN)


def run(cmd: list[str], cwd: Path, env_path: str | None = None) -> int:
    say(f"  run (in {cwd}): {' '.join(cmd)}")
    if args.dry_run:
        return 0
    env = None if env_path is None else dict(os.environ, PYTHONPATH=env_path)
    p = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    for line in (p.stdout + p.stderr).strip().splitlines()[-6:]:
        say(f"    | {line}")
    say(f"  exit {p.returncode}")
    return p.returncode


def wait_clean() -> str:
    """The main repo's HEAD once it has no modified tracked file (waits up to ten minutes)."""
    if args.dry_run:
        return "dry-run"
    t0 = time.time()
    while True:
        st = subprocess.run(["git", "-C", str(REPO), "status", "--porcelain", "--untracked-files=no"],
                            capture_output=True, text=True).stdout.strip()
        head = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True,
                              text=True).stdout.strip()
        if not st:
            return head
        if time.time() - t0 > CLEAN_WAIT_S:
            say(f"  the main repo still has modified tracked files after ten minutes ({st.splitlines()[:3]}); "
                f"going on: the run record will say dirty")
            return head
        time.sleep(15)


def copy_set(stem: str) -> bool:
    if not args.dry_run:
        DEST.mkdir(parents=True, exist_ok=True)
        OFF.mkdir(parents=True, exist_ok=True)
    for r in runs_of(stem):
        rc = run([PY, "scripts/copy_run_results.py", str(RT), r, "--dest", str(DEST), "--off-git", str(OFF)],
                 cwd=RT, env_path=str(RT / "src"))
        if rc != 0:
            say(f"{stem}: the copy of {r} FAILED; the set is not scored")
            return False
    missing = [f"{r}_{f}" for r in runs_of(stem) for f in STAGE_FILES
               if not args.dry_run and not (DEST / f"{r}_{f}").exists() and not (OFF / f"{r}_{f}").exists()]
    if missing:
        say(f"{stem}: MISSING after the copy: {missing}; copy each in by the record's rule, then score the "
            f"set by hand (the commands below)")
        return False
    say(f"{stem}: copied, every stage file and the elbow's run record there")
    return True


def main() -> int:
    pos, rest = args.from_byte, b""
    done_runs: set[str] = set()
    state = {s: "waiting" for s in SETS}
    chance: dict[str, subprocess.Popen] = {}
    batch_ended = False
    say(f"started: the batch log {args.batch_log} from byte {args.from_byte}; sets {list(SETS)}")
    while True:
        with args.batch_log.open("rb") as f:
            f.seek(pos)
            chunk = f.read()
        pos += len(chunk)
        *lines, rest = (rest + chunk).split(b"\n")
        for raw in lines:
            line = raw.decode(errors="replace").strip()
            m = exported.match(line)
            if m:
                done_runs.add(m.group(1))
                say(f"exported: {m.group(1)}")
            if ended in line:
                batch_ended = True
                say(f"the batch ended: {line!r}")
        for stem, (pattern, scored) in SETS.items():
            if state[stem] != "waiting" or not all(r in done_runs for r in runs_of(stem)):
                continue
            say(f"{stem}: its runs are all exported")
            if not copy_set(stem):
                state[stem] = "copy failed"
                continue
            if not scored:
                state[stem] = "copied"
                continue
            head = wait_clean()
            say(f"{stem}: the field check, from the main repo at {head[:7]}")
            if run([PY, "odisha_script/odisha_keptland_score.py", "--runs", pattern, "--stem", stem,
                    "--stands-dir", str(DEST.relative_to(REPO))], cwd=REPO) != 0:
                state[stem] = "field check failed"
                continue
            head = wait_clean()
            cmd = [PY, "odisha_script/odisha_keptland_chance.py", "--stands-from", "geojson", "--stands-dir",
                   str(DEST.relative_to(REPO)), "--runs", pattern, "--scored-stem", stem, "--declared"]
            say(f"{stem}: the chance test started, from the main repo at {head[:7]}: {' '.join(cmd)}")
            out = ((args.out.parent if args.dry_run else LOGS) / f"{stem}_chance_console.log").open("a")
            chance[stem] = subprocess.Popen(["true"] if args.dry_run else cmd, cwd=REPO, stdout=out,
                                            stderr=subprocess.STDOUT, start_new_session=True)
            state[stem] = "chance test running"
        for stem, p in list(chance.items()):
            if state[stem] == "chance test running" and p.poll() is not None:
                state[stem] = f"chance test ended, exit {p.returncode}"
                say(f"{stem}: the chance test ended, exit {p.returncode}")
        if batch_ended and all(not s.startswith("chance test running") for s in state.values()):
            for stem, s in state.items():
                if s == "waiting":
                    s = f"NOT EXPORTED: {sum(r in done_runs for r in runs_of(stem))} of its {len(runs_of(stem))} runs exported"
                say(f"at the end: {stem}: {s}")
            return 0 if all(s in ("copied", "chance test ended, exit 0") for s in state.values()) else 1
        time.sleep(POLL_S)


if __name__ == "__main__":
    sys.exit(main())

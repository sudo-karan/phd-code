"""Run run_config_passes.sh one pass at a time, never while earlier tasks are still queued.

    python odisha_script/run_passes_safely.py --label <name> [--run-tree <dir>] [--log-dir <dir>]
        [--passes 3] <config.yaml> [<config.yaml> ...]

WHY THIS EXISTS
---------------
run_config_passes.sh repeats a config until it completes, sleeping 60 s between passes. A
stage that fails partway through (the expected "User memory limit exceeded" on a cold
cache) returns WITHOUT waiting for the exports it has already submitted, and the cache
check looks only for finished assets. On a slow queue the next pass therefore submits a
second copy of every export that is still running. CLAUDE.md says never to start it again
while tasks from an earlier start are still queued; its pass loop can break that rule by
itself.

So this wrapper calls it with MAX_PASSES=1 and, before every pass, waits until Earth
Engine has no queued or running task whose description starts with the name of a config it
is about to run. It sets RUN_PASSES_SAFELY=1 for the script (`pass_env`), which refuses to
start without it (round 12), so the script is started only from here. It also:

  - never re-runs a config that has finished. The export stage submits its Drive exports
    every time it runs, so re-running a finished config would duplicate them. A batch started
    again under the same label reads <label>.state.json first, and skips, with a log line,
    every config an earlier batch of the label finished or put under needs attention (round
    13, review B4). To run one of those again, use another label;
  - does not retry a config whose EXPORT stage failed: Drive exports may already have been
    submitted, so a person should read the log first;
  - allows one batch at a time (a lock file holding a live pid);
  - runs from a "run tree": a checkout whose tracked files are unmodified. A multi-hour run
    started from a working tree that is being edited executes whatever half-finished code
    is on disk when each stage starts. Use a clean clone pinned to one commit;
  - writes the commit it ran from, and each pass's per-stage exit codes, to
    <log-dir>/<label>.state.json beside the log, after the record of the label's earlier
    batches. A pass cut short (Ctrl-C) still records the configs it finished.

Run from anywhere; the run tree needs its own .env (the pipeline reads .env from the working
directory). NEEDS LIVE EARTH ENGINE and submits tasks.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ACTIVE_STATES = ("PENDING", "RUNNING", "CANCELLING")
STAGE_EXIT = re.compile(r"^--- PASS1 (\S+) (features|segmentation|clustering|export) exit=(\d+) ---$")
POLL_S = 60
# The variable run_config_passes.sh checks before it does anything (round 12).
STARTED_BY_THE_WRAPPER = "RUN_PASSES_SAFELY"


def pass_env(python: str, run_tree: Path) -> dict[str, str]:
    """The environment run_config_passes.sh runs in: one pass, this interpreter, the run tree's
    code, and RUN_PASSES_SAFELY=1, without which the script refuses to start."""
    return dict(os.environ, PYTHON=python, MAX_PASSES="1", PYTHONPATH=str(run_tree / "src"),
                **{STARTED_BY_THE_WRAPPER: "1"})


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("configs", nargs="+", help="config paths, relative to the run tree")
    ap.add_argument("--label", required=True, help="names the log, the state file and the lock")
    ap.add_argument("--run-tree", type=Path, default=Path(__file__).resolve().parent.parent,
                    help="checkout to run from (default: the one holding this script)")
    ap.add_argument("--log-dir", type=Path, default=None,
                    help="where the log and state file go (default <run-tree>/logs)")
    ap.add_argument("--passes", type=int, default=3)
    ap.add_argument("--python", default=sys.executable)
    args = ap.parse_args()

    rt = args.run_tree.resolve()
    log_dir = (args.log_dir or rt / "logs").resolve()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{args.label}.log"
    state_path = log_dir / f"{args.label}.state.json"
    lock = log_dir / "run_passes_safely.lock"

    def say(msg: str) -> None:
        line = f"[run_passes_safely {time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
        print(line, flush=True)
        with log_path.open("a") as f:
            f.write(line + "\n")

    if lock.exists():
        try:
            os.kill(int(lock.read_text().strip()), 0)
            print(f"REFUSING: a batch with pid {lock.read_text().strip()} is still running")
            return 90
        except (ProcessLookupError, ValueError):
            pass  # a stale lock from a batch that has ended
    # Tracked files only: finished runs leave untracked outputs behind, and those are not code.
    modified = subprocess.run(
        ["git", "-C", str(rt), "status", "--porcelain", "--untracked-files=no"],
        capture_output=True, text=True, check=True).stdout.strip()
    if modified:
        print("REFUSING: the run tree has modified tracked files:\n" + modified)
        return 92
    commit = subprocess.run(["git", "-C", str(rt), "rev-parse", "HEAD"],
                            capture_output=True, text=True, check=True).stdout.strip()
    for c in args.configs:
        if not (rt / c).exists():
            print(f"REFUSING: {c} does not exist in the run tree at {commit[:7]}")
            return 94
    name_of = {c: Path(c).stem for c in args.configs}
    # The earlier batches of this label (review B4): a config one of them finished, or put under
    # needs attention, is not run again. Read before anything is written, so that a state file
    # that cannot be read stops the batch here and is left as it is.
    earlier: list[dict] = []
    if state_path.exists():
        last = json.loads(state_path.read_text())
        earlier = [*last.pop("earlier_batches", []), last]
    done_before: dict[str, str] = {}  # config -> the commit of the batch that finished it
    attention_before: dict[str, str] = {}  # config -> why it needs attention
    for b in earlier:
        c7 = str((b.get("git") or {}).get("commit") or b.get("commit") or "")[:7]
        done_before.update({n: c7 for n in b.get("done", [])})
        attention_before.update(b.get("needs_attention", {}))
    skipped: dict[str, str] = {}
    for c in args.configs:
        if name_of[c] in done_before:
            skipped[c] = (f"an earlier batch of label {args.label} finished it "
                          f"(commit {done_before[name_of[c]]})")
        elif name_of[c] in attention_before:
            skipped[c] = (f"an earlier batch of label {args.label} put it under needs attention "
                          f"({attention_before[name_of[c]]})")

    os.chdir(rt)  # fmu reads .env from the working directory
    sys.path.insert(0, str(rt / "src"))  # the run tree's code, not an editable install elsewhere
    import ee

    from fmu.settings import get_settings
    ee.Initialize(project=get_settings().gee_project_id)

    def active(names: list[str]) -> list[str]:
        out = []
        for op in ee.data.listOperations():
            md = op.get("metadata", {})
            d = md.get("description", "")
            if md.get("state") in ACTIVE_STATES and any(d.startswith(n) for n in names):
                out.append(d)
        return out

    def wait_until_idle(names: list[str], why: str) -> None:
        last_said = 0.0
        while True:
            try:
                a = active(names)
            except Exception as e:  # noqa: BLE001 - a failed poll is retried, never read as "idle"
                say(f"queue check failed ({str(e)[:120]}); retrying in {POLL_S} s")
                time.sleep(POLL_S)
                continue
            if not a:
                return
            if time.time() - last_said > 600:
                say(f"{why}: {len(a)} task(s) of these configs still queued or running; "
                    f"waiting (for example {a[0]})")
                last_said = time.time()
            time.sleep(POLL_S)

    remaining = [c for c in args.configs if c not in skipped]
    done: list[str] = []
    attention: dict[str, str] = {}
    history: list[dict] = []
    running: list[int] = []  # the pass whose exit lines are not yet read, and its first log line

    def save() -> None:
        state_path.write_text(json.dumps({
            "label": args.label,
            "git": {"commit": commit, "dirty": False},
            "configs": [name_of[c] for c in args.configs],
            "done": [name_of[c] for c in done],
            "needs_attention": {name_of[c]: why for c, why in attention.items()},
            "not_finished": [name_of[c] for c in remaining],
            "passes": history,
            "skipped": {name_of[c]: why for c, why in skipped.items()},
            "earlier_batches": earlier,
        }, indent=1))

    def read_pass(p: int, rc: int | None, n0: int) -> None:
        """The pass's exit lines, from line n0 of the log on: a config whose export stage exited 0
        is done, one whose export stage failed needs attention."""
        exits: dict[str, dict[str, int]] = {}
        for line in log_path.read_text().splitlines()[n0:]:
            m = STAGE_EXIT.match(line.strip())
            if m:
                exits.setdefault(m.group(1), {})[m.group(2)] = int(m.group(3))
        history.append({"pass": p, "exit": rc, "stage_exits": exits})
        for c in list(remaining):
            st = exits.get(name_of[c], {})
            if st.get("export") == 0:
                done.append(c)
                remaining.remove(c)
            elif "export" in st:
                attention[c] = f"export stage exited {st['export']} in pass {p}; not retried"
                remaining.remove(c)
        save()

    lock.write_text(str(os.getpid()))
    try:
        say(f"batch {args.label} started from commit {commit} (tracked files unmodified); "
            f"{len(args.configs)} config(s), up to {args.passes} pass(es)")
        for c, why in skipped.items():
            say(f"{name_of[c]}: skipped, {why}")
        env = pass_env(args.python, rt)
        for p in range(1, args.passes + 1):
            if not remaining:
                break
            names = [name_of[c] for c in remaining]
            wait_until_idle(names, f"before pass {p}")
            n0 = len(log_path.read_text().splitlines())
            say(f"pass {p}: {' '.join(names)}")
            running[:] = [p, n0]
            rc = subprocess.run(
                ["bash", "odisha_script/run_config_passes.sh", str(log_path), *remaining],
                cwd=rt, env=env).returncode
            running.clear()
            read_pass(p, rc, n0)
            say(f"pass {p} exit={rc}; finished: {[name_of[c] for c in done]}; "
                f"not finished: {[name_of[c] for c in remaining]}; "
                f"needs attention: {[name_of[c] for c in attention]}")
        held_back = [c for c in skipped if name_of[c] not in done_before]
        ok = not remaining and not attention and not held_back
        say(f"batch {args.label} ended: {'ALL CONFIGS COMPLETE' if ok else 'NOT ALL COMPLETE'}")
        return 0 if ok else 1
    finally:
        if running:  # a pass cut short (Ctrl-C): the configs it finished are done all the same
            read_pass(running[0], None, running[1])
        save()
        lock.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())

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
is about to run (its name:, after which the pipeline names every task of it). It sets
RUN_PASSES_SAFELY=1 for the script (`pass_env`), which refuses to start without it (round
12), so the script is started only from here. It also:

  - knows each config by its name:, which it reads with the run tree's fmu.config, and
    refuses (exit 93) a config whose name: differs from its file stem (run_config_passes.sh
    names the exit lines after the stem), a path that does not end in .yaml, and a name
    listed twice (round 13, review B8);
  - never re-runs a config that has finished. The export stage submits its Drive exports
    every time it runs, so re-running a finished config would duplicate them. A batch started
    again under the same label reads <label>.state.json first, and skips, with a log line,
    every config an earlier batch of the label finished or put under needs attention (round
    13, review B4). To run one of those again, use another label;
  - does not retry a config whose EXPORT stage failed: Drive exports may already have been
    submitted, so a person should read the log first. The same holds for an export stage that
    started and has no exit line, because a signal or an error cut the pass short while it ran
    (round 13, a check of the B4 fix);
  - allows one batch at a time on this machine: before anything else it takes an exclusive
    lock (fcntl.flock) on ~/.fmu/run_passes_safely.lock, whatever the run tree or the log
    folder, and refuses to start (exit 90) while another batch holds it. The kernel lets go
    of the lock when the batch ends, however it ends (round 13, review B6 and B7). The shell
    script and the runner hold it too, so it is free only once every process of the batch
    has ended, even if this wrapper is killed with kill -9 (B5);
  - passes SIGTERM, SIGHUP and SIGINT (Ctrl-C) on to the shell script and the runner, which
    run in a process group of their own, waits for them to end, records the pass and stops
    (exit 128 plus the signal's number). A signal that was ignored when the batch started
    (nohup, or SIGINT in a background job) stays ignored (round 13, review B5);
  - runs from a "run tree": a checkout whose tracked files are unmodified. A multi-hour run
    started from a working tree that is being edited executes whatever half-finished code
    is on disk when each stage starts. Use a clean clone pinned to one commit;
  - reads the run tree's commit and modified tracked files again before and after each pass,
    and starts no pass on a tree that has changed since the batch started (its commit moved,
    or a tracked file is modified): the configs left are not finished, and it stops (exit 95).
    Until round 13 it read the tree once, at the start, so a change while a batch ran was
    not seen, and the next pass ran other code than the passes before it (review C32);
  - writes the run tree's state as the batch started, each pass's per-stage exit codes and
    the tree's state before and after it, and the change that stopped the batch if one did,
    to <log-dir>/<label>.state.json beside the log, after the record of the label's earlier
    batches. A pass cut short (Ctrl-C) still records the configs it finished;
  - counts a config as finished ("done" in the state file, and "ALL CONFIGS COMPLETE" in the
    log once every config is) when its export stage exits 0. That means its Drive exports were
    submitted, not that they completed: nothing in the batch waits on them or records how they
    ended, since the runner's --wait covers cache exports only and the export call is not given
    it (review C39, round 13). Their task ids are in the config's run record (drive_exports);
    their states are on the Earth Engine task list.

Exit codes: 0 every config complete; 1 not all complete (one not finished, or one needing
attention); 90 another batch holds the lock; 92 the run tree has modified tracked files; 93 a
config refused (B8); 94 a config missing from the run tree; 95 the run tree changed while the
batch ran (C32); 128 + n stopped by signal n (129 SIGHUP, 130 Ctrl-C, 143 SIGTERM).

Run from anywhere; the run tree needs its own .env (the pipeline reads .env from the working
directory). NEEDS LIVE EARTH ENGINE and submits tasks.
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

ACTIVE_STATES = ("PENDING", "RUNNING", "CANCELLING")
STAGE_EXIT = re.compile(r"^--- PASS1 (\S+) (features|segmentation|clustering|export) exit=(\d+) ---$")
# The line run_config_passes.sh writes as it starts a stage.
STAGE_START = re.compile(r"^##### PASS1 (\S+) :: (features|segmentation|clustering|export) :: .* #####$")
POLL_S = 60
# The variable run_config_passes.sh checks before it does anything (round 12).
STARTED_BY_THE_WRAPPER = "RUN_PASSES_SAFELY"
# One batch at a time on this machine, whatever its run tree and log folder (review B7).
LOCK_FILE = Path(".fmu") / "run_passes_safely.lock"  # under the home folder
# Passed on to the shell script and the runner (review B5).
STOP_SIGNALS = (signal.SIGTERM, signal.SIGHUP, signal.SIGINT)


def pass_env(python: str, run_tree: Path) -> dict[str, str]:
    """The environment run_config_passes.sh runs in: one pass, this interpreter, the run tree's
    code, and RUN_PASSES_SAFELY=1, without which the script refuses to start."""
    return dict(os.environ, PYTHON=python, MAX_PASSES="1", PYTHONPATH=str(run_tree / "src"),
                **{STARTED_BY_THE_WRAPPER: "1"})


def take_lock(path: Path) -> int | None:
    """The descriptor of an exclusive lock on `path`, or None if another batch holds it.

    The lock is held, not written (review B6): taking it is one step, so two starts cannot both
    pass a check before either writes, and the kernel lets go of it when the last process holding
    the descriptor ends, so a batch that dies leaves no stale lock behind. The pid written into
    the file is only for the message of a start that is refused.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return None
    os.ftruncate(fd, 0)
    os.write(fd, str(os.getpid()).encode())
    return fd


def tree_state(rt: Path, *, check: bool = False) -> dict:
    """The run tree's commit and its modified tracked files, read now. Untracked files are left
    out: finished runs leave untracked outputs behind, and those are not code. With `check`, a git
    command that fails raises; otherwise the failure is recorded under "error"."""
    head = subprocess.run(["git", "-C", str(rt), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=check)
    status = subprocess.run(["git", "-C", str(rt), "status", "--porcelain", "--untracked-files=no"],
                            capture_output=True, text=True, check=check)
    if head.returncode or status.returncode:
        return {"commit": None, "dirty": None, "modified": [],
                "error": (head.stderr or status.stderr).strip()[:300] or "git failed"}
    modified = sorted(line[3:] for line in status.stdout.splitlines() if line.strip())
    return {"commit": head.stdout.strip(), "dirty": bool(modified), "modified": modified, "error": None}


def wait_for_group(pgid: int) -> None:
    """Until no process of the group is left: the runner can outlive the shell script. macOS
    refuses to signal a group of which only zombies are left (EPERM); they run nothing and hold
    no file, so the group has ended."""
    while True:
        try:
            os.killpg(pgid, 0)
        except (ProcessLookupError, PermissionError):
            return
        time.sleep(0.1)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("configs", nargs="+", help="config paths, relative to the run tree")
    ap.add_argument("--label", required=True, help="names the log and the state file")
    ap.add_argument("--run-tree", type=Path, default=Path(__file__).resolve().parent.parent,
                    help="checkout to run from (default: the one holding this script)")
    ap.add_argument("--log-dir", type=Path, default=None,
                    help="where the log and state file go (default <run-tree>/logs)")
    ap.add_argument("--passes", type=int, default=3)
    ap.add_argument("--python", default=sys.executable)
    args = ap.parse_args()

    # Taken first, before git, `import ee` and ee.Initialize (review B6), and held to the end.
    lock = Path.home() / LOCK_FILE
    lock_fd = take_lock(lock)
    if lock_fd is None:
        print(f"REFUSING: a batch with pid {lock.read_text().strip()} is still running")
        return 90
    rt = args.run_tree.resolve()
    log_dir = (args.log_dir or rt / "logs").resolve()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{args.label}.log"
    state_path = log_dir / f"{args.label}.state.json"

    def say(msg: str) -> None:
        line = f"[run_passes_safely {time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
        print(line, flush=True)
        with log_path.open("a") as f:
            f.write(line + "\n")

    # Tracked files only: finished runs leave untracked outputs behind, and those are not code.
    started = tree_state(rt, check=True)
    if started["dirty"]:
        print("REFUSING: the run tree has modified tracked files:\n" + "\n".join(started["modified"]))
        return 92
    commit = started["commit"]
    for c in args.configs:
        if not (rt / c).exists():
            print(f"REFUSING: {c} does not exist in the run tree at {commit[:7]}")
            return 94
    sys.path.insert(0, str(rt / "src"))  # the run tree's code, not an editable install elsewhere
    from fmu.config import load_config

    # A config is known by its name: (review B8): the pipeline names every task of it after it,
    # so the wait before a pass, the state file and the skip of an earlier batch's configs go by
    # it. run_config_passes.sh names the exit lines after the file stem, so the two must agree.
    name_of: dict[str, str] = {}
    for c in args.configs:
        if Path(c).suffix != ".yaml":
            print(f"REFUSING: {c} is not a .yaml file (run_config_passes.sh takes a config's "
                  f"name from its file name less .yaml)")
            return 93
        name = load_config(rt / c).name
        if name != Path(c).stem:
            print(f"REFUSING: {c} has name: {name}, not its file stem {Path(c).stem}; its tasks "
                  f"are named after name:, its exit lines after the file stem")
            return 93
        if name in name_of.values():
            print(f"REFUSING: {name} is listed twice")
            return 93
        name_of[c] = name
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
    import ee

    from fmu.settings import get_settings
    ee.Initialize(project=get_settings().gee_project_id)
    # A deadline on every request, as the runner sets on its own polls (review B9): the client has
    # none by default, so a queue poll made during a network drop (the laptop asleep) would never
    # return, and the batch would stall with no log line. A poll that times out is retried.
    ee.data.setDeadline(120_000)

    def active(names: list[str]) -> list[str]:
        out = []
        for op in ee.data.listOperations():
            md = op.get("metadata", {})
            d = md.get("description", "")
            if md.get("state") in ACTIVE_STATES and any(d.startswith(n) for n in names):
                out.append(d)
        return out

    stopped_by: list[int] = []  # the signals received: no pass starts after the first
    child: list[subprocess.Popen] = []  # the shell script, while a pass runs

    def on_signal(signum: int, frame: object) -> None:
        # Passed on to the shell script and the runner (review B5): they run in a process group of
        # their own, so a Ctrl-C in the terminal reaches this process only, and the pass loop
        # waits for them to end before it records the pass and stops. Nothing is raised here, so
        # no write of the log or the state file is cut short. Nor is a lock taken: the handler runs
        # in the main thread, and one that waited for a lock the main thread held when the signal
        # came (a threading.Event takes one) would wait forever.
        stopped_by.append(signum)
        if child:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(child[0].pid, signum)

    for s in STOP_SIGNALS:
        if signal.getsignal(s) is not signal.SIG_IGN:  # one ignored at the start stays so (nohup)
            signal.signal(s, on_signal)

    def pause(seconds: float) -> None:
        """Sleeps for `seconds`, or less once a signal has come: in steps of at most a second."""
        end = time.monotonic() + seconds
        while not stopped_by and (left := end - time.monotonic()) > 0:
            time.sleep(min(left, 1.0))

    def wait_until_idle(names: list[str], why: str) -> bool:
        """True once no task of `names` is queued or running; False if the batch is stopped first."""
        last_said = 0.0
        while not stopped_by:
            try:
                a = active(names)
            except Exception as e:  # noqa: BLE001 - a failed poll is retried, never read as "idle"
                say(f"queue check failed ({str(e)[:120]}); retrying in {POLL_S} s")
                pause(POLL_S)
                continue
            if not a:
                return True
            if time.time() - last_said > 600:
                say(f"{why}: {len(a)} task(s) of these configs still queued or running; "
                    f"waiting (for example {a[0]})")
                last_said = time.time()
            pause(POLL_S)
        return False

    remaining = [c for c in args.configs if c not in skipped]
    done: list[str] = []
    attention: dict[str, str] = {}
    history: list[dict] = []
    running: list[int] = []  # the pass whose exit lines are not yet read, and its first log line
    running_git: list[dict] = []  # the run tree as that pass started
    changed: list[dict] = []  # how the run tree had changed when the batch stopped for it (C32)

    def moved(state: dict) -> bool:
        """Whether the run tree is not the tree the batch started from (C32)."""
        return (state["commit"], state["dirty"]) != (commit, False)

    def save() -> None:
        # Written beside the state file and moved over it (os.replace), so that a save cut short
        # (the disk full, the machine down) leaves the earlier state whole: B4's resume reads it.
        text = json.dumps({
            "label": args.label,
            # As the batch started; each pass adds how the tree stood before and after it (C32).
            "git": started,
            "configs": [name_of[c] for c in args.configs],
            "done": [name_of[c] for c in done],
            "needs_attention": {name_of[c]: why for c, why in attention.items()},
            "not_finished": [name_of[c] for c in remaining],
            "passes": history,
            "skipped": {name_of[c]: why for c, why in skipped.items()},
            "run_tree_changed": changed[0] if changed else None,
            "earlier_batches": earlier,
        }, indent=1)
        tmp = state_path.with_name(f"{state_path.name}.tmp")
        try:
            with tmp.open("w") as f:
                f.write(text)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, state_path)
        finally:
            tmp.unlink(missing_ok=True)

    def read_pass(p: int, rc: int | None, n0: int, git_before: dict) -> None:
        """The pass's stage lines, from line n0 of the log on: a config whose export stage exited 0
        is done; one whose export stage failed, or started and has no exit line (the pass was cut
        short while it ran, after it may have submitted its Drive exports), needs attention. The
        pass's record holds the run tree as it stood before the pass and after it (C32)."""
        exits: dict[str, dict[str, int]] = {}
        exports_started: set[str] = set()
        for line in log_path.read_text().splitlines()[n0:]:
            m = STAGE_EXIT.match(line.strip())
            if m:
                exits.setdefault(m.group(1), {})[m.group(2)] = int(m.group(3))
            m = STAGE_START.match(line.strip())
            if m and m.group(2) == "export":
                exports_started.add(m.group(1))
        history.append({"pass": p, "exit": rc, "stage_exits": exits,
                        "git_before": git_before, "git_after": tree_state(rt)})
        for c in list(remaining):
            st = exits.get(name_of[c], {})
            if st.get("export") == 0:
                done.append(c)
                remaining.remove(c)
            elif "export" in st:
                attention[c] = f"export stage exited {st['export']} in pass {p}; not retried"
                remaining.remove(c)
            elif name_of[c] in exports_started:
                attention[c] = (f"export stage started in pass {p} and has no exit line (the pass "
                                f"was cut short while it ran); not retried")
                remaining.remove(c)
        save()

    try:
        say(f"batch {args.label} started from commit {commit} (tracked files unmodified); "
            f"{len(args.configs)} config(s), up to {args.passes} pass(es)")
        for c, why in skipped.items():
            say(f"{name_of[c]}: skipped, {why}")
        env = pass_env(args.python, rt)
        for p in range(1, args.passes + 1):
            if not remaining or stopped_by:
                break
            names = [name_of[c] for c in remaining]
            if not wait_until_idle(names, f"before pass {p}"):
                break
            # The run tree, read again (review C32): no pass runs on other code than the passes
            # before it, as no batch starts on a tree with modified tracked files.
            before = tree_state(rt)
            if moved(before):
                changed[:] = [{"before_pass": p, "git": before}]
                say(f"REFUSING pass {p}: the run tree changed since the batch started (commit "
                    f"{commit[:7]}; now {str(before['commit'])[:7]}, modified tracked files: "
                    f"{before['modified'] or 'none'}" + (f", {before['error']}" if before["error"] else "")
                    + "); the configs left are not finished")
                break
            n0 = len(log_path.read_text().splitlines())
            say(f"pass {p}: {' '.join(names)}")
            running[:] = [p, n0]
            running_git[:] = [before]
            # A process group of its own, and the lock's descriptor, which the runner inherits
            # too: the lock stays held for as long as any of them runs (review B5).
            child[:] = [subprocess.Popen(
                ["bash", "odisha_script/run_config_passes.sh", str(log_path), *remaining],
                cwd=rt, env=env, start_new_session=True, pass_fds=(lock_fd,))]
            if stopped_by:  # a signal while the pass was starting
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(child[0].pid, stopped_by[0])
            rc = child[0].wait()
            wait_for_group(child[0].pid)
            child.clear()
            running.clear()
            read_pass(p, rc, n0, before)
            say(f"pass {p} exit={rc}; finished: {[name_of[c] for c in done]}; "
                f"not finished: {[name_of[c] for c in remaining]}; "
                f"needs attention: {[name_of[c] for c in attention]}")
        if not changed and history and moved(history[-1]["git_after"]):
            # The last pass ended on a changed tree: its later calls may have run other code (C32).
            after = history[-1]["git_after"]
            changed[:] = [{"after_pass": history[-1]["pass"], "git": after}]
            say(f"the run tree changed during pass {history[-1]['pass']} (commit {commit[:7]}; now "
                f"{str(after['commit'])[:7]}, modified tracked files: {after['modified'] or 'none'})")
        held_back = [c for c in skipped if name_of[c] not in done_before]
        ok = not remaining and not attention and not held_back
        if stopped_by:
            say(f"batch {args.label} ended: NOT ALL COMPLETE "
                f"(stopped by {signal.Signals(stopped_by[0]).name})")
            return 128 + stopped_by[0]
        if changed:
            say(f"batch {args.label} ended: NOT ALL COMPLETE (the run tree changed)")
            return 95
        say(f"batch {args.label} ended: {'ALL CONFIGS COMPLETE' if ok else 'NOT ALL COMPLETE'}")
        return 0 if ok else 1
    finally:
        if running:  # a pass cut short by an error here: what it finished is done all the same
            read_pass(running[0], None, running[1], running_git[0])
        save()
        os.close(lock_fd)  # lets go of the lock; the file stays, as removing it would open a race


if __name__ == "__main__":
    sys.exit(main())

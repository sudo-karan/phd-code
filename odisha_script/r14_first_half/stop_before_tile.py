"""Stop R3's first half before the 10 km tile (Jaskaran, 28 Oct 2026: "Drop the 10 km tile from R3:
once the last 10 ha box has finished its elbow pass, stop the batch before the tile. Record the tile
as dropped from R3, to run later."; the round 14 record, Done, the plan changed to finish today).

The tile is the declared order's last config, so the batch starts it as soon as the config before it
has ended, with no pause between: the shell script writes that config's exit line, then the tile's
first header, and starts the tile's runner. So this reads the batch log, from the given byte on,
every 0.2 seconds, and at each header of the tile (any pass, any stage) reads the whole log for the
k elbow exit lines of the other eighteen configs (odisha_script/r14_first_half/order.py, less the
tile; "--- PASS<n> <config> k_elbow exit=0 ---", in any pass):
  - all eighteen done: SIGTERM to the batch's wrapper (the lock's pid, once ps shows it is this
    label's run_passes_safely.py; looked for again for two seconds before it gives up), which passes
    it on to the shell script and the runner, records the pass (the eighteen done, the tile not
    finished) and ends: "batch <label> ended: NOT ALL COMPLETE (stopped by SIGTERM)". If the wrapper
    is gone but the pass's shell script runs on (it holds the lock too), SIGTERM to the shell's
    process group instead;
  - one or more not done (a config that failed in this pass, which the wrapper's next pass would try
    again): SIGTERM to the tile's runner alone (the process running
    odisha_phase2_2_run_pipeline.py --config configs/<tile>.yaml, waited for up to ten seconds), so
    that the tile's stage fails, the pass ends, and the wrapper's next pass tries those configs
    again, the tile last; this watch goes on, and does the same at the tile's next header.
A runner calls Earth Engine first when its imports are done (fmu's init_gee, before its first log
line; about 27 seconds from its header to its run folder and about 48 to its first task in this
batch's log), so the tile's is stopped before it reads or writes anything on Earth Engine.

It ends without a signal if the batch ends first (a batch of this label resumed later needs this
watch armed again), or if the wrapper and the pass's shell script are both gone. It writes each
header, exit line and wrapper line it sees, each line after the stop that names the tile, and what it
did, to its own log with the time; an error of its own (ps, a signal, a file) is logged and the
watch goes on. It never calls Earth Engine.

    python odisha_script/r14_first_half/stop_before_tile.py --log <batch log> --out <its log>
        --from-byte N [--label r14_first_half] [--tile <config>] [--lock <lock file>]

Exit codes: 0 the batch ended (after the stop, or before the tile); 2 at an all-done header, neither
the wrapper nor the pass's shell script found to stop; 3 the wrapper and the shell script gone with
no ended line; 4 no ended line within 30 minutes of the stop.
"""
from __future__ import annotations

import argparse
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
TILE = "odisha_v120_3ha_tile10km_angul_keptland_s1desc_r14"
POLL_S = 0.2
WRAPPER_CHECK_S = 10.0
GONE_CHECKS = 3  # the wrapper and the shell script not found this many checks in a row: gone
AFTER_STOP_S = 1800.0

ap = argparse.ArgumentParser()
ap.add_argument("--log", type=Path, required=True)
ap.add_argument("--out", type=Path, required=True)
ap.add_argument("--from-byte", type=int, required=True)
ap.add_argument("--label", default="r14_first_half")
ap.add_argument("--tile", default=TILE)
ap.add_argument("--lock", type=Path, default=Path.home() / ".fmu" / "run_passes_safely.lock")
ap.add_argument("--others", nargs="*", default=None,
                help="the configs that must be done first (default: the first half's order less the tile)")
args = ap.parse_args()

header = re.compile(rf"^##### PASS\d+ {re.escape(args.tile)} :: ")
stage_line = re.compile(r"^(##### PASS\d+ \S+ :: |--- PASS\d+ \S+ \S+ exit=)")
elbow_done = re.compile(r"^--- PASS\d+ (\S+) k_elbow exit=0 ---$")
ended = f"] batch {args.label} ended:"


def say(msg: str) -> None:
    try:
        with args.out.open("a") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S %Z')}] {msg}\n")
    except OSError as e:
        print(f"(its log not written: {e!r}) {msg}", flush=True)


def ps(*pids: int) -> dict[int, tuple[int, str]]:
    """pid -> (process group, command) of every process, or of the given ones."""
    cmd = ["ps", "-o", "pid=,pgid=,command="] + (["-p", ",".join(map(str, pids))] if pids else ["-ax"])
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=20).stdout
    procs = {}
    for line in out.splitlines():
        parts = line.split(None, 2)
        if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
            procs[int(parts[0])] = (int(parts[1]), parts[2])
    return procs


def wrapper_pid() -> int | None:
    """The lock's pid, if ps shows it is this label's run_passes_safely.py."""
    try:
        pid = int(args.lock.read_text().strip())
        cmd = ps(pid).get(pid, (0, ""))[1]
    except (OSError, ValueError, subprocess.SubprocessError) as e:
        say(f"(the wrapper could not be looked for: {e!r})")
        return None
    if "run_passes_safely.py" in cmd and f" --label {args.label} " in f"{cmd.strip()} ":
        return pid
    return None


def shell_pgid() -> int | None:
    """The process group of the pass's shell script, run_config_passes.sh with this batch log."""
    try:
        for pid, (pgid, cmd) in ps().items():
            if "run_config_passes.sh" in cmd and str(args.log) in cmd and "bash" in cmd:
                return pgid
    except subprocess.SubprocessError as e:
        say(f"(the shell script could not be looked for: {e!r})")
    return None


def tile_runner() -> list[int]:
    try:
        return [pid for pid, (_, cmd) in ps().items()
                if "odisha_phase2_2_run_pipeline.py" in cmd and f"configs/{args.tile}.yaml" in cmd]
    except subprocess.SubprocessError as e:
        say(f"(the tile's runner could not be looked for: {e!r})")
        return []


def others() -> list[str]:
    if args.others is not None:
        return args.others
    out = subprocess.run([sys.executable, "odisha_script/r14_first_half/order.py"], cwd=HERE,
                         capture_output=True, text=True, timeout=60)
    names = [Path(p).stem for p in out.stdout.split()]
    if out.returncode != 0 or len(names) != 19 or args.tile not in names:
        raise SystemExit(f"the first half's order could not be read: {out.stderr.strip()}")
    return [n for n in names if n != args.tile]


def not_done(must: list[str]) -> list[str]:
    done = set()
    with args.log.open("rb") as f:
        for raw in f:
            m = elbow_done.match(raw.decode(errors="replace").strip())
            if m:
                done.add(m.group(1))
    return [n for n in must if n not in done]


class Reader:
    """The log's whole lines from a byte on; a line not yet ended waits for its end."""

    def __init__(self, path: Path, start: int) -> None:
        self.path, self.pos, self.rest = path, start, b""

    def lines(self) -> list[str]:
        try:
            with self.path.open("rb") as f:
                f.seek(self.pos)
                chunk = f.read()
        except OSError as e:
            say(f"(the batch log could not be read: {e!r})")
            return []
        self.pos += len(chunk)
        *whole, self.rest = (self.rest + chunk).split(b"\n")
        return [w.decode(errors="replace").rstrip("\r") for w in whole]


def kill(pid: int, what: str, group: bool = False) -> bool:
    try:
        (os.killpg if group else os.kill)(pid, signal.SIGTERM)
        return True
    except OSError as e:
        say(f"(SIGTERM to {what} {pid} failed: {e!r})")
        return False


RUNNER_STOPS: list[int] = []  # the tile's runners stopped alone


def at_tile_header(s: str, must: list[str]) -> bool:
    """What to do at a header of the tile; True once the batch is stopped."""
    left = not_done(must)
    if left:
        for _ in range(50):  # the shell starts the runner just after the header
            pids = tile_runner()
            if pids:
                break
            time.sleep(0.2)
        else:
            say(f"SEEN the tile's header: {s!r}; NOT DONE yet: {left}; the tile's runner NOT FOUND in ten "
                f"seconds; the watch goes on")
            return False
        sent = [p for p in pids if kill(p, "the tile's runner")]
        RUNNER_STOPS.extend(sent)
        say(f"SEEN the tile's header: {s!r}; NOT DONE yet: {left}; SIGTERM to the tile's runner alone, pid "
            f"{sent}, so that the wrapper's next pass tries them again; the watch goes on")
        return False
    for _ in range(10):
        pid = wrapper_pid()
        if pid is not None:
            break
        time.sleep(0.2)
    if pid is not None and kill(pid, "the wrapper"):
        say(f"SEEN the tile's header: {s!r}; the other {len(must)} all done; SIGTERM sent to the wrapper, pid {pid}")
        return True
    pgid = shell_pgid()
    if pgid is not None and kill(pgid, "the pass's process group", group=True):
        say(f"SEEN the tile's header: {s!r}; the other {len(must)} all done; NO wrapper of label {args.label}: "
            f"SIGTERM sent to the pass's process group {pgid} (the shell script and the runner)")
        return True
    say(f"SEEN the tile's header: {s!r}; the other {len(must)} all done; NO wrapper of label {args.label} "
        f"and no shell script of this log to stop")
    raise SystemExit(2)


def main() -> int:
    must = others()
    reader = Reader(args.log, args.from_byte)
    say(f"armed: the batch log {args.log} from byte {args.from_byte}; at each header of {args.tile}: the "
        f"wrapper of label {args.label} stopped if the other {len(must)} are done, else the tile's runner "
        f"alone; the wrapper now (lock {args.lock}): {wrapper_pid()}")
    stopped_at: float | None = None
    last_check, missing = 0.0, 0
    while True:
        for line in reader.lines():
            s = line.strip()
            if stopped_at is not None and args.tile in s:
                say(f"AFTER THE STOP, a line naming the tile: {s!r}")
            elif header.match(s):
                if at_tile_header(s, must):
                    stopped_at = time.time()
                continue
            if ended in s:
                say(f"the batch ended: {s!r}" + (
                    "" if stopped_at is not None else
                    f" (the wrapper not stopped; the tile's runner stopped alone {len(RUNNER_STOPS)} time(s); "
                    "arm this watch again before a batch of this label is resumed)"))
                return 0
            if stage_line.match(s) or s.startswith("[run_passes_safely"):
                say(f"line: {s!r}")
        now = time.time()
        if stopped_at is not None and now - stopped_at > AFTER_STOP_S:
            say("no ended line within 30 minutes of the stop")
            return 4
        if now - last_check >= WRAPPER_CHECK_S:
            last_check = now
            alive = wrapper_pid() is not None or shell_pgid() is not None
            missing = 0 if alive else missing + 1
            if missing >= GONE_CHECKS:
                for line in reader.lines():  # its last lines, if it wrote them as it went
                    if ended in line:
                        say(f"the batch ended: {line.strip()!r}")
                        return 0
                    if header.match(line.strip()):
                        say(f"a header of the tile after the batch's processes were gone: {line.strip()!r}")
                say(f"the wrapper of label {args.label} and the pass's shell script are gone, with no ended line")
                return 3
        time.sleep(POLL_S)


if __name__ == "__main__":
    sys.exit(main())

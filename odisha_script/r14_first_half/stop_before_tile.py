"""Stop R3's first half before the 10 km tile (Jaskaran, 28 Oct 2026: "Drop the 10 km tile from R3:
once the last 10 ha box has finished its elbow pass, stop the batch before the tile. Record the tile
as dropped from R3, to run later."; the round 14 record, Done, the plan changed to finish today).

The tile is the declared order's last config, so the batch starts it as soon as the last 10 ha box's
k elbow pass ends, with no pause between: the shell script writes the box's exit line, then the
tile's first header, and starts the tile's runner. So this reads the batch log, from the given byte
on, every 0.2 seconds, and at the first header of the tile (any pass, any stage) sends SIGTERM to the
batch's wrapper: the lock's pid, once ps shows it is this label's run_passes_safely.py. The wrapper
passes the signal on to the shell script and the runner, records the pass (each config whose k elbow
exited 0 is done; the tile is not finished) and ends: "batch <label> ended: NOT ALL COMPLETE (stopped
by SIGTERM)". A runner takes about 27 seconds from its header to its run folder and about 48 to its
first task (the first half's log, 28 Oct 2026), so the tile's is stopped before it reads or writes
anything on Earth Engine.

It ends without a signal if the batch ends first, or if the wrapper is gone. It writes each header,
exit line and wrapper line it sees, each line after the stop that names the tile, and what it did,
to its own log with the time. It never calls Earth Engine.

    python odisha_script/r14_first_half/stop_before_tile.py --log <batch log> --out <its log>
        --from-byte N [--label r14_first_half] [--tile <config>] [--lock <lock file>]

Exit codes: 0 the batch ended (after the stop, or before the tile); 2 the tile's header seen and no
wrapper of the label to stop; 3 the wrapper gone with no ended line; 4 no ended line within 30
minutes of the stop.
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

TILE = "odisha_v120_3ha_tile10km_angul_keptland_s1desc_r14"
POLL_S = 0.2
WRAPPER_CHECK_S = 10.0
GONE_CHECKS = 3  # the wrapper not found this many checks in a row: gone
AFTER_STOP_S = 1800.0

ap = argparse.ArgumentParser()
ap.add_argument("--log", type=Path, required=True)
ap.add_argument("--out", type=Path, required=True)
ap.add_argument("--from-byte", type=int, required=True)
ap.add_argument("--label", default="r14_first_half")
ap.add_argument("--tile", default=TILE)
ap.add_argument("--lock", type=Path, default=Path.home() / ".fmu" / "run_passes_safely.lock")
args = ap.parse_args()

header = re.compile(rf"^##### PASS\d+ {re.escape(args.tile)} :: ")
stage_line = re.compile(r"^(##### PASS\d+ \S+ :: |--- PASS\d+ \S+ \S+ exit=)")
ended = f"] batch {args.label} ended:"


def say(msg: str) -> None:
    with args.out.open("a") as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S %Z')}] {msg}\n")


def wrapper_pid() -> int | None:
    """The lock's pid, if ps shows it is this label's run_passes_safely.py."""
    try:
        pid = int(args.lock.read_text().strip())
    except (OSError, ValueError):
        return None
    cmd = subprocess.run(["ps", "-o", "command=", "-p", str(pid)], capture_output=True,
                         text=True).stdout
    if "run_passes_safely.py" in cmd and f" --label {args.label} " in f"{cmd.strip()} ":
        return pid
    return None


class Reader:
    """The log's whole lines from a byte on; a line not yet ended waits for its end."""

    def __init__(self, path: Path, start: int) -> None:
        self.path, self.pos, self.rest = path, start, b""

    def lines(self) -> list[str]:
        with self.path.open("rb") as f:
            f.seek(self.pos)
            chunk = f.read()
        self.pos += len(chunk)
        *whole, self.rest = (self.rest + chunk).split(b"\n")
        return [w.decode(errors="replace").rstrip("\r") for w in whole]


def main() -> int:
    reader = Reader(args.log, args.from_byte)
    say(f"armed: the batch log {args.log} from byte {args.from_byte}; the stop at the first header "
        f"of {args.tile}; the wrapper of label {args.label} (lock {args.lock}): {wrapper_pid()}")
    stopped_at: float | None = None
    last_check, missing = 0.0, 0
    while True:
        for line in reader.lines():
            s = line.strip()
            if stopped_at is None and header.match(s):
                pid = wrapper_pid()
                if pid is None:
                    say(f"SEEN the tile's header: {s!r}; NO wrapper of label {args.label} to stop")
                    return 2
                os.kill(pid, signal.SIGTERM)
                stopped_at = time.time()
                say(f"SEEN the tile's header: {s!r}; SIGTERM sent to the wrapper, pid {pid}")
                continue
            if ended in s:
                say(f"the batch ended: {s!r}"
                    + ("" if stopped_at is not None else " (before the tile: no signal sent)"))
                return 0
            if stage_line.match(s) or s.startswith("[run_passes_safely"):
                say(f"line: {s!r}")
            elif stopped_at is not None and args.tile in s:
                say(f"AFTER THE STOP, a line naming the tile: {s!r}")
        now = time.time()
        if stopped_at is not None and now - stopped_at > AFTER_STOP_S:
            say("no ended line within 30 minutes of the stop")
            return 4
        if now - last_check >= WRAPPER_CHECK_S:
            last_check = now
            missing = 0 if wrapper_pid() is not None else missing + 1
            if missing >= GONE_CHECKS:
                for line in reader.lines():  # its last lines, if it wrote them as it went
                    if ended in line:
                        say(f"the batch ended: {line.strip()!r}")
                        return 0
                say(f"the wrapper of label {args.label} is gone, with no ended line")
                return 3
        time.sleep(POLL_S)


if __name__ == "__main__":
    sys.exit(main())

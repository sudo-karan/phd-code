"""The stop rule of R3's first half (the round 14 record, Done, the cost estimate: the batch is
stopped when the round's use reaches 150 - 1.2 x max(1, r) x 12.51, r the third live check's
charged cost over 7.94): read the round's Earth Engine use every INTERVAL seconds (at most half an
hour apart, as the rule says), read-only (odisha_script/r14_smoke_test/round_use.py: Cloud
Monitoring's hourly sums and the task list, under ee_read_only.forbid_writes), write each reading
to QUOTA_LOG, and when the use reaches STOP send SIGTERM to the batch's wrapper (its pid is in
~/.fmu/run_passes_safely.lock), which passes it on to the pass in flight, records the pass and
stops; the tasks already submitted run on. Ends when the batch's log says it ended, or no wrapper
is alive. (Committed before R3's first half, 27 Oct 2026; until then in the session's scratch
folder, first_half_watch.py.)

    python odisha_script/r14_first_half/watch.py STOP BATCH_LOG QUOTA_LOG [INTERVAL]
"""
import json
import os
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

STOP = float(sys.argv[1])
BATCH_LOG = Path(sys.argv[2])
QUOTA_LOG = Path(sys.argv[3])
INTERVAL = int(sys.argv[4]) if len(sys.argv) > 4 else 1200
REPO = Path(__file__).resolve().parents[2]
QUOTA = REPO / "odisha_script" / "r14_smoke_test" / "round_use.py"
LOCK = Path.home() / ".fmu" / "run_passes_safely.lock"
PY = "/Users/karan/Desktop/phd-code/.venv/bin/python"


def say(line: str) -> None:
    stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    with QUOTA_LOG.open("a") as f:
        f.write(f"[{stamp}] {line}\n")
    print(f"[{stamp}] {line}", flush=True)


def wrapper_pid() -> int | None:
    try:
        pid = int(LOCK.read_text().strip())
        os.kill(pid, 0)
        return pid
    except (OSError, ValueError):
        return None


def ended() -> bool:
    """The wrapper's last line, "[run_passes_safely ...] batch <label> ended: ...", is in the log."""
    if not BATCH_LOG.exists():
        return False
    return any(line.startswith("[run_passes_safely") and "] batch " in line and " ended: " in line
               for line in BATCH_LOG.read_text().splitlines()[-5:])


if not 0 < INTERVAL <= 1800:
    sys.exit("INTERVAL must be at most half an hour (1800 s), as the stop rule says")
say(f"watch started: stop at {STOP:.4f} EECU-hours, a reading every {INTERVAL} s")
while True:
    if ended():
        say("the batch ended; watch ends")
        break
    pid = wrapper_pid()
    if pid is None:
        say("no wrapper holds the lock; watch ends")
        break
    try:
        out = subprocess.run([PY, str(QUOTA)], capture_output=True, text=True, timeout=600,
                             cwd=REPO).stdout
        r = json.loads(out[out.index("{"):])
        use = float(r["round_use_h"])
        say(f"round use {use:.4f} (batch {max(r['monitoring_batch_h'], r['task_list_batch_h_since_round_start']):.4f}, "
            f"online {r['monitoring_online_h']:.4f}), October left {r['october_left_h']:.2f}, "
            f"queued or running {len(r['queued_or_running'])}")
        if use >= STOP:
            say(f"STOP: the round's use {use:.4f} reached {STOP:.4f}; SIGTERM to the wrapper (pid {pid})")
            os.kill(pid, signal.SIGTERM)
            break
    except Exception as e:  # a reading that fails is said, and the next one is tried
        say(f"reading failed: {e!r}")
    time.sleep(INTERVAL)

"""The stop rule of R3's first half (the round 14 record, Done, the cost estimate: "the batch is
stopped (SIGTERM to the wrapper, which records the pass) when the round's use reaches
150 - 1.2 x max(1, r) x 12.51", r the third live check's charged cost over its estimate, 7.94; the
quota read "at most half an hour apart"), with the round's budget raised to 200 EECU-hours and the
stop moved by as much, by Jaskaran's answer to question 14 (b), 28 Oct 2026: the stop is
200 - 1.2 x max(1, r) x 12.51.

    python odisha_script/r14_first_half/watch.py --label r14_first_half --costs <live_check_3 folder>
        --batch-log <logs>/r14_first_half.log --quota-log <logs>/r14_first_half_quota.log
        [--interval 1200] [--from-byte N]    (from the batch's run tree, so that its code is the batch's)

r is worked here from the third check's two cost files (cost_<run>.json, their totals), and the stop
from r, so that neither is typed by hand. It waits up to ten minutes for the batch's wrapper: the
pid in ~/.fmu/run_passes_safely.lock, alive, whose command is run_passes_safely.py with --label
<label>, and the wrapper's "batch <label> started" line in the batch log after --from-byte (the
log's length before the batch was started, as launch.sh gives it; by default its length when the
watch began): a batch resumed under the same label appends to the same log, and only its own lines
count. Then
it reads the round's use (odisha_script/r14_smoke_test/round_use.py of its own checkout, read-only)
every --interval seconds of wall clock, at most 1800; once the use is within one margin of the stop
(1.2 x max(1, r) x 12.51 below it), every 300 seconds and at every new stage header of the batch
log as well, so that a crossing is seen before the next stage submits its tasks. A failed reading
is tried again after 60 seconds, and logged with the end of its error. When the use reaches the
stop it sends SIGTERM to the wrapper (checked again to be the wrapper), which passes it on to the
pass in flight, records the pass and stops; the tasks already submitted run on. If no reading has
succeeded for 1800 seconds, the rule cannot be kept, and it stops the batch the same way (fail-safe;
the record's question 15 asks whether that is what Jaskaran wants). Each line goes to --quota-log.

Exit 0: the batch ended (its "batch <label> ended:" line, written after the watch began); 3: stopped
by the rule; 4: stopped because no reading succeeded for 30 minutes; 5: no wrapper of the label
found within ten minutes; 6: the wrapper is gone without its ended line; 2: refused (the arguments).
"""
import argparse
import json
import math
import os
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

BUDGET, ESTIMATE, LARGEST_PASS = 200.0, 7.94, 12.51  # the round's EECU-hours (question 14 (b))
HERE = Path(__file__).resolve().parents[2]  # the checkout this script is in: the run tree
QUOTA = HERE / "odisha_script" / "r14_smoke_test" / "round_use.py"
LOCK = Path.home() / ".fmu" / "run_passes_safely.lock"
PY = "/Users/karan/Desktop/phd-code/.venv/bin/python"
RUNS = ("odisha_v120_3ha_squares_angul_keptland_s1desc_r14_check_e",
        "odisha_v120_3ha_squares_angul_keptland_s1desc_r14_check_f")
NO_READING_LIMIT, RETRY, NEAR_INTERVAL, TICK = 1800, 60, 300, 20

ap = argparse.ArgumentParser()
ap.add_argument("--label", required=True)
ap.add_argument("--costs", type=Path, required=True, help="the third live check's records folder")
ap.add_argument("--batch-log", type=Path, required=True)
ap.add_argument("--quota-log", type=Path, required=True)
ap.add_argument("--interval", type=int, default=1200)
ap.add_argument("--from-byte", type=int, default=None, help="the batch log's length before the batch started")
args = ap.parse_args()


def say(line: str) -> None:
    stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        with args.quota_log.open("a") as f:
            f.write(f"[{stamp}] {line}\n")
    except OSError as e:
        print(f"[{stamp}] (quota log not written: {e!r})", flush=True)
    print(f"[{stamp}] {line}", flush=True)


if not 0 < args.interval <= 1800:
    say("REFUSED: --interval must be more than 0 and at most half an hour (1800 s), as the stop rule says")
    sys.exit(2)
try:
    totals = [float(json.loads((args.costs / f"cost_{run}.json").read_text())["total"]) for run in RUNS]
except (OSError, ValueError, KeyError) as e:
    say(f"REFUSED: the third check's cost files could not be read ({e!r})")
    sys.exit(2)
r = sum(totals) / ESTIMATE
if not (math.isfinite(r) and 0 < r < 10):
    say(f"REFUSED: r = {r} is not a ratio the rule can use")
    sys.exit(2)
MARGIN = 1.2 * max(1.0, r) * LARGEST_PASS
STOP = BUDGET - MARGIN
NEAR = STOP - MARGIN
START_OFFSET = (args.from_byte if args.from_byte is not None
                else args.batch_log.stat().st_size if args.batch_log.exists() else 0)


def new_lines() -> list[str]:
    """The batch log's lines written since the watch began."""
    try:
        with args.batch_log.open("rb") as f:
            f.seek(START_OFFSET)
            return f.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return []


def started() -> bool:
    return any(line.startswith("[run_passes_safely") and f"] batch {args.label} started" in line
               for line in new_lines())


def ended() -> bool:
    return any(line.startswith("[run_passes_safely") and f"] batch {args.label} ended: " in line
               for line in new_lines())


def stage_headers() -> int:
    return sum(1 for line in new_lines() if line.startswith("##### PASS"))


def wrapper() -> int | None:
    """The pid in the lock, if it is alive and is this label's wrapper."""
    try:
        pid = int(LOCK.read_text().strip())
        os.kill(pid, 0)
        cmd = subprocess.run(["ps", "-o", "command=", "-p", str(pid)], capture_output=True, text=True,
                             timeout=30).stdout
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    words = f" {cmd.strip()} "
    return pid if "run_passes_safely.py" in words and f" --label {args.label} " in words else None


def stop(why: str, code: int) -> None:
    pid = wrapper()
    if pid is None:
        say(f"{why}; but no wrapper of {args.label} is alive to stop")
        sys.exit(6)
    say(f"{why}; SIGTERM to the wrapper (pid {pid})")
    os.kill(pid, signal.SIGTERM)
    for _ in range(90):  # up to 30 minutes for the pass in flight to end and the wrapper to record it
        if ended():
            say("the batch ended after the stop: " + next(
                line for line in reversed(new_lines()) if f"] batch {args.label} ended: " in line))
            sys.exit(code)
        time.sleep(TICK)
    say("the batch has not logged its end 30 minutes after the stop; the watch ends (look at the batch)")
    sys.exit(code)


say(f"watch started: r = {r:.4f} ({totals[0]:.4f} + {totals[1]:.4f} over {ESTIMATE}); the stop at "
    f"{STOP:.4f} EECU-hours ({BUDGET:.0f} - {MARGIN:.4f}); readings every {args.interval} s, every "
    f"{NEAR_INTERVAL} s and at each stage header from {NEAR:.4f}; the round's use read by {QUOTA}")
for _ in range(30):  # up to ten minutes for the wrapper
    if wrapper() is not None and started():
        break
    time.sleep(TICK)
else:
    say(f"NO WRAPPER of {args.label} found within ten minutes (the lock, its command, its started line); "
        "the watch ends: the stop rule is NOT being kept")
    sys.exit(5)
say(f"the wrapper of {args.label} is pid {wrapper()}")

# Wall-clock times: the rule's half hour is the clock's, and Earth Engine's tasks run on while
# this Mac sleeps. The first reading is made at once; the 30 minutes without a reading count from
# the last good one, or from here, and stop the batch only after three failed tries in a row.
last_good = last_try = time.time() - args.interval
good_at, failures = time.time(), 0
last_use, headers_seen = None, stage_headers()
while True:
    try:
        if ended():
            say("the batch ended; the watch ends")
            sys.exit(0)
        if wrapper() is None:
            time.sleep(5)
            if ended():
                say("the batch ended; the watch ends")
                sys.exit(0)
            say(f"THE WRAPPER OF {args.label} IS GONE without its ended line; the watch ends (look at the batch)")
            sys.exit(6)
        now = time.time()
        near = last_use is not None and last_use >= NEAR
        headers = stage_headers()
        due = (now - last_good >= (NEAR_INTERVAL if near else args.interval)
               or (near and headers > headers_seen))
        retry = last_try > last_good and now - last_try >= RETRY
        if due and (last_try <= last_good or retry):
            last_try = now
            headers_seen = headers
            p = subprocess.run([PY, str(QUOTA)], capture_output=True, text=True, timeout=300, cwd=HERE)
            try:
                q = json.loads(p.stdout[p.stdout.index("{"):])
                use = float(q["round_use_h"])
            except (ValueError, KeyError, TypeError) as e:
                say(f"reading failed ({e!r}); exit {p.returncode}; its error ends: "
                    f"{' | '.join(p.stderr.strip().splitlines()[-3:])}")
                use = None
            if use is None or not math.isfinite(use):
                failures += 1
            else:
                last_good = good_at = time.time()
                last_use, failures = use, 0
                if use >= STOP:
                    stop(f"STOP: the round's use {use:.4f} reached the stop {STOP:.4f}", 3)
                say(f"round use {use:.4f} (batch {max(q.get('monitoring_batch_h', 0), q.get('task_list_batch_h_since_round_start', 0)):.4f}, "
                    f"online {q.get('monitoring_online_h', 0):.4f}), October left {q.get('october_left_h', 0):.2f}, "
                    f"queued or running {len(q.get('queued_or_running', []))}; the stop {STOP:.4f}"
                    + ("; near it" if use >= NEAR else ""))
        if time.time() - good_at >= NO_READING_LIMIT and failures >= 3:
            stop("NO READING FOR 30 MINUTES: the stop rule cannot be kept (fail-safe)", 4)
    except subprocess.TimeoutExpired:
        failures += 1
        say("reading failed: round_use.py did not answer within 300 s")
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001 (said, and the watch goes on; the 30 minutes still count)
        say(f"error in the watch, going on: {e!r}")
    time.sleep(TICK)

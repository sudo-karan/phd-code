"""Cancel the Drive exports of a throwaway check copy that were not ended at the one reading of its
Drive states, by their task ids, and record it (the round 14 record: the smoke test's rule 2, "one
not yet ended ... is then cancelled by the round (a throwaway copy's export, by its task id)"; the
step before Task 5; the brief's Task 7.3: "A stuck Drive export may be cancelled. Do not send it
again unless the record needs the file, and record what you did"). Nothing is sent again.

It reads the run's <run>_drive_exports.json (the one reading, scripts/drive_export_states.py). Every
file whose state there is not an end (COMPLETED, FAILED, CANCELLED) gets a row. A file READY or
RUNNING at the reading is cancelled (cancelOperation, the only write this script makes) if its task
is still queued or running and its description is the reading's; any other is recorded, not
cancelled. Then each cancelled task is read until it has ended (up to five minutes). A task counts
as ended only when its operation is done and its state is SUCCEEDED, FAILED or CANCELLED.

The record is written as each cancel is sent, so that a stop or crash after it loses nothing: a run
over a record not marked complete finishes it without cancelling again (the cancels it shows were
sent). <out.json> holds results only (each row: the export, file, folder, task id, description,
state at the reading, state, progress and work units before, whether the cancel was sent, state
after, ended); <out stem>_run.json the command, the git block of this script's checkout read before
anything is written, the reading's SHA-256, when it started, when each cancel was sent and the
tasks' own times. It refuses a run that is not a check copy (`_r14_check_` in its name) and an out
folder that does not exist, before Earth Engine is reached.

Exit 0: none of those tasks is left queued or running; 1: one is (still cancelling after five
minutes, its state unknown, or not cancelled because its description differs); 2: refused, nothing
done; 3: the record is there already, complete, nothing done; 4: Earth Engine not reached (run it
again: a partial record is finished, and a cancel it shows sent is not sent again).

    python cancel_drive_export.py <run>_drive_exports.json <out.json>   (from the repo root)
"""
import hashlib
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from fmu.utils.gee import init_gee
from fmu.utils.provenance import git_state_now

NOT_ENDED = ("READY", "RUNNING")  # at the reading, as scripts/drive_export_states.py names them
ENDS_AT_THE_READING = ("COMPLETED", "FAILED", "CANCELLED")
OP_NOT_ENDED = ("PENDING", "RUNNING")  # the same, as the task's operation names them
OP_ENDS = ("SUCCEEDED", "FAILED", "CANCELLED")
PROJECT = "projects/replicating-paper/operations"


def now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def work_units(meta: dict) -> list[dict]:
    return [{"stage": s.get("displayName"), "complete": int(s.get("completeWorkUnits", 0)),
             "total": int(s.get("totalWorkUnits", 0))} for s in meta.get("stages", [])]


def ended(op: dict) -> bool:
    return bool(op.get("done")) and op.get("metadata", {}).get("state") in OP_ENDS


reading, out = Path(sys.argv[1]), Path(sys.argv[2])
run_file = out.with_name(out.stem + "_run.json")
if not out.parent.is_dir():
    print(f"REFUSED: the out folder {out.parent} does not exist")
    sys.exit(2)
earlier = json.loads(out.read_text()) if out.exists() else None
if earlier is not None and earlier.get("complete"):
    print(f"{out} is there already, complete: nothing done")
    sys.exit(3)
try:
    states = json.loads(reading.read_text())
    config, files = states["config"], states["files"]
except (OSError, ValueError, KeyError) as e:
    print(f"REFUSED: {reading} is not a reading of Drive states ({e!r})")
    sys.exit(2)
if "_r14_check_" not in config:
    print(f"REFUSED: {config} is not a check copy")
    sys.exit(2)

run = json.loads(run_file.read_text()) if earlier is not None and run_file.exists() else {
    "result_file": out.name, "command_line": " ".join(["python", *sys.argv]), "started": now(),
    "git": git_state_now(Path(__file__).resolve().parent),
    "reading": str(reading), "reading_sha256": hashlib.sha256(reading.read_bytes()).hexdigest(),
    "cancel_sent_at": {}, "tasks": {}}
rows = {(r.get("task_id") or f"no task id: {r['export']}"): r
        for r in (earlier or {}).get("not_ended_at_the_reading", [])}


def write(complete: bool) -> None:
    done = all(r.get("ended") for r in rows.values())
    out.write_text(json.dumps({
        "what": "The Drive exports of a check copy not ended at the one reading of its Drive states, "
                "cancelled by the round by their task ids (cancel_drive_export.py). Results only.",
        "config": config, "reading": reading.name, "not_ended_at_the_reading": list(rows.values()),
        "none_left_queued_or_running": complete and done, "complete": complete}, indent=1) + "\n")
    run_file.write_text(json.dumps(run, indent=1) + "\n")


try:
    init_gee()
    import ee
    ee.data.setDeadline(120_000)
except Exception as e:  # noqa: BLE001 (any failure to reach Earth Engine)
    print(f"Earth Engine not reached: {e!r}")
    sys.exit(4)

print(f"started {now()}", flush=True)


def get_operation(task_id: str) -> dict | None:
    """The task's operation, or None if Earth Engine has no such task; any other error is raised."""
    try:
        return ee.data.getOperation(f"{PROJECT}/{task_id}")
    except ee.EEException as e:
        if "not found" in str(e).lower():
            return None
        raise


try:
    # The cancels, each recorded before it is sent ("sending") and again once Earth Engine has
    # taken it (true): a record left at "sending" by a stop in between says so, and a run over it
    # sends the cancel again only if the task is still queued or running. A file with no task id,
    # or whose task Earth Engine does not know, has nothing queued or running: recorded so.
    for name, f in files.items():
        if f.get("state") in ENDS_AT_THE_READING:
            continue
        key = f.get("task_id") or f"no task id: {name}"
        row = rows.get(key)
        if row is not None and row.get("cancel_sent") != "sending":
            continue
        base = {"export": name, "file": f.get("filename"), "folder": f.get("folder"),
                "task_id": f.get("task_id"), "state_at_the_reading": f.get("state")}
        if not f.get("task_id"):
            rows[key] = {**base, "no_task_id": True, "cancel_sent": False, "ended": True}
            write(complete=False)
            continue
        op = get_operation(f["task_id"])
        if op is None:
            rows[key] = {**base, "not_found_on_earth_engine": True, "cancel_sent": False, "ended": True}
            write(complete=False)
            continue
        meta = op.get("metadata", {})
        if row is None:
            row = {**base, "description": meta.get("description"), "state_before": meta.get("state"),
                   "progress_before": meta.get("progress"), "work_units_before": work_units(meta),
                   "cancel_sent": False, "state_after": meta.get("state") if ended(op) else None,
                   "ended": ended(op)}
            run["tasks"][key] = {k: meta.get(k) for k in ("createTime", "startTime", "updateTime")}
        same = (meta.get("description") == f.get("description")
                and str(meta.get("description", "")).startswith(config + "_"))
        if f.get("state") in NOT_ENDED and meta.get("state") in OP_NOT_ENDED and not op.get("done"):
            if not same:
                row["not_cancelled_because"] = "its description is not the reading's"
                print(f"{now()} NOT CANCELLED: {key} is described {meta.get('description')!r}, "
                      f"the reading {f.get('description')!r}", flush=True)
            else:
                row["cancel_sent"] = "sending"
                rows[key] = row
                write(complete=False)
                ee.data.cancelOperation(f"{PROJECT}/{key}")
                row["cancel_sent"] = True
                run["cancel_sent_at"][key] = now()
        rows[key] = row
        write(complete=False)
        if row["cancel_sent"] is True:
            print(f"{now()} cancel sent: {key} {meta.get('description')}", flush=True)
    # Each row read until its task has ended, up to five minutes.
    for attempt in range(31):
        for key, row in rows.items():
            if row.get("ended"):
                continue
            op = get_operation(key)
            if op is None:
                row["not_found_on_earth_engine"], row["ended"] = True, True
                continue
            row["state_after"], row["ended"] = op.get("metadata", {}).get("state"), ended(op)
            run["tasks"].setdefault(key, {}).update(
                {k: op.get("metadata", {}).get(k) for k in ("updateTime", "endTime")})
        left = [k for k, r in rows.items() if not r.get("ended")]
        print(f"{now()} read {attempt + 1}: {len(left)} not ended {left}", flush=True)
        if not left:
            break
        time.sleep(10)
except Exception as e:  # noqa: BLE001 (record what was done, then stop)
    write(complete=False)
    print(f"{now()} Earth Engine error, the record written as far as it went (run again to finish it): {e!r}")
    sys.exit(4)

run["ended"] = now()
write(complete=True)
for k, r in rows.items():
    print(f"{k} {r['export']}: at the reading {r.get('state_at_the_reading')}, before {r.get('state_before')} "
          f"(progress {r.get('progress_before')}), cancel sent {r.get('cancel_sent')}, after "
          f"{r.get('state_after')}, ended {r.get('ended')}")
left = [k for k, r in rows.items() if not r.get("ended")]
print(f"ended {now()}; none left queued or running: {not left}")
sys.exit(0 if not left else 1)

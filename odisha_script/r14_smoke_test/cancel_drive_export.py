"""Cancel the Drive exports of a throwaway check copy that were not ended at the one reading of its
Drive states, by their task ids, and record it (the round 14 record: the smoke test's rule 2, "one
not yet ended ... is then cancelled by the round (a throwaway copy's export, by its task id)"; the
step before Task 5; the brief's Task 7.3: "A stuck Drive export may be cancelled. Do not send it
again unless the record needs the file, and record what you did"). Nothing is sent again.

It reads the run's <run>_drive_exports.json (the one reading, scripts/drive_export_states.py) and,
for each file READY or RUNNING there, reads its task, cancels it if it is still not ended
(cancelOperation, the only write this script makes), and reads it again until it is cancelled (up
to five minutes); one that ended on its own after the reading is recorded so, not cancelled. It
refuses a run that is not a check copy (`_r14_check_` in its name). Writes <out.json> (results
only: each task's file, id, state at the reading, state, progress and work units before, whether
the cancel was sent, state after) and <out stem>_run.json (the command, the git block, the tasks'
times). Exit 0 if none of those tasks is left queued or running; 1 if one is; 3, nothing done, if
<out.json> is there already.

    python cancel_drive_export.py <run>_drive_exports.json <out.json>   (from the repo root)
"""
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from fmu.utils.gee import init_gee
from fmu.utils.provenance import git_state_now

NOT_ENDED = ("READY", "RUNNING")  # at the reading, as scripts/drive_export_states.py names them
OP_NOT_ENDED = ("PENDING", "RUNNING")  # the same, as the task's operation names them
OP_ENDING = (*OP_NOT_ENDED, "CANCELLING")


def now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def read(task_id: str) -> dict:
    import ee
    return ee.data.getOperation(f"projects/replicating-paper/operations/{task_id}")["metadata"]


def work_units(meta: dict) -> list[dict]:
    return [{"stage": s.get("displayName"), "complete": int(s.get("completeWorkUnits", 0)),
             "total": int(s.get("totalWorkUnits", 0))} for s in meta.get("stages", [])]


reading, out = Path(sys.argv[1]), Path(sys.argv[2])
if out.exists():
    print(f"{out} is there already: nothing done")
    sys.exit(3)
states = json.loads(reading.read_text())
config = states["config"]
if "_r14_check_" not in config:
    sys.exit(f"REFUSED: {config} is not a check copy")
init_gee()
import ee  # noqa: E402

print(f"started {now()}")
rows, times = [], []
for name, f in states["files"].items():
    if f.get("state") not in NOT_ENDED:
        continue
    before = read(f["task_id"])
    row = {"export": name, "file": f["filename"], "folder": f["folder"], "task_id": f["task_id"],
           "description": before.get("description"), "state_at_the_reading": f["state"],
           "state_before": before.get("state"), "progress_before": before.get("progress"),
           "work_units_before": work_units(before)}
    row["cancel_sent"] = before.get("state") in OP_NOT_ENDED
    if row["cancel_sent"]:
        ee.data.cancelOperation(f"projects/replicating-paper/operations/{f['task_id']}")
        print(f"{now()} cancel sent: {f['task_id']} {before.get('description')}")
        after = read(f["task_id"])
        for _ in range(30):
            if after.get("state") not in OP_ENDING:
                break
            time.sleep(10)
            after = read(f["task_id"])
    else:
        after = before
    row["state_after"] = after.get("state")
    rows.append(row)
    times.append({"task_id": f["task_id"], "createTime": before.get("createTime"),
                  "startTime": before.get("startTime"), "updateTime_before": before.get("updateTime"),
                  "updateTime_after": after.get("updateTime"), "endTime": after.get("endTime")})
    print(f"{now()} {f['task_id']}: {row['state_before']} -> {row['state_after']}, "
          f"progress {row['progress_before']}, work units {row['work_units_before']}")

passes = all(r["state_after"] not in OP_ENDING for r in rows)
out.write_text(json.dumps({
    "what": "The Drive exports of a check copy not ended at the one reading of its Drive states, "
            "cancelled by the round by their task ids (cancel_drive_export.py). Results only.",
    "config": config, "reading": reading.name, "not_ended_at_the_reading": rows,
    "none_left_queued_or_running": passes}, indent=1) + "\n")
out.with_name(out.stem + "_run.json").write_text(json.dumps({
    "result_file": out.name, "command_line": " ".join(["python", *sys.argv]), "ended": now(),
    "git": git_state_now(Path(".")), "tasks": times}, indent=1) + "\n")
print(f"ended {now()}; none left queued or running: {passes}")
sys.exit(0 if passes else 1)

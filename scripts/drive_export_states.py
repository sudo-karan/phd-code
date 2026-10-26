"""How a run's Drive exports ended: the state of every Drive task id in its run record, read after a batch.

    python scripts/drive_export_states.py <config>_run.json [<config>_run.json ...]

The export stage submits each Drive file (the three rasters, and each vector layer in each format)
as an Earth Engine task and returns. Nothing in a batch waits on those tasks or records how they
ended: a config counts as finished, and the batch says ALL CONFIGS COMPLETE, once they are submitted
(review C39). Their ids are in the run record the export pass writes,
odisha_script/phase2_vectors/<config>_run.json, under `drive_exports`. Run this after the batch, once
the task list shows none of them queued or running, from the run tree's root (fmu reads .env from
the working directory, and the tasks are read in the project it names). Round 14: round 13's question
40, answer (b).

READ-ONLY on Earth Engine: after `ee_read_only.forbid_writes()` it asks ee.data.getTaskStatus for
the record's task ids (one request per task), and submits, cancels or changes nothing.

Beside each record it writes:
  <config>_drive_exports.json      results only, no times or dates, so a later read that finds the
                                   same states leaves it as it was: for each Drive file of the
                                   record's `drive_exports`, under the record's key, the file name,
                                   its Drive folder, the task id, the task's description and state,
                                   and its error message (null when there is none); the count of
                                   each state; whether every task COMPLETED; and the files that have
                                   no task id
  <config>_drive_exports_run.json  how it was made: the command, when the states were read, and the
                                   git block of this script's checkout (fmu.utils.provenance
                                   .git_state, without its root), read before anything is written

A state is Earth Engine's: COMPLETED, FAILED or CANCELLED for a task that has ended; READY, RUNNING
or CANCEL_REQUESTED for one that has not; UNKNOWN when Earth Engine answers that it has no task of
that id (for one, when it is asked in another project than the one the batch ran in).

It also reads the copies of the records that scripts/copy_run_results.py makes under
docs/reproducibility/ (they keep `drive_exports`), and the older records that key each Drive file by
its name (folder, task_id, kind). Every record is read before any file is written.

Exit 0 when every task of every record COMPLETED; 1 when one ended otherwise or is UNKNOWN, or a file
has no task id; 2 when none of those but a task has not ended yet (read again later); 3 when a record
cannot be read or placed (not JSON, no `drive_exports`, a name that does not end in `_run.json`, or
a `config` that is not the name's), before Earth Engine is set up; 4 when Earth Engine cannot be set
up or read. With 3 or 4 nothing is written.
"""

from __future__ import annotations

import argparse
import collections
import json
import shlex
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fmu.utils.provenance import git_state

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))  # for ee_read_only

RECORD_SUFFIX = "_run.json"
NOT_ENDED = ("READY", "RUNNING", "CANCEL_REQUESTED")
# A request deadline, as the pass runner's wait on its cache exports has, so that a read issued
# during a network drop fails rather than hangs.
DEADLINE_MS = 120_000

StatusReader = Callable[[list[str]], list[dict[str, Any]]]


class RecordError(ValueError):
    """A run record this script cannot read or place."""


def earth_engine_reader() -> StatusReader:
    """ee.data.getTaskStatus, on a session that can submit or change nothing."""
    import ee
    import ee_read_only

    from fmu.utils.gee import init_gee

    init_gee()
    ee_read_only.forbid_writes()
    ee.data.setDeadline(DEADLINE_MS)
    return ee.data.getTaskStatus


def load_record(path: Path) -> tuple[str, dict[str, dict[str, Any]]]:
    """(config, drive_exports) of a run record; RecordError when it cannot be read or placed."""
    config = path.name.removesuffix(RECORD_SUFFIX)
    if not path.name.endswith(RECORD_SUFFIX) or not config:
        raise RecordError(f"{path}: not a run record's name (<config>{RECORD_SUFFIX})")
    try:
        record = json.loads(path.read_text())
    except (OSError, ValueError) as e:
        raise RecordError(f"{path}: cannot be read as JSON ({e})") from e
    exports = record.get("drive_exports") if isinstance(record, dict) else None
    if not isinstance(exports, dict) or not all(isinstance(e, dict) for e in exports.values()):
        raise RecordError(f"{path}: no drive_exports, so not the record of an export pass")
    if record.get("config") != config:
        raise RecordError(f"{path}: its config is {record.get('config')!r}, not {config!r} as its name says")
    return config, exports


def task_ids(exports: dict[str, dict[str, Any]]) -> list[str]:
    """The record's task ids, in its order, each once; a file without one is left out."""
    return list(dict.fromkeys(e["task_id"] for e in exports.values() if e.get("task_id")))


def export_states(config: str, exports: dict[str, dict[str, Any]],
                  statuses: list[dict[str, Any]]) -> dict[str, Any]:
    """The result file: each Drive file's task state and error message. Results only."""
    by_id = {s.get("id"): s for s in statuses}
    unanswered = [i for i in task_ids(exports) if not isinstance(by_id.get(i, {}).get("state"), str)]
    if unanswered:
        raise RuntimeError(f"{config}: Earth Engine's answer gives no state for task(s) {unanswered}")
    files: dict[str, dict[str, Any]] = {}
    for key, entry in exports.items():
        task_id = entry.get("task_id") or None
        status = by_id[task_id] if task_id else {}
        files[key] = {
            "filename": entry.get("filename", key),
            "folder": entry.get("folder"),
            "task_id": task_id,
            "description": status.get("description"),
            "state": status.get("state"),
            "error_message": status.get("error_message"),
        }
    counts = collections.Counter(f["state"] for f in files.values() if f["task_id"])
    no_id = [key for key, f in files.items() if not f["task_id"]]
    return {
        "what": "How each Drive export of the run ended: the state of its Earth Engine task, read "
                "after the batch by scripts/drive_export_states.py. Results only.",
        "config": config,
        "files": files,
        "states": dict(sorted(counts.items())),
        "all_completed": not no_id and set(counts) <= {"COMPLETED"},
        "files_with_no_task_id": no_id,
    }


def exit_code(result: dict[str, Any]) -> int:
    """0: every task COMPLETED. 1: a file has no task id, or a task FAILED, was CANCELLED, is
    UNKNOWN or has a state this script does not know. 2: none of those, but a task has not ended."""
    states = set(result["states"])
    if result["files_with_no_task_id"] or states - {"COMPLETED", *NOT_ENDED}:
        return 1
    return 2 if states & set(NOT_ENDED) else 0


def _write(path: Path, text: str) -> str:
    before = path.read_text() if path.exists() else None
    path.write_text(text)
    return "wrote" if before is None else ("unchanged" if before == text else "replaced")


def main(argv: list[str] | None = None, reader: Callable[[], StatusReader] = earth_engine_reader) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("records", nargs="+", type=Path, help="run records, <config>_run.json")
    args = ap.parse_args(argv)
    given = sys.argv[1:] if argv is None else argv
    command_line = " ".join(["python", "scripts/drive_export_states.py", *map(shlex.quote, given)])

    # Which code: this script's checkout, as it is before anything is written (the rule review C38
    # set for the cost script's record).
    git = {k: v for k, v in git_state(HERE).items() if k != "root"}

    try:
        loaded = [(path, *load_record(path)) for path in args.records]
    except RecordError as e:
        print(f"REFUSED, nothing read and nothing written: {e}", file=sys.stderr)
        return 3

    read: list[tuple[Path, str, dict[str, Any], str]] = []
    try:
        get_status = reader()
        for path, config, exports in loaded:
            ids = task_ids(exports)
            statuses = get_status(ids) if ids else []
            read_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            read.append((path, config, export_states(config, exports, statuses), read_at))
    except Exception as e:  # noqa: BLE001 - any failure to read stops the run before it writes
        print(f"FAILED to read the task states from Earth Engine, nothing written: {e!r}",
              file=sys.stderr)
        return 4

    codes = []
    for path, config, result, read_at in read:
        out = path.with_name(f"{config}_drive_exports.json")
        done = _write(out, json.dumps(result, indent=1) + "\n")
        run = {
            "result_file": out.name,
            "run_record": path.name,
            "command_line": command_line,
            "read_at": read_at,
            "git": git,
        }
        _write(out.with_name(f"{config}_drive_exports_run.json"), json.dumps(run, indent=1) + "\n")
        codes.append(exit_code(result))
        counts = ", ".join(f"{state} {n}" for state, n in result["states"].items()) or "no task"
        no_id = len(result["files_with_no_task_id"])
        print(f"{config}: {len(result['files'])} Drive file(s): {counts}"
              f"{f'; {no_id} with no task id' if no_id else ''} ({done} {out})")
    return 1 if 1 in codes else (2 if 2 in codes else 0)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

"""scripts/drive_export_states.py, offline: how each Drive export of a run ended, read after a batch.

Nothing in a batch waits on the export stage's Drive tasks or records how they ended (review C39):
a config counts as finished once they are submitted. Jaskaran's answer to round 13's question 40
(b), round 14: "A read-only script, run after a batch, that reads the end state of every Drive task
id in each run record and writes it beside the record."

No Earth Engine call and no network: the task states come from a stand-in for
ee.data.getTaskStatus, handed to the script's main(); one test runs the script's own Earth Engine
reader against a stand-in `ee` module, to check that it forbids writes before it reads.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shlex
import shutil
import sys
import types
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "drive_export_states.py"
# Committed export-pass records: one as odisha_script/odisha_phase2_2_run_pipeline.py writes it, and
# one as scripts/copy_run_results.py copies it into docs/reproducibility/ (without submitted_at).
COMMITTED_RECORDS = (
    REPO / "odisha_script" / "phase2_vectors" / "odisha_alphaearth_angul_run.json",
    REPO / "docs" / "reproducibility" / "r9_runs" / "sanjay_van_baseline_keptland_r9_run.json",
)
# Task times as Earth Engine gives them (ms since 1970); none may reach the result file.
CREATED_MS, STARTED_MS, UPDATED_MS = 1760000000000, 1760000100000, 1760000200000


def _load() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("drive_export_states", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _status(task_id: str, state: str, description: str | None = None,
            error: str | None = None) -> dict[str, Any]:
    """One entry of ee.data.getTaskStatus's answer (earthengine-api 1.7.35)."""
    if state == "UNKNOWN":  # Earth Engine has no task of that id: a 404, answered so
        return {"id": task_id, "state": "UNKNOWN", "name": f"projects/p/operations/{task_id}"}
    out: dict[str, Any] = {
        "creation_timestamp_ms": CREATED_MS, "update_timestamp_ms": UPDATED_MS,
        "start_timestamp_ms": STARTED_MS, "attempt": 1, "state": state,
        "description": description, "task_type": "EXPORT_FEATURES", "priority": 100,
        "destination_uris": ["https://drive.google.com/#folders/abc"],
        "batch_eecu_usage_seconds": 12.5, "id": task_id, "name": f"projects/p/operations/{task_id}",
    }
    if error is not None:
        out["error_message"] = error
    return out


class _Tasks:
    """A stand-in for ee.data.getTaskStatus: the given state of each id, and a log of the asks."""

    def __init__(self, states: dict[str, tuple[str, str | None]]):
        self.states = states
        self.asked: list[list[str]] = []

    def __call__(self, task_ids: list[str]) -> list[dict[str, Any]]:
        self.asked.append(list(task_ids))
        out = []
        for i in task_ids:
            state, error = self.states.get(i, ("UNKNOWN", None))
            out.append(_status(i, state, description=f"desc_{i}", error=error))
        return out


def _record(folder: Path, config: str, files: dict[str, str | None], **extra: Any) -> Path:
    """A run record whose drive_exports holds one entry per file (file name -> task id)."""
    exports = {}
    for i, (filename, task_id) in enumerate(files.items()):
        exports[f"file_{i}"] = {
            "folder": "fmu_exports_test", "filename": filename, "format": "GEOJSON",
            "task_id": task_id, "submitted_at": "2026-10-26T10:00:00+00:00" if task_id else None,
            "task_submitted": task_id is not None,
        }
    path = folder / f"{config}_run.json"
    path.write_text(json.dumps({"config": config, "fingerprint": "0123456789",
                                "drive_exports": exports, **extra}, indent=1))
    return path


def _run(mod: types.ModuleType, records: list[Path], tasks: _Tasks) -> int:
    return mod.main([str(p) for p in records], reader=lambda: tasks)


def _states_file(record: Path) -> Path:
    return record.with_name(record.name.removesuffix("_run.json") + "_drive_exports.json")


def _states_record(record: Path) -> Path:
    return record.with_name(record.name.removesuffix("_run.json") + "_drive_exports_run.json")


@pytest.fixture
def mod() -> types.ModuleType:
    return _load()


@pytest.mark.parametrize("committed", COMMITTED_RECORDS, ids=lambda p: p.parent.name)
def test_every_drive_file_of_a_committed_record_gets_its_task_s_state(
        mod, tmp_path: Path, committed: Path):
    record = tmp_path / committed.name
    shutil.copy2(committed, record)
    exports = json.loads(record.read_text())["drive_exports"]
    assert len(exports) == 9  # three rasters, three layers in two formats
    tasks = _Tasks({e["task_id"]: ("COMPLETED", None) for e in exports.values()})
    assert _run(mod, [record], tasks) == 0
    result = json.loads(_states_file(record).read_text())
    assert result["config"] == committed.name.removesuffix("_run.json")
    assert list(result["files"]) == list(exports)
    for key, entry in exports.items():
        assert result["files"][key] == {
            "filename": entry["filename"], "folder": entry["folder"], "task_id": entry["task_id"],
            "description": f"desc_{entry['task_id']}", "state": "COMPLETED", "error_message": None,
        }
    assert result["states"] == {"COMPLETED": len(exports)}
    assert result["all_completed"] is True
    assert tasks.asked == [[e["task_id"] for e in exports.values()]]


def test_a_failed_and_a_cancelled_task_are_recorded_with_their_messages(mod, tmp_path: Path):
    record = _record(tmp_path, "cfg_a", {"cfg_a_cluster_labels.tif": "T1",
                                         "cfg_a_features_raw.tif": "T2",
                                         "cfg_a_stands_merged.geojson": "T3"})
    tasks = _Tasks({"T1": ("COMPLETED", None),
                    "T2": ("FAILED", "Exported bands must have compatible data types."),
                    "T3": ("CANCELLED", "Cancelled.")})
    assert _run(mod, [record], tasks) == 1
    files = json.loads(_states_file(record).read_text())["files"]
    assert [(f["filename"], f["state"], f["error_message"]) for f in files.values()] == [
        ("cfg_a_cluster_labels.tif", "COMPLETED", None),
        ("cfg_a_features_raw.tif", "FAILED", "Exported bands must have compatible data types."),
        ("cfg_a_stands_merged.geojson", "CANCELLED", "Cancelled."),
    ]
    result = json.loads(_states_file(record).read_text())
    assert result["states"] == {"CANCELLED": 1, "COMPLETED": 1, "FAILED": 1}
    assert result["all_completed"] is False


def test_tasks_not_ended_yet_are_recorded_as_they_stand_and_exit_2(mod, tmp_path: Path):
    record = _record(tmp_path, "cfg_b", {"a.tif": "T1", "b.tif": "T2", "c.tif": "T3"})
    tasks = _Tasks({"T1": ("COMPLETED", None), "T2": ("RUNNING", None), "T3": ("READY", None)})
    assert _run(mod, [record], tasks) == 2
    result = json.loads(_states_file(record).read_text())
    assert [f["state"] for f in result["files"].values()] == ["COMPLETED", "RUNNING", "READY"]


def test_a_task_earth_engine_does_not_know_is_unknown_and_exits_1(mod, tmp_path: Path):
    record = _record(tmp_path, "cfg_c", {"a.tif": "T1", "b.tif": "GONE"})
    tasks = _Tasks({"T1": ("RUNNING", None)})  # GONE: no such task
    assert _run(mod, [record], tasks) == 1
    gone = json.loads(_states_file(record).read_text())["files"]["file_1"]
    assert gone == {"filename": "b.tif", "folder": "fmu_exports_test", "task_id": "GONE",
                    "description": None, "state": "UNKNOWN", "error_message": None}


def test_a_file_with_no_task_id_is_listed_and_not_asked_for(mod, tmp_path: Path):
    record = _record(tmp_path, "cfg_d", {"a.tif": "T1", "b.tif": None})
    tasks = _Tasks({"T1": ("COMPLETED", None)})
    assert _run(mod, [record], tasks) == 1
    result = json.loads(_states_file(record).read_text())
    assert tasks.asked == [["T1"]]
    assert result["files"]["file_1"]["task_id"] is None
    assert result["files"]["file_1"]["state"] is None
    assert result["files_with_no_task_id"] == ["file_1"]


def test_the_result_holds_results_only_no_time_or_date(mod, tmp_path: Path):
    """CLAUDE.md, Results: no run times or dates, so that git diff after a re-read shows a change
    of state only. The record's submitted_at and the tasks' times stay out."""
    record = _record(tmp_path, "cfg_e", {"a.tif": "T1", "b.zip": "T2"})
    _run(mod, [record], _Tasks({"T1": ("COMPLETED", None), "T2": ("FAILED", "x")}))
    text = _states_file(record).read_text()
    for number in (CREATED_MS, STARTED_MS, UPDATED_MS):
        assert str(number) not in text
    assert not re.search(r"20\d\d-\d\d-\d\d", text)

    def keys(obj: Any) -> list[str]:
        if isinstance(obj, dict):
            return [*obj, *(k for v in obj.values() for k in keys(v))]
        if isinstance(obj, list):
            return [k for v in obj for k in keys(v)]
        return []

    timed = [k for k in keys(json.loads(text))
             if any(w in k for w in ("time", "date", "submitted", "_ms", "elapsed", "eecu"))]
    assert timed == []


def test_a_second_read_that_finds_the_same_states_leaves_the_result_unchanged(mod, tmp_path: Path):
    record = _record(tmp_path, "cfg_f", {"a.tif": "T1", "b.tif": "T2"})
    tasks = _Tasks({"T1": ("COMPLETED", None), "T2": ("COMPLETED", None)})
    _run(mod, [record], tasks)
    first = _states_file(record).read_bytes()
    _run(mod, [record], tasks)
    assert _states_file(record).read_bytes() == first


def test_the_record_beside_it_names_the_command_when_it_was_read_and_the_git_state(
        mod, tmp_path: Path, monkeypatch):
    record = _record(tmp_path, "cfg_g", {"a.tif": "T1"})
    asked_at: list[bool] = []

    def git_state(start: Path | None = None, **_kwargs: Any) -> dict[str, Any]:
        # read before anything is written (review C38's rule for the scripts' records)
        asked_at.append(_states_file(record).exists() or _states_record(record).exists())
        assert start is not None and Path(start).resolve() == SCRIPT.parent.resolve()
        return {"commit": "c0ffee", "dirty": False, "modified": [], "modified_truncated": False,
                "untracked": [], "untracked_truncated": False, "root": "/somewhere", "error": None}

    monkeypatch.setattr(mod, "git_state", git_state)
    assert mod.main([str(record)], reader=lambda: _Tasks({"T1": ("COMPLETED", None)})) == 0
    assert asked_at == [False]
    run = json.loads(_states_record(record).read_text())
    assert run["result_file"] == "cfg_g_drive_exports.json"
    assert run["run_record"] == "cfg_g_run.json"
    assert run["command_line"] == f"python scripts/drive_export_states.py {shlex.quote(str(record))}"
    assert datetime.strptime(run["read_at"], "%Y-%m-%dT%H:%M:%SZ")
    assert run["git"] == {"commit": "c0ffee", "dirty": False, "modified": [],
                          "modified_truncated": False, "untracked": [],
                          "untracked_truncated": False, "error": None}


def test_the_older_record_keyed_by_file_name_is_read_too(mod, tmp_path: Path):
    """The kept-land Koraput records of docs/reproducibility/keptland_runs key each Drive file by
    its name, with folder, task_id and kind."""
    record = tmp_path / "old_cfg_run.json"
    record.write_text(json.dumps({"config": "old_cfg", "drive_exports": {
        "old_cfg_cluster_labels.tif": {"folder": "fmu_exports_kept_land", "task_id": "T1",
                                       "kind": "raster"}}}))
    assert _run(mod, [record], _Tasks({"T1": ("COMPLETED", None)})) == 0
    files = json.loads(_states_file(record).read_text())["files"]
    assert files == {"old_cfg_cluster_labels.tif": {
        "filename": "old_cfg_cluster_labels.tif", "folder": "fmu_exports_kept_land",
        "task_id": "T1", "description": "desc_T1", "state": "COMPLETED", "error_message": None}}


@pytest.mark.parametrize("problem", ["no drive_exports", "not a run record's name",
                                     "config differs from the name", "not JSON"])
def test_a_record_it_cannot_place_is_refused_before_anything_is_read(mod, tmp_path: Path, problem):
    good = _record(tmp_path, "cfg_ok", {"a.tif": "T1"})
    if problem == "no drive_exports":
        bad = tmp_path / "cfg_bad_run.json"
        bad.write_text(json.dumps({"config": "cfg_bad"}))
    elif problem == "not a run record's name":
        bad = tmp_path / "cfg_bad.json"
        bad.write_text(json.dumps({"config": "cfg_bad", "drive_exports": {}}))
    elif problem == "config differs from the name":
        bad = _record(tmp_path, "cfg_bad", {"b.tif": "T2"})
        bad.write_text(json.dumps({**json.loads(bad.read_text()), "config": "another"}))
    else:
        bad = tmp_path / "cfg_bad_run.json"
        bad.write_text("{not json")
    readers: list[int] = []

    def reader() -> _Tasks:
        readers.append(1)
        return _Tasks({})

    assert mod.main([str(good), str(bad)], reader=reader) == 3
    assert readers == []  # Earth Engine was never set up, let alone asked
    assert not _states_file(good).exists() and not _states_record(good).exists()


@pytest.mark.parametrize("failure", ["set-up fails", "a read fails", "an id is not answered"])
def test_when_earth_engine_cannot_be_read_nothing_is_written(mod, tmp_path: Path, failure):
    """Every record is read before any file is written, so a failure part way leaves none."""
    one = _record(tmp_path, "cfg_r1", {"a.tif": "T1"})
    two = _record(tmp_path, "cfg_r2", {"b.tif": "T2"})
    tasks = _Tasks({"T1": ("COMPLETED", None), "T2": ("COMPLETED", None)})

    def reader() -> Any:
        if failure == "set-up fails":
            raise RuntimeError("GEE project ID is not set. Set GEE_PROJECT_ID in .env.")
        if failure == "a read fails":
            def get_status(ids: list[str]) -> list[dict[str, Any]]:
                if ids == ["T2"]:
                    raise TimeoutError("the request deadline passed")
                return tasks(ids)
            return get_status
        return lambda ids: [s for s in tasks(ids) if s["id"] != "T2"]

    assert mod.main([str(one), str(two)], reader=reader) == 4
    for record in (one, two):
        assert not _states_file(record).exists() and not _states_record(record).exists()


def test_several_records_are_read_with_one_reader_each_beside_its_own_record(mod, tmp_path: Path):
    (tmp_path / "x").mkdir()
    (tmp_path / "y").mkdir()
    one = _record(tmp_path / "x", "cfg_1", {"a.tif": "T1"})
    two = _record(tmp_path / "y", "cfg_2", {"b.tif": "T2"})
    made: list[_Tasks] = []

    def reader() -> _Tasks:
        made.append(_Tasks({"T1": ("COMPLETED", None), "T2": ("FAILED", "boom")}))
        return made[-1]

    assert mod.main([str(one), str(two)], reader=reader) == 1
    assert len(made) == 1 and made[0].asked == [["T1"], ["T2"]]
    assert json.loads(_states_file(one).read_text())["states"] == {"COMPLETED": 1}
    assert json.loads(_states_file(two).read_text())["states"] == {"FAILED": 1}
    assert _states_record(one).exists() and _states_record(two).exists()


def test_the_earth_engine_reader_forbids_writes_before_it_reads(mod, tmp_path: Path, monkeypatch):
    """main() without a reader sets up Earth Engine itself: init_gee, then
    ee_read_only.forbid_writes(), then ee.data.getTaskStatus. Run here against a stand-in `ee`."""
    import fmu.utils.gee

    record = _record(tmp_path, "cfg_live", {"a.tif": "T1"})
    calls: list[str] = []

    def refused_already() -> bool:
        return getattr(fake_ee.batch.Task.start, "__name__", "").startswith("forbidden_")

    def get_task_status(task_ids: list[str]) -> list[dict[str, Any]]:
        calls.append(f"getTaskStatus, writes forbidden: {refused_already()}")
        return [_status(i, "COMPLETED", description=f"desc_{i}") for i in task_ids]

    def must_not_run(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("a write reached the stand-in")

    fake_ee = types.ModuleType("ee")
    fake_ee.batch = types.SimpleNamespace(Task=types.SimpleNamespace(start=must_not_run))
    fake_ee.data = types.SimpleNamespace(
        getTaskStatus=get_task_status, cancelTask=must_not_run, exportTable=must_not_run,
        setDeadline=lambda ms: calls.append(f"setDeadline {ms}"))
    monkeypatch.setitem(sys.modules, "ee", fake_ee)
    monkeypatch.setattr(fmu.utils.gee, "init_gee", lambda *a, **k: calls.append("init_gee"))
    assert mod.main([str(record)]) == 0
    assert calls[0] == "init_gee"
    assert calls[-1] == "getTaskStatus, writes forbidden: True"
    assert fake_ee.data.cancelTask.__name__ == "forbidden_cancelTask"
    assert json.loads(_states_file(record).read_text())["states"] == {"COMPLETED": 1}

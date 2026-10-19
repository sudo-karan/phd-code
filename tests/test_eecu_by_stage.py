"""scripts/eecu_by_stage.py, offline: the stage each task is given to, the pass spans, the sums.

No Earth Engine call: the task list and the wrapper log are made up here, but for one test that
runs the real run_config_passes.sh with a stand-in for the interpreter, which reaches nothing.
"""

from __future__ import annotations

import importlib.util
import inspect
import json
import os
import re
import shutil
import subprocess
import typing
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import fmu.stages.clustering  # noqa: F401  (registers the stage, as the runner does)
import fmu.stages.data_load  # noqa: F401
import fmu.stages.export as export
import fmu.stages.features_embedding  # noqa: F401
import fmu.stages.features_optical  # noqa: F401
import fmu.stages.features_radar  # noqa: F401
import fmu.stages.features_static  # noqa: F401
import fmu.stages.features_structure  # noqa: F401
import fmu.stages.k_elbow  # noqa: F401
import fmu.stages.masking  # noqa: F401
import fmu.stages.merge  # noqa: F401
import fmu.stages.metrics  # noqa: F401
import fmu.stages.profiling  # noqa: F401
import fmu.stages.segmentation  # noqa: F401
from fmu.config import ExportParams
from fmu.pipeline import Pipeline
from fmu.stages.base import _stage_registry

REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("eecu_by_stage", REPO / "scripts" / "eecu_by_stage.py")
assert _spec and _spec.loader
E = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(E)

CFG = "odisha_v120_3ha_tile10km_angul_keptland_s1desc_r9"


@pytest.mark.parametrize(("output", "stage"), [
    ("masking_habitat_mask", "masking"),
    ("data_load_s2_composite", "data_load"),
    ("features_optical_optical_features", "features_optical"),
    ("features_static_static_features", "features_static"),
    ("features_embedding_embedding_features", "features_embedding"),
    ("segmentation_snic_means", "segmentation"),
    ("clustering_feature_stack", "clustering"),
    ("k_elbow_k_elbow", "k_elbow"),
    ("features_raw", "export"),
    ("features_scaled", "export"),
    ("cluster_labels", "export"),
    ("stands_merged_geojson", "export"),
    # Not a name a task of the config takes: before round 13, "other: <output>", and charged.
    ("something_else", None),
    ("repro_masking_habitat_mask", None),  # <config>_repro's
    ("check_data_load_s2_composite", None),  # <config>_check's, as <name>_r9_check is <name>_r9's
])
def test_each_task_goes_to_the_stage_its_description_names(output, stage):
    assert E.stage_of(output) == stage


def test_the_names_are_those_the_steps_cache_and_the_export_stage_sends():
    """The table the tasks are matched against (review B26), against the pipeline's own: each
    stage's cacheable outputs, and the export stage's three rasters and its vector layers in each
    format."""
    cached = {}
    for name, cls in _stage_registry.items():
        if cls.__module__.startswith("fmu.stages."):
            keys = Pipeline._resolve_cacheable_outputs(cls())
            if keys:
                cached[name] = sorted(keys)
    assert cached == {stage: sorted(keys) for stage, keys in E.CACHED.items()}
    rasters = re.findall(r'f"\{config\.name\}_(\w+)"', inspect.getsource(export))
    (fmt,) = typing.get_args(ExportParams.model_fields["vector_formats"].annotation)
    layers = (export._MERGED_LAYER_NAME, export._SNIC_LAYER_NAME, export._DISSOLVED_LAYER_NAME)
    assert sorted(E.EXPORT_FILES) == sorted(
        rasters + [f"{layer}_{f}" for layer in layers for f in typing.get_args(fmt)])


def _hours(spans):
    return [(name, round((b - a).total_seconds() / 3600, 2)) for name, a, b in spans]


def test_each_pass_runs_to_the_next_header_of_any_config_and_the_last_to_the_batch_end():
    """Review B26: a pass ran to the costed config's own next pass, over the passes of the other
    configs in between, and its last pass to the batch's end."""
    log = "\n".join([
        "[run_passes_safely 2026-10-18 16:29:54] batch i_tile started from commit be36f74",
        f"##### PASS1 {CFG} :: features :: 16:29:57 #####",
        f"##### PASS1 {CFG} :: segmentation :: 16:54:45 #####",
        "##### PASS1 another_config :: features :: 16:55:00 #####",
        f"##### PASS1 {CFG} :: export :: 17:10:00 #####",
        "[run_passes_safely 2026-10-18 17:20:30] batch i_tile ended: ALL CONFIGS COMPLETE",
    ])
    spans = E.pass_spans(log, CFG)
    assert [(n, a.strftime("%H:%M:%S"), b.strftime("%H:%M:%S")) for n, a, b in spans] == [
        ("features", "10:59:57", "11:24:45"),  # 16:29:57 IST
        ("segmentation", "11:24:45", "11:25:00"),  # to another_config's header
        ("export", "11:40:00", "11:50:30"),  # to the batch's end
    ]
    assert spans[0][1] == datetime(2026, 10, 18, 10, 59, 57, tzinfo=UTC)


def test_a_log_whose_headers_carry_the_time_only_is_dated_past_midnight():
    """Review B26: every pass took the date of the log's first line. Round 2's odisha_squares_3ha
    log (13 Oct 23:58 to 14 Oct 02:54, shortened here) gave spans of -23.59 h and +26.46 h."""
    log = "\n".join([
        "[run_passes_safely 2026-10-13 23:58:06] batch sq started from commit 4795358",
        "[run_passes_safely 2026-10-13 23:58:09] pass 1: k a",
        "##### PASS1 k :: segmentation :: 23:58:10 #####",
        "##### PASS1 k :: clustering :: 00:23:00 #####",
        "##### PASS1 k :: export :: 00:27:29 #####",
        "##### PASS1 a :: segmentation :: 00:30:08 #####",
        "[run_passes_safely 2026-10-14 00:42:07] pass 1 exit=1; finished: ['k']",
        "[run_passes_safely 2026-10-14 01:48:09] pass 2: a",
        "##### PASS1 a :: segmentation :: 01:48:09 #####",
        "[run_passes_safely 2026-10-14 02:54:50] batch sq ended: NOT ALL COMPLETE",
    ])
    assert _hours(E.pass_spans(log, "k")) == [("segmentation", 0.41), ("clustering", 0.07),
                                              ("export", 0.04)]
    assert E.pass_spans(log, "k")[1][1] == datetime(2026, 10, 13, 18, 53, tzinfo=UTC)  # 00:23 IST


def test_a_header_with_its_date_is_read_so_and_a_batch_stopped_ends_its_last_pass():
    """Since round 13 a stage header carries its date. A label's log can hold a batch that was
    stopped and the batch that resumed it; the stopped pass ends with its batch."""
    log = "\n".join([
        "[run_passes_safely 2026-10-20 23:50:00] batch b started from commit abc1234",
        "##### PASS1 x :: features :: 2026-10-20 23:50:03 #####",
        "##### PASS1 x :: segmentation :: 2026-10-21 00:10:00 #####",
        "[run_passes_safely 2026-10-21 00:12:00] batch b ended: NOT ALL COMPLETE (stopped by SIGINT)",
        "[run_passes_safely 2026-10-21 09:00:00] batch b started from commit abc1234",
        "[run_passes_safely 2026-10-21 09:00:01] pass 1: x",
        "##### PASS1 x :: features :: 2026-10-21 09:00:01 #####",
        "##### PASS1 x :: segmentation :: 2026-10-21 09:00:37 #####",
        "##### PASS1 x :: clustering :: 2026-10-21 09:05:00 #####",
        "##### PASS1 x :: export :: 2026-10-21 09:10:00 #####",
        "[run_passes_safely 2026-10-21 09:12:30] batch b ended: ALL CONFIGS COMPLETE",
    ])
    assert _hours(E.pass_spans(log, "x")) == [
        ("features", 0.33), ("segmentation", 0.03),  # to the stopped batch's end, not to 09:00
        ("features", 0.01), ("segmentation", 0.07), ("clustering", 0.08), ("export", 0.04)]


def test_a_pass_whose_batch_has_no_end_line_is_refused():
    """A check of the B26 fix (round 13): a batch that ended with no "batch ... ended" line (the
    wrapper killed outright, or a crash) ran its last pass to the next batch's "started" line in
    the label's log, ten hours later here, and charged it the project's online use over the gap."""
    log = "\n".join([
        "[run_passes_safely 2026-10-20 22:00:00] batch b started from commit abc1234",
        "##### PASS1 x :: features :: 2026-10-20 22:00:03 #####",
        "##### PASS1 x :: segmentation :: 2026-10-20 22:20:00 #####",
        "##### PASS1 x :: clustering :: 2026-10-20 22:30:00 #####",
        "##### PASS1 x :: export :: 2026-10-20 22:40:00 #####",
        "[run_passes_safely 2026-10-21 09:00:00] batch b started from commit abc1234",
        "[run_passes_safely 2026-10-21 09:00:01] b: skipped, an earlier batch of label b finished it",
        "[run_passes_safely 2026-10-21 09:00:02] batch b ended: ALL CONFIGS COMPLETE",
    ])
    with pytest.raises(ValueError, match="no line of its own batch ends x's export pass"):
        E.pass_spans(log, "x")


def test_a_log_without_the_config_is_refused():
    with pytest.raises(ValueError):
        E.pass_spans("[run_passes_safely 2026-10-18 16:29:54] batch x ended", CFG)


PASS_SCRIPT = REPO / "odisha_script" / "run_config_passes.sh"
BASH = shutil.which("bash")


@pytest.mark.skipif(BASH is None, reason="needs bash")
def test_the_pass_script_writes_the_date_in_each_stage_header(tmp_path: Path):
    """run_config_passes.sh, with a stand-in for the interpreter that runs nothing: each stage
    header carries the date, the exit lines the wrapper reads are as before, and the spans read
    from the log it writes are dated."""
    python = tmp_path / "python"
    python.write_text("#!/bin/sh\nexit 0\n")
    python.chmod(0o755)
    log = tmp_path / "batch.log"
    start = datetime.now()
    log.write_text(f"[run_passes_safely {start:%Y-%m-%d %H:%M:%S}] batch b started from commit c\n")
    env = {**os.environ, "PYTHON": str(python), "MAX_PASSES": "1", "RUN_PASSES_SAFELY": "1"}
    subprocess.run([BASH, str(PASS_SCRIPT), str(log), "configs/x.yaml"], cwd=tmp_path, env=env,
                   check=True, capture_output=True, timeout=120)
    end = datetime.now() + timedelta(seconds=1)
    with log.open("a") as f:
        f.write(f"[run_passes_safely {end:%Y-%m-%d %H:%M:%S}] batch b ended: ALL CONFIGS COMPLETE\n")
    lines = log.read_text().splitlines()
    headers = [line for line in lines if line.startswith("#####")]
    assert [re.sub(r"\d", "9", h) for h in headers] == [
        f"##### PASS9 x :: {s} :: 9999-99-99 99:99:99 #####"
        for s in ("features", "segmentation", "clustering", "export")]
    assert [line for line in lines if line.startswith("---")] == [
        f"--- PASS1 x {s} exit=0 ---" for s in ("features", "segmentation", "clustering", "export")]
    spans = E.pass_spans(log.read_text(), "x")
    assert [n for n, _, _ in spans] == ["features", "segmentation", "clustering", "export"]
    for _, a, b in spans:  # in the clock the script wrote them in
        local_a, local_b = ((t + E.IST).replace(tzinfo=None) for t in (a, b))
        assert start.replace(microsecond=0) <= local_a <= local_b <= end


def test_batch_hours_are_summed_by_stage_failed_tasks_included_others_left_out():
    def op(desc, seconds, state="SUCCEEDED"):
        return {"metadata": {"description": desc, "batchEecuUsageSeconds": seconds, "state": state}}

    ops = [op(f"{CFG}_data_load_s2_composite", 7200), op(f"{CFG}_data_load_s2_composite", 3600, "FAILED"),
           op(f"{CFG}_stands_merged_shp", 36), op(f"{CFG}_features_raw", 360),
           op("odisha_v120_3ha_squares_angul_keptland_s1desc_r9_data_load_s2_composite", 9999)]
    hours, tasks = E.batch_by_stage(ops, CFG)
    assert hours == {"data_load": 3.0, "export": 0.11}
    assert [t["state"] for t in tasks["data_load"]] == ["SUCCEEDED", "FAILED"]
    result = E.summary(CFG, 10_000.0, hours, [("features", 0.5), ("export", 0.1)], tasks)
    assert result["batch_total"] == 3.11 and result["online_total"] == 0.6 and result["total"] == 3.71
    assert result["batch_eecu_h_per_1000_ha"]["data_load"] == 0.3
    assert result["total_per_1000_ha"] == 0.371
    assert "read_at" not in result and "from" not in str(result["online_eecu_h_by_pass"])


def test_the_tasks_of_a_config_whose_name_extends_this_one_are_not_charged_to_it():
    """Review B26: every task whose description began with the config's name and "_" was charged
    to it, so those of <config>_repro and <config>_r9_check (72 such pairs in configs/) were added."""
    def op(desc, seconds):
        return {"metadata": {"description": desc, "batchEecuUsageSeconds": seconds, "state": "SUCCEEDED"}}

    ops = [op(f"{CFG}_data_load_s2_composite", 3600), op(f"{CFG}_features_raw", 360),
           op(f"{CFG}_repro_data_load_s2_composite", 7200), op(f"{CFG}_repro_features_raw", 720),
           op(f"{CFG}_check_masking_habitat_mask", 36)]
    hours, tasks = E.batch_by_stage(ops, CFG)
    assert hours == {"data_load": 1.0, "export": 0.1}
    assert sum(len(t) for t in tasks.values()) == 2


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.org",
                           "-c", "commit.gpgsign=false", *args],
                          capture_output=True, text=True, check=True).stdout.strip()


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
@pytest.mark.parametrize("started_in", ["the script's checkout", "another repository"])
def test_the_run_record_names_the_scripts_checkout_as_it_was_before_the_result_was_written(
        tmp_path: Path, monkeypatch, started_in):
    """Review C38: the record read git in the working directory, after OUT.json was written. Run
    from another repository it named that one's commit, and measured again into a committed cost
    file it recorded tracked files as modified (the new numbers), though no code had changed."""
    import sys
    import types

    checkout, other = tmp_path / "checkout", tmp_path / "other"
    (checkout / "scripts").mkdir(parents=True)
    shutil.copy2(REPO / "scripts" / "eecu_by_stage.py", checkout / "scripts" / "eecu_by_stage.py")
    out = checkout / "cost.json"
    out.write_text('{"total": 1.0}\n')
    for repo in (checkout, other):
        repo.mkdir(exist_ok=True)
        _git(repo, "init", "-q")
        (repo / "README").write_text(repo.name)
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", repo.name)
    log = tmp_path / "batch.log"
    log.write_text("")

    class _Creds:
        token = "t"

        def refresh(self, request):
            return None

    fake_ee = types.ModuleType("ee")
    fake_ee.Initialize = lambda **kwargs: None
    fake_ee.data = types.SimpleNamespace(get_persistent_credentials=_Creds, listOperations=lambda: [])
    monkeypatch.setitem(sys.modules, "ee", fake_ee)
    spec = importlib.util.spec_from_file_location("eecu_copy", checkout / "scripts" / "eecu_by_stage.py")
    assert spec and spec.loader
    copy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(copy)
    monkeypatch.setattr(copy, "pass_spans", lambda text, config: [])
    monkeypatch.setattr(copy, "online_hours", lambda *a: 0.0)
    monkeypatch.chdir(checkout if started_in == "the script's checkout" else other)
    assert copy.main([CFG, str(log), "100", str(out)]) == 0
    assert json.loads(out.read_text())["total"] == 0.0  # the committed file now holds new numbers
    record = json.loads((checkout / "cost_run.json").read_text())
    assert record["git"]["commit"] == _git(checkout, "rev-parse", "HEAD")
    # Called tracked_files_modified before round 13; now the block every run record has.
    assert record["git"].get("dirty", record["git"].get("tracked_files_modified")) is False
    assert record["git"]["modified"] == []

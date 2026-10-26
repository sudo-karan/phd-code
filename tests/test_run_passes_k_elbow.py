"""A batch that stops after the k elbow (round 14, Task 2.4): `--through k_elbow`.

docs/decisions.yaml, spec-batch-through-the-k-elbow. With k_elbow.in_fit_space on, the k elbow
step needs nothing of the clustering stage, so a batch can run features, segmentation and the
elbow (the merge runs inside the elbow's pass) and submit no clustering, profiling or export
task. The wrapper takes `--through k_elbow`, refuses it for a config with the setting off,
hands the shell script its list of stages, counts a config as done when its last stage exits 0,
and keeps a batch through the elbow apart from a full one under the same label. A full batch of
configs with the setting on runs the elbow's pass before clustering. The real wrapper and shell
script run against the modelled Earth Engine of tests/_wrapper_harness.py; the runner's pass is
tested offline.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from _wrapper_harness import Harness

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "odisha_script"))

import odisha_phase2_2_run_pipeline as runner  # noqa: E402
import run_passes_safely  # noqa: E402

from fmu.config import Config, load_config  # noqa: E402
from fmu.pipeline import feature_stage_names  # noqa: E402

needs_bash = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
BOX = REPO / "configs" / "odisha_v120_3ha_squares_kendujhar_keptland_s1desc.yaml"


def _with_elbow(path: Path) -> Config:
    import yaml

    raw = yaml.safe_load(path.read_text())
    raw["clustering"] = {**raw.get("clustering", {}), "fit_outside_earth_engine": True}
    raw["k_elbow"] = {"in_fit_space": True}
    return Config.model_validate(raw)


# ---------- the runner's pass ----------


def test_the_runner_knows_the_pass_and_it_needs_the_features_and_segmentation_only():
    assert runner.PASSES == ("features", "segmentation", "k_elbow", "clustering", "export")
    cfg = _with_elbow(BOX)
    assert runner.prerequisites(cfg, "k_elbow") == [*feature_stage_names(cfg), "segmentation"]
    names = runner.stage_names(cfg, "k_elbow")
    assert names[-1] == "k_elbow" and "clustering" not in names and "merge" in names


def test_the_runner_refuses_the_elbow_pass_for_a_config_with_the_setting_off(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["runner", "--config", str(BOX), "--through", "k_elbow"])
    monkeypatch.setattr(runner, "init_gee", lambda: (_ for _ in ()).throw(AssertionError("no Earth Engine")))
    assert runner.main() == runner.ELBOW_NEEDS_THE_SETTING
    assert "k_elbow.in_fit_space" in capsys.readouterr().out


def test_the_files_of_a_stage_that_ran_are_copied_beside_the_layers(tmp_path, monkeypatch):
    run_dir = tmp_path / "runs" / "x_2026"
    run_dir.mkdir(parents=True)
    (run_dir / "k_elbow_fit_rows.csv").write_text("stand_lbl,in_fit\n1,1\n")
    vectors = tmp_path / "phase2_vectors"
    monkeypatch.setattr(runner, "VECTOR_DIR", vectors)

    class _Stage:
        name, files = "k_elbow", {"k_elbow_fit_rows.csv": {"bytes": 20, "sha256": "x"}}

    copied = runner.copy_stage_files("cfg_r14", run_dir, [_Stage()])
    assert (vectors / "cfg_r14_k_elbow_fit_rows.csv").read_text() == "stand_lbl,in_fit\n1,1\n"
    assert copied == {"cfg_r14_k_elbow_fit_rows.csv": {"bytes": 20, "sha256": "x"}}


# ---------- the shell script ----------


@needs_bash
def test_the_shell_script_runs_the_stages_the_wrapper_gives_it(tmp_path: Path):
    python = tmp_path / "python"
    python.write_text('#!/bin/sh\necho "$*" >> "$STAND_IN_RECORD"\n')
    python.chmod(0o755)
    env = run_passes_safely.pass_env(str(python), tmp_path, stages=("features", "segmentation", "k_elbow"))
    assert env["STAGES"] == "features segmentation k_elbow"
    env = {**env, "STAND_IN_RECORD": str(tmp_path / "calls.txt")}
    got = subprocess.run(
        ["bash", str(REPO / "odisha_script" / "run_config_passes.sh"), str(tmp_path / "batch.log"),
         "configs/x_r14.yaml"], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120)
    assert got.returncode == 0, got.stdout + got.stderr
    calls = (tmp_path / "calls.txt").read_text().splitlines()
    assert [c.split("--through ")[1] for c in calls] == [
        "features --wait", "segmentation --wait", "k_elbow --wait"]
    exits = [m.groups() for line in (tmp_path / "batch.log").read_text().splitlines()
             if (m := run_passes_safely.STAGE_EXIT.match(line.strip()))]
    assert exits == [("x_r14", s, "0") for s in ("features", "segmentation", "k_elbow")]


@needs_bash
def test_the_shell_script_refuses_a_stage_it_does_not_know(tmp_path: Path):
    env = {**run_passes_safely.pass_env("python", tmp_path), "STAGES": "features clusterin"}
    got = subprocess.run(
        ["bash", str(REPO / "odisha_script" / "run_config_passes.sh"), str(tmp_path / "batch.log"),
         "configs/x.yaml"], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60)
    assert got.returncode == 97 and "clusterin" in got.stderr


def test_the_wrappers_environment_always_names_the_stages(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("STAGES", "features")  # a stray variable does not change a normal batch
    env = run_passes_safely.pass_env("python", tmp_path)
    assert env["STAGES"] == "features segmentation clustering export"


def test_the_stage_lists_follow_the_setting():
    assert run_passes_safely.stages_for("export", elbow=False) == (
        "features", "segmentation", "clustering", "export")
    assert run_passes_safely.stages_for("export", elbow=True) == (
        "features", "segmentation", "k_elbow", "clustering", "export")
    assert run_passes_safely.stages_for("k_elbow", elbow=True) == ("features", "segmentation", "k_elbow")


# ---------- the wrapper, against the modelled Earth Engine ----------


@pytest.fixture
def harness(tmp_path: Path):
    h = Harness(tmp_path)
    yield h
    h.cleanup()


def _state(h: Harness, label: str = "batch") -> dict:
    return h.state(label)


def _passes_run(h: Harness) -> list[tuple[str, str]]:
    return [(name, stage) for _, _, name, stage in h.runners()]


def _finish(h: Harness, p) -> tuple[int, str]:
    return h.finish(p)


@needs_bash
def test_a_batch_through_the_elbow_runs_no_clustering_and_no_export(harness: Harness):
    a = harness.config("cfg_a_r14", elbow_in_fit_space=True)
    b = harness.config("cfg_b_r14", elbow_in_fit_space=True)
    harness.commit()
    p = harness.start("--through", "k_elbow", a, b)
    rc, out = _finish(harness, p)
    assert rc == 0, out
    assert _passes_run(harness) == [
        (n, s) for n in ("cfg_a_r14", "cfg_b_r14") for s in ("features", "segmentation", "k_elbow")
    ]
    tasks = json.loads((harness.ee / "tasks.json").read_text())
    assert not [t for t in tasks if "clustering" in t["description"] or "stands_" in t["description"]]
    state = _state(harness)
    assert state["through"] == "k_elbow" and state["stages"] == ["features", "segmentation", "k_elbow"]
    assert state["done"] == ["cfg_a_r14", "cfg_b_r14"]


@needs_bash
def test_a_full_batch_of_configs_with_the_setting_on_runs_the_elbow_before_clustering(harness: Harness):
    a = harness.config("cfg_a_r14", elbow_in_fit_space=True)
    harness.commit()
    p = harness.start(a)
    rc, out = _finish(harness, p)
    assert rc == 0, out
    assert [s for _, s in _passes_run(harness)] == [
        "features", "segmentation", "k_elbow", "clustering", "export"]
    assert _state(harness)["done"] == ["cfg_a_r14"]


@needs_bash
@pytest.mark.parametrize("through", ["k_elbow", "export"])
def test_a_batch_refuses_a_config_with_the_setting_off_or_a_mix(harness: Harness, through: str):
    on = harness.config("cfg_on_r14", elbow_in_fit_space=True)
    off = harness.config("cfg_off")
    harness.commit()
    args = ("--through", through, on, off)
    p = harness.start(*args)
    rc, out = _finish(harness, p)
    assert rc == 93, out
    assert "k_elbow.in_fit_space" in out
    assert not (harness.ee / "runners.txt").exists()


@needs_bash
def test_a_config_done_through_the_elbow_is_not_skipped_by_a_full_batch_of_the_same_label(harness: Harness):
    a = harness.config("cfg_a_r14", elbow_in_fit_space=True)
    harness.commit()
    first = harness.start("--through", "k_elbow", a)
    rc, out = _finish(harness, first)
    assert rc == 0, out
    second = harness.start(a)
    rc, out = _finish(harness, second)
    assert rc == 0, out
    assert [s for _, s in _passes_run(harness)][-2:] == ["clustering", "export"]
    n_runners = len(harness.runners())
    third = harness.start(a)  # done in a full batch: skipped, as since round 13 (B4), and exit 0
    rc, out = _finish(harness, third)
    assert rc == 0, out
    assert "skipped" in harness.log()
    assert len(harness.runners()) == n_runners

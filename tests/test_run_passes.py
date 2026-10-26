"""The batch runner's passes (round 9, issue #44 item 2), offline.

Every feature stage a config needs is cached by a first pass of its own, before
the first pass that reads any of them; each later pass refuses to start while any
of them, or anything else upstream of it, is missing. And the pass script starts
only when the wrapper starts it (round 12, roadmap 3.6, issue #44 item 10).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "odisha_script"))

import odisha_phase2_2_run_pipeline as runner  # noqa: E402
import run_passes_safely  # noqa: E402

from fmu.config import load_config  # noqa: E402
from fmu.pipeline import default_stage_names, feature_stage_names  # noqa: E402
from fmu.stages.base import _stage_registry  # noqa: E402

CONFIGS = [
    REPO / "configs" / "odisha_v120_3ha_squares_kendujhar_keptland_s1desc.yaml",
    REPO / "configs" / "sanjay_van_baseline_keptland.yaml",
    REPO / "configs" / "sanjay_van_alphaearth_keptland.yaml",
]
_REGISTERED = {n: c for n, c in _stage_registry.items() if c.__module__.startswith("fmu.stages.")}


@pytest.fixture(autouse=True)
def _restore_stage_registry():
    _stage_registry.clear()
    _stage_registry.update(_REGISTERED)
    yield


@pytest.mark.parametrize("path", CONFIGS, ids=lambda p: p.stem)
def test_the_features_pass_holds_every_feature_stage_a_run_needs(path: Path):
    cfg = load_config(path)
    full = default_stage_names(cfg, through="export")
    features = runner.stage_names(cfg, "features")
    assert features == feature_stage_names(cfg)
    assert features[:2] == ["masking", "data_load"]
    assert set(features) == {n for n in full if n.startswith("features_")} | {"masking", "data_load"}
    assert "segmentation" not in features


@pytest.mark.parametrize("path", CONFIGS, ids=lambda p: p.stem)
def test_every_pass_after_the_first_needs_every_feature_asset(path: Path):
    cfg = load_config(path)
    features = feature_stage_names(cfg)
    assert runner.prerequisites(cfg, "features") == []
    for later in ("segmentation", "clustering", "export"):
        assert set(features) <= set(runner.prerequisites(cfg, later)), later
    assert "segmentation" in runner.prerequisites(cfg, "clustering")
    assert {"segmentation", "clustering"} <= set(runner.prerequisites(cfg, "export"))


def test_the_alphaearth_features_pass_holds_the_merge_criteria():
    """Round 2 found the AlphaEarth runs computing the merge's optical and structure
    features live in the clustering pass; they are in the features pass now."""
    cfg = load_config(CONFIGS[2])
    features = feature_stage_names(cfg)
    assert {"features_embedding", "features_optical", "features_structure"} <= set(features)


def test_the_pass_scripts_run_the_features_pass_first():
    text = (REPO / "odisha_script" / "run_config_passes.sh").read_text()
    # Round 14: the stages come from the wrapper (STAGES); the default is the four of before.
    assert "STAGES=${STAGES:-features segmentation clustering export}" in text
    assert "for stage in $STAGES; do" in text
    assert runner.PASSES == ("features", "segmentation", "k_elbow", "clustering", "export")
    line = "--- PASS1 odisha_x_r9 features exit=0 ---"
    m = run_passes_safely.STAGE_EXIT.match(line)
    assert m and m.group(2) == "features"
    assert re.match(run_passes_safely.STAGE_EXIT, "--- PASS1 c export exit=3 ---")


# ---------- the pass script starts only from the wrapper (round 12) ----------

PASS_SCRIPT = REPO / "odisha_script" / "run_config_passes.sh"
BASH = shutil.which("bash")
needs_bash = pytest.mark.skipif(BASH is None, reason="needs bash")
# Stands in for the interpreter: it records the runner's arguments and runs nothing.
STAND_IN = '#!/bin/sh\necho "$*" >> "$STAND_IN_RECORD"\n'


def _start_the_pass_script(tmp_path: Path, env: dict[str, str]) -> subprocess.CompletedProcess:
    """The pass script on one made-up config, from an empty folder (no .env, no runner) and
    with a stand-in for the interpreter, so that nothing can reach Earth Engine."""
    python = tmp_path / "python"
    python.write_text(STAND_IN)
    python.chmod(0o755)
    env = {**env, "PYTHON": str(python), "STAND_IN_RECORD": str(tmp_path / "calls.txt")}
    return subprocess.run(
        [BASH, str(PASS_SCRIPT), str(tmp_path / "batch.log"), "configs/x_r9.yaml"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120,
    )


@needs_bash
def test_the_pass_script_refuses_to_start_unless_the_wrapper_started_it(tmp_path: Path):
    """Without RUN_PASSES_SAFELY=1 it exits 96 before it reads an argument or writes
    anything. Before round 12 it ran its passes."""
    clean = {k: v for k, v in os.environ.items() if k != run_passes_safely.STARTED_BY_THE_WRAPPER}
    for value in (None, "", "0", "yes"):
        env = dict(clean, MAX_PASSES="1")
        if value is not None:
            env[run_passes_safely.STARTED_BY_THE_WRAPPER] = value
        got = _start_the_pass_script(tmp_path, env)
        assert got.returncode == 96, (value, got.stdout + got.stderr)
        assert "REFUSING" in got.stderr and "run_passes_safely.py" in got.stderr
        assert not (tmp_path / "batch.log").exists() and not (tmp_path / "calls.txt").exists()


@needs_bash
def test_the_pass_script_runs_in_the_environment_the_wrapper_gives_it(tmp_path: Path):
    env = run_passes_safely.pass_env("<the interpreter>", tmp_path)
    assert env[run_passes_safely.STARTED_BY_THE_WRAPPER] == "1" and env["MAX_PASSES"] == "1"
    got = _start_the_pass_script(tmp_path, env)
    assert got.returncode == 0, got.stdout + got.stderr
    calls = (tmp_path / "calls.txt").read_text().splitlines()
    assert [c.split("--through ")[1] for c in calls] == [
        "features --wait", "segmentation --wait", "clustering --wait", "export"]
    exits = [m.groups() for line in (tmp_path / "batch.log").read_text().splitlines()
             if (m := run_passes_safely.STAGE_EXIT.match(line.strip()))]
    assert exits == [("x_r9", s, "0") for s in ("features", "segmentation", "clustering", "export")]


def test_the_pass_script_checks_the_variable_the_wrapper_sets():
    text = PASS_SCRIPT.read_text()
    assert f'"${{{run_passes_safely.STARTED_BY_THE_WRAPPER}:-}}" != "1"' in text
    assert text.index("exit 96") < text.index("LOG=$1")

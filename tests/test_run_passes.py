"""The batch runner's passes (round 9, issue #44 item 2), offline.

Every feature stage a config needs is cached by a first pass of its own, before
the first pass that reads any of them; each later pass refuses to start while any
of them, or anything else upstream of it, is missing.
"""

from __future__ import annotations

import re
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
    assert "for stage in features segmentation clustering export; do" in text
    assert runner.PASSES == ("features", "segmentation", "clustering", "export")
    line = "--- PASS1 odisha_x_r9 features exit=0 ---"
    m = run_passes_safely.STAGE_EXIT.match(line)
    assert m and m.group(2) == "features"
    assert re.match(run_passes_safely.STAGE_EXIT, "--- PASS1 c export exit=3 ---")

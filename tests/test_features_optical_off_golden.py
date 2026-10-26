"""With features_optical.mean_over_window off, the optical stage does what it did before round 14.

tests/data/features_optical_off_calls.json holds, for three shipped configs (the NDVI
baseline, the NIRv dual-harmonic variant, and a kept-land box config), what
`FeaturesOpticalStage.run()` does on the recorder of tests/_ee_recorder.py (every Earth Engine
call, in order, with its arguments), together with the calls of the two functions it maps over
the Sentinel-2 collection (`_add_index` and `_add_regression_bands`, recorded by name only
inside the stage's own calls) run on one stand-in image, and its stage metadata. The file was
written from the stage as it was before round 14 (commit 284b73d, the round's first commit):

    git show 284b73d:src/fmu/stages/features_optical.py > /tmp/features_optical_284b73d.py
    python tests/test_features_optical_off_golden.py --write /tmp/features_optical_284b73d.py

and the stage of today must reproduce it exactly with the setting off; its stage metadata gains
the setting, false, and nothing else.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from _ee_recorder import Rec, call_log
from fmu.config import load_config
from fmu.stages.base import PipelineContext

REPO = Path(__file__).resolve().parent.parent
GOLDEN = REPO / "tests" / "data" / "features_optical_off_calls.json"
CONFIGS = (
    "configs/sanjay_van_baseline.yaml",
    "configs/sanjay_van_nirv_dual.yaml",
    "configs/odisha_v120_3ha_squares_angul_keptland_s1desc_r9.yaml",
)


def _bands(cfg: Any) -> list[str]:
    p = cfg.features_optical.index
    names = [f"{p}_mean", f"{p}_amplitude_annual", f"{p}_phase_annual"]
    if cfg.features_optical.harmonic_mode == "dual":
        names += [f"{p}_amplitude_semi", f"{p}_phase_semi"]
    if cfg.features_optical.include_trend:
        names.append(f"{p}_trend")
    return [*names, f"{p}_residual_variance", f"{p}_obs_count"]


def record(module: ModuleType, config_path: str) -> dict[str, Any]:
    cfg = load_config(REPO / config_path)
    assert not getattr(cfg.features_optical, "mean_over_window", False)
    log: list = []
    saved = {n: getattr(module, n) for n in ("ee", "safe_get_info")}
    try:
        module.ee = Rec("ee", log)  # type: ignore[attr-defined]
        module.safe_get_info = lambda obj, context="": _bands(cfg)  # type: ignore[attr-defined]
        ctx = PipelineContext()
        ctx.set("s2_collection", Rec("s2_collection", log))
        ctx.set("roi", Rec("roi", log))
        result = module.FeaturesOpticalStage().run(ctx, cfg)
        params = cfg.features_optical
        module._add_index(Rec("image", log), params.index)
        module._add_regression_bands(
            Rec("image", log), params.harmonic_mode, params.include_trend, params.time_reference
        )
    finally:
        for n, v in saved.items():
            setattr(module, n, v)
    return {"calls": call_log(log), "metadata": json.loads(json.dumps(result.metadata))}


def _golden() -> dict[str, Any]:
    return json.loads(GOLDEN.read_text())


def test_the_file_holds_the_three_configs():
    assert sorted(_golden()) == sorted(CONFIGS)


@pytest.mark.parametrize("config_path", CONFIGS)
def test_off_the_stage_makes_the_calls_it_made_before(config_path: str):
    import fmu.stages.features_optical as optical

    today = record(optical, config_path)
    golden = _golden()[config_path]
    assert today["calls"] == golden["calls"]
    meta = dict(today["metadata"])
    assert meta.pop("mean_over_window") is False
    assert meta == golden["metadata"]


def _load_other(path: Path) -> ModuleType:
    """Load another copy of the stage module without registering its stage twice."""
    import fmu.stages.base as base

    real = base.register_stage
    base.register_stage = lambda name: (lambda cls: cls)  # type: ignore[assignment]
    try:
        spec = importlib.util.spec_from_file_location("features_optical_other", path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        base.register_stage = real  # type: ignore[assignment]
    return module


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "--write":
        raise SystemExit(__doc__)
    sys.path.insert(0, str(REPO / "src"))
    sys.path.insert(0, str(REPO / "tests"))
    other = _load_other(Path(sys.argv[2]))
    recorded = {c: record(other, c) for c in CONFIGS}
    GOLDEN.write_text(json.dumps(recorded, indent=0, sort_keys=True) + "\n")
    print(f"wrote {GOLDEN}")

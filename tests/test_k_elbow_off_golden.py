"""With k_elbow.in_fit_space off, the k elbow step does what it did before round 14.

tests/data/k_elbow_off_calls.json holds, for three shipped configs (a box config whose fit
leaves the stands below the minimum out, the hand-crafted Sanjay Van baseline, and an
AlphaEarth config), what `KElbowStage.run()` does on stand-ins: every Earth Engine call as
recorded by tests/_ee_recorder.py (name, arguments and keyword arguments, in order, its
training_rows and the clustering helpers it calls included), every request it sends with the
context it names, the table it builds (the properties of each feature) and its stage metadata.
The file was written from the step as it was before round 14 (commit 284b73d, the round's
first commit), before the setting existed:

    git show 284b73d:src/fmu/stages/k_elbow.py > /tmp/k_elbow_284b73d.py
    python tests/test_k_elbow_off_golden.py --write /tmp/k_elbow_284b73d.py

and the step of today must reproduce it exactly. A deliberate change to the default path
rewrites the file the same way, from the new code, in the commit that makes it.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest

import fmu.stages.clustering as clustering
from _ee_recorder import Call, Rec, call_log
from fmu.config import load_config
from fmu.stages.base import PipelineContext

REPO = Path(__file__).resolve().parent.parent
GOLDEN = REPO / "tests" / "data" / "k_elbow_off_calls.json"
CONFIGS = (
    "configs/odisha_v120_3ha_squares_kendujhar_keptland_s1desc.yaml",
    "configs/sanjay_van_baseline.yaml",
    "configs/odisha_alphaearth_angul_repro.yaml",
)
BANDS = ["b0", "b1", "b2", "b3"]
N_ROWS = 40
BELOW_MIN = {5: 0.4, 11: 0.2}


def _rows() -> list[dict[str, Any]]:
    rng = np.random.default_rng(7)
    centres = np.array([[0, 0, 0, 0], [5, 0, 1, 2], [0, 6, -1, 1]], dtype=float)
    out = []
    for i in range(N_ROWS):
        v = centres[i % 3] + rng.normal(0, 0.5, 4)
        out.append({"type": "Feature", "geometry": None,
                    "properties": {"fmu_label": i, **{b: float(x) for b, x in zip(BANDS, v, strict=True)}}})
    return out


def _answers(log: list) -> Any:
    rows = _rows()
    left_out = [r for r in rows if r["properties"]["fmu_label"] in BELOW_MIN]

    def answer(context: str) -> Any:
        if context == "k elbow bands":
            return list(BANDS)
        if context == "k elbow row count":
            return N_ROWS
        if context == "k elbow rows: count":
            return N_ROWS - len(left_out)
        if context == "k elbow rows":
            return {"features": [r for r in rows if r not in left_out]}
        if context == "k-means training row count without the stands below the minimum":
            return N_ROWS - len(left_out)
        if context == "stands below the minimum with a training row":
            return [r["properties"]["fmu_label"] for r in left_out]
        raise AssertionError(f"unexpected request: {context}")

    def get_info(obj: Any, context: str = "") -> Any:
        log.append(Call("getInfo", None, None, (obj,), {"context": context}, None))
        return answer(context)

    return get_info


def _provenance() -> tuple[dict, dict]:
    prov = {sid: {"below_min": int(sid in BELOW_MIN)} for sid in range(N_ROWS)}
    attrs = {sid: {"area_ha": BELOW_MIN.get(sid, 2.0)} for sid in range(N_ROWS)}
    return prov, attrs


def record(module: ModuleType, config_path: str) -> dict[str, Any]:
    cfg = load_config(REPO / config_path)
    assert not getattr(cfg.k_elbow, "in_fit_space", False)
    log: list = []
    saved = {(m, n): getattr(m, n) for m in (module, clustering) for n in ("ee", "safe_get_info")}
    try:
        for m in (module, clustering):
            m.ee = Rec("ee", log)  # type: ignore[attr-defined]
            m.safe_get_info = _answers(log)  # type: ignore[attr-defined]
        ctx = PipelineContext()
        for key in ("roi", "habitat_mask", "feature_stack", cfg.unit_label_key()):
            ctx.set(key, Rec(key, log))
        prov, attrs = _provenance()
        ctx.set("stand_provenance", prov)
        ctx.set("stand_attributes", attrs)
        result = module.KElbowStage().run(ctx, cfg)
    finally:
        for (m, n), v in saved.items():
            setattr(m, n, v)
    features = [c for c in log if c.name == "ee.Feature"]
    return {
        "calls": call_log(log),
        "table": [c.args[1] for c in features],
        "metadata": json.loads(json.dumps(result.metadata)),
    }


def _golden() -> dict[str, Any]:
    return json.loads(GOLDEN.read_text())


def test_the_file_holds_the_three_configs():
    assert sorted(_golden()) == sorted(CONFIGS)


@pytest.mark.parametrize("config_path", CONFIGS)
def test_the_default_path_makes_the_calls_and_the_table_it_made_before(config_path: str):
    from fmu.stages import k_elbow

    today = record(k_elbow, config_path)
    golden = _golden()[config_path]
    assert today["calls"] == golden["calls"]
    assert today["table"] == golden["table"]
    assert today["metadata"] == golden["metadata"]


def _load_other(path: Path) -> ModuleType:
    """Load another copy of the k_elbow module without registering its stage twice."""
    import fmu.stages.base as base

    real = base.register_stage
    base.register_stage = lambda name: (lambda cls: cls)  # type: ignore[assignment]
    try:
        spec = importlib.util.spec_from_file_location("k_elbow_other", path)
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

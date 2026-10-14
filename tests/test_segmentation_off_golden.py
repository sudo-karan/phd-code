"""With segmentation.mask_before_snic off, segmentation makes the calls it always made.

Every run saved so far took the default path, so the setting must leave that path exactly
as it was. tests/data/segmentation_off_calls.json holds, for three shipped configs (the
hand-crafted baseline, a 3 ha box config, and an AlphaEarth config that takes every band
with "*"), the Earth Engine calls of `SegmentationStage.run()` as recorded by the stand-in
of tests/_ee_recorder.py: name, arguments and keyword arguments, in order. The file was
written from the stage as it was before the setting existed (commit 983dbe7):

    git show 983dbe7:src/fmu/stages/segmentation.py > /tmp/segmentation_983dbe7.py
    python tests/test_segmentation_off_golden.py --write /tmp/segmentation_983dbe7.py

and the stage of today must reproduce it call for call. A deliberate change to the default
path rewrites the file the same way, from the new code, in the commit that makes it.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
GOLDEN = HERE / "data" / "segmentation_off_calls.json"
CONFIGS = (
    "configs/sanjay_van_baseline.yaml",
    "configs/odisha_v120_3ha_squares_koraput.yaml",
    "configs/odisha_alphaearth_angul_repro.yaml",
)
EMBEDDING_BANDS = [f"A{i:02d}" for i in range(64)]

sys.path.insert(0, str(HERE))
from _ee_recorder import Rec, call_log  # noqa: E402


def _get_info(bands: list[str]):
    def get_info(obj: Any, context: str = "") -> Any:
        if context.startswith("band names of"):
            return list(EMBEDDING_BANDS)
        if obj.name.endswith(".bandNames()"):
            return list(bands)
        if obj.name.endswith(".nominalScale()"):
            return 10.0
        if obj.name.endswith(".crs()"):
            return "EPSG:32645"
        if context == "RMS adjacent feature distance":
            return {"d2": 4.0}
        raise AssertionError(f"unexpected getInfo on the default path: {context}")

    return get_info


def record(module: ModuleType, config_path: str) -> list[list[Any]]:
    """The calls `module.SegmentationStage().run()` makes for a config, setting off."""
    from fmu.config import load_config
    from fmu.stages.base import PipelineContext

    config = load_config(REPO / config_path)
    assert not config.segmentation.mask_before_snic
    names = []
    for spec in config.segmentation.input_bands:
        names.extend(EMBEDDING_BANDS if spec.band == "*" else [spec.band])
    log: list = []
    saved = {k: getattr(module, k) for k in ("ee", "safe_get_info", "_analysis_grid")}
    try:
        module.ee = Rec("ee", log)  # type: ignore[attr-defined]
        module.safe_get_info = _get_info(names)  # type: ignore[attr-defined]
        module._analysis_grid = lambda roi, scale: Rec("grid", log)  # type: ignore[attr-defined]
        ctx = PipelineContext()
        ctx.set("roi", Rec("roi", log))
        for source in sorted(config.segmentation.input_sources()):
            ctx.set(source, Rec(source, log))
        module.SegmentationStage().run(ctx, config)
    finally:
        for k, v in saved.items():
            setattr(module, k, v)
    return call_log(log)


@pytest.mark.parametrize("config_path", CONFIGS)
def test_the_default_path_makes_the_calls_it_made_before(config_path: str):
    import fmu.stages.segmentation as segmentation

    golden = json.loads(GOLDEN.read_text())
    assert record(segmentation, config_path) == golden[config_path]


def _load_other(path: Path) -> ModuleType:
    """Load another copy of the segmentation module without registering its stage twice."""
    import fmu.stages.base as base

    real = base.register_stage
    base.register_stage = lambda name: (lambda cls: cls)  # type: ignore[assignment]
    try:
        spec = importlib.util.spec_from_file_location("segmentation_other", path)
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
    other = _load_other(Path(sys.argv[2]))
    GOLDEN.write_text(
        json.dumps({c: record(other, c) for c in CONFIGS}, indent=0, sort_keys=True) + "\n"
    )
    print(f"wrote {GOLDEN}")

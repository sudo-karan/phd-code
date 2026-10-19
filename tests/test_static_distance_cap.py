"""Offline checks of `features_static.cap_distance_to_water`: distance to water capped at 10 km.

docs/decisions.yaml, spec-static-cap-distance-to-water. Where the distance transform finds no
water within features_static.max_water_distance_pixels it returns its fill value, sqrt(2^31 - 1)
pixels (463,409.5 m at 10 m), not a distance. With the setting on, the band is capped at that
reach, 10 km. Off, nothing is capped and the stage makes the calls
tests/data/features_static_off_calls.json holds for three shipped configs. They were recorded from
the stage at commit 6ad5055 (main at 3a51763), before the setting existed, and recorded again in
round 13: when the fix of review A1 gave the transform its own water input (all three cases
changed, in the water input's calls and the names made from them only), and when the fix of
review A5 took slope and aspect from ee.Terrain.slope and ee.Terrain.aspect on the DEM as float
(all three changed, in the terrain calls and the names made from them only).
Earth Engine is replaced by the recorder of tests/_ee_recorder.py.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

import fmu.stages.features_static as static_module
from _ee_recorder import Rec, call_log, calls, made_by
from fmu.config import Config, load_config
from fmu.stages.base import PipelineContext
from fmu.utils.caching import config_fingerprint

REPO = Path(__file__).resolve().parent.parent
GOLDEN = REPO / "tests" / "data" / "features_static_off_calls.json"
BANDS = ["elevation", "slope", "aspect", "distance_to_water", "annual_rainfall"]


def _run(monkeypatch, config: Config):
    log: list = []
    monkeypatch.setattr(static_module, "ee", Rec("ee", log))
    monkeypatch.setattr(static_module, "safe_get_info", lambda obj, context="": list(BANDS))
    ctx = PipelineContext()
    ctx.set("roi", Rec("roi", log))
    ctx.set("water_mask", Rec("water_mask", log))
    return static_module.FeaturesStaticStage().run(ctx, config), log


def _config(path: str, **static) -> Config:
    raw = yaml.safe_load((REPO / path).read_text())
    raw["features_static"] = {**raw.get("features_static", {}), **static}
    return Config.model_validate(raw)


@pytest.mark.parametrize("path", sorted(json.loads(GOLDEN.read_text())))
def test_off_the_stage_makes_the_calls_it_made_before(monkeypatch, path):
    golden = json.loads(GOLDEN.read_text())[path]
    result, log = _run(monkeypatch, load_config(REPO / path))
    assert call_log(log) == golden["calls"]
    assert not calls(log, ".min"), "nothing is capped with the setting off"
    # The stage metadata gains the setting, false; the rest is as it was.
    meta = dict(result.metadata)
    assert meta.pop("cap_distance_to_water") is False
    assert meta == golden["metadata"]


def test_on_the_distance_is_capped_at_the_neighbourhoods_reach(monkeypatch):
    config = _config("configs/sanjay_van_baseline.yaml", cap_distance_to_water=True)
    result, log = _run(monkeypatch, config)
    (transform,) = calls(log, ".fastDistanceTransform")
    assert transform.args == (1000, "pixels", "squared_euclidean")
    (cap,) = calls(log, ".min")
    assert cap.args == (1000 * 10,)
    multiply = made_by(log, cap.owner)
    assert (multiply.attr, multiply.args) == ("multiply", (10,))
    (rename,) = [c for c in log if c.attr == "rename" and c.args == ("distance_to_water",)]
    assert rename.owner is cap.out, "the capped image is the band"
    assert result.metadata["cap_distance_to_water"] is True


def test_the_cap_follows_the_neighbourhood_and_the_scale(monkeypatch):
    config = _config("configs/sanjay_van_baseline.yaml", cap_distance_to_water=True,
                     max_water_distance_pixels=500)
    _, log = _run(monkeypatch, config)
    (cap,) = calls(log, ".min")
    assert cap.args == (500 * config.export.analysis_scale_m,)


def test_off_by_default_and_left_out_of_the_fingerprint_while_off():
    base = load_config(REPO / "configs" / "sanjay_van_baseline.yaml")
    assert base.features_static.cap_distance_to_water is False
    assert config_fingerprint(base) == "7f642cf2ca"  # the name of its saved assets
    written_out = _config("configs/sanjay_van_baseline.yaml", cap_distance_to_water=False)
    assert config_fingerprint(written_out) == config_fingerprint(base)
    on = _config("configs/sanjay_van_baseline.yaml", cap_distance_to_water=True)
    assert config_fingerprint(on) != config_fingerprint(base)

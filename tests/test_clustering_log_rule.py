"""clustering.log_rule right_skew: the log rule of round 14 (Task 2.2; A3, B12, round 13's Q8).

docs/decisions.yaml, spec-clustering-log-rule-right-skewed-bands. With the rule on (and
clustering.fit_outside_earth_engine, which it needs), only right-skewed bands are logged, as
log1p((x - min) / IQR); a constant band is dropped first; the sin and cos of an angle, aspect's
included, are never skew-tested or logged, and each pair is scaled with one shared spread; the
skew of each band is recorded before and after. Earth Engine is replaced by the recorder of
tests/_ee_recorder.py and the answers of tests/_clustering_stand_ins.py; the rule itself is
tested in tests/test_stand_table.py.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

import fmu.stages.clustering as clustering
from _clustering_stand_ins import HANDCRAFTED_DECOMPOSED, run_stage, table_rows
from _ee_recorder import calls, made_by, owner_call
from fmu.config import Config
from fmu.utils import stand_table as st
from fmu.utils.caching import config_fingerprint, step_keys

REPO = Path(__file__).resolve().parent.parent
BOX_YAML = REPO / "configs" / "odisha_v120_3ha_squares_koraput.yaml"
ANGLES = ("ndvi_phase_annual_sin", "ndvi_phase_annual_cos", "aspect_sin", "aspect_cos")


def _config(**clustering_settings: Any) -> Config:
    raw = yaml.safe_load(BOX_YAML.read_text())
    raw["clustering"] = {
        **raw.get("clustering", {}),
        "fit_excludes_stands_below_min_area": False,
        **clustering_settings,
    }
    return Config.model_validate(raw)


def _metadata(log: list) -> dict[str, Any]:
    (stamp,) = [c for c in log if c.attr == "set" and c.args[:1] == ("clustering_metadata",)]
    return json.loads(stamp.args[1])


def _expected() -> st.Preprocessed:
    bands = list(HANDCRAFTED_DECOMPOSED)
    table = st.stand_table_from_columns(table_rows(bands), bands=bands)
    return st.preprocess(
        table, rule="right_skew", threshold=1.0, decomposed=["ndvi_phase_annual", "aspect"]
    )


def test_the_default_is_the_rule_of_record_and_the_new_rule_needs_the_fit_off_earth_engine():
    assert _config().clustering.log_rule == "abs_skew"
    with pytest.raises(ValidationError, match="fit_outside_earth_engine"):
        _config(log_rule="right_skew")


def test_with_the_rule_on_only_right_skewed_bands_are_logged_and_no_angle_is_tested():
    config = _config(fit_outside_earth_engine=True, log_rule="right_skew")
    _, log, _ = run_stage(clustering, config)
    meta = _metadata(log)
    pre = _expected()
    assert meta["log_rule"] == "right_skew"
    assert meta["log_transformed_bands"] == pre.record["log_transformed_bands"]
    assert "vh_iqr" in meta["log_transformed_bands"]  # right-skewed in the stand-ins
    assert "slope" not in meta["log_transformed_bands"]  # left-skewed: not transformed
    for comp in ANGLES:  # round 13's question 8: aspect's pair too
        assert comp not in meta["skew_before"] and comp not in meta["log_transformed_bands"]
    assert set(meta["skew_before"]) == set(meta["skew_after"])
    assert meta["skew_before"]["vh_iqr"] == pytest.approx(pre.record["skew_before"]["vh_iqr"])
    assert "distance_to_water" in meta["dropped_constant_bands"]
    assert "distance_to_water" not in meta["skew_before"]


def test_each_angle_pair_is_scaled_with_one_shared_spread():
    config = _config(fit_outside_earth_engine=True, log_rule="right_skew")
    _, log, _ = run_stage(clustering, config)
    meta = _metadata(log)
    pairs = {tuple(p["bands"]): p["shared_spread"] for p in meta["angle_pairs"]}
    assert set(pairs) == {("ndvi_phase_annual_sin", "ndvi_phase_annual_cos"), ("aspect_sin", "aspect_cos")}
    for (a, b), spread in pairs.items():
        assert meta["scaling"][a]["spread"] == meta["scaling"][b]["spread"] == spread


def test_the_feature_stack_applies_log1p_over_the_iqr_then_the_scaling():
    config = _config(fit_outside_earth_engine=True, log_rule="right_skew")
    _, log, _ = run_stage(clustering, config)
    pre = _expected()
    band = "vh_iqr"
    params = pre.record["log1p_params"][band]
    renames = [c for c in calls(log, ".rename") if c.args == (band,)]
    (scaled,) = [c for c in renames if made_by(log, c.owner).attr == "divide"]
    divide = made_by(log, scaled.owner)
    assert divide.args == (pre.record["scaling"][band]["spread"],)
    subtract = owner_call(log, divide)
    assert subtract.args == (pre.record["scaling"][band]["center"],)
    took_log = owner_call(log, subtract)
    assert took_log.attr == "log"
    plus_one = owner_call(log, took_log)
    assert (plus_one.attr, plus_one.args) == ("add", (1,))
    over_iqr = owner_call(log, plus_one)
    assert (over_iqr.attr, over_iqr.args) == ("divide", (params["iqr"],))
    less_min = owner_call(log, over_iqr)
    assert (less_min.attr, less_min.args) == ("subtract", (params["min"],))


def test_the_rule_moves_the_clustering_and_k_elbow_keys_and_its_default_moves_none(monkeypatch):
    monkeypatch.chdir(REPO)
    base = _config(fit_outside_earth_engine=True)
    written = _config(fit_outside_earth_engine=True, log_rule="abs_skew")
    on = _config(fit_outside_earth_engine=True, log_rule="right_skew")
    assert step_keys(written) == step_keys(base)
    assert config_fingerprint(written) == config_fingerprint(base)
    keys, keys_on = step_keys(base), step_keys(on)
    assert {s for s in keys if keys[s] != keys_on[s]} == {"clustering", "k_elbow"}
    assert config_fingerprint(on) != config_fingerprint(base)

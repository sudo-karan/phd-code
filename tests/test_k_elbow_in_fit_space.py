"""k_elbow.in_fit_space: the k elbow on the fit's own rows, in its own space (round 14, Task 2.4).

docs/decisions.yaml, spec-k-elbow-in-the-fits-space. With the setting on, the k elbow step
reads the table of units as the clustering stage does with clustering.fit_outside_earth_engine
on (the same request), preprocesses it by the same rule, and runs k-means on the rows of the fit
for every k from k_min to k_max: 25 k-means++ starts from the seed, the best kept, the starts'
agreement measured, the knee taken on the within-cluster sums of squares. It needs neither the
clustering stage nor its outputs, so a pass can stop after it. Earth Engine is replaced by the
recorder of tests/_ee_recorder.py and the answers of tests/_clustering_stand_ins.py.
tests/test_k_elbow_off_golden.py holds the path with the setting off.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

import fmu.stages.clustering as clustering
from _clustering_stand_ins import (
    HANDCRAFTED_DECOMPOSED,
    TABLE_LABELS,
    TABLE_OF_UNITS,
    answers,
    inputs,
    run_stage,
    table_rows,
)
from _ee_recorder import Rec, calls
from fmu.config import Config
from fmu.pipeline import default_stage_names
from fmu.stages import k_elbow
from fmu.stages.base import PipelineContext
from fmu.utils import stand_table as st
from fmu.utils.caching import config_fingerprint, step_keys

REPO = Path(__file__).resolve().parent.parent
BOX_YAML = REPO / "configs" / "odisha_v120_3ha_squares_koraput.yaml"


def _config(*, in_fit_space: bool = True, **clustering_settings: Any) -> Config:
    raw = yaml.safe_load(BOX_YAML.read_text())
    raw["clustering"] = {
        **raw.get("clustering", {}),
        "fit_outside_earth_engine": True,
        "log_rule": "right_skew",
        "fit_excludes_stands_below_min_area": False,
        **clustering_settings,
    }
    raw["k_elbow"] = {"in_fit_space": in_fit_space}
    return Config.model_validate(raw)


def _run(config: Config):
    log: list = []
    saved = {(m, n): getattr(m, n) for m in (k_elbow, clustering) for n in ("ee", "safe_get_info")}
    try:
        for m in (k_elbow, clustering):
            m.ee = Rec("ee", log)  # type: ignore[attr-defined]
            m.safe_get_info = answers(config, log)  # type: ignore[attr-defined]
        ctx = PipelineContext()
        for key in sorted(inputs(config)):
            ctx.set(key, Rec(key, log))
        result = k_elbow.KElbowStage().run(ctx, config)
    finally:
        for (m, n), v in saved.items():
            setattr(m, n, v)
    return result, log


def _expected(config: Config):
    bands = list(HANDCRAFTED_DECOMPOSED)
    table = st.stand_table_from_columns(table_rows(bands), bands=bands)
    pre = st.preprocess(table, rule="right_skew", threshold=1.0, decomposed=["ndvi_phase_annual", "aspect"])
    return table, pre


def test_off_by_default_and_needs_the_fit_off_earth_engine_with_the_fits_starts():
    raw = yaml.safe_load(BOX_YAML.read_text())
    assert Config.model_validate(raw).k_elbow.in_fit_space is False
    with pytest.raises(ValidationError, match="fit_outside_earth_engine"):
        _config(fit_outside_earth_engine=False, log_rule="abs_skew")
    raw2 = yaml.safe_load(BOX_YAML.read_text())
    raw2["clustering"] = {**raw2.get("clustering", {}), "fit_outside_earth_engine": True}
    raw2["k_elbow"] = {"in_fit_space": True, "n_init": 10}
    with pytest.raises(ValidationError, match="25"):
        Config.model_validate(raw2)
    raw2["k_elbow"] = {"in_fit_space": True, "seed": 7}
    with pytest.raises(ValidationError, match="seed"):
        Config.model_validate(raw2)


def test_a_run_through_the_elbow_has_no_clustering_stage_with_the_setting_on():
    on, off = _config(), _config(in_fit_space=False)
    assert default_stage_names(on, through="k_elbow") == [
        *[n for n in default_stage_names(on, through="clustering") if n != "clustering"], "k_elbow",
    ]
    assert default_stage_names(off, through="k_elbow") == [
        *default_stage_names(off, through="clustering"), "k_elbow",
    ]


def test_the_step_asks_for_the_fits_inputs_not_the_clustering_stages_outputs():
    config = _config()
    ctx = PipelineContext()
    for key in inputs(config):
        ctx.set(key, key)
    k_elbow.KElbowStage().validate(ctx, config)  # no feature_stack: fine
    short = PipelineContext()
    for key in inputs(config) - {"optical_features"}:
        short.set(key, key)
    with pytest.raises(KeyError, match="optical_features"):
        k_elbow.KElbowStage().validate(short, config)


def test_the_elbow_is_the_sweep_of_the_fit_rows_with_25_starts_and_the_starts_agreement():
    config = _config()
    result, log = _run(config)
    reads = [c.kwargs["context"] for c in log if c.name == "getInfo"]
    assert reads.count(TABLE_OF_UNITS) == 1
    table, pre = _expected(config)
    rows = pre.values[table.in_fit]
    meta = result.metadata
    assert meta["in_fit_space"] is True and meta["ks"] == list(range(2, 13))
    for k, wcss, med, low in zip(meta["ks"], meta["inertia"], meta["ari_median"], meta["ari_min"], strict=True):
        starts = st.kmeans_starts(rows, k, n_starts=25, seed=42)
        best = starts[st.best_start(starts)]
        assert wcss == round(best.wcss, 6)
        agreement = st.starts_agreement(starts)
        assert med == round(agreement["ari_median"], 6) and low == round(agreement["ari_min"], 6)
    assert meta["elbow_k"] == k_elbow.knee(meta["ks"], meta["inertia"])
    features = [c.args[1] for c in calls(log, "ee.Feature")]
    assert [f["k"] for f in features] == meta["ks"]
    assert {"ari_median", "ari_min", "in_fit_space"} <= set(features[0])


def test_at_the_configs_k_the_elbow_is_the_clustering_stages_own_fit():
    """Same rows, same space, same starts: the elbow's sum of squares at k is the fit's."""
    config = _config()
    result, _ = _run(config)
    _, log, _ = run_stage(clustering, config)
    (stamp,) = [c for c in log if c.attr == "set" and c.args[:1] == ("clustering_metadata",)]
    fit_wcss = json.loads(stamp.args[1])["kmeans_wcss"]
    k = config.clustering.k
    assert result.metadata["inertia"][result.metadata["ks"].index(k)] == round(fit_wcss, 6)


def test_the_step_writes_the_elbow_the_table_the_rows_and_the_types_at_each_k():
    config = _config()
    result, _ = _run(config)
    table, pre = _expected(config)
    files = result.files
    assert set(files) == {
        "k_elbow.csv", "k_elbow_stand_table.csv", "k_elbow_fit_rows.csv",
        "k_elbow_types.csv", "k_elbow_preprocessing.json",
    }
    elbow = list(csv.DictReader(io.StringIO(files["k_elbow.csv"])))
    assert [int(r["k"]) for r in elbow] == list(range(2, 13))
    assert sum(int(r["is_knee"]) for r in elbow) == 1
    rows = list(csv.reader(io.StringIO(files["k_elbow_fit_rows.csv"])))
    assert rows[0] == ["stand_lbl", "in_fit", *pre.bands]
    assert [int(r[0]) for r in rows[1:]] == sorted(TABLE_LABELS)
    types = list(csv.reader(io.StringIO(files["k_elbow_types.csv"])))
    assert types[0] == ["stand_lbl", "in_fit", *[f"type_k{k}" for k in range(2, 13)]]
    record = json.loads(files["k_elbow_preprocessing.json"])
    assert record["log_rule"] == "right_skew" and record["active_bands"] == pre.bands


def test_on_only_the_k_elbow_key_moves_and_off_none(monkeypatch):
    monkeypatch.chdir(REPO)
    base, on = _config(in_fit_space=False), _config()
    raw = yaml.safe_load(BOX_YAML.read_text())
    raw["clustering"] = {**raw.get("clustering", {}), "fit_outside_earth_engine": True,
                         "log_rule": "right_skew", "fit_excludes_stands_below_min_area": False}
    absent = Config.model_validate(raw)
    assert step_keys(absent) == step_keys(base)
    keys, keys_on = step_keys(base), step_keys(on)
    assert {s for s in keys if keys[s] != keys_on[s]} == {"k_elbow"}
    assert config_fingerprint(on) == config_fingerprint(base)  # k_elbow is outside the legacy fingerprint

"""clustering.fit_outside_earth_engine: k-means fitted off Earth Engine (round 14, Task 2.1).

docs/decisions.yaml, spec-clustering-kmeans-outside-earth-engine. With the setting on, the
clustering stage reads the table of its units back in one request, does the declared
preprocessing and the k-means fit in plain Python (fmu.utils.stand_table), and writes each
unit's type back to the image by its label. Earth Engine is replaced by the recorder of
tests/_ee_recorder.py and the answers of tests/_clustering_stand_ins.py; the fit is checked
against fmu.utils.stand_table on the same table. tests/test_clustering_off_golden.py holds the
path with the setting off.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml
from pydantic import ValidationError

import fmu.stages.clustering as clustering
from _clustering_stand_ins import (
    HANDCRAFTED_DECOMPOSED,
    TABLE_LABELS,
    TABLE_OF_UNITS,
    TRAINING_ROWS,
    run_stage,
    table_rows,
)
from _ee_recorder import calls, made_by, owner_call
from fmu.config import Config
from fmu.utils import stand_table as st
from fmu.utils.caching import config_fingerprint, step_keys

REPO = Path(__file__).resolve().parent.parent
BOX_YAML = REPO / "configs" / "odisha_v120_3ha_squares_koraput.yaml"
EMBEDDING_YAML = REPO / "configs" / "odisha_alphaearth_angul_repro.yaml"
BELOW_MIN = {4: 0.12, 9: 0.5, 12: 0.03, 15: 0.8, 99: 0.2}  # 99 has no row


def _config(path: Path = BOX_YAML, **clustering_settings: Any) -> Config:
    raw = yaml.safe_load(path.read_text())
    raw["clustering"] = {
        **raw.get("clustering", {}),
        "fit_outside_earth_engine": True,
        **clustering_settings,
    }
    return Config.model_validate(raw)


def _merge_outputs() -> dict[str, Any]:
    provenance = {sid: {"below_min": int(sid in BELOW_MIN)} for sid in range(100)}
    attributes = {sid: {"area_ha": BELOW_MIN.get(sid, 2.0)} for sid in range(100)}
    return {"stand_provenance": provenance, "stand_attributes": attributes}


def _metadata(log: list) -> dict[str, Any]:
    (stamp,) = [c for c in log if c.attr == "set" and c.args[:1] == ("clustering_metadata",)]
    return json.loads(stamp.args[1])


def _expected(config: Config, left_out: set[int] | None = None):
    """The table, preprocessing and fit the stage should reach, by fmu.utils.stand_table."""
    bands = list(HANDCRAFTED_DECOMPOSED)
    table = st.stand_table_from_columns(table_rows(bands), bands=bands, left_out=left_out)
    pre = st.preprocess(
        table,
        rule="abs_skew",
        threshold=config.clustering.skewness_threshold,
        decomposed=["ndvi_phase_annual", "aspect"],
    )
    fit = st.fit_types(pre, table.in_fit, k=config.clustering.k, n_starts=25, seed=42)
    return table, pre, fit


def _run(config: Config, **kwargs: Any):
    return run_stage(clustering, config, **kwargs)


def test_off_by_default_and_needs_robust_scaling():
    raw = yaml.safe_load(BOX_YAML.read_text())
    assert Config.model_validate(raw).clustering.fit_outside_earth_engine is False
    raw["normalization"] = {"method": "zscore"}
    raw["clustering"] = {**raw.get("clustering", {}), "fit_outside_earth_engine": True}
    with pytest.raises(ValidationError, match="robust"):
        Config.model_validate(raw)


def test_the_table_is_read_once_and_no_clusterer_is_trained_in_earth_engine():
    config = _config(fit_excludes_stands_below_min_area=False)
    _, log, _ = _run(config)
    reads = [c.kwargs["context"] for c in log if c.name == "getInfo"]
    assert reads.count(TABLE_OF_UNITS) == 1
    assert not [r for r in reads if r.startswith(("skew of", "min of", "values of"))]
    assert not calls(log, "wekaKMeans") and not calls(log, ".cluster")
    (to_list,) = calls(log, "ee.Reducer.toList")
    assert to_list.args == (1 + len(HANDCRAFTED_DECOMPOSED),)
    (columns,) = [c for c in calls(log, ".reduceColumns") if c.kwargs.get("reducer") is to_list.out]
    assert columns.kwargs["selectors"] == ["fmu_label", *HANDCRAFTED_DECOMPOSED]


def test_each_unit_s_type_is_written_back_by_its_label_and_masked_to_the_habitat():
    config = _config(fit_excludes_stands_below_min_area=False)
    _, log, ctx = _run(config)
    table, _, fit = _expected(config)
    (remap,) = [c for c in calls(log, ".remap") if c.owner is ctx.get("stand_clusters")]
    assert remap.args[0] == sorted(TABLE_LABELS) == table.labels.tolist()
    assert remap.args[1] == fit.types.tolist()
    (masked,) = [c for c in calls(log, ".updateMask") if c.owner is remap.out]
    assert masked.args == (ctx.get("habitat_mask"),)
    (renamed,) = [c for c in calls(log, ".rename") if c.owner is masked.out]
    assert renamed.args == ("cluster_id",)


def test_the_metadata_holds_the_fit_its_starts_and_the_coverage():
    config = _config(fit_excludes_stands_below_min_area=False)
    _, log, _ = _run(config)
    meta = _metadata(log)
    _, pre, fit = _expected(config)
    assert meta["fit_outside_earth_engine"] is True
    assert meta["kmeans_wcss"] == pytest.approx(fit.wcss, rel=1e-12)
    assert meta["kmeans_starts_ari_median"] == pytest.approx(fit.agreement["ari_median"])
    assert meta["kmeans_starts_ari_min"] == pytest.approx(fit.agreement["ari_min"])
    assert meta["kmeans"]["n_starts"] == 25 and meta["kmeans"]["seed"] == 42
    assert len(meta["kmeans"]["wcss_of_each_start"]) == 25
    assert meta["active_bands"] == pre.bands
    assert meta["log_transformed_bands"] == pre.record["log_transformed_bands"]
    assert meta["n_training_units"] == TRAINING_ROWS
    # 22 in habitat, 21 with a habitat pixel centre, 20 rows (the stand-ins).
    assert meta["n_units_no_pixel_centre_in_roi"] == 1
    assert meta["n_units_dropped_null_band"] == 1


def test_the_stands_left_out_are_not_rows_of_the_fit_and_take_the_nearest_centre():
    config = _config(fit_excludes_stands_below_min_area=True)
    _, log, ctx = _run(config, merge_outputs=_merge_outputs())
    left = {4, 9, 12, 15}
    table, pre, fit = _expected(config, left_out=set(BELOW_MIN))
    assert set(table.labels[~table.in_fit].tolist()) == left
    meta = _metadata(log)
    assert meta["n_training_units"] == TRAINING_ROWS - len(left)
    assert meta["n_stands_below_min_area"] == len(BELOW_MIN)
    assert meta["n_stands_left_out_of_fit"] == len(left)
    assert meta["area_ha_in_stands_left_out_of_fit"] == pytest.approx(0.12 + 0.5 + 0.03 + 0.8)
    (remap,) = [c for c in calls(log, ".remap") if c.owner is ctx.get("stand_clusters")]
    assert remap.args[1] == fit.types.tolist()
    nearest = st.nearest_centre(pre.values[~table.in_fit], fit.centres)
    assert (fit.types[~table.in_fit] == nearest).all()
    # No masked sample of the stands below the minimum: they are found by label, off Earth Engine.
    assert not [c for c in log if c.name == "getInfo"
                and c.kwargs["context"] == "stands below the minimum with a training row"]


def test_the_feature_stack_is_the_preprocessing_applied_server_side():
    config = _config(fit_excludes_stands_below_min_area=False)
    result, log, _ = _run(config)
    _, pre, _ = _expected(config)
    logged = pre.record["log_transformed_bands"][0]
    renames = [c for c in calls(log, ".rename") if c.args == (logged,)]
    (scaled,) = [c for c in renames if made_by(log, c.owner).attr == "divide"]
    divide = made_by(log, scaled.owner)
    assert divide.args == (pre.record["scaling"][logged]["spread"],)
    subtract = owner_call(log, divide)
    assert subtract.args == (pre.record["scaling"][logged]["center"],)
    took_log = owner_call(log, subtract)
    assert took_log.attr == "log"
    added = owner_call(log, took_log)
    assert added.attr == "add" and added.args == (pre.record["log_offsets"][logged],)


def test_the_stage_hands_over_the_table_the_rows_and_the_fit_as_files():
    config = _config(fit_excludes_stands_below_min_area=False)
    result, _, _ = _run(config)
    table, pre, fit = _expected(config)
    files = result.files
    assert set(files) == {"clustering_stand_table.csv", "clustering_fit_rows.csv", "clustering_kmeans.json"}
    raw = list(csv.reader(io.StringIO(files["clustering_stand_table.csv"])))
    assert raw[0] == ["stand_lbl", "in_fit", *table.bands]
    assert [int(r[0]) for r in raw[1:]] == sorted(TABLE_LABELS)
    rows = list(csv.reader(io.StringIO(files["clustering_fit_rows.csv"])))
    assert rows[0] == ["stand_lbl", "in_fit", "type", *pre.bands]
    assert [int(r[2]) for r in rows[1:]] == fit.types.tolist()
    fitted = json.loads(files["clustering_kmeans.json"])
    assert np.allclose(fitted["centres"], fit.centres) and fitted["k"] == config.clustering.k


def test_the_stage_metadata_says_how_it_was_fitted():
    config = _config(fit_excludes_stands_below_min_area=False)
    result, _, _ = _run(config)
    meta = result.metadata
    assert meta["fit_outside_earth_engine"] is True and meta["log_rule"] == "abs_skew"
    assert {"kmeans_wcss", "kmeans_starts_ari_median", "kmeans_starts_ari_min"} <= set(meta)


def test_the_embedding_arm_takes_the_same_path():
    config = _config(EMBEDDING_YAML, fit_excludes_stands_below_min_area=False)
    _, log, _ = _run(config)
    meta = _metadata(log)
    assert meta["fit_outside_earth_engine"] is True and meta["feature_source"] == "embedding"
    assert len(meta["active_bands"]) == 63  # A63 has no spread (the stand-ins)


def test_too_few_rows_for_k_is_an_error():
    config = _config(k=21, fit_excludes_stands_below_min_area=False)
    with pytest.raises(ValueError, match="only 20"):
        _run(config)


def test_off_no_key_moves_and_on_the_clustering_and_k_elbow_keys_and_the_fingerprint_move(monkeypatch):
    monkeypatch.chdir(REPO)
    raw = yaml.safe_load(BOX_YAML.read_text())
    base = Config.model_validate(raw)
    written_off = Config.model_validate(
        {**raw, "clustering": {**raw.get("clustering", {}), "fit_outside_earth_engine": False}}
    )
    on = _config()
    assert step_keys(written_off) == step_keys(base)
    assert config_fingerprint(written_off) == config_fingerprint(base)
    keys, keys_on = step_keys(base), step_keys(on)
    assert {s for s in keys if keys[s] != keys_on[s]} == {"clustering", "k_elbow"}
    assert config_fingerprint(on) != config_fingerprint(base)

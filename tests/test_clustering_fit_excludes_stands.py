"""Offline checks of `clustering.fit_excludes_stands_below_min_area`: specks out of the fit.

docs/decisions.yaml, spec-clustering-fit-excludes-stands-below-min-area. The stands the
merge leaves below merge.min_area_ha stay on the map, are left out of the k-means training
rows, and are typed by the trained clusterer like every other unit. Earth Engine is
replaced by the recorder of tests/_ee_recorder.py and the answers of
tests/_clustering_stand_ins.py, so what is checked here is the wiring: which image each
sample is taken from, which rows the fit is trained on, which image is typed, what is
counted, and what is recorded. tests/test_clustering_off_golden.py holds the default path;
tests/test_clustering_fit_excludes_ee_graph.py builds the requests of this path with the
real Earth Engine client, offline.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

import fmu.stages.clustering as clustering
from _clustering_stand_ins import (
    LEFT_OUT_ROWS,
    TRAINING_ROWS,
    UNITS_IN_HABITAT,
    UNITS_IN_ROI,
    inputs,
    run_stage,
)
from _ee_recorder import Call, Rec, call_log, calls, made_by, owner_call
from fmu.config import Config
from fmu.stages.base import PipelineContext
from fmu.stages.clustering import (
    ClusteringStage,
    _stands_below_min_area,
    tabulate_clustering_metadata,
)
from fmu.stages.merge import MergeStage
from fmu.utils.gee import LABEL_BAND

REPO = Path(__file__).resolve().parent.parent
BOX_YAML = REPO / "configs" / "odisha_v120_3ha_squares_koraput.yaml"  # k = 5

# Four of the 25 stands are below the minimum. Stand 15 has no training row (it lies
# outside the habitat mask, say), so the sample of the four finds the other three.
BELOW_MIN = {4: 0.12, 9: 0.5, 12: 0.03, 15: 0.8}
WITH_A_ROW = [4, 9, 12]
FIT_ROWS = TRAINING_ROWS - len(WITH_A_ROW)
NEW_KEYS = {
    "fit_excludes_stands_below_min_area",
    "n_stands_below_min_area",
    "area_ha_in_stands_below_min_area",
    "n_stands_left_out_of_fit",
    "area_ha_in_stands_left_out_of_fit",
}


def _config(on: bool = True) -> Config:
    raw = yaml.safe_load(BOX_YAML.read_text())
    raw["clustering"] = {**raw.get("clustering", {}), "fit_excludes_stands_below_min_area": on}
    return Config.model_validate(raw)


def _merge_outputs(below_min: dict[int, float]) -> dict[str, Any]:
    """stand_provenance and stand_attributes as the merge writes them, for 25 stands."""
    provenance = {
        sid: {
            "n_superpx": 1,
            "n_pass1": 0,
            "n_relaxed": 0,
            "n_fallback": 0,
            "below_min": int(sid in below_min),
            "below_why": "isolated" if sid in below_min else "",
        }
        for sid in range(UNITS_IN_ROI)
    }
    attributes = {
        sid: {"n_pixels": 300, "area_ha": below_min.get(sid, 2.5)} for sid in range(UNITS_IN_ROI)
    }
    return {"stand_provenance": provenance, "stand_attributes": attributes}


def _run_on(
    below_min: dict[int, float] = BELOW_MIN,
    fit_rows: int = FIT_ROWS,
    left_out_rows: list[Any] = WITH_A_ROW,
) -> tuple[Any, list, PipelineContext]:
    return run_stage(
        clustering,
        _config(),
        merge_outputs=_merge_outputs(below_min),
        fit_rows=fit_rows,
        left_out_rows=left_out_rows,
    )


def _clustering_metadata(log: list) -> dict[str, Any]:
    (stamp,) = [c for c in log if c.attr == "set" and c.args[:1] == ("clustering_metadata",)]
    return json.loads(stamp.args[1])


def _recs(value: Any) -> list[Rec]:
    if isinstance(value, Rec):
        return [value]
    if isinstance(value, dict):
        return [r for v in value.values() for r in _recs(v)]
    if isinstance(value, (list, tuple)):
        return [r for v in value for r in _recs(v)]
    return []


def _upstream(log: list, obj: Any) -> list[Call]:
    """Every recorded call `obj` was built from: the call that made it, then the calls
    that made the object it was a method of and its arguments, back to the inputs."""
    made = {id(c.out): c for c in log if isinstance(c.out, Rec)}
    found: list[Call] = []
    todo, seen = [obj], set()
    while todo:
        call = made.get(id(todo.pop()))
        if call is None or id(call) in seen:
            continue
        seen.add(id(call))
        found.append(call)
        todo.extend([call.owner, *_recs(call.args), *_recs(call.kwargs)])
    return found


def _masks(log: list) -> tuple[Call, Call]:
    """The two remaps of the stand labels: 1 on the other stands, then 1 on these."""
    others, themselves = calls(log, ".remap")
    return others, themselves


# ---------------------------------------------------------------- which rows, which image


def test_the_k_means_rows_come_from_the_image_masked_to_the_other_stands():
    _, log, ctx = _run_on()
    others, themselves = _masks(log)
    assert others.owner is ctx.get("stand_clusters")
    assert others.args == ([4, 9, 12, 15], [0, 0, 0, 0], 1)
    (train,) = calls(log, ".train")
    sample = made_by(log, train.kwargs["features"])
    assert sample.attr == "stratifiedSample"
    stacked = owner_call(log, sample)
    assert stacked.attr == "addBands"
    masked = owner_call(log, stacked)
    assert masked.attr == "updateMask" and masked.args == (others.out,)
    # ... of the training image itself: the scaled stack inside the habitat mask.
    assert made_by(log, masked.owner).args == (ctx.get("habitat_mask"),)
    assert themselves not in _upstream(log, train.kwargs["features"])


def test_the_preprocessing_samples_still_take_every_unit():
    """The log transform is log(x - min + 0.001), min the minimum of its sample: a stand
    left out of that sample could lie below it and get the log of a negative number."""
    _, log, _ = _run_on()

    def masked_by_label(obj: Any) -> bool:
        return any(c.attr == "remap" for c in _upstream(log, obj))

    samples = calls(log, ".stratifiedSample")
    assert len(samples) == 5  # skewness and offsets, scaling, all rows, fit rows, rows left out
    assert [masked_by_label(s.out) for s in samples] == [False, False, False, True, True]
    columns = calls(log, ".reduceColumns")
    assert columns, "no statistic was taken"
    assert not [c.args for c in columns if masked_by_label(c.out)]


def test_every_unit_is_typed_by_the_trained_clusterer():
    _, log, _ = _run_on()
    (cluster,) = calls(log, ".cluster")
    (train,) = calls(log, ".train")
    assert cluster.args == (train.out,)
    upstream = _upstream(log, cluster.owner)
    assert not [c for c in upstream if c.attr == "remap"]
    # The image typed is the one every row was sampled from.
    all_rows = calls(log, ".stratifiedSample")[2]
    assert owner_call(log, all_rows).owner is cluster.owner


def test_the_stands_left_out_are_read_from_a_sample_of_them_alone():
    _, log, ctx = _run_on()
    others, themselves = _masks(log)
    assert themselves.owner is ctx.get("stand_clusters")
    assert themselves.args == ([4, 9, 12, 15], [1, 1, 1, 1], 0)
    (array,) = calls(log, ".aggregate_array")
    assert array.args == (LABEL_BAND,)
    upstream = _upstream(log, array.out)
    assert themselves in upstream and others not in upstream
    asked = [c.kwargs["context"] for c in log if c.name == "getInfo" and c.args == (array.out,)]
    assert asked == [LEFT_OUT_ROWS]


# ---------------------------------------------------------------- what is counted and recorded


def test_the_metadata_says_how_many_were_left_out_and_their_area():
    """Stand 15 is below the minimum but had no row, so it counts below the minimum and
    not as left out of the fit."""
    _, log, _ = _run_on()
    meta = _clustering_metadata(log)
    assert meta["fit_excludes_stands_below_min_area"] is True
    assert meta["n_stands_below_min_area"] == 4
    assert meta["area_ha_in_stands_below_min_area"] == pytest.approx(1.45)
    assert meta["n_stands_left_out_of_fit"] == 3
    assert meta["area_ha_in_stands_left_out_of_fit"] == pytest.approx(0.65)
    assert meta["n_training_units"] == FIT_ROWS


def test_missing_band_data_is_counted_against_the_rows_before_the_stands_are_left_out():
    _, log, _ = _run_on()
    meta = _clustering_metadata(log)
    assert meta["n_units_dropped_null_band"] == UNITS_IN_HABITAT - TRAINING_ROWS == 2
    assert meta["n_units_in_habitat"] == (
        meta["n_training_units"] + meta["n_units_dropped_null_band"] + meta["n_stands_left_out_of_fit"]
    )


def test_on_the_metadata_is_the_metadata_of_off_with_the_new_keys():
    """Everything the preprocessing found is as it is with the setting off; only the row
    count of the fit and the five new keys differ."""
    _, off_log, _ = run_stage(clustering, _config(on=False))
    _, on_log, _ = _run_on()
    off, on = _clustering_metadata(off_log), _clustering_metadata(on_log)
    assert set(on) - set(off) == NEW_KEYS
    assert set(off) <= set(on)
    same = set(off) - {"n_training_units"}
    assert {k: on[k] for k in same} == {k: off[k] for k in same}
    assert off["n_training_units"] == TRAINING_ROWS


def test_the_summary_numbers_read_the_metadata_with_the_setting_on():
    _, log, _ = _run_on()
    numbers = tabulate_clustering_metadata(_clustering_metadata(log))
    assert numbers["units_fitted"] == FIT_ROWS
    assert numbers["units_dropped_missing_band"] == 2


def test_the_stage_metadata_records_the_setting_on_and_off():
    on, _, _ = _run_on()
    off, _, _ = run_stage(clustering, _config(on=False))
    assert on.metadata["fit_excludes_stands_below_min_area"] is True
    assert off.metadata["fit_excludes_stands_below_min_area"] is False
    assert {k: v for k, v in on.metadata.items() if k != "fit_excludes_stands_below_min_area"} == {
        k: v for k, v in off.metadata.items() if k != "fit_excludes_stands_below_min_area"
    }


def test_with_no_stand_below_the_minimum_the_fit_takes_every_row_and_counts_zeros():
    """Nothing more is asked of Earth Engine: the calls are those of the default path."""
    _, log, _ = run_stage(clustering, _config(), merge_outputs=_merge_outputs({}))
    assert not calls(log, ".remap") and not calls(log, ".aggregate_array")
    samples = calls(log, ".stratifiedSample")
    assert len(samples) == 3
    (train,) = calls(log, ".train")
    assert train.kwargs["features"] is samples[2].out
    meta = _clustering_metadata(log)
    assert {k: meta[k] for k in NEW_KEYS} == {
        "fit_excludes_stands_below_min_area": True,
        "n_stands_below_min_area": 0,
        "area_ha_in_stands_below_min_area": 0.0,
        "n_stands_left_out_of_fit": 0,
        "area_ha_in_stands_left_out_of_fit": 0.0,
    }
    assert isinstance(meta["area_ha_in_stands_below_min_area"], float)
    assert meta["n_training_units"] == TRAINING_ROWS

    _, off_log, _ = run_stage(clustering, _config(on=False))
    on_calls, off_calls = call_log(log), call_log(off_log)
    stamp = [i for i, c in enumerate(log) if c.attr == "set"]
    assert len(on_calls) == len(off_calls) and stamp == [i for i, c in enumerate(off_log) if c.attr == "set"]
    keep = [i for i in range(len(log)) if i not in stamp]
    assert [on_calls[i] for i in keep] == [off_calls[i] for i in keep]


def test_rows_that_do_not_add_up_are_warned_about_and_the_fit_goes_on(caplog):
    with caplog.at_level(logging.WARNING, logger=clustering.log.name):
        _, log, _ = _run_on(fit_rows=FIT_ROWS - 1)
    assert "do not add up" in caplog.text
    assert _clustering_metadata(log)["n_training_units"] == FIT_ROWS - 1


def test_a_row_of_another_unit_in_the_sample_of_the_stands_is_not_counted(caplog):
    with caplog.at_level(logging.WARNING, logger=clustering.log.name):
        _, log, _ = _run_on(fit_rows=FIT_ROWS - 1, left_out_rows=[*WITH_A_ROW, 7])
    assert "other unit(s) (7)" in caplog.text
    assert _clustering_metadata(log)["n_stands_left_out_of_fit"] == 3


def test_no_row_for_any_of_them_is_warned_about(caplog):
    """With the stands on kept land, a stand below the minimum is in the habitat mask, so
    none of them with a row is worth a look."""
    with caplog.at_level(logging.WARNING, logger=clustering.log.name):
        _, log, _ = _run_on(fit_rows=TRAINING_ROWS, left_out_rows=[])
    assert "none of the 4 stand(s)" in caplog.text
    meta = _clustering_metadata(log)
    assert meta["n_stands_left_out_of_fit"] == 0 and meta["n_training_units"] == TRAINING_ROWS


def test_the_guard_on_k_counts_the_rows_of_the_fit():
    """Twenty rows clear k = 5; four left after the stands are left out do not."""
    with pytest.raises(ValueError, match="only 4 stand_clusters unit.*once the 3 stand"):
        _run_on(fit_rows=4)


def test_too_few_rows_before_any_stand_is_left_out_stops_before_the_two_samples(monkeypatch):
    """Three rows do not clear k = 5 whatever is left out: the stage says so at once, as with
    the setting off, without the two samples of the stands left out and without blaming them."""
    import _clustering_stand_ins as stand_ins

    asked: list[str] = []
    real = stand_ins.answers

    def recording(config, log, **kwargs):
        get = real(config, log, **kwargs)

        def wrapped(obj, context=""):
            asked.append(context)
            return get(obj, context=context)

        return wrapped

    monkeypatch.setattr(stand_ins, "answers", recording)
    monkeypatch.setattr(stand_ins, "TRAINING_ROWS", 3)
    with pytest.raises(ValueError) as err:
        _run_on(fit_rows=2, left_out_rows=[4])
    assert "only 3 stand_clusters unit(s) available to fit k=5 clusters on." in str(err.value)
    assert "once the" not in str(err.value)
    assert asked and stand_ins.FIT_ROW_COUNT not in asked and stand_ins.LEFT_OUT_ROWS not in asked


# ---------------------------------------------------------------- inputs and config


def test_the_stands_below_the_minimum_are_the_ones_the_merge_flags():
    merge = _merge_outputs(BELOW_MIN)
    merge["stand_provenance"][9]["below_why"] = "area_blocked"
    assert _stands_below_min_area(merge["stand_provenance"], merge["stand_attributes"]) == BELOW_MIN
    as_text = {str(k): v for k, v in merge["stand_provenance"].items()}
    attributes = {str(k): v for k, v in merge["stand_attributes"].items()}
    assert _stands_below_min_area(as_text, attributes) == BELOW_MIN


def _ctx(keys: set[str]) -> PipelineContext:
    ctx = PipelineContext()
    for key in sorted(keys):
        ctx.set(key, f"<{key}>")
    return ctx


def test_validate_asks_for_the_two_merge_outputs_only_with_the_setting_on():
    base = inputs(_config(on=False))
    ClusteringStage().validate(_ctx(base), _config(on=False))
    with pytest.raises(KeyError, match=r"\['stand_attributes', 'stand_provenance'\]"):
        ClusteringStage().validate(_ctx(base), _config())
    ClusteringStage().validate(_ctx(base | {"stand_provenance", "stand_attributes"}), _config())
    assert {"stand_provenance", "stand_attributes"} <= MergeStage.produces


def test_the_setting_needs_the_merge():
    raw = yaml.safe_load(BOX_YAML.read_text())
    raw["merge"]["enabled"] = False
    raw["clustering"]["fit_excludes_stands_below_min_area"] = True
    with pytest.raises(ValidationError, match="needs merge.enabled"):
        Config.model_validate(raw)
    raw["clustering"]["fit_excludes_stands_below_min_area"] = False
    assert Config.model_validate(raw).unit_label_key() == "snic_clusters"


def test_off_by_default():
    from fmu.config import ClusteringParams

    assert ClusteringParams().fit_excludes_stands_below_min_area is False

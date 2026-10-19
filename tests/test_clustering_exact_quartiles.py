"""The constant-band test and the robust scaling take exact quartiles (review B16).

The robust scaling (DEC-003) divides each band by its IQR over the one-row-per-unit sample,
and drops a band whose IQR is 0 as constant. It took p25, p50 and p75 from Earth Engine's
percentile reducer, which falls back to histogram buckets: where p25 and p75 share a bucket
the spread is exactly 0, and a band with spread was dropped (distance_to_water in round 7's
two Koraput runs). The quartiles are now exact: each band's column of the sample is read back
and its quartiles taken by linear interpolation between order statistics, numpy's default.
The drop test and the scaling use that one centre and spread.

On the stand-ins of tests/_clustering_stand_ins.py, distance_to_water is given a column whose
exact IQR is 0.1, and, for the request the stage made before, the answer of a histogram whose
one bucket holds p25 to p75.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import _clustering_stand_ins as stand_ins
import fmu.stages.clustering as clustering
from _ee_recorder import calls, made_by
from fmu.config import load_config

HERE = Path(__file__).resolve().parent
WATER = [5.1, 4.9, 5.0, 5.05, 4.95]  # exact p25 4.95, p50 5.0, p75 5.05: an IQR of 0.1
ONE_BUCKET = {"p25": 5.0, "p50": 5.0, "p75": 5.0}


def _run(config_name: str) -> tuple[dict[str, Any], list]:
    """clustering_metadata of a run on the stand-ins, and its call log."""
    config = load_config(HERE.parent / "configs" / config_name)
    _, log, _ = stand_ins.run_stage(clustering, config)
    (stamp,) = [c for c in log if c.attr == "set" and c.args[:1] == ("clustering_metadata",)]
    return json.loads(stamp.args[1]), log


@pytest.fixture
def water_with_spread(monkeypatch) -> tuple[dict[str, Any], list]:
    """The baseline run, with distance_to_water's column spread over 0.1 and its histogram
    quartiles in one bucket."""
    real = stand_ins.answers

    def answers(config: Any, log: list, **kwargs: Any) -> Any:
        get = real(config, log, **kwargs)

        def get_info(obj: Any, context: str = "") -> Any:
            answer = get(obj, context=context)
            if context == "values of distance_to_water":
                return list(WATER)
            if context == "p25/p50/p75 of distance_to_water":
                return dict(ONE_BUCKET)
            return answer

        return get_info

    monkeypatch.setattr(stand_ins, "answers", answers)
    return _run("sanjay_van_baseline.yaml")


def test_a_band_with_spread_is_kept_though_its_histogram_quartiles_coincide(water_with_spread):
    meta, _ = water_with_spread
    assert "distance_to_water" not in meta["dropped_constant_bands"]
    assert "distance_to_water" in meta["active_bands"]


def test_its_centre_and_spread_are_the_exact_median_and_iqr(water_with_spread):
    meta, _ = water_with_spread
    assert meta["scaling"]["distance_to_water"]["center"] == 5.0
    assert meta["scaling"]["distance_to_water"]["spread"] == pytest.approx(0.1)


def test_the_scaling_takes_that_centre_and_spread(water_with_spread):
    """The drop test and the scaling read the same centre and spread:
    (x - centre) / spread."""
    meta, log = water_with_spread
    (divide,) = [
        c for c in calls(log, ".divide")
        if made_by(log, made_by(log, c.owner).owner).args == ("distance_to_water",)
    ]
    subtract = made_by(log, divide.owner)
    assert subtract.attr == "subtract"
    assert subtract.args == (meta["scaling"]["distance_to_water"]["center"],)
    assert divide.args == (meta["scaling"]["distance_to_water"]["spread"],)


def test_a_band_without_spread_is_still_dropped():
    """The stand-ins' constant bands: distance_to_water, and A63 of the embedding."""
    for config_name, band in (
        ("sanjay_van_baseline.yaml", "distance_to_water"),
        ("odisha_alphaearth_angul_repro.yaml", "A63"),
    ):
        meta, _ = _run(config_name)
        assert meta["dropped_constant_bands"] == [band]
        assert meta["scaling"][band] == {"center": 5.0, "spread": 0.0}


def test_each_bands_column_is_read_and_no_percentile_reducer_is_used():
    meta, log = _run("sanjay_van_baseline.yaml")
    asked = [c.kwargs["context"] for c in log if c.name == "getInfo"]
    read = [c.removeprefix("values of ") for c in asked if c.startswith("values of ")]
    assert read == list(stand_ins.HANDCRAFTED_DECOMPOSED)
    assert not calls(log, "ee.Reducer.percentile")


@pytest.mark.parametrize(
    ("values", "quartiles"),
    [
        ([4.0, 1.0, 3.0, 2.0], (1.75, 2.5, 3.25)),
        ([7.0], (7.0, 7.0, 7.0)),
        ([float(v) for v in range(11)], (2.5, 5.0, 7.5)),
        (WATER, (4.95, 5.0, 5.05)),
    ],
)
def test_the_quartiles_interpolate_between_order_statistics(values, quartiles):
    """v[j] + (h - j)(v[j+1] - v[j]) with h = q(n - 1), j = floor(h), the values sorted."""
    assert clustering._exact_quartiles(values) == pytest.approx(quartiles)

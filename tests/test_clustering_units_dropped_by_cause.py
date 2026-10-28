"""The units with no k-means row, counted by cause (round 14; round 13's question 35, answer (a)).

Until round 14 `n_units_dropped_null_band` (the summary number `units_dropped_missing_band`)
was the units inside the habitat mask less the training rows. That lumped two causes
together: a unit with no habitat pixel whose centre is inside the ROI (the one-pixel sample
takes pixel centres, so it has no row, and the export gives it no polygon), which is what the
count held in every per-step run of record (review C15), and a unit with a band gap. They are
now counted apart: the units with a habitat pixel centre inside the ROI are counted with an
unweighted histogram, which counts whole pixels by their centre (as the merge's histograms do,
review B17), and whose "null" key holds the masked pixels, not a unit.

Earth Engine is replaced by the recorder of tests/_ee_recorder.py and the answers of
tests/_clustering_stand_ins.py: 22 units inside the habitat mask, 21 of them with a habitat
pixel centre inside the ROI, 20 training rows.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

import fmu.stages.clustering as clustering
from _clustering_stand_ins import (
    TRAINING_ROWS,
    UNITS_IN_HABITAT,
    UNITS_WITH_A_CENTRE,
    run_stage,
)
from _ee_recorder import calls, made_by, owner_call
from fmu.config import Config
from fmu.stages.clustering import tabulate_clustering_metadata

REPO = Path(__file__).resolve().parent.parent
BOX_YAML = REPO / "configs" / "odisha_v120_3ha_squares_koraput.yaml"


def _config() -> Config:
    return Config.model_validate(yaml.safe_load(BOX_YAML.read_text()))


def _metadata(log: list) -> dict[str, Any]:
    (stamp,) = [c for c in log if c.attr == "set" and c.args[:1] == ("clustering_metadata",)]
    return json.loads(stamp.args[1])


def test_the_two_causes_are_counted_apart():
    _, log, _ = run_stage(clustering, _config())
    meta = _metadata(log)
    assert meta["n_units_no_pixel_centre_in_roi"] == UNITS_IN_HABITAT - UNITS_WITH_A_CENTRE == 1
    assert meta["n_units_dropped_null_band"] == UNITS_WITH_A_CENTRE - TRAINING_ROWS == 1
    assert meta["n_units_in_habitat"] == (
        meta["n_training_units"]
        + meta["n_units_dropped_null_band"]
        + meta["n_units_no_pixel_centre_in_roi"]
    )


def test_the_count_by_pixel_centre_is_an_unweighted_histogram_of_the_habitat_labels():
    """Unweighted: a pixel counts by its centre, the pixels the one-pixel sample can take;
    and of the unit labels masked to the habitat mask."""
    _, log, ctx = run_stage(clustering, _config())
    histograms = calls(log, "frequencyHistogram")
    unweighted = [c for c in calls(log, ".unweighted") if made_by(log, c.owner) in histograms]
    assert len(unweighted) == 1
    (reduce,) = [c for c in calls(log, ".reduceRegion") if c.kwargs.get("reducer") is unweighted[0].out]
    selected = owner_call(log, reduce)  # labels.select([band])
    masked = owner_call(log, selected)  # unit_labels.updateMask(habitat_mask)
    assert masked.attr == "updateMask"
    assert masked.owner is ctx.get("stand_clusters")
    assert masked.args == (ctx.get("habitat_mask"),)


def test_the_masked_pixels_of_the_unweighted_histogram_are_not_a_unit():
    """The stand-in's histogram has 21 labels and the key "null"; 22 would be counted
    by taking every key."""
    _, log, _ = run_stage(clustering, _config())
    assert _metadata(log)["n_units_no_pixel_centre_in_roi"] == 1


def test_the_summary_numbers_count_both_causes():
    _, log, _ = run_stage(clustering, _config())
    numbers = tabulate_clustering_metadata(_metadata(log))
    assert numbers["units_dropped_missing_band"] == 1
    assert numbers["units_with_no_pixel_centre_in_roi"] == 1
    assert numbers["units_in_habitat"] == (
        numbers["units_fitted"]
        + numbers["units_dropped_missing_band"]
        + numbers["units_with_no_pixel_centre_in_roi"]
        + numbers["units_left_out_of_fit"]
    )


def test_an_asset_made_before_the_split_has_no_count_by_pixel_centre():
    """Its n_units_dropped_null_band held both causes; nothing splits it afterwards, so the
    new number is absent (None), not 0, and the old one is given as it was recorded."""
    old = {
        "k": 5,
        "n_training_units": 280,
        "n_units_total": 300,
        "n_units_in_habitat": 284,
        "n_units_outside_habitat": 16,
        "n_units_dropped_null_band": 4,
    }
    numbers = tabulate_clustering_metadata(old)
    assert numbers["units_with_no_pixel_centre_in_roi"] is None
    assert numbers["units_dropped_missing_band"] == 4


def test_the_new_number_is_declared_and_described():
    said = {s.name: s.description for s in clustering.ClusteringStage.summary_numbers}
    assert "units_with_no_pixel_centre_in_roi" in said
    assert "centre" in said["units_with_no_pixel_centre_in_roi"]
    assert "band gap" in said["units_dropped_missing_band"]


def test_the_split_never_goes_negative():
    """The counts come from different reductions, so they are clamped at 0, as the
    split between habitat and non-habitat is."""
    assert clustering._split_by_cause(n_in_habitat=20, n_with_a_centre=22, n_rows=23) == (0, 0)


@pytest.mark.parametrize("n_in_habitat, n_with_a_centre, n_rows", [(22, 21, 20), (5, 5, 5)])
def test_the_split_adds_up(n_in_habitat: int, n_with_a_centre: int, n_rows: int):
    no_centre, band_gap = clustering._split_by_cause(
        n_in_habitat=n_in_habitat, n_with_a_centre=n_with_a_centre, n_rows=n_rows
    )
    assert no_centre + band_gap + n_rows == n_in_habitat

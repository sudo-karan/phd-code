"""A harmonic phase's sin and cos are never candidates for the skew test or the log (review B13).

The cyclic decomposition runs before the skew test, so the sin and cos of a phase band
(ndvi_phase_annual_sin, ndvi_phase_annual_cos) were tested for skew and logged one by one,
like any band: the cos in every hand-crafted _r9 run. A phase's components now go to the
scaling as they come out of the decomposition. Every other band is tested exactly as before:
the same |skew| > threshold rule and the same offset. Aspect's pair is a band like the others
here (the brief names the phase only). Run on the stand-ins of tests/_clustering_stand_ins.py.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import _clustering_stand_ins as stand_ins
import fmu.stages.clustering as clustering
from fmu.config import load_config

HERE = Path(__file__).resolve().parent
PHASE_PAIR = ("ndvi_phase_annual_sin", "ndvi_phase_annual_cos")
SKEWED = 2.5  # the skew the stand-ins give vh_iqr


def _metadata_and_requests(config_name: str) -> tuple[dict[str, Any], list[str]]:
    """clustering_metadata of a run on the stand-ins, and the context of every request."""
    config = load_config(HERE.parent / "configs" / config_name)
    _, log, _ = stand_ins.run_stage(clustering, config)
    (stamp,) = [c for c in log if c.attr == "set" and c.args[:1] == ("clustering_metadata",)]
    return json.loads(stamp.args[1]), [c.kwargs["context"] for c in log if c.name == "getInfo"]


@pytest.fixture
def skewed_phase(monkeypatch) -> tuple[dict[str, Any], list[str]]:
    """The baseline run with the phase pair and aspect_cos given the skew of vh_iqr."""
    for band in (*PHASE_PAIR, "aspect_cos"):
        monkeypatch.setitem(stand_ins.SKEW, band, SKEWED)
    return _metadata_and_requests("sanjay_van_baseline.yaml")


def test_a_phase_component_above_the_threshold_is_not_logged(skewed_phase):
    meta, _ = skewed_phase
    for band in PHASE_PAIR:
        assert band not in meta["log_transformed_bands"]
        assert band not in meta["log_offsets"]


def test_another_band_with_the_same_skew_still_is(skewed_phase):
    """vh_iqr has the same skew; aspect's pair is tested like any other band."""
    meta, _ = skewed_phase
    assert stand_ins.SKEW["vh_iqr"] == SKEWED
    for band in ("vh_iqr", "aspect_cos"):
        assert band in meta["log_transformed_bands"]
        assert band in meta["log_offsets"]


def test_the_phase_pair_is_not_asked_for_its_skew_and_every_other_band_is(skewed_phase):
    _, asked = skewed_phase
    tested = sorted(c.removeprefix("skew of ") for c in asked if c.startswith("skew of "))
    assert tested == sorted(b for b in stand_ins.HANDCRAFTED_DECOMPOSED if b not in PHASE_PAIR)


def test_the_phase_pair_is_still_scaled_and_clustered(skewed_phase):
    """Only the skew test and the log leave it out; the scaling is as before (A2)."""
    meta, _ = skewed_phase
    for band in PHASE_PAIR:
        assert band in meta["active_bands"]
        assert meta["scaling"][band] == {"center": 0.5, "spread": 0.75}


@pytest.mark.parametrize(
    "config_name", ["odisha_v120_3ha_squares_koraput.yaml", "odisha_alphaearth_angul_repro.yaml"]
)
def test_with_the_phase_pair_below_the_threshold_the_logged_bands_are_as_recorded(config_name):
    """With the stand-ins' own skews (0.3 for the phase pair) nothing changes: the logged
    bands and offsets are those of tests/data/clustering_off_calls.json."""
    recorded = json.loads((HERE / "data" / "clustering_off_calls.json").read_text())
    before = recorded[f"configs/{config_name}"]["clustering_metadata"]
    meta, _ = _metadata_and_requests(config_name)
    assert meta["log_transformed_bands"] == before["log_transformed_bands"]
    assert meta["log_offsets"] == before["log_offsets"]

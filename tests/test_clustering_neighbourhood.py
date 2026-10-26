"""The reduceConnectedComponents neighbourhood of the clustering stage, and what replaced it.

From round 9 to round 12 the clustering stage averaged the features per unit with
reduceConnectedComponents, and passed it as maxSize the widest unit extent it measured, plus
a margin and never above Config.max_component_pixels(), because Earth Engine pads every tile
by maxSize (docs/pending_decisions/clustering_rcc_neighbourhood.md, and the register entry
spec-clustering-measured-neighbourhood). This file tested that measurement.

reduceConnectedComponents averages each 8-connected piece of a label on its own, so a stand
in several pieces had one mean per piece (review B14). Since round 13 the stage takes one mean
per unit label with a grouped reduction, which has no maxSize, and the neighbourhood, its
measurement, the stage's check of the labels against the cap and the stage-metadata keys
that described them went with it. The new means are tested in
tests/test_clustering_one_mean_per_unit.py (numpy stand-ins) and
tests/test_clustering_unit_means_live.py (Earth Engine). What is left here pins that the
neighbourhood went: the stage makes neither call and records none of the five keys.

No Earth Engine call is made.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import fmu.stages.clustering as clustering
from _clustering_stand_ins import run_stage
from _ee_recorder import calls
from fmu.config import load_config

REPO = Path(__file__).resolve().parent.parent
# Recorded until round 13 in the clustering stage's metadata (docs/outputs.md).
GONE = {
    "n_components",
    "largest_component_px",
    "max_component_px_cap",
    "rcc_neighbourhood_px",
    "widest_unit_extent_px",
}


@pytest.mark.parametrize(
    "config_name", ["sanjay_van_baseline.yaml", "odisha_alphaearth_angul_repro.yaml"]
)
def test_the_unit_means_take_no_neighbourhood(config_name: str):
    result, log, _ = run_stage(clustering, load_config(REPO / "configs" / config_name))
    assert not calls(log, ".reduceConnectedComponents")
    assert not calls(log, "ee.Image.pixelCoordinates")
    assert not GONE & set(result.metadata)

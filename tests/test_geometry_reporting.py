"""Non-live tests for two counts a live run showed were not what they claimed.

Both are cases where a number looked fine and meant something else.

1. `stands_merged: 329 features` against a merge that produced **327 stands**.
   `reduceToVectors` emits one polygon per connected component of a label, not
   one per label, so a spatially disconnected stand comes back as several
   polygons sharing a `stand_lbl`. Nothing said so, and `n_features` went into
   the manifest where it read as the stand count.

2. `Polsby-Popper min/median/max = 0.031 / 0.174 / 1.058`. Polsby-Popper is
   `4*pi*A/P^2`, which is exactly 1.0 for a circle and strictly below it for
   every other planar shape. 1.058 is not a rounder stand; it is arithmetic on
   an area and a perimeter that describe different footprints.
"""

from __future__ import annotations

import pytest

import fmu.stages.export as export_mod
from fmu.stages.export import _stand_polygon_counts, _warn_on_split_stands
from fmu.utils.adjacency import summarize_stand_geometry

# ---------- polygons vs stands ----------


class _FakeFC:
    def __init__(self, labels):
        self._labels = labels

    def aggregate_array(self, prop):  # noqa: N802 - mirrors the ee API
        assert prop == "stand_lbl"
        return self._labels


@pytest.fixture
def no_getinfo(monkeypatch):
    # `aggregate_array` already hands back the plain list here, so the fake
    # `safe_get_info` is the identity rather than a getInfo.
    monkeypatch.setattr(export_mod, "safe_get_info", lambda obj, *, context="": obj)


def test_one_polygon_per_stand_is_the_clean_case(no_getinfo):
    c = _stand_polygon_counts(_FakeFC([11, 22, 33]))
    assert c == {"n_stands": 3, "n_split": 0, "max_pieces": 1}


def test_a_split_stand_is_counted_once_as_a_stand(no_getinfo):
    """The observed shape: two labels each vectorised into two polygons, giving
    329 features for 327 stands."""
    c = _stand_polygon_counts(_FakeFC([11, 11, 22, 22, 33]))
    assert c["n_stands"] == 3
    assert c["n_split"] == 2
    assert c["max_pieces"] == 2


def test_the_worst_case_is_reported_not_just_the_count(no_getinfo):
    """Two stands each in two pieces is a boundary artefact. One stand in six is
    a different problem, and the split count alone cannot tell them apart."""
    c = _stand_polygon_counts(_FakeFC([11] * 6 + [22, 33]))
    assert c["n_split"] == 1
    assert c["max_pieces"] == 6


def test_float_labels_from_the_server_still_group(no_getinfo):
    """EE returns label values as floats often enough that grouping on the raw
    value would split 11 from 11.0."""
    c = _stand_polygon_counts(_FakeFC([11.0, 11, 22.0]))
    assert c["n_stands"] == 2


def test_an_empty_collection_does_not_raise(no_getinfo):
    assert _stand_polygon_counts(_FakeFC([])) == {
        "n_stands": 0,
        "n_split": 0,
        "max_pieces": 1,
    }


def test_no_warning_when_polygons_and_stands_agree(caplog):
    with caplog.at_level("WARNING"):
        _warn_on_split_stands({"n_stands": 327, "n_split": 0, "max_pieces": 1}, 327)
    assert caplog.text == ""


def test_the_warning_names_both_counts_and_the_remedy(caplog):
    with caplog.at_level("WARNING"):
        _warn_on_split_stands({"n_stands": 327, "n_split": 2, "max_pieces": 2}, 329)
    assert "329" in caplog.text and "327" in caplog.text
    # The remedy has to be in the message: whoever reads the layer needs to know
    # dissolving on stand_lbl recovers one feature per stand.
    assert "stand_lbl" in caplog.text


# ---------- impossible compactness ----------


def _geom(pp_values):
    return {
        i: {
            "area_ha": 1.0,
            "polsby_popper": v,
            "n_pixels": 100,
            "perimeter_m": 100,
        }
        for i, v in enumerate(pp_values)
    }


def test_a_normal_distribution_reports_no_violations():
    s = summarize_stand_geometry(_geom([0.10, 0.30, 0.78]), min_area_ha=0.5)
    assert s["polsby_popper_above_one"] == 0


def test_a_circle_is_the_boundary_and_is_allowed():
    """Exactly 1.0 is attainable in principle; only above it is impossible."""
    s = summarize_stand_geometry(_geom([0.5, 1.0]), min_area_ha=0.5)
    assert s["polsby_popper_above_one"] == 0


def test_values_above_one_are_counted():
    s = summarize_stand_geometry(_geom([0.2, 1.058, 1.2]), min_area_ha=0.5)
    assert s["polsby_popper_above_one"] == 2


def test_the_impossible_values_are_not_clamped_away():
    """A clamp would put a plausible 1.0 in the output and delete the only
    evidence that area and perimeter disagree. The count is the finding."""
    s = summarize_stand_geometry(_geom([0.2, 1.058]), min_area_ha=0.5)
    assert s["polsby_popper_max"] == 1.058


def test_the_warning_says_it_is_geometrically_impossible(caplog):
    with caplog.at_level("WARNING"):
        summarize_stand_geometry(_geom([0.2, 1.058]), min_area_ha=0.5)
    assert "1.058" in caplog.text
    assert "planar" in caplog.text


def test_no_warning_for_a_clean_distribution(caplog):
    with caplog.at_level("WARNING"):
        summarize_stand_geometry(_geom([0.2, 0.5, 0.78]), min_area_ha=0.5)
    assert "Polsby-Popper" not in caplog.text


def test_an_empty_partition_still_short_circuits():
    assert summarize_stand_geometry({}, min_area_ha=1.0) == {"n_stands": 0}

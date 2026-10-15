"""The parts of odisha_script/odisha_read_back_export.py that need no Earth Engine."""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "odisha_script" / "odisha_read_back_export.py"


def _load():
    spec = importlib.util.spec_from_file_location("odisha_read_back_export", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _polygon(lat: float, lon: float, **props) -> dict:
    ring = [[lon, lat], [lon + 0.001, lat], [lon + 0.001, lat + 0.001], [lon, lat + 0.001], [lon, lat]]
    return {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring]},
            "properties": {"centroid_lat": lat, "centroid_lon": lon, **props}}


def test_renumber_goes_north_first_then_west_as_the_export_stage_does():
    mod = _load()
    # Two parts read one after the other, each numbered 1..n by the stage on its own.
    part_a = [_polygon(20.50, 85.20, stand_id=1, stand_lbl=7), _polygon(20.40, 85.10, stand_id=2, stand_lbl=8)]
    part_b = [_polygon(20.60, 85.30, stand_id=1, stand_lbl=3), _polygon(20.50, 85.10, stand_id=2, stand_lbl=4)]
    out = mod.renumber(part_a + part_b, "stand_id", 1_000_000)
    assert [(f["properties"]["stand_id"], f["properties"]["stand_lbl"]) for f in out] == [(1, 3), (2, 4), (3, 7), (4, 8)]
    # The unit a polygon belongs to is not touched.
    assert sorted(f["properties"]["stand_lbl"] for f in out) == [3, 4, 7, 8]


def test_layer_counts_give_polygons_units_and_units_in_pieces():
    mod = _load()
    features = [_polygon(1, 1, stand_lbl=5), _polygon(2, 2, stand_lbl=5), _polygon(3, 3, stand_lbl=6)]
    assert mod.layer_counts(features, "stand_lbl") == {"n_features": 3, "n_stands": 2, "n_stands_split_into_pieces": 1}
    assert mod.layer_counts(features, None) == {"n_features": 3, "n_stands": None, "n_stands_split_into_pieces": None}


def test_compare_layer_is_equal_for_the_same_polygons_in_another_order():
    mod = _load()
    mine = [_polygon(20.5, 85.2, stand_id=1, area_ha=1.5, cluster_id=2.0), _polygon(20.4, 85.1, stand_id=2, area_ha=2.0, cluster_id=None)]
    theirs = [dict(f, properties=dict(f["properties"])) for f in reversed(mine)]
    theirs[0]["properties"]["area_ha"] = 2.0 + 1e-9   # a rounding difference is not a difference
    report = mod.compare_layer(mine, theirs, "stand_id")
    assert report["equal"] and report["polygons"] == {"read_back": 2, "in_the_file": 2}


def test_compare_layer_counts_a_property_an_outline_and_a_missing_polygon():
    mod = _load()
    mine = [_polygon(20.5, 85.2, stand_id=1, cluster_id=2.0), _polygon(20.4, 85.1, stand_id=2, cluster_id=1.0),
            _polygon(20.3, 85.0, stand_id=3, cluster_id=1.0)]
    theirs = [_polygon(20.5, 85.2, stand_id=1, cluster_id=3.0),          # another type
              _polygon(20.4, 85.1005, stand_id=2, cluster_id=1.0)]        # moved, so centroid and outline differ
    report = mod.compare_layer(mine, theirs, "stand_id")
    assert not report["equal"]
    assert report["numbers_only_in_one"] == 1
    assert report["polygons_with_a_property_that_differs"] == 2
    assert report["polygons_whose_outline_differs"] == 1
    assert report["examples"][0] == [1, ["cluster_id"]]


def test_drive_exports_are_read_from_a_wrapped_log():
    mod = _load()
    log = """
[02:46:10] INFO       submitted raster Drive export:
                    task_id=NSYZMFUGZUT2FAPQHG4MF6BW, folder='fmu_exports_odisha_squares',
                    file='site_cluster_labels.tif'
[02:46:20] INFO       submitted vector Drive export: task_id=GZHL, folder='fmu_exports_odisha_squares', file='site_stands_merged.geojson'
           INFO     nothing to see here
"""
    assert mod.drive_exports_in_log(log) == {
        "site_cluster_labels.tif": {"folder": "fmu_exports_odisha_squares", "task_id": "NSYZMFUGZUT2FAPQHG4MF6BW", "kind": "raster"},
        "site_stands_merged.geojson": {"folder": "fmu_exports_odisha_squares", "task_id": "GZHL", "kind": "vector"},
    }

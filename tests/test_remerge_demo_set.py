"""The parts of scripts/remerge_demo_set.py that need no Earth Engine.

The tool itself reads saved assets and is run by hand (docs/demo/remerge/README.md). What is
tested here is the arithmetic it rests on: the stand raster from the merge's table, the checks
against a run's own record and exported layer, the type of a stand from a type raster, the elbow,
and the table of results.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest
from affine import Affine

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import remerge_demo_set as rm  # noqa: E402

NODATA = rm.NODATA


def _square(x0: float, y0: float, size: float = 1.0) -> dict:
    ring = [[x0, y0], [x0 + size, y0], [x0 + size, y0 + size], [x0, y0 + size], [x0, y0]]
    return {"type": "Polygon", "coordinates": [ring]}


def _feature(stand: float, cluster_id: float | None, area_ha: float, geometry: dict) -> dict:
    props = {"stand_lbl": stand, "area_ha": area_ha}
    if cluster_id is not None:
        props["cluster_id"] = cluster_id
    return {"type": "Feature", "geometry": geometry, "properties": props}


# ---------------------------------------------------------------------------
# stand_raster
# ---------------------------------------------------------------------------


def test_stand_raster_maps_each_superpixel_to_its_stand_and_counts_unseen_labels():
    labels = np.array([[10, 10, 20], [30, 30, 99], [30, 77, 77]])
    valid = np.array([[True, True, True], [True, True, True], [True, False, False]])
    stands, unseen = rm.stand_raster(labels, valid, raw_labels=[10, 20, 30], assignment=[5, 5, 8])
    assert stands.tolist() == [[5, 5, 5], [8, 8, NODATA], [8, NODATA, NODATA]]
    # Label 99 is valid on the raster but the merge never saw it: one pixel, reported.
    assert unseen == 1


def test_stand_raster_rejects_a_table_of_unequal_lengths():
    with pytest.raises(ValueError):
        rm.stand_raster(np.zeros((1, 1), int), np.ones((1, 1), bool), raw_labels=[1, 2], assignment=[1])


# ---------------------------------------------------------------------------
# compare_records
# ---------------------------------------------------------------------------


def _record(n_stands: int = 2, mean: float = 0.5) -> dict:
    diagnostics = {k: 0 for k in rm.PINNED_DIAGNOSTICS}
    diagnostics["n_stands"] = n_stands
    return {"merge_diagnostics": diagnostics,
            "stand_attributes": {1: {"n_pixels": 120, "mean_ndvi": mean}, 2: {"n_pixels": 300, "mean_ndvi": 0.25}}}


def test_compare_records_equal_whether_stand_ids_are_numbers_or_strings():
    mine, theirs = _record(), _record()
    theirs["stand_attributes"] = {str(k): v for k, v in theirs["stand_attributes"].items()}
    got = rm.compare_records(mine, theirs)
    assert got["equal"] and got["totals_equal"] and got["same_stand_ids"]
    assert got["stand_values_that_differ"] == 0 and got["largest_difference"] == 0.0


def test_compare_records_reports_a_total_and_a_stand_value_that_differ():
    got = rm.compare_records(_record(n_stands=2, mean=0.5), _record(n_stands=3, mean=0.6))
    assert not got["equal"] and not got["totals_equal"]
    assert got["totals_that_differ"] == {"n_stands": [2, 3]}
    assert got["stand_values_that_differ"] == 1
    assert got["examples"] == [["1", "mean_ndvi", 0.5, 0.6]]
    assert got["largest_difference"] == pytest.approx(0.1)


def test_compare_records_tolerance_is_on_the_difference():
    assert rm.compare_records(_record(mean=0.5), _record(mean=0.5 + 5e-10))["equal"]
    assert not rm.compare_records(_record(mean=0.5), _record(mean=0.5 + 5e-9))["equal"]


def test_compare_records_notices_a_stand_that_only_one_side_has():
    theirs = _record()
    theirs["stand_attributes"][3] = {"n_pixels": 10, "mean_ndvi": 0.1}
    got = rm.compare_records(_record(), theirs)
    assert not got["equal"] and not got["same_stand_ids"]
    assert (got["stands_mine"], got["stands_theirs"]) == (2, 3)


# ---------------------------------------------------------------------------
# stands_on_grid
# ---------------------------------------------------------------------------


def test_stands_on_grid_looks_up_the_stand_under_each_pixel_centre():
    # Stands on a 10 m UTM grid (zone 45N): the left half is stand 1, the right half stand 2.
    utm = Affine(10, 0, 300000, 0, -10, 2400000)
    stands = np.full((20, 20), 1, dtype=np.int32)
    stands[:, 10:] = 2
    stands[0, 0] = NODATA
    # Another grid, in degrees, laid over the same ground and a little beyond it.
    from pyproj import Transformer

    to_lonlat = Transformer.from_crs(32645, 4326, always_xy=True)
    west, north = to_lonlat.transform(300000 - 50, 2400000 + 50)
    east, south = to_lonlat.transform(300000 + 250, 2400000 - 250)
    n = 30
    geo = Affine((east - west) / n, 0, west, 0, (south - north) / n, north)
    got = rm.stands_on_grid(stands, utm, 32645, (n, n), geo, 4326)

    to_utm = Transformer.from_crs(4326, 32645, always_xy=True)
    seen = set()
    for row in range(n):
        for col in range(n):
            lon, lat = geo * (col + 0.5, row + 0.5)
            x, y = to_utm.transform(lon, lat)
            c, r = int(np.floor((x - 300000) / 10)), int(np.floor((2400000 - y) / 10))
            want = stands[r, c] if 0 <= r < 20 and 0 <= c < 20 else NODATA
            assert got[row, col] == want, (row, col)
            seen.add(int(want))
    assert seen == {NODATA, 1, 2}


# ---------------------------------------------------------------------------
# types_by_mode, typing_agreement
# ---------------------------------------------------------------------------


def test_types_by_mode_takes_the_commonest_type_and_ignores_untyped_pixels():
    stands = np.array([[1, 1, 1, 2, 2], [1, 3, 3, 2, NODATA]])
    types = np.array([[4, 4, 0, 255, 255], [255, 2, 3, 255, 1]], dtype=np.uint8)
    got = rm.types_by_mode(stands, types, untyped=255)
    # Stand 1: two pixels of type 4, one of type 0, one untyped. Stand 2: no typed pixel.
    # Stand 3: a tie between 2 and 3, the smaller wins. The pixel outside every stand is ignored.
    assert got == {1: 4, 2: None, 3: 2}


def test_renumbering_agreement_is_one_when_only_the_numbers_differ():
    a = [0, 0, 1, 1, 2, 2]
    b = [5, 5, 3, 3, 0, 0]
    got = rm.renumbering_agreement(a, b)
    assert got == {"compared": 6, "same_numbers": 0, "same_after_best_renumbering": 6,
                   "differ_after_best_renumbering": 0, "adjusted_rand_index": 1.0}


def test_renumbering_agreement_counts_what_no_renumbering_can_fix():
    # Type 0 of `a` splits over two types of `b`: one of the six items cannot be matched.
    got = rm.renumbering_agreement([0, 0, 0, 1, 1, 1], [7, 7, 8, 8, 8, 8])
    assert got["same_after_best_renumbering"] == 5 and got["differ_after_best_renumbering"] == 1
    assert 0 < got["adjusted_rand_index"] < 1
    # More types on one side than on the other is allowed.
    assert rm.renumbering_agreement([0, 1, 2, 3], [0, 0, 1, 1])["same_after_best_renumbering"] == 2


def test_renumbering_agreement_with_nothing_to_compare_and_with_unequal_lengths():
    assert rm.renumbering_agreement([], [])["compared"] == 0
    assert rm.renumbering_agreement([], [])["adjusted_rand_index"] is None
    with pytest.raises(ValueError):
        rm.renumbering_agreement([1, 2], [1])


def test_type_pixel_check_compares_the_pixels_typed_in_both():
    live = np.array([0, 0, 1, 1, 255, 2, 255])
    saved = np.array([3, 3, 4, 4, 255, 255, 1])
    got = rm.type_pixel_check(live, saved)
    assert got["pixels_typed_in_both"] == 4 and got["pixels_typed_in_one_only"] == 2
    assert got["pixels_whose_type_number_differs"] == 4
    assert got["up_to_renumbering"]["differ_after_best_renumbering"] == 0


def test_typing_agreement_compares_groupings_not_type_numbers():
    a = np.array([0, 0, 1, 1, 2, 2, 255])
    b = np.array([5, 5, 3, 3, 0, 0, 255])
    both = a != 255
    assert rm.typing_agreement(a, b, both) == {"pixels_typed_in_both": 6, "adjusted_rand_index": 1.0}
    assert rm.typing_agreement(a, b, np.zeros(7, bool)) == {"pixels_typed_in_both": 0, "adjusted_rand_index": None}


# ---------------------------------------------------------------------------
# knee, elbow
# ---------------------------------------------------------------------------


def _phase3_knee():
    spec = importlib.util.spec_from_file_location(
        "odisha_phase3_2_stand_k_elbow", REPO / "odisha_script" / "odisha_phase3_2_stand_k_elbow.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.knee


def test_knee_is_the_phase_3_definition():
    theirs = _phase3_knee()
    rng = np.random.default_rng(7)
    ks = list(rm.K_RANGE)
    for _ in range(50):
        inertia = sorted(rng.uniform(1, 100, size=len(ks)).tolist(), reverse=True)
        assert rm.knee(ks, inertia) == theirs(ks, inertia)
    assert rm.knee([2, 3, 4, 5, 6], [100.0, 40.0, 10.0, 8.0, 7.0]) == 4


def test_elbow_finds_the_number_of_well_separated_groups():
    rng = np.random.default_rng(3)
    centres = np.array([[0.0, 0.0], [10.0, 0.0], [0.0, 10.0], [10.0, 10.0]])
    rows = np.vstack([c + rng.normal(0, 0.3, size=(30, 2)) for c in centres])
    got = rm.elbow(rows)
    assert got["rows"] == 120 and got["ks"] == list(rm.K_RANGE)
    assert got["elbow_k"] == 4
    assert all(a >= b for a, b in zip(got["inertia"], got["inertia"][1:], strict=False))


def test_elbow_with_too_few_rows_gives_no_k():
    got = rm.elbow(np.array([[0.0], [1.0], [2.0], [3.0]]))
    assert got["ks"] == [2, 3] and got["elbow_k"] is None


# ---------------------------------------------------------------------------
# exported_types, compare_layers
# ---------------------------------------------------------------------------


def test_exported_types_reads_noisy_floats_missing_types_and_split_stands():
    features = [
        _feature(1.0, 2.9999999, 2.0, _square(0, 0)),
        _feature(2.0, None, 1.5, _square(1, 0)),
        # Stand 3 in two pieces that disagree: the larger piece gives the type.
        _feature(3.0, 1.0, 0.2, _square(2, 0)),
        _feature(3.0, 4.0, 2.5, _square(3, 0)),
    ]
    assert rm.exported_types(features) == {1: 3, 2: None, 3: 4}


def _layer() -> list[dict]:
    return [
        _feature(1, 3.0, 2.0, _square(0, 0)),
        _feature(2, None, 1.5, _square(1, 0)),
        _feature(3, 4.0, 0.2, _square(2, 0)),
        _feature(3, 4.0, 2.5, _square(3, 1)),
    ]


def test_compare_layers_equal_for_the_same_layer_in_another_order():
    got = rm.compare_layers(_layer(), list(reversed(_layer())))
    assert got["equal"]
    assert got["features"] == {"mine": 4, "theirs": 4}
    assert got["stands"] == {"mine": 3, "theirs": 3, "only_in_mine": 0, "only_in_theirs": 0}


def test_compare_layers_counts_a_type_an_area_and_an_outline_that_differ():
    theirs = _layer()
    theirs[0]["properties"]["cluster_id"] = 1.0            # stand 1: another type
    theirs[1]["properties"]["area_ha"] = 1.6               # stand 2: another area
    theirs[2]["geometry"] = _square(2.25, 0)               # stand 3: one piece moved
    got = rm.compare_layers(_layer(), theirs)
    assert not got["equal"]
    assert got["stands_whose_type_differs"] == 1 and got["examples_of_a_different_type"] == [[1, 3, 1]]
    assert got["stands_whose_area_differs"] == 1
    assert got["stands_whose_outline_differs"] == 1
    assert got["stands_whose_number_of_pieces_differs"] == 0


def test_compare_layers_tells_a_renumbering_from_a_different_grouping():
    def layer(types: dict[int, float | None]) -> list[dict]:
        return [_feature(s, t, 1.0, _square(s, 0)) for s, t in types.items()]

    mine = layer({1: 0.0, 2: 0.0, 3: 1.0, 4: 1.0, 5: None})
    renumbered = layer({1: 1.0, 2: 1.0, 3: 0.0, 4: 0.0, 5: None})
    got = rm.compare_layers(mine, renumbered)
    assert got["stands_whose_type_differs"] == 4          # by number, every typed stand
    assert got["stand_types_up_to_renumbering"]["differ_after_best_renumbering"] == 0
    assert got["stands_typed_in_one_layer_only"] == 0
    assert rm.types_reproduce(got) and not got["equal"]

    regrouped = layer({1: 0.0, 2: 1.0, 3: 1.0, 4: 1.0, 5: 0.0})
    got = rm.compare_layers(mine, regrouped)
    assert got["stand_types_up_to_renumbering"] == {
        "compared": 4, "same_numbers": 3, "same_after_best_renumbering": 3,
        "differ_after_best_renumbering": 1, "adjusted_rand_index": got["stand_types_up_to_renumbering"]["adjusted_rand_index"]}
    assert got["stands_typed_in_one_layer_only"] == 1     # stand 5 has a type in one layer only
    assert not rm.types_reproduce(got)


def test_compare_layers_notices_a_missing_stand_and_a_stand_in_fewer_pieces():
    theirs = [f for f in _layer() if f["properties"]["stand_lbl"] != 2][:-1]
    got = rm.compare_layers(_layer(), theirs)
    assert not got["equal"]
    assert got["stands"]["only_in_mine"] == 1 and got["stands"]["only_in_theirs"] == 0
    assert got["stands_whose_number_of_pieces_differs"] == 1


# ---------------------------------------------------------------------------
# summary_table
# ---------------------------------------------------------------------------


def _summary(run_id: str, reproduces: bool, plots: dict | None) -> dict:
    return {
        "run_id": run_id, "k": 5,
        "old_rule_check": {
            "reproduces": reproduces, "types_reproduce": reproduces,
            "layer": {"stands_typed_in_one_layer_only": 0 if reproduces else 2,
                      "stand_types_up_to_renumbering": {"compared": 173, "adjusted_rand_index": 1.0 if reproduces else 0.44,
                                                        "differ_after_best_renumbering": 0 if reproduces else 29}}},
        "stands": {"old": 180, "new": 198},
        "change": {"share_area_changed": 0.165, "area_ha_changed": 66.7, "area_ha_total": 404.4},
        "plots": plots,
        "elbow": {"old": {"elbow_k": 6}, "new": {"elbow_k": 6}},
    }


def test_summary_table_has_one_row_per_run_in_run_id_order():
    table = rm.summary_table([
        _summary("b_run", False, None),
        _summary("a_run", True, {"changed_stand": 0, "in_a_stand": 8}),
    ])
    lines = table.strip().split("\n")
    assert len(lines) == 4 and lines[1].startswith("|---")
    assert lines[2] == "| `a_run` | yes | yes (173 stands) | 180 to 198 | 16.5% (66.7 of 404.4 ha) | 0 of 8 | 5 | 6 / 6 |"
    assert lines[3] == ("| `b_run` | **NO** | no: 29 of 173 stands differ, 2 typed in one only (ARI 0.44) | 180 to 198 | "
                        "16.5% (66.7 of 404.4 ha) | no field plots | 5 | 6 / 6 |")


def test_types_table_says_what_was_live_and_how_many_stands_each_fit_counted():
    a = _summary("a_run", True, None)
    a["old_rule_check"]["saved_fit"] = {"n_units_total": 215}
    a["stands"]["old"] = 215
    a["old_rule_check"]["layer"]["type_pixels_against_the_saved_type_raster"] = {"up_to_renumbering": {"adjusted_rand_index": 1.0}}
    b = _summary("b_run", False, None)
    b["old_rule_check"]["saved_fit"] = {"n_units_total": 102}
    b["stands"]["old"] = 97
    b["old_rule_check"]["layer"]["type_pixels_against_the_saved_type_raster"] = {"up_to_renumbering": {"adjusted_rand_index": 0.4167}}
    routes = [
        {"config": "a_run", "runs": [{"inputs": {"masking/habitat_mask": "hit", "features_static/static_features": "hit"}}]},
        {"config": "b_run", "runs": [{"inputs": {"masking/habitat_mask": "hit"}},
                                     {"inputs": {"features_optical/optical_features": "miss-exported",
                                                 "features_structure/structure_features": "miss-exported",
                                                 "masking/habitat_mask": "hit"}}]},
    ]
    lines = rm.types_table([b, a], routes).strip().split("\n")
    assert lines[2] == "| `a_run` | nothing (all read from the cache) | 215 | 215 | 0 of 173 | 1.00 |"
    assert lines[3] == "| `b_run` | `optical_features`, `structure_features` | 102 | 97 | 29 of 173 | 0.42 |"
    # A run whose route or saved fit is not known says so.
    del b["old_rule_check"]["saved_fit"]
    assert "| not recorded | not read |" in rm.types_table([b], [])


# ---------------------------------------------------------------------------
# The committed results: docs/demo/remerge/
# ---------------------------------------------------------------------------

RESULTS = REPO / "docs" / "demo" / "remerge"


def _committed_summaries() -> list[dict]:
    import json

    return [json.loads(p.read_text()) for p in sorted(RESULTS.glob("*_repro.json"))]


def test_the_results_page_shows_the_tables_the_tool_prints_from_the_committed_files():
    import json

    summaries = _committed_summaries()
    demo = json.loads((REPO / "docs" / "demo" / "demo_set.json").read_text())
    hull_runs = sorted(r["run_id"] for r in demo["runs"] if r["run_id"].endswith("_repro"))
    assert sorted(s["run_id"] for s in summaries) == hull_runs
    readme = (RESULTS / "README.md").read_text()
    assert rm.summary_table(summaries) in readme
    assert rm.types_table(summaries, json.loads(rm.CLUSTERING_ROUTE.read_text())) in readme


def test_the_committed_summaries_hold_results_only_and_submitted_nothing():
    for s in _committed_summaries():
        assert s["export_tasks_submitted"] == 0, s["run_id"]
        assert not {"date", "command_line", "git", "seconds", "run_time"} & set(s), s["run_id"]
        check = s["old_rule_check"]
        # The two verdicts are what their parts say, not a value written by hand.
        assert check["reproduces"] == bool(
            check["record"]["equal"] and check["pixels"]["same_partition"]
            and check["pixels"]["pixels_in_another_stand"] == 0), s["run_id"]
        assert check["types_reproduce"] == rm.types_reproduce(check["layer"]), s["run_id"]

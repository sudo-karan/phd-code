"""Offline tests of scripts/stand_types_from_fit_rows.py on a made-up run of three stands."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import box, mapping
from shapely.ops import transform

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import stand_types_from_fit_rows as script  # noqa: E402

EPSG = 32645
X0, Y0 = 300000.0, 2300000.0
TO_LL = Transformer.from_crs(EPSG, 4326, always_xy=True).transform


def _square(col: int, row: int, w: int = 1, h: int = 1):
    """w x h pixels of 10 m, lower left at pixel (col, row) of the grid."""
    return box(X0 + 10 * col, Y0 + 10 * row, X0 + 10 * (col + w), Y0 + 10 * (row + h))


def _write(path: Path, features: list[tuple[dict, object]]) -> None:
    path.write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": props, "geometry": mapping(transform(TO_LL, geom))}
        for props, geom in features]}))


def _run(tmp_path: Path, monkeypatch, stands, superpixels, excludes: bool = False) -> dict:
    run = "made_up_run"
    _write(tmp_path / f"{run}_stands_merged.geojson", stands)
    _write(tmp_path / f"{run}_stands_snic.geojson", superpixels)
    _write(tmp_path / f"{run}_stands_dissolved.geojson", [({"unit_id": 1, "cluster_id": 1}, _square(0, 0, 8, 2))])
    (tmp_path / f"{run}_run.json").write_text(json.dumps({"stand_provenance": {
        "1": {"below_min": 0}, "2": {"below_min": 1}, "3": {"below_min": 0}}}))
    monkeypatch.setattr(script, "grid_epsg", lambda r: EPSG)
    monkeypatch.setattr(script, "fit_excludes", lambda r: excludes)
    return script.count(run, tmp_path)


def test_a_stand_whose_own_superpixels_agree_with_its_type_does_not_change(tmp_path, monkeypatch):
    got = _run(tmp_path, monkeypatch,
               stands=[({"stand_lbl": 1, "cluster_id": 1}, _square(0, 0, 4, 2))],
               superpixels=[({"snic_label": 11, "cluster_id": 1}, _square(0, 0, 2, 2)),
                            ({"snic_label": 12, "cluster_id": 1}, _square(2, 0, 2, 2))])
    assert got["stands_that_would_change_type"] == 0
    assert got["typed_stands_checked"] == 1 and got["typed_stands_unchecked"] == 0
    assert got["vertices_off_the_grid"] == 0 and got["type_image_vertices_off_the_grid"] == 0


def test_a_polygon_outvoted_by_a_neighbour_would_change_and_a_neighbours_superpixel_is_not_counted(
    tmp_path, monkeypatch
):
    """Stand 2's exported type is 3 but its own superpixel says 2: it would change. Stand 3's
    superpixel lies wholly in stand 3, though it shares an edge with stand 2."""
    got = _run(tmp_path, monkeypatch,
               stands=[({"stand_lbl": 2, "cluster_id": 3}, _square(0, 0, 2, 2)),
                       ({"stand_lbl": 3, "cluster_id": 3}, _square(2, 0, 2, 2))],
               superpixels=[({"snic_label": 21, "cluster_id": 2}, _square(0, 0, 2, 2)),
                            ({"snic_label": 31, "cluster_id": 3}, _square(2, 0, 2, 2))])
    assert got["stands_that_would_change_type"] == 1
    assert got["changed_stand_labels"] == [2]
    assert got["left_out_stands_whose_type_is_not_their_own"] == 0


def test_a_stand_left_out_of_the_fit_is_counted_apart(tmp_path, monkeypatch):
    """With the setting on, stand 2 (below the minimum) keeps the vote in the export, so it
    does not count as changing; it is counted apart."""
    got = _run(tmp_path, monkeypatch, excludes=True,
               stands=[({"stand_lbl": 2, "cluster_id": 3}, _square(0, 0, 2, 2)),
                       ({"stand_lbl": 3, "cluster_id": 3}, _square(2, 0, 2, 2))],
               superpixels=[({"snic_label": 21, "cluster_id": 2}, _square(0, 0, 2, 2)),
                            ({"snic_label": 31, "cluster_id": 3}, _square(2, 0, 2, 2))])
    assert got["stands_that_would_change_type"] == 0
    assert got["stands_left_out_of_the_fit"] == 1
    assert got["left_out_stands_whose_type_is_not_their_own"] == 1


def test_pieces_of_different_types_count_the_minority_piece(tmp_path, monkeypatch):
    """A stand in two pieces, 4 pixels of type 4 and 1 of type 3: one polygon would change."""
    got = _run(tmp_path, monkeypatch,
               stands=[({"stand_lbl": 1, "cluster_id": 4}, _square(0, 0, 2, 2)),
                       ({"stand_lbl": 1, "cluster_id": 3}, _square(5, 0))],
               superpixels=[({"snic_label": 11, "cluster_id": 4}, _square(0, 0, 2, 2)),
                            ({"snic_label": 12, "cluster_id": 3}, _square(5, 0))])
    assert got["stands_in_several_pieces_of_different_types"] == 1
    assert got["stands_that_would_change_type"] == 1
    assert got["polygons_that_would_change_type"] == 1


def test_a_vertex_off_the_grid_is_counted(tmp_path, monkeypatch):
    shifted = box(X0 + 5, Y0, X0 + 25, Y0 + 20)
    got = _run(tmp_path, monkeypatch,
               stands=[({"stand_lbl": 1, "cluster_id": 1}, shifted)],
               superpixels=[({"snic_label": 11, "cluster_id": 1}, shifted)])
    assert got["vertices_off_the_grid"] > 0
    assert 4.9 < got["largest_vertex_offset_m"] < 5.1

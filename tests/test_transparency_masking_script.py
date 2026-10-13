"""Fast tests for the parts of scripts/transparency_masking.py that need neither
Earth Engine nor matplotlib: naming the parts of a ROI, tabulating a saved
reason raster by pixel area, classifying points from a raster, and building the
summary text from numbers. Rasters are small synthetic ones written to tmp_path.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import transparency_masking as tm  # noqa: E402

from fmu.stages.masking import MaskingStage  # noqa: E402

D = tm.pixel_size_deg(10)
# A 6-row, 8-column grid, anchored on the origin grid near 21.6 N.
COL0, ROW0 = 950_000, 240_000
LEFT, TOP = COL0 * D, ROW0 * D
H, W = 6, 8
TRANSFORM = from_origin(LEFT, TOP, D, D)


def _write(path: Path, bands: list[np.ndarray], nodata: int = tm.NODATA) -> Path:
    with rasterio.open(
        path, "w", driver="GTiff", height=H, width=W, count=len(bands), dtype="uint8",
        crs="EPSG:4326", transform=TRANSFORM, nodata=nodata,
    ) as dst:
        for i, band in enumerate(bands, start=1):
            dst.write(band.astype("uint8"), i)
    return path


def _cells(col0: int, row0: int, col1: int, row1: int):
    """The polygon covering whole cells [col0, col1) x [row0, row1) of the grid."""
    return box(LEFT + col0 * D, TOP - row1 * D, LEFT + col1 * D, TOP - row0 * D)


def _layers() -> tuple[dict, dict]:
    reason, source = (layer.to_manifest() for layer in MaskingStage.display_layers)
    return reason, source


@pytest.fixture
def rasters(tmp_path: Path) -> dict[str, Path]:
    """Left half kept, then cropland, built-up, water columns; one row decided by WorldCover."""
    reason = np.full((H, W), 1)
    reason[:, 4:6] = 2
    reason[:, 6] = 3
    reason[:, 7] = 4
    source = np.full((H, W), 1)
    source[0, :] = 2
    habitat = (reason == 1).astype(int)
    return {
        "mask_provenance": _write(tmp_path / "p_mask_provenance.tif", [reason, source]),
        "habitat_mask": _write(tmp_path / "p_habitat_mask.tif", [habitat]),
    }


# ----------------------------------------------------------------- naming parts
def test_single_polygon_feature_takes_its_name():
    roi = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"name": "the_park"},
         "geometry": json.loads(json.dumps(box(0, 0, 1, 1).__geo_interface__))}]}
    parts = tm.roi_parts(roi)
    assert [p.name for p in parts] == ["the_park"]
    assert parts[0].slug == "part01_the_park"


def test_multipolygon_parts_named_from_the_parts_list_with_the_given_key():
    geom = {"type": "MultiPolygon", "coordinates": [
        box(0, 0, 1, 1).__geo_interface__["coordinates"],
        box(2, 0, 3, 1).__geo_interface__["coordinates"],
    ]}
    roi = {"type": "FeatureCollection", "features": [{
        "type": "Feature", "geometry": geom,
        "properties": {"name": "whole", "parts": [{"places": ["A B"]}, {"places": ["C", "D"]}]},
    }]}
    parts = tm.roi_parts(roi, name_key="places")
    assert [p.name for p in parts] == ["A B", "C + D"]
    assert [p.slug for p in parts] == ["part01_a_b", "part02_c_d"]
    # Without the key the file carries no name for the parts: they are numbered.
    assert [p.name for p in tm.roi_parts(roi)] == ["part 1", "part 2"]


def test_unnamed_and_repeated_names_stay_distinct():
    feature = {"type": "Feature", "properties": {"name": "same"},
               "geometry": box(0, 0, 1, 1).__geo_interface__}
    bare = {"type": "Feature", "properties": {}, "geometry": box(5, 5, 6, 6).__geo_interface__}
    parts = tm.roi_parts({"type": "FeatureCollection", "features": [feature, feature, bare]})
    assert [p.name for p in parts] == ["same (1)", "same (2)", "part 3"]
    assert len({p.slug for p in parts}) == 3


def test_bare_geometry_and_non_polygon():
    assert len(tm.roi_parts(box(0, 0, 1, 1).__geo_interface__)) == 1
    with pytest.raises(ValueError, match="polygonal"):
        tm.roi_parts({"type": "Point", "coordinates": [0, 0]})


def test_roi_outline_keeps_every_part():
    parts = tm.roi_parts(box(0, 0, 1, 1).__geo_interface__)
    outline = tm.roi_outline_geojson(parts)
    assert [f["properties"]["part"] for f in outline["features"]] == ["part 1"]


# ----------------------------------------------------------------- the grid
def test_snapped_bounds_land_on_the_origin_grid_and_contain_the_input():
    bounds = (LEFT + 0.3 * D, TOP - 5.2 * D, LEFT + 7.1 * D, TOP - 0.4 * D)
    minx, miny, maxx, maxy = tm.snapped_bounds(bounds, 10, pad_pixels=0)
    for value in (minx, miny, maxx, maxy):
        assert abs(value / D - round(value / D)) < 1e-6
    assert minx <= bounds[0] and miny <= bounds[1] and maxx >= bounds[2] and maxy >= bounds[3]
    assert round((maxx - minx) / D) == 8 and round((maxy - miny) / D) == 6


def test_pixel_area_is_smaller_than_scale_squared_away_from_the_equator():
    areas = tm.row_pixel_area_m2(TRANSFORM, H)
    assert areas.shape == (H,)
    # 10 m tall, 10 m x cos(latitude) wide; latitude is about 21.56 N.
    assert areas == pytest.approx(100 * np.cos(np.radians(21.56)), rel=0.01)


# ----------------------------------------------------------------- tabulating
def test_tabulate_part_shares_by_area(rasters):
    table = tm.tabulate_part(rasters["mask_provenance"], rasters["habitat_mask"],
                             _cells(0, 0, W, H))
    assert table["share_kept"] == pytest.approx(0.5, abs=1e-4)
    assert table["share_by_reason"]["cropland"] == pytest.approx(0.25, abs=1e-4)
    assert table["share_by_reason"]["built_up"] == pytest.approx(0.125, abs=1e-4)
    assert table["share_by_reason"]["water"] == pytest.approx(0.125, abs=1e-4)
    assert sum(table["share_by_reason"].values()) == pytest.approx(1.0, abs=1e-5)
    assert table["share_decided_by_source"]["worldcover"] == pytest.approx(1 / 6, abs=1e-3)
    assert table["share_kept_by_source"]["worldcover"] == pytest.approx(0.5 / 6, abs=1e-3)
    assert table["area_ha_reason_disagrees_with_habitat_mask"] == 0.0
    expected_ha = tm.row_pixel_area_m2(TRANSFORM, H).sum() * W / 1e4
    assert table["area_ha"] == pytest.approx(expected_ha, abs=1e-4)


def test_tabulate_part_counts_only_pixels_inside_the_part(rasters):
    # Columns 4..7 only: cropland, cropland, built-up, water.
    table = tm.tabulate_part(rasters["mask_provenance"], rasters["habitat_mask"],
                             _cells(4, 0, W, H))
    assert table["share_kept"] == 0.0
    assert table["share_by_reason"]["cropland"] == pytest.approx(0.5, abs=1e-4)


def test_disagreement_with_the_mask_is_measured_and_kept_follows_the_mask(tmp_path, rasters):
    with rasterio.open(rasters["habitat_mask"]) as ds:
        habitat = ds.read(1)
    habitat[:, 0] = 0  # the cached mask dropped a column the reason layer keeps
    stale = _write(tmp_path / "stale_habitat_mask.tif", [habitat])
    table = tm.tabulate_part(rasters["mask_provenance"], stale, _cells(0, 0, W, H))
    assert table["share_by_reason"]["kept"] == pytest.approx(0.5, abs=1e-4)
    assert table["share_kept"] == pytest.approx(3 / 8, abs=1e-4)
    assert table["area_ha_reason_disagrees_with_habitat_mask"] == pytest.approx(
        table["area_ha"] / 8, abs=1e-3
    )


def test_pixels_without_a_value_are_not_counted(tmp_path, rasters):
    with rasterio.open(rasters["mask_provenance"]) as ds:
        reason, source = ds.read(1), ds.read(2)
    reason[:, 4:], source[:, 4:] = tm.NODATA, tm.NODATA
    cut = _write(tmp_path / "cut_mask_provenance.tif", [reason, source])
    table = tm.tabulate_part(cut, rasters["habitat_mask"], _cells(0, 0, W, H))
    assert table["share_kept"] == pytest.approx(1.0)


def test_blank_untouched_writes_no_data_outside_the_part_and_keeps_the_edge():
    # What a download of a clipped image looks like: 0 outside the clip, and 0
    # is a legend value ("no land-cover data", "not habitat").
    downloaded = np.zeros((2, H, W), dtype=np.uint8)
    downloaded[:, 1:5, 2:6] = 1
    # A part covering cells [2, 6) x [1, 5), grown by a third of a pixel: the
    # ring of pixels around it is touched by the outline, centres outside.
    part = _cells(2, 1, 6, 5).buffer(D / 3)
    out = tm.blank_untouched(downloaded, part, TRANSFORM, tm.NODATA)
    assert (out[:, 1:5, 2:6] == 1).all()
    assert (out[:, 0, 1:7] == 0).all() and (out[:, 1:5, 1] == 0).all()  # touched: kept as sent
    assert (out[:, :, 0] == tm.NODATA).all() and (out[:, :, 7] == tm.NODATA).all()
    assert (downloaded != tm.NODATA).all()  # the input is not changed


def test_a_raster_blanked_outside_the_part_tabulates_the_part_only(tmp_path):
    reason = np.zeros((H, W), dtype=np.uint8)
    reason[1:5, 2:6] = 1
    reason[1:5, 5] = 2
    part = _cells(2, 1, 6, 5)
    both = tm.blank_untouched(np.stack([reason, (reason > 0).astype(np.uint8)]), part,
                              TRANSFORM, tm.NODATA)
    habitat = tm.blank_untouched((reason == 1).astype(np.uint8)[None], part, TRANSFORM, tm.NODATA)
    assert set(np.unique(both[0])) == {1, 2, tm.NODATA}
    prov = _write(tmp_path / "b_mask_provenance.tif", [both[0], both[1]])
    hab = _write(tmp_path / "b_habitat_mask.tif", [habitat[0]])
    # Tabulated over the whole grid, only the part's 16 pixels count: no
    # "no land-cover data" area appears from outside it.
    table = tm.tabulate_part(prov, hab, _cells(0, 0, W, H))
    assert table["share_kept"] == pytest.approx(0.75, abs=1e-4)
    assert table["share_by_reason"]["no_data"] == 0.0
    assert table["area_ha"] == pytest.approx(
        tm.row_pixel_area_m2(TRANSFORM, H)[1:5].sum() * 4 / 1e4, abs=1e-4)


def test_area_by_key_rejects_mismatched_shapes():
    a = np.zeros((2, 2), dtype=np.uint8)
    with pytest.raises(ValueError, match="one shape"):
        tm.area_by_key(a, a, np.zeros((3, 2), dtype=np.uint8), a.astype(bool), np.ones(2))


def test_pooled_weights_parts_by_area():
    got = tm.pooled([{"area_ha": 100.0, "share_kept": 1.0}, {"area_ha": 300.0, "share_kept": 0.0}])
    assert got == {"area_ha": 400.0, "share_kept": 0.25}


# ----------------------------------------------------------------- points
def _centre(col: int, row: int) -> tuple[float, float]:
    return LEFT + (col + 0.5) * D, TOP - (row + 0.5) * D


def test_classify_points_from_rasters(rasters):
    part = tm.RoiPart(0, "only", "p", _cells(0, 0, W, H))
    reason_layer, source_layer = _layers()
    points = [
        {"id": "kept_wc", "lon": _centre(1, 0)[0], "lat": _centre(1, 0)[1]},
        {"id": "crop", "lon": _centre(4, 3)[0], "lat": _centre(4, 3)[1]},
        {"id": "built", "lon": _centre(6, 5)[0], "lat": _centre(6, 5)[1]},
        {"id": "far", "lon": LEFT - 1.0, "lat": TOP + 1.0},
    ]
    got = {r["id"]: r for r in tm.classify_points(
        points, [part], {"p": rasters["mask_provenance"]}, {"p": rasters["habitat_mask"]},
        tm.legend_labels(reason_layer), tm.legend_labels(source_layer))}
    assert got["kept_wc"]["kept"] is True
    assert got["kept_wc"]["source_name"] == "worldcover"
    assert got["crop"]["kept"] is False
    assert (got["crop"]["reason_code"], got["crop"]["reason_name"]) == (2, "cropland")
    assert got["crop"]["reason_label"] == "Removed: cropland"
    assert got["crop"]["source_label"] == "IndiaSAT decided"
    assert got["built"]["reason_name"] == "built_up"
    assert got["far"]["in_roi"] is False and got["far"]["kept"] is None
    assert got["far"]["part"] is None and got["far"]["reason_code"] is None
    # The 5 x 5 around (col 4, row 3): columns 2..6, of which 2 and 3 are kept.
    assert (got["crop"]["window_kept"], got["crop"]["window_pixels"]) == (10, 25)
    # At the top-left the window is cut by the raster's edge: 3 rows x 4 columns.
    assert (got["kept_wc"]["window_kept"], got["kept_wc"]["window_pixels"]) == (12, 12)
    assert got["far"]["window_pixels"] is None
    counts = tm.count_points(list(got.values()))
    assert counts == {"given": 4, "in_roi": 3, "outside_roi": 1, "kept": 1, "dropped": 2,
                      "no_value": 0}
    geo = tm.points_geojson(list(got.values()))
    assert len(geo["features"]) == 4
    assert geo["features"][0]["properties"]["part"] == "only"


def test_a_point_on_a_pixel_without_a_value_is_reported_as_such(tmp_path, rasters):
    with rasterio.open(rasters["mask_provenance"]) as ds:
        reason, source = ds.read(1), ds.read(2)
    reason[2, 2], source[2, 2] = tm.NODATA, tm.NODATA
    cut = _write(tmp_path / "cut_mask_provenance.tif", [reason, source])
    part = tm.RoiPart(0, "only", "p", _cells(0, 0, W, H))
    reason_layer, source_layer = _layers()
    lon, lat = _centre(2, 2)
    neighbour = _centre(3, 2)
    got = tm.classify_points(
        [{"id": "edge", "lon": lon, "lat": lat},
         {"id": "next", "lon": neighbour[0], "lat": neighbour[1]}],
        [part], {"p": cut}, {"p": rasters["habitat_mask"]},
        tm.legend_labels(reason_layer), tm.legend_labels(source_layer))
    assert got[0]["in_roi"] is True and got[0]["kept"] is None and got[0]["reason_code"] is None
    assert tm.count_points(got)["no_value"] == 1
    # The neighbour's window leaves the valueless pixel out of both counts.
    assert got[1]["kept"] is True and got[1]["window_pixels"] == 24


def test_read_points_carries_extra_columns_and_rejects_bad_input(tmp_path):
    path = tmp_path / "pts.csv"
    path.write_text("key,x,y,village\na,85.1,21.5,V1\nb,85.2,21.6,V2\n")
    points = tm.read_points(path, "key", "x", "y")
    assert points[0] == {"id": "a", "lon": 85.1, "lat": 21.5, "attributes": {"village": "V1"}}
    with pytest.raises(ValueError, match="no column"):
        tm.read_points(path, "id", "x", "y")
    path.write_text("key,x,y\na,1,2\na,3,4\n")
    with pytest.raises(ValueError, match="not unique"):
        tm.read_points(path, "key", "x", "y")


# ----------------------------------------------------------------- summary text
def _numbers(rasters) -> dict:
    numbers = tm.tabulate_part(rasters["mask_provenance"], rasters["habitat_mask"],
                               _cells(0, 0, W, H))
    numbers["kept_classes"] = {"indiasat": [6, 12], "worldcover": [10, 20, 30]}
    return numbers


def _transparency(numbers: dict) -> dict:
    reason, source = _layers()
    return {"display_layers": [reason, source],
            "summary_numbers": [{"name": k, "value": v} for k, v in numbers.items()]}


def test_summary_values_and_display_layer_read_the_manifest_record(rasters):
    record = _transparency(_numbers(rasters))
    assert tm.summary_values(record)["share_kept"] == pytest.approx(0.5, abs=1e-4)
    assert tm.display_layer(record, "mask_provenance", "source")["band"] == "source"
    with pytest.raises(KeyError):
        tm.display_layer(record, "mask_provenance", "nope")
    with pytest.raises(RuntimeError, match="summary failed"):
        tm.summary_values({"summary_error": "timed out"})
    with pytest.raises(RuntimeError, match="no summary numbers"):
        tm.summary_values({"summary_numbers": []})


def _summary_kwargs(numbers: dict, **over) -> dict:
    reason_layer, source_layer = _layers()
    kwargs = dict(
        config_name="demo", config_path="configs/demo.yaml", roi_file="aois/demo.geojson",
        fingerprint="abc123", numbers=numbers, reason_layer=reason_layer,
        source_layer=source_layer, layer_status={}, part_tables=[("only", numbers)],
        points=None, map_files=["habitat_mask.png"],
    )
    kwargs.update(over)
    return kwargs


def _one_map(numbers: dict) -> dict:
    """The same numbers with IndiaSAT deciding everything, as on every site so far."""
    return dict(
        numbers,
        share_decided_by_source={"none": 0.0, "indiasat": 1.0, "worldcover": 0.0},
        share_kept_by_source={"none": 0.0, "indiasat": numbers["share_kept"], "worldcover": 0.0},
    )


def test_summary_markdown_states_the_numbers_and_the_habitat_sentence(rasters):
    numbers = _numbers(rasters)
    reason_layer, _ = _layers()
    points = [
        {"id": "p1", "lon": 0, "lat": 0, "in_roi": True, "part": "north", "kept": True,
         "reason_label": "Kept", "source_label": "IndiaSAT decided", "attributes": {},
         "window_kept": 25, "window_pixels": 25},
        {"id": "p2", "lon": 0, "lat": 0, "in_roi": True, "part": "south", "kept": False,
         "reason_label": "Removed: cropland", "source_label": "IndiaSAT decided",
         "attributes": {}, "window_kept": 23, "window_pixels": 25},
        {"id": "p3", "lon": 0, "lat": 0, "in_roi": False, "part": None, "kept": None,
         "reason_label": None, "source_label": None, "attributes": {}},
    ]
    text = tm.summary_markdown(**_summary_kwargs(
        numbers,
        layer_status={"habitat_mask": "hit", "mask_provenance": "miss"},
        part_tables=[("north", numbers), ("south", numbers)], points=points,
        map_files=["habitat_mask_sheet1of2.png", "habitat_mask_sheet2of2.png"],
        notes=["A note."], roi_notes=["A box around the site."], scale_m=10.0,
        comparisons=[{"label": "x/masking/habitat_mask__old", "area_ha": 10.0,
                      "area_ha_differs": 0.0, "share_differs": 0.0}],
        stretch={"low": 200.0, "high": 1500.0, "gamma": 0.75, "percentiles": [1.0, 99.0],
                 "bands": ["B4_median", "B3_median", "B2_median"]},
    ))
    assert text.startswith("# Habitat mask: demo\n")
    # The result first, in plain words, largest reason first.
    lead = text.split("\n")[2]
    assert "keeps 50.0% of it as habitat and removes the rest: cropland 25.0%, " in lead
    assert "Of the 3 points given, 2 are inside the ROI: 1 on a kept pixel and 1 on a removed" in lead
    assert "1 lies outside the ROI and is not on the map." in lead
    assert reason_layer["legend_note"] in text
    assert "not a strict forest mask" in text and "docs/design_notes.md" in text
    assert "| Kept as habitat (not only forest) | 50.0% |" in text
    assert "| Removed: cropland | 25.0% |" in text
    # Two maps decided here, so the table says how much each.
    assert "| Share of the area. WorldCover decided (IndiaSAT has no data) | 16.7% |" in text
    assert "Check against the cached mask: 0.0 ha." in text
    assert "zero by construction" not in text
    assert "`habitat_mask`, the mask the rest of the pipeline uses: read from the cached asset" in text
    assert "the reason and deciding-map layer: computed live" in text
    assert "## By part" in text and "| north |" in text and "| south |" in text
    assert "3 points given, 2 inside the ROI: 1 kept, 1 dropped. 1 outside the ROI." in text
    assert "by the single 10 m pixel it falls on" in text
    assert "| `p2` | south | Removed: cropland | IndiaSAT decided | 23 of 25 |" in text
    assert "Outside the ROI, so not on the map and not counted above: `p3`." in text
    assert "- A note." in text
    assert 'says of itself: "A box around the site."' in text
    assert "differs over 0.00 ha" in text
    assert "linear stretch, from 200 to 1500" in text
    assert "cache fingerprint `abc123`" in text.split("## For the record")[1]


def test_summary_markdown_is_free_of_dates_and_the_same_every_time(rasters):
    kwargs = _summary_kwargs(_numbers(rasters))
    first, second = tm.summary_markdown(**kwargs), tm.summary_markdown(**kwargs)
    assert first == second
    assert "## By part" not in first and "## Points" not in first
    import datetime as dt

    assert str(dt.date.today().year) not in first


def test_summary_says_so_when_the_mask_was_not_read_from_the_cache(rasters):
    # Both layers computed in the run: their agreement is no check of anything.
    text = tm.summary_markdown(**_summary_kwargs(_numbers(rasters), layer_status={}))
    assert "zero by construction" in text
    assert "Check against the cached mask" not in text


def test_summary_is_short_where_one_map_decided_everything(rasters):
    numbers = _one_map(_numbers(rasters))
    text = tm.summary_markdown(**_summary_kwargs(
        numbers, part_tables=[("north", numbers), ("south", numbers)]))
    assert tm.one_source_decided(numbers) and not tm.one_source_decided(_numbers(rasters))
    assert "Share of the area." not in text and "Kept as habitat, where" not in text
    assert "IndiaSAT decided: 100.0% of the area. So every kept pixel" in text
    header = next(line for line in text.splitlines() if line.startswith("| Part |"))
    assert header == "| Part | Area | Kept | cropland | built-up | water | other non-habitat |"
    assert "No part has a pixel without land-cover data." in text
    # The kept share is given once in the table, not once per layer.
    whole = text.split("## Whole ROI")[1].split("## By part")[0]
    assert whole.count("| 50.0% |") == 1


def test_summary_shows_both_kept_shares_when_the_layers_disagree(rasters):
    numbers = dict(_numbers(rasters), area_ha_reason_disagrees_with_habitat_mask=1.5,
                   share_kept=0.4)
    text = tm.summary_markdown(**_summary_kwargs(numbers, layer_status={"habitat_mask": "hit"}))
    assert "| Kept as habitat (not only forest) | 40.0% |" in text
    assert "| Kept according to the reason layer computed in this run | 50.0% |" in text
    assert "Check against the cached mask: 1.5 ha." in text


def test_points_take_the_name_they_are_given_and_the_title_is_plain(rasters):
    points = [{"id": "a", "lon": 0, "lat": 0, "in_roi": True, "part": "only", "kept": False,
               "reason_label": "Removed: cropland", "source_label": "IndiaSAT decided",
               "attributes": {}, "window_kept": 2, "window_pixels": 25}]
    text = tm.summary_markdown(**_summary_kwargs(
        _numbers(rasters), points=points, point_noun="field plot", title="A district: the mask"))
    assert text.startswith("# A district: the mask\n")
    assert "## Field plots" in text and "Dropped field plots:" in text
    assert "Of the 1 field plot given, 1 is inside the ROI" in text
    assert "| Field plot | Part | Reason |" in text
    assert "name `demo`" in text  # the config is still named, in the record section


def test_roi_file_notes_are_read_from_the_file():
    geom = box(0, 0, 1, 1).__geo_interface__
    roi = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"note": " A box. "}, "geometry": geom},
        {"type": "Feature", "properties": {"note": "A box."}, "geometry": geom},
        {"type": "Feature", "properties": {}, "geometry": geom}]}
    assert tm.roi_file_notes(roi) == ["A box."]
    assert tm.roi_file_notes(geom) == []


def test_absent_reason_codes_are_those_no_pixel_has():
    reason_layer, _ = _layers()
    got = tm.absent_reason_codes([np.array([1, 2, 2]), np.array([3])], reason_layer["legend"])
    assert got == [0, 4, 5]
    assert tm.absent_reason_codes([], reason_layer["legend"]) == [0, 1, 2, 3, 4, 5]


def test_git_blob_id_is_the_id_git_gives_the_content(tmp_path):
    path = tmp_path / "f.txt"
    path.write_bytes(b"hello\n")
    # `printf 'hello\n' | git hash-object --stdin`
    assert tm.git_blob_id(path) == "ce013625030ba8dba906f756967f9e9ca394464a"
    record = tm.code_record([Path(tm.__file__)])
    assert list(record) == ["scripts/transparency_masking.py"]


def test_decided_sentence_names_only_the_maps_that_decided(rasters):
    _, source_layer = _layers()
    labels = tm.legend_labels(source_layer)
    numbers = _numbers(rasters)
    sentence = tm.decided_sentence(numbers, labels)
    assert "IndiaSAT decided: 83.3% of the area" in sentence
    assert "WorldCover decided (IndiaSAT has no data): 16.7% of the area" in sentence
    assert "Neither" not in sentence
    only = dict(numbers, share_decided_by_source={"none": 0.0, "indiasat": 1.0, "worldcover": 0.0})
    assert tm.decided_sentence(only, labels) == (
        "Which map decided. IndiaSAT decided: 100.0% of the area."
    )


# ----------------------------------------------------------------- map helpers
def test_sheets_fill_evenly_and_files_are_named_for_them():
    assert tm.sheet_groups(1) == [[0]]
    assert tm.sheet_groups(4) == [[0, 1, 2, 3]]
    assert tm.sheet_groups(7) == [[0, 1, 2, 3], [4, 5, 6]]
    assert [len(g) for g in tm.sheet_groups(9)] == [3, 3, 3]
    assert tm.sheet_groups(0) == []
    assert tm.map_file_names(4) == ["habitat_mask.png"]
    assert tm.map_file_names(8) == ["habitat_mask_sheet1of2.png", "habitat_mask_sheet2of2.png"]


def test_stretch_is_one_range_for_all_bands_and_stays_in_0_1():
    rgb = np.array([[[200.0, 400.0, 800.0], [1600.0, 100.0, 5000.0]]])
    low, high = tm.stretch_limits(np.linspace(100, 2100, 201), (0.0, 100.0))
    assert (low, high) == (100.0, 2100.0)
    out = tm.stretch_rgb(rgb, low, high, gamma=1.0)
    assert out.min() >= 0.0 and out.max() <= 1.0
    assert out[0, 0, 1] == pytest.approx(0.15) and out[0, 1, 2] == 1.0
    assert tm.stretch_rgb(rgb, low, high, gamma=0.5)[0, 0, 1] > out[0, 0, 1]
    assert tm.stretch_limits(np.zeros(5)) == (0.0, 1.0)


def test_scale_bar_is_a_round_length_under_a_third_of_the_width():
    assert tm.scale_bar_metres(3000) == 1000
    assert tm.scale_bar_metres(1700) == 500
    assert tm.scale_bar_metres(650) == 200
    assert tm.scale_bar_metres(40) == 10


def test_colour_image_uses_the_legend_and_is_clear_outside():
    reason_layer, _ = _layers()
    codes = np.array([[1, 2], [3, 1]], dtype=np.uint8)
    inside = np.array([[True, True], [True, False]])
    rgba = tm.colour_image(codes, reason_layer["legend"], inside)
    kept = next(e["color"] for e in reason_layer["legend"] if e["value"] == 1)
    assert rgba[0, 0, :3] == pytest.approx([int(kept[i:i + 2], 16) / 255 for i in (0, 2, 4)])
    assert rgba[0, 0, 3] == 1.0 and rgba[1, 1, 3] == 0.0


def test_true_colour_bands_are_found_whatever_the_reducer_suffix():
    names = ["B1_median", "B2_median", "B3_median", "B4_median", "B8_median", "B11_median"]
    assert tm.true_colour_bands(names) == ["B4_median", "B3_median", "B2_median"]
    assert tm.true_colour_bands(["B2", "B3", "B4"]) == ["B4", "B3", "B2"]
    with pytest.raises(ValueError, match="B4"):
        tm.true_colour_bands(["B2", "B3"])


def test_arguments_for_plain_words_and_the_default_command_line():
    args = tm.parse_args(["--config", "c.yaml", "--title", "T", "--map-note", "m1",
                          "--map-note", "m2", "--point-noun", "field plot"])
    assert (args.title, args.map_note, args.point_noun) == ("T", ["m1", "m2"], "field plot")
    plain = tm.parse_args(["--config", "c.yaml"])
    assert (plain.title, plain.map_note, plain.point_noun) == (None, None, "point")


def test_the_module_does_not_import_matplotlib_at_the_top():
    source = (Path(__file__).parent.parent / "scripts" / "transparency_masking.py").read_text()
    top_level = [line for line in source.splitlines() if line.startswith(("import ", "from "))]
    assert not any("matplotlib" in line or "geopandas" in line for line in top_level)

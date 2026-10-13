"""scripts/raster_vector_tools.py on small hand-built arrays, where the answer can be worked
out by hand.

Offline and fast: no Earth Engine, no network, no files beyond tmp_path. The UTM rasters sit
in zone 45N near 21.6 N 85.4 E on a 10 m grid, as the stand rasters of the pipeline do; the
EPSG:4326 ones use the pipeline's pixel of 10 m / 111319.49 m per degree.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pytest
import rasterio
import shapely
from affine import Affine
from PIL import Image
from pyproj import Transformer
from rasterio.features import rasterize
from shapely.geometry import MultiPolygon, Point, Polygon, shape

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import raster_vector_tools as rvt  # noqa: E402
import transparency_masking as tm  # noqa: E402

UTM = "EPSG:32645"
# The upper-left corner of the UTM test rasters: 21.6 N 85.4 E, snapped to the 10 m grid.
_E, _N = Transformer.from_crs(4326, UTM, always_xy=True).transform(85.4, 21.6)
X0, Y0 = round(_E / 10) * 10.0, round(_N / 10) * 10.0
UTM_TRANSFORM = Affine(10.0, 0.0, X0, 0.0, -10.0, Y0)
D = tm.pixel_size_deg(10)
DEG_TRANSFORM = Affine(D, 0.0, 950_600 * D, 0.0, -D, 240_450 * D)  # 85.39 E, 21.60 N
PIXEL_HA = 0.01

# 4 rows by 5 columns. Label 7 is two pixels touching at a corner (rows 0 and 1); label -3
# (superpixel labels can be negative) is two blobs that do not touch; label 2 fills the rest.
LABELS = np.array(
    [
        [7, 2, 2, -3, -3],
        [2, 7, 2, 2, 2],
        [2, 2, 2, 2, 2],
        [-3, -3, 2, 2, 2],
    ],
    dtype=np.int32,
)
ALL = np.ones(LABELS.shape, dtype=bool)


def _lonlat(x: float, y: float) -> tuple[float, float]:
    return Transformer.from_crs(UTM, 4326, always_xy=True).transform(x, y)


# --------------------------------------------------------------------------- reading
def test_read_raster_one_band_and_several(tmp_path):
    one = tmp_path / "stands.tif"
    with rasterio.open(
        one, "w", driver="GTiff", height=4, width=5, count=1, dtype="int32", crs=UTM,
        transform=UTM_TRANSFORM, nodata=-1,
    ) as dst:
        dst.write(LABELS, 1)
        dst.set_band_description(1, "stand_clusters")
    array, transform, crs, nodata, names = rvt.read_raster(one)
    assert array.shape == (4, 5) and array.dtype == np.int32
    assert np.array_equal(array, LABELS)
    assert transform == UTM_TRANSFORM
    assert crs.to_epsg() == 32645
    assert nodata == -1
    assert names == ("stand_clusters",)

    two = tmp_path / "features.tif"
    bands = np.stack([LABELS, LABELS * 2]).astype("float32")
    with rasterio.open(
        two, "w", driver="GTiff", height=4, width=5, count=2, dtype="float32", crs="EPSG:4326",
        transform=DEG_TRANSFORM,
    ) as dst:
        dst.write(bands)
        dst.set_band_description(2, "ndvi")
    raster = rvt.read_raster(two)
    assert raster.array.shape == (2, 4, 5)
    assert np.array_equal(raster.array, bands)
    assert raster.nodata is None
    assert raster.descriptions == (None, "ndvi")


# --------------------------------------------------------------------------- polygons
@pytest.mark.parametrize("connectivity", [4, 8])
def test_vectorise_areas_add_up(connectivity):
    geoms = rvt.vectorise_labels(LABELS, UTM_TRANSFORM, UTM, valid=ALL, connectivity=connectivity)
    assert list(geoms) == [-3, 2, 7]  # one geometry per label, in label order
    counts = rvt.pixel_counts(LABELS, ALL)
    assert counts == {-3: 4, 2: 14, 7: 2}
    for label, geom in geoms.items():
        assert geom.is_valid
        assert geom.area == pytest.approx(counts[label] * 100.0)  # 10 m pixels: 100 m2 each
    assert sum(g.area for g in geoms.values()) == pytest.approx(LABELS.size * 100.0)
    # together the geometries are the raster's rectangle, with no overlap between them
    union = shapely.union_all(list(geoms.values()))
    assert union.equals(shapely.box(X0, Y0 - 40, X0 + 50, Y0))


@pytest.mark.parametrize("connectivity", [4, 8])
def test_vectorise_two_pixels_touching_at_a_corner(connectivity):
    geom = rvt.vectorise_labels(LABELS, UTM_TRANSFORM, UTM, valid=ALL, connectivity=connectivity)[7]
    assert geom.is_valid
    assert isinstance(geom, MultiPolygon) and len(geom.geoms) == 2
    assert geom.area == pytest.approx(200.0)
    expected = MultiPolygon(
        [shapely.box(X0, Y0 - 10, X0 + 10, Y0), shapely.box(X0 + 10, Y0 - 20, X0 + 20, Y0 - 10)]
    )
    assert geom.equals(expected)


def test_vectorise_one_label_in_two_separate_blobs():
    geom = rvt.vectorise_labels(LABELS, UTM_TRANSFORM, UTM, valid=ALL)[-3]
    assert isinstance(geom, MultiPolygon) and len(geom.geoms) == 2
    expected = MultiPolygon(
        [shapely.box(X0 + 30, Y0 - 10, X0 + 50, Y0), shapely.box(X0, Y0 - 40, X0 + 20, Y0 - 30)]
    )
    assert geom.equals(expected)


def test_vectorise_follows_pixel_edges_exactly():
    geoms = rvt.vectorise_labels(LABELS, UTM_TRANSFORM, UTM, valid=ALL)
    for geom in geoms.values():
        xy = shapely.get_coordinates(geom)
        assert np.array_equal(xy, np.round(xy / 10.0) * 10.0)  # every vertex on a pixel corner


def test_vectorise_then_rasterise_gives_the_labels_back():
    rng = np.random.default_rng(3)
    # blocky random labels with awkward values, a hole of invalid pixels and an invalid rim
    coarse = rng.choice(np.array([-2_000_000_000, -1, 0, 5, 2_000_000_000]), size=(6, 9))
    labels = np.kron(coarse, np.ones((3, 2), dtype=np.int64)).astype(np.int32)
    labels[rng.random(labels.shape) < 0.15] = 9
    valid = np.ones(labels.shape, dtype=bool)
    valid[7:10, 5:9] = False
    valid[0, :] = False
    valid[rng.random(labels.shape) < 0.05] = False

    geoms = rvt.vectorise_labels(labels, UTM_TRANSFORM, UTM, valid=valid)
    assert set(geoms) == set(np.unique(labels[valid]).tolist())
    assert sum(g.area for g in geoms.values()) == pytest.approx(valid.sum() * 100.0)

    # labels can be any int32, so paint each geometry's position in the list, not its label
    order = list(geoms)
    painted = rasterize(
        [(geoms[label], k + 1) for k, label in enumerate(order)], out_shape=labels.shape,
        transform=UTM_TRANSFORM, fill=0, all_touched=False, dtype="int32",
    )
    assert np.array_equal(painted > 0, valid)
    back = np.array(order, dtype=np.int64)[painted[valid] - 1]
    assert np.array_equal(back, labels[valid])


def test_vectorise_leaves_invalid_pixels_out_and_accepts_wider_integers():
    valid = LABELS != 2
    geoms = rvt.vectorise_labels(LABELS.astype(np.int64), UTM_TRANSFORM, valid=valid)
    assert list(geoms) == [-3, 7]
    with pytest.raises(ValueError, match="int32"):
        rvt.vectorise_labels(LABELS.astype(np.int64) * 2**31, UTM_TRANSFORM, valid=ALL)
    with pytest.raises(TypeError):
        rvt.vectorise_labels(LABELS.astype(float), UTM_TRANSFORM, valid=ALL)
    with pytest.raises(ValueError, match="connectivity"):
        rvt.vectorise_labels(LABELS, UTM_TRANSFORM, valid=ALL, connectivity=6)


def test_vectorise_on_a_degree_grid():
    geoms = rvt.vectorise_labels(LABELS, DEG_TRANSFORM, "EPSG:4326", valid=ALL)
    assert sum(g.area for g in geoms.values()) == pytest.approx(LABELS.size * D * D)


def test_to_lonlat_converts_every_vertex_at_full_precision():
    geom = rvt.vectorise_labels(LABELS, UTM_TRANSFORM, UTM, valid=ALL)[7]
    out = rvt.to_lonlat(geom, UTM)
    assert out.geom_type == "MultiPolygon" and out.is_valid
    before, after = shapely.get_coordinates(geom), shapely.get_coordinates(out)
    assert before.shape == after.shape
    lon, lat = Transformer.from_crs(UTM, 4326, always_xy=True).transform(before[:, 0], before[:, 1])
    assert np.array_equal(after, np.column_stack([lon, lat]))
    # the raster's corner is the point it was built from, to the 10 m snap
    assert after[:, 0].min() == pytest.approx(85.4, abs=1e-4)
    assert after[:, 1].max() == pytest.approx(21.6, abs=1e-4)
    # a rasterio CRS object (what read_raster returns) works as well as a string
    same = rvt.to_lonlat(geom, rasterio.crs.CRS.from_epsg(32645))
    assert np.allclose(shapely.get_coordinates(same), after, rtol=0, atol=1e-12)
    # longitude and latitude in, the same out
    assert rvt.to_lonlat(Point(85.4, 21.6), "EPSG:4326").equals(Point(85.4, 21.6))


# --------------------------------------------------------------------------- comparing
A = np.array(
    [
        [0, 0, 1, 1, 2],
        [0, 0, 1, 1, 2],
    ]
)


def test_partition_report_relabelled_but_equal():
    b = np.array([[40, 40, -7, -7, 9], [40, 40, -7, -7, 9]])
    report = rvt.partition_report(A, b, np.ones(A.shape, dtype=bool))
    assert report == {
        "n_pixels": 10, "n_labels_a": 3, "n_labels_b": 3, "identical_labels": False,
        "same_partition": True, "pixels_not_in_matching_sets": 0, "n_mismatches": 0,
        "examples": [],
    }
    same = rvt.partition_report(A, A.copy(), None)
    assert same["identical_labels"] is True and same["same_partition"] is True


def test_partition_report_on_a_split():
    # stand 1 of a (4 pixels) is two labels in b: 3 pixels under 1 and 1 pixel under 5
    b = np.array([[0, 0, 1, 1, 2], [0, 0, 1, 5, 2]])
    report = rvt.partition_report(A, b, np.ones(A.shape, dtype=bool))
    assert report["n_labels_a"] == 3 and report["n_labels_b"] == 4
    assert report["identical_labels"] is False
    assert report["same_partition"] is False
    assert report["pixels_not_in_matching_sets"] == 4
    assert report["n_mismatches"] == 2
    assert report["examples"] == [[1, 1, 3], [1, 5, 1]]  # the largest overlap first


def test_partition_report_on_a_merge():
    # stands 1 and 2 of a (4 and 2 pixels) are one label in b
    b = np.array([[0, 0, 8, 8, 8], [0, 0, 8, 8, 8]])
    report = rvt.partition_report(A, b, np.ones(A.shape, dtype=bool))
    assert report["n_labels_a"] == 3 and report["n_labels_b"] == 2
    assert report["same_partition"] is False
    assert report["pixels_not_in_matching_sets"] == 6
    assert report["examples"] == [[1, 8, 4], [2, 8, 2]]


def test_partition_report_same_number_of_labels_is_not_enough():
    # three labels each, but the line between two of them has moved by one pixel
    b = np.array([[0, 0, 1, 2, 2], [0, 0, 1, 1, 2]])
    report = rvt.partition_report(A, b, np.ones(A.shape, dtype=bool))
    assert report["n_labels_a"] == report["n_labels_b"] == 3
    assert report["same_partition"] is False
    assert report["pixels_not_in_matching_sets"] == 6  # stands 1 and 2, whole
    assert report["examples"] == [[1, 1, 3], [2, 2, 2], [1, 2, 1]]


def test_partition_report_ignores_invalid_pixels_and_caps_the_examples():
    b = A.copy()
    b[0, 4] = 99  # differs only on a pixel that does not count
    valid = np.ones(A.shape, dtype=bool)
    valid[0, 4] = False
    report = rvt.partition_report(A, b, valid)
    assert report["n_pixels"] == 9 and report["same_partition"] is True

    one = np.zeros(60, dtype=np.int64)
    many = np.arange(60)
    report = rvt.partition_report(one, many, None)
    assert report["n_mismatches"] == 60 and len(report["examples"]) == rvt.MAX_EXAMPLES
    assert report["pixels_not_in_matching_sets"] == 60

    empty = rvt.partition_report(A, b, np.zeros(A.shape, dtype=bool))
    assert empty["n_pixels"] == 0 and empty["same_partition"] is True

    with pytest.raises(ValueError, match="shape"):
        rvt.partition_report(A, b[:, :4], None)


# Old map: stand 0 (4 pixels), stand 1 (4 pixels), stand 2 (2 pixels); see A above.
# New map: stand 0 as it was; old stand 1 cut into 3 pixels (still 1) and 1 pixel (new id 3);
# old stand 2 with the same pixels under another number (7).
NEW = np.array(
    [
        [0, 0, 1, 1, 7],
        [0, 0, 1, 3, 7],
    ]
)


def test_change_report_hand_worked():
    report = rvt.change_report(A, NEW, np.ones(A.shape, dtype=bool), PIXEL_HA)
    assert report["n_old"] == 3
    assert report["n_new"] == 4
    assert report["n_unchanged"] == 2  # stand 0, and stand 2 = new 7 (renumbered only)
    assert report["n_pixels"] == 10
    assert report["n_pixels_changed"] == 4  # the 4 pixels of old stand 1
    assert report["area_ha_total"] == pytest.approx(0.10)
    assert report["area_ha_changed"] == pytest.approx(0.04)
    assert report["share_area_changed"] == pytest.approx(0.4)
    # old -> new: stand 0 IoU 1 (weight 4); stand 1 best match new 1, 3 common of 4 together
    # = 0.75 (weight 4); stand 2 IoU 1 (weight 2).  (4 + 3 + 2) / 10 = 0.9
    assert report["area_weighted_iou_old_to_new"] == pytest.approx(0.9)
    # new -> old: new 0 IoU 1 (weight 4); new 1 = 3/4 (weight 3); new 3 = 1/4 (weight 1);
    # new 7 IoU 1 (weight 2).  (4 + 2.25 + 0.25 + 2) / 10 = 0.85
    assert report["area_weighted_iou_new_to_old"] == pytest.approx(0.85)
    # everything in a report is a plain number, so it can go straight into a JSON file
    assert json.loads(json.dumps(report)) == report


def test_change_report_halves_score_a_half_both_ways_as_in_compare_stand_runs():
    old = np.zeros((2, 4), dtype=np.int32)
    new = np.array([[0, 0, 1, 1], [0, 0, 1, 1]], dtype=np.int32)
    report = rvt.change_report(old, new, None, PIXEL_HA)
    assert report["n_unchanged"] == 0 and report["share_area_changed"] == 1.0
    assert report["area_weighted_iou_old_to_new"] == pytest.approx(0.5)
    assert report["area_weighted_iou_new_to_old"] == pytest.approx(0.5)


def test_change_report_nothing_changed_and_nothing_valid():
    same = rvt.change_report(A, A + 100, None, PIXEL_HA)
    assert same["n_unchanged"] == 3 and same["n_pixels_changed"] == 0
    assert same["share_area_changed"] == 0.0
    assert same["area_weighted_iou_old_to_new"] == 1.0
    assert same["area_weighted_iou_new_to_old"] == 1.0

    none = rvt.change_report(A, NEW, np.zeros(A.shape, dtype=bool), PIXEL_HA)
    assert none["n_pixels"] == 0 and none["area_ha_total"] == 0.0
    assert none["share_area_changed"] is None
    assert none["area_weighted_iou_old_to_new"] is None


def test_changed_mask_marks_whole_stands():
    valid = np.ones(A.shape, dtype=bool)
    assert np.array_equal(
        rvt.changed_mask(A, NEW, valid),
        np.array([[0, 0, 1, 1, 0], [0, 0, 1, 1, 0]], dtype=bool),
    )
    valid[0, 2] = False  # an invalid pixel is never "changed"
    assert not rvt.changed_mask(A, NEW, valid)[0, 2]


# --------------------------------------------------------------------------- several parts
def test_merging_part_reports_equals_the_report_on_all_pixels():
    # a second part of the same ROI: other stand ids, one stand merged into its neighbour
    old2 = np.array([[10, 10, 11], [10, 12, 12]])
    new2 = np.array([[10, 10, 10], [10, 12, 12]])
    valid1 = np.ones(A.shape, dtype=bool)
    valid2 = np.array([[1, 1, 1], [1, 1, 0]], dtype=bool)
    parts = [(A, NEW, valid1), (old2, new2, valid2)]

    assert rvt.labels_in_several_parts([A, old2], [valid1, valid2]) == {}
    whole = rvt.change_report_parts(parts, PIXEL_HA)
    assert whole["n_parts"] == 2
    assert whole["n_old_in_several_parts"] == 0 and whole["n_new_in_several_parts"] == 0
    assert whole["n_old"] == 6 and whole["n_new"] == 6 and whole["n_pixels"] == 15

    merged = rvt.merge_part_reports(
        [rvt.change_report(old, new, valid, PIXEL_HA) for old, new, valid in parts]
    )
    for key, value in merged.items():
        assert whole[key] == pytest.approx(value), key

    # partition_report takes the stacked pixels the same way
    stacked = rvt.partition_report(*rvt.stack_parts(parts))
    assert stacked["n_pixels"] == 15 and stacked["same_partition"] is False


def test_a_stand_in_two_parts_is_found_and_counted_once():
    # stand 5 lies in both parts and is unchanged; adding the per-part reports counts it twice
    old1, new1 = np.array([[5, 5, 6]]), np.array([[5, 5, 6]])
    old2, new2 = np.array([[5, 8, 8]]), np.array([[5, 8, 9]])
    parts = [(old1, new1, None), (old2, new2, None)]
    assert rvt.labels_in_several_parts([old1, old2], [None, None]) == {5: [0, 1]}

    whole = rvt.change_report_parts(parts, PIXEL_HA)
    assert whole["n_old_in_several_parts"] == 1 and whole["n_new_in_several_parts"] == 1
    assert whole["n_old"] == 3 and whole["n_unchanged"] == 2  # stands 5 and 6

    merged = rvt.merge_part_reports(
        [rvt.change_report(old, new, valid, PIXEL_HA) for old, new, valid in parts]
    )
    assert merged["n_old"] == 4  # the double count merge_part_reports warns about
    with pytest.raises(ValueError):
        rvt.merge_part_reports([])


def test_mosaic_parts_puts_each_part_in_its_place():
    left = np.array([[1, 2], [3, 4]], dtype=np.int32)
    right = np.array([[5, 6, 7]], dtype=np.int32)
    t_left = UTM_TRANSFORM
    t_right = Affine(10.0, 0.0, X0 + 30, 0.0, -10.0, Y0 + 10)  # 3 pixels east, 1 pixel north
    right_valid = np.array([[True, False, True]])
    canvas, transform, valid = rvt.mosaic_parts(
        [left, right], [t_left, t_right], [None, right_valid], fill=-1
    )
    assert transform == Affine(10.0, 0.0, X0, 0.0, -10.0, Y0 + 10)
    assert np.array_equal(
        canvas, np.array([[-1, -1, -1, 5, -1, 7], [1, 2, -1, -1, -1, -1], [3, 4, -1, -1, -1, -1]])
    )
    assert np.array_equal(valid, canvas != -1)
    assert canvas.dtype == np.int32

    # an RGBA image per part is mosaicked the same way
    rgba, _, shown = rvt.mosaic_parts(
        [rvt.categorical_rgba(left, {1: "#ff0000"}, None), rvt.categorical_rgba(right, {7: "#0000ff"}, None)],
        [t_left, t_right],
    )
    assert rgba.shape == (3, 6, 4) and shown.sum() == 7  # 4 pixels and 3, none shared
    assert rgba[1, 0].tolist() == [255, 0, 0, 255] and rgba[0, 5].tolist() == [0, 0, 255, 255]

    with pytest.raises(ValueError, match="one grid"):
        rvt.mosaic_parts([left, right], [t_left, Affine(10.0, 0.0, X0 + 35, 0.0, -10.0, Y0)])
    with pytest.raises(ValueError, match="pixel size"):
        rvt.mosaic_parts([left, right], [t_left, Affine(20.0, 0.0, X0, 0.0, -20.0, Y0)])


def test_mosaic_parts_on_the_degree_grid():
    # two parts whose origins were each computed as a whole number of pixels times D
    a, b = np.ones((2, 2), dtype=np.uint8), np.full((2, 2), 2, dtype=np.uint8)
    t_a = Affine(D, 0.0, 950_600 * D, 0.0, -D, 240_450 * D)
    t_b = Affine(D, 0.0, 950_603 * D, 0.0, -D, 240_449 * D)
    canvas, _, valid = rvt.mosaic_parts([a, b], [t_a, t_b])
    assert canvas.shape == (3, 5)
    assert np.array_equal(canvas, np.array([[1, 1, 0, 0, 0], [1, 1, 0, 2, 2], [0, 0, 0, 2, 2]]))
    assert np.array_equal(valid, canvas > 0)


# --------------------------------------------------------------------------- sampling
GRID = np.arange(20, dtype=np.int32).reshape(4, 5)  # value = row * 5 + col


def test_sample_at_xy_centres_and_edges():
    xs = [X0 + 5, X0 + 45, X0 + 25, X0 + 20, X0, X0 + 50, X0 + 5, X0 + 5, X0 - 0.001]
    ys = [Y0 - 5, Y0 - 35, Y0 - 15, Y0 - 10, Y0, Y0 - 5, Y0 - 40, Y0 + 0.001, Y0 - 5]
    assert rvt.sample_at_xy(GRID, UTM_TRANSFORM, xs, ys) == [
        0,  # centre of the first pixel
        19,  # centre of the last
        7,  # centre of row 1, column 2
        7,  # the corner shared by four pixels belongs to the one to its lower right
        0,  # the raster's upper-left corner is inside it
        None,  # the right edge is outside
        None,  # the bottom edge is outside
        None,  # above
        None,  # left
    ]


def test_sample_at_lonlat_on_a_utm_raster():
    # pixel centres
    lon_a, lat_a = _lonlat(X0 + 5, Y0 - 5)
    lon_b, lat_b = _lonlat(X0 + 35, Y0 - 25)
    # 1 cm either side of the line between columns 1 and 2, in row 0
    lon_w, lat_w = _lonlat(X0 + 20 - 0.01, Y0 - 5)
    lon_e, lat_e = _lonlat(X0 + 20 + 0.01, Y0 - 5)
    # 1 cm either side of the line between rows 2 and 3, in column 4
    lon_n, lat_n = _lonlat(X0 + 45, Y0 - 30 + 0.01)
    lon_s, lat_s = _lonlat(X0 + 45, Y0 - 30 - 0.01)
    # 1 cm outside the right edge, and far away
    lon_o, lat_o = _lonlat(X0 + 50 + 0.01, Y0 - 5)
    values = rvt.sample_at_lonlat(
        GRID, UTM_TRANSFORM, UTM,
        [lon_a, lon_b, lon_w, lon_e, lon_n, lon_s, lon_o, 77.17],
        [lat_a, lat_b, lat_w, lat_e, lat_n, lat_s, lat_o, 28.53],
    )
    assert values == [0, 13, 1, 2, 14, 19, None, None]
    assert all(v is None or type(v) is int for v in values)  # plain numbers, not numpy ones


def test_sample_respects_valid_and_reads_all_bands():
    valid = GRID != 13
    lon_b, lat_b = _lonlat(X0 + 35, Y0 - 25)
    assert rvt.sample_at_lonlat(GRID, UTM_TRANSFORM, UTM, [lon_b], [lat_b], valid=valid) == [None]
    bands = np.stack([GRID, GRID * 10]).astype(float)
    assert rvt.sample_at_lonlat(bands, UTM_TRANSFORM, UTM, [lon_b], [lat_b]) == [[13.0, 130.0]]
    # a raster in degrees: the centre of row 1, column 3
    lon, lat = DEG_TRANSFORM * (3.5, 1.5)
    assert rvt.sample_at_lonlat(GRID, DEG_TRANSFORM, "EPSG:4326", [lon], [lat]) == [8]
    assert rvt.sample_at_lonlat(GRID, DEG_TRANSFORM, "EPSG:4326", [], []) == []


def test_sample_gives_none_for_nan():
    # NaN is "no value" here as in the colour functions, with or without a validity array
    values = GRID.astype(float)
    values[0, 0] = np.nan
    values[0, 1] = np.inf
    xs, ys = [X0 + 5, X0 + 15, X0 + 25], [Y0 - 5, Y0 - 5, Y0 - 5]
    assert rvt.sample_at_xy(values, UTM_TRANSFORM, xs, ys) == [None, np.inf, 2.0]
    # several bands: the bands that have a value keep it
    bands = np.stack([values, GRID * 10.0])
    assert rvt.sample_at_xy(bands, UTM_TRANSFORM, xs, ys) == [[None, 0.0], [np.inf, 10.0], [2.0, 20.0]]
    json.dumps(rvt.sample_at_xy(bands, UTM_TRANSFORM, xs[:1], ys[:1]), allow_nan=False)


# --------------------------------------------------------------------------- outlines
def test_outline_mask_three_by_three():
    labels = np.array([[1, 1, 2], [1, 3, 2], [4, 4, 4]])
    valid = np.ones((3, 3), dtype=bool)
    # a pixel is marked where the label to its right or below it differs
    assert np.array_equal(
        rvt.outline_mask(labels, valid),
        np.array([[0, 1, 0], [1, 1, 1], [0, 0, 0]], dtype=bool),
    )
    assert not rvt.outline_mask(np.ones((3, 3), dtype=int), valid).any()


def test_outline_mask_draws_the_rim_of_the_valid_area_on_the_valid_side():
    labels = np.ones((3, 3), dtype=int)
    valid = np.ones((3, 3), dtype=bool)
    valid[1, 1] = False
    labels[1, 1] = 99  # a label under an invalid pixel must not matter
    assert np.array_equal(
        rvt.outline_mask(labels, valid),
        np.array([[0, 1, 0], [1, 0, 1], [0, 1, 0]], dtype=bool),
    )
    assert np.array_equal(
        rvt.outline_mask(labels, valid, edge_is_boundary=True),
        np.array([[1, 1, 1], [1, 0, 1], [1, 1, 1]], dtype=bool),
    )
    # a label change across an invalid pixel is a rim, not a line between labels
    row = np.array([[1, 0, 2, 2]])
    row_valid = np.array([[True, False, True, True]])
    assert rvt.outline_mask(row, row_valid).tolist() == [[True, False, True, False]]


# --------------------------------------------------------------------------- colour
def test_categorical_rgba():
    codes = np.array([[0.0, 1.0, 2.0], [1.0, np.nan, 5.0]])
    valid = np.array([[True, True, True], [False, True, True]])
    rgba = rvt.categorical_rgba(codes, {0: "#2e7d32", 1: "#ff0000", 2: "0000ff"}, valid)
    assert rgba.dtype == np.uint8 and rgba.shape == (2, 3, 4)
    assert rgba[0, 0].tolist() == [0x2E, 0x7D, 0x32, 255]
    assert rgba[0, 1].tolist() == [255, 0, 0, 255]
    assert rgba[0, 2].tolist() == [0, 0, 255, 255]
    assert rgba[1, 0].tolist() == [0, 0, 0, 0]  # not valid
    assert rgba[1, 1].tolist() == [0, 0, 0, 0]  # NaN
    assert rgba[1, 2].tolist() == [0, 0, 0, 0]  # a code with no colour
    # whole-number codes, and the masking stage's 255 for "no pixel"
    whole = rvt.categorical_rgba(np.array([[1, 255]], dtype=np.uint8), {1: "#ffffff"}, None)
    assert whole[..., 3].tolist() == [[255, 0]]
    with pytest.raises(ValueError, match="#rrggbb"):
        rvt.categorical_rgba(codes, {0: "green"}, valid)


def test_continuous_rgba_interpolates_and_clips():
    values = np.array([[-5.0, 0.0, 7.5, 15.0], [22.5, 30.0, 99.0, np.nan]])
    valid = np.ones(values.shape, dtype=bool)
    valid[0, 1] = False
    rgba = rvt.continuous_rgba(values, 0.0, 30.0, ["#000000", "#646464", "#c800c8"], valid)
    assert rgba.dtype == np.uint8 and rgba.shape == (2, 4, 4)
    assert rgba[0, 0].tolist() == [0, 0, 0, 255]  # below vmin: the first colour
    assert rgba[0, 1].tolist() == [0, 0, 0, 0]  # not valid
    assert rgba[0, 2].tolist() == [50, 50, 50, 255]  # halfway to the middle colour
    assert rgba[0, 3].tolist() == [100, 100, 100, 255]  # the middle colour
    assert rgba[1, 0].tolist() == [150, 50, 150, 255]  # halfway from the middle to the last
    assert rgba[1, 1].tolist() == [200, 0, 200, 255]  # vmax: the last colour
    assert rgba[1, 2].tolist() == [200, 0, 200, 255]  # above vmax: clipped
    assert rgba[1, 3].tolist() == [0, 0, 0, 0]  # NaN
    two = rvt.continuous_rgba(np.array([[0.0, 15.0, 30.0]]), 0, 30, ["#f7fcf5", "#00441b"], None)
    assert two[0, 0].tolist() == [0xF7, 0xFC, 0xF5, 255] and two[0, 2].tolist() == [0, 0x44, 0x1B, 255]
    # infinity is a value beyond the limits, not a missing one: clipped, and opaque
    ends = rvt.continuous_rgba(np.array([[-np.inf, np.inf, np.nan]]), 0, 30, ["#000000", "#ffffff"], None)
    assert ends.tolist() == [[[0, 0, 0, 255], [255, 255, 255, 255], [0, 0, 0, 0]]]
    with pytest.raises(ValueError, match="vmax"):
        rvt.continuous_rgba(values, 5.0, 5.0, ["#000000", "#ffffff"], valid)


def test_rgb_rgba_stretches_each_band_between_its_limits():
    red = np.array([[0.0, 500.0, 1000.0, 2000.0]])
    green = np.array([[100.0, 100.0, np.nan, 300.0]])
    blue = np.array([[0.0, 0.0, 0.0, 50.0]])
    valid = np.array([[True, True, True, False]])
    limits = [(0.0, 1000.0), (100.0, 300.0), (0.0, 100.0)]
    rgba = rvt.rgb_rgba(red, green, blue, limits, valid)
    assert rgba.dtype == np.uint8 and rgba.shape == (1, 4, 4)
    assert rgba[0, 0].tolist() == [0, 0, 0, 255]  # opaque black, not clear
    assert rgba[0, 1].tolist() == [128, 0, 0, 255]  # 0.5 * 255 = 127.5, rounded to even
    assert rgba[0, 2].tolist() == [0, 0, 0, 0]  # NaN in one band
    assert rgba[0, 3].tolist() == [0, 0, 0, 0]  # not valid
    # gamma is the one of transparency_masking.stretch_rgb
    bright = rvt.rgb_rgba(red, red, red, [(0.0, 1000.0)] * 3, None, gamma=0.5)
    assert bright[0, 1].tolist() == [180, 180, 180, 255]  # 0.5 ** 0.5 * 255 = 180.3
    assert bright[0, 3].tolist() == [255, 255, 255, 255]  # above the limit: clipped
    expected = np.rint(tm.stretch_rgb(red, 0.0, 1000.0, 0.5) * 255).astype(np.uint8)
    assert np.array_equal(bright[..., 0], expected)
    # infinity is clipped like any value beyond the limits
    ends = np.array([[np.inf, -np.inf]])
    assert rvt.rgb_rgba(ends, ends, -ends, [(0.0, 1000.0)] * 3, None).tolist() == [
        [[255, 255, 0, 255], [0, 0, 255, 255]]
    ]
    with pytest.raises(ValueError, match="three"):
        rvt.rgb_rgba(red, red, red, [(0.0, 1.0)], None)


# --------------------------------------------------------------------------- web PNG
RED, BLUE = (255, 0, 0, 255), (0, 0, 255, 255)
PNG_SHAPE = (40, 60)
MARK_ROW, MARK_COL = 12, 41  # the middle pixel of a 3 by 3 blue mark


def _test_image() -> np.ndarray:
    """Red everywhere, a clear block of invalid pixels in one corner, one blue mark."""
    rgba = np.zeros((*PNG_SHAPE, 4), dtype=np.uint8)
    rgba[:] = RED
    rgba[25:, :20] = 0
    rgba[MARK_ROW - 1 : MARK_ROW + 2, MARK_COL - 1 : MARK_COL + 2] = BLUE
    return rgba


def _source_extent_lonlat(transform: Affine, crs: str) -> tuple[float, float, float, float]:
    rows, cols = PNG_SHAPE
    corners = [transform * (c, r) for c, r in ((0, 0), (cols, 0), (cols, rows), (0, rows))]
    tr = Transformer.from_crs(crs, 4326, always_xy=True)
    lon, lat = tr.transform([p[0] for p in corners], [p[1] for p in corners])
    return min(lon), min(lat), max(lon), max(lat)


@pytest.mark.parametrize(
    ("transform", "crs"), [(UTM_TRANSFORM, UTM), (DEG_TRANSFORM, "EPSG:4326")], ids=["utm45n", "lonlat"]
)
def test_write_web_png(tmp_path, transform, crs):
    rgba = _test_image()
    path = tmp_path / "layers" / "layer.png"
    bounds = rvt.write_web_png(rgba, transform, crs, path)

    with Image.open(path) as png:
        assert png.format == "PNG" and png.mode == "RGBA"
        out = np.array(png)
    height, width = out.shape[:2]
    # about the source's number of pixels
    assert abs(height - PNG_SHAPE[0]) <= 2 and abs(width - PNG_SHAPE[1]) <= 2

    # transparent where the source is invalid, and nothing blurred: only the source's colours
    colours = {tuple(c) for c in out.reshape(-1, 4).tolist()}
    assert colours == {RED, BLUE, (0, 0, 0, 0)}
    clear = out[..., 3] == 0
    n_clear_source = int((rgba[..., 3] == 0).sum())
    assert clear.any()
    assert abs(int(clear.sum()) - n_clear_source) <= 0.1 * n_clear_source + height + width
    assert clear[height - 3, 3] and not clear[3, width - 3]

    # the returned bounds are the source's extent to within one pixel (about 1e-4 degrees)
    west, south, east, north = bounds
    assert all(type(v) is float for v in bounds)
    assert west < east and south < north
    one_pixel = 1.05e-4
    assert np.abs(np.array(bounds) - np.array(_source_extent_lonlat(transform, crs))).max() < one_pixel

    # the blue mark is where it was: place the PNG by its bounds, as Leaflet does (linearly in
    # EPSG:3857), and take the middle of the blue pixels back to the source grid
    to_web = Transformer.from_crs(4326, 3857, always_xy=True)
    (left, right), (bottom, top) = to_web.transform([west, east], [south, north])
    rows, cols = np.nonzero((out == BLUE).all(axis=-1))
    assert 6 <= len(rows) <= 12  # a 3 by 3 mark, give or take a row or column
    x = left + (cols.mean() + 0.5) / width * (right - left)
    y = top - (rows.mean() + 0.5) / height * (top - bottom)
    sx, sy = Transformer.from_crs(3857, crs, always_xy=True).transform(x, y)
    col, row = ~transform * (sx, sy)
    assert abs(col - (MARK_COL + 0.5)) <= 0.5
    assert abs(row - (MARK_ROW + 0.5)) <= 0.5

    # no date in the file: writing again gives the same bytes
    again = tmp_path / "again.png"
    assert rvt.write_web_png(rgba, transform, crs, again) == bounds
    assert again.read_bytes() == path.read_bytes()


@pytest.mark.parametrize(
    ("transform", "crs", "shape_hw"),
    [(UTM_TRANSFORM, UTM, (218, 1183)), (DEG_TRANSFORM, "EPSG:4326", (120, 160))],
    ids=["utm45n_wide", "lonlat"],
)
def test_write_web_png_every_pixel_is_the_source_pixel_under_its_centre(
    tmp_path, transform, crs, shape_hw
):
    # every source pixel has a colour of its own (its number, in red, green and blue), so a
    # PNG pixel that took a neighbour's colour shows. The wide UTM raster is the size of the
    # largest part: the UTM grid is turned against the web-map grid, most over a long row.
    rows, cols = shape_hw
    number = np.arange(rows * cols).reshape(rows, cols)
    rgba = np.stack(
        [number % 256, number // 256 % 256, number // 65536, np.full(shape_hw, 255)], axis=-1
    ).astype(np.uint8)
    rvt.write_web_png(rgba, transform, crs, tmp_path / "unique.png")
    with Image.open(tmp_path / "unique.png") as png:
        out = np.array(png)

    # the centre of each PNG pixel, taken to the source grid with pyproj
    canvas, width, height = rvt.web_canvas(transform, crs, shape_hw)
    assert out.shape == (height, width, 4)
    cc, rr = np.meshgrid(np.arange(width) + 0.5, np.arange(height) + 0.5)
    x, y = canvas * (cc, rr)
    sx, sy = Transformer.from_crs(3857, crs, always_xy=True).transform(x, y)
    col, row = ~transform * (sx, sy)
    # a centre within a thousandth of a pixel of a pixel edge may go either way: left out
    clear_of_edges = (np.abs(col - np.rint(col)) > 1e-3) & (np.abs(row - np.rint(row)) > 1e-3)
    c, r = np.floor(col).astype(int), np.floor(row).astype(int)
    inside = (r >= 0) & (r < rows) & (c >= 0) & (c < cols)
    assert clear_of_edges.mean() > 0.99 and inside.mean() > 0.9

    check = clear_of_edges & inside
    assert np.array_equal(out[check], rgba[r[check], c[check]])
    assert not out[clear_of_edges & ~inside].any()  # beside the raster: clear


def test_write_web_png_keeps_a_web_mercator_source_pixel_for_pixel(tmp_path):
    rgba = _test_image()
    x0, y0 = Transformer.from_crs(4326, 3857, always_xy=True).transform(85.4, 21.6)
    transform = Affine(10.0, 0.0, round(x0), 0.0, -10.0, round(y0))
    bounds = rvt.write_web_png(rgba, transform, "EPSG:3857", tmp_path / "web.png")
    with Image.open(tmp_path / "web.png") as png:
        assert np.array_equal(np.array(png), rgba)
    lon, lat = Transformer.from_crs(3857, 4326, always_xy=True).transform(
        [round(x0), round(x0) + 600.0], [round(y0) - 400.0, round(y0)]
    )
    assert bounds == pytest.approx([lon[0], lat[0], lon[1], lat[1]], abs=1e-12)


def test_web_canvas_keeps_the_pixel_count_of_a_degree_raster():
    # an EPSG:4326 pixel is wider than tall in web-map units; the canvas keeps both sizes, so
    # each source column gets exactly one column and no pixel is dropped
    transform, width, height = rvt.web_canvas(DEG_TRANSFORM, "EPSG:4326", (300, 400))
    assert width == 400 and 300 <= height <= 301
    assert transform.a == pytest.approx(10.0, rel=1e-6)  # 10 m of longitude at the equator
    assert transform.e == pytest.approx(-10.0 / np.cos(np.radians(21.6)), rel=1e-2)
    with pytest.raises(ValueError, match="uint8"):
        rvt.write_web_png(np.zeros((3, 3, 4)), DEG_TRANSFORM, "EPSG:4326", "unused.png")


# --------------------------------------------------------------------------- GeoJSON
SQUARE = Polygon(
    [(85.1234564, 21.6000004), (85.1244567, 21.6000004), (85.1244567, 21.6010006),
     (85.1234564, 21.6010006)]
)


def _features() -> list[dict]:
    return [
        {
            "geometry": SQUARE,
            "properties": {
                "stand_id": np.int32(17),
                "area_ha": np.float32(1.5),
                "below_min": np.bool_(True),
                "below_why": "isolated",
                "mean": float("nan"),
                "worst": np.float64("inf"),
                "bands": np.array([1.0, np.nan]),
                "missing": None,
            },
        },
        {"geometry": {"type": "Point", "coordinates": [85.40000049, 21.59999951]},
         "properties": {"plot_key": "angul_01"}},
        {"geometry": None, "properties": {"plot_key": "nowhere"}},
    ]


def test_write_geojson_rounds_and_is_compact(tmp_path):
    path = tmp_path / "out" / "stands.geojson"
    size = rvt.write_geojson(_features(), path)
    data = path.read_bytes()
    assert size == len(data) == path.stat().st_size
    text = data.decode("utf-8")
    assert not re.search(r"\s", text)  # no space, no newline
    assert text.startswith('{"type":"FeatureCollection","features":[{"type":"Feature","properties":{')
    assert not re.search(r"\.\d{7}", text)  # no number with more than 6 decimal places
    assert "NaN" not in text and "Infinity" not in text

    collection = json.loads(text)
    first, second, third = collection["features"]
    assert first["geometry"]["type"] == "Polygon"
    assert first["geometry"]["coordinates"][0][0] == [85.123456, 21.6]
    assert first["geometry"]["coordinates"][0][2] == [85.124457, 21.601001]
    assert first["properties"] == {
        "area_ha": 1.5, "bands": [1.0, None], "below_min": True, "below_why": "isolated",
        "mean": None, "missing": None, "stand_id": 17, "worst": None,
    }
    assert second["geometry"] == {"type": "Point", "coordinates": [85.4, 21.6]}
    assert third["geometry"] is None


def test_write_geojson_full_precision(tmp_path):
    rvt.write_geojson(_features(), tmp_path / "full.geojson", decimals=None)
    first = json.loads((tmp_path / "full.geojson").read_text())["features"][0]
    assert first["geometry"]["coordinates"][0][0] == [85.1234564, 21.6000004]
    rvt.write_geojson(_features(), tmp_path / "two.geojson", decimals=2)
    assert not re.search(r"\.\d{3}", (tmp_path / "two.geojson").read_text())


def test_write_geojson_same_input_same_bytes(tmp_path):
    rvt.write_geojson(_features(), tmp_path / "a.geojson")
    rvt.write_geojson(_features(), tmp_path / "b.geojson")
    assert (tmp_path / "a.geojson").read_bytes() == (tmp_path / "b.geojson").read_bytes()
    # the order in which the properties were filled in does not change the file
    shuffled = _features()
    shuffled[0]["properties"] = dict(reversed(list(shuffled[0]["properties"].items())))
    rvt.write_geojson(shuffled, tmp_path / "c.geojson")
    assert (tmp_path / "c.geojson").read_bytes() == (tmp_path / "a.geojson").read_bytes()


def test_write_geojson_repairs_what_rounding_breaks(tmp_path):
    # the notch at (0.5, 0.0000004) stops just short of the bottom edge; rounded to 6 places it
    # lands on it, and the outline then touches itself
    notched = Polygon([(0, 0), (1, 0), (1, 1), (0.5, 0.0000004), (0, 1)])
    assert notched.is_valid
    assert not shapely.transform(notched, lambda xy: np.round(xy, 6)).is_valid
    rvt.write_geojson([{"geometry": notched, "properties": {}}], tmp_path / "n.geojson")
    text = (tmp_path / "n.geojson").read_text()
    written = shape(json.loads(text)["features"][0]["geometry"])
    assert written.is_valid
    assert written.area == pytest.approx(0.5, abs=1e-5)
    assert not re.search(r"\.\d{7}", text)

    # a stand polygon from a raster stays what it was: same parts, same number of vertices
    stand = rvt.to_lonlat(rvt.vectorise_labels(LABELS, UTM_TRANSFORM, UTM, valid=ALL)[7], UTM)
    rounded = rvt.round_geometry(stand, 6)
    assert rounded.is_valid and len(rounded.geoms) == 2
    assert shapely.get_num_coordinates(rounded) == shapely.get_num_coordinates(stand)
    assert np.abs(shapely.get_coordinates(rounded) - shapely.get_coordinates(stand)).max() <= 5e-7

    with pytest.raises(TypeError, match="Path"):
        rvt.write_geojson([{"geometry": None, "properties": {"p": tmp_path}}], tmp_path / "x.geojson")


def test_write_geojson_repairs_a_polygon_that_came_in_invalid(tmp_path):
    # a unit square with a spike out of one corner and back: not valid, and repairing it gives
    # the square and a line. The line has no area and is dropped; the square is written.
    spike = Polygon([(0, 0), (1, 0), (1, 1), (2, 2), (1, 1), (0, 1)])
    assert not spike.is_valid
    assert shapely.make_valid(spike).geom_type == "GeometryCollection"
    rounded = rvt.round_geometry(spike, 6)
    assert rounded.geom_type == "Polygon" and rounded.is_valid
    assert rounded.area == pytest.approx(1.0)
    rvt.write_geojson([{"geometry": spike, "properties": {}}], tmp_path / "s.geojson")
    written = shape(json.loads((tmp_path / "s.geojson").read_text())["features"][0]["geometry"])
    assert written.is_valid and written.equals(Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]))

    # a bow tie crosses itself: its two triangles are kept
    bow = Polygon([(0, 0), (2, 2), (2, 0), (0, 2)])
    assert rvt.round_geometry(bow, 6).area == pytest.approx(2.0)
    # nothing but a line is left of a polygon with no area: written as null
    flat = Polygon([(0, 0), (1, 1), (2, 2), (0, 0)])
    assert rvt.round_geometry(flat, 6).is_empty
    rvt.write_geojson([{"geometry": flat, "properties": {}}], tmp_path / "f.geojson")
    assert json.loads((tmp_path / "f.geojson").read_text())["features"][0]["geometry"] is None
    assert rvt.round_geometry(Point(0.1234567, 1), 6).equals(Point(0.123457, 1))


def test_rounded_neighbours_no_longer_tile_exactly():
    # what the docstring of write_geojson warns of: each polygon is rounded on its own, so
    # neighbours can overlap or gap by about the rounding step. Areas come from pixel counts.
    blocks = np.arange(12).reshape(3, 4).repeat(5, axis=0).repeat(5, axis=1)
    valid = np.ones(blocks.shape, dtype=bool)
    polygons = rvt.vectorise_labels(blocks, UTM_TRANSFORM, UTM, valid=valid)
    rounded = [rvt.round_geometry(rvt.to_lonlat(g, UTM), 6) for g in polygons.values()]
    assert all(g.is_valid and not g.is_empty for g in rounded)
    total, union = sum(g.area for g in rounded), shapely.union_all(rounded).area
    assert total == pytest.approx(union, rel=1e-2)  # close, and that is all that is promised


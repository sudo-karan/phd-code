"""Tests of `fmu.evaluation.spatial_null` with known answers.

All maps, plots and regions are built here. Nothing from any real site is read.
"""

from __future__ import annotations

import numpy as np
import pytest
import shapely
from scipy.spatial.distance import pdist

from fmu.evaluation import spatial_null as sn
from fmu.evaluation._common import Statistic
from fmu.evaluation.permutation import NullDraws, permanova_statistic, run_test

# ---------------------------------------------------------------------------
# Maps
# ---------------------------------------------------------------------------


def test_raster_lookup_by_hand():
    raster = sn.RasterStandMap([[0, 1, 2], [3, -1, 5]], origin=(100.0, 50.0), pixel_size=10.0)
    assert raster.n_stands == 6 and raster.shape == (2, 3)
    row, col = raster.rowcol([[105.0, 45.0], [125.0, 31.0]])
    assert (row.tolist(), col.tolist()) == ([0, 1], [0, 2])
    points = [[105.0, 45.0], [125.0, 31.0], [99.0, 45.0], [105.0, 51.0], [115.0, 35.0]]
    assert raster.lookup(points).tolist() == [0, 5, -1, -1, -1]
    assert raster.lookup([130.0, 45.0]) == -1  # the right edge is outside
    assert raster.lookup([105.0, 30.0]) == -1  # and so is the bottom edge
    assert raster.lookup(np.array(points).reshape(1, 5, 2)).shape == (1, 5)
    with pytest.raises(ValueError):
        sn.RasterStandMap([0, 1, 2], (0, 0), 10)
    with pytest.raises(ValueError):
        sn.RasterStandMap([[0, 1]], (0, 0), 0)
    with pytest.raises(ValueError):
        sn.RasterStandMap([[0, 1]], (0, 0), 10, stand_type=[0])
    with pytest.raises(ValueError):
        sn.RasterStandMap([[0.5, 1]], (0, 0), 10)


def test_polygon_lookup_by_hand():
    squares = [shapely.box(0, 0, 1, 1), shapely.box(1, 0, 2, 1)]
    stands = sn.PolygonStandMap(squares, stand_types=[7, 8])
    assert stands.n_stands == 2
    points = [[0.5, 0.5], [1.5, 0.5], [5.0, 5.0], [1.0, 0.5]]
    assert stands.lookup(points).tolist() == [0, 1, -1, 0]  # shared edge: the smallest code
    assert stands.lookup(np.array(points).reshape(2, 2, 2)).shape == (2, 2)
    reversed_order = sn.PolygonStandMap(squares[::-1])
    assert reversed_order.lookup([[1.0, 0.5]]).tolist() == [0]
    with pytest.raises(ValueError):
        sn.PolygonStandMap(squares, stand_types=[1])
    with pytest.raises(ValueError):
        sn.PolygonStandMap([1, 2])


# ---------------------------------------------------------------------------
# Rigid motion
# ---------------------------------------------------------------------------


def test_rigid_move_keeps_distances_and_lands_on_centre():
    rng = np.random.default_rng(1)
    xy = rng.uniform(0, 500, size=(12, 2))
    for angle in (0.3, 2.0, 5.5):
        moved = sn.rigid_move(xy, angle, (1000.0, -200.0))
        np.testing.assert_allclose(pdist(moved), pdist(xy), rtol=1e-12, atol=1e-9)
        np.testing.assert_allclose(moved.mean(axis=0), [1000.0, -200.0], atol=1e-9)
    # a quarter turn, counter-clockwise: offset (1, 0) becomes (0, 1)
    pair = np.array([[1.0, 0.0], [-1.0, 0.0]])
    np.testing.assert_allclose(
        sn.rigid_move(pair, np.pi / 2, (0.0, 0.0)), [[0.0, 1.0], [0.0, -1.0]], atol=1e-12
    )
    # the orientation is kept (a rotation, not a mirror image)
    tri = np.array([[0.0, 0.0], [4.0, 0.0], [0.0, 3.0]])
    turned = sn.rigid_move(tri, 1.1, (10.0, 10.0))

    def signed_area(p):
        return (p[1, 0] - p[0, 0]) * (p[2, 1] - p[0, 1]) - (p[2, 0] - p[0, 0]) * (p[1, 1] - p[0, 1])

    assert signed_area(turned) == pytest.approx(signed_area(tri))
    np.testing.assert_allclose(sn.rigid_move([[3.0, 4.0]], 1.0, (7.0, 8.0)), [[7.0, 8.0]])
    with pytest.raises(ValueError):
        sn.rigid_move(np.empty((0, 2)), 0.0, (0.0, 0.0))


def _checker(size: int = 20, pixel: float = 10.0, block: int = 4, types: bool = True):
    """A raster of square stands, `block` pixels wide; stand codes all differ."""
    rows, cols = np.indices((size, size))
    per_side = size // block
    labels = (rows // block) * per_side + cols // block
    stand_type = (np.arange(per_side * per_side) % 3) if types else None
    raster = sn.RasterStandMap(labels, (0.0, size * pixel), pixel, stand_type=stand_type)
    return raster, shapely.box(0, 0, size * pixel, size * pixel)


def test_zero_rotation_with_no_shift_returns_the_observed_labelling():
    raster, region = _checker()
    rng = np.random.default_rng(2)
    xy = rng.uniform(20, 180, size=(15, 2))
    draws = sn.rotation_null(xy, np.zeros(15, int), raster, region, 5, seed=1)
    centre = tuple(xy.mean(axis=0))
    unmoved = sn.rigid_move(xy, 0.0, centre)
    np.testing.assert_allclose(unmoved, xy, atol=1e-9)
    np.testing.assert_array_equal(raster.lookup(unmoved), draws.observed_id)
    np.testing.assert_array_equal(raster.lookup(xy), draws.observed_id)
    assert draws.observed_type is not None and raster.stand_type is not None
    np.testing.assert_array_equal(raster.stand_type[draws.observed_id], draws.observed_type)
    # a full turn is the identity too
    np.testing.assert_array_equal(
        raster.lookup(sn.rigid_move(xy, 2 * np.pi, centre)), draws.observed_id
    )


# ---------------------------------------------------------------------------
# The rotation null
# ---------------------------------------------------------------------------


def test_rotation_returns_draws_and_no_score():
    raster, region = _checker()
    rng = np.random.default_rng(3)
    xy = rng.uniform(60, 140, size=(8, 2))
    draws = sn.rotation_null(xy, np.zeros(8, int), raster, region, 30, seed=5)
    assert isinstance(draws, NullDraws) and draws.name == "rotation"
    assert draws.ids.shape == (30, 8) and draws.types is not None
    assert set(draws.info) == {"n_groups", "acceptance", "require_type"}
    assert draws.info["n_groups"] == 1 and 0 < draws.info["acceptance"][0] <= 1
    # stand and type move together: the type is always the type of the stand
    assert raster.stand_type is not None
    np.testing.assert_array_equal(draws.types, raster.stand_type[draws.ids])
    assert len({tuple(r) for r in draws.ids.tolist()}) > 1  # the labels do change
    # no public function of the module returns a number about agreement
    public = [name for name in vars(sn) if not name.startswith("_") and "score" in name.lower()]
    assert public == []
    # a number only comes from a named statistic
    stat = Statistic("n_stands_hit", lambda s, t: float(len(set(s.tolist()))), "greater")
    assert run_test(stat, draws).null == "rotation"


def test_one_stand_everywhere_gives_the_observed_labels_in_every_draw():
    raster = sn.RasterStandMap(np.zeros((10, 10), int), (0.0, 100.0), 10.0)
    region = shapely.box(0, 0, 100, 100)
    xy = np.array([[40.0, 40.0], [50.0, 60.0], [60.0, 45.0]])
    draws = sn.rotation_null(xy, [0, 0, 0], raster, region, 40, seed=2)
    assert draws.types is None and draws.observed_type is None
    np.testing.assert_array_equal(draws.ids, np.zeros((40, 3), int))
    np.testing.assert_array_equal(draws.observed_id, [0, 0, 0])
    torus = sn.torus_translation_null(xy, [0, 0, 0], raster, 40, seed=2)
    np.testing.assert_array_equal(torus.ids, np.zeros((40, 3), int))


def test_one_plot_lands_on_each_half_equally_often():
    raster = sn.RasterStandMap([[0, 1], [0, 1]], (0.0, 100.0), 50.0)
    region = shapely.box(0, 0, 100, 100)
    draws = sn.rotation_null([[25.0, 50.0]], [0], raster, region, 2000, seed=7)
    assert draws.observed_id.tolist() == [0]
    assert float((draws.ids == 0).mean()) == pytest.approx(0.5, abs=0.05)
    assert set(np.unique(draws.ids)) == {0, 1}
    # the same with polygons
    halves = sn.PolygonStandMap([shapely.box(0, 0, 50, 100), shapely.box(50, 0, 100, 100)])
    poly = sn.rotation_null([[25.0, 50.0]], [0], halves, region, 2000, seed=7)
    assert float((poly.ids == 0).mean()) == pytest.approx(0.5, abs=0.05)
    # and the region limits where the plot can go: only the left half is allowed
    left = sn.rotation_null([[25.0, 50.0]], [0], raster, shapely.box(0, 0, 50, 100), 200, seed=7)
    assert (left.ids == 0).all()


def test_plots_on_stands_must_land_on_stands():
    raster, region = _checker(types=False)
    labels = raster.labels.copy()
    labels[6:14, 6:14] = -1  # a hole with no stand in the middle
    holed = sn.RasterStandMap(labels, raster.origin, raster.pixel_size)
    xy = np.array([[25.0, 25.0], [45.0, 30.0], [30.0, 50.0], [100.0, 100.0]])  # the last: in the hole
    draws = sn.rotation_null(xy, np.zeros(4, int), holed, region, 300, seed=11)
    assert draws.observed_id[3] == -1 and (draws.observed_id[:3] >= 0).all()
    assert (draws.ids[:, :3] >= 0).all()  # never in the hole
    assert (draws.ids[:, 3] == -1).all()  # an unscored plot stays unscored
    assert draws.info["acceptance"][0] < 1.0
    torus = sn.torus_translation_null(xy, np.zeros(4, int), holed, 300, seed=11)
    assert (torus.ids[:, :3] >= 0).all() and (torus.ids[:, 3] == -1).all()


def test_require_type_keeps_typed_plots_on_typed_stands():
    raster, region = _checker()
    assert raster.stand_type is not None
    stand_type = raster.stand_type.copy()
    stand_type[[6, 7, 8, 11, 12, 13]] = -1  # some stands have no type
    typed = sn.RasterStandMap(raster.labels, raster.origin, raster.pixel_size, stand_type)
    xy = np.array([[25.0, 185.0], [70.0, 170.0], [150.0, 30.0], [70.0, 130.0]])
    observed_type = stand_type[typed.lookup(xy)]
    assert observed_type[3] == -1 and (observed_type[:3] >= 0).all()
    strict = sn.rotation_null(xy, np.zeros(4, int), typed, region, 300, seed=13, require_type=True)
    assert strict.types is not None and strict.info["require_type"] is True
    assert (strict.types[:, :3] >= 0).all()
    assert (strict.types[:, 3] == -1).all() and (strict.ids[:, 3] >= 0).all()
    loose = sn.rotation_null(xy, np.zeros(4, int), typed, region, 300, seed=13)
    assert loose.types is not None and (loose.types[:, :3] == -1).any()
    torus = sn.torus_translation_null(xy, np.zeros(4, int), typed, 300, seed=13, require_type=True)
    assert torus.types is not None and (torus.types[:, :3] >= 0).all()
    untyped, _ = _checker(types=False)
    with pytest.raises(ValueError):
        sn.rotation_null(xy, np.zeros(4, int), untyped, region, 5, seed=1, require_type=True)


def test_region_smaller_than_the_layout_is_not_estimable():
    raster, _ = _checker()
    xy = np.array([[20.0, 20.0], [150.0, 150.0]])
    with pytest.raises(sn.NullNotEstimable, match="group 0"):
        sn.rotation_null(
            xy, [0, 0], raster, shapely.box(90, 90, 100, 100), 1, seed=1, max_proposals_per_draw=1
        )
    one_pixel = sn.RasterStandMap([[0]], (0.0, 10.0), 10.0)
    with pytest.raises(sn.NullNotEstimable):
        sn.torus_translation_null([[5.0, 5.0]], [0], one_pixel, 3, seed=1)
    with pytest.raises(ValueError):
        sn.rotation_null(xy, [0, 1], raster, {0: shapely.box(0, 0, 200, 200)}, 2, seed=1)
    with pytest.raises(ValueError):
        sn.rotation_null(xy, [0, 0], raster, shapely.Polygon(), 2, seed=1)
    with pytest.raises(TypeError):
        sn.torus_translation_null(xy, [0, 0], sn.PolygonStandMap([shapely.box(0, 0, 9, 9)]), 2, seed=1)  # type: ignore[arg-type]


def test_rotation_is_seeded_and_groups_have_their_own_stream():
    raster, region = _checker()
    rng = np.random.default_rng(17)
    xy = rng.uniform(40, 160, size=(9, 2))
    groups = np.array([0, 0, 0, 0, 1, 1, 1, -1, -1])
    a = sn.rotation_null(xy, groups, raster, region, 25, seed=3)
    b = sn.rotation_null(xy, groups, raster, region, 25, seed=3)
    np.testing.assert_array_equal(a.ids, b.ids)
    np.testing.assert_array_equal(a.types, b.types)
    assert a.info == b.info
    c = sn.rotation_null(xy, groups, raster, region, 25, seed=4)
    assert not np.array_equal(a.ids, c.ids)
    # plots in no group keep their observed labels in every draw
    np.testing.assert_array_equal(a.ids[:, 7:], np.tile(a.observed_id[7:], (25, 1)))
    # adding a group does not change the draws of the groups before it
    fewer = sn.rotation_null(xy[:4], groups[:4], raster, region, 25, seed=3)
    np.testing.assert_array_equal(fewer.ids, a.ids[:, :4])
    t_all = sn.torus_translation_null(xy, groups, raster, 25, seed=3)
    t_few = sn.torus_translation_null(xy[:4], groups[:4], raster, 25, seed=3)
    np.testing.assert_array_equal(t_few.ids, t_all.ids[:, :4])
    np.testing.assert_array_equal(
        t_all.ids, sn.torus_translation_null(xy, groups, raster, 25, seed=3).ids
    )


def test_rotated_layout_stays_rigid_inside_the_null():
    # Stand code = pixel index on a fine grid, so a draw's labels give back the
    # moved positions to within a pixel; the distances between plots must match.
    size, pixel = 200, 1.0
    labels = np.arange(size * size).reshape(size, size)
    raster = sn.RasterStandMap(labels, (0.0, size * pixel), pixel)
    region = shapely.box(0, 0, size * pixel, size * pixel)
    xy = np.array([[80.0, 80.0], [120.0, 85.0], [100.0, 130.0], [95.0, 100.0]])
    draws = sn.rotation_null(xy, np.zeros(4, int), raster, region, 60, seed=19)
    rows, cols = np.divmod(draws.ids, size)
    x = (cols + 0.5) * pixel
    y = size * pixel - (rows + 0.5) * pixel
    for r in range(60):
        moved = np.column_stack([x[r], y[r]])
        np.testing.assert_allclose(pdist(moved), pdist(xy), atol=1.5 * pixel)
    # and the layout is really turned: the direction between two plots varies
    angles = np.arctan2(y[:, 1] - y[:, 0], x[:, 1] - x[:, 0])
    assert np.ptp(angles) > np.pi


# ---------------------------------------------------------------------------
# The torus translation
# ---------------------------------------------------------------------------


def test_torus_excludes_the_identity_and_is_uniform():
    raster = sn.RasterStandMap([[0, 1, 2, 3, 4]], (0.0, 10.0), 10.0)
    draws = sn.torus_translation_null([[25.0, 5.0]], [0], raster, 2000, seed=23)
    assert draws.name == "torus_translation"
    assert draws.observed_id.tolist() == [2]
    assert not (draws.ids == 2).any()
    for other in (0, 1, 3, 4):
        assert float((draws.ids == other).mean()) == pytest.approx(0.25, abs=0.05)
    assert draws.info["n_shifts"] == {0: 4}
    assert set(draws.info) == {"n_groups", "acceptance", "require_type", "n_shifts"}


def test_torus_moves_every_plot_by_the_same_shift():
    h, w = 4, 6
    stripes = np.tile(np.arange(w), (h, 1))  # vertical stripes: the stand is the column
    raster = sn.RasterStandMap(stripes, (0.0, 40.0), 10.0)
    xy = np.array([[15.0, 35.0], [45.0, 5.0]])  # columns 1 and 4
    draws = sn.torus_translation_null(xy, [0, 0], raster, 200, seed=29)
    assert draws.observed_id.tolist() == [1, 4]
    assert ((draws.ids[:, 1] - draws.ids[:, 0]) % w == 3).all()
    assert len(np.unique(draws.ids[:, 0])) == w  # every column shift occurs
    # by hand: a shift of dc columns reads labels[row, (col - dc) mod w]
    assert set(((1 - draws.ids[:, 0]) % w).tolist()) == set(range(w))


def test_codes_are_unique_across_the_maps_of_the_groups():
    map_a, region = _checker(size=8, block=4)  # 4 stands
    map_b, _ = _checker(size=8, block=2)  # 16 stands
    rng = np.random.default_rng(31)
    xy = rng.uniform(25, 55, size=(6, 2))
    groups = np.array([3, 3, 3, 7, 7, 7])
    draws = sn.rotation_null(xy, groups, {3: map_a, 7: map_b}, {3: region, 7: region}, 80, seed=2)
    first, second = draws.ids[:, :3], draws.ids[:, 3:]
    assert first.min() >= 0 and first.max() < 4
    assert second.min() >= 4 and second.max() < 20
    np.testing.assert_array_equal(draws.observed_id[:3], map_a.lookup(xy[:3]))
    np.testing.assert_array_equal(draws.observed_id[3:], map_b.lookup(xy[3:]) + 4)
    assert map_b.stand_type is not None and draws.types is not None
    np.testing.assert_array_equal(draws.types[:, 3:], map_b.stand_type[second - 4])  # types unchanged
    torus = sn.torus_translation_null(xy, groups, {3: map_a, 7: map_b}, 80, seed=2)
    assert torus.ids[:, :3].max() < 4 and torus.ids[:, 3:].min() >= 4
    # one map for all groups: no offset
    single = sn.rotation_null(xy, groups, map_b, region, 20, seed=2)
    np.testing.assert_array_equal(single.observed_id, map_b.lookup(xy))
    # the very same map given to two groups is one map: a stand keeps one code
    same = sn.rotation_null(xy, groups, {3: map_b, 7: map_b}, region, 20, seed=2)
    np.testing.assert_array_equal(same.observed_id, map_b.lookup(xy))
    assert same.ids.max() < 16
    # plots in no group, with one map per group, have no map to be read from
    loose = sn.rotation_null(xy, [3, 3, 3, -1, -1, -1], {3: map_a}, region, 5, seed=2)
    assert (loose.observed_id[3:] == -1).all() and (loose.ids[:, 3:] == -1).all()
    with pytest.raises(ValueError):
        sn.rotation_null(xy, groups, {3: map_a}, region, 5, seed=2)
    untyped, _ = _checker(size=8, block=4, types=False)
    with pytest.raises(ValueError):
        sn.rotation_null(xy, groups, {3: map_a, 7: untyped}, region, 5, seed=2)


def test_rotation_null_has_the_right_size_on_a_smooth_field():
    # A field that is smooth in space and a map that knows nothing about it:
    # the share of p <= 0.05 must not be far above 0.05. (A rough check on 80
    # data sets; the synthetic validation measures the rate properly.)
    raster, region = _checker(size=40, block=5, types=False)
    rng = np.random.default_rng(37)
    n_sets, rejections, n_tested = 80, 0, 0
    for _ in range(n_sets):
        xy = rng.uniform(120, 280, size=(12, 2))
        direction = rng.normal(size=2)
        values = xy @ direction + rng.normal(scale=5.0, size=12)  # a trend plus noise

        statistic = permanova_statistic(pdist(values[:, None]))
        # the map's position is unrelated to the field
        moved_map = sn.RasterStandMap(
            np.roll(raster.labels, rng.integers(0, 40, 2), axis=(0, 1)),
            raster.origin,
            raster.pixel_size,
        )
        draws = sn.rotation_null(xy, np.zeros(12, int), moved_map, region, 19, seed=rng)
        p_value = run_test(statistic, draws).p_value
        n_tested += not np.isnan(p_value)
        rejections += p_value <= 0.05
    # with 19 draws, p <= 0.05 means the observed value beat every draw
    assert n_tested >= 70
    assert rejections / n_tested <= 0.125

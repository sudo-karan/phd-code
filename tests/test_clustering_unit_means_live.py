"""Live test: one mean per unit label (review B14), on Earth Engine, on synthetic images.

No asset is read and no task is submitted. A 20 x 10 pixel grid at 10 m in UTM, built from
pixel coordinates (col 0 to 19 west to east, row 0 to 9 north to south):

- unit 1 in two pieces far apart: cols 0-3 x rows 0-3, and cols 16-19 x rows 6-9;
- unit 2 in one piece: cols 6-9 x rows 0-3;
- unit 3 in one piece, cols 6-13 x rows 6-9, where band b has no data east of col 9;
- unit 4 in one piece, cols 16-19 x rows 0-3, where band b has no data at all;
- no unit anywhere else.

Band a is col + 10 x row, so that each piece has a mean of its own; band b is a with the gaps
above. What this pins is how Earth Engine answers the calls `_compute_superpixel_means`
makes: the grouped sums' dictionary (and a band with no data in a group), the remap that
paints the means back, the means' pixel type, and that for a unit in one piece the means are
those of reduceConnectedComponents, which the stage called before round 13, but for a unit with
no data in a band. The rule itself is tested on numpy stand-ins in
tests/test_clustering_one_mean_per_unit.py.

Run on 20 Oct 2026 (round 13, read-only) against the first version of the change, a grouped
unweighted mean of the masked bands, the first and third tests failed: Earth Engine's grouped
unweighted reducers add a band's masked pixels into its sum (unit 3's b came out 83.25, not
82.5), so the stage now sums each band unmasked beside a band of where it has data.
"""

from __future__ import annotations

import ee
import pytest

from _live_cache_fixtures import init_real_gee_or_skip
from fmu.stages import clustering
from fmu.utils.gee import LABEL_BAND

pytestmark = pytest.mark.live_gee

CRS = "EPSG:32643"
X0, Y0 = 700000, 3150000
W, H = 20, 10
BANDS = ["a", "b"]
# Each unit's pixels as boxes of (cols, rows), both ends included.
UNITS = {
    1: [((0, 3), (0, 3)), ((16, 19), (6, 9))],
    2: [((6, 9), (0, 3))],
    3: [((6, 13), (6, 9))],
    4: [((16, 19), (0, 3))],
}


def _has_b(unit: int, col: int) -> bool:
    return not (unit == 4 or (unit == 3 and col > 9))


def _expected_mean(unit: int, band: str) -> float | None:
    """The mean of band a, or b, over the unit's pixels where the band has data."""
    values = [
        col + 10 * row
        for (c0, c1), (r0, r1) in UNITS[unit]
        for col in range(c0, c1 + 1)
        for row in range(r0, r1 + 1)
        if band == "a" or _has_b(unit, col)
    ]
    return sum(values) / len(values) if values else None


def _n_pixels(unit: int) -> int:
    return sum((c1 - c0 + 1) * (r1 - r0 + 1) for (c0, c1), (r0, r1) in UNITS[unit])


@pytest.fixture(scope="module")
def images():
    init_real_gee_or_skip()
    proj = ee.Projection(CRS).atScale(10)
    region = ee.Geometry.Rectangle([X0, Y0 - 10 * H, X0 + 10 * W, Y0], CRS, False)
    xy = ee.Image.pixelCoordinates(ee.Projection(CRS)).reproject(proj)
    col = xy.select("x").subtract(X0).divide(10).floor()
    row = xy.select("y").subtract(Y0).multiply(-1).divide(10).floor()

    def box(cols, rows):
        return col.gte(cols[0]).And(col.lte(cols[1])).And(row.gte(rows[0])).And(row.lte(rows[1]))

    labels = ee.Image(0).reproject(proj)
    for unit, boxes in UNITS.items():
        for cols, rows in boxes:
            labels = labels.where(box(cols, rows), unit)
    labels = labels.updateMask(labels.gt(0)).toInt().rename("stand").reproject(proj)
    a = col.add(row.multiply(10)).toDouble().rename("a").reproject(proj)
    b = a.updateMask(labels.neq(4).And(labels.neq(3).Or(col.lte(9)))).rename("b")
    features = a.addBands(b)
    means = clustering._compute_superpixel_means(features, labels, BANDS, region, 10)
    per_piece = (
        features.addBands(labels.rename(LABEL_BAND))
        .reduceConnectedComponents(reducer=ee.Reducer.mean(), labelBand=LABEL_BAND, maxSize=64)
        .select(BANDS)
    )
    return labels, means, per_piece, region, proj


def _per_unit(image, labels, region, proj) -> dict[int, dict[str, list]]:
    """{unit: {band: [min, max, count]}} of an image over each unit's pixels."""
    grouped = (
        image.select(BANDS)
        .addBands(labels.rename(LABEL_BAND))
        .reduceRegion(
            reducer=ee.Reducer.minMax()
            .combine(ee.Reducer.count(), sharedInputs=True)
            .forEachBand(image.select(BANDS))
            .group(groupField=len(BANDS), groupName=LABEL_BAND),
            geometry=region,
            crs=proj,
            maxPixels=1_000_000,
        )
        .getInfo()
    )
    return {
        int(g[LABEL_BAND]): {
            band: [g.get(f"{band}_min"), g.get(f"{band}_max"), g.get(f"{band}_count", 0)]
            for band in BANDS
        }
        for g in grouped["groups"]
    }


def test_every_pixel_of_a_unit_holds_its_mean_both_pieces_too(images):
    labels, means, _per_piece, region, proj = images
    got = _per_unit(means, labels, region, proj)
    assert sorted(got) == [1, 2, 3, 4]
    for unit in UNITS:
        for band in BANDS:
            expected = _expected_mean(unit, band)
            low, high, count = got[unit][band]
            if expected is None:
                assert not count, (unit, band, got[unit][band])
            else:
                assert low == pytest.approx(expected, rel=1e-6), (unit, band, got[unit][band])
                assert high == pytest.approx(expected, rel=1e-6), (unit, band, got[unit][band])
                assert count == _n_pixels(unit), (unit, band, got[unit][band])


def test_reduce_connected_components_gave_the_two_pieces_two_means(images):
    """The finding, on Earth Engine: the call the stage made before round 13 gives unit 1's
    pieces 16.5 and 92.5, where the stage now gives both 54.5."""
    labels, _means, per_piece, region, proj = images
    got = _per_unit(per_piece, labels, region, proj)
    assert got[1]["a"][:2] == pytest.approx([16.5, 92.5])
    assert _expected_mean(1, "a") == 54.5


def test_a_unit_in_one_piece_has_the_means_reduce_connected_components_gives(images):
    """Wherever both give a unit in one piece a value, the stage gives what
    reduceConnectedComponents gives, to floating-point summation order: unit 3's band b too,
    the mean of its pixels with data, which reduceConnectedComponents writes to every pixel of
    the unit, as the stage does."""
    labels, means, per_piece, region, proj = images
    one_piece = labels.neq(1)
    largest = (
        means.subtract(per_piece).abs().updateMask(one_piece)
        .reduceRegion(reducer=ee.Reducer.max(), geometry=region, crs=proj, maxPixels=1_000_000)
        .getInfo()
    )
    for band in BANDS:
        assert largest[band] is not None and largest[band] <= 1e-9, largest


def test_a_unit_with_no_data_in_a_band_is_masked_where_reduce_connected_components_gave_0(images):
    """Read on Earth Engine on 20 Oct 2026 (round 13): reduceConnectedComponents gives unit 4,
    which has no data in band b, the value 0 in b on all 16 of its pixels, unmasked, so before
    round 13 such a unit had a k-means row with a 0 it never measured. The stage now masks the
    unit in that band, so it has no row (dropNulls), as the stage's own warning describes."""
    labels, means, per_piece, region, proj = images
    unit_4 = labels.eq(4)
    theirs = per_piece.select("b").updateMask(unit_4).reduceRegion(
        reducer=ee.Reducer.minMax().combine(ee.Reducer.count(), sharedInputs=True),
        geometry=region, crs=proj, maxPixels=1_000_000,
    ).getInfo()
    assert theirs == {"b_min": 0, "b_max": 0, "b_count": 16}
    only_theirs = (
        per_piece.mask().And(means.mask().Not()).updateMask(labels.neq(1))
        .reduceRegion(reducer=ee.Reducer.sum(), geometry=region, crs=proj, maxPixels=1_000_000)
        .getInfo()
    )
    assert only_theirs == {"a": 0, "b": 16}


def test_the_means_are_double_precision(images):
    _labels, means, _per_piece, _region, _proj = images
    types = means.bandTypes().getInfo()
    assert {band: types[band]["precision"] for band in BANDS} == {"a": "double", "b": "double"}


def test_a_band_whose_footprint_ends_inside_a_unit_is_averaged_over_its_data(images):
    """A band clipped at x = 100 m (col 10) has data on unit 1's first piece, all of unit 2,
    the west half of unit 3 and none of unit 4. Read on Earth Engine on 20 Oct 2026 (round 13):
    unmask(0) alone leaves it masked outside its footprint, and the grouped unweighted sum then
    took those pixels in (unit 3: 2,664 over 32 pixels, where 1,320 over 16 is right); unmasked
    everywhere it is right."""
    labels, _means, _per_piece, region, proj = images
    xy = ee.Image.pixelCoordinates(ee.Projection(CRS)).reproject(proj)
    col = xy.select("x").subtract(X0).divide(10).floor()
    row = xy.select("y").subtract(Y0).multiply(-1).divide(10).floor()
    a = col.add(row.multiply(10)).toDouble().reproject(proj)
    small = ee.Geometry.Rectangle([X0, Y0 - 10 * H, X0 + 100, Y0], CRS, False)
    c = a.clip(small).rename("c")
    means = clustering._compute_superpixel_means(c, labels, ["c"], region, 10)
    grouped = (
        means.addBands(labels.rename(LABEL_BAND))
        .reduceRegion(
            reducer=ee.Reducer.minMax().combine(ee.Reducer.count(), sharedInputs=True)
            .group(groupField=1, groupName=LABEL_BAND),
            geometry=region, crs=proj, maxPixels=1_000_000,
        )
        .getInfo()
    )
    got = {int(g[LABEL_BAND]): (g.get("min"), g.get("max"), g.get("count", 0)) for g in grouped["groups"]}
    assert got[1][:2] == pytest.approx((16.5, 16.5)) and got[1][2] == 32
    assert got[2][:2] == pytest.approx((22.5, 22.5)) and got[2][2] == 16
    assert got[3][:2] == pytest.approx((82.5, 82.5)) and got[3][2] == 32
    assert got[4][2] == 0

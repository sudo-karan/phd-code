"""Live test: the merge's pixel counts, valid counts and criterion means (review B17), on Earth
Engine, on synthetic images.

No asset is read and no task is submitted. The grid of tests/test_clustering_unit_means_live.py,
20 x 10 pixels at 10 m in UTM: unit 1 in two pieces (32 pixels), units 2 to 4 in one (16, 32 and
16 pixels); band a is col + 10 x row everywhere, and band b is a with no data east of col 9 in
unit 3 and none at all in unit 4. What this pins is how Earth Engine answers
`extract_superpixel_graph` and `extract_superpixel_attributes`: each superpixel's pixel count,
and each band's valid count and its mean over the pixels where it has data, with no data read as
None.

Run read-only on 20 Oct 2026 (round 13) against B17 as first written, it stopped in
`extract_superpixel_graph`: an unweighted frequencyHistogram counts the region's masked pixels
under the key "null", which the graph read as a label (ValueError: could not convert string to
float: 'null'). Its grouped reducer for the means, a grouped unweighted mean and count of the
band as it is, tried on the same images on its own (call 7 of the round 13 record), gave unit
3's b 83.25 over 16 pixels where its 16 values average 82.5: Earth Engine's grouped unweighted
reducers add a band's masked pixels into the sum they give a group, though their count leaves
them out. Now the histograms leave "null" out, and the band goes in unmasked beside a band of
where it has data, the mean being the one sum over the other. Both tests pass.
"""

from __future__ import annotations

import ee
import pytest

from _live_cache_fixtures import init_real_gee_or_skip
from fmu.utils.adjacency import extract_superpixel_attributes, extract_superpixel_graph

pytestmark = pytest.mark.live_gee

CRS = "EPSG:32643"
X0, Y0 = 700000, 3150000
W, H = 20, 10
UNITS = {
    1: [((0, 3), (0, 3)), ((16, 19), (6, 9))],
    2: [((6, 9), (0, 3))],
    3: [((6, 13), (6, 9))],
    4: [((16, 19), (0, 3))],
}
# {unit: {band: (valid pixels, mean over them)}}, worked out from the definitions above.
EXPECTED = {
    1: {"a": (32, 54.5), "b": (32, 54.5)},
    2: {"a": (16, 22.5), "b": (16, 22.5)},
    3: {"a": (32, 84.5), "b": (16, 82.5)},
    4: {"a": (16, 32.5), "b": (0, None)},
}


@pytest.fixture(scope="module")
def merged_inputs():
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
    labels = labels.updateMask(labels.gt(0)).toInt().rename("snic_clusters").reproject(proj)
    a = col.add(row.multiply(10)).toDouble().rename("a").reproject(proj)
    b = a.updateMask(labels.neq(4).And(labels.neq(3).Or(col.lte(9)))).rename("b")
    graph = extract_superpixel_graph(labels, region, 10, context="live merge graph")
    means, counts = extract_superpixel_attributes(
        a.addBands(b), labels, graph, region, 10, context="live merge criteria"
    )
    return graph, means, counts


def test_each_superpixel_has_its_pixel_count(merged_inputs):
    graph, _, _ = merged_inputs
    assert dict(zip(graph.raw_labels, graph.n_pixels, strict=True)) == {1: 32, 2: 16, 3: 32, 4: 16}


def test_a_band_is_counted_and_averaged_over_its_pixels_with_data(merged_inputs):
    graph, means, counts = merged_inputs
    for i, unit in enumerate(graph.raw_labels):
        for band, (n_valid, mean) in EXPECTED[unit].items():
            assert counts[i][band] == n_valid, (unit, band, counts[i])
            if mean is None:
                assert means[i][band] is None, (unit, band, means[i])
            else:
                assert means[i][band] == pytest.approx(mean, rel=1e-9), (unit, band, means[i])

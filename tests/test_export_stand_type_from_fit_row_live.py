"""Live test: the export's stand types from the fit's rows, on Earth Engine, on synthetic images.

No asset is read and no task is submitted: sixteen stands of 5 x 5 pixels on a 10 m UTM grid,
each of type label mod 3, built from pixel coordinates. Stand 101's types are all masked (it has
no row in the fit); half of stand 202's are (it has one). What this pins is how Earth Engine
answers the calls `_stand_row_types` and `_take_the_fit_rows_types` make: the grouped reduction's
keys (a group whose values are all masked comes back without a "mode", seen on 19 Oct 2026), the
label keys formatted with "%d", the lookup that retypes a polygon, and, since round 13, the null
type a polygon gets when its stand has no row. The fake-raster tests in
tests/test_export_stand_type_from_fit_row.py cover the rule itself.
"""

from __future__ import annotations

import ee
import pytest

from _live_cache_fixtures import init_real_gee_or_skip
from fmu.stages import export as export_mod

pytestmark = pytest.mark.live_gee

CRS = "EPSG:32643"
X0, Y0 = 700000, 3150000
LABELS = [0, 1, 2, 3, 100, 101, 102, 103, 200, 201, 202, 203, 300, 301, 302, 303]


@pytest.fixture(scope="module")
def images():
    init_real_gee_or_skip()
    proj = ee.Projection(CRS).atScale(10)
    region = ee.Geometry.Rectangle([X0, Y0 - 200, X0 + 200, Y0], CRS, False)
    xy = ee.Image.pixelCoordinates(ee.Projection(CRS)).reproject(proj)
    x, y = xy.select("x").subtract(X0), xy.select("y").subtract(Y0).multiply(-1)
    labels = x.divide(50).floor().add(y.divide(50).floor().multiply(100)).toInt().rename("stand").reproject(proj)
    types = (
        labels.mod(3).toInt()
        .updateMask(labels.neq(101))
        .updateMask(labels.neq(202).Or(x.mod(50).lt(25)))
        .rename("cluster_id")
        .reproject(proj)
    )
    return labels, types, region


def test_every_stand_with_a_typed_pixel_has_its_row_type_and_no_other_stand_does(images):
    labels, types, region = images
    got = export_mod._stand_row_types(types, labels, region, 10).getInfo()
    assert got == {str(s): s % 3 for s in LABELS if s != 101}


def test_a_polygon_takes_its_stands_row_type_and_a_stand_without_one_is_null(images):
    """Every polygon is first given a wrong type, 9, as a vote that took a neighbour's type
    would be; then the stands with a row take their row's type, and the stand without one
    (101), or left out of the dictionary (0 and 102), gets a null type, not the 9 (round 13).
    The layer is read feature by feature, so that a null type is read as the stand's, not
    dropped from a list of values zipped with the labels."""
    labels, types, region = images
    polygons = labels.reduceToVectors(
        geometry=region, scale=10, geometryType="polygon", eightConnected=True,
        labelProperty="stand_lbl", maxPixels=int(1e9),
    ).map(lambda f: f.set("cluster_id", 9))
    row_types = export_mod._stand_row_types(types, labels, region, 10)

    def typed(fit_row_types):
        fc = export_mod._take_the_fit_rows_types(polygons, fit_row_types)
        features = fc.select(["stand_lbl", "cluster_id"], None, False).getInfo()["features"]
        return {int(f["properties"]["stand_lbl"]): f["properties"].get("cluster_id") for f in features}

    assert typed(row_types) == {s: (None if s == 101 else s % 3) for s in LABELS}
    assert typed(row_types.remove(["0", "102"], True)) == {
        s: (None if s in (0, 101, 102) else s % 3) for s in LABELS
    }

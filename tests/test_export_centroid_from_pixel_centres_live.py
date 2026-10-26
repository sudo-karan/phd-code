"""Live test: each polygon's centroid is the mean of its pixel centres (round 14), on Earth Engine.

Written in round 14 and NOT RUN when it was written: that task made no Earth Engine call. What
it pins was read once on Earth Engine before the change (26 Oct 2026, read-only, on a synthetic
6 x 4 labelled image with three rectangles): with the export's reducer, countEvery combined with
the mean of pixelLonLat's two bands, every polygon's 'count' is the default reducer's, and the
two means are the grouped means of pixelLonLat by label. The rule itself is tested offline in
tests/test_export_centroid_from_pixel_centres.py.

No asset is read and no task is submitted. An 8 x 6 pixel grid at 10 m in UTM 43N, built from
pixel coordinates (col 0 to 7 west to east, row 0 to 5 north to south): label 2 is cols 1-2 x
rows 1-2, and label 1 every other pixel, a ring around label 2 whose hole is off its centre, so
that its pixel centres' mean is not the middle of the grid. The expected means are computed here
from the pixel centres with pyproj.
"""

from __future__ import annotations

import ee
import numpy as np
import pytest
from pyproj import Transformer

from _live_cache_fixtures import init_real_gee_or_skip
from fmu.stages import export as export_mod

pytestmark = pytest.mark.live_gee

CRS = "EPSG:32643"
X0, Y0 = 700000, 3150000
W, H = 8, 6
HOLE = ((1, 2), (1, 2))  # label 2: (cols, rows), both ends included


def _label(col: int, row: int) -> int:
    (c0, c1), (r0, r1) = HOLE
    return 2 if c0 <= col <= c1 and r0 <= row <= r1 else 1


def _expected() -> dict[int, dict[str, float]]:
    """{label: {"count", "lon", "lat"}}: its pixels, and the mean of their centres' lon and lat."""
    to_lonlat = Transformer.from_crs(CRS, "EPSG:4326", always_xy=True).transform
    centres: dict[int, list[tuple[float, float]]] = {}
    for col in range(W):
        for row in range(H):
            lon, lat = to_lonlat(X0 + 10 * col + 5, Y0 - 10 * row - 5)
            centres.setdefault(_label(col, row), []).append((lon, lat))
    return {
        label: {"count": len(xy), "lon": float(np.mean([p[0] for p in xy])),
                "lat": float(np.mean([p[1] for p in xy]))}
        for label, xy in centres.items()
    }


@pytest.fixture(scope="module")
def labels():
    init_real_gee_or_skip()
    proj = ee.Projection(CRS).atScale(10)
    region = ee.Geometry.Rectangle([X0, Y0 - 10 * H, X0 + 10 * W, Y0], CRS, False)
    xy = ee.Image.pixelCoordinates(ee.Projection(CRS)).reproject(proj)
    col = xy.select("x").subtract(X0).divide(10).floor()
    row = xy.select("y").subtract(Y0).multiply(-1).divide(10).floor()
    (c0, c1), (r0, r1) = HOLE
    hole = col.gte(c0).And(col.lte(c1)).And(row.gte(r0)).And(row.lte(r1))
    image = ee.Image(1).reproject(proj).where(hole, 2).toInt().rename("lbl").reproject(proj)
    return image, region


def _by_label(fc: ee.FeatureCollection) -> dict[int, dict]:
    features = fc.getInfo()["features"]
    got = {int(f["properties"]["lbl"]): f["properties"] for f in features}
    assert len(got) == len(features), "a label came out in more than one polygon"
    return got


def test_the_count_is_the_default_reducers_count(labels):
    image, region = labels
    ours = _by_label(export_mod._vectorise_with_pixel_centres(image, region=region, scale=10, label_property="lbl"))
    default = _by_label(image.reduceToVectors(
        geometry=region, scale=10, geometryType="polygon", eightConnected=True,
        labelProperty="lbl", maxPixels=int(1e9),
    ))
    assert {k: v["count"] for k, v in ours.items()} == {k: v["count"] for k, v in default.items()}
    assert {k: v["count"] for k, v in ours.items()} == {k: v["count"] for k, v in _expected().items()}


def test_the_two_means_are_the_mean_of_the_pixel_centres(labels):
    image, region = labels
    got = _by_label(export_mod._vectorise_with_pixel_centres(image, region=region, scale=10, label_property="lbl"))
    for label, want in _expected().items():
        p = got[label]
        assert p[export_mod._PIXEL_CENTRES_LON] == pytest.approx(want["lon"], abs=1e-8), label
        assert p[export_mod._PIXEL_CENTRES_LAT] == pytest.approx(want["lat"], abs=1e-8), label


def test_the_layer_takes_its_centroid_from_them_and_keeps_neither(labels):
    """What the builders do after the call: the centroid from the two means, which are dropped."""
    image, region = labels
    fc = (
        export_mod._vectorise_with_pixel_centres(image, region=region, scale=10, label_property="lbl")
        .map(lambda f: export_mod._add_geom_attrs(f, 10))
        .map(export_mod._drop_internal_properties)
    )
    got = _by_label(fc)
    for label, want in _expected().items():
        p = got[label]
        assert p["n_pixels"] == want["count"], label
        assert p["centroid_lon"] == pytest.approx(want["lon"], abs=1e-8), label
        assert p["centroid_lat"] == pytest.approx(want["lat"], abs=1e-8), label
        assert not {"count", export_mod._PIXEL_CENTRES_LON, export_mod._PIXEL_CENTRES_LAT} & set(p), label

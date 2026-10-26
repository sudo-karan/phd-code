"""Non-live tests: a polygon's centroid is the mean position of its pixel centres (round 14).

Until round 14 the export took `centroid_lat` and `centroid_lon` from the geometry's
`centroid()`. On the polygons of review A6, whose hole touches the outer ring at a vertex, that
centroid counts the hole as area, as `area()` did: stand 83 (`stand_id` 223) of
`sanjay_van_alphaearth_keptland_r9` sits 35.1 m from its centroid with the hole subtracted, in its
committed layer (docs/reproducibility/r9_runs/sanjay_van_alphaearth_keptland_r9_stands_merged.geojson;
docs/handoff/2026-10-20-round13.md, Task 2, A6). `stand_id` and `unit_id` are numbered by the
centroid. Round 13's question 21 was answered (a) for round 14: take the centroid from the pixels,
as A6 takes the area, the mean position of each polygon's pixel centres from the same
reduceToVectors call (register entry spec-export-centroid-from-pixel-centres).

Stand 83's committed polygon is read here and projected to its run's analysis grid (the UTM zone
of the ROI's midpoint, 10 m pixels with their edges on multiples of 10 m: fmu.utils.grid). The
centres of the grid's pixels inside it, with its hole, are found with shapely; there are 823, the
pixel count of its merge record. The mean of their longitudes and latitudes is what the mean of
`ee.Image.pixelLonLat()` over the polygon's pixels gives it. Then, on a fake Earth Engine, the
three builders: each must vectorise its label band with pixelLonLat's two bands beside it, ask
reduceToVectors for countEvery combined with the mean of the two, take the centroid (and so the
numbering) from those means, and leave no property on the layer that it did not carry before.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml
from pyproj import Geod, Transformer
from shapely import contains_xy
from shapely.geometry import shape
from shapely.ops import transform

import fmu.stages.export as export_mod
from fmu.config import load_config
from fmu.stages.base import PipelineContext
from fmu.utils.grid import utm_epsg_code

REPO = Path(__file__).resolve().parent.parent
RUN = "sanjay_van_alphaearth_keptland_r9"
LAYER = REPO / "docs" / "reproducibility" / "r9_runs" / f"{RUN}_stands_merged.geojson"
RECORD = REPO / "docs" / "reproducibility" / "r9_runs" / f"{RUN}_run.json"
CONFIG = REPO / "configs" / f"{RUN}.yaml"
BASELINE_YAML = REPO / "configs" / "sanjay_van_baseline.yaml"
SCALE_M = 10
GEOD = Geod(ellps="WGS84")

# The names under which reduceToVectors gives a polygon the mean of pixelLonLat's two bands.
PIXEL_LON, PIXEL_LAT = "pixel_lon", "pixel_lat"


def _metres(a: tuple[float, float], b: tuple[float, float]) -> float:
    """The distance between two (lon, lat) points on the WGS84 ellipsoid, in metres."""
    return float(GEOD.inv(a[0], a[1], b[0], b[1])[2])


def _grid_epsg() -> int:
    """The run's analysis grid, as fmu.utils.grid.analysis_grid picks it: the ROI's midpoint."""
    roi_file = yaml.safe_load(CONFIG.read_text())["roi"]["roi_file"]
    roi = json.loads((REPO / roi_file).read_text())
    bounds = np.array([shape(f["geometry"]).bounds for f in roi["features"]])
    west, south = bounds[:, 0].min(), bounds[:, 1].min()
    east, north = bounds[:, 2].max(), bounds[:, 3].max()
    return utm_epsg_code((west + east) / 2.0, (south + north) / 2.0)


@pytest.fixture(scope="module")
def stand_83() -> dict[str, Any]:
    """Stand 83 as its committed layer gives it, and as its pixels on the analysis grid give it."""
    (feature,) = [
        f for f in json.loads(LAYER.read_text())["features"] if f["properties"]["stand_lbl"] == 83
    ]
    epsg = _grid_epsg()
    to_grid = Transformer.from_crs(4326, epsg, always_xy=True).transform
    to_lonlat = Transformer.from_crs(epsg, 4326, always_xy=True).transform
    polygon = transform(to_grid, shape(feature["geometry"]))
    vertices = np.array(
        [xy for ring in [polygon.exterior, *polygon.interiors] for xy in ring.coords]
    )
    minx, miny, maxx, maxy = polygon.bounds
    xs = np.arange(math.floor(minx / SCALE_M) * SCALE_M + SCALE_M / 2, maxx, SCALE_M)
    ys = np.arange(math.floor(miny / SCALE_M) * SCALE_M + SCALE_M / 2, maxy, SCALE_M)
    x, y = (a.ravel() for a in np.meshgrid(xs, ys))
    inside = contains_xy(polygon, x, y)
    lon, lat = to_lonlat(x[inside], y[inside])
    exterior = type(polygon)(polygon.exterior)
    holes = [type(polygon)(ring) for ring in polygon.interiors]
    with_holes_added = (
        sum(p.area * p.centroid.x for p in [exterior, *holes]) / sum(p.area for p in [exterior, *holes]),
        sum(p.area * p.centroid.y for p in [exterior, *holes]) / sum(p.area for p in [exterior, *holes]),
    )
    props = feature["properties"]
    return {
        "epsg": epsg,
        "props": props,
        "n_holes": len(holes),
        "largest_vertex_offset_m": float(
            np.abs(vertices - SCALE_M * np.round(vertices / SCALE_M)).max()
        ),
        "n_pixel_centres": int(inside.sum()),
        "committed": (props["centroid_lon"], props["centroid_lat"]),
        "pixel_centres_mean": (float(np.mean(lon)), float(np.mean(lat))),
        "holes_subtracted": to_lonlat(polygon.centroid.x, polygon.centroid.y),
        "holes_added": to_lonlat(*with_holes_added),
    }


def test_stand_83_on_its_grid_is_the_polygon_round_13_measured(stand_83):
    """The scenario, before and after the fix: one hole; every vertex on the 10 m grid of UTM 43N,
    so the polygon is whole pixels, 823 of them as its merge record says; the committed centroid
    is the centroid with the hole added, 35 m from the one with the hole subtracted."""
    record = json.loads(RECORD.read_text())["stand_attributes"]["83"]
    assert stand_83["epsg"] == 32643
    assert (stand_83["props"]["stand_id"], stand_83["n_holes"]) == (223, 1)
    assert stand_83["largest_vertex_offset_m"] < 1e-3
    assert stand_83["n_pixel_centres"] == record["n_pixels"] == 823
    assert _metres(stand_83["committed"], stand_83["holes_added"]) < 0.01
    assert 35.0 < _metres(stand_83["committed"], stand_83["holes_subtracted"]) < 35.2


def test_the_mean_of_stand_83s_pixel_centres_is_its_centroid_with_the_hole_subtracted(stand_83):
    """What the pixels give, and why they are the right source: the mean position of the 823
    pixel centres lies within 1 cm of the centroid with the hole subtracted, and 35 m from the
    committed centroid."""
    assert _metres(stand_83["pixel_centres_mean"], stand_83["holes_subtracted"]) < 0.01
    assert 35.0 < _metres(stand_83["pixel_centres_mean"], stand_83["committed"]) < 35.2


# ---------------------------------------------------------------------------
# A fake Earth Engine, enough for _add_geom_attrs, the three builders and the numbering
# ---------------------------------------------------------------------------


def _val(x: Any) -> Any:
    return x.value if isinstance(x, _Number) else x


class _Number:
    def __init__(self, value: Any):
        self.value = _val(value)

    def multiply(self, other: Any) -> _Number:
        return _Number(self.value * _val(other))

    def divide(self, other: Any) -> _Number:
        return _Number(self.value / _val(other))

    def add(self, other: Any) -> _Number:
        return _Number(self.value + _val(other))

    def subtract(self, other: Any) -> _Number:
        return _Number(self.value - _val(other))


class _List(list):
    def get(self, i: Any) -> Any:
        return self[_val(i)]

    def map(self, fn) -> _List:
        return _List(fn(x) for x in self)

    def removeAll(self, other) -> _List:  # noqa: N802 - mirrors the ee API
        return _List(x for x in self if x not in set(other))

    def getInfo(self) -> list:  # noqa: N802 - mirrors the ee API
        return list(self)

    @staticmethod
    def sequence(start: Any, end: Any) -> _List:
        return _List(range(_val(start), _val(end) + 1))


class _Geometry:
    """A polygon's geometry: its perimeter, and the centroid `centroid()` gives it."""

    def __init__(self, lon: float, lat: float, perimeter_m: float = 40.0):
        self.lon, self.lat, self.perimeter_m = lon, lat, perimeter_m

    def perimeter(self, maxError: float) -> _Number:  # noqa: N803 - Earth Engine's name
        return _Number(self.perimeter_m)

    def centroid(self, maxError: float) -> Any:  # noqa: N803 - Earth Engine's name
        geometry = self

        class _Point:
            def coordinates(self) -> _List:
                return _List([geometry.lon, geometry.lat])

        return _Point()


class _Feature:
    def __init__(self, props: dict[str, Any], geometry: _Geometry | None = None):
        self.props, self._geometry = dict(props), geometry

    def geometry(self) -> _Geometry | None:
        return self._geometry

    def get(self, name: str) -> Any:
        return self.props[name]

    def set(self, name: Any, value: Any = None) -> _Feature:
        new = dict(name) if isinstance(name, dict) else {name: value}
        return _Feature({**self.props, **new}, self._geometry)

    def propertyNames(self) -> _List:  # noqa: N802 - mirrors the ee API
        return _List(self.props)

    def select(self, names: list[str]) -> _Feature:
        return _Feature({k: self.props[k] for k in names}, self._geometry)


class _FC:
    def __init__(self, features: list[_Feature]):
        self.features = list(features)

    def map(self, fn) -> _FC:
        return _FC([fn(f) for f in self.features])

    def filter(self, keep) -> _FC:
        return _FC([f for f in self.features if keep(f)])

    def sort(self, prop: str) -> _FC:
        return _FC(sorted(self.features, key=lambda f: _val(f.props[prop])))

    def size(self) -> _Number:
        return _Number(len(self.features))

    def toList(self, n: Any) -> _List:  # noqa: N802 - mirrors the ee API
        return _List(self.features[: _val(n)])


class _Reducer:
    """What a reducer was built as; its inputs and outputs as Earth Engine's docs give them."""

    def __init__(self, kind: str, parts: tuple[_Reducer, ...] = (), names: tuple[str, ...] = ()):
        self.kind, self.parts, self.names = kind, parts, tuple(names)
        self.prefix: Any = None
        self.shared: Any = None

    @staticmethod
    def countEvery() -> _Reducer:  # noqa: N802 - mirrors the ee API
        return _Reducer("countEvery")

    @staticmethod
    def mean() -> _Reducer:
        return _Reducer("mean")

    @staticmethod
    def mode() -> _Reducer:
        return _Reducer("mode")

    def combine(self, reducer2: _Reducer, outputPrefix: Any = None, sharedInputs: Any = None) -> _Reducer:  # noqa: N803
        out = _Reducer("combine", (self, reducer2))
        out.prefix, out.shared = outputPrefix, sharedInputs
        return out

    def forEach(self, outputNames: list[str]) -> _Reducer:  # noqa: N802, N803 - mirrors the ee API
        return _Reducer("forEach", (self,), tuple(outputNames))

    def described(self) -> Any:
        if not self.parts:
            return self.kind
        return (self.kind, *(p.described() for p in self.parts), *([self.names] if self.names else []))

    def n_inputs(self) -> int:
        """countEvery has none, mean one; forEach of a one-input reducer one per name; combine,
        with sharedInputs false (its default), the inputs of the first then of the second."""
        if self.kind == "countEvery":
            return 0
        if self.kind in ("mean", "mode"):
            return 1
        if self.kind == "forEach":
            return len(self.names) * self.parts[0].n_inputs()
        assert self.kind == "combine" and not self.shared and not self.prefix
        return self.parts[0].n_inputs() + self.parts[1].n_inputs()

    def outputs(self) -> list[str]:
        """countEvery and mean give "count" and "mean"; forEach of a one-output reducer gives the
        names as they are; combine, with no prefix, the first's outputs then the second's."""
        if not self.parts:
            return [self.kind if self.kind != "countEvery" else "count"]
        if self.kind == "forEach":
            return list(self.names)
        return self.parts[0].outputs() + self.parts[1].outputs()


# Each polygon reduceToVectors makes: (label, pixel count, centroid() of its geometry, mean of its
# pixel centres as (lon, lat)). By the geometry 1 is the northernmost, then 2, then 3; by the
# pixels 3, then 2, then 1, as a hole counted as area can put a centroid north of its stand.
POLYGONS = [
    (1, 7, (77.10, 28.60), (77.10, 28.50)),
    (2, 1, (77.20, 28.55), (77.20, 28.55)),
    (3, 40, (77.30, 28.52), (77.30, 28.58)),
]


class _Image:
    """A label band or a feature stack; pixelLonLat's two bands are 'longitude' and 'latitude'."""

    def __init__(self, bands: list[str], vectorised: list[dict[str, Any]]):
        self.bands, self.vectorised = list(bands), vectorised

    def toInt(self) -> _Image:  # noqa: N802 - mirrors the ee API
        return self

    def rename(self, name: str) -> _Image:
        assert len(self.bands) == 1
        return _Image([name], self.vectorised)

    def addBands(self, other: _Image) -> _Image:  # noqa: N802 - mirrors the ee API
        return _Image(self.bands + other.bands, self.vectorised)

    def bandNames(self) -> _List:  # noqa: N802 - mirrors the ee API
        return _List(self.bands)

    def select(self, bands: Any) -> _Image:
        return self

    def reduceToVectors(self, **kw: Any) -> _FC:  # noqa: N802 - mirrors the ee API
        """One polygon per label of the first band, given the reducer's outputs over its pixels.
        The reducer gets the bands after the first, as Earth Engine's does (one fewer input than
        the image has bands); without one, countEvery (its default)."""
        self.vectorised.append({"bands": list(self.bands), **kw})
        reducer = kw.get("reducer") or _Reducer.countEvery()
        inputs = self.bands[1:]
        assert reducer.n_inputs() == len(inputs), (reducer.described(), inputs)
        out = []
        for label, count, geometry_centroid, (lon, lat) in POLYGONS:
            means = iter([{"longitude": lon, "latitude": lat}[band] for band in inputs])
            props: dict[str, Any] = {kw["labelProperty"]: label}
            for name in reducer.outputs():
                props[name] = count if name == "count" else next(means)
            out.append(_Feature(props, _Geometry(*geometry_centroid)))
        return _FC(out)

    def reduceRegions(self, collection: _FC, reducer: _Reducer, scale: int) -> _FC:  # noqa: N802
        new = {"canopy_height": 12.5} if reducer.kind == "mean" else {"mode": 1}
        return collection.map(lambda f: f.set(new))


class _Filter:
    @staticmethod
    def notNull(props: list[str]):  # noqa: N802 - mirrors the ee API
        return lambda f: all(f.props.get(p) is not None for p in props)

    @staticmethod
    def gte(prop: str, value: Any):
        return lambda f: _val(f.props[prop]) >= value


def _fake_ee(vectorised: list[dict[str, Any]]) -> type:
    class _ImageModule:
        @staticmethod
        def pixelLonLat() -> _Image:  # noqa: N802 - mirrors the ee API
            return _Image(["longitude", "latitude"], vectorised)

    class _FakeEE:
        Number = _Number
        List = _List
        Reducer = _Reducer
        Filter = _Filter
        Image = _ImageModule
        Feature = staticmethod(lambda f: f)
        FeatureCollection = staticmethod(lambda items: _FC(list(items)))

    return _FakeEE


@pytest.fixture
def fake(monkeypatch) -> list[dict[str, Any]]:
    """The fake Earth Engine in place; returns the record of every reduceToVectors call."""
    vectorised: list[dict[str, Any]] = []
    monkeypatch.setattr(export_mod, "ee", _fake_ee(vectorised))
    monkeypatch.setattr(
        export_mod, "_feature_source_image",
        lambda ctx: _Image(["canopy_height", "ndvi_obs_count"], vectorised),
    )
    # The stand types are not under test here (tests/test_export_stand_type_from_fit_row.py).
    monkeypatch.setattr(export_mod, "_stand_row_types", lambda *args: None)
    monkeypatch.setattr(export_mod, "_take_the_fit_rows_types", lambda fc, row_types: fc)
    return vectorised


# ---------------------------------------------------------------------------
# _add_geom_attrs: the centroid from the pixel centres
# ---------------------------------------------------------------------------


def test_stand_83_takes_the_mean_of_its_pixel_centres_not_its_geometrys_centroid(fake, stand_83):
    """The finding itself: before round 14 stand 83's centroid was the one centroid() gives its
    geometry, the committed one, 35 m off; now it is the mean of its pixel centres, which
    reduceToVectors puts on the polygon beside its pixel count."""
    lon, lat = stand_83["committed"]
    feature = _Feature(
        {
            "stand_lbl": 83,
            "count": stand_83["n_pixel_centres"],
            PIXEL_LON: stand_83["pixel_centres_mean"][0],
            PIXEL_LAT: stand_83["pixel_centres_mean"][1],
        },
        _Geometry(lon, lat, perimeter_m=stand_83["props"]["perim_m"]),
    )
    out = export_mod._add_geom_attrs(feature, SCALE_M).props
    centroid = (_val(out["centroid_lon"]), _val(out["centroid_lat"]))
    assert _metres(centroid, stand_83["holes_subtracted"]) < 0.01
    assert _val(out["n_pixels"]) == 823
    assert _val(out["perim_m"]) == stand_83["props"]["perim_m"]


def test_the_pixel_centres_means_are_dropped_with_the_count():
    """No new property is left on a layer: the two means go where 'count' goes."""
    assert {"count", "mode", PIXEL_LON, PIXEL_LAT} == set(export_mod._SNIC_INTERNAL_PROPERTIES_TO_DROP)


# ---------------------------------------------------------------------------
# The three builders
# ---------------------------------------------------------------------------

BUILDERS = [
    ("stands_merged", export_mod._build_merged_feature_collection, "stand_lbl", "stand_id",
     {"stand_lbl", "canopy_height", "area_ha", "perim_m", "n_pixels", "centroid_lat",
      "centroid_lon", "stand_id", "_sort_key"}),
    ("stands_snic", export_mod._build_snic_feature_collection, "snic_label", "stand_id",
     {"snic_label", "canopy_height", "cluster_id", "area_ha", "perim_m", "n_pixels",
      "centroid_lat", "centroid_lon", "stand_id", "_sort_key"}),
    ("stands_dissolved", export_mod._build_dissolved_feature_collection, "cluster_id", "unit_id",
     {"cluster_id", "area_ha", "perim_m", "n_pixels", "centroid_lat", "centroid_lon", "unit_id",
      "_sort_key"}),
]


def _build(builder, vectorised: list[dict[str, Any]]) -> _FC:
    cfg = load_config(BASELINE_YAML)
    cfg.export.vector_min_stand_pixels = 1
    ctx = PipelineContext()
    for key in ("stand_clusters", "snic_clusters", "cluster_labels"):
        ctx.set(key, _Image([key], vectorised))
    ctx.set("roi", "<roi>")
    ctx.set("cluster_profiles", [])
    return builder(ctx=ctx, config=cfg, scale=SCALE_M)


@pytest.mark.parametrize("layer, builder, label, id_field, columns", BUILDERS, ids=[b[0] for b in BUILDERS])
def test_every_builder_vectorises_the_label_with_the_pixel_coordinates_beside_it(
    fake, layer, builder, label, id_field, columns
):
    """One reduceToVectors call per layer: the label band first, pixelLonLat's two bands after
    it, and countEvery combined with the mean of each, named longitude first, as the two bands
    come; the count keeps its name, 'count', so area_ha and n_pixels are as before (review A6)."""
    _build(builder, fake)
    (call,) = fake
    assert call["bands"] == [label, "longitude", "latitude"]
    assert call["labelProperty"] == label
    assert call["reducer"].described() == ("combine", "countEvery", ("forEach", "mean", (PIXEL_LON, PIXEL_LAT)))
    assert call["reducer"].outputs() == ["count", PIXEL_LON, PIXEL_LAT]
    assert {k: call[k] for k in ("scale", "geometryType", "eightConnected", "maxPixels")} == {
        "scale": SCALE_M, "geometryType": "polygon", "eightConnected": True, "maxPixels": int(1e9)
    }


def _calls(node: Any, values: dict[str, Any]) -> Any:
    """An encoded Earth Engine expression as nested (function, {argument: ...}), constants as they are."""
    if isinstance(node, dict):
        if set(node) == {"valueReference"}:
            return _calls(values[node["valueReference"]], values)
        if set(node) == {"constantValue"}:
            return node["constantValue"]
        if set(node) == {"arrayValue"}:
            return [_calls(v, values) for v in node["arrayValue"]["values"]]
        if set(node) == {"functionInvocationValue"}:
            inv = node["functionInvocationValue"]
            return (inv["functionName"], {k: _calls(v, values) for k, v in inv.get("arguments", {}).items()})
    return node


def test_the_vectorisation_is_a_valid_request_for_the_real_client():
    """Offline, as tests/test_mask_before_snic_ee_graph.py: earthengine-api's own test
    initialisation loads the algorithm signatures it ships and sends nothing anywhere, so a
    misspelt argument or a wrong method fails here rather than on Earth Engine. The request is the
    label band with pixelLonLat added, and countEvery combined with the mean of each of its bands."""
    apitestcase = pytest.importorskip("ee.apitestcase")

    class _Offline(apitestcase.ApiTestCase):
        __test__ = False

        def runTest(self) -> None:  # noqa: N802 - unittest's name
            pass

    case = _Offline()
    case.setUp()
    try:
        import ee

        label = ee.Image("projects/fake/assets/stand_clusters").toInt().rename("stand_lbl")
        fc = export_mod._vectorise_with_pixel_centres(
            label, region=ee.Geometry.Rectangle([77.16, 28.51, 77.19, 28.55]), scale=SCALE_M,
            label_property="stand_lbl",
        )
        encoded = ee.serializer.encode(fc, for_cloud_api=True)
    finally:
        case.tearDown()
    name, args = _calls(encoded["values"][encoded["result"]], encoded["values"])
    assert name == "Image.reduceToVectors"
    assert args["image"] == ("Image.addBands", {
        "dstImg": ("Image.rename", {"input": ("Image.toInt", {"value": (
            "Image.load", {"id": "projects/fake/assets/stand_clusters"})}), "names": ["stand_lbl"]}),
        "srcImg": ("Image.pixelLonLat", {}),
    })
    assert args["reducer"] == ("Reducer.combine", {
        "reducer1": ("Reducer.countEvery", {}),
        "reducer2": ("Reducer.forEach", {"reducer": ("Reducer.mean", {}), "outputNames": [PIXEL_LON, PIXEL_LAT]}),
    })
    assert {k: args[k] for k in ("labelProperty", "scale", "geometryType", "eightConnected", "maxPixels")} == {
        "labelProperty": "stand_lbl", "scale": SCALE_M, "geometryType": "polygon",
        "eightConnected": True, "maxPixels": int(1e9),
    }


@pytest.mark.parametrize("layer, builder, label, id_field, columns", BUILDERS, ids=[b[0] for b in BUILDERS])
def test_every_layer_is_numbered_by_the_mean_of_its_pixel_centres(
    fake, layer, builder, label, id_field, columns
):
    """North first by the pixels: label 3, then 2, then 1, where the geometry's centroid() would
    number them 1, 2, 3. Each polygon's centroid is its pixel centres' mean, its area its count,
    and it carries the properties it carried before round 14, no more."""
    fc = _build(builder, fake)
    got = {f.props[label]: f.props for f in fc.features}
    assert {lbl: _val(p[id_field]) for lbl, p in got.items()} == {3: 1, 2: 2, 1: 3}
    for lbl, count, _, (lon, lat) in POLYGONS:
        p = got[lbl]
        assert (_val(p["centroid_lon"]), _val(p["centroid_lat"])) == (lon, lat)
        assert (_val(p["n_pixels"]), _val(p["area_ha"])) == (count, pytest.approx(count / 100))
        assert set(p) == columns

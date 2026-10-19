"""Non-live tests: a polygon's n_pixels and area_ha come from reduceToVectors' count (review A6, round 13).

Until round 13 the export took `area_ha` from the polygon's geometry (`area()`) and `n_pixels`
from that area at the analysis scale. For some polygons with a hole that touches the outer ring
at a vertex, Earth Engine's `area()` adds the hole instead of subtracting it: stand 83 of
`sanjay_van_alphaearth_keptland_r9` is 18.27 ha and 1,827 pixels in its committed layer
(docs/reproducibility/r9_runs/sanjay_van_alphaearth_keptland_r9_stands_merged.geojson), while
its planar area with its 5.01 ha hole subtracted is 8.23 ha and the merge record
(sanjay_van_alphaearth_keptland_r9_run.json, stand_attributes) gives 823 pixels. Now `n_pixels`
is the `count` reduceToVectors puts on every polygon, and `area_ha` is that count at the
analysis scale; the perimeter and the centroid are still the geometry's.

The builders must leave `count` on each polygon until `_add_geom_attrs` has read it: the
reductions between add their outputs beside it (a band's mean under the band's name, the vote
under "mode"), and `_drop_internal_properties` drops it only afterwards. That order is checked
here on a fake Earth Engine for all three layers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import fmu.stages.export as export_mod
from fmu.config import load_config
from fmu.stages.base import PipelineContext

REPO_ROOT = Path(__file__).parent.parent
BASELINE_YAML = REPO_ROOT / "configs" / "sanjay_van_baseline.yaml"

# Stand 83 of sanjay_van_alphaearth_keptland_r9, as its committed layer and its run record give it.
STAND_83_GEOMETRY_AREA_HA = 18.27041063087302
STAND_83_PERIMETER_M = 3699.4437069764995
STAND_83_COUNT = 823


class _Number:
    def __init__(self, value: Any):
        self.value = value.value if isinstance(value, _Number) else value

    def divide(self, other: Any) -> _Number:
        return _Number(self.value / _Number(other).value)

    def multiply(self, other: Any) -> _Number:
        return _Number(self.value * _Number(other).value)

    def round(self) -> _Number:
        return _Number(round(self.value))


class _Coordinates(list):
    def get(self, i: int) -> float:
        return self[i]


class _Geometry:
    def __init__(self, area_m2: float, perimeter_m: float, lon: float, lat: float):
        self.area_m2, self.perimeter_m, self.lon, self.lat = area_m2, perimeter_m, lon, lat

    def area(self, maxError: float) -> _Number:  # noqa: N803 - Earth Engine's name
        return _Number(self.area_m2)

    def perimeter(self, maxError: float) -> _Number:  # noqa: N803 - Earth Engine's name
        return _Number(self.perimeter_m)

    def centroid(self, maxError: float) -> Any:  # noqa: N803 - Earth Engine's name
        geometry = self

        class _Point:
            def coordinates(self) -> _Coordinates:
                return _Coordinates([geometry.lon, geometry.lat])

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


def _value(x: Any) -> Any:
    return x.value if isinstance(x, _Number) else x


@pytest.fixture
def number_ee(monkeypatch):
    class _FakeEE:
        Number = _Number
        Feature = staticmethod(lambda f: f)

    monkeypatch.setattr(export_mod, "ee", _FakeEE)


def test_stand_83_takes_its_pixel_count_not_its_geometrys_area(number_ee):
    """The finding itself: before round 13, n_pixels 1827 and area_ha 18.27; now 823 and 8.23."""
    stand_83 = _Feature(
        {"stand_lbl": 83, "count": STAND_83_COUNT},
        _Geometry(STAND_83_GEOMETRY_AREA_HA * 10_000, STAND_83_PERIMETER_M, 77.16255, 28.53196),
    )
    out = export_mod._add_geom_attrs(stand_83, 10)
    assert _value(out.props["n_pixels"]) == 823
    assert _value(out.props["area_ha"]) == pytest.approx(8.23, abs=1e-12)


def test_the_perimeter_and_the_centroid_are_still_the_geometrys(number_ee):
    out = export_mod._add_geom_attrs(
        _Feature({"count": 4}, _Geometry(400.0, 80.0, 77.1, 28.5)), 10
    )
    assert _value(out.props["perim_m"]) == 80.0
    assert (out.props["centroid_lon"], out.props["centroid_lat"]) == (77.1, 28.5)


@pytest.mark.parametrize("scale, count, area_ha", [(10, 1, 0.01), (10, 1000, 10.0), (30, 3, 0.27)])
def test_the_area_is_the_count_at_the_analysis_scale(number_ee, scale, count, area_ha):
    """The area on the analysis grid: count x scale^2 / 10,000, whatever the geometry's area()."""
    out = export_mod._add_geom_attrs(_Feature({"count": count}, _Geometry(1e9, 1.0, 0.0, 0.0)), scale)
    assert _value(out.props["n_pixels"]) == count
    assert _value(out.props["area_ha"]) == pytest.approx(area_ha, abs=1e-12)


# ---------------------------------------------------------------------------
# The order of operations in the three builders
# ---------------------------------------------------------------------------


class _FC:
    def __init__(self, features: list[_Feature]):
        self.features = features

    def map(self, fn):
        return _FC([fn(f) for f in self.features])

    def filter(self, predicate):
        return _FC([f for f in self.features if predicate(f)])


class _List(list):
    def removeAll(self, other):  # noqa: N802 - mirrors the ee API
        return _List(x for x in self if x not in set(other))


class _Reducer:
    def __init__(self, name: str):
        self.name = name

    @staticmethod
    def mean():
        return _Reducer("mean")

    @staticmethod
    def mode():
        return _Reducer("mode")


class _Filter:
    @staticmethod
    def notNull(props):  # noqa: N802 - mirrors the ee API
        return lambda f: all(f.props.get(p) is not None for p in props)

    @staticmethod
    def gte(prop, value):
        return lambda f: f.props[prop] >= value


# Each polygon reduceToVectors makes, as (label, count), and a count no reduction may overwrite.
POLYGONS = [(1, 7), (2, 1), (3, 40)]


class _Image:
    """Records nothing; gives every polygon its count, as reduceToVectors' countEvery does."""

    def toInt(self):  # noqa: N802 - mirrors the ee API
        return self

    def rename(self, name):
        return self

    def bandNames(self):  # noqa: N802 - mirrors the ee API
        return _List(["canopy_height", "ndvi_obs_count"])

    def select(self, bands):
        return self

    def reduceToVectors(self, **kw):  # noqa: N802 - mirrors the ee API
        return _FC([_Feature({kw["labelProperty"]: label, "count": n}) for label, n in POLYGONS])

    def reduceRegions(self, collection, reducer, scale):  # noqa: N802 - mirrors the ee API
        # As Earth Engine: the reducer's outputs are added beside the polygon's properties.
        new = {"canopy_height": 12.5} if reducer.name == "mean" else {"mode": 1}
        return collection.map(lambda f: f.set(new))


@pytest.mark.parametrize(
    "builder",
    [
        export_mod._build_merged_feature_collection,
        export_mod._build_snic_feature_collection,
        export_mod._build_dissolved_feature_collection,
    ],
    ids=["stands_merged", "stands_snic", "stands_dissolved"],
)
def test_every_builder_hands_add_geom_attrs_the_count_reducetovectors_gave(builder, monkeypatch):
    seen: list[int] = []

    def record(feature, scale):
        seen.append(feature.props["count"])
        return feature.set({"n_pixels": feature.props["count"]})

    class _FakeEE:
        Reducer = _Reducer
        Filter = _Filter
        Feature = staticmethod(lambda f: f)

        @staticmethod
        def List(items):  # noqa: N802 - mirrors the ee API
            return _List(items)

    monkeypatch.setattr(export_mod, "ee", _FakeEE)
    monkeypatch.setattr(export_mod, "_feature_source_image", lambda ctx: _Image())
    monkeypatch.setattr(export_mod, "_stand_row_types", lambda *args: None)
    monkeypatch.setattr(export_mod, "_take_the_fit_rows_types", lambda fc, row_types: fc)
    monkeypatch.setattr(export_mod, "_add_geom_attrs", record)
    monkeypatch.setattr(export_mod, "_renumber_by_centroid", lambda fc, *, id_field: fc)
    cfg = load_config(BASELINE_YAML)
    cfg.export.vector_min_stand_pixels = 1
    ctx = PipelineContext()
    for key in ("stand_clusters", "snic_clusters", "cluster_labels"):
        ctx.set(key, _Image())
    ctx.set("roi", "<roi>")
    ctx.set("cluster_profiles", [])

    fc = builder(ctx=ctx, config=cfg, scale=10)

    assert seen == [n for _, n in POLYGONS]
    for f in fc.features:
        assert "count" not in f.props, "count is bookkeeping, dropped after _add_geom_attrs read it"
        assert "mode" not in f.props
    assert [f.props["n_pixels"] for f in fc.features] == [n for _, n in POLYGONS]

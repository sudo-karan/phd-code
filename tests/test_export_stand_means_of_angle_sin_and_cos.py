"""Non-live tests: the stand layers give the stand means of each angle's sine and cosine (round 14).

In every stand layer the per-stand `aspect` and `ndvi_phase_annual` are plain means of the pixel
values, arithmetic means of angles (review C10): a stand whose pixels face 350 and 10 degrees
reads 180, south, not north. Round 13's question 33 was answered (a) for round 14: add the stand
means of each angle's sine and cosine as new columns (`aspect_sin`, `aspect_cos`,
`ndvi_phase_annual_sin`, `ndvi_phase_annual_cos`), counting a flat cell as no direction, as the
clustering does; the old columns keep their meaning (register entry
spec-export-stand-means-of-angle-sin-and-cos).

The angle bands and their sine and cosine are the clustering stage's, by its rule
(clustering._decompose_cyclic_bands): aspect, made radians from degrees, and every band with
"_phase_" in its name, in radians; a cell whose slope is 0 has the aspect pair (0, 0); a stack
with aspect and no slope is refused. Computed here per pixel on numpy stand-ins for the images
(tests/_ee_arrays.py) and averaged over each polygon's pixels, as reduceRegions' mean does, in
the merged and the superpixel layers. The embedding arm, which has no angle band, gets no new
column, and the shapefiles keep their columns (a name such as ndvi_phase_annual_sin is longer than
a shapefile's ten characters).
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pytest

import fmu.stages.clustering as clustering
import fmu.stages.export as export_mod
from _ee_arrays import Image, Value, install
from fmu.config import load_config
from fmu.stages.base import PipelineContext

REPO = Path(__file__).resolve().parent.parent
BASELINE_YAML = REPO / "configs" / "sanjay_van_baseline.yaml"
DEG = math.pi / 180.0

# One row of six cells, three stands of two cells each:
#   stand 1: aspects 350 and 10 degrees on slopes, phases 3.0 and -3.0 (both sides of +-pi);
#   stand 2: a flat cell (slope 0, aspect 0) and a slope facing due east, phases 0.5;
#   stand 3: two slopes facing due south, phases -1.0.
STACK = {
    "elevation": [[210.0, 212.0, 230.0, 232.0, 250.0, 252.0]],
    "slope": [[5.0, 5.0, 0.0, 4.0, 2.0, 2.0]],
    "aspect": [[350.0, 10.0, 0.0, 90.0, 180.0, 180.0]],
    "ndvi_phase_annual": [[3.0, -3.0, 0.5, 0.5, -1.0, -1.0]],
    "canopy_height": [[8.0, 10.0, 12.0, 14.0, 16.0, 18.0]],
    "ndvi_obs_count": [[40.0, 41.0, 42.0, 43.0, 44.0, 45.0]],
}
STANDS = {1: [(0, 0), (0, 1)], 2: [(0, 2), (0, 3)], 3: [(0, 4), (0, 5)]}
NEW = ("aspect_sin", "aspect_cos", "ndvi_phase_annual_sin", "ndvi_phase_annual_cos")


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


# What each stand's new columns must hold: the mean over its two cells of each cell's sine and
# cosine, the flat cell (stand 2's first) counted as (0, 0).
EXPECTED_NEW = {
    1: {"aspect_sin": _mean([math.sin(350 * DEG), math.sin(10 * DEG)]),
        "aspect_cos": _mean([math.cos(350 * DEG), math.cos(10 * DEG)]),
        "ndvi_phase_annual_sin": _mean([math.sin(3.0), math.sin(-3.0)]),
        "ndvi_phase_annual_cos": _mean([math.cos(3.0), math.cos(-3.0)])},
    2: {"aspect_sin": _mean([0.0, math.sin(90 * DEG)]),
        "aspect_cos": _mean([0.0, math.cos(90 * DEG)]),
        "ndvi_phase_annual_sin": math.sin(0.5),
        "ndvi_phase_annual_cos": math.cos(0.5)},
    3: {"aspect_sin": math.sin(180 * DEG), "aspect_cos": -1.0,
        "ndvi_phase_annual_sin": math.sin(-1.0), "ndvi_phase_annual_cos": math.cos(-1.0)},
}
# The old columns, plain means of the cells' values as before.
EXPECTED_OLD = {
    1: {"aspect": 180.0, "ndvi_phase_annual": 0.0, "slope": 5.0, "canopy_height": 9.0},
    2: {"aspect": 45.0, "ndvi_phase_annual": 0.5, "slope": 2.0, "canopy_height": 13.0},
    3: {"aspect": 180.0, "ndvi_phase_annual": -1.0, "slope": 2.0, "canopy_height": 17.0},
}


# ---------------------------------------------------------------------------
# A fake Earth Engine for the two builders: numpy images, polygons that know their pixels
# ---------------------------------------------------------------------------


class _Feature:
    def __init__(self, props: dict[str, Any], pixels: list[tuple[int, int]]):
        self.props, self.pixels = dict(props), pixels

    def get(self, name: str) -> Any:
        return self.props[name]

    def set(self, name: Any, value: Any = None) -> _Feature:
        new = dict(name) if isinstance(name, dict) else {name: value}
        return _Feature({**self.props, **new}, self.pixels)


class _FC:
    def __init__(self, features: list[_Feature]):
        self.features = list(features)

    def map(self, fn) -> _FC:
        return _FC([fn(f) for f in self.features])

    def filter(self, keep) -> _FC:
        return _FC([f for f in self.features if keep(f)])


class _Reducer:
    def __init__(self, kind: str):
        self.kind = kind

    @staticmethod
    def mean() -> _Reducer:
        return _Reducer("mean")

    @staticmethod
    def mode() -> _Reducer:
        return _Reducer("mode")


class _Filter:
    @staticmethod
    def notNull(props: list[str]):  # noqa: N802 - mirrors the ee API
        return lambda f: all(f.props.get(p) is not None for p in props)


class _ExportEE:
    """What the two builders reach of `ee` themselves; the decomposition runs on tests/_ee_arrays.py."""

    Reducer = _Reducer
    Filter = _Filter
    List = staticmethod(lambda items: list(items))
    Feature = staticmethod(lambda f: f)


def _reduce_regions(self: Image, collection: _FC, reducer: _Reducer, scale: int) -> _FC:
    """reduceRegions with the mean: each band's mean over the polygon's pixels where it has data,
    under the band's name, beside the polygon's properties."""
    assert reducer.kind == "mean"
    out = []
    for f in collection.features:
        means = {}
        for name, values in self.bands.items():
            have = [values[at] for at in f.pixels if self.masks[name][at]]
            if have:
                means[name] = float(np.mean(have))
        out.append(f.set(means))
    return _FC(out)


class _Types:
    """A label or type image: the type image gives every polygon type 0 (stands_snic)."""

    def toInt(self) -> _Types:  # noqa: N802 - mirrors the ee API
        return self

    def rename(self, name: str) -> _Types:
        return self

    def reduceRegions(self, collection: _FC, reducer: _Reducer, scale: int) -> _FC:  # noqa: N802
        assert reducer.kind == "mode"
        return collection.map(lambda f: f.set("mode", 0))


@pytest.fixture
def fake(monkeypatch):
    """Returns a function that builds a layer over a stack of the given bands."""
    install(monkeypatch, clustering)
    monkeypatch.setattr(export_mod, "ee", _ExportEE)
    monkeypatch.setattr(Image, "reduceRegions", _reduce_regions, raising=False)
    monkeypatch.setattr(
        Value, "removeAll", lambda self, other: Value([v for v in self.value if v not in set(other)]),
        raising=False,
    )
    # The polygons, their types, sizes and numbering are not under test here.
    monkeypatch.setattr(
        export_mod, "_vectorise_with_pixel_centres",
        lambda image, *, region, scale, label_property: _FC(
            [_Feature({label_property: s, "count": len(px)}, px) for s, px in STANDS.items()]
        ),
    )
    monkeypatch.setattr(export_mod, "_stand_row_types", lambda *args: None)
    monkeypatch.setattr(export_mod, "_take_the_fit_rows_types", lambda fc, row_types: fc)
    monkeypatch.setattr(export_mod, "_add_geom_attrs", lambda f, scale: f)
    monkeypatch.setattr(
        export_mod, "_drop_internal_properties",
        lambda f: _Feature({k: v for k, v in f.props.items() if k not in ("count", "mode")}, f.pixels),
    )
    monkeypatch.setattr(export_mod, "_renumber_by_centroid", lambda fc, *, id_field: fc)

    def build(builder, bands: dict[str, Any]) -> dict[int, dict[str, Any]]:
        stack = Image(bands)
        monkeypatch.setattr(export_mod, "_feature_source_image", lambda ctx: stack)
        ctx = PipelineContext()
        for key in ("stand_clusters", "snic_clusters", "cluster_labels"):
            ctx.set(key, _Types())
        ctx.set("roi", "<roi>")
        fc = builder(ctx=ctx, config=load_config(BASELINE_YAML), scale=10)
        label = "stand_lbl" if builder is export_mod._build_merged_feature_collection else "snic_label"
        return {f.props[label]: f.props for f in fc.features}

    return build


LAYERS = [
    ("stands_merged", export_mod._build_merged_feature_collection, "stand_lbl", set()),
    ("stands_snic", export_mod._build_snic_feature_collection, "snic_label", {"cluster_id"}),
]


# ---------------------------------------------------------------------------
# The tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("layer, builder, label, extra", LAYERS, ids=[x[0] for x in LAYERS])
def test_each_stand_has_the_means_of_its_angles_sine_and_cosine(fake, layer, builder, label, extra):
    """The change itself: four new columns, each the stand's mean of its cells' sine or cosine.
    Stand 1 faces north (cos 0.98), where its aspect reads 180, and its phases sit near pi (cos
    -0.99), where its ndvi_phase_annual reads 0."""
    got = fake(builder, STACK)
    for stand, want in EXPECTED_NEW.items():
        assert {k: got[stand].get(k) for k in NEW} == pytest.approx(want, abs=1e-12), stand


@pytest.mark.parametrize("layer, builder, label, extra", LAYERS, ids=[x[0] for x in LAYERS])
def test_a_flat_cell_counts_as_no_direction(fake, layer, builder, label, extra):
    """Stand 2: a flat cell and a slope facing due east. The flat cell's pair is (0, 0), so the
    stand's aspect vector is (0.5, 0): east, shortened by its share of flat cells. Counted as a
    slope facing north, (0, 1), it would be (0.5, 0.5), north-east."""
    got = fake(builder, STACK)[2]
    assert (got.get("aspect_sin"), got.get("aspect_cos")) == pytest.approx((0.5, 0.0), abs=1e-12)


@pytest.mark.parametrize("layer, builder, label, extra", LAYERS, ids=[x[0] for x in LAYERS])
def test_the_old_columns_keep_their_meaning(fake, layer, builder, label, extra):
    """The plain means stay, angles too, so a layer read as before reads the same; and the
    layer's columns are the old ones and the four new ones, no others."""
    got = fake(builder, STACK)
    old = {label, "elevation", "slope", "aspect", "ndvi_phase_annual", "canopy_height"} | extra
    for stand, want in EXPECTED_OLD.items():
        assert {k: got[stand][k] for k in want} == pytest.approx(want, abs=1e-12), stand
        assert old <= set(got[stand]) and set(got[stand]) - old <= set(NEW), stand


@pytest.mark.parametrize("layer, builder, label, extra", LAYERS, ids=[x[0] for x in LAYERS])
def test_the_columns_follow_the_rule_not_four_names(fake, layer, builder, label, extra):
    """A dual-harmonic NIRv stack gets the pairs of its own angle bands: aspect, nirv_phase_annual
    and nirv_phase_semi, each as <band>_sin and <band>_cos."""
    bands = {
        "slope": STACK["slope"],
        "aspect": STACK["aspect"],
        "nirv_phase_annual": STACK["ndvi_phase_annual"],
        "nirv_phase_semi": [[0.1, 0.2, 0.3, 0.4, 0.5, 0.6]],
        "nirv_amplitude_annual": [[0.2] * 6],
    }
    got = fake(builder, bands)[1]
    pairs = {f"{b}_{part}" for b in ("aspect", "nirv_phase_annual", "nirv_phase_semi") for part in ("sin", "cos")}
    assert set(got) - set(bands) - {label} - extra == pairs
    assert got["nirv_phase_semi_cos"] == pytest.approx(_mean([math.cos(0.1), math.cos(0.2)]), abs=1e-12)


@pytest.mark.parametrize("layer, builder, label, extra", LAYERS, ids=[x[0] for x in LAYERS])
def test_the_embedding_arm_gets_no_new_column(fake, layer, builder, label, extra):
    """No band of the embedding is an angle: its layers hold the band means alone, as before."""
    got = fake(builder, {"A00": [[0.1] * 6], "A01": [[-0.2] * 6], "A63": [[0.3] * 6]})
    for stand in STANDS:
        assert set(got[stand]) == {label, "A00", "A01", "A63"} | extra


@pytest.mark.parametrize("layer, builder, label, extra", LAYERS, ids=[x[0] for x in LAYERS])
def test_a_stack_with_aspect_and_no_slope_is_refused(fake, layer, builder, label, extra):
    """Which cells are flat is read from the slope, as in the clustering stage."""
    bands = {k: v for k, v in STACK.items() if k != "slope"}
    with pytest.raises(ValueError, match="slope"):
        fake(builder, bands)


def _function_names(node: Any) -> set[str]:
    """The names of the functions an encoded Earth Engine expression calls."""
    if isinstance(node, dict):
        found = {node["functionName"]} if isinstance(node.get("functionName"), str) else set()
        return found.union(*(_function_names(v) for v in node.values()))
    if isinstance(node, list):
        return set().union(*(_function_names(v) for v in node))
    return set()


def test_the_pairs_are_a_valid_request_for_the_real_client(monkeypatch):
    """Offline, as tests/test_mask_before_snic_ee_graph.py: earthengine-api's own test
    initialisation loads the algorithm signatures it ships and sends nothing anywhere, so a wrong
    method or argument fails here rather than on Earth Engine. The stack's band names, which the
    stage reads with one request, are given here."""
    apitestcase = pytest.importorskip("ee.apitestcase")

    class _Offline(apitestcase.ApiTestCase):
        __test__ = False

        def runTest(self) -> None:  # noqa: N802 - unittest's name
            pass

    bands = ["elevation", "slope", "aspect", "ndvi_phase_annual", "canopy_height"]
    case = _Offline()
    case.setUp()
    try:
        import ee

        monkeypatch.setattr(clustering, "safe_get_info", lambda obj, context="": list(bands))
        stack = ee.Image("projects/fake/assets/features").select(bands)
        encoded = ee.serializer.encode(export_mod._with_angle_sin_cos(stack), for_cloud_api=True)
    finally:
        case.tearDown()
    called = _function_names(encoded)
    assert {"Image.sin", "Image.cos", "Image.eq", "Image.where", "Image.addBands", "Image.select"} <= called


def test_the_shapefiles_keep_their_columns():
    """The new columns are in the GeoJSON only: a shapefile's field names stop at ten characters,
    and the selectors are unchanged."""
    assert export_mod._SHP_SELECTORS_MERGED == ("stand_id", "stand_lbl", "cluster_id", "area_ha", "perim_m", "n_pixels")
    assert export_mod._SHP_SELECTORS_SNIC == ("stand_id", "snic_label", "cluster_id", "area_ha", "perim_m", "n_pixels")
    assert export_mod._SHP_SELECTORS_DISSOLVED == ("unit_id", "cluster_id", "area_ha", "perim_m", "n_pixels")
    assert max(len(n) for n in NEW) > 10

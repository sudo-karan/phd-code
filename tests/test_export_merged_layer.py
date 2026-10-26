"""Non-live tests for the merged-stand vector layer.

The layer exists because a full pipeline run exported seven files and none of
them was the thing the pipeline produces. `export.py` read `snic_clusters`
directly rather than `config.unit_label_key()`, so it never learned that merge
had run: `stands_snic` held the 1302 pre-merge superpixels and
`stands_dissolved` held dissolve-by-cluster-id, the layer the merge design
replaces. The 327 merged stands were computed, logged, and then dropped on the
floor.

Nothing failed. Every stage reported success. That is what these pin.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import fmu.stages.export as export_mod
from fmu.config import load_config
from fmu.stages.base import PipelineContext
from fmu.stages.export import (
    _SHP_SELECTORS_MERGED,
    _SHP_SELECTORS_SNIC,
    ExportStage,
)
from fmu.utils.region_merge import PROVENANCE_FIELDS

REPO_ROOT = Path(__file__).parent.parent
BASELINE_YAML = REPO_ROOT / "configs" / "sanjay_van_baseline.yaml"
ALPHAEARTH_YAML = REPO_ROOT / "configs" / "sanjay_van_alphaearth.yaml"

_INVARIANT = {
    "roi",
    "cluster_labels",
    "feature_stack",
    "snic_clusters",
    "stand_clusters",
    "cluster_profiles",
}
_HANDCRAFTED = {
    "optical_features",
    "radar_features",
    "structure_features",
    "static_features",
}


def _ctx(keys):
    ctx = PipelineContext()
    for k in keys:
        ctx.set(k, f"<{k}>")
    return ctx


# ---------- configuration ----------


@pytest.mark.parametrize("path", [BASELINE_YAML, ALPHAEARTH_YAML])
def test_both_shipped_configs_export_the_merged_layer(path):
    cfg = load_config(path)
    assert cfg.export.export_vector_merged is True
    assert cfg.merge.enabled is True
    assert cfg.unit_label_key() == "stand_clusters"


def test_shp_field_names_fit_the_ten_character_limit():
    """SHP silently truncates longer names, which would rename the column
    without saying so."""
    for name in _SHP_SELECTORS_MERGED:
        assert len(name) <= 10, name


def test_the_merged_layer_carries_the_raw_merge_label():
    """`stand_id` is a renumbering, so it cannot be joined back to the
    `stand_clusters` raster. `stand_lbl` is what makes the vector and raster
    exports refer to the same objects."""
    assert "stand_lbl" in _SHP_SELECTORS_MERGED
    assert "stand_id" in _SHP_SELECTORS_MERGED


# ---------- the stage contract ----------


def test_export_requires_the_merge_output_when_merge_ran():
    cfg = load_config(BASELINE_YAML)
    ExportStage().validate(_ctx(_INVARIANT | _HANDCRAFTED), cfg)
    with pytest.raises(KeyError, match="stand_clusters"):
        ExportStage().validate(_ctx((_INVARIANT - {"stand_clusters"}) | _HANDCRAFTED), cfg)


def test_export_does_not_require_it_when_merge_is_off():
    """Without merge the key does not exist, and demanding it would break every
    merge-disabled config rather than just skipping a layer."""
    cfg = load_config(BASELINE_YAML)
    cfg.merge.enabled = False
    assert cfg.unit_label_key() == "snic_clusters"
    ExportStage().validate(_ctx((_INVARIANT - {"stand_clusters"}) | _HANDCRAFTED), cfg)


# ---------- the deliberate difference from stands_snic ----------


class _FakeList:
    def __init__(self, items):
        self.items = list(items)

    def removeAll(self, other):  # noqa: N802 - mirrors the ee API
        drop = set(other.items if isinstance(other, _FakeList) else other)
        return _FakeList([i for i in self.items if i not in drop])


class _FakeFC:
    """Records what the builder does to the collection."""

    def __init__(self, calls):
        self.calls = calls

    def map(self, fn):
        self.calls.append("map")
        return self

    def filter(self, f):
        self.calls.append("filter")
        return self


class _FakeImage:
    def __init__(self, calls, bands=("canopy_height",)):
        self.calls = calls
        self._bands = list(bands)

    def toInt(self):  # noqa: N802 - mirrors the ee API
        return self

    def rename(self, name):
        self.calls.append(("rename", name))
        return self

    def bandNames(self):  # noqa: N802 - mirrors the ee API
        return _FakeList(self._bands)

    def select(self, bands):
        return self

    def reduceToVectors(self, **kw):  # noqa: N802 - mirrors the ee API
        self.calls.append(("labelProperty", kw.get("labelProperty")))
        return _FakeFC(self.calls)

    def reduceRegions(self, **kw):  # noqa: N802 - mirrors the ee API
        return _FakeFC(self.calls)


@pytest.fixture
def fake_ee(monkeypatch):
    class _Reducer:
        @staticmethod
        def mean():
            return object()

        @staticmethod
        def mode():
            return object()

    class _Filter:
        @staticmethod
        def notNull(props):  # noqa: N802 - mirrors the ee API
            return object()

    class _FakeEE:
        Reducer = _Reducer
        Filter = _Filter
        List = _FakeList

    monkeypatch.setattr(export_mod, "ee", _FakeEE)
    # Not under test here, and its server-side sort/iterate chain would need a
    # far larger fake than the question warrants.
    monkeypatch.setattr(
        export_mod, "_renumber_by_centroid", lambda fc, *, id_field: fc
    )
    # Nor is the type each stand takes from its own row (rounds 12 and 13), which
    # tests/test_export_stand_type_from_fit_row.py runs on a fake raster. Here the
    # request for the row types is recorded where the builder makes it.
    monkeypatch.setattr(
        export_mod,
        "_stand_row_types",
        lambda cluster_labels, unit_labels, region, scale: cluster_labels.calls.append(
            "stand_row_types"
        ),
    )
    return _FakeEE


def _run_builder(builder, calls, monkeypatch):
    img = _FakeImage(calls)
    monkeypatch.setattr(export_mod, "_feature_source_image", lambda ctx: img)
    cfg = load_config(BASELINE_YAML)
    ctx = PipelineContext()
    for key in ("stand_clusters", "snic_clusters", "cluster_labels", "roi"):
        ctx.set(key, img)
    return builder(ctx=ctx, config=cfg, scale=10)


def test_the_merged_layer_keeps_stands_clustering_could_not_type(fake_ee, monkeypatch):
    """The whole point of keeping them.

    A stand exists because SNIC and merge delineated it; clustering only
    attaches a type label afterwards. Filtering on a null cluster_id would drop
    real delineated area from the deliverable and leave the file looking
    complete -- a run that fit k-means on 289 of 327 stands would have exported
    289 polygons with nothing to say the other 38 were gone.
    """
    calls: list = []
    _run_builder(export_mod._build_merged_feature_collection, calls, monkeypatch)
    assert "filter" not in calls, (
        "stands_merged must not drop unclustered stands; cluster_id is null on "
        "them instead"
    )


def test_the_snic_layer_still_drops_them(fake_ee, monkeypatch):
    """The contrast that makes the choice above deliberate rather than an
    oversight: stands_snic's job is tracing *clustered* polygons back to their
    superpixels, so an unclustered one has no place in it."""
    calls: list = []
    _run_builder(export_mod._build_snic_feature_collection, calls, monkeypatch)
    assert "filter" in calls


def test_the_merged_layer_vectorises_the_merge_output(fake_ee, monkeypatch):
    calls: list = []
    _run_builder(export_mod._build_merged_feature_collection, calls, monkeypatch)
    assert ("labelProperty", "stand_lbl") in calls
    assert ("rename", "stand_lbl") in calls


def test_the_snic_layer_still_vectorises_snic(fake_ee, monkeypatch):
    calls: list = []
    _run_builder(export_mod._build_snic_feature_collection, calls, monkeypatch)
    assert ("labelProperty", "snic_label") in calls


def test_the_two_layers_are_not_the_same_layer():
    """They were, in effect, before this: stands_snic was the only per-unit
    polygon layer and it held superpixels."""
    assert export_mod._MERGED_LAYER_NAME != export_mod._SNIC_LAYER_NAME
    assert _SHP_SELECTORS_MERGED != _SHP_SELECTORS_SNIC


# ---------- merge provenance on the merged layer ----------

# What the merge stage puts in the context: stand id -> provenance.
_PROVENANCE = {
    0: {"n_superpx": 1, "n_pass1": 0, "n_relaxed": 0, "n_fallback": 0,
        "below_min": 1, "below_why": "isolated"},
    1: {"n_superpx": 5, "n_pass1": 2, "n_relaxed": 1, "n_fallback": 1,
        "below_min": 0, "below_why": ""},
}


def test_provenance_fields_fit_the_shapefile_and_clash_with_no_column():
    for name in PROVENANCE_FIELDS:
        assert len(name) <= 10, name
    assert not set(PROVENANCE_FIELDS) & set(_SHP_SELECTORS_MERGED)
    assert not set(PROVENANCE_FIELDS) & {"centroid_lat", "centroid_lon", "mode", "count"}


def test_no_shipped_config_merges_on_a_band_named_like_a_provenance_field():
    """Every config in configs/: no merge criterion band has one of the six
    names.

    This covers the merge criteria only. The GeoJSON also carries a per-stand
    mean of every features_* band, and those names exist only on the server, so
    no offline test can list them; `_attach_stand_provenance` would overwrite a
    property with one of these names. (Checked by hand on 2026-10-13: none of
    the 94 property names in the 19 committed stands_merged files is one.)
    """
    paths = sorted((REPO_ROOT / "configs").glob("*.yaml"))
    assert BASELINE_YAML in paths and ALPHAEARTH_YAML in paths
    for path in paths:
        cfg = load_config(path)
        bands = {c.band for c in cfg.merge.criteria}
        assert not bands & set(PROVENANCE_FIELDS), path.name


def test_the_layer_carries_provenance_only_when_the_merge_supplied_it():
    ctx = _ctx(_INVARIANT)
    assert export_mod._stand_provenance_fields(ctx) == ()
    ctx.set("stand_provenance", _PROVENANCE)
    assert export_mod._stand_provenance_fields(ctx) == PROVENANCE_FIELDS


def test_export_does_not_require_the_provenance():
    """A context without it still validates: the layer is then written as it
    was before, rather than the export failing."""
    cfg = load_config(BASELINE_YAML)
    assert "stand_provenance" not in ExportStage.required_inputs
    ExportStage().validate(_ctx(_INVARIANT | _HANDCRAFTED), cfg)


def test_without_provenance_the_builder_makes_these_calls_and_no_more(
    fake_ee, monkeypatch
):
    """The builder's calls with no `stand_provenance` in the context: the rename
    and the vectorisation of the stand labels, the request for the stands' row
    types, the map that sets each stand's cluster_id from them, and the two maps
    of geometry and bookkeeping, and nothing after them: no provenance step.
    Since round 13 there is no vote (no rename to cluster_id and no map naming
    the vote cluster_id): a stand with no row gets a null type."""
    calls: list = []
    _run_builder(export_mod._build_merged_feature_collection, calls, monkeypatch)
    assert calls == [
        ("rename", "stand_lbl"),
        ("labelProperty", "stand_lbl"),
        "stand_row_types",
        "map",
        "map",
        "map",
    ]


class _Feature:
    """A feature as a dict of properties plus a geometry that must not change."""

    def __init__(self, props, geometry):
        self.props, self.geometry = dict(props), geometry

    def get(self, name):
        return self.props[name]

    def set(self, new):
        return _Feature({**self.props, **new}, self.geometry)


class _MappedFC:
    def __init__(self, features):
        self.features = features

    def map(self, fn):
        return _MappedFC([fn(f) for f in self.features])


@pytest.fixture
def lookup_ee(monkeypatch):
    """Enough of `ee` for the server-side lookup to run in Python."""

    class _Number:
        def __init__(self, value):
            self.value = value

        def format(self, pattern):
            return pattern % self.value

    class _Dictionary(dict):
        def get(self, key):  # an unknown key is an error, as it is server-side
            return self[key]

    class _FakeEE:
        Number = _Number
        Dictionary = _Dictionary
        Feature = staticmethod(lambda f: f)

    monkeypatch.setattr(export_mod, "ee", _FakeEE)


def test_every_polygon_gets_its_stands_provenance_and_keeps_everything_else(lookup_ee):
    """Looked up by `stand_lbl`, the merge's own id -- not `stand_id`, which is a
    renumbering of polygons. Stand 1 is in two pieces; both carry its values."""
    before = [
        _Feature({"stand_id": 1, "stand_lbl": 1, "cluster_id": 2, "area_ha": 3.5}, "<g1>"),
        _Feature({"stand_id": 2, "stand_lbl": 0, "cluster_id": None, "area_ha": 0.4}, "<g2>"),
        _Feature({"stand_id": 3, "stand_lbl": 1, "cluster_id": 2, "area_ha": 0.1}, "<g3>"),
    ]
    ctx = PipelineContext()
    ctx.set("stand_provenance", _PROVENANCE)

    after = export_mod._attach_stand_provenance(_MappedFC(before), ctx).features

    assert len(after) == len(before)
    for old, new in zip(before, after, strict=True):
        assert new.geometry is old.geometry
        assert {k: new.props[k] for k in old.props} == old.props
        assert set(new.props) - set(old.props) == set(PROVENANCE_FIELDS)
        assert {k: new.props[k] for k in PROVENANCE_FIELDS} == _PROVENANCE[old.props["stand_lbl"]]
    assert after[0].props["n_fallback"] == after[2].props["n_fallback"] == 1
    assert after[1].props["below_why"] == "isolated"


def test_a_polygon_whose_stand_has_no_provenance_fails_the_layer(lookup_ee):
    """A `stand_lbl` that is not in `stand_provenance` is an error, not a
    polygon with blank provenance: the lookup has no default. Server-side,
    `ee.Dictionary.get` on a missing key fails the same way. Not reachable in a
    pipeline run (the merge stage writes both from one result); pinned so that
    nobody adds a default that would hide a mixed-up context."""
    fc = _MappedFC([_Feature({"stand_lbl": 0}, "<g0>"), _Feature({"stand_lbl": 7}, "<g7>")])
    ctx = PipelineContext()
    ctx.set("stand_provenance", _PROVENANCE)
    with pytest.raises(KeyError, match="7"):
        export_mod._attach_stand_provenance(fc, ctx)


def test_without_provenance_the_collection_is_returned_untouched(lookup_ee):
    fc = _MappedFC([_Feature({"stand_lbl": 0}, "<g>")])
    assert export_mod._attach_stand_provenance(fc, PipelineContext()) is fc


def test_the_shapefile_export_and_the_manifest_list_the_provenance_fields():
    """The shapefile export names its columns; a property left out of the
    selectors would be on the GeoJSON and silently missing from the shapefile."""
    import inspect

    src = inspect.getsource(export_mod.ExportStage.run)
    assert "provenance_fields = _stand_provenance_fields(ctx)" in src
    assert src.count("[*_SHP_SELECTORS_MERGED, *provenance_fields]") == 2
    assert '"provenance_attributes": list(provenance_fields)' in src


# ---------- the GeoTIFF exports ----------


def test_the_multiband_rasters_are_cast_to_one_type():
    """`Exported bands must have compatible data types; found inconsistent
    types: Float64 and Int32.`

    GeoTIFF does not cast a mixed-type image to a common type -- a comment in
    this file used to claim it did. EE rejects it, and rejects it
    *asynchronously*: the stage reported success, the task failed three seconds
    in, and the file simply never arrived in Drive. Both multiband rasters bolt
    an integer `cluster_id` onto float feature bands, so both need the cast.
    """
    import inspect

    src = inspect.getsource(export_mod.ExportStage.run)
    raster_block = src[src.index("raster_specs = ["): src.index("for manifest_key")]

    for spec in ("_build_raw_feature_export_image(ctx)", 'ctx.get("feature_stack")'):
        line = next(ln for ln in raster_block.splitlines() if spec in ln)
        assert ".toFloat()" in line, f"{spec} reaches GeoTIFF export uncast: {line.strip()}"


def test_the_single_band_label_raster_stays_an_integer():
    """The multiband rasters carry cluster_id as a float for compatibility, so
    the uint8 raster is the only place the labels survive as exact integers.
    Casting it to float too would leave none."""
    import inspect

    src = inspect.getsource(export_mod.ExportStage.run)
    line = next(ln for ln in src.splitlines() if "toUint8()" in ln)
    assert ".toFloat()" not in line

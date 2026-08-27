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

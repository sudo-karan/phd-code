"""Non-live tests for the merge stage's wiring.

The algorithm itself is covered in `test_region_merge.py` and the graph
extraction in `test_adjacency.py`. What is pinned here is the contract between
them and the rest of the pipeline: the stage declaration, the config-driven
dependency check, the unit key every downstream stage has to agree on, and the
diagnostics that turn a bad threshold choice into a legible warning rather than
a silently odd stand map.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import fmu.stages.merge as merge_module
from fmu.config import Config, load_config
from fmu.pipeline import default_stage_names
from fmu.stages.base import PipelineContext, Stage, get_stage_class
from fmu.stages.clustering import ClusteringStage
from fmu.stages.merge import (
    MergeStage,
    _warnings_from,
    merge_kind_code,
    summarise_merge_diagnostics,
)
from fmu.stages.metrics import MetricsStage
from fmu.utils.adjacency import SuperpixelGraph
from fmu.utils.gee import LABEL_BAND, check_band_name
from fmu.utils.region_merge import PROVENANCE_FIELDS, merge_superpixels

REPO_ROOT = Path(__file__).parent.parent
CONFIG_DIR = REPO_ROOT / "configs"
BASELINE_YAML = CONFIG_DIR / "sanjay_van_baseline.yaml"
ALPHAEARTH_YAML = CONFIG_DIR / "sanjay_van_alphaearth.yaml"


def _ctx_with(keys: set[str]) -> PipelineContext:
    ctx = PipelineContext()
    for k in keys:
        ctx.set(k, f"<{k}>")
    return ctx


def _cfg(**merge_overrides) -> Config:
    raw = yaml.safe_load(BASELINE_YAML.read_text())
    if merge_overrides:
        raw["merge"] = {**raw.get("merge", {}), **merge_overrides}
    return Config.model_validate(raw)


# ---------- stage declaration ----------


def test_merge_is_registered():
    assert get_stage_class("merge") is MergeStage


def test_merge_produces_the_stand_layer():
    assert MergeStage.produces == {
        "stand_clusters",
        "stand_attributes",
        "merge_diagnostics",
        "stand_provenance",
        "merge_provenance",
    }


def test_diagnostics_travel_through_context_not_just_the_manifest():
    """The orphan split and the threshold calibration are results, not log
    lines. Metrics folds them into metrics_<config>.json so reading them does
    not require manifest archaeology."""
    assert "merge_diagnostics" in MergeStage.produces


def test_merge_is_not_cached():
    """Deliberate. Caching it would need the merge config hashed into the key,
    and thresholds are the main thing being iterated on -- a stale cache would
    silently poison exactly the experiment being run. The image is a remap of a
    cached asset, so rebuilding it is cheap."""
    assert MergeStage.cacheable_outputs == set()


def test_required_inputs_is_the_invariant_subset_only():
    """The criteria bands' sources depend on `merge.criteria`, which a static
    class attribute cannot see."""
    assert MergeStage.required_inputs == {"roi", "snic_clusters"}


# ---------- validate() ----------


def test_validate_passes_with_the_configured_criterion_sources():
    cfg = _cfg()
    MergeStage().validate(
        _ctx_with({"roi", "snic_clusters"} | cfg.merge.input_sources()), cfg
    )


def test_validate_raises_on_a_missing_criterion_source():
    cfg = _cfg()
    ctx = _ctx_with(
        {"roi", "snic_clusters"} | cfg.merge.input_sources() - {"optical_features"}
    )
    with pytest.raises(KeyError, match="optical_features"):
        MergeStage().validate(ctx, cfg)


def test_validate_error_points_at_the_config_key():
    cfg = _cfg()
    with pytest.raises(KeyError, match="merge.criteria"):
        MergeStage().validate(_ctx_with({"roi", "snic_clusters"}), cfg)


def test_validate_follows_a_changed_criterion_source():
    """Swap in a radar criterion and the stage should demand radar_features."""
    cfg = _cfg(
        criteria=[
            {"source": "structure_features", "band": "canopy_height", "tolerance": 2.0},
            {
                "source": "radar_features",
                "band": "vv_minus_vh_median",
                "tolerance": 0.65,
            },
        ]
    )
    with pytest.raises(KeyError, match="radar_features"):
        MergeStage().validate(
            _ctx_with({"roi", "snic_clusters", "structure_features"}), cfg
        )


# ---------- the unit key every downstream stage shares ----------


def test_unit_key_is_stands_when_merge_runs():
    assert _cfg().unit_label_key() == "stand_clusters"


def test_unit_key_falls_back_to_superpixels_when_merge_is_off():
    assert _cfg(enabled=False).unit_label_key() == "snic_clusters"


def test_clustering_labels_stands_not_superpixels():
    """Clustering is demoted to attaching a type label to a finished stand, so
    it must reduce over `stand_clusters`."""
    cfg = _cfg()
    base = {"roi", "habitat_mask"} | {
        "optical_features",
        "radar_features",
        "structure_features",
        "static_features",
    }
    ClusteringStage().validate(_ctx_with(base | {"stand_clusters"}), cfg)
    with pytest.raises(KeyError, match="stand_clusters"):
        ClusteringStage().validate(_ctx_with(base | {"snic_clusters"}), cfg)


def test_clustering_falls_back_to_superpixels_when_merge_is_off():
    cfg = _cfg(enabled=False)
    base = {"roi", "habitat_mask"} | {
        "optical_features",
        "radar_features",
        "structure_features",
        "static_features",
    }
    ClusteringStage().validate(_ctx_with(base | {"snic_clusters"}), cfg)


def test_metrics_uses_the_same_unit_key():
    """A silhouette over stands and a profile over superpixels are not
    comparable, and nothing in the numbers would say so -- so every stage must
    read the same key."""
    cfg = _cfg()
    base = {"roi", "cluster_labels", "habitat_mask"}
    MetricsStage().validate(_ctx_with(base | {"stand_clusters"}), cfg)
    with pytest.raises(KeyError, match="stand_clusters"):
        MetricsStage().validate(_ctx_with(base | {"snic_clusters"}), cfg)


# ---------- pipeline placement ----------


def test_merge_sits_between_segmentation_and_clustering():
    stages = default_stage_names(_cfg())
    assert stages.index("segmentation") < stages.index("merge") < stages.index(
        "clustering"
    )


def test_disabling_merge_removes_it_from_every_tail():
    cfg = _cfg(enabled=False)
    for through in ("clustering", "profiling", "export", "metrics"):
        assert "merge" not in default_stage_names(cfg, through=through)


def test_merge_criteria_pull_in_their_feature_stages():
    """An embedding run still computes canopy height and NDVI amplitude, purely
    because the merge gate reads them -- the merge rule is held identical across
    arms so that delineation is the only thing differing."""
    stages = default_stage_names(load_config(ALPHAEARTH_YAML))
    assert "features_structure" in stages
    assert "features_optical" in stages
    for stage in ("features_structure", "features_optical"):
        assert stages.index(stage) < stages.index("merge")


# ---------- diagnostics -> warnings ----------


class _Params:
    min_area_ha = 1.0
    max_area_ha = 10.0
    min_frac_valid = 0.5
    max_pass2_iterations = 60


_CLEAN = {
    "orphans_area_blocked": 0,
    "orphans_isolated": 0,
    "orphans_no_attribute_match": 0,
    "stands_with_incomplete_criteria": 0,
    "pass2_fallback_merges": 0,
    "pass2_merges": 0,
    "n_stands": 100,
    "n_superpixels": 1000,
}


def test_clean_run_produces_no_warnings():
    assert _warnings_from(dict(_CLEAN), _Params()) == []


def test_area_blocked_orphans_name_the_right_cause():
    """The distinction that matters: area-blocked means max_area_ha is too
    tight, which is a config fix, not a fact about the forest."""
    w = _warnings_from({**_CLEAN, "orphans_area_blocked": 163}, _Params())
    assert len(w) == 1
    assert "max_area_ha" in w[0]
    assert "too tight" in w[0]


def test_isolated_orphans_are_reported_separately():
    w = _warnings_from({**_CLEAN, "orphans_isolated": 3}, _Params())
    assert len(w) == 1
    assert "no 4-connected neighbour" in w[0]


def test_iteration_cap_is_reported_as_such():
    w = _warnings_from({**_CLEAN, "orphans_no_attribute_match": 2}, _Params())
    assert "ran out of its 60 iterations" in w[0]


def test_incomplete_criteria_are_surfaced():
    w = _warnings_from({**_CLEAN, "stands_with_incomplete_criteria": 14}, _Params())
    assert "null rather than as a mean" in w[0]


def test_fallback_merges_are_surfaced():
    w = _warnings_from(
        {**_CLEAN, "pass2_fallback_merges": 40, "pass2_merges": 50}, _Params()
    )
    assert "shared-edge fallback" in w[0]


def test_no_merging_at_all_is_loud():
    """Silent identity is the failure mode most likely to be mistaken for a
    working run: every stand map looks plausible at 1249 units."""
    w = _warnings_from({**_CLEAN, "n_stands": 1000, "n_superpixels": 1000}, _Params())
    assert any("No superpixels merged" in x for x in w)


# ---------- summary numbers (the transparency contract) ----------

# What `merge_superpixels` reports for a run of 1000 superpixels into 100
# stands, written out by hand: 700 first-pass merges and 200 second-pass ones,
# 40 of those by the shared-edge fallback, and 12 stands left below the minimum
# size holding 4.25 ha.
_DIAGNOSTICS = {
    "n_superpixels": 1000,
    "n_stands": 100,
    "reduction_factor": 10.0,
    "pass1_rounds": 9,
    "pass1_merges": 700,
    "pass1_pairs_blocked_by_area_round1": 31,
    "pass1_pairs_blocked_by_undefined_criteria_round1": 4,
    "pass2_iterations": 3,
    "pass2_merges": 200,
    "pass2_fallback_merges": 40,
    "stands_below_min_area": 12,
    "area_in_undersized_stands_ha": 4.25,
    "orphans_isolated": 2,
    "orphans_area_blocked": 9,
    "orphans_no_attribute_match": 1,
    "stands_with_incomplete_criteria": 5,
}

_SUMMARY = {
    "superpixels_in": 1000,
    "stands_out": 100,
    "merges_first_pass": 700,
    "merges_second_pass_relaxed": 160,
    "merges_second_pass_shared_edge_fallback": 40,
    "stands_below_min_area": 12,
    "stands_below_min_area_by_cause": {
        "isolated": 2,
        "area_blocked": 9,
        "iteration_cap": 1,
    },
    "area_ha_in_stands_below_min_area": 4.25,
}


def test_merge_declares_its_summary_numbers():
    assert [s.name for s in MergeStage.summary_numbers] == list(_SUMMARY)
    for number in MergeStage.summary_numbers:
        assert number.description and number.unit


def test_summarise_turns_the_diagnostics_into_the_declared_numbers():
    assert summarise_merge_diagnostics(_DIAGNOSTICS) == _SUMMARY


def test_second_pass_merges_are_split_not_double_counted():
    """`pass2_merges` includes the fallback merges. Reported side by side they
    would read as 200 + 40; split, the three counts are the whole account."""
    s = summarise_merge_diagnostics(_DIAGNOSTICS)
    assert (
        s["merges_second_pass_relaxed"] + s["merges_second_pass_shared_edge_fallback"]
        == _DIAGNOSTICS["pass2_merges"]
    )


class _NoEarthEngine:
    """Stands in for the `ee` module: any use of it fails the test."""

    def __getattr__(self, name: str):
        raise AssertionError(f"summarise() touched Earth Engine: ee.{name}")


def test_summarise_reads_the_context_and_makes_no_earth_engine_call(monkeypatch):
    """It runs after the stage, on a live run or not, so it may only read what
    is in the context. The merge already counted everything it reports."""
    monkeypatch.setattr(merge_module, "ee", _NoEarthEngine())
    ctx = PipelineContext()
    # What the stage puts in the context: the diagnostics plus the three keys
    # the stage adds on top. summarise() must not mind the extras.
    ctx.set(
        "merge_diagnostics",
        {**_DIAGNOSTICS, "adjacency": {}, "threshold_calibration": {}, "warnings": []},
    )

    numbers = MergeStage().summarise(ctx, _cfg())

    assert numbers == _SUMMARY
    assert set(numbers) == {s.name for s in MergeStage.summary_numbers}


def test_summarise_needs_the_stage_to_have_run():
    with pytest.raises(KeyError, match="merge_diagnostics"):
        MergeStage().summarise(PipelineContext(), _cfg())


def test_summary_numbers_account_for_a_real_merge():
    """The same numbers from the merge itself, on a graph built to take every
    path: one first-pass merge, one relaxed second-pass merge, one shared-edge
    fallback, one stand with no neighbour and one blocked by the maximum size.

    Each merge joins two regions into one, so what went in minus what came out
    has to be the three merge counts added together.
    """
    # 1 ha at 10 m = 100 px.
    n_pixels = [300, 300, 50, 60, 40, 980, 30]
    rows = [
        {"ch": 10.0, "std": 0.5},  # 0: merges with 1 in the first pass
        {"ch": 10.5, "std": 0.5},  # 1
        {"ch": 13.0, "std": 0.5},  # 2: small; joins 0+1 under relaxed tolerances
        {"ch": 30.0, "std": 2.0},  # 3: small, unlike 0+1; joins it by the fallback
        {"ch": 20.0, "std": 1.0},  # 4: small, touches nothing
        {"ch": 50.0, "std": 5.0},  # 5: 9.8 ha, so nothing fits beside it
        {"ch": 80.0, "std": 9.0},  # 6: small, its only neighbour is 5
    ]
    graph = SuperpixelGraph(
        raw_labels=list(range(100, 107)),
        n_pixels=n_pixels,
        edges={(0, 1): 10, (0, 2): 5, (1, 3): 5, (5, 6): 5},
        scale_m=10,
    )
    means = {i: dict(r) for i, r in enumerate(rows)}
    counts = {i: {b: n_pixels[i] for b in r} for i, r in enumerate(rows)}
    result = merge_superpixels(
        graph,
        means,
        counts,
        criteria={"ch": 2.0, "std": 0.45},
        relax_factor=1.75,
        min_area_ha=1.0,
        max_area_ha=10.0,
        min_defined_criteria=2,
        min_frac_valid=0.5,
        max_pass2_iterations=60,
    )

    s = summarise_merge_diagnostics(result.diagnostics)

    assert s == {
        "superpixels_in": 7,
        "stands_out": 4,
        "merges_first_pass": 1,
        "merges_second_pass_relaxed": 1,
        "merges_second_pass_shared_edge_fallback": 1,
        "stands_below_min_area": 2,
        "stands_below_min_area_by_cause": {
            "isolated": 1,
            "area_blocked": 1,
            "iteration_cap": 0,
        },
        "area_ha_in_stands_below_min_area": 0.7,
    }
    assert s["superpixels_in"] - s["stands_out"] == (
        s["merges_first_pass"]
        + s["merges_second_pass_relaxed"]
        + s["merges_second_pass_shared_edge_fallback"]
    )
    assert sum(s["stands_below_min_area_by_cause"].values()) == s["stands_below_min_area"]
    # And it agrees with the assignment the merge returned.
    assert s["stands_out"] == result.n_stands == len(set(result.assignment))


# ---------- per-stand provenance and its display layer ----------


def _prov(pass1: int = 0, relaxed: int = 0, fallback: int = 0) -> dict:
    return {
        "n_superpx": 1 + pass1 + relaxed + fallback,
        "n_pass1": pass1,
        "n_relaxed": relaxed,
        "n_fallback": fallback,
        "below_min": 0,
        "below_why": "",
    }


@pytest.mark.parametrize(
    ("provenance", "code"),
    [
        (_prov(), 0),
        (_prov(pass1=4), 1),
        (_prov(pass1=4, relaxed=1), 2),
        (_prov(relaxed=2), 2),
        (_prov(pass1=9, relaxed=3, fallback=1), 3),
        (_prov(fallback=1), 3),
    ],
)
def test_a_stand_is_coded_by_the_weakest_merge_it_contains(provenance, code):
    assert merge_kind_code(provenance) == code


def test_merge_declares_one_layer_showing_how_each_stand_was_built():
    (layer,) = MergeStage.display_layers
    assert (layer.key, layer.band) == ("merge_provenance", "merge_kind")
    assert [e.value for e in layer.legend] == [0, 1, 2, 3]
    by_code = {e.value: e.label.lower() for e in layer.legend}
    assert "single superpixel" in by_code[0]
    assert "first-pass" in by_code[1]
    assert "relaxed" in by_code[2]
    assert "fallback" in by_code[3]
    # The reader has to be told what a fallback merge is, where the legend is.
    assert "no criterion justified" in by_code[3]
    assert "no merge criterion justified" in layer.legend_note
    # A remap of the cached SNIC image: nothing of the stage's is cached.
    assert MergeStage.cacheable_outputs == set()


def test_no_other_stage_produces_or_requires_the_new_keys():
    """The context is write-once, so a second producer would fail the run, and
    a stage that required them would fail on a merge-disabled config."""
    import importlib
    import pkgutil

    import fmu.stages

    for module in pkgutil.iter_modules(fmu.stages.__path__):
        importlib.import_module(f"fmu.stages.{module.name}")
    new = {"stand_provenance", "merge_provenance"}
    others = [
        cls
        for cls in Stage.__subclasses__()
        if cls.__module__.startswith("fmu.stages.") and cls is not MergeStage
    ]
    assert len(others) >= 10
    for cls in others:
        assert not new & cls.produces, cls.name
        assert not new & cls.required_inputs, cls.name


class _FakeImage:
    """Records the relabels the stage asks for."""

    def __init__(self, log: list, steps: tuple = ()):
        self.log, self.steps = log, steps

    def _then(self, *step):
        return _FakeImage(self.log, (*self.steps, step))

    def remap(self, old, new):
        self.log.append((list(old), list(new)))
        return self._then("remap", len(self.log) - 1)

    def rename(self, name):
        return self._then("rename", name)

    def toInt32(self):  # noqa: N802 - mirrors the ee API
        return self._then("toInt32")

    def toUint8(self):  # noqa: N802 - mirrors the ee API
        return self._then("toUint8")

    def clip(self, roi):
        return self._then("clip", roi)

    def addBands(self, other):  # noqa: N802 - mirrors the ee API
        return self


def test_the_stage_passes_the_provenance_through_and_builds_the_layer(monkeypatch):
    """run() with Earth Engine stubbed out, on the seven-superpixel graph of
    `test_summary_numbers_account_for_a_real_merge`: superpixels 0-3 become one
    stand holding one merge of each kind; 4, 5 and 6 stay single."""
    n_pixels = [300, 300, 50, 60, 40, 980, 30]
    rows = [
        {"ch": 10.0, "std": 0.5},
        {"ch": 10.5, "std": 0.5},
        {"ch": 13.0, "std": 0.5},
        {"ch": 30.0, "std": 2.0},
        {"ch": 20.0, "std": 1.0},
        {"ch": 50.0, "std": 5.0},
        {"ch": 80.0, "std": 9.0},
    ]
    graph = SuperpixelGraph(
        raw_labels=list(range(100, 107)),
        n_pixels=n_pixels,
        edges={(0, 1): 10, (0, 2): 5, (1, 3): 5, (5, 6): 5},
        scale_m=10,
    )
    means = {
        i: {**r, "longitude": 77.0 + i * 0.001, "latitude": 28.5}
        for i, r in enumerate(rows)
    }
    counts = {i: {b: n_pixels[i] for b in means[i]} for i in means}

    class _Params:
        criteria = ()
        max_superpixels = 50_000
        relax_factor = 1.75
        min_area_ha = 1.0
        max_area_ha = 10.0
        min_defined_criteria = 2
        min_frac_valid = 0.5
        max_pass2_iterations = 60
        pass2_skip_at_min_area = False

        def tolerances(self):
            return {"ch": 2.0, "std": 0.45}

    class _Export:
        analysis_scale_m = 10

    class _Config:
        merge = _Params()
        export = _Export()

        def max_component_pixels(self):
            return 1000

    class _EE:
        class Image:
            @staticmethod
            def pixelLonLat():  # noqa: N802 - mirrors the ee API
                return "<lonlat>"

    relabels: list = []
    monkeypatch.setattr(merge_module, "ee", _EE)
    monkeypatch.setattr(merge_module, "assert_components_fit", lambda *a, **k: None)
    monkeypatch.setattr(merge_module, "extract_superpixel_graph", lambda *a, **k: graph)
    monkeypatch.setattr(
        merge_module, "extract_superpixel_attributes", lambda *a, **k: (means, counts)
    )
    monkeypatch.setattr(
        merge_module, "_criteria_image", lambda ctx, params: _FakeImage(relabels)
    )
    ctx = PipelineContext()
    ctx.set("roi", "<roi>")
    ctx.set("snic_clusters", _FakeImage(relabels))

    # The second-pass setting must reach the merge as configured, and the stage
    # must say in its metadata which rule ran.
    seen: list[bool] = []
    real_merge = merge_module.merge_superpixels

    def spy(*args, **kwargs):
        seen.append(kwargs["pass2_skip_at_min_area"])
        return real_merge(*args, **kwargs)

    monkeypatch.setattr(merge_module, "merge_superpixels", spy)
    result = MergeStage().run(ctx, _Config())
    out = result.outputs
    assert seen == [False] and result.metadata["pass2_skip_at_min_area"] is False

    _Params.pass2_skip_at_min_area = True
    ctx_on = PipelineContext()
    ctx_on.set("roi", "<roi>")
    ctx_on.set("snic_clusters", _FakeImage([]))
    assert MergeStage().run(ctx_on, _Config()).metadata["pass2_skip_at_min_area"] is True
    assert seen == [False, True]

    assert set(out) == MergeStage.produces
    # Same stand ids as stand_attributes, the documented fields, and totals that
    # are the ones merge_diagnostics already carried.
    prov = out["stand_provenance"]
    assert list(prov) == list(out["stand_attributes"]) == [0, 1, 2, 3]
    assert all(tuple(p) == PROVENANCE_FIELDS for p in prov.values())
    d = out["merge_diagnostics"]
    assert sum(p["n_pass1"] for p in prov.values()) == d["pass1_merges"] == 1
    assert sum(p["n_fallback"] for p in prov.values()) == d["pass2_fallback_merges"] == 1
    assert sorted(p["below_why"] for p in prov.values()) == ["", "", "area_blocked", "isolated"]
    assert not set(PROVENANCE_FIELDS) & set(out["stand_attributes"][0])
    assert "stand_provenance" not in d

    # Two relabels of the SNIC image, from the same raw labels: stand ids, then
    # the code of the stand each superpixel ended up in.
    (labels_a, stand_ids), (labels_b, codes) = relabels
    assert labels_a == labels_b == graph.raw_labels
    merged = stand_ids[0]
    assert stand_ids[:4] == [merged] * 4
    assert codes == [merge_kind_code(prov[sid]) for sid in stand_ids] == [3, 3, 3, 3, 0, 0, 0]
    assert out["stand_clusters"].steps == (
        ("remap", 0),
        ("rename", "stand_clusters"),
        ("toInt32",),
        ("clip", "<roi>"),
    )
    assert out["merge_provenance"].steps == (
        ("remap", 1),
        ("rename", "merge_kind"),
        ("toUint8",),
        ("clip", "<roi>"),
    )


# ---------- k-means fits on units, not pixels ----------


def test_n_training_samples_is_retired():
    """It sampled 10,000 *pixels* -- ~37 per superpixel -- from a stack that is
    constant within a unit, so it drew each unit once per pixel and
    area-weighted every statistic computed from it. A config still carrying it
    now fails to load."""
    raw = yaml.safe_load(BASELINE_YAML.read_text())
    raw["clustering"]["n_training_samples"] = 10000
    with pytest.raises(Exception):  # noqa: B017 - pydantic ValidationError
        Config.model_validate(raw)


@pytest.mark.parametrize(
    "path", sorted(CONFIG_DIR.glob("sanjay_van_*.yaml")), ids=lambda p: p.stem
)
def test_shipped_configs_no_longer_carry_n_training_samples(path: Path):
    raw = yaml.safe_load(path.read_text())
    assert "n_training_samples" not in raw.get("clustering", {})


def test_sampler_stratifies_one_point_per_unit():
    """Pin the call shape: numPoints=1 with no classValues takes one point from
    every class present, so no unit is dropped for being small."""
    from fmu.stages.clustering import _sample_one_point_per_unit

    captured = {}

    class _Img:
        def addBands(self, other):  # noqa: N802 - mirrors the ee API
            return self

        def rename(self, name):
            return self

        def stratifiedSample(self, **kw):  # noqa: N802
            captured.update(kw)
            return "<fc>"

    _sample_one_point_per_unit(
        _Img(), _Img(), "<roi>", 10, seed=42, context="test"
    )
    assert captured["numPoints"] == 1
    # Against the constant, not a literal. This line used to read
    # `== "_unit_label"`, so it held the broken name in place and stayed green
    # while the stage failed live -- `_Img.rename` accepts anything, which is
    # exactly what EE does not.
    assert captured["classBand"] == LABEL_BAND
    assert check_band_name(captured["classBand"]) == captured["classBand"]
    assert captured["scale"] == 10
    assert captured["dropNulls"] is True
    # No classValues: every class present is sampled, small units included.
    assert "classValues" not in captured

"""Non-live tests for the config-driven SNIC input stack.

Covers the parts that need no Earth Engine:
  - the `segmentation.input_bands` schema and its validators;
  - the cross-block guard tying an optical SNIC band to features_optical.index;
  - `SegmentationParams.input_sources()`, the single definition three callers
    depend on (orchestrator, stage validate(), tests);
  - `SegmentationStage.validate()` deriving its requirements from config
    rather than from the static `required_inputs`;
  - `_resolve_input_stack()` band ordering, "*" expansion and duplicate
    detection, exercised against fake images so no server is involved.

The live behaviour (does SNIC actually run on a 64-band stack, what the RMS
distance normaliser evaluates to) needs a GEE-authed run; these pin the
contract around it.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from fmu.config import Config, SegmentationParams, SnicInputBand, load_config
from fmu.stages.base import PipelineContext
from fmu.stages.segmentation import SegmentationStage, _resolve_input_stack

REPO_ROOT = Path(__file__).parent.parent
BASELINE_YAML = REPO_ROOT / "configs" / "sanjay_van_baseline.yaml"
ALPHAEARTH_YAML = REPO_ROOT / "configs" / "sanjay_van_alphaearth.yaml"
NIRV_DUAL_YAML = REPO_ROOT / "configs" / "sanjay_van_nirv_dual.yaml"


# ---------- the default stack ----------


def test_default_input_bands():
    """Six bands over ~four independent axes, in a fixed order.

    Pinned literally: the default IS the shipped baseline experiment (the
    config deliberately does not repeat it), so a change here silently changes
    what the thesis reports.
    """
    assert [(b.source, b.band) for b in SegmentationParams().input_bands] == [
        ("s2_composite", "B4_median"),
        ("s2_composite", "B8_median"),
        ("structure_features", "canopy_height"),
        ("structure_features", "canopy_height_std"),
        ("optical_features", "ndvi_amplitude_annual"),
        ("radar_features", "vv_minus_vh_median"),
    ]


def test_composite_nirv_not_in_default():
    """It is (B8/10000) x NDVI — three columns for two degrees of freedom."""
    assert "composite_nirv" not in {b.band for b in SegmentationParams().input_bands}


def test_composite_nirv_still_declarable():
    p = SegmentationParams(
        input_bands=[SnicInputBand(source="s2_composite", band="composite_nirv")]
    )
    assert p.input_bands[0].band == "composite_nirv"


def test_normalize_distance_scale_defaults_on():
    assert SegmentationParams().normalize_distance_scale is True


# ---------- input_sources() ----------


def test_input_sources_deduplicates():
    p = SegmentationParams(
        input_bands=[
            SnicInputBand(source="s2_composite", band="B4_median"),
            SnicInputBand(source="s2_composite", band="B8_median"),
            SnicInputBand(source="radar_features", band="vv_minus_vh_median"),
        ]
    )
    assert p.input_sources() == {"s2_composite", "radar_features"}


def test_default_input_sources():
    assert SegmentationParams().input_sources() == {
        "s2_composite",
        "structure_features",
        "optical_features",
        "radar_features",
    }


def test_every_declarable_source_maps_to_a_stage():
    """`_SNIC_SOURCE_STAGE` must cover the whole `SnicInputBand.source` Literal.

    Otherwise a legal config raises KeyError inside the orchestrator instead of
    being rejected at load, and only for the source nobody mapped.
    """
    from typing import get_args

    from fmu.pipeline import _SNIC_SOURCE_STAGE

    declarable = set(get_args(SnicInputBand.model_fields["source"].annotation))
    assert declarable == set(_SNIC_SOURCE_STAGE)


# ---------- validators ----------


def test_rejects_empty_input_bands():
    with pytest.raises(ValidationError):
        SegmentationParams(input_bands=[])


def test_rejects_unknown_source():
    with pytest.raises(ValidationError):
        SnicInputBand(source="lidar_features", band="x")  # type: ignore[arg-type]


def test_rejects_duplicate_band_names():
    with pytest.raises(ValidationError, match="duplicate band name"):
        SegmentationParams(
            input_bands=[
                SnicInputBand(source="s2_composite", band="B4_median"),
                SnicInputBand(source="optical_features", band="B4_median"),
            ]
        )


def test_rejects_wildcard_mixed_with_named_bands_of_same_source():
    with pytest.raises(ValidationError, match="all bands"):
        SegmentationParams(
            input_bands=[
                SnicInputBand(source="embedding_features", band="*"),
                SnicInputBand(source="embedding_features", band="A00"),
            ]
        )


def test_allows_wildcard_alongside_a_different_source():
    p = SegmentationParams(
        input_bands=[
            SnicInputBand(source="embedding_features", band="*"),
            SnicInputBand(source="structure_features", band="canopy_height"),
        ]
    )
    assert p.input_sources() == {"embedding_features", "structure_features"}


def test_rejects_empty_band_name():
    with pytest.raises(ValidationError):
        SnicInputBand(source="s2_composite", band="")


# ---------- cross-block guard: optical prefix vs features_optical.index ----------


def _baseline_raw() -> dict:
    return yaml.safe_load(BASELINE_YAML.read_text())


def test_ndvi_band_with_nirv_index_is_rejected_at_load():
    """The default stack names `ndvi_amplitude_annual`; an `index: nirv` arm
    produces `nirv_*`. Left unchecked this is a GEE band-not-found error
    partway through a run, after the feature stages are already paid for."""
    raw = _baseline_raw()
    raw["features_optical"] = {"index": "nirv"}
    with pytest.raises(ValidationError, match="features_optical.index"):
        Config.model_validate(raw)


def test_nirv_band_with_ndvi_index_is_rejected_at_load():
    raw = _baseline_raw()
    raw["segmentation"]["input_bands"] = [
        {"source": "optical_features", "band": "nirv_amplitude_annual"}
    ]
    with pytest.raises(ValidationError, match="features_optical.index"):
        Config.model_validate(raw)


_NIRV_MERGE_CRITERIA = [
    {"source": "structure_features", "band": "canopy_height", "tolerance": 2.00},
    {"source": "structure_features", "band": "canopy_height_std", "tolerance": 0.45},
    {"source": "optical_features", "band": "nirv_amplitude_annual", "tolerance": 0.030},
]


def test_matching_prefix_passes():
    raw = _baseline_raw()
    raw["features_optical"] = {"index": "nirv"}
    raw["segmentation"]["input_bands"] = [
        {"source": "optical_features", "band": "nirv_amplitude_annual"}
    ]
    raw["merge"] = {"criteria": _NIRV_MERGE_CRITERIA}
    Config.model_validate(raw)  # no raise


def test_guard_ignores_index_independent_optical_bands():
    """composite_*/obs_count carry no index prefix, so they must not trip it."""
    raw = _baseline_raw()
    raw["features_optical"] = {"index": "nirv"}
    raw["segmentation"]["input_bands"] = [
        {"source": "optical_features", "band": "composite_brightness"}
    ]
    raw["merge"] = {"criteria": _NIRV_MERGE_CRITERIA}
    Config.model_validate(raw)  # no raise


def test_guard_also_covers_merge_criteria():
    """The merge gate reads optical bands too, and gets the same trap: an
    `index: nirv` arm has no `ndvi_amplitude_annual` to gate on."""
    raw = _baseline_raw()
    raw["features_optical"] = {"index": "nirv"}
    raw["segmentation"]["input_bands"] = [
        {"source": "optical_features", "band": "nirv_amplitude_annual"}
    ]
    # merge left at the default, which names ndvi_amplitude_annual
    with pytest.raises(ValidationError, match="merge.criteria"):
        Config.model_validate(raw)


def test_shipped_nirv_dual_config_names_nirv_bands():
    cfg = load_config(NIRV_DUAL_YAML)
    assert cfg.features_optical.index == "nirv"
    optical = [b.band for b in cfg.segmentation.input_bands if b.source == "optical_features"]
    assert optical == ["nirv_amplitude_annual"]


# ---------- SegmentationStage.validate() ----------


def _ctx_with(keys: set[str]) -> PipelineContext:
    ctx = PipelineContext()
    for k in keys:
        ctx.set(k, f"<{k}>")  # validate() inspects keys only, never values
    return ctx


def test_validate_passes_with_configured_sources():
    cfg = load_config(BASELINE_YAML)
    SegmentationStage().validate(_ctx_with({"roi"} | cfg.segmentation.input_sources()), cfg)


def test_validate_raises_on_missing_source():
    cfg = load_config(BASELINE_YAML)
    ctx = _ctx_with({"roi"} | cfg.segmentation.input_sources() - {"radar_features"})
    with pytest.raises(KeyError, match="radar_features"):
        SegmentationStage().validate(ctx, cfg)


def test_validate_embedding_arm_does_not_require_handcrafted_images():
    """The whole point of arm independence: an embedding run has no radar or
    structure image, and segmentation must not demand one."""
    cfg = load_config(ALPHAEARTH_YAML)
    SegmentationStage().validate(_ctx_with({"roi", "embedding_features"}), cfg)


def test_validate_embedding_arm_requires_the_embedding():
    cfg = load_config(ALPHAEARTH_YAML)
    with pytest.raises(KeyError, match="embedding_features"):
        SegmentationStage().validate(_ctx_with({"roi"}), cfg)


def test_static_required_inputs_is_the_invariant_subset_only():
    """required_inputs is a class attribute and cannot see the config, so it
    must stay minimal — the real check lives in validate()."""
    assert SegmentationStage.required_inputs == {"roi"}


# ---------- _resolve_input_stack() ----------


class _FakeImage:
    """Minimal stand-in for ee.Image: records select/rename, reports bands."""

    def __init__(self, bands: list[str]) -> None:
        self.bands = bands

    def select(self, band: str) -> _FakeImage:
        assert band in self.bands, f"select({band!r}) not in {self.bands}"
        return type(self)([band])  # subclasses stay themselves

    def rename(self, band: str) -> _FakeImage:
        return type(self)([band])

    def bandNames(self) -> list[str]:  # noqa: N802 - mirrors the ee API
        return self.bands


@pytest.fixture
def fake_cat(monkeypatch):
    """Replace ee.Image.cat and safe_get_info so no server is touched."""
    import fmu.stages.segmentation as seg

    monkeypatch.setattr(
        seg.ee.Image,
        "cat",
        staticmethod(lambda images: _FakeImage([b for i in images for b in i.bands])),
    )
    monkeypatch.setattr(seg, "safe_get_info", lambda obj, context="": obj)


def _cfg_with_bands(bands: list[dict[str, str]]) -> Config:
    raw = _baseline_raw()
    raw["segmentation"]["input_bands"] = bands
    return Config.model_validate(raw)


def test_resolve_preserves_declared_order(fake_cat):
    cfg = _cfg_with_bands(
        [
            {"source": "radar_features", "band": "vv_minus_vh_median"},
            {"source": "s2_composite", "band": "B4_median"},
            {"source": "structure_features", "band": "canopy_height"},
        ]
    )
    ctx = PipelineContext()
    ctx.set("s2_composite", _FakeImage(["B4_median", "B8_median"]))
    ctx.set("radar_features", _FakeImage(["vv_minus_vh_median", "vv_median"]))
    ctx.set("structure_features", _FakeImage(["canopy_height"]))

    names, stack = _resolve_input_stack(ctx, cfg)
    assert names == ["vv_minus_vh_median", "B4_median", "canopy_height"]
    assert stack.bands == names  # the stack's band order must match the names


def test_resolve_expands_wildcard(fake_cat):
    cfg = _cfg_with_bands([{"source": "embedding_features", "band": "*"}])
    ctx = PipelineContext()
    ctx.set("embedding_features", _FakeImage([f"A{i:02d}" for i in range(64)]))

    names, stack = _resolve_input_stack(ctx, cfg)
    assert len(names) == 64
    assert names[0] == "A00" and names[-1] == "A63"
    assert stack.bands == names


def test_resolve_wildcard_mixed_with_named_band(fake_cat):
    cfg = _cfg_with_bands(
        [
            {"source": "structure_features", "band": "canopy_height"},
            {"source": "embedding_features", "band": "*"},
        ]
    )
    ctx = PipelineContext()
    ctx.set("structure_features", _FakeImage(["canopy_height"]))
    ctx.set("embedding_features", _FakeImage(["A00", "A01"]))

    names, _ = _resolve_input_stack(ctx, cfg)
    assert names == ["canopy_height", "A00", "A01"]


def test_resolve_rejects_post_expansion_duplicates(fake_cat):
    """Two sources sharing a band name is only detectable after expansion —
    the config validator cannot see what "*" will resolve to."""
    cfg = _cfg_with_bands(
        [
            {"source": "structure_features", "band": "canopy_height"},
            {"source": "embedding_features", "band": "*"},
        ]
    )
    ctx = PipelineContext()
    ctx.set("structure_features", _FakeImage(["canopy_height"]))
    ctx.set("embedding_features", _FakeImage(["canopy_height", "A01"]))

    with pytest.raises(ValueError, match="duplicate band name"):
        _resolve_input_stack(ctx, cfg)


def test_resolve_derives_composite_nirv_without_an_upstream_band(fake_cat):
    """composite_nirv exists on no upstream image; the stage computes it from
    the composite's B4/B8, using the reducer suffix from data_load."""
    cfg = _cfg_with_bands([{"source": "s2_composite", "band": "composite_nirv"}])
    assert cfg.data_load.s2_composite_reducer == "median"

    class _Arith(_FakeImage):
        def subtract(self, other):
            return self

        def divide(self, other):
            return self

        def add(self, other):
            return self

        def multiply(self, other):
            return self

    ctx = PipelineContext()
    ctx.set("s2_composite", _Arith(["B4_median", "B8_median"]))

    names, _ = _resolve_input_stack(ctx, cfg)
    assert names == ["composite_nirv"]


def test_baseline_and_embedding_resolve_to_different_stacks():
    """The arms are independent pipelines: different band count, no overlap."""
    base = load_config(BASELINE_YAML).segmentation
    emb = load_config(ALPHAEARTH_YAML).segmentation
    assert base.input_sources() != emb.input_sources()
    assert not (base.input_sources() & emb.input_sources())


# ---------- segmentation_stage_names() ----------


def test_segmentation_stage_names_stops_at_segmentation():
    from fmu.pipeline import segmentation_stage_names

    for path in (BASELINE_YAML, ALPHAEARTH_YAML, NIRV_DUAL_YAML):
        stages = segmentation_stage_names(load_config(path))
        assert stages[-1] == "segmentation"
        assert "clustering" not in stages


def test_segmentation_stage_names_omits_stages_snic_does_not_read():
    """features_static feeds clustering only — an inspect-segmentation run has
    no reason to pay for it."""
    from fmu.pipeline import segmentation_stage_names

    stages = segmentation_stage_names(load_config(BASELINE_YAML))
    assert "features_static" not in stages
    assert stages == [
        "masking", "data_load", "features_optical", "features_radar",
        "features_structure", "segmentation",
    ]


def test_segmentation_stage_names_follows_the_embedding_arm():
    from fmu.pipeline import segmentation_stage_names

    assert segmentation_stage_names(load_config(ALPHAEARTH_YAML)) == [
        "masking", "data_load", "features_embedding", "segmentation",
    ]


def test_segmentation_stage_names_covers_every_configured_source():
    """Whatever input_bands names, the producing stage must be in the list —
    otherwise validate() fails at run time on a legal config."""
    from fmu.pipeline import _SNIC_SOURCE_STAGE, segmentation_stage_names

    cfg = _cfg_with_bands(
        [
            {"source": "static_features", "band": "elevation"},
            {"source": "embedding_features", "band": "*"},
        ]
    )
    stages = set(segmentation_stage_names(cfg))
    for source in cfg.segmentation.input_sources():
        assert _SNIC_SOURCE_STAGE[source] in stages, source


# ---------- config round-trip ----------


def test_input_bands_survive_a_yaml_round_trip():
    cfg = load_config(ALPHAEARTH_YAML)
    reloaded = Config.model_validate(copy.deepcopy(cfg.model_dump()))
    assert [
        (b.source, b.band) for b in reloaded.segmentation.input_bands
    ] == [(b.source, b.band) for b in cfg.segmentation.input_bands]

"""Offline checks of `segmentation.mask_before_snic`: SNIC and the merge on kept land only.

docs/decisions.yaml, spec-segmentation-mask-before-snic. Earth Engine is replaced by a
recorder that keeps every call the stage code makes (tests/_ee_recorder.py), so what is
checked here is the wiring: which image each statistic is taken over, what SNIC is given,
what comes out, and that with the setting off nothing reads the mask and nothing is masked.
tests/test_mask_before_snic_ee_graph.py builds the same calls with the real Earth Engine
client, offline; whether Earth Engine then does what they ask is what
scripts/check_snic_on_kept_land.py finds out on Earth Engine itself.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

import fmu.stages.merge as merge_module
import fmu.stages.segmentation as segmentation_module
import fmu.utils.kept_land as kept_land_module
from _ee_recorder import Rec, calls, made_by, owner_call
from fmu.config import Config, load_config
from fmu.pipeline import default_stage_names, segmentation_stage_names
from fmu.stages.base import PipelineContext
from fmu.stages.merge import MergeStage
from fmu.stages.segmentation import SegmentationStage, _mean_square_over_pairs
from fmu.utils.adjacency import SuperpixelGraph
from fmu.utils.caching import config_fingerprint
from fmu.utils.kept_land import tabulate_kept_land_coverage

REPO = Path(__file__).resolve().parent.parent
BASELINE_YAML = REPO / "configs" / "sanjay_van_baseline.yaml"
BASELINE_FP = "7f642cf2ca"  # the name of the baseline's saved assets


def _fake_get_info(bands: list[str], *, kept_found: int = 1):
    pairs = {"dx2_sum": 30.0, "dx2_count": 10, "dy2_sum": 10.0, "dy2_count": 10}

    def get_info(obj: Any, context: str = "") -> Any:
        name = obj.name
        if name.endswith(".bandNames()"):
            return list(bands)
        if name.endswith(".nominalScale()"):
            return 10.0
        if name.endswith(".crs()"):
            return "EPSG:32645"
        if context == "RMS adjacent feature distance":
            return {"d2": 4.0}
        if context == "RMS adjacent feature distance over kept land":
            return dict(pairs)
        if context == "kept land in the ROI":
            return {"kept": kept_found}
        raise AssertionError(f"unexpected getInfo: {name} ({context})")

    return get_info


def _config(**segmentation: Any) -> Config:
    raw = yaml.safe_load(BASELINE_YAML.read_text())
    raw["segmentation"] = {**raw.get("segmentation", {}), **segmentation}
    return Config.model_validate(raw)


def _run_segmentation(monkeypatch, config: Config, *, with_mask: bool, kept_found: int = 1):
    log: list = []
    ee = Rec("ee", log)
    bands = [b.band for b in config.segmentation.input_bands]
    for module in (segmentation_module, kept_land_module):
        monkeypatch.setattr(module, "ee", ee)
        monkeypatch.setattr(module, "safe_get_info", _fake_get_info(bands, kept_found=kept_found))
    monkeypatch.setattr(segmentation_module, "_analysis_grid", lambda roi, scale: Rec("grid", log))
    ctx = PipelineContext()
    ctx.set("roi", Rec("roi", log))
    for source in config.segmentation.input_sources():
        ctx.set(source, Rec(source, log))
    habitat = Rec("habitat_mask", log)
    if with_mask:
        ctx.set("habitat_mask", habitat)
    result = SegmentationStage().run(ctx, config)
    return result, log, habitat


def _kept(log: list) -> Rec:
    (call,) = [c for c in log if c.attr == "rename" and c.args == ("kept",)]
    return call.out


# ---------------------------------------------------------------- config and fingerprint


def test_off_by_default_and_left_out_of_the_fingerprint_while_off():
    """Off, left out of the YAML or written out as false, hashes as before the settings
    existed (tests/test_repro_fingerprints.py pins the 14 _repro configs)."""
    base = load_config(BASELINE_YAML)
    assert base.segmentation.mask_before_snic is False
    assert base.segmentation.drop_kept_patches_below_min_area is False
    assert config_fingerprint(base) == BASELINE_FP
    written_out = _config(mask_before_snic=False, drop_kept_patches_below_min_area=False)
    assert config_fingerprint(written_out) == BASELINE_FP


def test_each_setting_switched_on_gives_its_own_fingerprint():
    """Other superpixels, so other cached assets: sharing a key would hand a masked run
    the unmasked superpixels, and the clustering cache the types fitted on them."""
    on = _config(mask_before_snic=True)
    both = _config(mask_before_snic=True, drop_kept_patches_below_min_area=True)
    assert len({BASELINE_FP, config_fingerprint(on), config_fingerprint(both)}) == 3


def test_they_survive_a_round_trip():
    on = _config(mask_before_snic=True, drop_kept_patches_below_min_area=True)
    again = Config.model_validate(copy.deepcopy(on.model_dump(mode="json")))
    assert again.segmentation.mask_before_snic is True
    assert again.segmentation.drop_kept_patches_below_min_area is True
    assert config_fingerprint(again) == config_fingerprint(on)


def test_leaving_out_small_patches_needs_the_mask_before_snic():
    with pytest.raises(ValidationError, match="needs segmentation.mask_before_snic"):
        _config(drop_kept_patches_below_min_area=True)


def test_explicit_seeds_need_a_grid_spacing_of_two_or_more():
    """Touching seed pixels are one seed to SNIC, so spacing 1 would make each kept
    patch one superpixel."""
    with pytest.raises(ValidationError, match="at least 2"):
        _config(mask_before_snic=True, size=1)
    assert _config(size=1).segmentation.size == 1  # unchanged when the setting is off


def test_the_smallest_patch_is_the_smallest_stand_in_pixels():
    assert _config(mask_before_snic=True).kept_patch_min_pixels() == 0
    on = _config(mask_before_snic=True, drop_kept_patches_below_min_area=True)
    assert on.merge.min_area_ha == 1.0 and on.export.analysis_scale_m == 10
    assert on.kept_patch_min_pixels() == 100
    raw = on.model_dump(mode="json")
    raw["merge"]["min_area_ha"] = 0.55
    assert Config.model_validate(raw).kept_patch_min_pixels() == 55


def test_the_mask_is_made_before_segmentation_in_every_stage_list():
    on = _config(mask_before_snic=True)
    for names in (default_stage_names(on), segmentation_stage_names(on)):
        assert names.index("masking") < names.index("segmentation")


# ---------------------------------------------------------------- validate()


def test_segmentation_needs_the_mask_only_when_the_setting_is_on():
    off, on = _config(), _config(mask_before_snic=True)
    ctx = PipelineContext()
    for key in {"roi"} | off.segmentation.input_sources():
        ctx.set(key, object())
    SegmentationStage().validate(ctx, off)
    with pytest.raises(KeyError, match="habitat_mask"):
        SegmentationStage().validate(ctx, on)
    ctx.set("habitat_mask", object())
    SegmentationStage().validate(ctx, on)


def test_merge_needs_the_mask_only_when_the_setting_is_on():
    off, on = _config(), _config(mask_before_snic=True)
    ctx = PipelineContext()
    for key in {"roi", "snic_clusters"} | off.merge.input_sources():
        ctx.set(key, object())
    MergeStage().validate(ctx, off)
    with pytest.raises(KeyError, match="mask_before_snic"):
        MergeStage().validate(ctx, on)


# ---------------------------------------------------------------- segmentation run()


def test_off_reads_no_mask_masks_nothing_and_gives_snic_no_seeds(monkeypatch):
    """The default path is the one every saved run took. The context holds no
    habitat_mask at all, so reading it would fail the run. (That the default path makes
    exactly the calls it made before the setting existed is
    tests/test_segmentation_off_golden.py.)"""
    result, log, _ = _run_segmentation(monkeypatch, _config(), with_mask=False)
    (snic,) = calls(log, ".SNIC")
    assert "seeds" not in snic.kwargs
    assert not calls(log, ".updateMask"), "nothing is masked on the default path"
    assert not calls(log, ".seedGrid") and not calls(log, ".connectedComponents")
    assert result.metadata["mask_before_snic"] is False
    assert "kept_patch_min_pixels" not in result.metadata
    assert result.metadata["distance_scale"] == 2.0  # sqrt of the canned mean 4.0


def test_on_masks_snic_input_to_kept_land_and_seeds_every_patch(monkeypatch):
    config = _config(mask_before_snic=True)
    result, log, habitat = _run_segmentation(monkeypatch, config, with_mask=True)

    # Kept land is habitat_mask's first band, unmasked to 0, equal to 1.
    kept = _kept(log)
    eq = owner_call(log, made_by(log, kept))
    unmask = owner_call(log, eq)
    select = owner_call(log, unmask)
    assert (eq.attr, eq.args) == ("eq", (1,))
    assert (unmask.attr, unmask.args) == ("unmask", (0,))
    assert (select.attr, select.args, select.owner) == ("select", ([0],), habitat)
    assert not calls(log, ".connectedPixelCount"), "no patch is left out unless asked"

    (snic,) = calls(log, ".SNIC")
    image = made_by(log, snic.kwargs["image"])
    assert image.attr == "updateMask" and image.args == (kept,)
    for key in ("size", "compactness", "connectivity", "neighborhoodSize"):
        assert key in snic.kwargs
    seeds = made_by(log, snic.kwargs["seeds"])
    assert seeds.attr == "rename" and seeds.args == ("seeds",)

    # The seed grid at the configured spacing, and patches joined as SNIC joins pixels.
    (grid,) = calls(log, ".seedGrid")
    assert grid.args == (config.segmentation.size,)
    (cc,) = calls(log, ".connectedComponents")
    assert cc.args[1] == config.segmentation.neighborhood_size
    assert made_by(log, cc.args[0]).name == "ee.Kernel.square"
    (rcc,) = calls(log, ".reduceConnectedComponents")
    assert rcc.args[1:] == ("labels", config.segmentation.neighborhood_size)
    assert made_by(log, rcc.args[0]).name == "ee.Reducer.max"

    # Both outputs end masked to kept land.
    for key in ("snic_clusters", "snic_means"):
        last = made_by(log, result.outputs[key])
        assert last.attr == "updateMask" and last.args == (kept,), key
    assert result.metadata["mask_before_snic"] is True
    assert result.metadata["kept_patch_min_pixels"] == 0


def test_on_with_small_patches_left_out_counts_patches_as_snic_joins_pixels(monkeypatch):
    config = _config(mask_before_snic=True, drop_kept_patches_below_min_area=True)
    result, log, _ = _run_segmentation(monkeypatch, config, with_mask=True)
    kept = _kept(log)
    joined = owner_call(log, made_by(log, kept))
    assert joined.attr == "And"
    (count,) = calls(log, ".connectedPixelCount")
    assert count.kwargs == {"maxSize": 100, "eightConnected": True}
    (gte,) = [c for c in log if c.attr == "gte" and c.owner is count.out]
    assert gte.args == (100,)
    # SNIC sees that kept land, and so do the seeds.
    (snic,) = calls(log, ".SNIC")
    assert made_by(log, snic.kwargs["image"]).args == (kept,)
    assert result.metadata["kept_patch_min_pixels"] == 100


def test_four_connected_snic_counts_four_connected_patches(monkeypatch):
    config = _config(mask_before_snic=True, drop_kept_patches_below_min_area=True, connectivity=4)
    _, log, _ = _run_segmentation(monkeypatch, config, with_mask=True)
    (count,) = calls(log, ".connectedPixelCount")
    assert count.kwargs["eightConnected"] is False
    (cc,) = calls(log, ".connectedComponents")
    assert made_by(log, cc.args[0]).name == "ee.Kernel.plus"


def test_an_roi_with_no_kept_land_fails_with_a_plain_message(monkeypatch):
    with pytest.raises(ValueError, match="holds no kept land"):
        _run_segmentation(monkeypatch, _config(mask_before_snic=True), with_mask=True, kept_found=0)


def test_on_takes_the_z_score_over_kept_land_and_applies_it_everywhere(monkeypatch):
    """The mean and spread are those of the pixels SNIC sees; the image they are applied
    to is not masked, so the distance normaliser below can difference real neighbours."""
    config = _config(mask_before_snic=True)
    _, log, _ = _run_segmentation(monkeypatch, config, with_mask=True)
    kept = _kept(log)
    raw_stack = calls(log, "ee.Image.cat")[0].out  # _resolve_input_stack's stack
    (zscore,) = [r for r in calls(log, ".reduceRegion") if owner_call(log, r).attr == "updateMask"]
    masked = owner_call(log, zscore)
    assert masked.args == (kept,) and masked.owner is raw_stack
    # Each band is normalised on the stack itself, not on the masked copy.
    on_raw = [c.args[0] for c in log if c.attr == "select" and c.owner is raw_stack]
    assert on_raw == [b.band for b in config.segmentation.input_bands]


def test_on_measures_the_distance_over_pairs_of_kept_pixels_with_every_band(monkeypatch):
    result, log, _ = _run_segmentation(monkeypatch, _config(mask_before_snic=True), with_mask=True)
    kept = _kept(log)
    # The pairs: kept at both pixels, and every band defined there.
    (valid,) = [c for c in log if c.attr == "And" and c.owner is kept]
    assert owner_call(log, made_by(log, valid.args[0])).attr == "reduce"
    # Both directions, with the weights made positive: a pair counts if both pixels count.
    on_valid = [c for c in log if c.attr == "convolve" and c.owner is valid.out]
    assert len(on_valid) == 2
    weights = sorted(str(made_by(log, c.args[0]).args) for c in on_valid)
    assert weights == ["(1, 2, [[1], [1]])", "(2, 1, [[1, 1]])"]
    # 30 + 10 over 10 + 10 pairs: the mean over all pairs of both directions.
    assert result.metadata["distance_scale"] == pytest.approx(2.0**0.5)


def test_the_mean_square_counts_every_pair_of_both_directions():
    assert _mean_square_over_pairs(
        {"dx2_sum": 30.0, "dx2_count": 10, "dy2_sum": 10.0, "dy2_count": 30}
    ) == pytest.approx(1.0)
    empty = {"dx2_sum": 0, "dx2_count": 0, "dy2_sum": 0, "dy2_count": 0}
    assert _mean_square_over_pairs(empty) is None
    assert _mean_square_over_pairs({}) is None


def test_seeds_refuse_a_connectivity_snic_does_not_have():
    with pytest.raises(ValueError, match="4 or 8"):
        kept_land_module.seeds_on_kept_land(object(), size=6, connectivity=6, max_extent=128)


# ---------------------------------------------------------------- kept-land coverage


def test_coverage_is_converted_to_hectares_on_the_analysis_grid():
    got = tabulate_kept_land_coverage(
        {"kept": 1234.5, "kept_unlabelled": 2, "labelled_not_kept": 0, "small_patches": 50}, 10
    )
    assert got == {
        "kept_land_ha": 12.345,
        "small_patches_ha": 0.5,
        "kept_land_ha_without_superpixel": 0.02,
        "superpixel_ha_off_kept_land": 0.0,
    }
    assert tabulate_kept_land_coverage({}, 10)["kept_land_ha"] == 0.0


def test_coverage_counts_on_the_label_images_own_pixels(monkeypatch):
    """The projection, transform included, and no scale: a cached label image is not
    resampled onto another grid before it is compared with kept land."""
    log: list = []
    monkeypatch.setattr(kept_land_module, "ee", Rec("ee", log))
    seen: dict = {}

    def get_info(obj: Any, context: str = "") -> Any:
        seen["context"] = context
        return {"kept": 100, "kept_unlabelled": 0, "labelled_not_kept": 0, "small_patches": 0}

    monkeypatch.setattr(kept_land_module, "safe_get_info", get_info)
    labels = Rec("labels", log)
    got = kept_land_module.kept_land_coverage(
        labels, Rec("habitat", log), Rec("roi", log), 10,
        min_patch_pixels=100, connectivity=8, context="test",
    )
    (reduce,) = calls(log, ".reduceRegion")
    assert "scale" not in reduce.kwargs
    assert made_by(log, reduce.kwargs["crs"]).name == "labels.projection"
    (cat,) = calls(log, "ee.Image.cat")
    named = [made_by(log, band).args for band in cat.args[0]]
    assert named == [("kept",), ("kept_unlabelled",), ("labelled_not_kept",), ("small_patches",)]
    # Kept land made the way segmentation makes it: once as is, once less small patches.
    (count,) = calls(log, ".connectedPixelCount")
    assert count.kwargs == {"maxSize": 100, "eightConnected": True}
    assert got["kept_land_ha"] == 1.0 and seen["context"] == "test: kept land and superpixels"


# ---------------------------------------------------------------- the merge


def _merge_config(on: bool, min_patch: int = 0):
    class _Params:
        criteria = ()
        max_superpixels = 50_000
        relax_factor = 1.75
        min_area_ha = 1.0
        max_area_ha = 10.0
        min_defined_criteria = 2
        min_frac_valid = 0.5
        max_pass2_iterations = 60
        pass2_skip_at_min_area = True
        pass2_soft_ceiling = False

        def tolerances(self):
            return {"ch": 2.0}

    class _Export:
        analysis_scale_m = 10

    class _Segmentation:
        mask_before_snic = on
        connectivity = 8

    class _Config:
        merge = _Params()
        export = _Export()
        segmentation = _Segmentation()

        def max_component_pixels(self):
            return 1000

        def kept_patch_min_pixels(self):
            return min_patch

    return _Config()


def _run_merge(monkeypatch, on: bool, cover: dict | None, min_patch: int = 0):
    """Two kept patches that do not touch: one stand each, the small one isolated."""
    graph = SuperpixelGraph(raw_labels=[7, 9], n_pixels=[300, 40], edges={}, scale_m=10)
    means = {
        0: {"ch": 10.0, "longitude": 85.0, "latitude": 20.0},
        1: {"ch": 11.0, "longitude": 85.01, "latitude": 20.0},
    }
    counts = {i: {b: graph.n_pixels[i] for b in means[i]} for i in means}
    seen: list = []
    log: list = []
    monkeypatch.setattr(merge_module, "ee", Rec("ee", log))
    monkeypatch.setattr(merge_module, "assert_components_fit", lambda *a, **k: None)
    monkeypatch.setattr(merge_module, "extract_superpixel_graph", lambda *a, **k: graph)
    monkeypatch.setattr(
        merge_module, "extract_superpixel_attributes", lambda *a, **k: (means, counts)
    )
    monkeypatch.setattr(merge_module, "_criteria_image", lambda ctx, params: Rec("criteria", log))

    def coverage(labels, habitat, roi, scale, **kwargs):
        seen.append((labels, habitat, scale, kwargs))
        return cover

    monkeypatch.setattr(merge_module, "kept_land_coverage", coverage)
    ctx = PipelineContext()
    ctx.set("roi", "<roi>")
    ctx.set("snic_clusters", Rec("snic_clusters", log))
    if on:
        ctx.set("habitat_mask", "<habitat>")
    return MergeStage().run(ctx, _merge_config(on, min_patch)), seen


def _cover(**over: float) -> dict:
    return {"kept_land_ha": 3.4, "small_patches_ha": 0.0, "kept_land_ha_without_superpixel": 0.0,
            "superpixel_ha_off_kept_land": 0.0, **over}


def test_merge_off_measures_nothing_and_keeps_its_keys(monkeypatch):
    result, seen = _run_merge(monkeypatch, on=False, cover=None)
    assert seen == []
    assert "kept_land" not in result.outputs["merge_diagnostics"]
    assert result.metadata["mask_before_snic"] is False


def test_merge_on_reports_kept_land_and_leaves_an_isolated_patch_alone(monkeypatch):
    cover = _cover(small_patches_ha=0.25)
    result, seen = _run_merge(monkeypatch, on=True, cover=cover, min_patch=100)
    (labels, habitat, scale, kwargs) = seen[0]
    assert labels.name == "snic_clusters" and habitat == "<habitat>" and scale == 10
    # Kept land is made in the merge exactly as segmentation made it.
    assert kwargs["min_patch_pixels"] == 100 and kwargs["connectivity"] == 8
    d = result.outputs["merge_diagnostics"]
    assert d["kept_land"] == cover
    assert not any("kept land" in w for w in result.warnings)
    # "Merge only where possible": no edge, so no merge; the 0.4 ha patch stays its own
    # stand, below the minimum, for the reason that says so.
    assert d["n_stands"] == 2 and d["pass1_merges"] == d["pass2_merges"] == 0
    assert sorted(p["below_why"] for p in result.outputs["stand_provenance"].values()) == [
        "",
        "isolated",
    ]


def test_merge_on_warns_when_kept_land_is_left_out_or_a_superpixel_lies_off_it(monkeypatch):
    cover = _cover(kept_land_ha_without_superpixel=0.05, superpixel_ha_off_kept_land=0.01)
    result, _ = _run_merge(monkeypatch, on=True, cover=cover)
    said = " ".join(result.warnings)
    assert "0.05 ha of kept land has no superpixel" in said
    assert "0.01 ha of superpixels lies off kept land" in said
    assert result.outputs["merge_diagnostics"]["warnings"] == result.warnings

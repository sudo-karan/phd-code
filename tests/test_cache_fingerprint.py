"""Non-live tests for the config fingerprint in cache asset paths.

The cache used to be keyed on the config *name* alone: edit a threshold,
re-run the same config, silently get the old asset back. That is not a
performance bug but a correctness one, and it matters more under the merge
design than it did before — the segmentation IS the primary output now, and
threshold tuning is the main activity, so a stale cache poisons precisely the
thing being iterated on.

The most important test here is `test_every_config_block_is_classified`. The
fingerprint covers most of the config and explicitly excludes the rest; a new
config block that nobody classified would silently fall out of the hash and
reintroduce the bug for whatever reads it. That test fails instead.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from fmu.config import Config, load_config
from fmu.utils.caching import (
    _CACHE_IRRELEVANT_BLOCKS,
    _CACHE_RELEVANT_BLOCKS,
    _OMITTED_AT_DEFAULT,
    cached_asset_path,
    config_fingerprint,
)

REPO_ROOT = Path(__file__).parent.parent
CONFIG_DIR = REPO_ROOT / "configs"
BASELINE_YAML = CONFIG_DIR / "sanjay_van_baseline.yaml"


def _raw() -> dict:
    return yaml.safe_load(BASELINE_YAML.read_text())


def _fp(mutate=None) -> str:
    raw = _raw()
    if mutate:
        mutate(raw)
    return config_fingerprint(Config.model_validate(raw))


# ---------- the completeness guard ----------


def test_every_config_block_is_classified():
    """Every top-level config field must be declared either able or unable to
    change a cached raster. A block nobody classified would drop out of the
    fingerprint unnoticed, which is exactly the stale-cache bug this exists to
    prevent — just for one block instead of all of them."""
    fields = set(Config.model_fields)
    classified = _CACHE_RELEVANT_BLOCKS | _CACHE_IRRELEVANT_BLOCKS | {"export"}
    assert fields == classified, {
        "unclassified": sorted(fields - classified),
        "classified_but_gone": sorted(classified - fields),
    }


def test_relevant_and_irrelevant_do_not_overlap():
    assert not (_CACHE_RELEVANT_BLOCKS & _CACHE_IRRELEVANT_BLOCKS)


def test_metrics_is_excluded_because_it_caches_nothing():
    """Safe to exclude only because MetricsStage declares no cacheable outputs.
    If that ever changes, this test is the reminder."""
    from fmu.stages.metrics import MetricsStage

    assert "metrics" in _CACHE_IRRELEVANT_BLOCKS
    assert MetricsStage.cacheable_outputs == set()


# ---------- what changes the fingerprint ----------


def test_fingerprint_is_stable_for_an_unchanged_config():
    assert _fp() == _fp()


def test_merge_threshold_change_changes_the_fingerprint():
    """The case the spec called out: thresholds are the main thing being
    iterated on, so a stale cache here would poison the experiment."""
    base = _fp()

    def bump(raw):
        raw["merge"] = {
            "criteria": [
                {
                    "source": "structure_features",
                    "band": "canopy_height",
                    "tolerance": 2.6,
                },
                {
                    "source": "structure_features",
                    "band": "canopy_height_std",
                    "tolerance": 0.45,
                },
                {
                    "source": "optical_features",
                    "band": "ndvi_amplitude_annual",
                    "tolerance": 0.030,
                },
            ]
        }

    assert _fp(bump) != base


def test_segmentation_band_change_changes_the_fingerprint():
    """The 1249-vs-1312 divergence is a bug in the primary output now."""
    base = _fp()

    def swap(raw):
        raw["segmentation"]["input_bands"] = [
            {"source": "s2_composite", "band": "B4_median"},
            {"source": "s2_composite", "band": "B8_median"},
            {"source": "structure_features", "band": "canopy_height"},
        ]

    assert _fp(swap) != base


def test_analysis_scale_changes_the_fingerprint():
    """It governs every reduction and every export resolution."""
    assert _fp(lambda r: r["export"].__setitem__("analysis_scale_m", 20)) != _fp()


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda r: r["clustering"].__setitem__("k", 8), id="clustering.k"),
        pytest.param(
            lambda r: r["clustering"].__setitem__("seed", 7), id="clustering.seed"
        ),
        pytest.param(
            lambda r: r["normalization"].__setitem__("method", "zscore"),
            id="normalization",
        ),
        pytest.param(
            lambda r: r["masking"].__setitem__("jrc_water_occurrence_threshold", 70.0),
            id="masking",
        ),
        pytest.param(
            lambda r: r["cloud_mask"].__setitem__("max_cloud_pct", 40.0),
            id="cloud_mask",
        ),
        pytest.param(
            lambda r: r["features_structure"].__setitem__(
                "neighborhood_kernel_size", 5
            ),
            id="features_structure",
        ),
        pytest.param(
            lambda r: r["datasets"].__setitem__("dem", "USGS/SRTMGL1_003"),
            id="datasets",
        ),
        pytest.param(
            lambda r: r["dates"]["radar"].__setitem__("end", "2021-12-31"), id="dates"
        ),
    ],
)
def test_content_changes_invalidate_the_cache(mutate):
    assert _fp(mutate) != _fp()


# ---------- what does NOT change it ----------


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(
            lambda r: r.__setitem__("description", "reworded"), id="description"
        ),
        pytest.param(
            lambda r: r["export"].__setitem__("drive_folder", "elsewhere"),
            id="export.drive_folder",
        ),
        pytest.param(
            lambda r: r["export"].__setitem__("vector_formats", ["geojson"]),
            id="export.vector_formats",
        ),
        pytest.param(
            lambda r: r["export"].__setitem__("export_vector_snic", False),
            id="export.export_vector_snic",
        ),
        pytest.param(
            lambda r: r["metrics"].__setitem__("n_comparison_samples", 500),
            id="metrics",
        ),
    ],
)
def test_output_plumbing_does_not_invalidate_the_cache(mutate):
    """Changing where a file lands, or how the comparison is sampled, must not
    throw away an expensive raster — those cannot change what the raster is."""
    assert _fp(mutate) == _fp()


# ---------- the asset path ----------


def test_path_carries_the_fingerprint(monkeypatch):
    monkeypatch.setenv("GEE_PROJECT_ID", "test-project")
    from fmu.settings import get_settings

    get_settings(force_reload=True)
    path = cached_asset_path("cfg", "segmentation", "snic_clusters", "abc1234567")
    assert path.endswith("/cfg/segmentation/snic_clusters__abc1234567")


def test_path_without_a_fingerprint_is_the_old_layout(monkeypatch):
    """Kept for reading pre-fingerprint assets, not for writing new ones."""
    monkeypatch.setenv("GEE_PROJECT_ID", "test-project")
    from fmu.settings import get_settings

    get_settings(force_reload=True)
    path = cached_asset_path("cfg", "segmentation", "snic_clusters")
    assert path.endswith("/cfg/segmentation/snic_clusters")


def test_path_rejects_a_non_alphanumeric_fingerprint(monkeypatch):
    monkeypatch.setenv("GEE_PROJECT_ID", "test-project")
    from fmu.settings import get_settings

    get_settings(force_reload=True)
    with pytest.raises(ValueError, match="alphanumeric"):
        cached_asset_path("cfg", "segmentation", "snic_clusters", "bad/slash")


def test_fingerprint_is_short_and_hex():
    fp = _fp()
    assert len(fp) == 10
    assert all(c in "0123456789abcdef" for c in fp)


# ---------- the shipped configs ----------


def test_shipped_configs_have_distinct_fingerprints():
    """Different experiments must not collide, or one would read the other's
    assets from under the shared stage path.

    A `_repro` copy is the same experiment under a new name, so it shares its
    original's fingerprint on purpose; it is left out here and checked below.
    """
    fps = {
        p.stem: config_fingerprint(load_config(p))
        for p in sorted(CONFIG_DIR.glob("sanjay_van_*.yaml"))
        if not p.stem.endswith("_repro")
    }
    assert len(set(fps.values())) == len(fps), fps


@pytest.mark.parametrize(
    "path", sorted(CONFIG_DIR.glob("*_repro.yaml")), ids=lambda p: p.stem
)
def test_repro_copy_differs_from_its_original_in_name_only(path: Path):
    """A `_repro` copy exists to recompute a config from scratch in a fresh
    asset namespace (CLAUDE.md, "Earth Engine"). That is a reproducibility test
    only if nothing but the name differs: same content, so same fingerprint,
    under a different config name, so a different asset path."""
    original = load_config(path.with_name(path.name.replace("_repro.yaml", ".yaml")))
    repro = load_config(path)
    a, b = original.model_dump(mode="json"), repro.model_dump(mode="json")
    assert [k for k in a if a[k] != b[k]] == ["name"]
    assert repro.name == original.name + "_repro"
    fp = config_fingerprint(original)
    assert config_fingerprint(repro) == fp
    assert cached_asset_path(repro.name, "masking", "habitat_mask", fp) != (
        cached_asset_path(original.name, "masking", "habitat_mask", fp)
    )


def test_reference_config_file_resolves_by_convention():
    cfg = load_config(CONFIG_DIR / "sanjay_van_alphaearth.yaml")
    resolved = cfg.metrics.resolved_reference_config_file()
    assert resolved == Path("configs") / "sanjay_van_baseline.yaml"


def test_no_reference_means_no_reference_file():
    cfg = load_config(BASELINE_YAML)
    assert cfg.metrics.reference_config_name is None
    assert cfg.metrics.resolved_reference_config_file() is None


def test_round_trip_through_model_dump_is_stable():
    """The fingerprint must not depend on how the config was constructed."""
    cfg = load_config(BASELINE_YAML)
    reloaded = Config.model_validate(copy.deepcopy(cfg.model_dump(mode="json")))
    assert config_fingerprint(cfg) == config_fingerprint(reloaded)


# ---------- settings added after assets were cached ----------


def test_a_setting_left_out_at_its_default_is_named_with_the_models_own_default():
    """`_OMITTED_AT_DEFAULT` repeats each default. If the model's default moved
    and the table did not, the fingerprint would treat the OLD default as the
    one to leave out, and existing configs would silently change behaviour
    under an unchanged fingerprint."""
    assert _OMITTED_AT_DEFAULT, "the table is empty: delete this test with it"
    for (block, field), default in _OMITTED_AT_DEFAULT.items():
        assert block in _CACHE_RELEVANT_BLOCKS, block
        model = Config.model_fields[block].annotation
        assert field in model.model_fields, (block, field)
        assert model.model_fields[field].default == default, (block, field)


def test_the_second_pass_setting_leaves_the_fingerprint_alone_while_off():
    """Off, whether left out of the YAML or written out as false, hashes as the
    config did before the setting existed. The literal is the fingerprint of the
    baseline's saved assets (tests/test_repro_fingerprints.py pins all 14)."""
    assert _fp() == "7f642cf2ca"

    def written_out(raw):
        raw.setdefault("merge", {})["pass2_skip_at_min_area"] = False

    assert _fp(written_out) == "7f642cf2ca"


def test_switching_the_second_pass_setting_on_changes_the_fingerprint():
    """On is a different merge, so it must not share cached assets with off:
    clustering is cached under the same key, and would hand back stand types
    computed for the other stands."""

    def on(raw):
        raw.setdefault("merge", {})["pass2_skip_at_min_area"] = True

    assert _fp(on) != _fp()
    cfg_on = Config.model_validate({**_raw(), "merge": {"pass2_skip_at_min_area": True}})
    assert cfg_on.merge.pass2_skip_at_min_area is True
    assert cached_asset_path(cfg_on.name, "clustering", "cluster_labels", config_fingerprint(cfg_on)) != (
        cached_asset_path(cfg_on.name, "clustering", "cluster_labels", _fp())
    )


def test_the_dump_written_to_manifests_still_carries_the_setting():
    """Only the hash leaves it out. The config dumped into a manifest says
    which rule ran."""
    assert Config.model_validate(_raw()).model_dump(mode="json")["merge"]["pass2_skip_at_min_area"] is False


def test_the_soft_ceiling_leaves_the_fingerprint_alone_while_off():
    """spec-merge-pass2-soft-ceiling. Off, whether left out of the YAML or
    written out as false, hashes as the config did before the setting existed
    (tests/test_every_config_fingerprint.py pins every config)."""
    assert _fp() == "7f642cf2ca"

    def written_out(raw):
        raw.setdefault("merge", {})["pass2_soft_ceiling"] = False

    assert _fp(written_out) == "7f642cf2ca"


def test_switching_the_soft_ceiling_on_changes_the_fingerprint():
    """On is a different merge, so it must share cached assets neither with off
    nor with the other second-pass setting: clustering is cached under the same
    key, and would hand back stand types computed for other stands."""

    def on(raw):
        raw.setdefault("merge", {})["pass2_soft_ceiling"] = True

    def skip(raw):
        raw.setdefault("merge", {})["pass2_skip_at_min_area"] = True

    def both(raw):
        on(raw)
        skip(raw)

    assert len({_fp(), _fp(on), _fp(skip), _fp(both)}) == 4
    cfg_on = Config.model_validate({**_raw(), "merge": {"pass2_soft_ceiling": True}})
    assert cfg_on.merge.pass2_soft_ceiling is True
    assert cached_asset_path(cfg_on.name, "clustering", "cluster_labels", config_fingerprint(cfg_on)) != (
        cached_asset_path(cfg_on.name, "clustering", "cluster_labels", _fp())
    )


def test_the_dump_written_to_manifests_carries_the_soft_ceiling():
    assert Config.model_validate(_raw()).model_dump(mode="json")["merge"]["pass2_soft_ceiling"] is False


def test_the_fit_exclusion_setting_leaves_the_fingerprint_alone_while_off():
    """clustering.fit_excludes_stands_below_min_area off, left out of the YAML or
    written out as false, hashes as the config did before the setting existed."""
    assert _fp() == "7f642cf2ca"

    def written_out(raw):
        raw.setdefault("clustering", {})["fit_excludes_stands_below_min_area"] = False

    assert _fp(written_out) == "7f642cf2ca"


def test_switching_the_fit_exclusion_setting_on_changes_the_fingerprint():
    """On is another fit, so it must not share cached assets with off: the
    clustering cache would hand back stand types fitted on every stand."""

    def on(raw):
        raw.setdefault("clustering", {})["fit_excludes_stands_below_min_area"] = True

    assert _fp(on) != _fp()
    raw = _raw()
    on(raw)
    cfg_on = Config.model_validate(raw)
    assert cfg_on.clustering.fit_excludes_stands_below_min_area is True
    assert cached_asset_path(cfg_on.name, "clustering", "cluster_labels", config_fingerprint(cfg_on)) != (
        cached_asset_path(cfg_on.name, "clustering", "cluster_labels", _fp())
    )


def test_the_dump_written_to_manifests_still_carries_the_fit_exclusion_setting():
    dumped = Config.model_validate(_raw()).model_dump(mode="json")
    assert dumped["clustering"]["fit_excludes_stands_below_min_area"] is False

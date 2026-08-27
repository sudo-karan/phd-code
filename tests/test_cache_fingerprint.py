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
    assets from under the shared stage path."""
    fps = {
        p.stem: config_fingerprint(load_config(p))
        for p in sorted(CONFIG_DIR.glob("sanjay_van_*.yaml"))
    }
    assert len(set(fps.values())) == len(fps), fps


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

"""End-to-end smoke test for the full pipeline.

This test runs the complete pipeline (masking → ... → metrics) on the
Sanjay Van AOI in cache-only mode: all upstream stages should hit cache,
proving the full chain works without re-running heavy compute.

This addresses the gap that per-stage live tests can't cover: each stage
works in isolation, but the *chain* — output keys flowing from one stage's
produces into the next stage's required_inputs — only gets exercised by
a real run. This test catches contract drift (e.g., stage A renames an
output that stage B expects) immediately.

Marked `live_gee` because it touches the cache layer (asset_exists calls).
Skips automatically if the cache isn't populated.
"""

from __future__ import annotations

from pathlib import Path

import ee
import pytest

from fmu.config import load_config
from fmu.pipeline import Pipeline
from fmu.stages.base import PipelineContext

# Import all stages so they register with the registry
from fmu.stages.clustering import ClusteringStage  # noqa: F401
from fmu.stages.data_load import DataLoadStage  # noqa: F401
from fmu.stages.export import ExportStage  # noqa: F401
from fmu.stages.features_optical import FeaturesOpticalStage  # noqa: F401
from fmu.stages.features_radar import FeaturesRadarStage  # noqa: F401
from fmu.stages.features_static import FeaturesStaticStage  # noqa: F401
from fmu.stages.features_structure import FeaturesStructureStage  # noqa: F401
from fmu.stages.masking import MaskingStage  # noqa: F401
from fmu.stages.metrics import MetricsStage  # noqa: F401
from fmu.stages.profiling import ProfilingStage  # noqa: F401
from fmu.stages.segmentation import SegmentationStage  # noqa: F401
from fmu.utils.caching import asset_exists, cached_asset_path
from fmu.utils.gee import load_roi_geometry

pytestmark = pytest.mark.live_gee


# The full pipeline order, exactly as the inspect scripts run it.
FULL_PIPELINE_STAGES = [
    "masking",
    "data_load",
    "features_optical",
    "features_radar",
    "features_structure",
    "features_static",
    "segmentation",
    "clustering",
    "profiling",
    "export",
]


@pytest.fixture(scope="module")
def real_gee():
    import fmu.utils.gee as gee_mod
    from fmu.settings import get_settings

    gee_mod._initialized = False
    get_settings(force_reload=True)

    settings = get_settings()
    if not settings.gee_project_id:
        pytest.skip("GEE_PROJECT_ID not set in .env")

    try:
        gee_mod.init_gee()
    except ee.EEException as e:
        if "authenticate" in str(e).lower() or "credentials" in str(e).lower():
            pytest.skip(f"GEE not authenticated. {e}")
        raise
    yield


@pytest.fixture(scope="module")
def baseline_assets_cached(real_gee):
    """Skip the smoke test if baseline assets aren't in the cache.

    We don't want this test to *populate* the cache — that takes hours.
    The expectation is that the user has run `inspect_clustering.py` (or
    similar) at least once. If not, skip with a clear message.
    """
    must_have = [
        ("masking", "habitat_mask"),
        ("data_load", "s2_composite"),
        ("features_optical", "optical_features"),
        ("clustering", "cluster_labels"),
    ]
    missing = []
    for stage, key in must_have:
        path = cached_asset_path("sanjay_van_baseline", stage, key)
        if not asset_exists(path):
            missing.append(f"{stage}/{key}")
    if missing:
        pytest.skip(
            "Baseline cache not populated; run inspect_clustering.py on "
            f"sanjay_van_baseline first. Missing: {', '.join(missing)}"
        )


def test_full_pipeline_chain_runs_end_to_end(baseline_assets_cached, monkeypatch):
    """The full 10-stage pipeline runs end-to-end with cache enabled.

    What this proves:
      - Every stage's output keys feed correctly into the next stage's
        required_inputs (no contract drift between stages).
      - The cache layer correctly short-circuits cached stages.
      - The orchestrator's write-once context never collides.
      - Manifest assembly works against the full stage list.
    """
    repo_root = Path(__file__).parent.parent
    config = load_config(repo_root / "configs" / "sanjay_van_baseline.yaml")
    roi = load_roi_geometry(repo_root / "aois" / "sanjay_van.geojson")
    ctx = PipelineContext()
    ctx.set("roi", roi)

    # Subclass ExportStage to skip the Drive task submission — we're
    # smoke-testing the chain, not the side-effecting export.
    from fmu.stages.base import _stage_registry

    class _SmokeExport(ExportStage):
        def _submit_drive_export(self, **_kwargs):
            return {"id": "SMOKE_TEST_NO_REAL_TASK"}

    # Swap the registry entry via monkeypatch — auto-restored on test exit,
    # even if pytest aborts mid-test (KeyboardInterrupt, OOM). Avoids the
    # bug where a manual try/finally leaves the registry mutated if the
    # test process gets killed before finally runs.
    monkeypatch.setitem(_stage_registry, "export", _SmokeExport)

    # Use a temporary run dir so we don't litter the user's runs/
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        pipeline = Pipeline(stage_names=FULL_PIPELINE_STAGES, use_cache=True)
        result = pipeline.run(config=config, run_dir=run_dir, initial_context=ctx)

    # Every stage in the chain must have run successfully
    stage_names_run = [s.name for s in result.stages]
    assert stage_names_run == FULL_PIPELINE_STAGES, (
        f"Pipeline ran wrong stages: expected {FULL_PIPELINE_STAGES}, got {stage_names_run}"
    )

    # Stages that produce ONLY ee.Image outputs are fully cacheable and
    # should all hit cache here (baseline_assets_cached confirmed upstream).
    # data_load is intentionally excluded: it produces ee.ImageCollections
    # (s2_collection, s1_collection) that aren't cacheable as assets, so
    # it always re-derives them live even when its s2_composite is cached.
    # That's by design — the collections are cheap to rebuild.
    # Asserting by name is more diagnostic than "at least 6 cached" — a name
    # match tells you WHICH stage was unexpectedly missing from cache.
    expected_cached_stages = {
        "masking",
        "features_optical",
        "features_radar",
        "features_structure",
        "features_static",
        "segmentation",
        "clustering",
    }
    cached_by_name = {
        s.name for s in result.stages if s.metadata.get("source") == "cache"
    }
    not_cached = expected_cached_stages - cached_by_name
    assert not not_cached, (
        f"These stages should have been served from cache but weren't: {sorted(not_cached)}. "
        "Either upstream assets are missing or the cache layer is broken."
    )

    # data_load always runs live (uncacheable collection outputs); verify
    # it actually ran rather than being skipped.
    data_load_record = next(
        (s for s in result.stages if s.name == "data_load"), None
    )
    assert data_load_record is not None, "data_load stage didn't run"
    assert data_load_record.metadata.get("source") != "cache", (
        "data_load should always run live (it produces uncacheable collections)"
    )

    # profiling and export are never cached by design — they always run.
    # Make sure they ran (not cache-skipped) for the same reason.
    for always_run_stage in ("profiling", "export"):
        record = next((s for s in result.stages if s.name == always_run_stage), None)
        assert record is not None, f"{always_run_stage} didn't run"
        assert record.metadata.get("source") != "cache", (
            f"{always_run_stage} should never be served from cache"
        )

    # Final context should have every produced key from every stage.
    # NB: masking's `produces` is {habitat_mask, water_mask, landcover_summary}
    # — built_up_mask is an internal intermediate inside the masking stage,
    # not a context output. The export.py inventory list previously included
    # it by mistake; that's why the export manifest reports 11 cached assets
    # rather than 12.
    expected_keys = {
        # masking
        "habitat_mask", "water_mask", "landcover_summary",
        # data_load
        "s2_composite",
        # features
        "optical_features", "radar_features", "structure_features", "static_features",
        # segmentation
        "snic_clusters", "snic_means",
        # clustering
        "cluster_labels", "feature_stack",
        # profiling
        "cluster_profiles",
        # export
        "export_manifest",
    }
    actual_keys = result.context.keys() - {"roi"}  # roi is pre-loaded
    missing = expected_keys - actual_keys
    assert not missing, f"Context missing keys at end of run: {sorted(missing)}"

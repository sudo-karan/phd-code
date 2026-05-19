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


def test_full_pipeline_chain_runs_end_to_end(baseline_assets_cached):
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

    # Use a temporary run dir so we don't litter the user's runs/
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        pipeline = Pipeline(stage_names=FULL_PIPELINE_STAGES, use_cache=True)
        # Subclass ExportStage to skip the Drive task submission — we're
        # smoke-testing the chain, not the side-effecting export.
        from fmu.stages.export import ExportStage

        class _SmokeExport(ExportStage):
            def _submit_drive_export(self, **_kwargs):
                return {"id": "SMOKE_TEST_NO_REAL_TASK"}

        # Re-register under the same name. We have to clear and re-register
        # because the registry rejects duplicate names by default.
        from fmu.stages.base import _stage_registry
        _stage_registry["export"] = _SmokeExport

        try:
            result = pipeline.run(config=config, run_dir=run_dir, initial_context=ctx)
        finally:
            # Restore original
            _stage_registry["export"] = ExportStage

    # Every stage in the chain must have run successfully
    stage_names_run = [s.name for s in result.stages]
    assert stage_names_run == FULL_PIPELINE_STAGES, (
        f"Pipeline ran wrong stages: expected {FULL_PIPELINE_STAGES}, got {stage_names_run}"
    )

    # Each cached stage should report "from cache" (source=cache in metadata).
    # The export stage and metrics-less profiling won't.
    cached_stages = [s for s in result.stages if s.metadata.get("source") == "cache"]
    assert len(cached_stages) >= 6, (
        "Expected at least 6 cached stages (masking through clustering); "
        f"got {len(cached_stages)}"
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

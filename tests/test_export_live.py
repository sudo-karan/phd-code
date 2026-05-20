"""Live integration tests for the export stage.

The Drive submission is mocked-out via subclass to avoid creating a real
Drive export task every time tests run. The rest of the stage runs live
against GEE (asset existence checks, cluster distribution computation,
metadata reads).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import ee
import pytest

from fmu.config import load_config
from fmu.stages.base import PipelineContext
from fmu.stages.clustering import ClusteringStage
from fmu.stages.data_load import DataLoadStage
from fmu.stages.export import ExportStage
from fmu.stages.features_optical import FeaturesOpticalStage
from fmu.stages.features_radar import FeaturesRadarStage
from fmu.stages.features_static import FeaturesStaticStage
from fmu.stages.features_structure import FeaturesStructureStage
from fmu.stages.masking import MaskingStage
from fmu.stages.segmentation import SegmentationStage
from fmu.utils.gee import load_roi_geometry

pytestmark = pytest.mark.live_gee


class _NoDriveExportStage(ExportStage):
    """ExportStage subclass that pretends to submit a Drive task.

    Returns a fake task descriptor without actually queuing a Drive job.
    """

    def _submit_drive_export(self, **_kwargs: Any) -> dict[str, str]:
        return {"id": "FAKE_TASK_FOR_TESTING"}


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
        msg = str(e).lower()
        if "authenticate" in msg or "credentials" in msg:
            pytest.skip(f"GEE not authenticated. {e}")
        raise
    yield


@pytest.fixture(scope="module")
def ctx_ready_for_export(real_gee):
    repo_root = Path(__file__).parent.parent
    config = load_config(repo_root / "configs" / "sanjay_van_baseline.yaml")
    roi = load_roi_geometry(repo_root / "aois" / "sanjay_van.geojson")
    ctx = PipelineContext()
    ctx.set("roi", roi)

    stages = [
        MaskingStage(),
        DataLoadStage(),
        FeaturesOpticalStage(),
        FeaturesRadarStage(),
        FeaturesStructureStage(),
        FeaturesStaticStage(),
        SegmentationStage(),
        ClusteringStage(),
    ]
    for stage in stages:
        result = stage.run(ctx, config)
        for key, value in result.outputs.items():
            if not ctx.has(key):
                ctx.set(key, value)
    return ctx, config


def test_runs_end_to_end(ctx_ready_for_export):
    ctx, config = ctx_ready_for_export
    result = _NoDriveExportStage().run(ctx, config)
    assert "export_manifest" in result.outputs
    manifest = result.outputs["export_manifest"]
    assert isinstance(manifest, dict)


def test_manifest_has_required_sections(ctx_ready_for_export):
    ctx, config = ctx_ready_for_export
    result = _NoDriveExportStage().run(ctx, config)
    manifest = result.outputs["export_manifest"]

    expected_keys = {
        "config_name",
        "pipeline_version",
        "run_timestamp",
        "roi",
        "config_snapshot",
        "asset_paths",
        "clustering",
        "drive_export",
        "decisions_source",
    }
    missing = expected_keys - set(manifest.keys())
    assert not missing, f"Manifest missing keys: {missing}"


def test_cluster_distribution_present_and_consistent(ctx_ready_for_export):
    """Cluster distribution should sum to a sensible habitat pixel count."""
    ctx, config = ctx_ready_for_export
    result = _NoDriveExportStage().run(ctx, config)
    manifest = result.outputs["export_manifest"]
    distribution = manifest["clustering"]["cluster_distribution"]

    assert len(distribution) == config.clustering.k
    total = sum(c["pixel_count"] for c in distribution)
    assert total > 5000, f"Only {total} pixels; habitat mask too aggressive?"

    # Percent of habitat should sum to ~100%
    total_pct = sum(c["percent_of_habitat"] for c in distribution)
    assert 99.0 < total_pct < 101.0, (
        f"Percent of habitat sums to {total_pct}, expected ~100"
    )


def test_asset_paths_include_clustering_outputs(ctx_ready_for_export):
    ctx, config = ctx_ready_for_export
    result = _NoDriveExportStage().run(ctx, config)
    manifest = result.outputs["export_manifest"]
    asset_paths = manifest["asset_paths"]

    # cluster_labels should always be present (clustering must have completed)
    assert "cluster_labels" in asset_paths
    assert config.name in asset_paths["cluster_labels"]


def test_drive_export_descriptor_populated(ctx_ready_for_export):
    ctx, config = ctx_ready_for_export
    result = _NoDriveExportStage().run(ctx, config)
    manifest = result.outputs["export_manifest"]
    drive = manifest["drive_export"]

    assert drive["task_submitted"] is True
    assert drive["task_id"] == "FAKE_TASK_FOR_TESTING"
    assert drive["filename"].endswith(".tif")
    assert config.name in drive["filename"]


def test_pipeline_version_recorded(ctx_ready_for_export):
    ctx, config = ctx_ready_for_export
    result = _NoDriveExportStage().run(ctx, config)
    manifest = result.outputs["export_manifest"]
    assert manifest["pipeline_version"]
    # Should match the current package version
    from fmu import __version__
    assert manifest["pipeline_version"] == __version__

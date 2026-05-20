"""Live integration tests for the export stage.

The Drive submission is mocked-out via subclass to avoid creating a real
Drive export task every time tests run. The rest of the stage runs live
against GEE (asset existence checks, cluster distribution computation,
metadata reads).

Upstream artifacts loaded from GEE cache (see tests/_live_cache_fixtures.py
for rationale). To populate the cache, run `python scripts/inspect_clustering.py`
on each config you want covered.
"""

from __future__ import annotations

from typing import Any

import pytest

from _live_cache_fixtures import ctx_ready_for_downstream
from fmu.stages.export import ExportStage

pytestmark = pytest.mark.live_gee


class _NoDriveExportStage(ExportStage):
    """ExportStage subclass that pretends to submit a Drive task.

    Returns a fake task descriptor without actually queuing a Drive job.
    """

    def _submit_drive_export(self, **_kwargs: Any) -> dict[str, str]:
        return {"id": "FAKE_TASK_FOR_TESTING"}


@pytest.fixture(scope="module")
def ctx_ready_for_export():
    return ctx_ready_for_downstream(
        "sanjay_van_baseline.yaml", include_clustering=True
    )


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
    assert total > 5000, f"Only {total} pixels — habitat mask too aggressive?"

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

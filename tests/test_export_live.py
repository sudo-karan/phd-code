"""Live integration tests for the export stage.

Drive submission (both raster and vector) is mocked-out via subclass to
avoid creating real Drive export tasks every time tests run. The rest
of the stage runs live against GEE: asset existence checks, cluster
distribution computation, metadata reads, and the server-side vector
construction pipelines (reduceToVectors, reduceRegions, renumbering).

Upstream artifacts loaded from GEE cache (see tests/_live_cache_fixtures.py
for rationale). To populate the cache, run `python scripts/inspect_export.py`
on each config you want covered (this also exercises profiling, which
the export stage now depends on for the dissolved vector layer).
"""

from __future__ import annotations

from typing import Any

import pytest

from _live_cache_fixtures import ctx_ready_for_downstream
from fmu.stages.export import ExportStage

pytestmark = pytest.mark.live_gee


class _NoDriveExportStage(ExportStage):
    """ExportStage subclass that pretends to submit Drive tasks.

    Both the raster and vector submission hooks are overridden, so no
    Drive job is queued. Each fake task gets a deterministic id so we
    can assert which task came from which call site if needed.
    """

    def _submit_drive_export(self, **kwargs: Any) -> dict[str, str]:
        filename = kwargs.get("filename", "unknown")
        return {"id": f"FAKE_RASTER_{filename}"}

    def _submit_drive_vector_export(self, **kwargs: Any) -> dict[str, str]:
        filename = kwargs.get("filename", "unknown")
        fmt = kwargs.get("file_format", "unknown")
        return {"id": f"FAKE_VECTOR_{filename}_{fmt}"}


@pytest.fixture(scope="module")
def ctx_ready_for_export():
    return ctx_ready_for_downstream(
        "sanjay_van_baseline.yaml",
        include_clustering=True,
        include_profiling=True,
    )


# ---------- Existing assertions (preserved, lightly updated) ----------


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
        "drive_exports",        # was drive_export (singular) pre-v1.1.0
        "vector_layers",        # new in v1.1.0
        "decisions_source",
    }
    missing = expected_keys - set(manifest.keys())
    assert not missing, f"Manifest missing keys: {missing}"
    # Make sure the old singular field doesn't sneak back in.
    assert "drive_export" not in manifest, (
        "Manifest still has the pre-v1.1.0 'drive_export' field; should be 'drive_exports'."
    )


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


def test_pipeline_version_recorded(ctx_ready_for_export):
    ctx, config = ctx_ready_for_export
    result = _NoDriveExportStage().run(ctx, config)
    manifest = result.outputs["export_manifest"]
    assert manifest["pipeline_version"]
    # Should match the current package version
    from fmu import __version__
    assert manifest["pipeline_version"] == __version__


# ---------- v1.1.0: drive_exports dict structure ----------


def test_drive_exports_has_raster_entry(ctx_ready_for_export):
    ctx, config = ctx_ready_for_export
    result = _NoDriveExportStage().run(ctx, config)
    drive_exports = result.outputs["export_manifest"]["drive_exports"]

    assert "raster_cluster_labels" in drive_exports
    entry = drive_exports["raster_cluster_labels"]
    assert entry["task_submitted"] is True
    assert entry["task_id"].startswith("FAKE_RASTER_")
    assert entry["filename"].endswith(".tif")
    assert entry["format"] == "GeoTIFF"
    assert config.name in entry["filename"]


def test_drive_exports_has_all_vector_layer_format_entries(ctx_ready_for_export):
    """Every (layer × format) combo enabled by config should appear."""
    ctx, config = ctx_ready_for_export
    result = _NoDriveExportStage().run(ctx, config)
    drive_exports = result.outputs["export_manifest"]["drive_exports"]

    expected_keys = set()
    if config.export.export_geotiff:
        expected_keys.add("raster_cluster_labels")
    if config.export.export_vector_snic:
        for fmt in config.export.vector_formats:
            expected_keys.add(f"vector_stands_snic_{fmt}")
    if config.export.export_vector_dissolved:
        for fmt in config.export.vector_formats:
            expected_keys.add(f"vector_stands_dissolved_{fmt}")

    assert set(drive_exports.keys()) == expected_keys


def test_drive_exports_entries_have_consistent_shape(ctx_ready_for_export):
    ctx, config = ctx_ready_for_export
    result = _NoDriveExportStage().run(ctx, config)
    drive_exports = result.outputs["export_manifest"]["drive_exports"]

    required_per_entry = {
        "folder", "filename", "format", "task_id",
        "submitted_at", "task_submitted",
    }
    for key, entry in drive_exports.items():
        assert required_per_entry.issubset(entry.keys()), (
            f"drive_exports[{key!r}] missing fields: "
            f"{required_per_entry - set(entry.keys())}"
        )


def test_drive_folder_from_config(ctx_ready_for_export):
    """Folder field on every entry matches config.export.drive_folder."""
    ctx, config = ctx_ready_for_export
    result = _NoDriveExportStage().run(ctx, config)
    drive_exports = result.outputs["export_manifest"]["drive_exports"]

    for key, entry in drive_exports.items():
        assert entry["folder"] == config.export.drive_folder, (
            f"drive_exports[{key!r}].folder = {entry['folder']!r}, "
            f"expected {config.export.drive_folder!r}"
        )


# ---------- v1.1.0: vector_layers section ----------


def test_vector_layers_section_present(ctx_ready_for_export):
    ctx, config = ctx_ready_for_export
    result = _NoDriveExportStage().run(ctx, config)
    vector_layers = result.outputs["export_manifest"]["vector_layers"]

    expected = set()
    if config.export.export_vector_snic:
        expected.add("stands_snic")
    if config.export.export_vector_dissolved:
        expected.add("stands_dissolved")

    assert set(vector_layers.keys()) == expected


def test_snic_vector_layer_metadata(ctx_ready_for_export):
    ctx, config = ctx_ready_for_export
    if not config.export.export_vector_snic:
        pytest.skip("export_vector_snic disabled in this config")
    result = _NoDriveExportStage().run(ctx, config)
    snic = result.outputs["export_manifest"]["vector_layers"]["stands_snic"]

    assert snic["geometry_type"] == "Polygon"
    assert snic["id_field"] == "stand_id"
    # Schema fields documented
    assert "stand_id" in snic["shp_attributes"]
    assert "snic_label" in snic["shp_attributes"]
    assert "cluster_id" in snic["shp_attributes"]
    # SNIC layer should always have features for a real-data run
    assert snic["n_features"] is not None
    assert snic["n_features"] > 0, (
        f"stands_snic has {snic['n_features']} features — expected > 0 for a populated AOI"
    )


def test_dissolved_vector_layer_metadata(ctx_ready_for_export):
    ctx, config = ctx_ready_for_export
    if not config.export.export_vector_dissolved:
        pytest.skip("export_vector_dissolved disabled in this config")
    result = _NoDriveExportStage().run(ctx, config)
    dissolved = result.outputs["export_manifest"]["vector_layers"]["stands_dissolved"]

    assert dissolved["geometry_type"] == "Polygon"
    assert dissolved["id_field"] == "unit_id"
    assert dissolved["min_stand_pixels"] == config.export.vector_min_stand_pixels
    assert "unit_id" in dissolved["shp_attributes"]
    assert "cluster_id" in dissolved["shp_attributes"]
    # Dissolved layer should have at least k features (one per cluster) for
    # a small contiguous AOI like Sanjay Van. In a fragmented AOI it could
    # be many more; both are valid.
    assert dissolved["n_features"] is not None
    assert dissolved["n_features"] >= config.clustering.k, (
        f"stands_dissolved has {dissolved['n_features']} features, "
        f"expected >= k={config.clustering.k}"
    )


# ---------- v1.1.0: stage metadata exposes diagnostic counters ----------


def test_stage_metadata_records_task_counts(ctx_ready_for_export):
    ctx, config = ctx_ready_for_export
    result = _NoDriveExportStage().run(ctx, config)
    md = result.metadata

    n_expected_tasks = 0
    if config.export.export_geotiff:
        n_expected_tasks += 1
    if config.export.export_vector_snic:
        n_expected_tasks += len(config.export.vector_formats)
    if config.export.export_vector_dissolved:
        n_expected_tasks += len(config.export.vector_formats)

    assert md["n_drive_tasks"] == n_expected_tasks
    assert len(md["drive_task_ids"]) == n_expected_tasks
    assert md["n_vector_layers"] == int(config.export.export_vector_snic) + int(
        config.export.export_vector_dissolved
    )
    assert md["drive_folder"] == config.export.drive_folder

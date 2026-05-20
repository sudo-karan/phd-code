"""Export stage. Packages the pipeline's final research-ready outputs:

  1. A GeoTIFF of cluster_labels exported to the user's Google Drive
     (loadable in QGIS / ArcGIS / rasterio for collaborators without
     GEE access).
  2. A run manifest (JSON) capturing:
       - pipeline version
       - run timestamp
       - the entire config that produced this run
       - paths to every cached GEE asset
       - clustering preprocessing parameters
       - per-cluster pixel-count distribution
       - the Drive export task ID
       - pointer to decisions.md as the source of truth

Feature assets are already cached as GEE assets by the orchestrator
(ENG-018). The export stage does not re-export them; it just records
their paths in the manifest so collaborators can be pointed directly
at the existing assets.

The manifest goes into the stage's metadata dict, which the orchestrator
writes to runs/{run_dir}/manifest.json automatically. The inspect script
also saves a standalone export_manifest_{config}.json for convenience.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, ClassVar

import ee

from fmu import __version__
from fmu.config import Config
from fmu.stages.base import PipelineContext, Stage, StageResult, register_stage
from fmu.utils.caching import asset_exists, cached_asset_path
from fmu.utils.gee import safe_call, safe_get_info
from fmu.utils.logging import get_logger

log = get_logger(__name__)


# The pipeline implements the decisions and engineering choices documented
# in phd-notebook/decisions.md (the source of truth, locked alongside this
# repo at the same git revision). We deliberately don't enumerate decision
# IDs here; they'd drift from the notebook as decisions are added/revised.
# Instead the manifest records a pointer to the source of truth.
_DECISIONS_SOURCE = "phd-notebook/decisions.md"


# The export manifest's asset inventory is derived from the stage registry
# at runtime; we ask every registered stage what its cacheable_outputs are
# (via the same MRO walk the orchestrator uses). This prevents the drift
# problem we hit when this list was hand-maintained: it always missed an
# output (e.g., landcover_summary), or kept a phantom entry for a key
# that wasn't actually produced. The single source of truth is each stage's
# class declaration.
#
# Stages that ARE in the registry but never go in the cache (because they
# either opt out via cacheable_outputs=set() or have non-image outputs
# like the export and metrics stages themselves) contribute nothing here.
# The probe is config-scoped: we only list paths that exist for THIS
# config's runs, so a stage that hasn't been run yet for this config
# won't appear.


@register_stage("export")
class ExportStage(Stage):
    name = "export"
    required_inputs = {"roi", "cluster_labels"}
    produces = {"export_manifest"}
    cacheable_outputs: ClassVar[set[str]] = set()  # always run; no GEE asset

    # Drive folder for GeoTIFF exports. Subclassable for tests.
    DRIVE_FOLDER: ClassVar[str] = "fmu_exports"

    @safe_call("export stage")
    def run(self, ctx: PipelineContext, config: Config) -> StageResult:
        roi = ctx.get("roi")
        cluster_labels: ee.Image = ctx.get("cluster_labels")
        scale = config.export.analysis_scale_m

        # 1. Pull the clustering preprocessing metadata off the asset property
        clustering_meta = _read_clustering_metadata(cluster_labels)
        log.info(
            "  clustering metadata: k=%s, %d active bands",
            clustering_meta.get("k", "?"),
            len(clustering_meta.get("active_bands", [])),
        )

        # 2. Per-cluster distribution from the cluster_labels image
        distribution = _compute_cluster_distribution(cluster_labels, roi, scale)
        log.info("  cluster distribution: %d clusters totaling %d pixels",
                 len(distribution), sum(c["pixel_count"] for c in distribution))

        # 3. Inventory cached assets for this config
        asset_paths = _inventory_cached_assets(config.name)
        log.info("  cached assets for this config: %d", len(asset_paths))

        # 4. Submit the Drive GeoTIFF export
        drive_filename = f"{config.name}_cluster_labels"
        task = self._submit_drive_export(
            cluster_labels=cluster_labels,
            roi=roi,
            scale=scale,
            filename=drive_filename,
        )

        # 5. ROI metadata (compute area on the fly)
        try:
            roi_area_m2 = safe_get_info(roi.area(maxError=1), context="roi area")
            roi_area_km2 = round((roi_area_m2 or 0) / 1e6, 3)
        except Exception:  # noqa: BLE001; area is informational, not critical
            roi_area_km2 = None

        # 6. Build the manifest
        now_iso = datetime.now(UTC).isoformat()
        manifest: dict[str, Any] = {
            "config_name": config.name,
            "pipeline_version": __version__,
            "run_timestamp": now_iso,
            "roi": {
                "name": config.roi.name,
                "area_km2": roi_area_km2,
                "geojson_path": str(config.roi.roi_file),
            },
            "config_snapshot": config.model_dump(mode="json"),
            "asset_paths": asset_paths,
            "clustering": {
                **clustering_meta,
                "cluster_distribution": distribution,
            },
            "drive_export": {
                "folder": self.DRIVE_FOLDER,
                "filename": f"{drive_filename}.tif",
                "task_id": task["id"] if task else None,
                "submitted_at": now_iso if task else None,
                "task_submitted": task is not None,
            },
            "decisions_source": _DECISIONS_SOURCE,
        }

        return StageResult(
            outputs={"export_manifest": manifest},
            metadata={
                "drive_task_id": task["id"] if task else None,
                "drive_filename": f"{drive_filename}.tif",
                "n_clusters": len(distribution),
                "n_cached_assets": len(asset_paths),
                "manifest": manifest,
            },
        )

    # ---------------------------------------------------------------------
    # Side-effecting hook; overridden in tests to skip Drive submission
    # ---------------------------------------------------------------------

    def _submit_drive_export(
        self,
        *,
        cluster_labels: ee.Image,
        roi: ee.Geometry,
        scale: int,
        filename: str,
    ) -> dict[str, Any] | None:
        """Submit a Drive export and return the task descriptor.

        Default implementation actually submits. Tests can override this
        to return a fake task descriptor without hitting GEE batch.
        """
        # Cast to integer; cluster IDs are inherently integer; this also
        # makes the resulting GeoTIFF smaller (uint8 if k ≤ 256).
        labels_int = cluster_labels.toUint8()

        task = ee.batch.Export.image.toDrive(
            image=labels_int,
            description=filename,
            folder=self.DRIVE_FOLDER,
            fileNamePrefix=filename,
            region=roi,
            scale=scale,
            maxPixels=1e9,
            fileFormat="GeoTIFF",
        )
        task.start()
        task_id = task.id
        log.info(
            "  submitted Drive export: task_id=%s, folder='%s', file='%s.tif'",
            task_id,
            self.DRIVE_FOLDER,
            filename,
        )
        return {"id": task_id}


# ---------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------


def _read_clustering_metadata(cluster_labels: ee.Image) -> dict[str, Any]:
    """Pull the JSON-serialized clustering metadata off the asset property.

    Raises if the property is missing or malformed. Both are integrity
    failures: the clustering stage MUST set this property (ENG-022), and
    the export stage MUST be able to read it for the manifest to be a
    valid reproducibility artifact. Silently substituting an empty dict
    would produce a manifest that looks valid but is missing the
    preprocessing parameters needed to interpret cluster IDs in original
    feature units.
    """
    raw = safe_get_info(
        cluster_labels.get("clustering_metadata"),
        context="clustering_metadata property",
    )
    if not raw:
        raise ValueError(
            "cluster_labels asset is missing the 'clustering_metadata' "
            "property. Re-run the clustering stage to produce a valid asset."
        )
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError) as e:
        raise ValueError(
            f"clustering_metadata property is not valid JSON: {e}. "
            "Re-run the clustering stage."
        ) from e


def _compute_cluster_distribution(
    cluster_labels: ee.Image,
    roi: ee.Geometry,
    scale: int,
) -> list[dict[str, Any]]:
    """Per-cluster pixel count + area + percent of habitat."""
    hist_result = safe_get_info(
        cluster_labels.reduceRegion(
            reducer=ee.Reducer.frequencyHistogram(),
            geometry=roi,
            scale=scale,
            maxPixels=1e9,
            bestEffort=True,
        ),
        context="cluster frequency histogram",
    )
    # The result is keyed by band name; cluster_labels has one band.
    # Find that band name dynamically (it's "cluster_id" by convention but
    # be defensive).
    if not hist_result:
        return []
    band_name = next(iter(hist_result.keys()))
    hist = hist_result.get(band_name) or {}
    pixel_area_ha = (scale * scale) / 10000.0
    total = sum(hist.values()) or 1

    distribution = []
    for cid_str in sorted(hist.keys(), key=int):
        n = int(hist[cid_str])
        distribution.append(
            {
                "cluster_id": int(cid_str),
                "pixel_count": n,
                "area_ha": round(n * pixel_area_ha, 2),
                "percent_of_habitat": round(100.0 * n / total, 2),
            }
        )
    return distribution


def _inventory_cached_assets(config_name: str) -> dict[str, str]:
    """Discover cached assets for this config by walking the stage registry.

    For each registered stage, ask the orchestrator's resolution helper
    what that stage's cacheable_outputs are (handles MRO inheritance and
    explicit opt-outs). Then probe each (stage, output) for an existing
    asset at the cache path.

    Returns a dict {output_key: full_asset_path} containing only the
    outputs that actually exist as cached GEE assets. Missing outputs
    (stage never run, or opt-out) are simply absent.
    """
    # Imported lazily to avoid a circular import with the pipeline module.
    from fmu.pipeline import Pipeline
    from fmu.stages.base import get_stage_class, list_registered_stages

    paths: dict[str, str] = {}
    for stage_name in list_registered_stages():
        stage = get_stage_class(stage_name)()
        # Use the same MRO-walking resolver the orchestrator uses, so an
        # opt-out via cacheable_outputs=set() is honored here too (and we
        # don't probe nonsense paths for stages like profiling/export/metrics).
        cacheable = Pipeline._resolve_cacheable_outputs(stage)
        for output_key in sorted(cacheable):
            path = cached_asset_path(config_name, stage_name, output_key)
            if asset_exists(path):
                paths[output_key] = path
    return paths

"""Export stage. Packages the pipeline's final research-ready outputs.

Three deliverable classes, all driven by toggles in `config.export`:

  1. **Raster GeoTIFFs** exported to the user's Google Drive (loadable in
     QGIS / ArcGIS / rasterio for collaborators without GEE access). Toggled
     via `export_geotiff`. Three products:
       - the single-band cluster-label map;
       - a multiband raster of every feature in ORIGINAL units + the cluster
         label (human-readable / GIS-ready);
       - a multiband raster of the SCALED feature_stack (exactly what k-means
         saw) + the cluster label.

  2. **Merged-stand vectors** (`stands_merged`): one polygon per merged
     stand -- the unit SNIC + merge delineate, and the pipeline's primary
     deliverable. Toggled via `export_vector_merged`; written only when
     `merge.enabled`, since without merge the stand *is* the superpixel and
     `stands_snic` already is that layer. Unlike `stands_snic`, stands that
     clustering could not type are kept with a null `cluster_id`. A stand takes
     its own row's type (round 12), a stand left out of the k-means fit too,
     and a stand with no row a null type (round 13).

  3. **SNIC superpixel vectors** (`stands_snic`): one polygon per SNIC
     superpixel with all per-superpixel feature means attached. The
     debugging / methodology layer; lets you trace from a polygon back
     to the SNIC label and inspect what fed clustering, and gives the
     pre-merge side of a pre/post-merge comparison. Toggled via
     `export_vector_snic`.

  4. **Dissolved cluster vectors** (`stands_dissolved`): one polygon per
     connected same-cluster region, with cluster profile statistics
     attached. Toggled via `export_vector_dissolved`. Filtered by
     `vector_min_stand_pixels` to drop speckle. Kept for continuity with
     the pre-merge outputs; `stands_merged` supersedes it as the unit of
     delineation, since dissolving by cluster id merges every same-type
     region that happens to touch, whatever its extent.

Each vector layer is exported in every format listed in
`config.export.vector_formats` (default: both SHP and GeoJSON). SHP
exports carry a minimal ~5-6-column attribute schema (10-char field-name
limit); GeoJSON exports carry the full attribute schema. See
docs/outputs.md for the per-layer schemas.

Plus a **run manifest** (JSON) capturing:
  - pipeline version, run timestamp
  - the entire config that produced this run
  - paths to every cached GEE asset
  - clustering preprocessing parameters + per-cluster distribution
  - one entry per submitted Drive task (raster + vector × format)
  - schemas of the emitted vector layers
  - pointer to decisions.md as the source of truth

Feature assets are already cached as GEE assets by the orchestrator
(ENG-018). The export stage does not re-export them; it just records
their paths in the manifest so collaborators can be pointed directly
at the existing assets.

The manifest goes into the stage's metadata dict, which the orchestrator
writes to runs/{run_dir}/manifest.json automatically. The inspect script
also saves a standalone export_manifest_{config}.json for convenience.

Schema note (v1.1.0 — breaking change from v0.18.0):
  The previous `drive_export` (singular) manifest field is gone.
  All Drive tasks are now keyed under a single `drive_exports` dict:
    - "raster_cluster_labels"          (present if export_geotiff)
    - "raster_features_raw"            (present if export_geotiff)
    - "raster_features_scaled"         (present if export_geotiff)
    - "vector_stands_merged_{fmt}"     (one per format, if export_vector_merged
                                        AND merge.enabled)
    - "vector_stands_snic_{fmt}"       (one per format, if export_vector_snic)
    - "vector_stands_dissolved_{fmt}"  (one per format, if export_vector_dissolved)
  Past on-disk manifests are unaffected (archival), but any downstream
  code that reads `manifest["drive_export"]["task_id"]` must migrate to
  `manifest["drive_exports"]["raster_cluster_labels"]["task_id"]`.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, ClassVar

import ee

from fmu import __version__
from fmu.config import Config
from fmu.stages.base import PipelineContext, Stage, StageResult, register_stage
from fmu.stages.clustering import _decompose_cyclic_bands
from fmu.utils.caching import asset_exists, cached_asset_path
from fmu.utils.gee import safe_call, safe_get_info
from fmu.utils.logging import get_logger
from fmu.utils.provenance import environment_state, git_state
from fmu.utils.region_merge import PROVENANCE_FIELDS

log = get_logger(__name__)


# The pipeline implements the decisions and engineering choices documented
# in phd-notebook/decisions.md (the source of truth, locked alongside this
# repo at the same git revision). We deliberately don't enumerate decision
# IDs here; they'd drift from the notebook as decisions are added/revised.
# Instead the manifest records a pointer to the source of truth.
_DECISIONS_SOURCE = "phd-notebook/decisions.md"

# Vector layer canonical names. Used as filename infixes and manifest keys.
_MERGED_LAYER_NAME = "stands_merged"
_SNIC_LAYER_NAME = "stands_snic"
_DISSOLVED_LAYER_NAME = "stands_dissolved"

# Composite sort-key for renumbering polygons by centroid lat-desc / lon-asc.
# Sort key = -lat * _SORT_LAT_MULT + lon. Larger latitudes get smaller (more
# negative) keys and sort first. The multiplier dominates the longitude
# contribution so longitude only breaks ties. Works for any AOI within ~1-2
# degrees of lat/lon extent (well beyond Sanjay Van's ~3 km extent).
_SORT_LAT_MULT = 1_000_000

# A polygon's centroid is the mean position of its pixel centres (round 14; round 13's
# question 21, answered (a)): the vectorisation averages ee.Image.pixelLonLat's two bands over
# each polygon's pixels, beside its pixel count, under these names
# (_vectorise_with_pixel_centres). _add_geom_attrs copies them to centroid_lon and
# centroid_lat, and _drop_internal_properties drops them, so no layer gains a property.
_PIXEL_CENTRES_LON = "pixel_lon"
_PIXEL_CENTRES_LAT = "pixel_lat"

# SHP attribute selectors. SHP has a hard 10-char field-name limit; everything
# in these lists is <= 10 chars. The GeoJSON exports omit the selectors arg
# entirely, so they include every property attached to the feature.
_SHP_SELECTORS_MERGED: tuple[str, ...] = (
    "stand_id",      # 8
    "stand_lbl",     # 9 -- the raw merge label, "stand_label" is 11 chars
    "cluster_id",    # 10
    "area_ha",       # 7
    "perim_m",       # 7
    "n_pixels",      # 8
)
_SHP_SELECTORS_SNIC: tuple[str, ...] = (
    "stand_id",      # 8
    "snic_label",    # 10
    "cluster_id",    # 10
    "area_ha",       # 7
    "perim_m",       # 7
    "n_pixels",      # 8
)
_SHP_SELECTORS_DISSOLVED: tuple[str, ...] = (
    "unit_id",       # 7
    "cluster_id",    # 10
    "area_ha",       # 7
    "perim_m",       # 7
    "n_pixels",      # 8
)


@register_stage("export")
class ExportStage(Stage):
    name = "export"
    # Dependencies are full: SNIC vectors need every features_* image to
    # compute per-superpixel means; dissolved vectors need cluster_profiles
    # for the attached profile attributes. Toggling individual outputs off
    # via config.export.* doesn't relax these inputs — the toggles control
    # whether we BUILD an output, not whether the upstream stage ran.
    # Invariant subset; the feature-source-specific inputs (four hand-crafted
    # images, or the single embedding image) are enforced in validate() so the
    # embedding arm isn't forced to produce the hand-crafted stack.
    required_inputs = {
        "roi",
        "cluster_labels",
        "feature_stack",
        "snic_clusters",
        "cluster_profiles",
    }
    produces = {"export_manifest"}
    # Nothing cached, so the orchestrator submits no export for this stage and its
    # StageRecord.export_tasks is empty. The Drive tasks it submits itself are in its
    # metadata (drive_task_ids) and the manifest (drive_exports); nothing waits on
    # them, the pass runner's --wait included (review C39).
    cacheable_outputs: ClassVar[set[str]] = set()  # always run; no GEE asset

    def validate(self, ctx: PipelineContext, config: Config) -> None:
        source = config.clustering.feature_source
        extra = (
            {"embedding_features"}
            if source == "embedding"
            else {"optical_features", "radar_features", "structure_features", "static_features"}
        )
        needed = {
            "roi", "cluster_labels", "feature_stack", "snic_clusters", "cluster_profiles",
        } | extra
        # The merged-stand layer needs the merge's output. Conditional rather
        # than a static required_input: without merge that key does not exist,
        # and demanding it would break every merge-disabled config.
        if config.export.export_vector_merged and config.merge.enabled:
            needed.add(config.unit_label_key())
        missing = needed - ctx.keys()
        if missing:
            raise KeyError(
                f"{self.name} (feature_source={source!r}): missing required "
                f"context inputs: {sorted(missing)}. Context has: {sorted(ctx.keys())}"
            )

    @safe_call("export stage")
    def run(self, ctx: PipelineContext, config: Config) -> StageResult:
        roi = ctx.get("roi")
        cluster_labels: ee.Image = ctx.get("cluster_labels")
        scale = config.export.analysis_scale_m
        drive_folder = config.export.drive_folder

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

        # 3. Inventory cached assets for this config, in the run's cache layout
        from fmu.pipeline import current_cache_key

        asset_paths = _inventory_cached_assets(
            config.name, key_for=lambda stage_name: current_cache_key(config, stage_name)
        )
        log.info("  cached assets for this config: %d", len(asset_paths))

        # 4. Submit Drive exports. Build up drive_exports dict and
        #    vector_layers dict as we go.
        now_iso_initial = datetime.now(UTC).isoformat()
        drive_exports: dict[str, dict[str, Any]] = {}
        vector_layers: dict[str, dict[str, Any]] = {}

        # 4a. Raster GeoTIFFs. Three multiband products (deck v3.0, Stage 10):
        #   - raster_cluster_labels : single-band uint8 cluster-label map.
        #   - raster_features_raw   : every feature band in ORIGINAL units
        #                             (metres, dB, NDVI, ...) + the cluster_id
        #                             band. The human-readable, GIS-ready map.
        #   - raster_features_scaled: the preprocessed feature_stack exactly as
        #                             k-means saw it (log / robust-scaled,
        #                             cyclic-decomposed) + the cluster_id band.
        if config.export.export_geotiff:
            # cluster_id band, shared by the two feature rasters.
            #
            # The whole image is cast to Float32 before export. GeoTIFF does
            # NOT cast a mixed-type image to a common type -- the previous
            # comment here claimed it did, and EE rejects it instead:
            #
            #   Exported bands must have compatible data types; found
            #   inconsistent types: Float64 and Int32. (Error code: 3)
            #
            # And it rejects it *asynchronously*, three seconds into a task
            # submitted long after the stage reported success, so the run looked
            # clean and the file simply never arrived.
            #
            # Float32 rather than Float64: it holds cluster ids 0..k-1 exactly,
            # carries ~7 significant digits across every feature band (elevation
            # in metres, radar in dB, indices in [-1, 1], the scaled stack in
            # roughly [-5, 5]), and halves the file. The authoritative integer
            # labels are the single-band uint8 raster below; cluster_id rides
            # along in these two for convenience.
            label_band = cluster_labels.rename("cluster_id")

            raster_specs = [
                (
                    "raster_cluster_labels",
                    f"{config.name}_cluster_labels",
                    cluster_labels.toUint8(),  # compact single-band label map
                ),
                (
                    "raster_features_raw",
                    f"{config.name}_features_raw",
                    _build_raw_feature_export_image(ctx).addBands(label_band).toFloat(),
                ),
                (
                    "raster_features_scaled",
                    f"{config.name}_features_scaled",
                    ctx.get("feature_stack").addBands(label_band).toFloat(),
                ),
            ]
            for manifest_key, raster_filename, raster_image in raster_specs:
                raster_task = self._submit_drive_export(
                    image=raster_image,
                    roi=roi,
                    scale=scale,
                    filename=raster_filename,
                    drive_folder=drive_folder,
                )
                drive_exports[manifest_key] = _format_task_entry(
                    folder=drive_folder,
                    filename=f"{raster_filename}.tif",
                    file_format="GeoTIFF",
                    task=raster_task,
                    submitted_at=now_iso_initial,
                )

        # The vector layers are built, counted and sent one ROI part at a time
        # (round 9, issue #44 item 11); an ROI of one polygon is one part.
        builds_vectors = (
            (config.export.export_vector_merged and config.merge.enabled)
            or config.export.export_vector_snic
            or config.export.export_vector_dissolved
        )
        parts = _roi_parts(roi, scale) if builds_vectors else [roi]
        if len(parts) > 1:
            log.info("  vector layers: built and counted one ROI part at a time (%d parts)", len(parts))

        # 4b. Merged-stand vectors -- the delineation this pipeline produces.
        #
        # Only when merge ran. Without it `unit_label_key()` is `snic_clusters`
        # and this layer would be a byte-for-byte duplicate of stands_snic
        # below, which is worse than absent: two files, same content, different
        # names, and a reader with no way to tell they are the same thing.
        if config.export.export_vector_merged and config.merge.enabled:
            log.info("  building merged-stand vector layer...")
            merged_fc, merged_parts = _layer_by_part(
                _build_merged_feature_collection,
                ctx=ctx, config=config, scale=scale, parts=parts, id_field="stand_id",
            )
            merged_counts = _count_by_part(
                merged_parts, context="stands_merged polygons", label_property="stand_lbl"
            )
            merged_n_features = merged_counts["n_features"]
            log.info(
                "  stands_merged: %s features over %d stands",
                merged_n_features,
                merged_counts["n_stands"],
            )
            _warn_on_split_stands(merged_counts, merged_n_features)
            # Merge provenance (n_superpx, n_pass1, ...): on the layer whenever
            # the merge stage put `stand_provenance` in the context.
            provenance_fields = _stand_provenance_fields(ctx)

            vector_layers[_MERGED_LAYER_NAME] = {
                "description": (
                    "One polygon per merged stand -- the unit SNIC + merge "
                    "delineate, and the pipeline's primary deliverable. "
                    "Attributes include the raw merge label (stand_lbl), the "
                    "assigned cluster_id, and per-stand means of every "
                    "features_* band. Stands clustering could not type carry a "
                    "null cluster_id and are KEPT: the stand exists whether or "
                    "not a type label could be attached to it."
                ),
                "n_features": merged_n_features,
                # Both, deliberately. `n_features` alone read as the stand count
                # and was not one: a live run reported 329 features for a merge
                # that produced 327 stands.
                "n_stands": merged_counts["n_stands"],
                "n_stands_split_into_pieces": merged_counts["n_split"],
                "max_pieces_per_stand": merged_counts["max_pieces"],
                # Built, counted and sent one ROI part at a time (round 9).
                "roi_parts": len(parts),
                "geometry_type": "Polygon",
                "id_field": "stand_id",
                "id_renumbering": (
                    "1..N, sorted by centroid latitude descending then "
                    "longitude ascending, the centroid being the mean "
                    "position of the polygon's pixel centres. Deterministic "
                    "pure function of the merged geometry."
                ),
                "unclustered_stands_retained": True,
                "shp_attributes": [*_SHP_SELECTORS_MERGED, *provenance_fields],
                "geojson_attributes": "all SHP attributes plus per-stand means "
                                      "of every features_* band and of the "
                                      "sine and cosine of each angle band "
                                      "(<band>_sin, <band>_cos)",
                "provenance_attributes": list(provenance_fields),
            }
            for fmt in config.export.vector_formats:
                filename = f"{config.name}_{_MERGED_LAYER_NAME}"
                task = self._submit_drive_vector_export(
                    feature_collection=merged_fc,
                    filename=filename,
                    drive_folder=drive_folder,
                    file_format=fmt,
                    selectors=(
                        [*_SHP_SELECTORS_MERGED, *provenance_fields]
                        if fmt == "shp"
                        else None
                    ),
                )
                drive_exports[f"vector_{_MERGED_LAYER_NAME}_{fmt}"] = (
                    _format_task_entry(
                        folder=drive_folder,
                        filename=f"{filename}{_filename_ext(fmt)}",
                        file_format=fmt.upper(),
                        task=task,
                        submitted_at=now_iso_initial,
                    )
                )
        elif config.export.export_vector_merged:
            log.info(
                "  skipping merged-stand vector layer: merge is disabled, so "
                "the stand is the SNIC superpixel and stands_snic already is it"
            )

        # 4c. SNIC superpixel vectors
        if config.export.export_vector_snic:
            log.info("  building SNIC superpixel vector layer...")
            snic_fc, snic_parts = _layer_by_part(
                _build_snic_feature_collection,
                ctx=ctx, config=config, scale=scale, parts=parts, id_field="stand_id",
            )
            snic_n_features = _count_by_part(snic_parts, context="stands_snic polygons")[
                "n_features"
            ]
            log.info("  stands_snic: %s features", snic_n_features)

            vector_layers[_SNIC_LAYER_NAME] = {
                "description": (
                    "One polygon per SNIC superpixel. Attributes include the "
                    "raw SNIC label (snic_label), the assigned cluster_id, and "
                    "per-superpixel means of every features_* band fed to "
                    "clustering. Use for methodology / debugging."
                ),
                "n_features": snic_n_features,
                "roi_parts": len(parts),
                "geometry_type": "Polygon",
                "id_field": "stand_id",
                "id_renumbering": (
                    "1..N, sorted by centroid latitude descending then "
                    "longitude ascending, the centroid being the mean "
                    "position of the polygon's pixel centres. Deterministic "
                    "pure function of the SNIC geometry; same inputs always "
                    "produce the same numbering."
                ),
                "shp_attributes": list(_SHP_SELECTORS_SNIC),
                "geojson_attributes": "all SHP attributes plus per-superpixel "
                                      "means of every features_* band and of "
                                      "the sine and cosine of each angle band "
                                      "(<band>_sin, <band>_cos)",
            }
            for fmt in config.export.vector_formats:
                filename = f"{config.name}_{_SNIC_LAYER_NAME}"
                task = self._submit_drive_vector_export(
                    feature_collection=snic_fc,
                    filename=filename,
                    drive_folder=drive_folder,
                    file_format=fmt,
                    selectors=(
                        list(_SHP_SELECTORS_SNIC) if fmt == "shp" else None
                    ),
                )
                drive_exports[f"vector_{_SNIC_LAYER_NAME}_{fmt}"] = (
                    _format_task_entry(
                        folder=drive_folder,
                        filename=f"{filename}{_filename_ext(fmt)}",
                        file_format=fmt.upper(),
                        task=task,
                        submitted_at=now_iso_initial,
                    )
                )

        # 4d. Dissolved cluster vectors
        if config.export.export_vector_dissolved:
            log.info("  building dissolved cluster vector layer...")
            dissolved_fc, dissolved_parts = _layer_by_part(
                _build_dissolved_feature_collection,
                ctx=ctx, config=config, scale=scale, parts=parts, id_field="unit_id",
            )
            dissolved_n_features = _count_by_part(
                dissolved_parts, context="stands_dissolved polygons"
            )["n_features"]
            log.info(
                "  stands_dissolved: %s features (after min_stand_pixels filter)",
                dissolved_n_features,
            )

            vector_layers[_DISSOLVED_LAYER_NAME] = {
                "description": (
                    "One polygon per connected same-cluster region. Forester-"
                    "facing management units. Filtered by "
                    f"vector_min_stand_pixels={config.export.vector_min_stand_pixels} "
                    "to drop speckle from misclassification."
                ),
                "n_features": dissolved_n_features,
                "roi_parts": len(parts),
                "geometry_type": "Polygon",
                "id_field": "unit_id",
                "id_renumbering": (
                    "1..M, sorted by centroid latitude descending then "
                    "longitude ascending, the centroid being the mean "
                    "position of the polygon's pixel centres, AFTER "
                    "min-pixel filtering. Deterministic pure function of the "
                    "cluster geometry."
                ),
                "min_stand_pixels": config.export.vector_min_stand_pixels,
                "shp_attributes": list(_SHP_SELECTORS_DISSOLVED),
                "geojson_attributes": (
                    "all SHP attributes plus profile_<band>_p50 columns from "
                    "cluster_profiles.csv (median of each feature band over "
                    "the unit's cluster, in original units)"
                ),
            }
            for fmt in config.export.vector_formats:
                filename = f"{config.name}_{_DISSOLVED_LAYER_NAME}"
                task = self._submit_drive_vector_export(
                    feature_collection=dissolved_fc,
                    filename=filename,
                    drive_folder=drive_folder,
                    file_format=fmt,
                    selectors=(
                        list(_SHP_SELECTORS_DISSOLVED) if fmt == "shp" else None
                    ),
                )
                drive_exports[f"vector_{_DISSOLVED_LAYER_NAME}_{fmt}"] = (
                    _format_task_entry(
                        folder=drive_folder,
                        filename=f"{filename}{_filename_ext(fmt)}",
                        file_format=fmt.upper(),
                        task=task,
                        submitted_at=now_iso_initial,
                    )
                )

        # 5. ROI metadata (compute area on the fly)
        try:
            roi_area_m2 = safe_get_info(roi.area(maxError=1), context="roi area")
            roi_area_km2 = round((roi_area_m2 or 0) / 1e6, 3)
        except Exception:  # noqa: BLE001 - area is informational, not critical
            roi_area_km2 = None

        # 6. Build the manifest
        now_iso = datetime.now(UTC).isoformat()
        manifest: dict[str, Any] = {
            "config_name": config.name,
            "pipeline_version": __version__,
            "git": git_state(),
            # The Python environment (round 9): fmu.utils.provenance.environment_state.
            "environment": environment_state(),
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
            "drive_exports": drive_exports,
            "vector_layers": vector_layers,
            "decisions_source": _DECISIONS_SOURCE,
        }

        return StageResult(
            outputs={"export_manifest": manifest},
            metadata={
                "n_drive_tasks": len(drive_exports),
                "drive_task_ids": [
                    e["task_id"] for e in drive_exports.values() if e["task_id"]
                ],
                "n_vector_layers": len(vector_layers),
                "n_clusters": len(distribution),
                "n_cached_assets": len(asset_paths),
                "drive_folder": drive_folder,
                "manifest": manifest,
            },
        )

    # ---------------------------------------------------------------------
    # Side-effecting hooks; overridden in tests to skip Drive submission
    # ---------------------------------------------------------------------

    def _submit_drive_export(
        self,
        *,
        image: ee.Image,
        roi: ee.Geometry,
        scale: int,
        filename: str,
        drive_folder: str,
    ) -> dict[str, Any] | None:
        """Submit a raster Drive export and return the task descriptor.

        `image` is exported as-is; the caller is responsible for band
        selection and pixel typing (e.g. toUint8() for the label map).
        Default implementation actually submits. Tests can override this
        to return a fake task descriptor without hitting GEE batch.
        """
        task = ee.batch.Export.image.toDrive(
            image=image,
            description=filename,
            folder=drive_folder,
            fileNamePrefix=filename,
            region=roi,
            scale=scale,
            maxPixels=1_000_000_000,
            fileFormat="GeoTIFF",
        )
        task.start()
        task_id = task.id
        log.info(
            "  submitted raster Drive export: task_id=%s, folder='%s', file='%s.tif'",
            task_id,
            drive_folder,
            filename,
        )
        return {"id": task_id}

    def _submit_drive_vector_export(
        self,
        *,
        feature_collection: ee.FeatureCollection,
        filename: str,
        drive_folder: str,
        file_format: str,
        selectors: list[str] | None,
    ) -> dict[str, Any] | None:
        """Submit a vector Drive export and return the task descriptor.

        `file_format`: "shp" or "geojson" (matches Literal in
        ExportParams.vector_formats). Mapped to GEE's "SHP" / "GeoJSON".

        `selectors`: list of property names to export. None = all
        properties. SHP exports pass the SHP-safe (<=10 char) subset;
        GeoJSON passes None for full schema.

        Default implementation actually submits. Tests can override.
        """
        gee_format = "SHP" if file_format == "shp" else "GeoJSON"
        kwargs: dict[str, Any] = {
            "collection": feature_collection,
            "description": f"{filename}_{file_format}",
            "folder": drive_folder,
            "fileNamePrefix": filename,
            "fileFormat": gee_format,
        }
        if selectors is not None:
            kwargs["selectors"] = selectors

        task = ee.batch.Export.table.toDrive(**kwargs)
        task.start()
        task_id = task.id
        log.info(
            "  submitted vector Drive export: task_id=%s, folder='%s', "
            "file='%s%s', format=%s",
            task_id,
            drive_folder,
            filename,
            _filename_ext(file_format),
            gee_format,
        )
        return {"id": task_id}


# ---------------------------------------------------------------------
# Pure helpers (existing)
# ---------------------------------------------------------------------


def _build_raw_feature_export_image(ctx: PipelineContext) -> ee.Image:
    """Concatenate every features_* image in ORIGINAL units for the raster.

    Drops only the obs_count metadata bands (matching the vector path and
    profiling's _EXCLUDE_BANDS); keeps the interpretable per-pixel features
    (including residual_variance and annual_rainfall) so the exported GeoTIFF
    is self-describing in real units.
    """
    all_features = _feature_source_image(ctx)
    excluded_metadata_bands = ee.List(["ndvi_obs_count", "nirv_obs_count"])
    kept = all_features.bandNames().removeAll(excluded_metadata_bands)
    return all_features.select(kept)


def _feature_source_image(ctx: PipelineContext) -> ee.Image:
    """The per-pixel feature image in ORIGINAL units for the active arm.

    Embedding arm: the single embedding image (present in context only then).
    Handcrafted arm: the four feature images concatenated. Band-name-based
    exclusions downstream are no-ops on embedding bands (A00..A63).
    """
    if ctx.has("embedding_features"):
        return ctx.get("embedding_features")
    return ee.Image.cat([
        ctx.get("optical_features"),
        ctx.get("radar_features"),
        ctx.get("structure_features"),
        ctx.get("static_features"),
    ])


def _with_angle_sin_cos(stack: ee.Image) -> ee.Image:
    """`stack` with the sine and cosine of each of its angle bands added, by the clustering stage's rule.

    The angle bands and their pairs are those of the clustering stage's
    _decompose_cyclic_bands, reused so that the stand layers average the values the
    clustering takes: aspect, made radians from degrees, and every band with "_phase_" in
    its name, in radians, each as <band>_sin and <band>_cos per pixel; a cell whose slope
    is 0 has the aspect pair (0, 0), no direction (review A5); a stack with aspect and no
    slope is refused. The bands of `stack` stay as they are, so the layers' plain means of
    the angles keep their columns (review C10), with the means of the pairs beside them
    (round 14; round 13's question 33, answered (a)). A stack with no angle band, the
    embedding arm's, is returned as it is. One request, for the stack's band names.
    """
    decomposed, angle_bands = _decompose_cyclic_bands(stack)
    if not angle_bands:
        return stack
    return stack.addBands(
        decomposed.select([f"{band}_{part}" for band in angle_bands for part in ("sin", "cos")])
    )


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
            maxPixels=1_000_000_000,
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


def _inventory_cached_assets(
    config_name: str,
    fingerprint: str | None = None,
    *,
    key_for: Callable[[str], str] | None = None,
) -> dict[str, str]:
    """Discover cached assets for this config by walking the stage registry.

    The key in each asset's name is `key_for(stage name)` when given (the run's
    cache layout: one key per stage in the per-step layout, round 9), else
    `fingerprint` for every stage (the legacy layout).

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
            path = cached_asset_path(
                config_name,
                stage_name,
                output_key,
                key_for(stage_name) if key_for is not None else fingerprint,
            )
            if asset_exists(path):
                paths[output_key] = path
    return paths


# ---------------------------------------------------------------------
# Pure helpers (new — vector building)
# ---------------------------------------------------------------------


def _filename_ext(file_format: str) -> str:
    """Return the on-disk extension for a Drive Export.table.toDrive output.

    GEE's SHP export produces a zip bundle; GeoJSON produces a .geojson.
    """
    return {"shp": ".zip", "geojson": ".geojson"}[file_format]


def _format_task_entry(
    *,
    folder: str,
    filename: str,
    file_format: str,
    task: dict[str, Any] | None,
    submitted_at: str,
) -> dict[str, Any]:
    """Standard manifest entry shape for a single Drive task."""
    return {
        "folder": folder,
        "filename": filename,
        "format": file_format,
        "task_id": task["id"] if task else None,
        "submitted_at": submitted_at if task else None,
        "task_submitted": task is not None,
    }


def _stand_polygon_counts(fc: ee.FeatureCollection) -> dict[str, int]:
    """How many distinct stands the merged polygon collection actually holds.

    `reduceToVectors` emits one polygon per *connected component* of a label,
    not one per label, so a stand that is spatially disconnected comes back as
    several polygons sharing a `stand_lbl`. The feature count then overstates
    the delineation, and `stand_id` -- assigned 1..N over polygons -- stops
    being a stand identifier.

    One `aggregate_array` and a client-side count: a few hundred integers, and
    it gives the distinct count, the split count and the worst case together.
    Counting distinct server-side would give only the first.
    """
    labels = safe_get_info(
        fc.aggregate_array("stand_lbl"), context="stands_merged stand labels"
    )
    pieces: dict[int, int] = {}
    for raw in labels or []:
        key = int(float(raw))
        pieces[key] = pieces.get(key, 0) + 1
    split = [n for n in pieces.values() if n > 1]
    return {
        "n_stands": len(pieces),
        "n_split": len(split),
        "max_pieces": max(split, default=1),
    }


def _warn_on_split_stands(counts: dict[str, int], n_features: int) -> None:
    """Say so when the polygon count is not the stand count."""
    if not counts["n_split"]:
        return
    log.warning(
        "  stands_merged: %d polygon(s) for %d stand(s) -- %d stand(s) are "
        "spatially disconnected and vectorised into up to %d pieces each. "
        "Most likely the ROI clip cutting a stand that straddles a concave "
        "part of the boundary; a disconnected SNIC label would do it too. "
        "Dissolve on stand_lbl to recover one feature per stand, and do not "
        "read the feature count as a stand count.",
        n_features,
        counts["n_stands"],
        counts["n_split"],
        counts["max_pieces"],
    )


# ---------------------------------------------------------------------
# The vector layers one ROI part at a time (round 9, issue #44 item 11)
# ---------------------------------------------------------------------


def _roi_parts(roi: ee.Geometry, scale: int) -> list[ee.Geometry]:
    """The ROI's polygons, for building and counting the vector layers one at a time.

    On an ROI of several polygons (the Odisha boxes) counting a layer's polygons
    in one request timed out (Dhenkanal's eight boxes), and reading a layer back
    in one request failed above 5,000 polygons (Koraput's superpixels).
    odisha_script/odisha_read_back_export.py showed that one part at a time gives
    the same layers. The parts are the ROI's own polygons (`geometries()`), so
    they keep its projection and its edges. An ROI of one polygon is returned
    whole, and its layers are built exactly as before round 9.

    Two parts closer than two pixels could hold the two halves of one connected
    stand, which a part at a time would vectorise as two polygons: then the ROI
    is built whole, with a warning. One request for the count of parts, one for
    the distances between them.
    """
    n = int(safe_get_info(roi.geometries().size(), context="ROI parts"))
    if n <= 1:
        return [roi]
    parts = [ee.Geometry(roi.geometries().get(i)) for i in range(n)]
    gaps = safe_get_info(
        ee.List(
            [parts[i].distance(parts[j], maxError=1) for i in range(n) for j in range(i + 1, n)]
        ),
        context="distances between ROI parts",
    )
    nearest = min(float(g) for g in gaps)
    if nearest < 2 * scale:
        log.warning(
            "  ROI parts lie %.1f m apart, within two pixels of each other: the vector "
            "layers are built over the whole ROI, not a part at a time", nearest,
        )
        return [roi]
    return parts


def _layer_by_part(
    build: Callable[..., ee.FeatureCollection],
    *,
    ctx: PipelineContext,
    config: Config,
    scale: int,
    parts: list[ee.Geometry],
    id_field: str,
) -> tuple[ee.FeatureCollection, list[ee.FeatureCollection]]:
    """A vector layer built one ROI part at a time: (the whole layer, each part's layer).

    Each part's layer is the builder's over that part; the whole layer is their
    union, numbered 1..N over all parts by the builders' own rule
    (`_renumber_by_centroid`), which is what the Drive export sends. With one
    part, the builder's layer over it, unchanged.
    """
    if len(parts) == 1:
        layer = build(ctx=ctx, config=config, scale=scale, region=parts[0])
        return layer, [layer]
    per_part = [build(ctx=ctx, config=config, scale=scale, region=part) for part in parts]
    whole = _renumber_by_centroid(ee.FeatureCollection(per_part).flatten(), id_field=id_field)
    return whole, per_part


def _count_by_part(
    per_part: list[ee.FeatureCollection],
    *,
    context: str,
    label_property: str | None = None,
) -> dict[str, int]:
    """A layer's polygons counted one part at a time, one request per part.

    With `label_property` (`stand_lbl` of the merged layer), also the distinct
    stands, how many are in more than one piece, and the most pieces of one, as
    `_stand_polygon_counts` gives them for a whole layer. A stand cannot be in two
    parts: the parts are at least two pixels apart (`_roi_parts`).
    """
    n_features = 0
    pieces: dict[int, int] = {}
    for i, layer in enumerate(per_part):
        got = safe_get_info(
            ee.Dictionary(
                {
                    "n": layer.size(),
                    "labels": layer.aggregate_array(label_property)
                    if label_property
                    else ee.List([]),
                }
            ),
            context=f"{context}, part {i + 1} of {len(per_part)}",
        )
        n_features += int(got["n"])
        for raw in got["labels"] or []:
            key = int(float(raw))
            pieces[key] = pieces.get(key, 0) + 1
    split = [n for n in pieces.values() if n > 1]
    return {
        "n_features": n_features,
        "n_stands": len(pieces),
        "n_split": len(split),
        "max_pieces": max(split, default=1),
    }


def _vectorise_with_pixel_centres(
    label_image: ee.Image, *, region: ee.Geometry, scale: int, label_property: str
) -> ee.FeatureCollection:
    """One polygon per connected piece of each label, with its pixel count and pixel centres' mean.

    The one reduceToVectors call of each of the three layers. It groups by the first band, the
    label, and hands the bands after it to the reducer: ee.Image.pixelLonLat()'s 'longitude' and
    'latitude', the position of each pixel's centre in the grid the call works in (the label's
    grid at `scale`). countEvery gives the polygon its pixel count as 'count', as the default
    reducer did (review A6, round 13), and the mean of each band, by forEach in the order the
    bands come, its pixel centres' mean longitude and latitude under _PIXEL_CENTRES_LON and
    _PIXEL_CENTRES_LAT: the centroid of the pixels, with any hole left out (round 14; round 13's
    question 21, answered (a)). The geometry's centroid() counted as area the hole of some
    polygons whose hole touches the outer ring at a vertex, as area() did (review A6).
    """
    return label_image.addBands(ee.Image.pixelLonLat()).reduceToVectors(
        reducer=ee.Reducer.countEvery().combine(
            ee.Reducer.mean().forEach([_PIXEL_CENTRES_LON, _PIXEL_CENTRES_LAT])
        ),
        geometry=region,
        scale=scale,
        geometryType="polygon",
        eightConnected=True,
        labelProperty=label_property,
        maxPixels=int(1e9),
    )


def _build_merged_feature_collection(
    *,
    ctx: PipelineContext,
    config: Config,
    scale: int,
    region: ee.Geometry | None = None,
) -> ee.FeatureCollection:
    """Build the merged-stand vector layer -- the pipeline's actual product.

    Same shape as `_build_snic_feature_collection`, over `stand_clusters`
    instead of `snic_clusters`, with one deliberate difference: **stands with no
    cluster_id are kept**.

    The SNIC layer drops them, and that is right for a layer whose stated job is
    to trace *clustered* polygons back to their superpixels. It is wrong here.
    Under the merge design SNIC plus merge produce the stand and clustering only
    attaches a type label to a finished one, so a stand that clustering could not
    type is still a stand, and dropping it would quietly delete real delineated
    area from the deliverable. A run that fit k-means on 289 of 327 stands would
    have exported 289 polygons and looked complete.

    So `cluster_id` is null on exactly those stands, which makes the coverage gap
    visible in the layer itself rather than only in the log.

    How a stand gets its `cluster_id` (register entries
    `spec-export-stand-type-from-its-fit-row`, round 12, and
    `spec-export-stand-type-from-its-own-row-or-null`, round 13): a stand with a
    row takes that row's type, read as the type most of its own typed pixels
    carry (`_stand_row_types`), and so does a stand left out of the k-means fit
    with clustering.fit_excludes_stands_below_min_area on, whose row the fitted
    clusters type too. A stand with no typed pixel of its own has no row and gets
    a null type, in every cache layout. Until round 12 every stand got a vote,
    the commonest type among the typed pixels its polygon touches, each weighted
    by its share inside the polygon, and until round 13 the stands with no row
    and those left out of the fit still did. On the analysis grid a polygon
    touches only its own stand's pixels, so the vote and the row's type agree,
    except on the pieces of a stand whose pieces carry different types (cluster
    labels made before round 13), which now all take one, and on a piece with no
    typed pixel of a stand that has a row elsewhere, which was null and now takes
    the stand's type; on the legacy cache layout the vote could take in slivers of
    a neighbour's pixels.

    `region` (default: the ROI) is the area vectorised: one part of the ROI when
    the layer is built a part at a time (`_layer_by_part`).
    """
    stand_clusters: ee.Image = ctx.get(config.unit_label_key())
    cluster_labels: ee.Image = ctx.get("cluster_labels")
    roi: ee.Geometry = region if region is not None else ctx.get("roi")

    # Step 1: vectorize the stand labels. `stand_lbl` rather than `stand_label`
    # so the name survives SHP's 10-character field limit unchanged, and both
    # formats therefore carry the same column name. reduceToVectors keeps the
    # pixels whose centre is inside `roi`, while SNIC labelled the edge pixels the
    # ROI clip keeps too, so a stand drawn through them can come out in more
    # than one polygon, and one with no pixel centre inside gets none (review C17).
    # Each polygon gets its pixel count and its pixel centres' mean (round 14).
    stand_label_image = stand_clusters.toInt().rename("stand_lbl")
    polygons = _vectorise_with_pixel_centres(
        stand_label_image, region=roi, scale=scale, label_property="stand_lbl"
    )

    # Step 2: per-stand feature means, same exclusions as the SNIC layer. Plain means
    # of the pixel values, the angle bands too: aspect (degrees) and *_phase_* (radians)
    # come out as arithmetic means of angles, not circular means (review C10). The
    # clustering does not read them; it takes sine and cosine per pixel, and since
    # round 14 the stack holds those too, beside the angles (_with_angle_sin_cos), so
    # each stand also gets their means, as <band>_sin and <band>_cos.
    all_features = _feature_source_image(ctx)
    kept_feature_bands = all_features.bandNames().removeAll(
        ee.List(["ndvi_obs_count", "nirv_obs_count"])
    )
    polygons_with_features = _with_angle_sin_cos(
        all_features.select(kept_feature_bands)
    ).reduceRegions(
        collection=polygons,
        reducer=ee.Reducer.mean(),
        scale=scale,
    )

    # Step 3: attach cluster_id, the type of the stand's own row (round 12), read
    # from its own typed pixels. Null where the stand has no typed pixel of its
    # own -- clustering never reached it: non-habitat, or a band with no data over
    # it (on the legacy cache layout, see _stand_row_types) -- in every cache
    # layout, with no vote over the pixels its polygon touches (round 13). Not
    # filtered.
    polygons_typed = _take_the_fit_rows_types(
        polygons_with_features,
        _stand_row_types(cluster_labels, stand_clusters, roi, scale),
    )

    # Steps 4-5: size and geometry attributes (n_pixels and area_ha from the count,
    # the centroid from the pixel centres' mean), drop bookkeeping, renumber by
    # centroid.
    polygons_with_geom = polygons_typed.map(
        lambda f: _add_geom_attrs(f, scale)
    ).map(_drop_internal_properties)

    renumbered = _renumber_by_centroid(polygons_with_geom, id_field="stand_id")

    # Step 6: merge provenance, added last so that nothing above sees it.
    return _attach_stand_provenance(renumbered, ctx)


def _stand_row_types(
    cluster_labels: ee.Image, unit_labels: ee.Image, region: ee.Geometry, scale: int
) -> ee.Dictionary:
    """{stand label as "%d": its row's type} for every stand with a typed pixel.

    The clustering stage averages the features over each stand, all of its
    pieces together, trains k-means on one row per stand (the means at one of
    its pixels inside the habitat mask where no band is missing, drawn at
    random) and then types every pixel of the image those rows were drawn from.
    A stand has the same means at each of its pixels, so every typed pixel of it
    carries the type the fitted clusters give its row, and on the analysis grid
    it has typed pixels exactly when it has a row: the commonest type over its
    own typed pixels is its row's type. Until round 13 the clustering stage
    averaged each connected piece of a stand on its own (reduceConnectedComponents;
    review B14), so in its cluster labels a stand in several pieces can carry
    different types on different pieces, with its row on one of them; for it
    this gives the commonest type over its typed pixels, which is its row's type
    unless the row was drawn on a piece of another type (the clustering stage
    does not record which pixel it drew; question 3 of
    docs/handoff/2026-10-19-round12.md). Grouped by label, not
    voted over the polygon: only the stand's own pixels count. On the legacy
    cache layout the type image lies on another grid than the labels, so a
    stand's pixels there are those whose centres it holds on the type grid: a
    stand with a row may then have none (it then gets a null type, round 13),
    and a stand with no row may have some (it then takes their type). The
    clusterer itself is not kept, so the type is read from the typed pixels.

    One reduction over `region`, in the grid of `cluster_labels`. A stand whose
    pixels are all untyped still forms a group, but one without a "mode" (seen
    on Earth Engine, 19 Oct 2026); those groups are dropped, so a stand with no
    typed pixel is not in the dictionary.
    """
    grouped = (
        cluster_labels.toInt()
        .rename("cluster_id")
        .addBands(unit_labels.toInt().rename("stand_lbl"))
        .reduceRegion(
            reducer=ee.Reducer.mode().group(groupField=1, groupName="stand_lbl"),
            geometry=region,
            scale=scale,
            maxPixels=int(1e9),
        )
    )
    typed = ee.List(grouped.get("groups")).map(
        lambda g: ee.Algorithms.If(ee.Dictionary(g).contains("mode"), g, None), True
    )
    return ee.Dictionary.fromLists(
        typed.map(lambda g: ee.Number(ee.Dictionary(g).get("stand_lbl")).format("%d")),
        typed.map(lambda g: ee.Dictionary(g).get("mode")),
    )


def _take_the_fit_rows_types(
    fc: ee.FeatureCollection, fit_row_types: ee.Dictionary
) -> ee.FeatureCollection:
    """Set each polygon's `cluster_id` to its stand's row type, or to null where the stand has none.

    `fit_row_types` is `_stand_row_types`: every stand with a typed pixel of its
    own, the stands left out of the k-means fit among them, whose rows the fitted
    clusters type too (round 13, question 2 of docs/handoff/2026-10-19-round12.md
    answered (b)). Looked up by `stand_lbl`, as the provenance is, so every piece
    of a stand in several pieces takes the same type. A polygon whose stand is not
    in `fit_row_types` gets a null `cluster_id`, whatever typed pixels it touches
    (round 13, question 1 answered (b)).
    """

    def retype(feature: ee.Feature) -> ee.Feature:
        key = ee.Number(feature.get("stand_lbl")).format("%d")
        # The lookup has a default (-1), so that the branch is safe to compute when the
        # key is missing: Earth Engine may evaluate both cases of If(). The branch is
        # chosen only when the key is there, so -1 never reaches the layer.
        return ee.Feature(
            ee.Algorithms.If(
                fit_row_types.contains(key),
                feature.set("cluster_id", fit_row_types.get(key, -1)),
                feature.set({"cluster_id": None}),
            )
        )

    return fc.map(retype)


def _stand_provenance_fields(ctx: PipelineContext) -> tuple[str, ...]:
    """The provenance properties `stands_merged` carries in this run.

    All of `PROVENANCE_FIELDS` when the merge stage put `stand_provenance` in
    the context, none when it did not (a context built by hand, or by a merge
    stage older than the provenance).
    """
    return PROVENANCE_FIELDS if ctx.has("stand_provenance") else ()


def _attach_stand_provenance(
    fc: ee.FeatureCollection, ctx: PipelineContext
) -> ee.FeatureCollection:
    """Add the merge's per-stand provenance to every stand polygon.

    The properties are `fmu.utils.region_merge.PROVENANCE_FIELDS` (documented
    there): how many superpixels the stand is made of, how many merges of each
    kind it contains, and whether and why it ended below the minimum size. They
    are looked up by `stand_lbl`, the merge's own stand id, so every polygon of
    a stand that was split into pieces carries the same values. Only `set()` is
    called on a feature: no geometry is changed, and no existing property is
    changed unless it already has one of the six names, which `set()` would
    overwrite (no property of a stand file exported so far has such a name).

    Every `stand_lbl` on the layer must be a key of `stand_provenance`. One that
    is not makes the server-side lookup fail, and with it the whole layer: a
    loud failure on purpose, rather than a polygon written with empty or wrong
    provenance. It cannot happen in a pipeline run, where the merge stage
    writes `stand_clusters` and `stand_provenance` from the same result; it can
    with a context put together by hand from two different merges.
    """
    if not _stand_provenance_fields(ctx):
        log.warning(
            "  stands_merged: no stand_provenance in the context, so the layer "
            "is written without the merge provenance properties."
        )
        return fc
    stand_provenance: dict[int, dict[str, Any]] = ctx.get("stand_provenance")
    lookups = {
        name: ee.Dictionary(
            {str(sid): p[name] for sid, p in stand_provenance.items()}
        )
        for name in PROVENANCE_FIELDS
    }

    def attach(feature: ee.Feature) -> ee.Feature:
        key = ee.Number(feature.get("stand_lbl")).format("%d")
        return ee.Feature(
            feature.set({name: lookups[name].get(key) for name in PROVENANCE_FIELDS})
        )

    return fc.map(attach)


def _build_snic_feature_collection(
    *,
    ctx: PipelineContext,
    config: Config,
    scale: int,
    region: ee.Geometry | None = None,
) -> ee.FeatureCollection:
    """Build the SNIC superpixel vector layer.

    Steps (all server-side):
      1. Vectorize snic_clusters via reduceToVectors; each polygon
         carries snic_label = raw SNIC hash, its pixel count ('count')
         and its pixel centres' mean longitude and latitude
         (_vectorise_with_pixel_centres, round 14).
      2. Attach per-superpixel feature means via reduceRegions on the
         concatenated features_* image stack (minus metadata bands like
         ndvi_obs_count, which match profiling's _EXCLUDE_BANDS), and since
         round 14 the means of the sine and cosine of each angle band
         (_with_angle_sin_cos).
      3. Attach cluster_id via reduceRegions(mode) on cluster_labels.
      4. Drop superpixels that fall entirely outside the habitat mask
         (cluster_labels is null there → no cluster_id). These are
         genuinely unclustered: the methodology layer's job is to trace
         clustered polygons back to SNIC, so unclustered SNIC has no
         place here. Typical drop rate: ~40-50% for an AOI with
         significant non-habitat (water, built).
      5. Add n_pixels and area_ha from reduceToVectors' 'count',
         centroid_lat and centroid_lon from its pixel centres' mean
         (since round 14; the geometry's centroid until then), and perim_m
         from the geometry. Then drop 'count', the two means and the
         reducer-leftover 'mode' via explicit property selection.
      6. Sort by centroid (lat desc, lon asc) and renumber stand_id 1..N.

    Returns a FeatureCollection with all attributes attached. The caller
    selects per-format subsets via the `selectors` arg on export. `region`
    (default: the ROI) is the area vectorised (`_layer_by_part`).
    """
    snic_clusters: ee.Image = ctx.get("snic_clusters")
    cluster_labels: ee.Image = ctx.get("cluster_labels")
    roi: ee.Geometry = region if region is not None else ctx.get("roi")

    # Step 1: vectorize SNIC labels. Rename to a known band name so
    # labelProperty is deterministic regardless of segmentation's band naming.
    # Only pixels whose centre is inside `roi` are kept, so a superpixel drawn
    # through the ROI's partly covered edge pixels can come out in more than one
    # polygon (review C17), as in the merged layer.
    snic_label_image = snic_clusters.toInt().rename("snic_label")
    polygons = _vectorise_with_pixel_centres(
        snic_label_image, region=roi, scale=scale, label_property="snic_label"
    )

    # Step 2: attach per-superpixel feature means: plain means, so aspect and
    # *_phase_* are arithmetic means of angles here too (review C10), with the
    # means of their sine and cosine beside them since round 14
    # (_with_angle_sin_cos, as in the merged layer).
    # ee.Image.cat concatenates multi-band images; band names must be unique
    # across the inputs, which they are by construction (ndvi_*, vv_*, vh_*,
    # canopy_*, elevation/slope/aspect/...). We drop the obs_count metadata
    # bands first; they aren't features and shouldn't be in stand attrs
    # (matches profiling.py's _EXCLUDE_BANDS).
    all_features = _feature_source_image(ctx)
    feature_band_names = all_features.bandNames()
    excluded_metadata_bands = ee.List(["ndvi_obs_count", "nirv_obs_count"])
    kept_feature_bands = feature_band_names.removeAll(excluded_metadata_bands)
    feature_stack_for_attrs = _with_angle_sin_cos(all_features.select(kept_feature_bands))

    polygons_with_features = feature_stack_for_attrs.reduceRegions(
        collection=polygons,
        reducer=ee.Reducer.mean(),
        scale=scale,
    )

    # Step 3: attach cluster_id via mode. Within a single SNIC superpixel
    # every pixel should already share the same cluster_id (because
    # clustering operates on superpixel means), but mode is safe against
    # any boundary noise. For superpixels that fall outside the habitat
    # mask, cluster_labels has no data → mode returns null, which we
    # filter out in Step 4.
    cluster_id_img = cluster_labels.toInt().rename("cluster_id")
    polygons_with_cluster = cluster_id_img.reduceRegions(
        collection=polygons_with_features,
        reducer=ee.Reducer.mode(),
        scale=scale,
    )

    # Step 4: drop unclustered superpixels (mode is null) and rename
    # mode → cluster_id. ee.Filter.notNull on a property removes features
    # where that property is missing or null.
    polygons_clustered = polygons_with_cluster.filter(
        ee.Filter.notNull(["mode"])
    ).map(_rename_mode_to_cluster_id)

    # Step 5: size and geometry attributes (n_pixels and area_ha from the
    # 'count' reduceToVectors added, the centroid from the pixel centres' mean
    # it added beside it), then drop bookkeeping properties we don't want to
    # ship ('count', now n_pixels, the two means, now the centroid, plus 'mode'
    # which is now a duplicate of cluster_id).
    polygons_with_geom = polygons_clustered.map(
        lambda f: _add_geom_attrs(f, scale)
    ).map(_drop_internal_properties)

    # Step 6: sort by centroid and renumber stand_id 1..N.
    return _renumber_by_centroid(polygons_with_geom, id_field="stand_id")


def _build_dissolved_feature_collection(
    *,
    ctx: PipelineContext,
    config: Config,
    scale: int,
    region: ee.Geometry | None = None,
) -> ee.FeatureCollection:
    """Build the dissolved cluster vector layer.

    Steps (all server-side except cluster_profiles lookup table construction):
      1. Vectorize cluster_labels via reduceToVectors with eightConnected=True;
         each polygon = one connected same-cluster region, with its pixel
         count and its pixel centres' mean (_vectorise_with_pixel_centres).
      2. Add n_pixels and area_ha from reduceToVectors' 'count', the
         centroid from the pixel centres' mean (since round 14; the
         geometry's until then), and perim_m from the geometry.
      3. Filter by vector_min_stand_pixels (drops speckle).
      4. Attach profile_<band>_p50 columns from the cluster_profiles list of
         dicts, joined by cluster_id.
      5. Sort by centroid (lat desc, lon asc) and renumber unit_id 1..M.

    `region` (default: the ROI) is the area vectorised (`_layer_by_part`).
    """
    cluster_labels: ee.Image = ctx.get("cluster_labels")
    roi: ee.Geometry = region if region is not None else ctx.get("roi")
    cluster_profiles: list[dict[str, Any]] = ctx.get("cluster_profiles")
    min_pixels = config.export.vector_min_stand_pixels

    # Step 1: vectorize cluster_labels. Connected same-cluster pixels become
    # one polygon. eightConnected matches SNIC's connectivity by default.
    cluster_id_img = cluster_labels.toInt().rename("cluster_id")
    polygons = _vectorise_with_pixel_centres(
        cluster_id_img, region=roi, scale=scale, label_property="cluster_id"
    )

    # Step 2: size and geometry attributes, then drop GEE's auto-added
    # 'count' bookkeeping property, which _add_geom_attrs has copied to
    # 'n_pixels' (round 13, review A6), and the pixel centres' mean, which it
    # has copied to the centroid (round 14).
    polygons_with_geom = polygons.map(
        lambda f: _add_geom_attrs(f, scale)
    ).map(_drop_internal_properties)

    # Step 3: filter by min pixel count.
    filtered = polygons_with_geom.filter(
        ee.Filter.gte("n_pixels", min_pixels)
    )

    # Step 4: attach profile_<band>_p50 columns. For each profile column,
    # build a server-side dict {str_cluster_id: value}; for each feature,
    # look up the value via cluster_id. Only attach _p50 (median) columns
    # to keep the schema manageable; the full per-cluster profile remains
    # available in cluster_profiles.csv.
    #
    # Defensive: scan the union of keys across all profiles (an empty
    # cluster's profile might be sparse), and skip None values (which
    # reduceRegion returns when a cluster has zero pixels in the ROI).
    if cluster_profiles:
        profile_cols = sorted({
            c for p in cluster_profiles for c in p if c.endswith("_p50")
        })
        lookup: dict[str, ee.Dictionary] = {}
        for col in profile_cols:
            entries = {
                str(p["cluster_id"]): p[col]
                for p in cluster_profiles
                if p.get(col) is not None
            }
            if entries:
                lookup[col] = ee.Dictionary(entries)

        if lookup:
            def attach_profile(feature: ee.Feature) -> ee.Feature:
                cid_str = ee.Number(feature.get("cluster_id")).format("%d")
                attrs = {
                    f"profile_{col}": d.get(cid_str)
                    for col, d in lookup.items()
                }
                return ee.Feature(feature.set(attrs))

            filtered = filtered.map(attach_profile)

    # Step 5: sort by centroid and renumber unit_id 1..M.
    return _renumber_by_centroid(filtered, id_field="unit_id")


def _add_geom_attrs(feature: ee.Feature, scale: int) -> ee.Feature:
    """Server-side: attach area_ha, perim_m, n_pixels, centroid_lat, centroid_lon.

    `n_pixels` is the 'count' reduceToVectors puts on every polygon it makes, its
    pixels at the analysis scale, and `area_ha` is that count at the analysis
    scale (n_pixels x scale² / 10,000): the area on the analysis grid, consistent
    with n_pixels. Until round 13 both came from the geometry's area(), which for
    some polygons with a hole that touches the outer ring at a vertex adds the
    hole instead of subtracting it (review A6: stand 83 of
    sanjay_van_alphaearth_keptland_r9, 823 pixels, read 1,827 pixels and
    18.27 ha). The perimeter is still the geometry's, and right on those polygons
    (the rings' length, the hole's included). `centroid_lat` and `centroid_lon` are
    the mean position of the polygon's pixel centres, which the same
    reduceToVectors call gives it under _PIXEL_CENTRES_LAT and _PIXEL_CENTRES_LON
    (_vectorise_with_pixel_centres), and `_renumber_by_centroid` numbers stand_id
    and unit_id by them. Until round 14 the centroid was the geometry's, which had
    the same hole error as area(): the centroid with the hole counted as area (on
    the merged layers of r9 and round 12, 54 of 7,371 centroids more than 1 m from
    the hole-subtracted one, 52 of them at the holes-added one, up to 35 m: stand
    83's 35.1 m), so a few ids followed the error (round 13's question 21,
    answered (a) for round 14). So the builders run this before
    `_drop_internal_properties` drops 'count' and the two means, and no reduction
    in between writes a property of those names. On the legacy cache layout
    `stands_dissolved` vectorises a type image on a geographic grid, whose pixels
    are not scale² in area, so there its area_ha is the pixel count at the
    nominal scale.
    """
    perimeter_m = feature.geometry().perimeter(maxError=1)
    n_pixels = ee.Number(feature.get("count"))
    # ee.Feature(...) is a cast: Element.set() is typed as returning Element, and
    # every one of these helpers is annotated -> ee.Feature because it is handed to
    # FeatureCollection.map(). Same wrap at the three sites below.
    return ee.Feature(feature.set({
        "area_ha": n_pixels.multiply(scale * scale).divide(10000),
        "perim_m": perimeter_m,
        "n_pixels": n_pixels,
        "centroid_lat": feature.get(_PIXEL_CENTRES_LAT),
        "centroid_lon": feature.get(_PIXEL_CENTRES_LON),
    }))


def _rename_mode_to_cluster_id(feature: ee.Feature) -> ee.Feature:
    """Move the value at property 'mode' to 'cluster_id'.

    reduceRegions with ee.Reducer.mode() writes the result under the
    reducer's name ('mode'). We want a stable 'cluster_id' property.
    The 'mode' property itself is dropped later by
    _drop_internal_properties (we can't drop it here because the
    server-side select() pattern would also strip every other property
    on the feature).
    """
    return ee.Feature(feature.set("cluster_id", feature.get("mode")))


# Properties to strip from the SNIC feature collection before export.
# - 'count' is auto-added by reduceToVectors (it's the source pixel count
#   per polygon, which _add_geom_attrs has already copied to 'n_pixels').
# - 'mode' is the leftover from reduceRegions(mode); we already copied its
#   value to 'cluster_id' via _rename_mode_to_cluster_id.
# - the pixel centres' mean longitude and latitude, which reduceToVectors adds
#   beside 'count' (_vectorise_with_pixel_centres, round 14) and
#   _add_geom_attrs has copied to 'centroid_lon' and 'centroid_lat'.
# Listing these explicitly is more robust than feature.set(k, None), which
# pydantic-style "drop the key" doesn't actually work in GEE's
# Feature.set() — None becomes a stored null, not a missing key.
_SNIC_INTERNAL_PROPERTIES_TO_DROP: tuple[str, ...] = (
    "count", "mode", _PIXEL_CENTRES_LON, _PIXEL_CENTRES_LAT,
)


def _drop_internal_properties(feature: ee.Feature) -> ee.Feature:
    """Strip bookkeeping properties from a SNIC feature.

    Uses propertyNames().removeAll() + selectArray() to keep all
    properties EXCEPT the listed ones. This is the server-side equivalent
    of `{k: v for k, v in props.items() if k not in DROP}`.
    """
    all_props = feature.propertyNames()
    kept_props = all_props.removeAll(ee.List(list(_SNIC_INTERNAL_PROPERTIES_TO_DROP)))
    # Feature.select(propertySelectors, newProperties=None, retainGeometry=True)
    # returns a new feature with only the specified properties.
    return feature.select(kept_props)


def _renumber_by_centroid(
    fc: ee.FeatureCollection, *, id_field: str
) -> ee.FeatureCollection:
    """Sort FC by centroid (lat desc, lon asc), assign sequential id 1..N.

    Server-side throughout. The sort key composes lat and lon into a single
    sortable number (GEE FC.sort takes one property only): we negate lat
    (so larger lat → smaller key, sorts first) and add lon scaled down so
    lon only breaks ties.

    The result is fully deterministic: the same FC with the same centroids
    will always produce the same numbering. This is the property that lets
    us treat the renumbering as reproducible (you don't need to memoize the
    output to reproduce it; just run the same code on the same input).

    Assumes _add_geom_attrs has already populated centroid_lat / centroid_lon:
    since round 14 the mean position of the polygon's pixel centres, until then
    the geometry's centroid.
    """
    def add_sort_key(feature: ee.Feature) -> ee.Feature:
        lat = ee.Number(feature.get("centroid_lat"))
        lon = ee.Number(feature.get("centroid_lon"))
        # -lat dominates; lon breaks ties.
        sort_key = lat.multiply(-_SORT_LAT_MULT).add(lon)
        return ee.Feature(feature.set("_sort_key", sort_key))

    sorted_fc = fc.map(add_sort_key).sort("_sort_key")
    size = sorted_fc.size()
    features_list = sorted_fc.toList(size)
    indices = ee.List.sequence(0, size.subtract(1))

    def assign_id(i: ee.ComputedObject) -> ee.Feature:
        idx = ee.Number(i)
        f = ee.Feature(features_list.get(idx))
        # Drop the internal sort key from the final output.
        return f.set(id_field, idx.add(1)).set("_sort_key", None)

    return ee.FeatureCollection(indices.map(assign_id))

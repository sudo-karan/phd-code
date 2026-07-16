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

  2. **SNIC superpixel vectors** (`stands_snic`): one polygon per SNIC
     superpixel with all per-superpixel feature means attached. The
     debugging / methodology layer; lets you trace from a polygon back
     to the SNIC label and inspect what fed clustering. Toggled via
     `export_vector_snic`.

  3. **Dissolved cluster vectors** (`stands_dissolved`): one polygon per
     connected same-cluster region, with cluster profile statistics
     attached. The forester-facing management-units layer. Toggled via
     `export_vector_dissolved`. Filtered by `vector_min_stand_pixels` to
     drop speckle.

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
    - "vector_stands_snic_{fmt}"       (one per format, if export_vector_snic)
    - "vector_stands_dissolved_{fmt}"  (one per format, if export_vector_dissolved)
  Past on-disk manifests are unaffected (archival), but any downstream
  code that reads `manifest["drive_export"]["task_id"]` must migrate to
  `manifest["drive_exports"]["raster_cluster_labels"]["task_id"]`.
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

# Vector layer canonical names. Used as filename infixes and manifest keys.
_SNIC_LAYER_NAME = "stands_snic"
_DISSOLVED_LAYER_NAME = "stands_dissolved"

# Composite sort-key for renumbering polygons by centroid lat-desc / lon-asc.
# Sort key = -lat * _SORT_LAT_MULT + lon. Larger latitudes get smaller (more
# negative) keys and sort first. The multiplier dominates the longitude
# contribution so longitude only breaks ties. Works for any AOI within ~1-2
# degrees of lat/lon extent (well beyond Sanjay Van's ~3 km extent).
_SORT_LAT_MULT = 1_000_000

# SHP attribute selectors. SHP has a hard 10-char field-name limit; everything
# in these lists is <= 10 chars. The GeoJSON exports omit the selectors arg
# entirely, so they include every property attached to the feature.
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
    required_inputs = {
        "roi",
        "cluster_labels",
        "feature_stack",
        "snic_clusters",
        "optical_features",
        "radar_features",
        "structure_features",
        "static_features",
        "cluster_profiles",
    }
    produces = {"export_manifest"}
    cacheable_outputs: ClassVar[set[str]] = set()  # always run; no GEE asset

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

        # 3. Inventory cached assets for this config
        asset_paths = _inventory_cached_assets(config.name)
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
            # cluster_id band, shared by the two feature rasters. Kept as a
            # plain band (GeoTIFF casts the whole image to a common type, so
            # it rides along as a float next to the feature bands).
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
                    _build_raw_feature_export_image(ctx).addBands(label_band),
                ),
                (
                    "raster_features_scaled",
                    f"{config.name}_features_scaled",
                    ctx.get("feature_stack").addBands(label_band),
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

        # 4b. SNIC superpixel vectors
        if config.export.export_vector_snic:
            log.info("  building SNIC superpixel vector layer...")
            snic_fc = _build_snic_feature_collection(
                ctx=ctx, config=config, scale=scale
            )
            snic_n_features = safe_get_info(
                snic_fc.size(), context="stands_snic feature count"
            )
            log.info("  stands_snic: %s features", snic_n_features)

            vector_layers[_SNIC_LAYER_NAME] = {
                "description": (
                    "One polygon per SNIC superpixel. Attributes include the "
                    "raw SNIC label (snic_label), the assigned cluster_id, and "
                    "per-superpixel means of every features_* band fed to "
                    "clustering. Use for methodology / debugging."
                ),
                "n_features": snic_n_features,
                "geometry_type": "Polygon",
                "id_field": "stand_id",
                "id_renumbering": (
                    "1..N, sorted by centroid latitude descending then "
                    "longitude ascending. Deterministic pure function of "
                    "the SNIC geometry; same inputs always produce the "
                    "same numbering."
                ),
                "shp_attributes": list(_SHP_SELECTORS_SNIC),
                "geojson_attributes": "all SHP attributes plus per-superpixel "
                                      "means of every features_* band",
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

        # 4c. Dissolved cluster vectors
        if config.export.export_vector_dissolved:
            log.info("  building dissolved cluster vector layer...")
            dissolved_fc = _build_dissolved_feature_collection(
                ctx=ctx, config=config, scale=scale
            )
            dissolved_n_features = safe_get_info(
                dissolved_fc.size(), context="stands_dissolved feature count"
            )
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
                "geometry_type": "Polygon",
                "id_field": "unit_id",
                "id_renumbering": (
                    "1..M, sorted by centroid latitude descending then "
                    "longitude ascending, AFTER min-pixel filtering. "
                    "Deterministic pure function of the cluster geometry."
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
            maxPixels=1e9,
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
    all_features = ee.Image.cat([
        ctx.get("optical_features"),
        ctx.get("radar_features"),
        ctx.get("structure_features"),
        ctx.get("static_features"),
    ])
    excluded_metadata_bands = ee.List(["ndvi_obs_count", "nirv_obs_count"])
    kept = all_features.bandNames().removeAll(excluded_metadata_bands)
    return all_features.select(kept)


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


def _build_snic_feature_collection(
    *,
    ctx: PipelineContext,
    config: Config,
    scale: int,
) -> ee.FeatureCollection:
    """Build the SNIC superpixel vector layer.

    Steps (all server-side):
      1. Vectorize snic_clusters via reduceToVectors; each polygon
         carries snic_label = raw SNIC hash.
      2. Attach per-superpixel feature means via reduceRegions on the
         concatenated features_* image stack (minus metadata bands like
         ndvi_obs_count, which match profiling's _EXCLUDE_BANDS).
      3. Attach cluster_id via reduceRegions(mode) on cluster_labels.
      4. Drop superpixels that fall entirely outside the habitat mask
         (cluster_labels is null there → no cluster_id). These are
         genuinely unclustered: the methodology layer's job is to trace
         clustered polygons back to SNIC, so unclustered SNIC has no
         place here. Typical drop rate: ~40-50% for an AOI with
         significant non-habitat (water, built).
      5. Add geometry-derived attributes (area_ha, perim_m, n_pixels,
         centroid_lat, centroid_lon). Drop GEE's auto-added 'count'
         and reducer-leftover 'mode' via explicit property selection.
      6. Sort by centroid (lat desc, lon asc) and renumber stand_id 1..N.

    Returns a FeatureCollection with all attributes attached. The caller
    selects per-format subsets via the `selectors` arg on export.
    """
    snic_clusters: ee.Image = ctx.get("snic_clusters")
    cluster_labels: ee.Image = ctx.get("cluster_labels")
    roi: ee.Geometry = ctx.get("roi")

    # Step 1: vectorize SNIC labels. Rename to a known band name so
    # labelProperty is deterministic regardless of segmentation's band naming.
    snic_label_image = snic_clusters.toInt().rename("snic_label")
    polygons = snic_label_image.reduceToVectors(
        geometry=roi,
        scale=scale,
        geometryType="polygon",
        eightConnected=True,
        labelProperty="snic_label",
        maxPixels=int(1e9),
    )

    # Step 2: attach per-superpixel feature means.
    # ee.Image.cat concatenates multi-band images; band names must be unique
    # across the inputs, which they are by construction (ndvi_*, vv_*, vh_*,
    # canopy_*, elevation/slope/aspect/...). We drop the obs_count metadata
    # bands first; they aren't features and shouldn't be in stand attrs
    # (matches profiling.py's _EXCLUDE_BANDS).
    all_features = ee.Image.cat([
        ctx.get("optical_features"),
        ctx.get("radar_features"),
        ctx.get("structure_features"),
        ctx.get("static_features"),
    ])
    feature_band_names = all_features.bandNames()
    excluded_metadata_bands = ee.List(["ndvi_obs_count", "nirv_obs_count"])
    kept_feature_bands = feature_band_names.removeAll(excluded_metadata_bands)
    feature_stack_for_attrs = all_features.select(kept_feature_bands)

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

    # Step 5: geometry-derived attributes, then drop bookkeeping properties
    # we don't want to ship (GEE's auto-added 'count' from reduceToVectors,
    # plus 'mode' which is now a duplicate of cluster_id).
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
) -> ee.FeatureCollection:
    """Build the dissolved cluster vector layer.

    Steps (all server-side except cluster_profiles lookup table construction):
      1. Vectorize cluster_labels via reduceToVectors with eightConnected=True;
         each polygon = one connected same-cluster region.
      2. Add geometry-derived attributes (area_ha, perim_m, n_pixels, centroid).
      3. Filter by vector_min_stand_pixels (drops speckle).
      4. Attach profile_<band>_p50 columns from the cluster_profiles list of
         dicts, joined by cluster_id.
      5. Sort by centroid (lat desc, lon asc) and renumber unit_id 1..M.
    """
    cluster_labels: ee.Image = ctx.get("cluster_labels")
    roi: ee.Geometry = ctx.get("roi")
    cluster_profiles: list[dict[str, Any]] = ctx.get("cluster_profiles")
    min_pixels = config.export.vector_min_stand_pixels

    # Step 1: vectorize cluster_labels. Connected same-cluster pixels become
    # one polygon. eightConnected matches SNIC's connectivity by default.
    cluster_id_img = cluster_labels.toInt().rename("cluster_id")
    polygons = cluster_id_img.reduceToVectors(
        geometry=roi,
        scale=scale,
        geometryType="polygon",
        eightConnected=True,
        labelProperty="cluster_id",
        maxPixels=int(1e9),
    )

    # Step 2: geometry-derived attributes, then drop GEE's auto-added
    # 'count' bookkeeping property (duplicates our 'n_pixels' but uses a
    # subtly different counting method; we ship n_pixels for consistency).
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
            c for p in cluster_profiles for c in p.keys() if c.endswith("_p50")
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
                return feature.set(attrs)

            filtered = filtered.map(attach_profile)

    # Step 5: sort by centroid and renumber unit_id 1..M.
    return _renumber_by_centroid(filtered, id_field="unit_id")


def _add_geom_attrs(feature: ee.Feature, scale: int) -> ee.Feature:
    """Server-side: attach area_ha, perim_m, n_pixels, centroid_lat, centroid_lon.

    `n_pixels` is computed from area at the analysis scale (area_m² / scale²),
    not from a separate pixel count, so it stays consistent with area_ha for
    consumers who derive one from the other.
    """
    geom = feature.geometry()
    area_m2 = geom.area(maxError=1)
    perimeter_m = geom.perimeter(maxError=1)
    centroid_coords = geom.centroid(maxError=1).coordinates()
    pixel_area_m2 = scale * scale
    return feature.set({
        "area_ha": area_m2.divide(10000),
        "perim_m": perimeter_m,
        "n_pixels": area_m2.divide(pixel_area_m2).round(),
        "centroid_lat": centroid_coords.get(1),
        "centroid_lon": centroid_coords.get(0),
    })


def _rename_mode_to_cluster_id(feature: ee.Feature) -> ee.Feature:
    """Move the value at property 'mode' to 'cluster_id'.

    reduceRegions with ee.Reducer.mode() writes the result under the
    reducer's name ('mode'). We want a stable 'cluster_id' property.
    The 'mode' property itself is dropped later by
    _drop_internal_properties (we can't drop it here because the
    server-side select() pattern would also strip every other property
    on the feature).
    """
    return feature.set("cluster_id", feature.get("mode"))


# Properties to strip from the SNIC feature collection before export.
# - 'count' is auto-added by reduceToVectors (it's the source pixel count
#   per polygon, which we already expose as 'n_pixels' from the geometry).
# - 'mode' is the leftover from reduceRegions(mode); we already copied its
#   value to 'cluster_id' via _rename_mode_to_cluster_id.
# Listing these explicitly is more robust than feature.set(k, None), which
# pydantic-style "drop the key" doesn't actually work in GEE's
# Feature.set() — None becomes a stored null, not a missing key.
_SNIC_INTERNAL_PROPERTIES_TO_DROP: tuple[str, ...] = ("count", "mode")


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

    Assumes _add_geom_attrs has already populated centroid_lat / centroid_lon.
    """
    def add_sort_key(feature: ee.Feature) -> ee.Feature:
        lat = ee.Number(feature.get("centroid_lat"))
        lon = ee.Number(feature.get("centroid_lon"))
        # -lat dominates; lon breaks ties.
        sort_key = lat.multiply(-_SORT_LAT_MULT).add(lon)
        return feature.set("_sort_key", sort_key)

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
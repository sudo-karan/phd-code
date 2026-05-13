"""Data-load stage. Loads S2 and S1 collections, cloud-masks S2,
builds the static S2 composite that SNIC will see.

Output context keys:
  - s2_collection: cloud-masked Sentinel-2 SR collection over the phenology window.
    Used downstream for harmonic regression / phenology features.
  - s1_collection: Sentinel-1 GRD collection over the radar window, dB-converted,
    filtered to a single orbit direction.
  - s2_composite: single cloud-free static image over the optical_composite window.
    Used by SNIC for segmentation. Cacheable (the expensive one to recompute).

Note: collections (ImageCollection) are NOT cacheable as single assets — they're
sequences of images, and exporting them all is expensive and rarely useful. Only
the static composite is in `cacheable_outputs`.
"""

from __future__ import annotations

import ee

from fmu.config import Config
from fmu.stages.base import PipelineContext, Stage, StageResult, register_stage
from fmu.utils.gee import safe_call, safe_get_info
from fmu.utils.logging import get_logger

log = get_logger(__name__)


# Reducer functions for the static composite — keyed by config string.
_REDUCERS = {
    "median": lambda: ee.Reducer.median(),
    "p25": lambda: ee.Reducer.percentile([25]),
    "p50": lambda: ee.Reducer.percentile([50]),
    "p75": lambda: ee.Reducer.percentile([75]),
}


@register_stage("data_load")
class DataLoadStage(Stage):
    name = "data_load"
    required_inputs = {"roi"}
    produces = {"s2_collection", "s1_collection", "s2_composite"}
    cacheable_outputs = {"s2_composite"}  # collections aren't cacheable as assets

    @safe_call("loading S2 + S1 data")
    def run(self, ctx: PipelineContext, config: Config) -> StageResult:
        roi = ctx.get("roi")

        s2_collection = self._load_s2(roi, config)
        s1_collection = self._load_s1(roi, config)
        s2_composite = self._build_composite(s2_collection, roi, config)

        return StageResult(
            outputs={
                "s2_collection": s2_collection,
                "s1_collection": s1_collection,
                "s2_composite": s2_composite,
            },
            metadata={
                "s2_dataset": config.datasets.phenology_collection,
                "s1_dataset": config.datasets.radar_collection,
                "s2_phenology_window": (
                    f"{config.dates.phenology.start} → {config.dates.phenology.end}"
                ),
                "s1_radar_window": (
                    f"{config.dates.radar.start} → {config.dates.radar.end}"
                ),
                "s2_composite_window": (
                    f"{config.dates.optical_composite.start} → "
                    f"{config.dates.optical_composite.end}"
                ),
                "s1_orbit": config.data_load.s1_orbit,
                "s1_polarizations": config.data_load.s1_polarizations,
                "s1_instrument_mode": config.data_load.s1_instrument_mode,
                "s2_composite_reducer": config.data_load.s2_composite_reducer,
                "cloud_max_pct": config.cloud_mask.max_cloud_pct,
                "scl_drop_classes": config.cloud_mask.drop_scl_classes,
            },
        )

    def _load_s2(self, roi: ee.Geometry, config: Config) -> ee.ImageCollection:
        """Load Sentinel-2 SR collection, filter by date + cloud %, apply SCL mask."""
        dates = config.dates.phenology
        ds = config.datasets.phenology_collection
        cm = config.cloud_mask

        coll = (
            ee.ImageCollection(ds)
            .filterBounds(roi)
            .filterDate(str(dates.start), str(dates.end))
            .filter(ee.Filter.lte("CLOUDY_PIXEL_PERCENTAGE", cm.max_cloud_pct))
        )

        # Fail loud if no images in window
        size = safe_get_info(coll.size(), context="S2 phenology window image count")
        if size == 0:
            raise RuntimeError(
                f"data_load: no S2 images in phenology window "
                f"{dates.start} → {dates.end} over ROI "
                f"with CLOUDY_PIXEL_PERCENTAGE ≤ {cm.max_cloud_pct}. "
                f"Loosen the cloud filter or widen the window."
            )
        log.info("  S2 phenology window: %d images after cloud filter", size)

        drop_classes = cm.drop_scl_classes
        return coll.map(lambda img: self._mask_s2_scl(img, drop_classes))

    @staticmethod
    def _mask_s2_scl(img: ee.Image, drop_classes: list[int]) -> ee.Image:
        """Apply SCL band masking. drop_classes are SCL values to mask out."""
        scl = img.select("SCL")
        # Start with 'all valid', then knock out each bad class
        mask = scl.neq(drop_classes[0])
        for cls in drop_classes[1:]:
            mask = mask.And(scl.neq(cls))
        return img.updateMask(mask)

    def _load_s1(self, roi: ee.Geometry, config: Config) -> ee.ImageCollection:
        """Load Sentinel-1 GRD, filter to IW/VV+VH/one orbit, convert to dB."""
        dates = config.dates.radar
        ds = config.datasets.radar_collection
        params = config.data_load

        coll = (
            ee.ImageCollection(ds)
            .filterBounds(roi)
            .filterDate(str(dates.start), str(dates.end))
            .filter(ee.Filter.eq("instrumentMode", params.s1_instrument_mode))
            .filter(ee.Filter.eq("orbitProperties_pass", params.s1_orbit))
        )

        # Require all selected polarizations to be present
        for pol in params.s1_polarizations:
            coll = coll.filter(ee.Filter.listContains("transmitterReceiverPolarisation", pol))

        # Select only the polarization bands we want
        coll = coll.select(params.s1_polarizations)

        size = safe_get_info(coll.size(), context="S1 radar window image count")
        if size == 0:
            raise RuntimeError(
                f"data_load: no S1 images in radar window "
                f"{dates.start} → {dates.end} over ROI with "
                f"mode={params.s1_instrument_mode}, orbit={params.s1_orbit}, "
                f"pol={params.s1_polarizations}. Try the other orbit direction "
                f"or widen the window."
            )
        log.info("  S1 radar window: %d images after orbit/pol filter", size)

        # NOTE: COPERNICUS/S1_GRD is *already* in decibels (the GEE pipeline
        # converts linear backscatter to dB during pre-processing). No log10
        # conversion is needed; the values come out as expected dB on read.
        # See https://developers.google.com/earth-engine/guides/sentinel1.
        # If linear-units S1 is needed instead, use COPERNICUS/S1_GRD_FLOAT.
        return coll

    def _build_composite(
        self, s2_collection: ee.ImageCollection, roi: ee.Geometry, config: Config
    ) -> ee.Image:
        """Make the static S2 composite for SNIC.

        Uses a separate date window (`optical_composite`) — typically a recent year,
        not the full phenology window — and re-filters from scratch so the composite
        date range is independent of the phenology collection.
        """
        dates = config.dates.optical_composite
        ds = config.datasets.optical_composite_collection
        cm = config.cloud_mask
        reducer_name = config.data_load.s2_composite_reducer

        coll = (
            ee.ImageCollection(ds)
            .filterBounds(roi)
            .filterDate(str(dates.start), str(dates.end))
            .filter(ee.Filter.lte("CLOUDY_PIXEL_PERCENTAGE", cm.max_cloud_pct))
            .map(lambda img: self._mask_s2_scl(img, cm.drop_scl_classes))
        )

        size = safe_get_info(coll.size(), context="S2 composite window image count")
        if size == 0:
            raise RuntimeError(
                f"data_load: no S2 images in composite window "
                f"{dates.start} → {dates.end}. "
                f"Loosen cloud filter or widen window."
            )
        log.info("  S2 composite window: %d images after cloud filter", size)

        reducer = _REDUCERS[reducer_name]()
        return coll.reduce(reducer).clip(roi)

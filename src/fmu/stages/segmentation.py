"""SNIC superpixel segmentation. Draws boundaries on a curated 5-band input
stack at 10 m native resolution, producing labeled superpixels for clustering.

Input bands (all 10 m native, hand-picked for boundary detection per the
resolution analysis):
  - B4_median, B8_median  → S2 visible red + NIR (spectral basis)
  - composite_nirv        → NIRv from the 2023 S2 composite; NDVI×NIR_reflectance,
                            doesn't saturate in dense canopy like NDVI would
  - canopy_height         → ETH 2020 structure (independent from optical)
  - vv_minus_vh_median    → S1 cross-pol contrast (independent from optical)

These 5 bands are z-scored per-band over the ROI (so no single band's
larger magnitude dominates SNIC's distance metric), then stacked and fed
to ee.Algorithms.Image.Segmentation.SNIC.

Same SNIC inputs across both configs — boundaries are a constant of the
experiment. Only the clustering stage's feature stack varies between
baseline and variant. This keeps Module 18's metrics attributable.

Outputs:
  - snic_clusters: integer cluster ID per pixel
  - snic_means:    per-cluster mean of each input band (5 bands)

Per DEC-001, clustering operates on superpixel means, not pixels.
"""

from __future__ import annotations

import ee

from fmu.config import Config
from fmu.stages.base import PipelineContext, Stage, StageResult, register_stage
from fmu.utils.gee import safe_call, safe_get_info
from fmu.utils.logging import get_logger

log = get_logger(__name__)


# The 5 bands fed to SNIC, in the order they're stacked. Stable identifiers
# referenced by tests, the inspect script, and downstream stages.
_SNIC_INPUT_BAND_NAMES = (
    "B4_median",
    "B8_median",
    "composite_nirv",
    "canopy_height",
    "vv_minus_vh_median",
)


@register_stage("segmentation")
class SegmentationStage(Stage):
    name = "segmentation"
    required_inputs = {"roi", "s2_composite", "structure_features", "radar_features"}
    produces = {"snic_clusters", "snic_means"}
    cacheable_outputs = {"snic_clusters", "snic_means"}

    @safe_call("running SNIC segmentation")
    def run(self, ctx: PipelineContext, config: Config) -> StageResult:
        roi = ctx.get("roi")
        s2_composite: ee.Image = ctx.get("s2_composite")
        structure_features: ee.Image = ctx.get("structure_features")
        radar_features: ee.Image = ctx.get("radar_features")
        params = config.segmentation
        scale = config.export.analysis_scale_m

        # Build the 5-band input stack
        b4 = s2_composite.select("B4_median")
        b8 = s2_composite.select("B8_median")

        # Composite NIRv: (NIR / 10000) × NDVI. S2 SR is scaled by 10000, so
        # divide back to actual reflectance before multiplying. Same convention
        # as features_optical's nirv computation.
        ndvi_from_composite = b8.subtract(b4).divide(b8.add(b4))
        nir_reflectance = b8.divide(10000)
        composite_nirv = nir_reflectance.multiply(ndvi_from_composite).rename("composite_nirv")

        canopy_height = structure_features.select("canopy_height")
        vv_minus_vh = radar_features.select("vv_minus_vh_median")

        raw_stack = ee.Image.cat(
            [b4, b8, composite_nirv, canopy_height, vv_minus_vh]
        )  # band names: B4_median, B8_median, composite_nirv, canopy_height, vv_minus_vh_median

        # Z-score per band over the ROI to put all bands on a comparable scale.
        # Without this, B4_median (0-3000) would dominate vs canopy_height (0-30).
        if params.normalize_inputs:
            snic_input = _zscore_per_band(raw_stack, roi, scale)
        else:
            snic_input = raw_stack

        # Run SNIC
        snic_result = ee.Algorithms.Image.Segmentation.SNIC(
            image=snic_input,
            size=params.size,
            compactness=params.compactness,
            connectivity=params.connectivity,
            neighborhoodSize=params.neighborhood_size,
        )
        # SNIC output bands:
        #   - "clusters": integer cluster ID per pixel
        #   - "seeds":    the seed locations (1 where a cluster centroid sits)
        #   - "<input>_mean": one band per input, holding the per-cluster mean
        # We keep the clusters band and the means; drop seeds.

        snic_clusters = snic_result.select("clusters").rename("snic_clusters").clip(roi)

        means_band_names = [f"{b}_mean" for b in _SNIC_INPUT_BAND_NAMES]
        snic_means = (
            snic_result.select(means_band_names)
            .rename(list(_SNIC_INPUT_BAND_NAMES))  # drop the _mean suffix
            .clip(roi)
        )

        # Diagnostic
        means_bands = safe_get_info(snic_means.bandNames(), context="snic_means bands")
        log.info("  snic_means bands (%d): %s", len(means_bands), means_bands)
        log.info(
            "  SNIC params: size=%d compactness=%s connectivity=%d neighborhood=%d normalize=%s",
            params.size,
            params.compactness,
            params.connectivity,
            params.neighborhood_size,
            params.normalize_inputs,
        )

        return StageResult(
            outputs={
                "snic_clusters": snic_clusters,
                "snic_means": snic_means,
            },
            metadata={
                "snic_input_bands": list(_SNIC_INPUT_BAND_NAMES),
                "normalize_inputs": params.normalize_inputs,
                "size": params.size,
                "compactness": params.compactness,
                "connectivity": params.connectivity,
                "neighborhood_size": params.neighborhood_size,
            },
        )


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------


def _zscore_per_band(image: ee.Image, roi: ee.Geometry, scale: int) -> ee.Image:
    """Z-score normalize each band of `image` independently over `roi`.

    Computes mean and stddev per band over the ROI, then subtracts the mean
    and divides by stddev (clamped at 1e-6 to avoid division-by-zero on
    constant bands).
    """
    stats = image.reduceRegion(
        reducer=ee.Reducer.mean().combine(ee.Reducer.stdDev(), sharedInputs=True),
        geometry=roi,
        scale=scale,
        maxPixels=1e9,
        bestEffort=True,
    )
    # Build the z-scored image band-by-band on the Python side; the band list
    # is small and fixed, so this is cleaner than server-side iteration.
    band_names = safe_get_info(image.bandNames(), context="z-score band names")
    normalized_bands: list[ee.Image] = []
    for b in band_names:
        mean = ee.Number(stats.get(f"{b}_mean"))
        std = ee.Number(stats.get(f"{b}_stdDev"))
        safe_std = std.max(1e-6)
        normalized = image.select(b).subtract(mean).divide(safe_std).rename(b)
        normalized_bands.append(normalized)
    return ee.Image.cat(normalized_bands)

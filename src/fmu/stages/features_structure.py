"""Structure features stage. Per-pixel structural metrics from canopy height.

Uses ETH Global Canopy Height 2020 (10 m, derived from GEDI + Sentinel-2
fusion — per DEC-009 we prefer this over GEDI L2A which is too sparse).

When `include_neighborhood_stats` is enabled, the stage also emits
standard deviation and max within a small window around each pixel.
This captures local structural heterogeneity that a single canopy
height value can't — a mature stand has tall, similar-height pixels
nearby (low std-dev); a regenerating patch has variable heights (high
std-dev); a forest edge has both tall and zero-height pixels (high std,
high max relative to height).

Output is a single multi-band image, cacheable.
"""

from __future__ import annotations

import ee

from fmu.config import Config
from fmu.stages.base import PipelineContext, Stage, StageResult, register_stage
from fmu.utils.gee import safe_call, safe_get_info
from fmu.utils.logging import get_logger

log = get_logger(__name__)


@register_stage("features_structure")
class FeaturesStructureStage(Stage):
    name = "features_structure"
    required_inputs = {"roi"}
    produces = {"structure_features"}
    cacheable_outputs = {"structure_features"}

    @safe_call("computing structure features")
    def run(self, ctx: PipelineContext, config: Config) -> StageResult:
        roi = ctx.get("roi")
        params = config.features_structure
        canopy_asset = config.datasets.canopy_height

        # Load ETH Global Canopy Height; single band, float meters
        canopy = ee.Image(canopy_asset).select(0).rename("canopy_height")

        output_bands: list[ee.Image] = [canopy]

        if params.include_neighborhood_stats:
            # ee.Kernel.square(radius=N) gives a (2N+1)×(2N+1) window
            radius = (params.neighborhood_kernel_size - 1) // 2
            kernel = ee.Kernel.square(radius=radius, units="pixels")

            height_std = canopy.reduceNeighborhood(
                reducer=ee.Reducer.stdDev(), kernel=kernel
            ).rename("canopy_height_std")

            height_max = canopy.reduceNeighborhood(
                reducer=ee.Reducer.max(), kernel=kernel
            ).rename("canopy_height_max")

            output_bands.extend([height_std, height_max])

        structure_features = ee.Image.cat(output_bands).clip(roi)

        band_names = safe_get_info(
            structure_features.bandNames(), context="structure_features band names"
        )
        log.info("  structure_features bands (%d): %s", len(band_names), band_names)

        return StageResult(
            outputs={"structure_features": structure_features},
            metadata={
                "canopy_height_dataset": canopy_asset,
                "include_neighborhood_stats": params.include_neighborhood_stats,
                "neighborhood_kernel_size": params.neighborhood_kernel_size,
                "output_bands": band_names,
            },
        )

"""Structure features stage. Per-pixel structural metrics from canopy height.

Uses ETH Global Canopy Height 2020 (10 m, derived from GEDI + Sentinel-2
fusion; per DEC-009 we prefer this over GEDI L2A which is too sparse).

When `include_neighborhood_stats` is enabled, the stage also emits
standard deviation and max within a small window around each pixel.
This captures local structural heterogeneity that a single canopy
height value can't; a mature stand has tall, similar-height pixels
nearby (low std-dev); a regenerating patch has variable heights (high
std-dev); a forest edge has both tall and zero-height pixels (high std,
high max relative to height).

Output is a single multi-band image, cacheable.
"""

from __future__ import annotations

import ee

from fmu.config import Config
from fmu.stages.base import (
    DisplayLayer,
    PipelineContext,
    Stage,
    StageResult,
    register_stage,
)
from fmu.utils.gee import safe_call, safe_get_info
from fmu.utils.logging import get_logger

log = get_logger(__name__)


@register_stage("features_structure")
class FeaturesStructureStage(Stage):
    name = "features_structure"
    required_inputs = {"roi"}
    produces = {"structure_features"}
    cacheable_outputs = {"structure_features"}

    # Transparency: the canopy height itself and its local spread. The spread
    # exists only under `include_neighborhood_stats` (the default); tests/
    # test_transparency_contract.py fails for a config under configs/ that
    # turns it off. `canopy_height_max` is not offered: it says little the
    # height does not.
    #
    # Height 0 to 30 m: the range the segmentation stage and SegmentationParams
    # give for this band; the stand means of the 14 runs of 13 Oct 2026 lie
    # between 1 and 25 m (the colour scales of the early ui_data build of that
    # day, scripts/build_ui_early_data.py). Spread 0 to 3 m: a starting value
    # with nothing measured behind it, set beside the 0.45 m tolerance that the
    # configs which merge on this band give it. Both are starting stretches
    # for a reader. The greens are the palette that build drew canopy height
    # in.
    display_layers = (
        DisplayLayer(
            key="structure_features",
            band="canopy_height",
            title="Canopy height (ETH 2020), m",
            description=(
                "Height of the top of the canopy in metres, from the ETH "
                "Global Canopy Height map for 2020 at 10 m. It is a single "
                "snapshot, the same in every run. It is one of the bands the "
                "superpixels are drawn on by default and one of the two the "
                "merge compares by default; a config can name other merge "
                "criteria."
            ),
            legend_note=(
                "This is a modelled map, not a field measurement. "
                "docs/datasets.md, section 'ETH Global Canopy Height 2020', "
                "records a field validation of this product; read "
                "differences of a few metres with that in mind."
            ),
            vis={
                "min": 0,
                "max": 30,
                "palette": ["f7fcf5", "c7e9c0", "74c476", "238b45", "00441b"],
            },
        ),
        DisplayLayer(
            key="structure_features",
            band="canopy_height_std",
            title="Local spread of canopy height, m",
            description=(
                "The standard deviation of ETH 2020 canopy height in a small "
                "window around each pixel (3 by 3 pixels by default), in "
                "metres. Low where neighbouring pixels have the same height, "
                "high at edges and gaps. It is shown because some "
                "configurations segment on it and some use it as a merge "
                "criterion; it is in neither the default segmentation bands "
                "nor the default merge criteria."
            ),
            vis={
                "min": 0,
                "max": 3,
                "palette": ["fcfbfd", "dadaeb", "9e9ac8", "6a51a3", "3f007d"],
            },
        ),
    )

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

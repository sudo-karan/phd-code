"""Radar features stage. Statistical reducers over the S1 collection.

Per-pixel features summarize 5 years of Sentinel-1 VV and VH backscatter
into stable statistics. No harmonic regression; SAR backscatter doesn't
have a clean seasonal cycle the way optical phenology does (returns
depend on geometry, moisture, biomass; not photosynthesis).

Per DEC-016: cross-pol contrast is VV_median - VH_median in dB. This is
equivalent to 10*log10(VV_linear / VH_linear) under the dB transform.
The notebook approach of dividing the dB values directly (vv.divide(vh))
isn't mathematically well-defined because dB is a log-scale quantity.

No speckle filtering. Temporal median over 100+ S1 images is already a
stronger despeckler than any spatial filter (variance reduction scales
with the number of independent samples). Spatial filters would also blur
edges, hurting SNIC segmentation downstream.

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


@register_stage("features_radar")
class FeaturesRadarStage(Stage):
    name = "features_radar"
    required_inputs = {"s1_collection", "roi"}
    produces = {"radar_features"}
    cacheable_outputs = {"radar_features"}

    # Transparency: the cross-polarisation contrast, the one radar band
    # segmentation reads by default, not all nine. It exists only under
    # `include_cross_pol_contrast` (the default); tests/
    # test_transparency_contract.py fails for a config under configs/ that
    # turns it off.
    #
    # Stretch 3 to 12 dB: a starting value around the stand means of the 14
    # runs of 13 Oct 2026, which lie between 4.3 and 10.1 dB (the colour scales
    # of the early ui_data build of that day, scripts/build_ui_early_data.py).
    # The palette is the one that build drew this band in.
    display_layers = (
        DisplayLayer(
            key="radar_features",
            band="vv_minus_vh_median",
            title="Radar contrast between polarisations (VV minus VH), dB",
            description=(
                "The median Sentinel-1 backscatter in VV minus the median in "
                "VH, in decibels, over the radar window. A difference in "
                "decibels is the ratio of the two signals. It comes from "
                "radar alone, so it does not depend on cloud or on the "
                "optical bands, and it is one of the bands the superpixels "
                "are drawn on by default. Read it as a second, independent "
                "view of surface structure, not as a measure of any one "
                "forest property."
            ),
            vis={
                "min": 3,
                "max": 12,
                "palette": ["f7fbff", "c6dbef", "6baed6", "2171b5", "08306b"],
            },
        ),
    )

    @safe_call("computing radar features")
    def run(self, ctx: PipelineContext, config: Config) -> StageResult:
        s1: ee.ImageCollection = ctx.get("s1_collection")
        roi = ctx.get("roi")
        params = config.features_radar

        # Figure out which percentiles to compute internally.
        # The user's requested percentiles plus any needed for derived
        # features (IQR needs 25/75; cross-pol contrast needs 50).
        requested = sorted(set(params.percentiles))
        needed = set(requested)
        if params.include_iqr:
            needed.update([10, 90])  # temporal spread = p90 - p10 (deck v3.0)
        if params.include_cross_pol_contrast:
            needed.add(50)
        all_pcts = sorted(needed)

        # One pass over the collection computes all percentiles.
        # Output band names follow GEE convention: VV_p10, VV_p50, ..., VH_p10, ...
        reducer = ee.Reducer.percentile(all_pcts)
        reduced = s1.select(["VV", "VH"]).reduce(reducer)

        output_bands: list[ee.Image] = []

        # Requested percentiles to output bands (renamed to lowercase prefix)
        for p in requested:
            output_bands.append(reduced.select(f"VV_p{p}").rename(f"vv_p{p}"))
            output_bands.append(reduced.select(f"VH_p{p}").rename(f"vh_p{p}"))

        # Temporal spread = p90 - p10 (deck v3.0, Stage 4). Kept under the
        # vv_iqr / vh_iqr band names the rest of the pipeline expects.
        if params.include_iqr:
            vv_iqr = (
                reduced.select("VV_p90")
                .subtract(reduced.select("VV_p10"))
                .rename("vv_iqr")
            )
            vh_iqr = (
                reduced.select("VH_p90")
                .subtract(reduced.select("VH_p10"))
                .rename("vh_iqr")
            )
            output_bands.extend([vv_iqr, vh_iqr])

        # Cross-pol contrast: VV_median - VH_median in dB
        if params.include_cross_pol_contrast:
            vv_minus_vh = (
                reduced.select("VV_p50")
                .subtract(reduced.select("VH_p50"))
                .rename("vv_minus_vh_median")
            )
            output_bands.append(vv_minus_vh)

        radar_features = ee.Image.cat(output_bands).clip(roi)

        # Diagnostic
        band_names = safe_get_info(
            radar_features.bandNames(), context="radar_features band names"
        )
        log.info("  radar_features bands (%d): %s", len(band_names), band_names)

        return StageResult(
            outputs={"radar_features": radar_features},
            metadata={
                "percentiles": params.percentiles,
                "include_iqr": params.include_iqr,
                "include_cross_pol_contrast": params.include_cross_pol_contrast,
                "output_bands": band_names,
            },
        )

"""Static features stage. Terrain, distance-to-water, climate climatology.

These are quantities that don't change meaningfully over the pipeline's
time window: a 30-year rainfall mean is roughly constant for
clustering purposes, as are elevation/slope/aspect.

Bands (with default config):
- elevation: meters above sea level (NASADEM)
- slope: degrees (derived from elevation)
- aspect: degrees 0-360, cyclic (derived from elevation)
- distance_to_water: meters to nearest water pixel from masking's water_mask
- annual_rainfall: mm/year, 30-year mean from CHIRPS climatology

Per DEC-014, computed over the full ROI; the habitat mask applies at
clustering. Output cacheable as single multi-band asset.

A note on aspect: it's emitted as raw degrees (0-360), which is cyclic.
This creates artifacts for distance-based clustering (north-facing at 0
and 359 look maximally different despite being identical). A sin/cos
decomposition would fix this; left as a future improvement so this stage
matches the notebook approach.
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


@register_stage("features_static")
class FeaturesStaticStage(Stage):
    name = "features_static"
    required_inputs = {"roi", "water_mask"}
    produces = {"static_features"}
    cacheable_outputs = {"static_features"}

    # Transparency: elevation only. Slope, aspect, distance to water and
    # rainfall go into the clustering features but are in no segmentation
    # stack, so they are left out of the display rather than offered as four
    # more toggles.
    #
    # Stretch 0 to 1500 m: the repo states no range for this band. It is wide
    # enough for a lowland and a plateau site on one scale, and so far too wide
    # for one small ROI, where a reader should stretch to the ROI's own range.
    display_layers = (
        DisplayLayer(
            key="static_features",
            band="elevation",
            title="Elevation (NASADEM), m",
            description=(
                "Height of the ground above sea level in metres, from NASADEM "
                "at 30 m. It does not change between runs. It is one of the "
                "features the stands are typed on in the hand-crafted arm, "
                "and by default it is not used to draw the superpixels. The "
                "colour scale is wide enough for lowland and plateau sites at "
                "once, so a small area can look almost flat on it; that is "
                "the scale, not the ground."
            ),
            vis={
                "min": 0,
                "max": 1500,
                "palette": ["440154", "3b528b", "21918c", "5ec962", "fde725"],
            },
        ),
    )

    @safe_call("computing static features")
    def run(self, ctx: PipelineContext, config: Config) -> StageResult:
        roi = ctx.get("roi")
        water_mask: ee.Image = ctx.get("water_mask")
        params = config.features_static

        # Terrain: elevation, slope, aspect from NASADEM
        dem = ee.Image(config.datasets.dem).select("elevation")
        terrain = ee.Terrain.products(dem)
        elevation = terrain.select("elevation").rename("elevation")
        slope = terrain.select("slope").rename("slope")
        aspect = terrain.select("aspect").rename("aspect")

        # Distance to water: fast distance transform on the water_mask.
        # fastDistanceTransform returns squared euclidean distance in pixels;
        # take sqrt and multiply by analysis scale (10 m) to get meters.
        max_dist_pix = params.max_water_distance_pixels
        distance_to_water = (
            water_mask.fastDistanceTransform(max_dist_pix, "pixels", "squared_euclidean")
            .sqrt()
            .multiply(config.export.analysis_scale_m)
            .rename("distance_to_water")
        )

        output_bands: list[ee.Image] = [elevation, slope, aspect, distance_to_water]

        # Climate: mean annual rainfall from CHIRPS pentad climatology.
        # CHIRPS pentads are 5-day rainfall totals (mm). Sum over the
        # climatology window then divide by number of years.
        if params.include_climate:
            climate_dates = config.dates.climate
            chirps = (
                ee.ImageCollection(config.datasets.climate)
                .filterDate(str(climate_dates.start), str(climate_dates.end))
            )
            n_years = climate_dates.end.year - climate_dates.start.year + 1
            annual_rainfall = (
                chirps.sum().divide(n_years).rename("annual_rainfall")
            )
            output_bands.append(annual_rainfall)

        static_features = ee.Image.cat(output_bands).clip(roi)

        band_names = safe_get_info(
            static_features.bandNames(), context="static_features band names"
        )
        log.info("  static_features bands (%d): %s", len(band_names), band_names)

        return StageResult(
            outputs={"static_features": static_features},
            metadata={
                "dem_dataset": config.datasets.dem,
                "climate_dataset": config.datasets.climate if params.include_climate else None,
                "climate_window": (
                    f"{config.dates.climate.start} to {config.dates.climate.end}"
                    if params.include_climate
                    else None
                ),
                "include_climate": params.include_climate,
                "max_water_distance_pixels": params.max_water_distance_pixels,
                "output_bands": band_names,
            },
        )

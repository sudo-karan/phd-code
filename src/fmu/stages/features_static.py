"""Static features stage. Terrain, distance-to-water, climate climatology.

These are quantities that don't change meaningfully over the pipeline's
time window: a 30-year rainfall mean is roughly constant for
clustering purposes, as are elevation/slope/aspect.

Bands (with default config):
- elevation: meters above sea level (NASADEM)
- slope: degrees, fractional (ee.Terrain.slope on the DEM as float; whole
  degrees from ee.Terrain.products until round 13, review A5)
- aspect: degrees 0-360, cyclic, fractional (ee.Terrain.aspect, likewise)
- distance_to_water: meters to nearest JRC water pixel, looked for within
  features_static.max_water_distance_pixels (10 km by default). Off the axes
  the search reaches a little past 10 km (real distances up to 12.3 km in the
  Odisha box runs); where it finds no water, the transform returns a fill
  value (463,409.5 m at 10 m). With features_static.cap_distance_to_water on,
  every distance past the cap, the fill value and those real ones, reads as
  the cap. The water is masking's definition (masking.jrc_water_mask), built
  here over the ROI buffered by the transform's reach (`water_reach_m`), not
  read from masking's water_mask, which ends at the ROI: before round 13 the
  transform saw no water outside the ROI (review A1).
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

import math
from typing import Any

import ee

from fmu.config import Config
from fmu.stages.base import (
    DisplayLayer,
    PipelineContext,
    Stage,
    StageResult,
    register_stage,
)
from fmu.stages.masking import jrc_water_mask
from fmu.utils.gee import safe_call, safe_get_info
from fmu.utils.logging import get_logger

log = get_logger(__name__)


def water_reach_m(max_water_distance_pixels: int, analysis_scale_m: int) -> int:
    """How far past the ROI the water input of distance_to_water is built, in metres.

    fastDistanceTransform looks for water in a square of half-width
    max_water_distance_pixels around each pixel, whose corners are sqrt(2) times
    as far: ceil(sqrt(2) x max_water_distance_pixels) whole pixels (14,150 m at
    the default 1,000 pixels of 10 m). Every water pixel that neighbourhood holds,
    for every pixel of the ROI, is then in the input, so every distance the
    transform finds is the one it would find with no clip (review A1).
    """
    return math.ceil(math.sqrt(2) * max_water_distance_pixels) * analysis_scale_m


@register_stage("features_static")
class FeaturesStaticStage(Stage):
    name = "features_static"
    required_inputs = {"roi"}
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

    def input_collections(self, ctx: PipelineContext, config: Config) -> dict[str, Any]:
        """The CHIRPS pentads the rainfall climatology sums, when it is computed (the
        DEM and the JRC water map are one image each, named in the config)."""
        if not config.features_static.include_climate:
            return {}
        return {"chirps": _climate_window(config)}

    @safe_call("computing static features")
    def run(self, ctx: PipelineContext, config: Config) -> StageResult:
        roi = ctx.get("roi")
        params = config.features_static

        # Terrain: elevation, slope and aspect from NASADEM. Slope and aspect come
        # from ee.Terrain.slope and ee.Terrain.aspect on the DEM cast to float, in
        # fractional degrees. Until round 13 they came from ee.Terrain.products,
        # which gives them as whole degrees (integer bands) on an integer and on a
        # float DEM alike (read on Earth Engine in round 13; review A5). Elevation
        # keeps the DEM's values, as a float band.
        dem = ee.Image(config.datasets.dem).select("elevation").toFloat()
        elevation = dem.rename("elevation")
        slope = ee.Terrain.slope(dem).rename("slope")
        aspect = ee.Terrain.aspect(dem).rename("aspect")

        # Distance to water: fast distance transform on JRC water, built over the
        # ROI buffered by the transform's reach so that water outside the ROI is
        # seen (review A1); the stack is clipped to the ROI below. maxError 1 m:
        # by default buffer() may fall short by 1% of the distance (141.5 m),
        # more than the ceil in water_reach_m leaves (7.9 m at 1,000 pixels).
        # fastDistanceTransform returns squared euclidean distance in pixels;
        # take sqrt and multiply by analysis scale (10 m) to get meters.
        max_dist_pix = params.max_water_distance_pixels
        reach_m = water_reach_m(max_dist_pix, config.export.analysis_scale_m)
        water = jrc_water_mask(
            ee.Image(config.datasets.water),
            config.masking.jrc_water_occurrence_threshold,
            roi.buffer(reach_m, maxError=1),
        )
        distance_to_water = (
            water.fastDistanceTransform(max_dist_pix, "pixels", "squared_euclidean")
            .sqrt()
            .multiply(config.export.analysis_scale_m)
        )
        if params.cap_distance_to_water:
            # Where the neighbourhood holds no water the transform returns its
            # fill value, sqrt(2^31 - 1) pixels, not a distance, and off the
            # axes it reaches a little past max_dist_pix: cap at max_dist_pix
            # (spec-static-cap-distance-to-water).
            distance_to_water = distance_to_water.min(
                max_dist_pix * config.export.analysis_scale_m
            )
        distance_to_water = distance_to_water.rename("distance_to_water")

        output_bands: list[ee.Image] = [elevation, slope, aspect, distance_to_water]

        # Climate: mean annual rainfall from CHIRPS pentad climatology.
        # CHIRPS pentads are 5-day rainfall totals (mm). Sum over the
        # climatology window then divide by number of years.
        if params.include_climate:
            climate_dates = config.dates.climate
            chirps = _climate_window(config)
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
                # Whether distance_to_water is capped there (on) or holds what
                # the transform returns, its fill value included (off, every
                # earlier run).
                "cap_distance_to_water": params.cap_distance_to_water,
                "output_bands": band_names,
            },
        )


def _climate_window(config: Config) -> ee.ImageCollection:
    """The CHIRPS pentads of the climatology window. One definition, read by `run()`
    and by `input_collections`."""
    climate_dates = config.dates.climate
    return ee.ImageCollection(config.datasets.climate).filterDate(
        str(climate_dates.start), str(climate_dates.end)
    )

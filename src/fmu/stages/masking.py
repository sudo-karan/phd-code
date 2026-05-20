"""Masking stage. Builds habitat_mask, water_mask, landcover_summary from
WorldCover, JRC GSW, Google Open Buildings, and VIIRS nightlights.

Output context keys:
  - habitat_mask: binary, 1 where pixel is forest-relevant (veg AND NOT water
    AND NOT built AND NOT bright_urban)
  - water_mask: binary, 1 where pixel is permanent water
  - landcover_summary: labeled image for visualization
      10/20/30 = WorldCover veg classes kept
      50 = built-up (from Open Buildings or VIIRS)
      80 = water
      0  = other (excluded but not in any specific category)

Note on data sources:
  WorldCover is S2-derived. The built-up signal comes from Open Buildings
  (vector, independent of S2) and VIIRS (different sensor) to avoid
  circularity with the S2 features used in downstream stages.
  See docs/design_notes.md.
"""

from __future__ import annotations

import ee

from fmu.config import Config
from fmu.stages.base import PipelineContext, Stage, StageResult, register_stage
from fmu.utils.gee import safe_call
from fmu.utils.logging import get_logger

log = get_logger(__name__)


@register_stage("masking")
class MaskingStage(Stage):
    name = "masking"
    required_inputs = {"roi"}
    produces = {"habitat_mask", "water_mask", "landcover_summary"}

    @safe_call("building masking layers")
    def run(self, ctx: PipelineContext, config: Config) -> StageResult:
        roi = ctx.get("roi")
        ds = config.datasets
        params = config.masking

        # ----- WorldCover: vegetation + a backup water signal -----
        wc = ee.ImageCollection(ds.worldcover).first().select("Map").clip(roi)
        keep = params.keep_worldcover_classes
        veg = wc.eq(keep[0])
        for cls in keep[1:]:
            veg = veg.Or(wc.eq(cls))
        wc_water = wc.eq(80)  # WorldCover permanent water class

        # ----- JRC GSW: occurrence-based water -----
        gsw = ee.Image(ds.water).select("occurrence").clip(roi)
        gsw_water = gsw.gte(params.jrc_water_occurrence_threshold).unmask(0)

        # Combined water: either source counts
        water_mask = gsw_water.Or(wc_water).rename("water_mask")

        # ----- Open Buildings: vector polygons to rasterized built mask -----
        # Filter to ROI and confidence threshold, then rasterize at the pipeline
        # analysis scale. Anything inside a building polygon becomes 1.
        buildings = (
            ee.FeatureCollection(ds.open_buildings)
            .filterBounds(roi)
            .filter(ee.Filter.gte("confidence", params.open_buildings_confidence))
        )
        built_from_buildings = (
            buildings.reduceToImage(properties=["confidence"], reducer=ee.Reducer.first())
            .gt(0)
            .unmask(0)
        )

        # ----- VIIRS: broad urban / bright-light areas -----
        # Use the latest available VIIRS monthly composite.
        viirs = (
            ee.ImageCollection(ds.nightlights)
            .select("avg_rad")
            .sort("system:time_start", False)
            .first()
            .clip(roi)
        )
        bright_urban = viirs.gte(params.nightlights_threshold).unmask(0)

        # ----- Combined built mask (either source) -----
        built_mask = built_from_buildings.Or(bright_urban)

        # ----- habitat_mask: veg AND NOT water AND NOT built -----
        habitat_mask = (
            veg.And(water_mask.Not()).And(built_mask.Not()).rename("habitat_mask")
        )

        # ----- landcover_summary: labeled output for visualization -----
        # Layered: WorldCover veg classes, then built (50), then water (80).
        # Later layers win where they overlap, so water/built take precedence
        # over a noisy WorldCover veg label at the same pixel.
        summary = ee.Image(0).int()
        for cls in keep:
            summary = summary.where(wc.eq(cls), cls)
        summary = summary.where(built_mask, 50)
        summary = summary.where(water_mask, 80).rename("landcover_summary")

        return StageResult(
            outputs={
                "habitat_mask": habitat_mask,
                "water_mask": water_mask,
                "landcover_summary": summary,
            },
            metadata={
                "worldcover_classes_kept": keep,
                "water_occurrence_threshold": params.jrc_water_occurrence_threshold,
                "open_buildings_confidence": params.open_buildings_confidence,
                "nightlights_threshold": params.nightlights_threshold,
                "worldcover_dataset": ds.worldcover,
                "water_dataset": ds.water,
                "open_buildings_dataset": ds.open_buildings,
                "nightlights_dataset": ds.nightlights,
            },
        )

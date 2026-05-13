"""Masking stage. Builds habitat_mask, water_mask, landcover_summary from
WorldCover + JRC GSW. See DEC-006 in decisions.md, docs/design_notes.md.

Output context keys:
  - habitat_mask:        binary, 1 where pixel is forest-relevant (tree/shrub/grass) and NOT water
  - water_mask:          binary, 1 where pixel is permanent water
  - landcover_summary:   labeled, for visualization (10/20/30 = veg, 80 = water, 0 = other)
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

        # WorldCover: single image collection, take the Map band
        wc = ee.ImageCollection(ds.worldcover).first().select("Map").clip(roi)

        # Vegetation mask: WorldCover class in keep_worldcover_classes.
        # Schema guarantees keep is non-empty (Field min_length=1).
        keep = params.keep_worldcover_classes
        veg = wc.eq(keep[0])
        for cls in keep[1:]:
            veg = veg.Or(wc.eq(cls))

        # Water mask from JRC GSW occurrence band. unmask(0) so areas
        # that JRC never observed don't become "no data" — treat them
        # as not-water, which is what we want.
        gsw = ee.Image(ds.water).select("occurrence").clip(roi)
        water_mask = gsw.gte(params.jrc_water_occurrence_threshold).unmask(0).rename("water_mask")

        # habitat_mask = vegetation AND NOT water
        habitat_mask = veg.And(water_mask.Not()).rename("habitat_mask")

        # landcover_summary: labeled output for visualization.
        # Start with 0 (other), overlay WorldCover veg classes, then water.
        # Water comes last so it wins over any pixel WorldCover called veg
        # but JRC flagged as water (riparian / banks).
        summary = ee.Image(0).int()
        for cls in keep:
            summary = summary.where(wc.eq(cls), cls)
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
                "worldcover_dataset": ds.worldcover,
                "water_dataset": ds.water,
            },
        )

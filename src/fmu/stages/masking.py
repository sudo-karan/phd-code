"""Masking stage. Builds habitat_mask, water_mask, landcover_summary.

Habitat is defined from the IndiaSAT LULC product (Bansal et al. 2021): the
per-pixel classes 6 = Trees and 12 = Shrubs/Scrubs are kept as habitat, every
other class excluded. Where IndiaSAT has no data, ESA WorldCover v200 (classes
10/20/30) is used as a fallback.

This is a SINGLE-PHASE habitat mask (deck v3.0, Stage 1): water, cropland, and
built-up are removed simply because their classes are not in the habitat set —
there is no separate water or built-up subtraction. JRC Global Surface Water is
loaded only to build `water_mask` for the downstream distance-to-water feature,
not for habitat masking.

IndiaSAT is an annual collection (2017-2022). We take the per-pixel MODAL class
over the collection, so a one-off yearly misclassification does not flip a
pixel's habitat status.

Output context keys:
  - habitat_mask: binary, 1 where the pixel is IndiaSAT Trees/Shrubs
    (WorldCover 10/20/30 where IndiaSAT is unavailable)
  - water_mask: binary, 1 where JRC permanent water; feeds distance-to-water
  - landcover_summary: labeled image for visualization
      6 / 12 = IndiaSAT habitat classes kept
      80     = JRC permanent water
      0      = other (excluded)
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

        # ----- IndiaSAT LULC: primary habitat source -----
        # Annual 30 m LULC raster; reduce to the per-pixel modal class over the
        # collection so a single bad year cannot flip a pixel's habitat status.
        indiasat_ic = ee.ImageCollection(ds.indiasat).filterBounds(roi)
        if params.indiasat_class_band is not None:
            indiasat_ic = indiasat_ic.select([params.indiasat_class_band])
        else:
            # First band is the class label; the collection also carries a
            # per-pixel confidence band we don't use here.
            indiasat_ic = indiasat_ic.map(lambda img: img.select(0))
        lulc = indiasat_ic.reduce(ee.Reducer.mode()).rename("indiasat_lulc").clip(roi)

        habitat_classes = params.indiasat_habitat_classes
        veg_indiasat = lulc.eq(habitat_classes[0])
        for cls in habitat_classes[1:]:
            veg_indiasat = veg_indiasat.Or(lulc.eq(cls))

        # ----- WorldCover fallback (only where IndiaSAT has no data) -----
        wc = ee.ImageCollection(ds.worldcover).first().select("Map").clip(roi)
        keep = params.keep_worldcover_classes
        veg_wc = wc.eq(keep[0])
        for cls in keep[1:]:
            veg_wc = veg_wc.Or(wc.eq(cls))

        # IndiaSAT where present; WorldCover where IndiaSAT is masked (no data).
        # IndiaSAT covers all of India, so the fallback is a safety net for
        # coverage gaps or AOIs outside its footprint.
        veg = veg_indiasat.unmask(veg_wc)

        # ----- habitat_mask: single-phase, habitat classes only -----
        # Water / built-up / cropland are excluded implicitly (they are not in
        # the habitat class set); no separate water or built subtraction.
        habitat_mask = veg.rename("habitat_mask")

        # ----- JRC water: distance-to-water feature only, NOT masking -----
        gsw = ee.Image(ds.water).select("occurrence").clip(roi)
        water_mask = (
            gsw.gte(params.jrc_water_occurrence_threshold)
            .unmask(0)
            .rename("water_mask")
        )

        # ----- landcover_summary: labeled output for visualization -----
        # IndiaSAT habitat classes, then water on top (water wins where they
        # overlap, since JRC and IndiaSAT are independent sources).
        summary = ee.Image(0).int()
        for cls in habitat_classes:
            summary = summary.where(lulc.eq(cls), cls)
        summary = summary.where(water_mask, 80).rename("landcover_summary")

        return StageResult(
            outputs={
                "habitat_mask": habitat_mask,
                "water_mask": water_mask,
                "landcover_summary": summary,
            },
            metadata={
                "indiasat_dataset": ds.indiasat,
                "indiasat_habitat_classes": habitat_classes,
                "indiasat_class_band": params.indiasat_class_band,
                "worldcover_fallback_classes": keep,
                "worldcover_dataset": ds.worldcover,
                "water_occurrence_threshold": params.jrc_water_occurrence_threshold,
                "water_dataset": ds.water,
            },
        )

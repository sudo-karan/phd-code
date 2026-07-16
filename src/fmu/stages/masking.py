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

IndiaSAT is an annual collection (2017-2022). Habitat is decided per pixel by a
MAJORITY VOTE over the usable (non-cloud / non-masked) years: a pixel is habitat
if more of its usable years were Trees/Shrubs than not. A tie (equal habitat and
non-habitat years) is broken by the MOST RECENT usable year, cascading to the
next-latest where the newest year is cloud/no-data. Voting on the binary
habitat question (rather than the multi-class mode) keeps the tie rule explicit
and ecologically meaningful instead of falling to an arbitrary class-code order.

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
        # Annual 30 m LULC (2017-2022). Decide habitat by majority vote over
        # the usable years, tie-broken by the most recent usable year.
        indiasat_ic = ee.ImageCollection(ds.indiasat).filterBounds(roi)
        if params.indiasat_class_band is not None:
            indiasat_ic = indiasat_ic.select([params.indiasat_class_band])
        else:
            # First band is the class label; the collection also carries a
            # per-pixel confidence band we don't use here.
            indiasat_ic = indiasat_ic.map(lambda img: img.select(0))

        habitat_classes = params.indiasat_habitat_classes

        def _is_habitat(class_img: ee.Image) -> ee.Image:
            hab = class_img.eq(habitat_classes[0])
            for cls in habitat_classes[1:]:
                hab = hab.Or(class_img.eq(cls))
            return hab

        # Per-year class image (single band, timestamp kept for the recency
        # tie-break) and the matching 0/1 habitat indicator.
        lulc_ic = indiasat_ic.map(
            lambda img: img.rename("lulc").copyProperties(img, ["system:time_start"])
        )
        hab_per_year = lulc_ic.map(
            lambda img: _is_habitat(img)
            .rename("habitat")
            .copyProperties(img, ["system:time_start"])
        )

        # Majority vote across usable (unmasked) years: more habitat years than
        # not. hab_votes = habitat-year count; n_usable = usable-year count.
        hab_votes = hab_per_year.sum().unmask(0).rename("h")
        n_usable = hab_per_year.count().rename("h")
        has_data = n_usable.gt(0)  # at least one usable year -> IndiaSAT decides
        majority_habitat = hab_votes.gt(n_usable.subtract(hab_votes)).rename("habitat")
        tie = hab_votes.multiply(2).eq(n_usable).rename("habitat")

        # Tie-break = most recent usable year. Sorting ascending by time and
        # mosaicking keeps the latest valid pixel on top, falling back to the
        # next-latest where the newest year is cloud/no-data.
        lulc_latest = (
            lulc_ic.sort("system:time_start").mosaic().rename("lulc").clip(roi)
        )
        latest_habitat = _is_habitat(lulc_latest).rename("habitat")

        # Majority decides; ties fall back to the most recent usable year.
        # Masked where IndiaSAT has no usable year at all (-> WorldCover below).
        veg_indiasat = (
            majority_habitat.where(tie, latest_habitat).updateMask(has_data)
        )

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
        # Colour habitat by the most-recent usable IndiaSAT class, then water
        # on top (water wins where the two independent sources overlap).
        summary = ee.Image(0).int()
        for cls in habitat_classes:
            summary = summary.where(lulc_latest.eq(cls), cls)
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
                "habitat_collapse": "majority_vote; ties -> most recent usable year",
                "worldcover_fallback_classes": keep,
                "worldcover_dataset": ds.worldcover,
                "water_occurrence_threshold": params.jrc_water_occurrence_threshold,
                "water_dataset": ds.water,
            },
        )

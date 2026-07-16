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

import re

import ee

from fmu.config import Config, MaskingParams
from fmu.stages.base import PipelineContext, Stage, StageResult, register_stage
from fmu.utils.gee import safe_call
from fmu.utils.logging import get_logger

log = get_logger(__name__)


def _hydro_start_year(asset_id: str) -> int | None:
    """Parse the hydrological start-year from a per-year LULC asset id.

    CoRE Stack images are named like '.../lulc_v4_2017_2018'; the first of the
    two years is the start of the hydrological year. Returns None if no
    ``YYYY_YYYY`` token is present.
    """
    m = re.search(r"(\d{4})_(\d{4})", asset_id.rsplit("/", 1)[-1])
    return int(m.group(1)) if m else None


def _load_indiasat_collection(
    asset: str, params: MaskingParams, roi: ee.Geometry
) -> ee.ImageCollection:
    """Load the annual LULC source as a single-band, time-stamped collection.

    The CoRE Stack LULC_v4 product is a FOLDER of per-year single-band images
    (band ``predicted_label``) that carry no ``system:time_start`` — so an
    ``ee.ImageCollection(folder)`` load fails and the recency tie-break has
    nothing to sort on. This lists the folder, keeps the images inside the
    configured hydrological-year window, selects the class band, and stamps
    each image with a ``system:time_start`` derived from the year in its asset
    id so the majority-vote + most-recent-year logic downstream works unchanged.

    If ``asset`` is instead a real ImageCollection, it is loaded directly
    (preserving the pre-CoRE-Stack behaviour).
    """
    band = params.indiasat_class_band

    try:
        asset_type = ee.data.getAsset(asset).get("type")
    except Exception:  # noqa: BLE001 - fall through to folder handling on any error
        asset_type = None

    if asset_type == "IMAGE_COLLECTION":
        ic = ee.ImageCollection(asset).filterBounds(roi)
        if band is not None:
            return ic.select([band])
        return ic.map(lambda img: img.select(0))

    # FOLDER (or unknown): build the collection from the per-year child images.
    children = ee.data.listAssets({"parent": asset}).get("assets", [])
    images: list[ee.Image] = []
    used_years: list[int] = []
    for child in children:
        if child.get("type") not in ("IMAGE", "Image"):
            continue
        cid = child.get("id") or child.get("name")
        year = _hydro_start_year(cid)
        if year is None:
            continue
        if params.indiasat_year_min is not None and year < params.indiasat_year_min:
            continue
        if params.indiasat_year_max is not None and year > params.indiasat_year_max:
            continue
        img = ee.Image(cid)
        img = img.select([band]) if band is not None else img.select(0)
        # Stamp a monotonic-in-year timestamp so .sort("system:time_start")
        # orders the images by recency (the images carry no native timestamp).
        img = img.set("system:time_start", ee.Date.fromYMD(year, 1, 1).millis())
        images.append(img)
        used_years.append(year)

    if not images:
        raise ee.EEException(
            f"No annual LULC images found under {asset!r} within year window "
            f"[{params.indiasat_year_min}, {params.indiasat_year_max}]. "
            "Check the asset path and the indiasat_year_min/max config."
        )

    log.info(
        "Built IndiaSAT collection from %d year-images (%s) under %s",
        len(images),
        ", ".join(str(y) for y in sorted(used_years)),
        asset,
    )
    return ee.ImageCollection(images).filterBounds(roi).sort("system:time_start")


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

        # ----- IndiaSAT / CoRE Stack LULC: primary habitat source -----
        # Annual 30 m LULC. Decide habitat by majority vote over the usable
        # years, tie-broken by the most recent usable year. The source is a
        # folder of per-year images; _load_indiasat_collection selects the
        # class band, applies the year window, and stamps a per-year timestamp.
        indiasat_ic = _load_indiasat_collection(ds.indiasat, params, roi)

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
                "indiasat_year_window": [params.indiasat_year_min, params.indiasat_year_max],
                "habitat_collapse": "majority_vote; ties -> most recent usable year",
                "worldcover_fallback_classes": keep,
                "worldcover_dataset": ds.worldcover,
                "water_occurrence_threshold": params.jrc_water_occurrence_threshold,
                "water_dataset": ds.water,
            },
        )

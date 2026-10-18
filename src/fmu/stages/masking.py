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
  - mask_provenance: why each pixel is in or out of habitat_mask, two bands
      reason  1 kept / 2 removed as cropland / 3 as built-up / 4 as water /
              5 as other non-habitat / 0 no land-cover data in either map
      source  1 IndiaSAT decided / 2 WorldCover decided (IndiaSAT has no data)
              / 0 neither map has data
    `reason == 1` exactly where `habitat_mask == 1`. It is derived beside the
    mask and never feeds it, so adding it cannot change a stand.

This is a HABITAT mask, not a strict forest mask: it keeps shrubs and scrub as
well as trees, and grassland too where the WorldCover fallback decides. The
definition is set out in the masking section of docs/design_notes.md, and the
legend of the reason layer says so wherever it is drawn.

Caching. The stage declares no `cacheable_outputs`, so all four outputs are
cached as Earth Engine assets. `mask_provenance` was added after the other three
had already been cached for the configs run so far. For such a config the next
cached run reads those three back, computes `mask_provenance` live and exports
only it; downstream stages keep receiving the cached `habitat_mask`, not a
recomputed one. The summary number `area_ha_reason_disagrees_with_habitat_mask`
is the check on that pairing: it is zero when the mask and the reason layer come
from the same inputs, so anything else means a land-cover input changed between
the day the mask was cached and the day the reason layer was computed.
"""

from __future__ import annotations

import re
from typing import Any

import ee

from fmu.config import Config, MaskingParams
from fmu.stages.base import (
    DisplayLayer,
    LegendEntry,
    PipelineContext,
    Stage,
    StageResult,
    SummaryNumber,
    register_stage,
)
from fmu.utils.gee import safe_call, safe_get_info
from fmu.utils.logging import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------------
# mask_provenance codes
# ---------------------------------------------------------------------
REASON_NO_DATA = 0
REASON_KEPT = 1
REASON_CROPLAND = 2
REASON_BUILT_UP = 3
REASON_WATER = 4
REASON_OTHER = 5

SOURCE_NONE = 0
SOURCE_INDIASAT = 1
SOURCE_WORLDCOVER = 2

REASON_NAMES: dict[int, str] = {
    REASON_NO_DATA: "no_data",
    REASON_KEPT: "kept",
    REASON_CROPLAND: "cropland",
    REASON_BUILT_UP: "built_up",
    REASON_WATER: "water",
    REASON_OTHER: "other_non_habitat",
}
SOURCE_NAMES: dict[int, str] = {
    SOURCE_NONE: "none",
    SOURCE_INDIASAT: "indiasat",
    SOURCE_WORLDCOVER: "worldcover",
}

# Which non-habitat classes fall under which reason. These are facts about the
# two land-cover legends, not settings: the habitat classes themselves stay in
# the config (`masking.indiasat_habitat_classes`, `keep_worldcover_classes`),
# and a class the config keeps is "kept" whatever group it is listed under here.
# Any class in neither a kept list nor a group below is "other non-habitat".
#
# IndiaSAT / CoRE Stack LULC_v4. The three groups are the ones the comment on
# fmu.config.MaskingParams gives: built-up 1, water 2-4, crops 5 and 8-11. What
# is left lands in "other non-habitat": 7, barren (MaskingParams); 13,
# orchard/plantation (docs/datasets.md); and 0, which only
# scripts/build_master_deck.js names ("Background"). The LULC_v4 images carry
# no class table of their own, so these groups rest on the repo's documents and
# cannot be checked against the dataset.
_INDIASAT_REASON_CLASSES: dict[int, tuple[int, ...]] = {
    REASON_CROPLAND: (5, 8, 9, 10, 11),
    REASON_BUILT_UP: (1,),
    REASON_WATER: (2, 3, 4),
}
# ESA WorldCover v200. The repo documents only the three classes it keeps (10
# tree cover, 20 shrubland, 30 grassland), so the groups below are NOT confirmed
# by anything in the repo. They follow the class table the Earth Engine asset
# itself carries (`Map_class_values` / `Map_class_names`, read 2026-10-13):
# 40 cropland, 50 built-up, 80 permanent water bodies. The rest of that table
# lands in "other non-habitat": 60 bare / sparse vegetation, 70 snow and ice,
# 90 herbaceous wetland, 95 mangroves, 100 moss and lichen.
_WORLDCOVER_REASON_CLASSES: dict[int, tuple[int, ...]] = {
    REASON_CROPLAND: (40,),
    REASON_BUILT_UP: (50,),
    REASON_WATER: (80,),
}

_REASON_LEGEND: tuple[LegendEntry, ...] = (
    LegendEntry(REASON_NO_DATA, "No land-cover data in either map (not habitat)", "000000"),
    LegendEntry(REASON_KEPT, "Kept as habitat (not only forest)", "1a9850"),
    LegendEntry(REASON_CROPLAND, "Removed: cropland", "fdae61"),
    LegendEntry(REASON_BUILT_UP, "Removed: built-up", "d73027"),
    LegendEntry(REASON_WATER, "Removed: water", "4575b4"),
    LegendEntry(REASON_OTHER, "Removed: other non-habitat", "9e9e9e"),
)
_SOURCE_LEGEND: tuple[LegendEntry, ...] = (
    LegendEntry(SOURCE_NONE, "Neither map has data", "000000"),
    LegendEntry(SOURCE_INDIASAT, "IndiaSAT decided", "7570b3"),
    LegendEntry(SOURCE_WORLDCOVER, "WorldCover decided (IndiaSAT has no data)", "e7298a"),
)

# Shown with the legend wherever the reason layer is drawn. The classes it names
# are the schema defaults (tests/test_transparency_contract.py holds the two
# together); a config may keep others, which is why it says "by default" and
# points at `kept_classes`, the summary number that lists what a run kept.
_HABITAT_NOTE = (
    "This is a habitat mask, not a strict forest mask. By default it keeps "
    "IndiaSAT Trees and Shrubs/Scrub, and WorldCover tree cover, shrubland and "
    "grassland where IndiaSAT has no data; the classes a run kept are listed "
    "in its masking summary (kept_classes). The definition and the reasoning "
    "behind it are in docs/design_notes.md, section \"Masking: "
    "IndiaSAT-primary, single-phase habitat\"."
)


def _reason_from_classes(
    class_img: ee.Image, groups: dict[int, tuple[int, ...]]
) -> ee.Image:
    """Map a land-cover class image to removal-reason codes.

    Classes named in `groups` get their reason; every other class gets
    REASON_OTHER. Masked pixels stay masked. Kept classes are not special-cased
    here: the caller overwrites them with REASON_KEPT from the habitat decision
    itself, so this never has to agree with the config about what is habitat.
    """
    src: list[int] = []
    dst: list[int] = []
    for reason, classes in sorted(groups.items()):
        src.extend(classes)
        dst.extend([reason] * len(classes))
    return class_img.remap(src, dst, REASON_OTHER)


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
    produces = {"habitat_mask", "water_mask", "landcover_summary", "mask_provenance"}

    display_layers = (
        DisplayLayer(
            key="mask_provenance",
            band="reason",
            title="Habitat mask, by reason",
            description=(
                "What the mask kept, and why it removed the rest: cropland, "
                "built-up, water or other non-habitat. Under IndiaSAT a pixel is "
                "kept or removed by a majority vote over its usable years, and a "
                "removed pixel is given the reason of its most recent "
                "non-habitat year. Other non-habitat is every remaining class: "
                "in IndiaSAT, barren land and orchard/plantation; in WorldCover, "
                "bare or sparse vegetation, snow and ice, herbaceous wetland, "
                "mangroves, and moss and lichen."
            ),
            legend=_REASON_LEGEND,
            legend_note=_HABITAT_NOTE,
        ),
        DisplayLayer(
            key="mask_provenance",
            band="source",
            title="Which map decided each pixel",
            description=(
                "IndiaSAT decides wherever it has at least one usable year; "
                "WorldCover decides only where IndiaSAT has no data."
            ),
            legend=_SOURCE_LEGEND,
        ),
    )
    summary_numbers = (
        SummaryNumber("area_ha", "Area of the ROI the mask was tabulated over", "ha"),
        SummaryNumber("share_kept", "Share of that area kept as habitat", "fraction"),
        SummaryNumber(
            "share_by_reason",
            "Share of the area under each reason: kept, removed as cropland, as "
            "built-up, as water, as other non-habitat, or no land-cover data. "
            "Adds up to 1",
            "fraction",
        ),
        SummaryNumber(
            "share_kept_by_source",
            "Share of the whole area that was kept as habitat, split by the map "
            "that decided it. Adds up to share_kept",
            "fraction",
        ),
        SummaryNumber(
            "share_decided_by_source",
            "Share of the area each map decided, kept or removed. Adds up to 1",
            "fraction",
        ),
        SummaryNumber(
            "area_ha_by_reason_and_source",
            "Area under each reason, split by the map that decided it",
            "ha",
        ),
        SummaryNumber(
            "area_ha_reason_disagrees_with_habitat_mask",
            "Area where the reason layer says kept and habitat_mask does not, or "
            "the reverse. Zero when both come from the same inputs; anything "
            "else means the cached habitat_mask predates a change in a "
            "land-cover input",
            "ha",
        ),
        SummaryNumber(
            "kept_classes",
            "Land-cover classes this run kept as habitat, from the config: "
            "IndiaSAT classes, and the WorldCover classes used where IndiaSAT "
            "has no data",
            "class code",
        ),
    )

    def input_collections(self, ctx: PipelineContext, config: Config) -> dict[str, Any]:
        """The annual LULC images the vote reads and the WorldCover image used where
        it has no data, as `run()` loads them (the JRC water map is one image, named
        in the config)."""
        roi = ctx.get("roi")
        return {
            "indiasat_lulc": _load_indiasat_collection(
                config.datasets.indiasat, config.masking, roi
            ),
            # run() takes the collection's first image
            "worldcover": ee.ImageCollection(config.datasets.worldcover).limit(1),
        }

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

        # ----- mask_provenance: why each pixel is in or out (transparency) -----
        # Derived beside the mask from the same inputs; nothing else in this
        # method reads it. "Kept" is taken from the habitat decision itself
        # (veg_indiasat, veg_wc), so reason == 1 exactly where habitat_mask == 1
        # by construction, whatever the class groups say.
        #
        # A removed IndiaSAT pixel takes the reason of its most recent
        # NON-HABITAT year. It always has one: it lost the majority vote, or
        # tied and its latest year was not habitat. So the unmask(REASON_OTHER)
        # below only ever fills pixels that are then set to kept or masked out.
        # "Most recent" mirrors the tie-break above, and says what the pixel is
        # now rather than what it was on average. It sorts on the same
        # per-year timestamp the tie-break sorts on, which
        # _load_indiasat_collection stamps from the year in each asset id (the
        # images have no timestamp of their own).
        nonhab_reason_latest = (
            lulc_ic.map(
                lambda img: _reason_from_classes(img, _INDIASAT_REASON_CLASSES)
                .updateMask(_is_habitat(img).Not())
                .rename("reason")
                .copyProperties(img, ["system:time_start"])
            )
            .sort("system:time_start")
            .mosaic()
            .rename("reason")
        )
        reason_indiasat = (
            nonhab_reason_latest.unmask(REASON_OTHER)
            .where(veg_indiasat.eq(1), REASON_KEPT)
            .updateMask(has_data)
        )
        reason_wc = _reason_from_classes(wc, _WORLDCOVER_REASON_CLASSES).where(
            veg_wc.eq(1), REASON_KEPT
        )
        reason = (
            reason_indiasat.unmask(reason_wc).unmask(REASON_NO_DATA).rename("reason")
        )
        source = (
            ee.Image.constant(SOURCE_INDIASAT)
            .updateMask(has_data)
            .unmask(ee.Image.constant(SOURCE_WORLDCOVER).updateMask(wc.mask()))
            .unmask(SOURCE_NONE)
            .rename("source")
        )
        mask_provenance = reason.addBands(source).toUint8().clip(roi)

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
                "mask_provenance": mask_provenance,
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
                "mask_provenance_reason_codes": {
                    str(k): v for k, v in REASON_NAMES.items()
                },
                "mask_provenance_source_codes": {
                    str(k): v for k, v in SOURCE_NAMES.items()
                },
            },
        )

    def summarise(self, ctx: PipelineContext, config: Config) -> dict[str, Any]:
        """Area of the ROI by reason and by deciding map, and the classes kept.

        One Earth Engine call: a grouped area sum over the ROI. It reads the
        images from the context, so it works the same on a live run and on one
        read back from the cache.
        """
        numbers = summarise_mask_provenance(
            ctx.get("mask_provenance"),
            ctx.get("habitat_mask"),
            ctx.get("roi"),
            config.export.analysis_scale_m,
        )
        numbers["kept_classes"] = {
            SOURCE_NAMES[SOURCE_INDIASAT]: list(config.masking.indiasat_habitat_classes),
            SOURCE_NAMES[SOURCE_WORLDCOVER]: list(config.masking.keep_worldcover_classes),
        }
        return numbers


def summarise_mask_provenance(
    mask_provenance: ee.Image,
    habitat_mask: ee.Image,
    roi: ee.Geometry,
    scale: float,
) -> dict[str, Any]:
    """Tabulate `mask_provenance` and `habitat_mask` over an ROI.

    The Earth Engine half is `mask_provenance_areas`, the arithmetic is
    `tabulate_mask_provenance`. Returns every masking summary number that is
    measured from the images; `kept_classes` comes from the config and is added
    by the stage.
    """
    return tabulate_mask_provenance(
        mask_provenance_areas(mask_provenance, habitat_mask, roi, scale)
    )


def mask_provenance_areas(
    mask_provenance: ee.Image,
    habitat_mask: ee.Image,
    roi: ee.Geometry,
    scale: float,
) -> dict[int, float]:
    """Square metres of the ROI under each (disagrees, source, reason).

    One grouped reduction, so one Earth Engine call. The group key packs the
    three codes into one integer, `disagrees * 100 + source * 10 + reason`,
    where `disagrees` is 1 where `reason` says kept and `habitat_mask` does not,
    or the reverse.

    It sums pixel area rather than counting pixels, and weights each edge pixel
    by how much of it the ROI covers, so the total is the ROI's area and not a
    pixel count times a nominal pixel size (in this grid a "10 m" pixel is
    10 m tall and 10 m x cos(latitude) wide).

    The grid is named rather than inherited: EPSG:4326 at `scale`. At the 10 m
    every shipped config uses, that is the grid a cache export of these images
    lands on and the grid of the IndiaSAT rasters themselves, so a cached
    `habitat_mask` is read pixel for pixel and is compared with `reason` at the
    very pixels it was exported at. A grouped sum keeps one running total per
    key, at most 36 of them, so its memory does not grow with the ROI.
    """
    reason = mask_provenance.select("reason")
    source = mask_provenance.select("source")
    disagrees = reason.eq(REASON_KEPT).neq(habitat_mask.unmask(0).eq(1))
    key = disagrees.multiply(100).add(source.multiply(10)).add(reason).rename("key")
    grouped = safe_get_info(
        ee.Image.pixelArea()
        .addBands(key)
        .reduceRegion(
            reducer=ee.Reducer.sum().group(groupField=1, groupName="key"),
            geometry=roi,
            crs="EPSG:4326",
            scale=scale,
            maxPixels=int(1e10),
            tileScale=4,
        ),
        context="mask_provenance area by reason and source",
    )
    return {int(g["key"]): float(g["sum"]) for g in grouped.get("groups", [])}


def tabulate_mask_provenance(area_m2_by_key: dict[int, float]) -> dict[str, Any]:
    """Turn the grouped areas into summary numbers. Pure Python.

    `area_m2_by_key` maps `disagrees * 100 + source * 10 + reason` to square
    metres, as `mask_provenance_areas` returns it. Split out from the Earth
    Engine call so the arithmetic is unit-tested.

    "Kept" means two things here and they are kept apart. `share_kept` and
    `share_kept_by_source` are read off `habitat_mask`, the mask the rest of the
    pipeline uses. `share_by_reason` and `area_ha_by_reason_and_source` are read
    off the reason layer. The two agree whenever
    `area_ha_reason_disagrees_with_habitat_mask` is zero, which it is unless the
    mask came from a cache older than a change in a land-cover input.
    """
    total = sum(area_m2_by_key.values())
    by_reason: dict[str, float] = {name: 0.0 for name in REASON_NAMES.values()}
    by_source: dict[str, float] = {name: 0.0 for name in SOURCE_NAMES.values()}
    kept_by_source: dict[str, float] = {name: 0.0 for name in SOURCE_NAMES.values()}
    nested: dict[str, dict[str, float]] = {
        r: {s: 0.0 for s in SOURCE_NAMES.values()} for r in REASON_NAMES.values()
    }
    kept_m2 = 0.0
    disagree_m2 = 0.0
    for key, m2 in area_m2_by_key.items():
        disagrees, rest = divmod(key, 100)
        source_code, reason_code = divmod(rest, 10)
        if (
            disagrees not in (0, 1)
            or source_code not in SOURCE_NAMES
            or reason_code not in REASON_NAMES
        ):
            raise ValueError(
                f"mask_provenance: group key {key} does not decode to a known "
                f"(disagrees, source, reason)."
            )
        r, s = REASON_NAMES[reason_code], SOURCE_NAMES[source_code]
        by_reason[r] += m2
        by_source[s] += m2
        nested[r][s] += m2
        # habitat_mask is 1 where reason says kept, except where they disagree.
        if (reason_code == REASON_KEPT) != bool(disagrees):
            kept_m2 += m2
            kept_by_source[s] += m2
        if disagrees:
            disagree_m2 += m2

    def share(m2: float) -> float:
        return round(m2 / total, 6) if total else 0.0

    def ha(m2: float) -> float:
        return round(m2 / 10_000.0, 4)

    return {
        "area_ha": ha(total),
        "share_kept": share(kept_m2),
        "share_by_reason": {r: share(m2) for r, m2 in by_reason.items()},
        "share_kept_by_source": {s: share(m2) for s, m2 in kept_by_source.items()},
        "share_decided_by_source": {s: share(m2) for s, m2 in by_source.items()},
        "area_ha_by_reason_and_source": {
            r: {s: ha(m2) for s, m2 in row.items()} for r, row in nested.items()
        },
        "area_ha_reason_disagrees_with_habitat_mask": ha(disagree_m2),
    }

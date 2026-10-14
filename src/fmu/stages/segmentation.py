"""SNIC superpixel segmentation. Draws boundaries on a config-driven input
stack at 10 m native resolution, producing labeled superpixels.

Under the merge design, SNIC is no longer a throwaway primitive whose output
gets dissolved by cluster id -- SNIC plus the `merge` stage *produces the
stand*, and clustering is demoted to attaching a type label to a finished
stand. That makes the choice of segmentation bands a first-class experimental
variable, so it lives in config (`segmentation.input_bands`) rather than in a
hardcoded literal here.

The default stack spans roughly four independent axes:
  - B4_median, B8_median        S2 red + NIR (optical colour)
  - canopy_height               ETH 2020 (vertical structure)
  - ndvi_amplitude_annual       seasonal swing (the deciduous/evergreen axis;
                                without it SNIC sees no phenology at all, since
                                it runs on a multi-year median composite)
  - vv_minus_vh_median          S1 cross-pol contrast (sensor-independent)

`canopy_height_std` (3x3 roughness) was in the default until the Odisha field
validation. It was documented here as canopy completeness -- "separates a smooth
plantation-like canopy from a gap-rich natural one at the same mean height" --
and that claim did not survive measurement: against field crown cover over 274
plots it scores R2=0.000 (r=-0.011). It is still computed by features_structure
and still declarable, but it is no longer a default segmentation band, because
drawing boundaries with it means drawing them on a quantity with no established
meaning.

`composite_nirv` is deliberately absent from the default: it is
(B8/10000) x NDVI, an algebraic function of B4 and B8, so carrying it spent
three columns on two degrees of freedom and inflated optical weight in SNIC's
distance metric. It remains *available* -- declare it explicitly as
{source: s2_composite, band: composite_nirv} and this stage computes it.

An entry may also use `band: "*"` to take every band of its source. That is how
the embedding arms segment on all 64 (or 128) dimensions without listing them
in YAML, and it keeps working if the embedding's dimensionality changes.

Bands are z-scored per-band over the ROI, then (by default) divided by the
empirical RMS 4-neighbour feature distance so that summed squared colour
distance is invariant to band count and to correlation between bands. Without
that second step `compactness` silently means something different in a 5-band
arm than in a 64-band embedding arm.

Boundaries are NOT held constant across arms: each pipeline segments on its own
feature space and the resulting stand maps are compared directly.

Kept land only (`segmentation.mask_before_snic`, off by default). With it on,
the z-score and the distance normaliser are measured over the land the masking
stage keeps, SNIC runs on the stack with every other pixel masked, from seeds
that leave no patch of kept land without one (`fmu.utils.kept_land`), and both
outputs are masked to kept land. Off, nothing here reads `habitat_mask`, and the
stage computes what it computed before the setting existed.

Outputs:
  - snic_clusters: integer cluster ID per pixel
  - snic_means:    per-cluster mean of each input band
"""

from __future__ import annotations

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
from fmu.utils.gee import safe_call, safe_get_info
from fmu.utils.grid import analysis_grid
from fmu.utils.kept_land import kept_land_in_roi, seeds_on_kept_land
from fmu.utils.logging import get_logger

log = get_logger(__name__)


# Bands this stage derives itself rather than selecting from an upstream image.
# Keyed by (source, band).
_DERIVED_BANDS: frozenset[tuple[str, str]] = frozenset(
    {("s2_composite", "composite_nirv")}
)


@register_stage("segmentation")
class SegmentationStage(Stage):
    name = "segmentation"
    # Invariant subset only. The feature images SNIC needs depend on
    # `segmentation.input_bands`, so the real dependency check lives in
    # validate() (required_inputs is a static class attribute and cannot see
    # the config). Same pattern as ClusteringStage.
    required_inputs = {"roi"}
    produces = {"snic_clusters", "snic_means"}
    cacheable_outputs = {"snic_clusters", "snic_means"}

    # Transparency: the superpixels as outlines. A superpixel label is an
    # arbitrary 32-bit number (one seen: 1779165740), so it can carry neither a
    # legend nor a colour scale; what there is to see is where the boundaries
    # run. `style: outline` says so (see DisplayLayer). The colour is the one
    # the early ui_data build of 13 Oct 2026 (scripts/build_ui_early_data.py)
    # drew superpixel boundaries in.
    display_layers = (
        DisplayLayer(
            key="snic_clusters",
            band="snic_clusters",
            title="Superpixels (outlines)",
            description=(
                "The boundaries of the SNIC superpixels: small patches of "
                "similar pixels, grown from a regular grid of seeds on the "
                "bands named in segmentation.input_bands. By default they "
                "cover the whole area. With segmentation.mask_before_snic on "
                "they cover only the land the masking step keeps, and a patch "
                "of kept land that no seed of the grid falls in is one "
                "superpixel. They are the pieces the merge step joins into "
                "stands, so every stand boundary runs along one of these "
                "lines. The superpixels are not stands, and their numbers "
                "mean nothing."
            ),
            vis={"style": "outline", "palette": ["ffd400"]},
        ),
    )

    def validate(self, ctx: PipelineContext, config: Config) -> None:
        needed = {"roi"} | config.segmentation.input_sources()
        if config.segmentation.mask_before_snic:
            needed.add("habitat_mask")
        missing = needed - ctx.keys()
        if missing:
            raise KeyError(
                f"{self.name}: missing required context inputs: {sorted(missing)}. "
                f"Context has: {sorted(ctx.keys())}. These are required because "
                f"segmentation.input_bands references them (and, for "
                f"habitat_mask, because segmentation.mask_before_snic is on) -- "
                f"either add the producing stage to the run, or change the config."
            )

    @safe_call("running SNIC segmentation")
    def run(self, ctx: PipelineContext, config: Config) -> StageResult:
        roi = ctx.get("roi")
        params = config.segmentation
        scale = config.export.analysis_scale_m

        # Build the input stack from config, in the declared order.
        input_band_names, raw_stack = _resolve_input_stack(ctx, config)

        # Kept land, when SNIC is to see only that (segmentation.mask_before_snic):
        # 1 where habitat_mask keeps the pixel (less the patches too small to be
        # a stand, with drop_kept_patches_below_min_area), 0 elsewhere. None when
        # the setting is off, and then nothing below reads the mask.
        # Kept land stops at the ROI: the mask is put on the analysis grid and
        # clipped to the ROI as the outputs are below, before anything is made
        # from it, so SNIC cannot grow a superpixel past the ROI edge that the
        # clip of its output would then cut (fmu.utils.kept_land.kept_land_in_roi).
        kept: ee.Image | None = None
        grid: ee.Projection | None = None
        if params.mask_before_snic:
            grid = _analysis_grid(roi, scale)
            kept = kept_land_in_roi(
                ctx.get("habitat_mask"),
                roi,
                grid,
                min_patch_pixels=config.kept_patch_min_pixels(),
                connectivity=params.connectivity,
            )
            _require_kept_land(kept, roi, scale)

        # Z-score per band over the ROI to put all bands on a comparable scale.
        # Without this, B4_median (0-3000) would dominate vs canopy_height (0-30).
        # With kept land only, the mean and spread are those of kept land: the
        # pixels SNIC will see.
        if params.normalize_inputs:
            snic_input = _zscore_per_band(raw_stack, roi, scale, within=kept)
        else:
            snic_input = raw_stack

        # Make `compactness` mean the same thing regardless of how many (and how
        # correlated) the input bands are. SNIC trades a colour distance against
        # a spatial-compactness term; summed squared colour distance grows with
        # the number of *effective* axes, so a 64-band embedding stack would
        # otherwise have a far weaker spatial term than a 5-band one at the same
        # `compactness`. Dividing by sqrt(n_bands) would assume the bands are
        # independent -- for an embedding they are not, and it over-corrects.
        # The empirical RMS distance between 4-adjacent pixels handles band count
        # and correlation together.
        distance_scale: float | None = None
        if params.normalize_distance_scale:
            distance_scale = _rms_adjacent_distance(snic_input, roi, scale, within=kept)
            snic_input = snic_input.divide(distance_scale)
            log.info(
                "  distance normaliser (RMS 4-neighbour feature distance): %.6f",
                distance_scale,
            )

        # Run SNIC
        if kept is None:
            snic_result = ee.Algorithms.Image.Segmentation.SNIC(
                image=snic_input,
                size=params.size,
                compactness=params.compactness,
                connectivity=params.connectivity,
                neighborhoodSize=params.neighborhood_size,
            )
        else:
            # Kept land only. SNIC grows superpixels through unmasked pixels
            # only, so a kept patch with no seed would get no superpixel; the
            # seeds are the grid plus every pixel of each kept patch that holds
            # no grid point (fmu.utils.kept_land). `size` is passed as before,
            # although SNIC ignores it once it is given seeds
            # (scripts/check_snic_on_kept_land.py, 14 Oct 2026).
            min_patch = config.kept_patch_min_pixels()
            log.info(
                "  kept land only: SNIC sees the pixels habitat_mask keeps, "
                "seeded on the grid plus each kept patch the grid misses%s",
                f"; kept patches under {min_patch} pixels left out" if min_patch else "",
            )
            snic_result = ee.Algorithms.Image.Segmentation.SNIC(
                image=snic_input.updateMask(kept),
                size=params.size,
                compactness=params.compactness,
                connectivity=params.connectivity,
                neighborhoodSize=params.neighborhood_size,
                seeds=seeds_on_kept_land(
                    kept,
                    size=params.size,
                    connectivity=params.connectivity,
                    max_extent=params.neighborhood_size,
                ),
            )
        # SNIC output bands:
        #   - "clusters": integer cluster ID per pixel
        #   - "seeds":    the seed locations (1 where a cluster centroid sits)
        #   - "<input>_mean": one band per input, holding the per-cluster mean
        # We keep the clusters band and the means; drop seeds.

        # Pin the outputs to a real pixel grid before handing them downstream.
        # SNIC's result does not carry one: EE gives an unbaked computed image
        # its default WGS84 1-degree projection, so `snic_clusters.projection()
        # .nominalScale()` reports ~111 km until the image has been written to
        # an asset. That is not cosmetic. The merge stage shifts by whole pixels
        # to build the adjacency graph, and doing that in a 1-degree grid
        # measures the wrong neighbours entirely -- and it would only show up on
        # a *fresh* run, since a cached asset reports its real projection and
        # works fine. A bug that appears only when the cache is cold is the kind
        # worth removing at the source.
        #
        # This is the one place the grid gets pinned, and everything downstream
        # inherits it: `reduceRegion` defaults its CRS to the first band's
        # projection, and merge, profiling, metrics and export all reduce over
        # images derived from these two.
        if grid is None:
            grid = _analysis_grid(roi, scale)
        snic_clusters = (
            snic_result.select("clusters")
            .rename("snic_clusters")
            .reproject(grid)
            .clip(roi)
        )

        means_band_names = [f"{b}_mean" for b in input_band_names]
        snic_means = (
            snic_result.select(means_band_names)
            .rename(input_band_names)  # drop the _mean suffix
            .reproject(grid)
            .clip(roi)
        )

        if kept is not None:
            # SNIC leaves masked input pixels unlabelled (A6, 14 Oct 2026). This
            # applies the rule as well, rather than relying on that, so no label
            # lies off kept land whatever SNIC does there. The merge stage measures, on
            # the image it reads, how much kept land is left without a label
            # (merge_diagnostics["kept_land"]); the export stage's count of
            # stands in several pieces would show a superpixel SNIC grew across
            # masked land.
            snic_clusters = snic_clusters.updateMask(kept)
            snic_means = snic_means.updateMask(kept)

        # Diagnostic
        grid_scale = safe_get_info(
            grid.nominalScale(), context="SNIC output grid scale"
        )
        log.info(
            "  output grid: %s at %.1f m (analysis scale %d m)",
            safe_get_info(grid.crs(), context="SNIC output grid CRS"),
            grid_scale,
            scale,
        )
        means_bands = safe_get_info(snic_means.bandNames(), context="snic_means bands")
        log.info("  snic_means bands (%d): %s", len(means_bands), means_bands)
        log.info(
            "  SNIC params: size=%d compactness=%s connectivity=%d neighborhood=%d normalize=%s",
            params.size,
            params.compactness,
            params.connectivity,
            params.neighborhood_size,
            params.normalize_inputs,
        )

        return StageResult(
            outputs={
                "snic_clusters": snic_clusters,
                "snic_means": snic_means,
            },
            metadata={
                "snic_input_bands": input_band_names,
                "snic_input_sources": [
                    {"source": b.source, "band": b.band} for b in params.input_bands
                ],
                "normalize_inputs": params.normalize_inputs,
                "normalize_distance_scale": params.normalize_distance_scale,
                # Derived, and it changes the segmentation -- so it has to be
                # auditable from the manifest rather than recomputed by hand.
                "distance_scale": distance_scale,
                "size": params.size,
                "compactness": params.compactness,
                "connectivity": params.connectivity,
                "neighborhood_size": params.neighborhood_size,
                # Which rule ran: the whole area, or kept land only, and the
                # smallest kept patch SNIC saw (0: none was left out).
                "mask_before_snic": params.mask_before_snic,
                **(
                    {"kept_patch_min_pixels": config.kept_patch_min_pixels()}
                    if params.mask_before_snic
                    else {}
                ),
            },
        )


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------


def _resolve_input_stack(
    ctx: PipelineContext, config: Config
) -> tuple[list[str], ee.Image]:
    """Resolve `segmentation.input_bands` to (band names, stacked image).

    Entries are concatenated in declared order. A `"*"` entry expands to every
    band of its source image, which costs one getInfo per wildcarded source --
    the only way to learn the names client-side, and we need them to build the
    `<band>_mean` select list off SNIC's output.
    """
    names: list[str] = []
    images: list[ee.Image] = []
    for spec in config.segmentation.input_bands:
        image = _resolve_input_band(ctx, config, spec.source, spec.band)
        if spec.band == "*":
            names.extend(
                safe_get_info(
                    image.bandNames(), context=f"band names of {spec.source}"
                )
            )
        else:
            names.append(spec.band)
        images.append(image)

    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        raise ValueError(
            f"segmentation.input_bands resolves to duplicate band name(s) "
            f"{dupes} (resolved stack: {names}). SNIC names its per-cluster "
            f"means '<band>_mean', so duplicates would be ambiguous. This can "
            f"only happen via a '*' entry -- two sources sharing a band name."
        )
    return names, ee.Image.cat(images)


def _resolve_input_band(
    ctx: PipelineContext, config: Config, source: str, band: str
) -> ee.Image:
    """Return the image for one configured SNIC input entry.

    Single-band for a named band, all bands for `"*"`. Most bands are selected
    straight off an upstream context image; the exception is `composite_nirv`,
    which no upstream stage produces -- it is derived here from the S2
    composite.
    """
    if (source, band) in _DERIVED_BANDS:
        return _derive_composite_nirv(ctx, config, source)
    image: ee.Image = ctx.get(source)
    if band == "*":
        return image
    return image.select(band).rename(band)


def _derive_composite_nirv(
    ctx: PipelineContext, config: Config, source: str
) -> ee.Image:
    """NIRv from the S2 composite: (NIR / 10000) x NDVI.

    S2 SR is stored scaled by 10000, so divide back to reflectance before
    multiplying. Same convention as features_optical's nirv computation.

    Band names carry the compositing reducer's suffix (B4_median for a median
    composite), so read the suffix from config rather than hardcoding "median".
    """
    suffix = config.data_load.s2_composite_reducer
    s2: ee.Image = ctx.get(source)
    b4 = s2.select(f"B4_{suffix}")
    b8 = s2.select(f"B8_{suffix}")
    ndvi = b8.subtract(b4).divide(b8.add(b4))
    return b8.divide(10000).multiply(ndvi).rename("composite_nirv")


def _rms_adjacent_distance(
    image: ee.Image,
    roi: ee.Geometry,
    scale: int,
    *,
    within: ee.Image | None = None,
) -> float:
    """RMS feature distance between 4-adjacent pixels, over all bands.

    For each pixel and each of the two unique 4-neighbour directions, the
    squared distance is the sum over bands of the squared per-band difference.
    This returns sqrt(mean of that over the ROI and over both directions).

    Dividing the stack by this makes SNIC's summed squared colour distance
    invariant to band count *and* to correlation between bands, so `compactness`
    is comparable across arms with different feature spaces. Adjacency is
    defined at `scale` (the analysis scale) via the reduction, so both arms must
    use the same scale for the numbers to mean the same thing.

    `within`, a 0/1 image (kept land), restricts the mean to pairs whose two
    pixels are both 1 and have every band: the pairs SNIC compares when it sees
    kept land only. The pairs are found with the same two kernels, weights made
    positive, so they are the very pixel pairs the differences are taken over;
    a pair counts in the direction it was found in, and the mean is over all
    counted pairs. `image` itself is not masked by `within`. None keeps the
    computation exactly as it was before the option.
    """
    kx = ee.Kernel.fixed(2, 1, [[-1, 1]])
    ky = ee.Kernel.fixed(1, 2, [[-1], [1]])
    dx2 = image.convolve(kx).pow(2).reduce(ee.Reducer.sum())
    dy2 = image.convolve(ky).pow(2).reduce(ee.Reducer.sum())
    if within is not None:
        # A pair also needs every band at both pixels: how convolve treats a
        # masked neighbour is not documented, so no difference is taken there.
        valid = within.And(image.mask().reduce(ee.Reducer.min()).gt(0))
        return _rms_over_pairs_within(dx2, dy2, valid, roi, scale)
    mean_sq = safe_get_info(
        dx2.add(dy2).divide(2).rename("d2").reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=roi,
            scale=scale,
            maxPixels=1_000_000_000,
            bestEffort=True,
        ),
        context="RMS adjacent feature distance",
    ).get("d2")

    if not mean_sq or mean_sq <= 0:
        log.warning(
            "  RMS adjacent distance is %r; falling back to 1.0 (no rescaling). "
            "This usually means the SNIC stack is constant over the ROI.",
            mean_sq,
        )
        return 1.0
    return float(mean_sq) ** 0.5


def _require_kept_land(kept: ee.Image, roi: ee.Geometry, scale: int) -> None:
    """Fail with a plain message when the ROI holds no kept land.

    Without it the z-score below has no pixel to take a mean over, and Earth
    Engine fails later with an error about a missing number. One small request.
    """
    found = safe_get_info(
        kept.reduceRegion(
            reducer=ee.Reducer.max(),
            geometry=roi,
            scale=scale,
            maxPixels=1_000_000_000,
            bestEffort=True,
        ),
        context="kept land in the ROI",
    ).get("kept")
    if not found:
        raise ValueError(
            "segmentation.mask_before_snic is on, but the ROI holds no kept land "
            "(habitat_mask is never 1 there, or every kept patch is below the "
            "minimum stand size): there is nothing for SNIC to segment."
        )


def _rms_over_pairs_within(
    dx2: ee.Image,
    dy2: ee.Image,
    within: ee.Image,
    roi: ee.Geometry,
    scale: int,
) -> float:
    """The kept-land half of `_rms_adjacent_distance`: one reduction, sums and
    counts per direction, so pairs found in one direction only still count."""
    both_x = within.convolve(ee.Kernel.fixed(2, 1, [[1, 1]])).eq(2)
    both_y = within.convolve(ee.Kernel.fixed(1, 2, [[1], [1]])).eq(2)
    pairs = ee.Image.cat(
        [dx2.updateMask(both_x).rename("dx2"), dy2.updateMask(both_y).rename("dy2")]
    )
    stats = safe_get_info(
        pairs.reduceRegion(
            reducer=ee.Reducer.sum().combine(ee.Reducer.count(), sharedInputs=True),
            geometry=roi,
            scale=scale,
            maxPixels=1_000_000_000,
            bestEffort=True,
        ),
        context="RMS adjacent feature distance over kept land",
    )
    mean_sq = _mean_square_over_pairs(stats)
    if mean_sq is None:
        log.warning(
            "  RMS adjacent distance over kept land is undefined (no pair of "
            "adjacent kept pixels, or a stack constant over them); falling back "
            "to 1.0 (no rescaling)."
        )
        return 1.0
    return mean_sq**0.5


def _mean_square_over_pairs(stats: dict[str, Any]) -> float | None:
    """Mean squared distance over the pairs of both directions. Pure Python.

    `stats` is the reduction of `_rms_over_pairs_within`: `dx2_sum`,
    `dx2_count`, `dy2_sum`, `dy2_count`. None when there is no pair, or the
    mean is not positive.
    """
    total = float(stats.get("dx2_sum") or 0.0) + float(stats.get("dy2_sum") or 0.0)
    n = float(stats.get("dx2_count") or 0.0) + float(stats.get("dy2_count") or 0.0)
    if n <= 0 or total <= 0:
        return None
    return total / n


def _zscore_per_band(
    image: ee.Image,
    roi: ee.Geometry,
    scale: int,
    *,
    within: ee.Image | None = None,
) -> ee.Image:
    """Z-score normalize each band of `image` independently over `roi`.

    Computes mean and stddev per band over the ROI, then subtracts the mean
    and divides by stddev (clamped at 1e-6 to avoid division-by-zero on
    constant bands).

    `within`, a 0/1 image (kept land), takes the mean and stddev over the
    pixels where it is 1 only. The image returned is not masked by it.
    """
    sample = image if within is None else image.updateMask(within)
    stats = sample.reduceRegion(
        reducer=ee.Reducer.mean().combine(ee.Reducer.stdDev(), sharedInputs=True),
        geometry=roi,
        scale=scale,
        maxPixels=1_000_000_000,
        bestEffort=True,
    )
    # Build the z-scored image band-by-band on the Python side; the band list
    # is small and fixed, so this is cleaner than server-side iteration.
    band_names = safe_get_info(image.bandNames(), context="z-score band names")
    normalized_bands: list[ee.Image] = []
    for b in band_names:
        mean = ee.Number(stats.get(f"{b}_mean"))
        std = ee.Number(stats.get(f"{b}_stdDev"))
        safe_std = std.max(1e-6)
        normalized = image.select(b).subtract(mean).divide(safe_std).rename(b)
        normalized_bands.append(normalized)
    return ee.Image.cat(normalized_bands)


def _analysis_grid(roi: ee.Geometry, scale: int) -> ee.Projection:
    """The pixel grid SNIC's outputs should live on: the ROI's UTM zone.

    Constructed from the ROI rather than inherited from the first input band.
    Inheriting looked safer -- take the grid the data is already on -- but the
    first band is `B4_median` off the S2 composite, which `data_load` does not
    cache, so it reports EE's WGS84 default and `atScale(10)` turns that into a
    geographic grid with 8.8 x 10 m pixels at this latitude. See
    `fmu.utils.grid` for why that matters and why UTM is the answer.
    """
    return analysis_grid(roi, scale, context="segmentation output grid")

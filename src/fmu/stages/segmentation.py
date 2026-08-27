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
  - canopy_height_std           3x3 roughness (canopy completeness: separates a
                                smooth plantation-like canopy from a gap-rich
                                natural one at the same mean height)
  - ndvi_amplitude_annual       seasonal swing (the deciduous/evergreen axis;
                                without it SNIC sees no phenology at all, since
                                it runs on a multi-year median composite)
  - vv_minus_vh_median          S1 cross-pol contrast (sensor-independent)

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
that second step `compactness` silently means something different in a 6-band
arm than in a 64-band embedding arm.

Boundaries are NOT held constant across arms: each pipeline segments on its own
feature space and the resulting stand maps are compared directly.

Outputs:
  - snic_clusters: integer cluster ID per pixel
  - snic_means:    per-cluster mean of each input band
"""

from __future__ import annotations

import ee

from fmu.config import Config
from fmu.stages.base import PipelineContext, Stage, StageResult, register_stage
from fmu.utils.gee import safe_call, safe_get_info
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

    def validate(self, ctx: PipelineContext, config: Config) -> None:
        needed = {"roi"} | config.segmentation.input_sources()
        missing = needed - ctx.keys()
        if missing:
            raise KeyError(
                f"{self.name}: missing required context inputs: {sorted(missing)}. "
                f"Context has: {sorted(ctx.keys())}. These are required because "
                f"segmentation.input_bands references them -- either add the "
                f"producing stage to the run, or change input_bands."
            )

    @safe_call("running SNIC segmentation")
    def run(self, ctx: PipelineContext, config: Config) -> StageResult:
        roi = ctx.get("roi")
        params = config.segmentation
        scale = config.export.analysis_scale_m

        # Build the input stack from config, in the declared order.
        input_band_names, raw_stack = _resolve_input_stack(ctx, config)

        # Z-score per band over the ROI to put all bands on a comparable scale.
        # Without this, B4_median (0-3000) would dominate vs canopy_height (0-30).
        if params.normalize_inputs:
            snic_input = _zscore_per_band(raw_stack, roi, scale)
        else:
            snic_input = raw_stack

        # Make `compactness` mean the same thing regardless of how many (and how
        # correlated) the input bands are. SNIC trades a colour distance against
        # a spatial-compactness term; summed squared colour distance grows with
        # the number of *effective* axes, so a 64-band embedding stack would
        # otherwise have a far weaker spatial term than a 6-band one at the same
        # `compactness`. Dividing by sqrt(n_bands) would assume the bands are
        # independent -- for an embedding they are not, and it over-corrects.
        # The empirical RMS distance between 4-adjacent pixels handles band count
        # and correlation together.
        distance_scale: float | None = None
        if params.normalize_distance_scale:
            distance_scale = _rms_adjacent_distance(snic_input, roi, scale)
            snic_input = snic_input.divide(distance_scale)
            log.info(
                "  distance normaliser (RMS 4-neighbour feature distance): %.6f",
                distance_scale,
            )

        # Run SNIC
        snic_result = ee.Algorithms.Image.Segmentation.SNIC(
            image=snic_input,
            size=params.size,
            compactness=params.compactness,
            connectivity=params.connectivity,
            neighborhoodSize=params.neighborhood_size,
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
        grid = _analysis_grid(raw_stack, scale)
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


def _rms_adjacent_distance(image: ee.Image, roi: ee.Geometry, scale: int) -> float:
    """RMS feature distance between 4-adjacent pixels, over all bands.

    For each pixel and each of the two unique 4-neighbour directions, the
    squared distance is the sum over bands of the squared per-band difference.
    This returns sqrt(mean of that over the ROI and over both directions).

    Dividing the stack by this makes SNIC's summed squared colour distance
    invariant to band count *and* to correlation between bands, so `compactness`
    is comparable across arms with different feature spaces. Adjacency is
    defined at `scale` (the analysis scale) via the reduction, so both arms must
    use the same scale for the numbers to mean the same thing.
    """
    kx = ee.Kernel.fixed(2, 1, [[-1, 1]])
    ky = ee.Kernel.fixed(1, 2, [[-1], [1]])
    dx2 = image.convolve(kx).pow(2).reduce(ee.Reducer.sum())
    dy2 = image.convolve(ky).pow(2).reduce(ee.Reducer.sum())
    mean_sq = safe_get_info(
        dx2.add(dy2).divide(2).rename("d2").reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=roi,
            scale=scale,
            maxPixels=1e9,
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


def _zscore_per_band(image: ee.Image, roi: ee.Geometry, scale: int) -> ee.Image:
    """Z-score normalize each band of `image` independently over `roi`.

    Computes mean and stddev per band over the ROI, then subtracts the mean
    and divides by stddev (clamped at 1e-6 to avoid division-by-zero on
    constant bands).
    """
    stats = image.reduceRegion(
        reducer=ee.Reducer.mean().combine(ee.Reducer.stdDev(), sharedInputs=True),
        geometry=roi,
        scale=scale,
        maxPixels=1e9,
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


def _analysis_grid(raw_stack: ee.Image, scale: int) -> ee.Projection:
    """The pixel grid SNIC's outputs should live on.

    Taken from the first input band rather than constructed, because the CRS
    matters as much as the scale: a 10 m grid in WGS84 is a different raster
    from Sentinel-2's 10 m UTM grid, and only the latter lines up with the
    pixels SNIC actually segmented. Reprojecting the labels onto a foreign CRS
    would resample them -- turning a metadata fix into real corruption.

    `select(0)` because `projection()` is a per-band property and the stack is
    multi-band (64 bands in an embedding arm). All the bands are 10 m native and
    co-registered, so the first is representative.
    """
    return raw_stack.select(0).projection().atScale(scale)

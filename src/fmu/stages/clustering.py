"""Clustering stage. Per-unit feature stack, preprocessing, k-means, then
per-pixel cluster labels.

Under the merge design this stage no longer decides *what a stand is* -- SNIC
plus `merge` produce the stand, and clustering is demoted to attaching a **type
label** to a finished one. The unit it reduces over is therefore
`stand_clusters` when merge ran and `snic_clusters` when it did not; see
`Config.unit_label_key()`, the single definition every downstream stage shares.

Implements DEC-001 (clustering operates on unit means, not pixels), DEC-003
(median/IQR robust scaling), DEC-004 (log-transform right-skewed bands), and the
cyclic-feature decomposition for phase and aspect (sin/cos pair).

Pipeline (server-side throughout):

  1. Build raw feature stack
       - All bands from optical, radar, structure, static features.
       - Drop *_obs_count (metadata), *_residual_variance (fit diagnostic),
         and annual_rainfall (constant in ROI).
       - Auto-detect optical band names (works for both ndvi_* and nirv_*).

  2. Cyclic decomposition
       - Each *_phase_* and aspect band becomes a sin/cos pair. Original dropped.

  3. Per-unit means
       - reduceConnectedComponents with the stand (or superpixel) labels.
       - Every pixel now holds the mean of its unit for each feature.
       - maxSize is the measured widest unit extent (plus margin, capped at
         Config.max_component_pixels), not the cap itself: EE pads every tile
         by maxSize, so memory grows with bands x pad and a wide band stack
         can run out of memory at the cap. See _component_neighbourhood_px.

  4. Habitat filter
       - updateMask(habitat_mask). Non-habitat pixels excluded from
         training and labelling.

  5. Skewness detection (DEC-004)
       - For each band, compute skewness over habitat-masked sample.
       - Mark bands with |skew| > skewness_threshold for log-transform.

  6. Log-transform marked bands
       - log(x - min + 1e-3) so x can include zero/negative values safely.

  7. Robust scaling (DEC-003, method=robust in config)
       - Per band: (x - median) / IQR. Drop bands with IQR near 0 (constant).
       - Median/IQR computed over the habitat-masked sample.

  8. Train k-means
       - ONE row per unit, and every unit -- no pixel sampling. The stack is
         constant within a unit, so a pixel sample drew the same vector once per
         pixel and area-weighted every statistic computed from it: a 10 ha stand
         outweighed a 0.1 ha stand 100 to 1 in the skewness, the median/IQR and
         the fit. That is a property of stand size, not of what a stand is.
       - ee.Clusterer.wekaKMeans(nClusters=k, seed=seed).

  9. Apply k-means to all habitat pixels, producing cluster_labels image (0..k-1).

  10. Attach all preprocessing params + k-means hyperparams as JSON
      string property "clustering_metadata" on cluster_labels image.
      Lets the profiling stage reconstruct what was done.

Outputs:
  - cluster_labels: per-pixel integer cluster ID (0..k-1, masked outside habitat)
  - feature_stack: the preprocessed (cyclic-decomposed, optionally log-transformed,
                   scaled) multi-band feature image. Useful for profiling.
"""

from __future__ import annotations

import json
import math

import ee

from fmu.config import Config
from fmu.stages.base import PipelineContext, Stage, StageResult, register_stage
from fmu.utils.components import assert_components_fit
from fmu.utils.gee import LABEL_BAND, safe_call, safe_get_info
from fmu.utils.logging import get_logger

log = get_logger(__name__)


# Bands to always drop from clustering. Metadata, not feature.
_EXCLUDE_BANDS: frozenset[str] = frozenset(
    {
        # Metadata bands from features_optical
        "ndvi_obs_count",
        "nirv_obs_count",
        # Harmonic fit-quality diagnostic. Exported per-pixel as a diagnostic
        # (deck v3.0, Stage 3) but NOT a clustering feature: clustering on how
        # well the harmonic fit each pixel would split otherwise-identical
        # phenology by noise, not ecology.
        "ndvi_residual_variance",
        "nirv_residual_variance",
        # Constant within the Sanjay Van ROI (CHIRPS 5500m resolution).
        # Kept in features_static for cross-AOI generality; dropped here.
        "annual_rainfall",
    }
)


# Context keys the raw feature stack is assembled from, per feature source.
# `_INVARIANT_INPUTS` are needed no matter the source; validate() adds the
# source-specific keys. (required_inputs stays the invariant subset because it
# is a static class attribute; the conditional check lives in validate().)
#
# The unit key is deliberately NOT invariant: clustering reduces over stands
# when merge ran and over raw superpixels when it did not. See
# `Config.unit_label_key()`, which is the single definition every stage shares.
_INVARIANT_INPUTS: frozenset[str] = frozenset({"roi", "habitat_mask"})
_HANDCRAFTED_INPUTS: frozenset[str] = frozenset(
    {"optical_features", "radar_features", "structure_features", "static_features"}
)
_EMBEDDING_INPUTS: frozenset[str] = frozenset({"embedding_features"})


@register_stage("clustering")
class ClusteringStage(Stage):
    name = "clustering"
    required_inputs = set(_INVARIANT_INPUTS)
    produces = {"cluster_labels", "feature_stack"}
    cacheable_outputs = {"cluster_labels", "feature_stack"}

    def validate(self, ctx: PipelineContext, config: Config) -> None:
        """Require the context keys the configured feature source needs.

        The static `required_inputs` only lists the always-needed keys; the
        feature-source-specific inputs (the four hand-crafted images, or the
        single embedding image) are checked here so an embedding run isn't
        forced to produce the hand-crafted stack it never uses. The unit key
        (`stand_clusters` or `snic_clusters`) is checked here for the same
        reason -- which one exists depends on whether merge ran.
        """
        source = config.clustering.feature_source
        extra = _EMBEDDING_INPUTS if source == "embedding" else _HANDCRAFTED_INPUTS
        needed = _INVARIANT_INPUTS | extra | {config.unit_label_key()}
        missing = needed - ctx.keys()
        if missing:
            raise KeyError(
                f"{self.name} (feature_source={source!r}): missing required "
                f"context inputs: {sorted(missing)}. Context has: {sorted(ctx.keys())}"
            )

    @safe_call("running k-means clustering")
    def run(self, ctx: PipelineContext, config: Config) -> StageResult:
        roi = ctx.get("roi")
        # Stands when merge ran, raw superpixels when it did not. Under the
        # merge design a stand is the unit being labelled; before it, a
        # superpixel was standing in for one.
        unit_key = config.unit_label_key()
        unit_labels: ee.Image = ctx.get(unit_key)
        habitat_mask: ee.Image = ctx.get("habitat_mask")
        params = config.clustering
        scale = config.export.analysis_scale_m

        # 1. Build raw feature stack (hand-crafted multi-sensor stack, or a
        #    single pretrained embedding image — the rest of the stage is
        #    identical either way).
        if params.feature_source == "embedding":
            raw_stack = _build_embedding_feature_stack(
                embedding=ctx.get("embedding_features")
            )
        else:
            raw_stack = _build_raw_feature_stack(
                optical=ctx.get("optical_features"),
                radar=ctx.get("radar_features"),
                structure=ctx.get("structure_features"),
                static=ctx.get("static_features"),
            )
        raw_band_names = safe_get_info(
            raw_stack.bandNames(), context="raw clustering bands"
        )
        log.info("  raw feature stack: %d bands", len(raw_band_names))

        # 2. Cyclic decomposition
        decomposed_stack, decomposition_log = _decompose_cyclic_bands(raw_stack)
        log.info(
            "  cyclic decomposition: %d band(s) replaced with sin/cos pairs (%s)",
            len(decomposition_log),
            ", ".join(decomposition_log) if decomposition_log else "none",
        )

        # 3. Per-unit means (per stand, or per superpixel if merge is off).
        # maxSize is derived, not configured (see Config.max_component_pixels),
        # and checked against the labels in hand first -- the argument masks any
        # component larger than it, so getting it wrong deletes stands rather
        # than raising.
        #
        # The cap still does that guarding. The argument actually passed is the
        # measured unit extent, because EE pads every tile by maxSize and a wide
        # band stack does not fit in memory at the cap. Every unit is still
        # aggregated whole, so the means cover the same pixels as at the cap;
        # why, and under what precondition, is in _component_neighbourhood_px.
        max_component_px = config.max_component_pixels()
        component_stats = assert_components_fit(
            unit_labels,
            roi,
            scale,
            max_component_px,
            context=f"clustering per-{unit_key} means",
        )
        # Failure mode, stated so nobody mistakes it for a silent one: an AOI
        # with an extremely elongated stand pushes the neighbourhood towards the
        # cap, and a wide band stack could then run out of memory again. That
        # run fails loudly, exactly as it did before this measurement existed.
        # A label reused across disjoint places inflates the measured extent the
        # same way and is warned about. widest_unit_extent_px in the stage
        # metadata is the diagnostic.
        neighbourhood_widest_px, rcc_neighbourhood_px = _component_neighbourhood_px(
            unit_labels,
            decomposed_stack,
            roi,
            scale,
            cap=max_component_px,
            n_labels=component_stats["n_components"],
            largest_component_px=component_stats["largest_component_px"],
            context=f"clustering per-{unit_key} means",
        )
        superpixel_stack = _compute_superpixel_means(
            decomposed_stack, unit_labels, rcc_neighbourhood_px
        )

        # 4. Habitat filter
        habitat_masked = superpixel_stack.updateMask(habitat_mask)

        # One row per unit, and every unit -- not a pixel sample.
        #
        # The feature stack is constant within a unit (it *is* the per-unit
        # mean), so a pixel sample was drawing the same vector once per pixel:
        # a 10 ha stand contributed 100x the rows of a 0.1 ha one. Every
        # statistic downstream -- skewness, median, IQR, and the k-means fit
        # itself -- was therefore area-weighted, which is a property of stand
        # size, not of what a stand is. With ~269 stands there is no reason to
        # sample at all: fit on all of them.
        #
        # This also retires the "10,000 superpixels" confusion in the docs. The
        # old `n_training_samples: 10000` was 10,000 *pixels*, roughly 37 per
        # superpixel, never 10,000 superpixels.
        candidate_bands = safe_get_info(
            habitat_masked.bandNames(), context="post-decomposition bands"
        )
        preprocessing_sample = _sample_one_point_per_unit(
            habitat_masked,
            unit_labels,
            roi,
            scale,
            seed=params.seed,
            context=f"preprocessing stats per {unit_key}",
        )

        # 5. Skewness detection (sample-based)
        skewed_bands = _identify_skewed_bands(
            preprocessing_sample,
            candidate_bands,
            threshold=params.skewness_threshold,
        )
        log.info(
            "  log-transform: %d band(s) above |skew|=%s (%s)",
            len(skewed_bands),
            params.skewness_threshold,
            ", ".join(skewed_bands) if skewed_bands else "none",
        )

        # 6. Apply log transform to skewed bands (offsets from sample minima)
        transformed_stack, log_offsets = _apply_log_transform(
            habitat_masked, skewed_bands, preprocessing_sample
        )

        # Re-sample after log transform. NOT a redundant call: log
        # transformation changes the distribution of the affected bands,
        # so percentiles (median/IQR) computed from preprocessing_sample
        # would describe the WRONG distribution for scaling. Same seed and
        # same one-point-per-unit stratification, so the same units are
        # represented -- only the values differ, by construction.
        post_log_sample = _sample_one_point_per_unit(
            transformed_stack,
            unit_labels,
            roi,
            scale,
            seed=params.seed,
            context=f"scaling stats per {unit_key}",
        )

        # 7. Robust scaling (sample-based). drop constant bands (IQR ~ 0).
        method = config.normalization.method
        scaled_stack, scaling_params, active_bands = _apply_scaling(
            transformed_stack, post_log_sample, candidate_bands, method=method
        )
        dropped_bands = sorted(set(candidate_bands) - set(active_bands))
        if dropped_bands:
            log.info(
                "  dropped %d constant band(s) (zero spread): %s",
                len(dropped_bands),
                ", ".join(dropped_bands),
            )
        log.info(
            "  final feature stack: %d active bands, normalization=%s",
            len(active_bands),
            method,
        )

        # 8-9. Train k-means on every unit, then apply to all habitat pixels.
        cluster_labels, unit_coverage = _train_and_apply_kmeans(
            scaled_stack=scaled_stack,
            active_bands=active_bands,
            unit_labels=unit_labels,
            habitat_mask=habitat_mask,
            roi=roi,
            scale=scale,
            k=params.k,
            seed=params.seed,
            unit_key=unit_key,
        )

        # 10. Attach preprocessing metadata
        clustering_metadata = {
            "k": params.k,
            "seed": params.seed,
            "feature_source": params.feature_source,
            # Every unit, not a pixel sample: see _sample_one_point_per_unit.
            # The full breakdown, not just the row count: a unit missing from
            # the fit had no say in the cluster definitions it is judged by, and
            # the two reasons for missing (non-habitat, no band data) mean
            # different things. See _train_and_apply_kmeans.
            **unit_coverage,
            "training_unit_key": unit_key,
            "normalization_method": method,
            "skewness_threshold": params.skewness_threshold,
            "log_transformed_bands": skewed_bands,
            "log_offsets": log_offsets,  # per-band offsets used in log
            "scaling": scaling_params,  # {band: {center, spread}}
            "active_bands": active_bands,
            "dropped_constant_bands": dropped_bands,
            "raw_band_names": raw_band_names,
            "cyclic_decomposition_log": decomposition_log,
        }
        metadata_json = json.dumps(clustering_metadata, sort_keys=True)
        # ee.Image(...) is a cast: Element.set() returns Element in the stubs, and
        # every consumer of this variable needs an Image.
        cluster_labels = ee.Image(cluster_labels.set("clustering_metadata", metadata_json))

        return StageResult(
            outputs={
                "cluster_labels": cluster_labels.clip(roi),
                "feature_stack": scaled_stack.clip(roi),
            },
            metadata={
                "k": params.k,
                "feature_source": params.feature_source,
                "n_active_bands": len(active_bands),
                "n_log_transformed": len(skewed_bands),
                "n_dropped_constant": len(dropped_bands),
                "normalization_method": method,
                # Which unit was labelled. Under the merge design this is a
                # stand; without merge it is a raw superpixel, and the two are
                # not interchangeable when reading a silhouette or a profile.
                "unit_key": unit_key,
                # Recorded even when the check passes: the headroom is the early
                # warning that a merge.max_area_ha change is about to start
                # masking components rather than merely resizing them.
                **component_stats,
                # Recorded so the manifest shows the neighbourhood actually used,
                # and how close the widest stand is to it. Deliberately kept out
                # of clustering_metadata, which stays key-for-key what it was.
                "rcc_neighbourhood_px": rcc_neighbourhood_px,
                "widest_unit_extent_px": neighbourhood_widest_px,
            },
        )


# ---------------------------------------------------------------------
# Step helpers. Each focused, each tested.
# ---------------------------------------------------------------------


def _build_raw_feature_stack(
    *,
    optical: ee.Image,
    radar: ee.Image,
    structure: ee.Image,
    static: ee.Image,
) -> ee.Image:
    """Stack all feature bands, auto-detect names, drop excluded bands.

    Auto-detection: we don't hardcode ndvi_* vs nirv_*. Whatever bands the
    optical_features asset contains are included (minus the excluded set).
    Same for the others.
    """
    combined = ee.Image.cat([optical, radar, structure, static])
    all_bands = safe_get_info(combined.bandNames(), context="combined feature bands")
    kept = [b for b in all_bands if b not in _EXCLUDE_BANDS]
    return combined.select(kept)


def _build_embedding_feature_stack(*, embedding: ee.Image) -> ee.Image:
    """Raw feature stack for the embedding arm: the embedding image itself.

    Unlike the hand-crafted stack there is nothing to concatenate or exclude —
    every embedding dimension is a feature (the band selection already happened
    in the features_embedding stage). Returned as-is so the rest of the
    clustering pipeline (superpixel means, skew/log, robust scaling, k-means)
    runs unchanged on the embedding bands.
    """
    return embedding


def _decompose_cyclic_bands(image: ee.Image) -> tuple[ee.Image, list[str]]:
    """Replace each cyclic band (phase / aspect) with sin and cos components.

    Cyclic features (degrees or radians) confuse Euclidean distance because
    0 and 2π are maximally far apart in linear space despite being identical
    angles. sin/cos decomposition removes that artifact.

    Returns the new image plus a list of band names that were decomposed.
    """
    band_names = safe_get_info(image.bandNames(), context="bands for cyclic check")
    cyclic_bands = [b for b in band_names if "_phase_" in b or b == "aspect"]

    if not cyclic_bands:
        return image, []

    # Phase bands are in radians (atan2 output ∈ [-π, π]).
    # Aspect is in degrees [0, 360] from ee.Terrain.products; convert first.
    new_bands: list[ee.Image] = []
    for cb in cyclic_bands:
        original = image.select(cb)
        if cb == "aspect":  # noqa: SIM108  (keep for the radians conversion comment)
            # Aspect is in degrees ∈ [0, 360]; convert to radians first.
            radians = original.multiply(math.pi / 180.0)
        else:
            # Phase bands from atan2 are already in radians ∈ [-π, π].
            radians = original
        sin_band = radians.sin().rename(f"{cb}_sin")
        cos_band = radians.cos().rename(f"{cb}_cos")
        new_bands.extend([sin_band, cos_band])

    kept_bands = [b for b in band_names if b not in cyclic_bands]
    return image.select(kept_bands).addBands(ee.Image.cat(new_bands)), cyclic_bands


# reduceConnectedComponents masks an object only when it is strictly LARGER than
# maxSize in either dimension, so the widest extent itself would already fit in
# the grid it was measured in. The margin is not for that equality case. It
# absorbs the difference between the grids that were measured and a grid
# neither saw exactly (an export aligns to the same CRS and scale but not
# necessarily the same pixel origin, which can move an extent by about a pixel).
_RCC_EXTENT_MARGIN = 1.2
# Flat pad on top of the relative margin: for a small widest extent, 20% is under
# a pixel and would not cover the ~1 px sub-pixel / ROI-edge alignment error.
_RCC_EXTENT_PAD_PX = 2
# A connected object's extent never exceeds its pixel count, so a measured extent
# more than this many times the largest label's count cannot be one object. It
# is a label reused across disjoint places, or a broken measurement. 2x leaves
# room for the ~1/cos(lat) width difference between the two measured grids.
_DISJOINT_LABEL_EXTENT_RATIO = 2


def _neighbourhood_from_groups(
    groups: list[dict[str, list[float]]] | None, *, cap: int
) -> tuple[int, int]:
    """Neighbourhood (px) for reduceConnectedComponents from per-label
    pixel-coordinate extents.

    Returns (widest_extent_px, neighbourhood_px).

    Each group carries the min and max pixel coordinate (x, y) of one label.
    The +1 turns a coordinate span into a pixel extent: a label occupying
    columns 10..137 is 128 px wide, not 127. The span is rounded before the +1
    because pixel coordinates come back as floats, and a 127-px span that
    arrives as 126.9999999 must not truncate to a 127-px extent. Truncating
    under-measures, the one direction this must not err in.

    neighbourhood = ceil(widest * _RCC_EXTENT_MARGIN) + _RCC_EXTENT_PAD_PX, never
    above the cap. That is always strictly greater than widest, so every
    measured label fits. Because of the cap, this can only narrow the
    neighbourhood relative to passing the cap directly. With no groups at all it
    returns the cap, which is exactly the old behaviour. The caller decides
    whether an empty result is legitimate (no labels) or a failure.

    Pure arithmetic, no Earth Engine: kept separate so the fast test tier pins
    it.
    """
    widest = 0
    for g in groups or []:
        span = max(g["max"][0] - g["min"][0], g["max"][1] - g["min"][1])
        widest = max(widest, int(round(span)) + 1)
    if widest == 0:
        return 0, cap
    return widest, min(
        cap, math.ceil(widest * _RCC_EXTENT_MARGIN) + _RCC_EXTENT_PAD_PX
    )


def _component_neighbourhood_px(
    unit_labels: ee.Image,
    feature_image: ee.Image,
    roi: ee.Geometry,
    scale: int,
    *,
    cap: int,
    n_labels: int,
    largest_component_px: int,
    context: str,
) -> tuple[int, int]:
    """Measure the widest unit extent and derive the maxSize to pass.

    Returns (widest_extent_px, neighbourhood_px); see _neighbourhood_from_groups.
    `n_labels` and `largest_component_px` are assert_components_fit's
    measurements of the same labels. They decide whether an empty measurement
    is legitimate and whether the extent is plausible for one object.

    Why this exists. reduceConnectedComponents' maxSize is an EXTENT in pixels
    ("objects larger than maxSize in either the horizontal or vertical
    dimension will be masked"), and EE pads every tile by it. tileScale does
    not shrink the pad. Config.max_component_pixels derives the cap as a pixel
    COUNT: 1200 at 10 ha / 10 m. Passed straight through, each 256 px tile was
    evaluated over about 2656^2 px per band, so memory scales with bands x pad,
    and a wide enough band stack exceeds the user memory limit.

    Why every unit is still aggregated whole. The argument does not rest on
    assert_components_fit. That bounds a pixel COUNT in the label grid, while
    the reduction runs in the feature image's first-band grid (EPSG:4326 for
    the feature sources in use), where the same stand is ~1/cos(lat) wider. A
    count bound in one grid does not bound an extent in the other. Instead:

      - When the cap does not bind, neighbourhood > widest, and widest is
        measured in the grid the reduction evaluates in. So no label exceeds
        maxSize and every label is aggregated whole. The old call, with a
        larger maxSize, also aggregated every label whole, because a label wider
        than the cap would be wider than widest. Same pixels in each mean.
      - When the cap binds, the argument passed IS the cap, so behaviour is
        exactly what it was before this function existed, including any
        pre-existing edge case at the cap.

    Values therefore agree up to floating-point summation order, not bit for
    bit: EE may sum a unit's pixels in a different order under a different
    tiling. Measured on two hand-crafted configs, training rows differed by at
    most ~2e-13 and scaling parameters by at most ~2.4e-14, and cluster labels
    were pixel-identical over the whole ROI. Do not expect byte-identical
    metadata JSON.

    Precondition. This holds when the lazy outputs are evaluated at
    analysis_scale_m in the measured grids. That is true of today's pipeline:
    the cache and Drive exports pass `scale` with no `crs`, so they evaluate in
    the image's first-band CRS at that scale, and profiling/metrics read either
    cached assets or the same lazy graph at the same scale. An evaluation in a
    different CRS, or at a coarser scale, is outside the argument. The
    alignment-only difference of an export (same CRS and scale, possibly a
    different origin) is what _RCC_EXTENT_MARGIN is for.

    What is measured, and where:
      - per LABEL, not per connected component, so a stand split into parts is
        bounded by the box around all of them. That is the conservative
        direction, but a label reused far apart inflates the extent. When that
        pushes the neighbourhood up to the cap, a WARNING says so.
      - over the ROI: labels are clipped to it upstream, so this sees every
        labelled pixel.
      - in two grids: the feature image's first-band projection and the labels'
        own grid; the larger is used. reduceConnectedComponents' output bands
        keep the input's band projections, so the reduced stack's band-0 grid
        is the feature band-0 grid. This was checked live: identical projection
        and identical widest extent on an embedding and a hand-crafted config.
      - no bestEffort: a downsampled grid would under-measure extents, the one
        direction this must not err in.

    Raises:
        RuntimeError: a measurement came back without groups although
            assert_components_fit found labels in the ROI. Falling back to the
            cap there would silently reintroduce the memory failure this exists
            to prevent (ENG-012).
    """
    all_groups: list[dict[str, list[float]]] = []
    for grid_name, proj in (
        ("feature band-0", feature_image.select([0]).projection().atScale(scale)),
        ("label", unit_labels.select([0]).projection().atScale(scale)),
    ):
        info = safe_get_info(
            ee.Image.pixelCoordinates(proj)
            .addBands(unit_labels.select([0]).rename(LABEL_BAND))
            .reduceRegion(
                reducer=ee.Reducer.minMax()
                .repeat(2)
                .group(groupField=2, groupName=LABEL_BAND),
                geometry=roi,
                crs=proj,
                maxPixels=1_000_000_000,
            ),
            context=f"{context} unit extents",
        )
        groups = (info or {}).get("groups")
        if not groups and n_labels > 0:
            raise RuntimeError(
                f"{context}: the unit-extent measurement in the {grid_name} grid "
                f"returned no groups ({info!r}), but the label histogram found "
                f"{n_labels} label(s) in the ROI. Refusing to fall back to the "
                f"cap ({cap} px): that is the neighbourhood that runs out of "
                f"memory on wide band stacks, and a measurement that silently "
                f"sees nothing is a bug to find, not a default to use."
            )
        all_groups.extend(groups or [])

    widest, neighbourhood = _neighbourhood_from_groups(all_groups, cap=cap)
    log.info(
        "  %s: widest unit %d px, reduceConnectedComponents neighbourhood %d px (cap %d)",
        context,
        widest,
        neighbourhood,
        cap,
    )
    if (
        neighbourhood == cap
        and widest > _DISJOINT_LABEL_EXTENT_RATIO * largest_component_px
    ):
        log.warning(
            "  %s: widest label extent %d px is more than %dx the largest label's "
            "pixel count (%d px), which no single connected object can be: a "
            "label is reused across disjoint places and has inflated the extent. "
            "The neighbourhood fell back to the cap (%d px), which is correct "
            "but may run out of memory on a wide band stack.",
            context,
            widest,
            _DISJOINT_LABEL_EXTENT_RATIO,
            largest_component_px,
            cap,
        )
    return widest, neighbourhood


def _compute_superpixel_means(
    feature_image: ee.Image, unit_labels: ee.Image, max_size: int
) -> ee.Image:
    """Replace each feature value with its mean over the containing unit.

    Adds the unit labels as a label band, then calls reduceConnectedComponents
    (the standard SNIC-aggregate pattern in GEE). Output has the same bands
    as the input but pixel values are constant within each unit.
    Note: reduceConnectedComponents preserves input band names, no
    _mean suffix is added (unlike SNIC's mean output bands).

    The unit is a merged stand when merge ran and a raw superpixel otherwise;
    the reduction is identical either way, which is why this took no change
    beyond the label image it is handed.

    `max_size` is the reduceConnectedComponents neighbourhood; ClusteringStage
    passes the measured unit extent (see _component_neighbourhood_px), not the
    count-derived cap.
    """
    band_names = feature_image.bandNames()
    # Was "snic_label", which is now the wrong word as well as a second
    # convention: the unit here is a merged stand whenever merge ran.
    label_band = LABEL_BAND

    with_labels = feature_image.addBands(unit_labels.rename(label_band))
    reduced = with_labels.reduceConnectedComponents(
        reducer=ee.Reducer.mean(),
        labelBand=label_band,
        maxSize=max_size,
    )
    # Drop the label band from the result; keep only the feature bands
    # (which retain their original names).
    return reduced.select(band_names)


def _identify_skewed_bands(
    sample: ee.FeatureCollection,
    band_names: list[str],
    threshold: float,
) -> list[str]:
    """Return bands whose |skewness| over the sample exceeds threshold.

    Operates on a FeatureCollection sample (typically 10k features) rather
    than the full image to stay within GEE's user memory limit. Per-band
    skewness uses `reduceColumns`: one server call per band, small payload.
    Skewness estimates are stable with n=10k.
    """
    skewed: list[str] = []
    for band in band_names:
        result = safe_get_info(
            sample.reduceColumns(
                reducer=ee.Reducer.skew(),
                selectors=[band],
            ),
            context=f"skew of {band}",
        )
        # reduceColumns with a single-output reducer returns {"skew": value}
        skew_val = result.get("skew") if result else None
        if skew_val is not None and abs(skew_val) > threshold:
            skewed.append(band)
    return skewed


def _apply_log_transform(
    image: ee.Image,
    skewed_bands: list[str],
    sample: ee.FeatureCollection,
) -> tuple[ee.Image, dict[str, float]]:
    """Apply log(x - min + epsilon) to each skewed band of the image.

    The offset min comes from the same sample used for skew detection
    (avoids re-scanning the full image just for one statistic per band).
    epsilon=1e-3 keeps log() defined exactly at the sample minimum; if
    a real pixel value is below the sample min, the log is still defined
    (just produces a small negative number).

    Returns the transformed image plus a dict of per-band log offsets.
    """
    if not skewed_bands:
        return image, {}

    epsilon = 1e-3
    log_offsets: dict[str, float] = {}
    transformed_bands: list[ee.Image] = []

    for band in skewed_bands:
        result = safe_get_info(
            sample.reduceColumns(
                reducer=ee.Reducer.min(),
                selectors=[band],
            ),
            context=f"min of {band}",
        )
        band_min = result.get("min") if result else None
        if band_min is None:
            # Shouldn't happen on real data; skip if so.
            transformed_bands.append(image.select(band))
            continue
        offset = -float(band_min) + epsilon  # shift so all values are > 0
        log_offsets[band] = offset
        shifted = image.select(band).add(offset)
        log_transformed = shifted.log().rename(band)
        transformed_bands.append(log_transformed)

    untouched_bands = [
        b
        for b in safe_get_info(image.bandNames(), context="bands")
        if b not in skewed_bands
    ]
    return image.select(untouched_bands).addBands(ee.Image.cat(transformed_bands)), log_offsets


def _apply_scaling(
    image: ee.Image,
    sample: ee.FeatureCollection,
    band_names: list[str],
    *,
    method: str,
) -> tuple[ee.Image, dict[str, dict[str, float]], list[str]]:
    """Scale each band of the image: (x - center) / spread.

    method="robust" (DEC-003): center=median, spread=IQR.
    method="zscore":           center=mean,   spread=stdDev.

    Scaling parameters are derived from the sample (FeatureCollection),
    not the full image. Sidesteps GEE memory limits on percentile reducers.

    Drops bands with spread ≤ epsilon (constant features can't be scaled
    and contribute nothing to clustering).
    """
    scaling_params: dict[str, dict[str, float]] = {}

    if method == "robust":
        for band in band_names:
            result = safe_get_info(
                sample.reduceColumns(
                    reducer=ee.Reducer.percentile([25, 50, 75]),
                    selectors=[band],
                ),
                context=f"p25/p50/p75 of {band}",
            )
            if result is None:
                continue
            p25 = result.get("p25")
            p50 = result.get("p50")
            p75 = result.get("p75")
            if p25 is None or p50 is None or p75 is None:
                continue
            scaling_params[band] = {
                "center": float(p50),
                "spread": float(p75) - float(p25),  # IQR
            }
    elif method == "zscore":
        for band in band_names:
            result = safe_get_info(
                sample.reduceColumns(
                    reducer=ee.Reducer.mean().combine(
                        ee.Reducer.stdDev(), sharedInputs=True
                    ),
                    selectors=[band],
                ),
                context=f"mean/stdDev of {band}",
            )
            if result is None:
                continue
            mean = result.get("mean")
            std = result.get("stdDev")
            if mean is None or std is None:
                continue
            scaling_params[band] = {"center": float(mean), "spread": float(std)}
    else:
        raise ValueError(f"Unknown normalization method: {method!r}")

    # Apply per band; drop those with spread ≤ epsilon (constant features).
    epsilon = 1e-9
    active_bands: list[str] = []
    scaled_bands: list[ee.Image] = []
    for band in band_names:
        sp = scaling_params.get(band)
        if sp is None or sp["spread"] <= epsilon:
            continue
        scaled = (
            image.select(band)
            .subtract(sp["center"])
            .divide(sp["spread"])
            .rename(band)
        )
        active_bands.append(band)
        scaled_bands.append(scaled)

    if not scaled_bands:
        raise ValueError(
            "All feature bands have zero spread; nothing left to cluster on."
        )

    return ee.Image.cat(scaled_bands), scaling_params, active_bands


def _sample_one_point_per_unit(
    image: ee.Image,
    unit_labels: ee.Image,
    roi: ee.Geometry,
    scale: int,
    *,
    seed: int,
    context: str,
) -> ee.FeatureCollection:
    """One feature per unit, carrying that unit's feature vector.

    The image handed in is constant within a unit (it is the per-unit mean), so
    a single pixel per unit reproduces the unit's vector exactly -- this is not
    an approximation of a larger sample, it is the complete set of distinct rows
    with the duplicates removed.

    Removing them matters. A pixel sample draws each unit once per pixel, so a
    10 ha stand outweighs a 0.1 ha stand 100 to 1 in every statistic computed
    from it -- skewness, median, IQR, and the k-means fit. That weighting is a
    property of stand size, not of what a stand is, and nothing downstream
    declares it.

    `stratifiedSample` with `numPoints=1` and no `classValues` takes one point
    from every class present, so no unit is dropped for being small.
    """
    label_band = LABEL_BAND
    stacked = image.addBands(unit_labels.rename(label_band))
    return stacked.stratifiedSample(
        numPoints=1,
        classBand=label_band,
        region=roi,
        scale=scale,
        seed=seed,
        dropNulls=True,
        geometries=False,
    )


def _train_and_apply_kmeans(
    *,
    scaled_stack: ee.Image,
    active_bands: list[str],
    unit_labels: ee.Image,
    habitat_mask: ee.Image,
    roi: ee.Geometry,
    scale: int,
    k: int,
    seed: int,
    unit_key: str,
) -> tuple[ee.Image, dict[str, int]]:
    """Train wekaKMeans on every unit, apply to the full habitat-masked stack.

    Returns the label image and the number of units actually fitted on, which
    goes into the manifest: k-means over 269 stands and k-means over 10,000
    pixels drawn from those stands are different fits, and the record has to say
    which one produced the labels.
    """
    # Sample only within habitat. Non-habitat pixels are masked out.
    training_input = scaled_stack.updateMask(habitat_mask)
    training_sample = _sample_one_point_per_unit(
        training_input,
        unit_labels,
        roi,
        scale,
        seed=seed,
        context=f"k-means training rows per {unit_key}",
    )

    n_units = int(
        safe_get_info(training_sample.size(), context="k-means training row count")
    )

    # How many units *should* have contributed, and why the rest did not.
    #
    # The fit defines what each cluster is, so a unit missing from it had no say
    # in the definition it will be judged by. Reporting only the row count hid
    # that: a run showed "289 (one per stand_clusters)" against a merge that had
    # just produced 327 stands, and nothing connected the two numbers.
    #
    # Two different exclusions, with different meanings:
    #   - outside the habitat mask: correct, and not a loss. A non-forest unit
    #     should not be typed as forest.
    #   - inside habitat but dropped by `dropNulls`: a band has no data over it.
    #     That is a *non-random* exclusion -- it tracks input coverage, not
    #     forest character -- and since `cluster()` masks wherever an input band
    #     is masked, those units are missing from `cluster_labels` too. They
    #     become holes in the map, not mistyped stands.
    n_total = _count_units(unit_labels, roi, scale, context=f"{unit_key} in ROI")
    n_in_habitat = _count_units(
        unit_labels.updateMask(habitat_mask),
        roi,
        scale,
        context=f"{unit_key} in habitat",
    )
    n_non_habitat = max(n_total - n_in_habitat, 0)
    n_null_dropped = max(n_in_habitat - n_units, 0)

    log.info(
        "  k-means training rows: %d of %d %s (%d outside habitat, %d dropped "
        "for missing band data)",
        n_units,
        n_total,
        unit_key,
        n_non_habitat,
        n_null_dropped,
    )
    if n_null_dropped:
        log.warning(
            "  %d %s unit(s) sit inside the habitat mask but contributed no "
            "training row: at least one of the %d active bands has no data over "
            "them, so dropNulls removed them. This exclusion follows input "
            "coverage rather than forest character, and the same masking leaves "
            "them unlabelled in cluster_labels -- they are holes in the map, not "
            "mistyped units.",
            n_null_dropped,
            unit_key,
            len(active_bands),
        )

    if n_units < k:
        raise ValueError(
            f"clustering: only {n_units} {unit_key} unit(s) available to fit "
            f"k={k} clusters on. Either the merge collapsed the ROI too far "
            f"(check merge.criteria and the threshold_calibration in the merge "
            f"stage metadata) or the habitat mask leaves too little standing."
        )

    # wekaKMeans: init=1 is k-means++ (better init than random).
    clusterer = ee.Clusterer.wekaKMeans(
        nClusters=k,
        init=1,
        seed=seed,
    ).train(features=training_sample, inputProperties=active_bands)

    coverage = {
        "n_training_units": n_units,
        "n_units_total": n_total,
        "n_units_in_habitat": n_in_habitat,
        "n_units_outside_habitat": n_non_habitat,
        "n_units_dropped_null_band": n_null_dropped,
    }
    return training_input.cluster(clusterer).rename("cluster_id"), coverage


def _count_units(
    labels: ee.Image, roi: ee.Geometry, scale: int, *, context: str
) -> int:
    """How many distinct unit labels are present in `labels` over `roi`.

    A frequency histogram rather than a distinct-count reducer: EE has no
    `countDistinct` over an image, and the histogram's keys are the label set.
    """
    band = safe_get_info(labels.bandNames(), context=f"{context} band name")[0]
    hist = (
        safe_get_info(
            labels.select([band]).reduceRegion(
                reducer=ee.Reducer.frequencyHistogram(),
                geometry=roi,
                scale=scale,
                maxPixels=1e9,
            ),
            context=f"{context} label histogram",
        ).get(band)
        or {}
    )
    return len(hist)

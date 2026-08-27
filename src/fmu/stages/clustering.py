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
        max_component_px = config.max_component_pixels()
        component_stats = assert_components_fit(
            unit_labels,
            roi,
            scale,
            max_component_px,
            context=f"clustering per-{unit_key} means",
        )
        superpixel_stack = _compute_superpixel_means(
            decomposed_stack, unit_labels, max_component_px
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
        cluster_labels, n_training_units = _train_and_apply_kmeans(
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
            "n_training_units": n_training_units,
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
        cluster_labels = cluster_labels.set("clustering_metadata", metadata_json)

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
) -> tuple[ee.Image, int]:
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
    log.info("  k-means training rows: %d (one per %s)", n_units, unit_key)
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

    return training_input.cluster(clusterer).rename("cluster_id"), n_units

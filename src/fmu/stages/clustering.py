"""Clustering stage. Per-superpixel feature stack, preprocessing,
k-means, then per-pixel cluster labels.

Implements DEC-001 (clustering operates on SNIC superpixel means, not
pixels), DEC-003 (median/IQR robust scaling), DEC-004 (log-transform
right-skewed bands), and the cyclic-feature decomposition for phase and
aspect (sin/cos pair).

Pipeline (server-side throughout):

  1. Build raw feature stack
       - All bands from optical, radar, structure, static features.
       - Drop *_obs_count (metadata), *_residual_variance (fit diagnostic),
         and annual_rainfall (constant in ROI).
       - Auto-detect optical band names (works for both ndvi_* and nirv_*).

  2. Cyclic decomposition
       - Each *_phase_* and aspect band becomes a sin/cos pair. Original dropped.

  3. Per-superpixel means
       - reduceConnectedComponents with the SNIC clusters image as labels.
       - Every pixel now holds the mean of its superpixel for each feature.

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
       - Sample n_training_samples pixels from the habitat-masked, scaled stack.
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
from fmu.utils.gee import safe_call, safe_get_info
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


@register_stage("clustering")
class ClusteringStage(Stage):
    name = "clustering"
    required_inputs = {
        "roi",
        "snic_clusters",
        "optical_features",
        "radar_features",
        "structure_features",
        "static_features",
        "habitat_mask",
    }
    produces = {"cluster_labels", "feature_stack"}
    cacheable_outputs = {"cluster_labels", "feature_stack"}

    @safe_call("running k-means clustering")
    def run(self, ctx: PipelineContext, config: Config) -> StageResult:
        roi = ctx.get("roi")
        snic_clusters: ee.Image = ctx.get("snic_clusters")
        habitat_mask: ee.Image = ctx.get("habitat_mask")
        params = config.clustering
        scale = config.export.analysis_scale_m

        # 1. Build raw feature stack
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

        # 3. Per-superpixel means
        superpixel_stack = _compute_superpixel_means(
            decomposed_stack, snic_clusters, params.superpixel_max_size
        )

        # 4. Habitat filter
        habitat_masked = superpixel_stack.updateMask(habitat_mask)

        # Take a sample now and use it for all subsequent preprocessing stats.
        # Computing skew / percentiles via reduceRegion on the full image hits
        # GEE's user memory limit when there are many bands. A 10k-pixel sample
        # gives stable estimates of median/IQR/skewness without the memory cost.
        candidate_bands = safe_get_info(
            habitat_masked.bandNames(), context="post-decomposition bands"
        )
        preprocessing_sample = habitat_masked.sample(
            region=roi,
            scale=scale,
            numPixels=10000,
            seed=params.seed,
            dropNulls=True,
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
        # would describe the WRONG distribution for scaling. Each sample
        # uses the same seed, samples the same pixel positions, but with
        # values reflecting their respective transform stages. Sampling
        # is cheap (~10k pixels × handful of bands per roundtrip).
        post_log_sample = transformed_stack.sample(
            region=roi,
            scale=scale,
            numPixels=10000,
            seed=params.seed,
            dropNulls=True,
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

        # 8-9. Train k-means and apply
        cluster_labels = _train_and_apply_kmeans(
            scaled_stack=scaled_stack,
            active_bands=active_bands,
            habitat_mask=habitat_mask,
            roi=roi,
            scale=scale,
            n_training_samples=params.n_training_samples,
            k=params.k,
            seed=params.seed,
        )

        # 10. Attach preprocessing metadata
        clustering_metadata = {
            "k": params.k,
            "seed": params.seed,
            "n_training_samples": params.n_training_samples,
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
                "n_active_bands": len(active_bands),
                "n_log_transformed": len(skewed_bands),
                "n_dropped_constant": len(dropped_bands),
                "normalization_method": method,
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
    feature_image: ee.Image, snic_clusters: ee.Image, max_size: int
) -> ee.Image:
    """Replace each feature value with its mean over the containing superpixel.

    Adds snic_clusters as a label band, then calls reduceConnectedComponents
    (the standard SNIC-aggregate pattern in GEE). Output has the same bands
    as the input but pixel values are constant within each superpixel.
    Note: reduceConnectedComponents preserves input band names, no
    _mean suffix is added (unlike SNIC's mean output bands).
    """
    band_names = feature_image.bandNames()
    label_band = "snic_label"

    with_labels = feature_image.addBands(snic_clusters.rename(label_band))
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


def _train_and_apply_kmeans(
    *,
    scaled_stack: ee.Image,
    active_bands: list[str],
    habitat_mask: ee.Image,
    roi: ee.Geometry,
    scale: int,
    n_training_samples: int,
    k: int,
    seed: int,
) -> ee.Image:
    """Train wekaKMeans on a sample, apply to the full habitat-masked stack."""
    # Sample only within habitat. Non-habitat pixels are masked out
    training_input = scaled_stack.updateMask(habitat_mask)
    training_sample = training_input.sample(
        region=roi,
        scale=scale,
        numPixels=n_training_samples,
        seed=seed,
        dropNulls=True,
    )

    # wekaKMeans: init=1 is k-means++ (better init than random).
    clusterer = ee.Clusterer.wekaKMeans(
        nClusters=k,
        init=1,
        seed=seed,
    ).train(features=training_sample, inputProperties=active_bands)

    return training_input.cluster(clusterer).rename("cluster_id")

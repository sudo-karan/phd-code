"""Metrics stage. Quantitative comparison of clusterings.

This is the actual research deliverable: does the variant clustering
differ meaningfully from the baseline, and how?

The stage runs in two modes depending on `metrics.reference_config_name`:

  - **null (baseline mode):** computes only intrinsic metrics (silhouette
    score) for the current config.

  - **set (comparison mode):** also loads the reference config's
    cluster_labels asset and computes:
      ARI: Adjusted Rand Index (partition similarity, 0=random, 1=identical)
      NMI: Normalized Mutual Information (information-theoretic agreement)
      Correspondence: Hungarian algorithm on the confusion matrix, gives
                      the optimal mapping {current_cluster_id: reference_cluster_id}
      Agreement rate: fraction of pixels where the mapped labels agree
      Confusion matrix: k x k pixel-overlap counts
      Agreement map: server-side image showing per-pixel agreement (1 where
                     configs agree, 0 where they differ)
      Confidence:    the agreement map rolled up to SNIC superpixels — each
                     stand's fraction of pixels that agree with the reference
                     (0..1). This is a *consensus/stability* layer: high where
                     the two representations delineate the same stand, low where
                     they disagree. It is NOT a correctness score (there is no
                     ground-truth stand map to score against); it flags where a
                     stand boundary is robust to the choice of feature source
                     and where it should be read with caution.

Implementation notes:
  - ARI/NMI computed on a random sample of habitat pixels (both labels
    sampled at identical locations via a stacked image).
  - Silhouette score computed on a stratified sample of the feature_stack
    (n samples per cluster), using sklearn's built-in implementation.
  - Cluster correspondence uses the confusion matrix (pixel overlap),
    NOT feature-space centroids. Feature bands differ between configs
    so centroid distance isn't meaningful.
"""

from __future__ import annotations

from typing import Any, ClassVar

import ee
import numpy as np
from scipy.optimize import linear_sum_assignment
from sklearn.metrics import (
    adjusted_rand_score,
    confusion_matrix,
    normalized_mutual_info_score,
    silhouette_score,
)

from fmu.config import Config
from fmu.stages.base import PipelineContext, Stage, StageResult, register_stage
from fmu.utils.caching import asset_exists, cached_asset_path
from fmu.utils.components import assert_components_fit
from fmu.utils.gee import safe_call, safe_get_info
from fmu.utils.logging import get_logger

log = get_logger(__name__)


@register_stage("metrics")
class MetricsStage(Stage):
    name = "metrics"
    # The unit label key is `stand_clusters` or `snic_clusters` depending on
    # whether merge ran, so it is checked in validate() rather than here.
    required_inputs = {"roi", "cluster_labels", "habitat_mask"}
    produces = {"comparison_metrics", "agreement_map", "confidence"}
    cacheable_outputs: ClassVar[set[str]] = set()  # always run; produces Python dict + images

    def validate(self, ctx: PipelineContext, config: Config) -> None:
        needed = self.required_inputs | {config.unit_label_key()}
        missing = needed - ctx.keys()
        if missing:
            raise KeyError(
                f"{self.name}: missing required context inputs: {sorted(missing)}. "
                f"Context has: {sorted(ctx.keys())}"
            )

    @safe_call("metrics stage")
    def run(self, ctx: PipelineContext, config: Config) -> StageResult:
        roi = ctx.get("roi")
        current_labels: ee.Image = ctx.get("cluster_labels")
        habitat_mask: ee.Image = ctx.get("habitat_mask")
        unit_key = config.unit_label_key()
        unit_labels: ee.Image = ctx.get(unit_key)
        scale = config.export.analysis_scale_m
        params = config.metrics
        k = config.clustering.k

        metrics: dict[str, Any] = {
            "current_config": config.name,
            "k": k,
        }

        # --- Intrinsic silhouette score for current config ---
        log.info("  computing intrinsic silhouette for %s", config.name)
        silh_current = _compute_silhouette(
            config_name=config.name,
            cluster_labels=current_labels,
            habitat_mask=habitat_mask,
            roi=roi,
            scale=scale,
            n_per_cluster=params.n_silhouette_samples_per_cluster,
            k=k,
            seed=config.clustering.seed,
        )
        metrics["silhouette_current"] = silh_current
        log.info("    silhouette (current=%s): %.4f", config.name, silh_current)

        # --- Comparison mode (only if reference set) ---
        agreement_map = None
        confidence = None
        if params.reference_config_name:
            log.info(
                "  comparison mode: against reference '%s'",
                params.reference_config_name,
            )
            reference_path = cached_asset_path(
                params.reference_config_name, "clustering", "cluster_labels"
            )
            if not asset_exists(reference_path):
                raise FileNotFoundError(
                    f"Reference cluster_labels not found at {reference_path}. "
                    f"Run the reference config ({params.reference_config_name}) "
                    "through clustering first."
                )
            reference_labels = ee.Image(reference_path)

            # Sample both images at the same pixels
            current_arr, reference_arr = _sample_paired_labels(
                current_labels=current_labels,
                reference_labels=reference_labels,
                habitat_mask=habitat_mask,
                roi=roi,
                scale=scale,
                n_samples=params.n_comparison_samples,
                seed=config.clustering.seed,
            )
            n_samples = len(current_arr)
            log.info("    paired sample size: %d pixels", n_samples)

            ari = float(adjusted_rand_score(reference_arr, current_arr))
            nmi = float(normalized_mutual_info_score(reference_arr, current_arr))
            metrics.update({
                "reference_config": params.reference_config_name,
                "ari": ari,
                "nmi": nmi,
                "n_samples_used": n_samples,
            })
            log.info("    ARI=%.4f  NMI=%.4f", ari, nmi)

            # Confusion matrix + Hungarian correspondence
            cm = confusion_matrix(current_arr, reference_arr, labels=list(range(k)))
            # Hungarian minimizes cost; we want to maximize overlap, so negate.
            row_ind, col_ind = linear_sum_assignment(-cm)
            correspondence = {int(r): int(c) for r, c in zip(row_ind, col_ind, strict=False)}
            total_pixels = int(cm.sum())
            agreed_pixels = int(sum(cm[r][c] for r, c in zip(row_ind, col_ind, strict=False)))
            agreement_rate = agreed_pixels / total_pixels if total_pixels else 0.0
            metrics.update({
                "correspondence": correspondence,
                "agreement_rate": agreement_rate,
                "confusion_matrix": cm.tolist(),
            })
            log.info(
                "    correspondence (current to reference): %s",
                ", ".join(f"{a} to {b}" for a, b in correspondence.items()),
            )
            log.info("    agreement rate after correspondence: %.2f%%", 100 * agreement_rate)

            # Reference silhouette (so we can compare intrinsic quality)
            ref_feature_stack_path = cached_asset_path(
                params.reference_config_name, "clustering", "feature_stack"
            )
            if asset_exists(ref_feature_stack_path):
                silh_reference = _compute_silhouette(
                    config_name=params.reference_config_name,
                    cluster_labels=reference_labels,
                    habitat_mask=habitat_mask,
                    roi=roi,
                    scale=scale,
                    n_per_cluster=params.n_silhouette_samples_per_cluster,
                    k=k,
                    seed=config.clustering.seed,
                )
                metrics["silhouette_reference"] = silh_reference
                log.info(
                    "    silhouette (reference=%s): %.4f",
                    params.reference_config_name, silh_reference,
                )

            # Server-side agreement map (remap current to reference label-space, compare)
            from_values = list(range(k))
            to_values = [correspondence[i] for i in from_values]
            remapped_current = current_labels.remap(from_values, to_values)
            agreement_map = (
                remapped_current.eq(reference_labels)
                .rename("agrees")
                .updateMask(habitat_mask)
                .clip(roi)
            )

            # --- Per-stand confidence: roll the per-pixel agreement up to SNIC
            # superpixels. Each stand's confidence = fraction of its pixels that
            # agree with the reference (0..1). Consensus/stability, not
            # correctness (no ground-truth stand map exists to score against).
            max_component_px = config.max_component_pixels()
            metrics["unit_key"] = unit_key
            metrics["component_stats"] = assert_components_fit(
                unit_labels,
                roi,
                scale,
                max_component_px,
                context=f"metrics per-{unit_key} confidence",
            )
            confidence = (
                agreement_map.addBands(unit_labels.rename("snic_label"))
                .reduceConnectedComponents(
                    reducer=ee.Reducer.mean(),
                    labelBand="snic_label",
                    # Derived, not configured, and asserted above: this argument
                    # masks components larger than it, so an undersized cap
                    # would drop the biggest stands out of the confidence layer
                    # entirely rather than raising.
                    maxSize=max_component_px,
                )
                .select(["agrees"], ["confidence"])
                .updateMask(habitat_mask)
                .clip(roi)
            )

            # Scalar summary for the metrics JSON / report. mean is the
            # area-weighted mean stand confidence; frac_area_ge_high is the
            # share of habitat sitting in high-agreement stands (the number that
            # says "how much of the map is robust to the feature choice").
            high_threshold = 0.8
            summary_stats = safe_get_info(
                confidence.addBands(
                    confidence.gte(high_threshold).rename("high")
                ).reduceRegion(
                    reducer=ee.Reducer.mean(),
                    geometry=roi,
                    scale=scale,
                    maxPixels=1e9,
                    bestEffort=True,
                ),
                context="confidence summary",
            )
            mean_conf = summary_stats.get("confidence") if summary_stats else None
            frac_high = summary_stats.get("high") if summary_stats else None
            metrics["confidence_summary"] = {
                "mean": float(mean_conf) if mean_conf is not None else None,
                "frac_area_ge_high": float(frac_high) if frac_high is not None else None,
                "high_threshold": high_threshold,
            }
            log.info(
                "    confidence: mean=%s, frac_area>=%.1f=%s",
                None if mean_conf is None else f"{mean_conf:.3f}",
                high_threshold,
                None if frac_high is None else f"{frac_high:.3f}",
            )
        else:
            log.info("  baseline mode: no reference config, intrinsic metrics only")

        # Output contract: `produces` always lists all three keys, so we always
        # write all three. In baseline mode `agreement_map` and `confidence` are
        # None (there is no reference to compare against). Downstream consumers
        # (currently just the inspect script) must handle the None case.
        outputs: dict[str, Any] = {
            "comparison_metrics": metrics,
            "agreement_map": agreement_map,
            "confidence": confidence,
        }

        return StageResult(
            outputs=outputs,
            metadata={
                "metrics": metrics,
                "has_agreement_map": agreement_map is not None,
                "has_confidence": confidence is not None,
            },
        )


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------


def _sample_paired_labels(
    *,
    current_labels: ee.Image,
    reference_labels: ee.Image,
    habitat_mask: ee.Image,
    roi: ee.Geometry,
    scale: int,
    n_samples: int,
    seed: int,
) -> tuple[list[int], list[int]]:
    """Sample both label images at identical pixel locations.

    Returns two lists of integer cluster IDs, aligned positionally.
    """
    combined = (
        current_labels.rename("current")
        .addBands(reference_labels.rename("reference"))
        .updateMask(habitat_mask)
    )
    sample = combined.sample(
        region=roi,
        scale=scale,
        numPixels=n_samples,
        seed=seed,
        dropNulls=True,
    )
    # Pull the feature collection to client
    features = safe_get_info(
        sample.toList(n_samples),
        context="paired label sample",
    )
    current_arr: list[int] = []
    reference_arr: list[int] = []
    for f in features:
        props = f.get("properties", {})
        c = props.get("current")
        r = props.get("reference")
        if c is None or r is None:
            continue
        current_arr.append(int(c))
        reference_arr.append(int(r))
    return current_arr, reference_arr


def _compute_silhouette(
    *,
    config_name: str,
    cluster_labels: ee.Image,
    habitat_mask: ee.Image,
    roi: ee.Geometry,
    scale: int,
    n_per_cluster: int,
    k: int,
    seed: int,
) -> float:
    """Compute silhouette score on a stratified sample of the feature_stack.

    Stratified sampling ensures each cluster contributes roughly the same
    number of points. Important for silhouette which compares within-cluster
    distance to nearest-cluster distance.
    """
    feature_stack_path = cached_asset_path(config_name, "clustering", "feature_stack")
    if not asset_exists(feature_stack_path):
        log.warning("  feature_stack asset not found for %s; skipping silhouette", config_name)
        return float("nan")
    feature_stack = ee.Image(feature_stack_path)

    combined = (
        feature_stack.addBands(cluster_labels.rename("cluster_id"))
        .updateMask(habitat_mask)
    )
    sample = combined.stratifiedSample(
        numPoints=n_per_cluster,
        classBand="cluster_id",
        region=roi,
        scale=scale,
        seed=seed,
        dropNulls=True,
    )
    n_total_target = n_per_cluster * k
    features = safe_get_info(
        sample.toList(n_total_target),
        context=f"stratified sample for silhouette ({config_name})",
    )

    # Get the feature band names by reading the first feature
    if not features:
        return float("nan")
    sample_props = features[0].get("properties", {})
    band_names = sorted([b for b in sample_props if b != "cluster_id"])

    feature_vectors = []
    labels = []
    for f in features:
        props = f.get("properties", {})
        cluster_id = props.get("cluster_id")
        if cluster_id is None:
            continue
        vec = [props.get(b) for b in band_names]
        if any(v is None for v in vec):
            continue
        feature_vectors.append(vec)
        labels.append(int(cluster_id))

    if len(feature_vectors) < 2 or len(set(labels)) < 2:
        return float("nan")

    return float(silhouette_score(np.array(feature_vectors), np.array(labels)))

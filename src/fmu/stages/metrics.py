"""Metrics stage — quantitative comparison of clusterings.

This is the actual research deliverable: does the variant clustering
differ meaningfully from the baseline, and how?

The stage runs in two modes depending on `metrics.reference_config_name`:

  - **null (baseline mode):** computes only intrinsic metrics (silhouette
    score) for the current config.

  - **set (comparison mode):** also loads the reference config's
    cluster_labels asset and computes:
      ARI  — Adjusted Rand Index (partition similarity, 0=random, 1=identical)
      NMI  — Normalized Mutual Information (information-theoretic agreement)
      Correspondence — Hungarian algorithm on the confusion matrix, gives
                       the optimal mapping {current_cluster_id: reference_cluster_id}
      Agreement rate — % of pixels where the mapped labels agree
      Confusion matrix — k×k pixel-overlap counts
      Agreement map — server-side image showing per-pixel agreement (1 where
                      configs agree, 0 where they differ)

Implementation notes:
  - ARI/NMI computed on a random sample of habitat pixels (both labels
    sampled at identical locations via a stacked image).
  - Silhouette score computed on a stratified sample of the feature_stack
    (n samples per cluster), using sklearn's built-in implementation.
  - Cluster correspondence uses the confusion matrix (pixel overlap),
    NOT feature-space centroids — feature bands differ between configs
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
from fmu.utils.gee import safe_call, safe_get_info
from fmu.utils.logging import get_logger

log = get_logger(__name__)


@register_stage("metrics")
class MetricsStage(Stage):
    name = "metrics"
    required_inputs = {"roi", "cluster_labels", "habitat_mask"}
    produces = {"comparison_metrics", "agreement_map"}
    cacheable_outputs: ClassVar[set[str]] = set()  # always run; produces Python dict + image

    @safe_call("metrics stage")
    def run(self, ctx: PipelineContext, config: Config) -> StageResult:
        roi = ctx.get("roi")
        current_labels: ee.Image = ctx.get("cluster_labels")
        habitat_mask: ee.Image = ctx.get("habitat_mask")
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
            # Hungarian minimizes cost; we want to maximize overlap → negate.
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
                "    correspondence (current→reference): %s",
                ", ".join(f"{a}→{b}" for a, b in correspondence.items()),
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
        else:
            log.info("  baseline mode — no reference config; intrinsic metrics only")

        # Output contract: `produces` always lists both keys, so we always
        # write both. In baseline mode `agreement_map` is None (the reference
        # asset doesn't exist to compare against). Downstream consumers
        # (currently just the inspect script) must handle the None case.
        outputs: dict[str, Any] = {
            "comparison_metrics": metrics,
            "agreement_map": agreement_map,
        }

        return StageResult(
            outputs=outputs,
            metadata={
                "metrics": metrics,
                "has_agreement_map": agreement_map is not None,
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
    number of points — important for silhouette which compares within-cluster
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

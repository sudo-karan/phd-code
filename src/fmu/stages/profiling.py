"""Profiling stage. Computes per-cluster statistics on every feature
band in ORIGINAL UNITS (not the scaled, log-transformed values used
for clustering). Output is a small list of dicts; one per cluster.

For each of the k clusters:
  - pixel_count, area_ha
  - For every non-cyclic original-units feature band:
      mean, p25, p50, p75
  - For cyclic bands (phase, aspect):
      sin/cos decomposition first, then mean/percentiles on the components
      (circular mean can be recovered as atan2(sin_mean, cos_mean))

This bridges raw cluster IDs to ecological interpretation. Without this,
a cluster map shows "cluster 3" with no way to say what cluster 3 is.

Not a cached stage; the operation is fast (k small reduceRegion calls)
and the output is a Python list. Saved by the inspect script as CSV/JSON
for downstream analysis.
"""

from __future__ import annotations

import math
from typing import Any

import ee

from fmu.config import Config
from fmu.stages.base import PipelineContext, Stage, StageResult, register_stage
from fmu.utils.gee import safe_call, safe_get_info
from fmu.utils.logging import get_logger

log = get_logger(__name__)


# Bands to drop from profiling (metadata, not feature)
_EXCLUDE_BANDS: frozenset[str] = frozenset({"ndvi_obs_count", "nirv_obs_count"})


# Feature-source-specific context inputs (mirrors the clustering stage).
_HANDCRAFTED_INPUTS = frozenset(
    {"optical_features", "radar_features", "structure_features", "static_features"}
)
_EMBEDDING_INPUTS = frozenset({"embedding_features"})


@register_stage("profiling")
class ProfilingStage(Stage):
    name = "profiling"
    # Invariant subset; the feature-source-specific inputs are enforced in
    # validate() so the embedding arm isn't forced to produce the hand-crafted
    # stack it never builds.
    required_inputs = {"roi", "cluster_labels"}
    produces = {"cluster_profiles"}
    cacheable_outputs = set()  # always run; small operation, no GEE asset

    def validate(self, ctx: PipelineContext, config: Config) -> None:
        source = config.clustering.feature_source
        extra = _EMBEDDING_INPUTS if source == "embedding" else _HANDCRAFTED_INPUTS
        missing = ({"roi", "cluster_labels"} | extra) - ctx.keys()
        if missing:
            raise KeyError(
                f"{self.name} (feature_source={source!r}): missing required "
                f"context inputs: {sorted(missing)}. Context has: {sorted(ctx.keys())}"
            )

    @safe_call("computing cluster profiles")
    def run(self, ctx: PipelineContext, config: Config) -> StageResult:
        roi = ctx.get("roi")
        cluster_labels: ee.Image = ctx.get("cluster_labels")
        scale = config.export.analysis_scale_m
        k = config.clustering.k

        # Build feature stack in ORIGINAL UNITS.
        # Handcrafted arm: concatenate the four feature images (keeping
        # annual_rainfall, informational even if constant, and decomposing
        # cyclic bands below). Embedding arm: the single embedding image is the
        # stack (no cyclic bands, nothing to exclude).
        if config.clustering.feature_source == "embedding":
            raw_stack = ctx.get("embedding_features")
        else:
            raw_stack = ee.Image.cat(
                [
                    ctx.get("optical_features"),
                    ctx.get("radar_features"),
                    ctx.get("structure_features"),
                    ctx.get("static_features"),
                ]
            )
        raw_band_names = safe_get_info(
            raw_stack.bandNames(), context="profiling raw bands"
        )
        kept_bands = [b for b in raw_band_names if b not in _EXCLUDE_BANDS]
        kept_stack = raw_stack.select(kept_bands)

        # Cyclic decomposition (same approach as clustering stage)
        feature_stack, decomposition_log = _decompose_cyclic_bands(kept_stack)
        feature_band_names = safe_get_info(
            feature_stack.bandNames(), context="profile feature bands"
        )
        log.info(
            "  profiling %d feature bands across %d clusters", len(feature_band_names), k
        )
        if decomposition_log:
            log.info(
                "  cyclic bands decomposed: %s", ", ".join(decomposition_log)
            )

        # Per-cluster reduce (k small server calls; memory-safe since each
        # cluster contains a subset of pixels and bestEffort caps the work)
        profiles: list[dict[str, Any]] = []
        pixel_area_ha = (scale * scale) / 10000.0

        for cluster_id in range(k):
            mask = cluster_labels.eq(cluster_id)
            cluster_image = feature_stack.updateMask(mask)

            # Pixel count; use the first band; identical for all bands
            count_stats = safe_get_info(
                cluster_image.select(feature_band_names[0]).reduceRegion(
                    reducer=ee.Reducer.count(),
                    geometry=roi,
                    scale=scale,
                    maxPixels=1e9,
                    bestEffort=True,
                ),
                context=f"pixel count for cluster {cluster_id}",
            )
            pixel_count = count_stats.get(feature_band_names[0]) or 0

            # Feature stats: mean + p25/p50/p75 per band in one call
            feature_stats = safe_get_info(
                cluster_image.reduceRegion(
                    reducer=ee.Reducer.mean().combine(
                        ee.Reducer.percentile([25, 50, 75]), sharedInputs=True
                    ),
                    geometry=roi,
                    scale=scale,
                    maxPixels=1e9,
                    bestEffort=True,
                ),
                context=f"feature stats for cluster {cluster_id}",
            )

            profile: dict[str, Any] = {
                "cluster_id": cluster_id,
                "pixel_count": int(pixel_count),
                "area_ha": round(int(pixel_count) * pixel_area_ha, 2),
            }
            # Add all the per-band stats from feature_stats
            profile.update(feature_stats or {})
            profiles.append(profile)
            log.info(
                "    cluster %d: %d pixels (%.1f ha)",
                cluster_id,
                int(pixel_count),
                int(pixel_count) * pixel_area_ha,
            )

        return StageResult(
            outputs={"cluster_profiles": profiles},
            metadata={
                "k": k,
                "n_feature_bands": len(feature_band_names),
                "feature_bands": feature_band_names,
                "cyclic_decomposed": decomposition_log,
                "profiles": profiles,  # also in metadata to goes to manifest.json
            },
        )


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------


def _decompose_cyclic_bands(image: ee.Image) -> tuple[ee.Image, list[str]]:
    """Replace cyclic bands (phase, aspect) with sin/cos pairs.

    Same logic as clustering's _decompose_cyclic_bands. Duplicated here
    instead of imported to keep the profiling stage standalone.
    """
    band_names = safe_get_info(image.bandNames(), context="bands for cyclic check")
    cyclic_bands = [b for b in band_names if "_phase_" in b or b == "aspect"]

    if not cyclic_bands:
        return image, []

    new_bands: list[ee.Image] = []
    for cb in cyclic_bands:
        original = image.select(cb)
        if cb == "aspect":  # noqa: SIM108  (keep for radians conversion comment)
            # Aspect is in degrees ∈ [0, 360]; convert to radians first.
            radians = original.multiply(math.pi / 180.0)
        else:
            # Phase bands from atan2 are already in radians ∈ [-π, π].
            radians = original
        new_bands.extend(
            [
                radians.sin().rename(f"{cb}_sin"),
                radians.cos().rename(f"{cb}_cos"),
            ]
        )

    kept_bands = [b for b in band_names if b not in cyclic_bands]
    return image.select(kept_bands).addBands(ee.Image.cat(new_bands)), cyclic_bands

"""Shared fixtures for live tests that need cached upstream stage outputs.

Background. The downstream live tests (clustering, export, metrics, profiling)
used to run every upstream stage live in their setup fixture. This worked
when GEE's memory budget per call was generous, but ~30 sequential skew
reducer calls in clustering's `_identify_skewed_bands` now exhaust the
budget — every downstream test errors at the same line with
"User memory limit exceeded".

The production path doesn't hit this. Why: in production, every stage's
output is cached as a GEE asset on first run. Subsequent runs (via the
inspect scripts) reload from cache and skip the heavy compute. The test
fixtures bypassed the cache because cache enablement wasn't part of the
bare `Stage().run()` pattern.

Fix. Test fixtures now load upstream artifacts directly from cached
GEE assets, matching the production cache-hit path. The downstream stage
itself still runs live (that's what we're testing); only its inputs come
from cache.

If the cache isn't populated (user hasn't run inspect_clustering.py yet),
tests skip with a clear message rather than re-deriving the heavy compute.

Profiling note (v1.1.0). Profiling produces `cluster_profiles` — a Python
list of dicts, not a cacheable image asset. So `include_profiling=True`
runs the profiling stage live rather than loading from cache. Profiling
is fast (k small reduceRegion calls, ~30s), so this is an acceptable cost
for downstream tests (export, metrics) that consume cluster_profiles.
"""

from __future__ import annotations

from pathlib import Path

import ee
import pytest

# Eager-import every stage module so that the @register_stage decorators
# fire and the stage registry is fully populated. This matters for any
# code that walks the registry (e.g., the export stage's inventory
# discovery). Without these imports, a test that only imports one stage
# would see an incomplete registry and silently return empty results.
import fmu.stages.clustering  # noqa: F401
import fmu.stages.data_load  # noqa: F401
import fmu.stages.export  # noqa: F401
import fmu.stages.features_optical  # noqa: F401
import fmu.stages.features_radar  # noqa: F401
import fmu.stages.features_static  # noqa: F401
import fmu.stages.features_structure  # noqa: F401
import fmu.stages.masking  # noqa: F401
import fmu.stages.metrics  # noqa: F401
import fmu.stages.profiling  # noqa: F401
import fmu.stages.segmentation  # noqa: F401
from fmu.config import Config, load_config
from fmu.stages.base import PipelineContext
from fmu.utils.caching import asset_exists, cached_asset_path
from fmu.utils.gee import load_roi_geometry

# Map of (stage_name, output_key) → context_key. context_key is what the
# downstream stage expects to find in PipelineContext. Most match the
# output key directly; we keep this explicit for clarity.
#
# This is the "image-only" cacheable surface — exactly what production
# caches and what downstream stages consume. data_load's collection
# outputs (s2_collection, s1_collection) aren't here because they aren't
# cacheable and downstream stages that need clustering inputs don't use
# them anyway.
_UPSTREAM_ASSETS = [
    ("masking", "habitat_mask", "habitat_mask"),
    ("masking", "water_mask", "water_mask"),
    ("data_load", "s2_composite", "s2_composite"),
    ("features_optical", "optical_features", "optical_features"),
    ("features_radar", "radar_features", "radar_features"),
    ("features_structure", "structure_features", "structure_features"),
    ("features_static", "static_features", "static_features"),
    ("segmentation", "snic_clusters", "snic_clusters"),
    ("segmentation", "snic_means", "snic_means"),
]

# Extended set for stages downstream of clustering (profiling, export,
# metrics). Adds clustering's outputs so the test fixture can populate
# them without running clustering live.
_UPSTREAM_ASSETS_INCLUDING_CLUSTERING = _UPSTREAM_ASSETS + [
    ("clustering", "cluster_labels", "cluster_labels"),
    ("clustering", "feature_stack", "feature_stack"),
]


def init_real_gee_or_skip() -> None:
    """Initialize GEE for live tests; skip the test if creds aren't set."""
    import fmu.utils.gee as gee_mod
    from fmu.settings import get_settings

    gee_mod._initialized = False
    get_settings(force_reload=True)

    settings = get_settings()
    if not settings.gee_project_id:
        pytest.skip("GEE_PROJECT_ID not set in .env")

    try:
        gee_mod.init_gee()
    except ee.EEException as e:
        msg = str(e).lower()
        if "authenticate" in msg or "credentials" in msg:
            pytest.skip(f"GEE not authenticated. {e}")
        raise


def load_config_and_roi(config_filename: str) -> tuple[Config, ee.Geometry]:
    """Load the config + ROI geometry from the standard repo layout."""
    repo_root = Path(__file__).parent.parent
    config = load_config(repo_root / "configs" / config_filename)
    roi = load_roi_geometry(repo_root / "aois" / "sanjay_van.geojson")
    return config, roi


def context_with_upstream_from_cache(
    config_name: str,
    *,
    include_clustering: bool = False,
) -> PipelineContext:
    """Build a PipelineContext populated from cached GEE assets.

    Loads every (stage, output) pair from the appropriate cache surface
    for the given config:
      - include_clustering=False (default): loads up through segmentation.
        Use for tests that drive the clustering stage itself.
      - include_clustering=True: also loads cluster_labels + feature_stack.
        Use for tests of stages DOWNSTREAM of clustering (profiling,
        export, metrics).

    If ANY required asset is missing, calls pytest.skip with a message
    telling the user how to populate the cache.

    The caller is responsible for setting `roi` separately (it's not a
    cached asset). Non-cacheable outputs (e.g., `cluster_profiles`) must
    be added by the caller too; see `ctx_ready_for_downstream` for the
    profiling path.
    """
    ctx = PipelineContext()
    missing: list[str] = []
    assets = _UPSTREAM_ASSETS_INCLUDING_CLUSTERING if include_clustering else _UPSTREAM_ASSETS

    for stage_name, output_key, context_key in assets:
        path = cached_asset_path(config_name, stage_name, output_key)
        if asset_exists(path):
            ctx.set(context_key, ee.Image(path))
        else:
            missing.append(f"  {stage_name}/{output_key} → {path}")

    if missing:
        pytest.skip(
            f"Upstream cache not populated for config {config_name!r}. "
            "Run `python scripts/inspect_clustering.py "
            f"--config configs/{config_name}.yaml` first to populate. "
            "Missing assets:\n" + "\n".join(missing)
        )

    return ctx


def ctx_ready_for_downstream(
    config_filename: str,
    *,
    include_clustering: bool = False,
    include_profiling: bool = False,
) -> tuple[PipelineContext, Config]:
    """One-stop helper: GEE init, config load, ROI load, context-from-cache.

    Returns a (context, config) tuple ready to be passed to a downstream
    stage's `run()` method. ROI is pre-populated on the context.

    Args:
        config_filename: yaml file under configs/
        include_clustering: True for stages downstream of clustering
            (profiling, export, metrics). False (default) for clustering
            itself.
        include_profiling: True for stages downstream of profiling
            (currently: export, when its dissolved-vector layer attaches
            cluster_profiles). Implies include_clustering=True. Runs the
            profiling stage live (~30s, k small reduceRegion calls) and
            populates `cluster_profiles` on the context. Profiling output
            is not a cacheable image asset, hence no cache-load path.
    """
    # Profiling consumes cluster_labels, so requesting profiling without
    # clustering would skip on a missing-asset error. Auto-enable to make
    # the fixture harder to misuse.
    if include_profiling and not include_clustering:
        include_clustering = True

    init_real_gee_or_skip()
    config, roi = load_config_and_roi(config_filename)
    ctx = context_with_upstream_from_cache(
        config.name, include_clustering=include_clustering
    )
    ctx.set("roi", roi)

    if include_profiling:
        # Run profiling live; its output is a Python list of dicts, not a
        # cacheable image. Stage runs in ~30s for typical k.
        from fmu.stages.profiling import ProfilingStage

        result = ProfilingStage().run(ctx, config)
        for output_key, output_value in result.outputs.items():
            ctx.set(output_key, output_value)

    return ctx, config
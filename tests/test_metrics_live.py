"""Live integration tests for the metrics stage.

These tests run against both configs:
  - sanjay_van_nirv_dual (comparison mode — reference set to baseline)
  - sanjay_van_baseline (baseline mode — no reference)

Upstream artifacts loaded from GEE cache (see tests/_live_cache_fixtures.py
for rationale). To populate the cache, run `python scripts/inspect_clustering.py
--config configs/sanjay_van_baseline.yaml` and the same for the variant.
"""

from __future__ import annotations

from pathlib import Path

import ee
import pytest

from _live_cache_fixtures import ctx_ready_for_downstream
from fmu.stages.metrics import MetricsStage
from fmu.utils.caching import asset_exists, cached_asset_path

pytestmark = pytest.mark.live_gee


@pytest.fixture(scope="module")
def ctx_ready_for_metrics():
    """Variant config — comparison mode."""
    ctx, config = ctx_ready_for_downstream(
        "sanjay_van_nirv_dual.yaml", include_clustering=True
    )
    # Comparison mode also needs the baseline reference assets — verify
    # they're cached too, otherwise the metrics stage will skip its
    # comparison path or error.
    ref = config.metrics.reference_config_name
    if ref:
        ref_path = cached_asset_path(ref, "clustering", "cluster_labels")
        if not asset_exists(ref_path):
            pytest.skip(
                f"Reference cluster_labels not cached at {ref_path}. "
                f"Run inspect_clustering.py --config configs/{ref}.yaml first."
            )
    return ctx, config


def test_runs_end_to_end(ctx_ready_for_metrics):
    ctx, config = ctx_ready_for_metrics
    result = MetricsStage().run(ctx, config)
    assert "comparison_metrics" in result.outputs
    # Agreement map should be present when comparison mode is active
    assert "agreement_map" in result.outputs


def test_metrics_has_required_keys(ctx_ready_for_metrics):
    ctx, config = ctx_ready_for_metrics
    result = MetricsStage().run(ctx, config)
    metrics = result.outputs["comparison_metrics"]
    # Comparison mode required keys
    for key in ("ari", "nmi", "agreement_rate", "correspondence",
                "confusion_matrix", "silhouette_current"):
        assert key in metrics, f"missing key: {key}"


def test_ari_nmi_in_valid_range(ctx_ready_for_metrics):
    """ARI ∈ [-1, 1] in theory; NMI ∈ [0, 1]."""
    ctx, config = ctx_ready_for_metrics
    result = MetricsStage().run(ctx, config)
    metrics = result.outputs["comparison_metrics"]
    assert -1.0 <= metrics["ari"] <= 1.0, f"ARI out of range: {metrics['ari']}"
    assert 0.0 <= metrics["nmi"] <= 1.0, f"NMI out of range: {metrics['nmi']}"


def test_silhouette_in_valid_range(ctx_ready_for_metrics):
    """Silhouette ∈ [-1, 1]."""
    ctx, config = ctx_ready_for_metrics
    result = MetricsStage().run(ctx, config)
    metrics = result.outputs["comparison_metrics"]
    silh = metrics["silhouette_current"]
    # nan also acceptable if feature_stack absent
    if silh == silh:  # not NaN
        assert -1.0 <= silh <= 1.0, f"silhouette out of range: {silh}"


def test_correspondence_is_one_to_one(ctx_ready_for_metrics):
    """Hungarian guarantees a 1-to-1 matching; verify."""
    ctx, config = ctx_ready_for_metrics
    result = MetricsStage().run(ctx, config)
    metrics = result.outputs["comparison_metrics"]
    correspondence = metrics["correspondence"]
    assert len(correspondence) == config.clustering.k
    keys = set(correspondence.keys())
    vals = set(correspondence.values())
    assert len(keys) == config.clustering.k, "duplicate current cluster IDs"
    assert len(vals) == config.clustering.k, "duplicate reference cluster IDs"


def test_confusion_matrix_shape(ctx_ready_for_metrics):
    ctx, config = ctx_ready_for_metrics
    result = MetricsStage().run(ctx, config)
    metrics = result.outputs["comparison_metrics"]
    cm = metrics["confusion_matrix"]
    k = config.clustering.k
    assert len(cm) == k
    for row in cm:
        assert len(row) == k


def test_agreement_map_is_image(ctx_ready_for_metrics):
    ctx, config = ctx_ready_for_metrics
    result = MetricsStage().run(ctx, config)
    agreement = result.outputs["agreement_map"]
    assert isinstance(agreement, ee.Image)


def test_confidence_is_image_and_summarised(ctx_ready_for_metrics):
    """Comparison mode rolls agreement up to a per-stand confidence image and
    writes a scalar summary into the metrics dict."""
    ctx, config = ctx_ready_for_metrics
    result = MetricsStage().run(ctx, config)
    confidence = result.outputs["confidence"]
    assert isinstance(confidence, ee.Image)

    summary = result.outputs["comparison_metrics"].get("confidence_summary")
    assert summary is not None
    assert summary["mean"] is None or 0.0 <= summary["mean"] <= 1.0
    if summary["frac_area_ge_high"] is not None:
        assert 0.0 <= summary["frac_area_ge_high"] <= 1.0


# ---------------------------------------------------------------------
# Baseline-mode tests: metrics.reference_config_name is null. The stage
# should compute intrinsic silhouette only and leave agreement_map as None.
# Importantly we ALSO exercise the orchestrator (not bare .run()) since
# the orchestrator's output-validation step is what catches contract
# violations.
# ---------------------------------------------------------------------


@pytest.fixture(scope="module")
def ctx_ready_for_baseline_metrics():
    """Same as ctx_ready_for_metrics but uses the baseline config (no reference)."""
    return ctx_ready_for_downstream(
        "sanjay_van_baseline.yaml", include_clustering=True
    )


def test_baseline_mode_only_returns_intrinsic_metrics(ctx_ready_for_baseline_metrics):
    """In baseline mode (no reference_config_name), comparison metrics are absent
    but the silhouette is still computed."""
    ctx, config = ctx_ready_for_baseline_metrics
    # Sanity check the fixture
    assert config.metrics.reference_config_name is None

    result = MetricsStage().run(ctx, config)
    metrics = result.outputs["comparison_metrics"]

    # Intrinsic metric must be present
    assert "silhouette_current" in metrics

    # Comparison metrics must NOT be present (no reference to compare against)
    for key in ("ari", "nmi", "agreement_rate", "correspondence", "confusion_matrix"):
        assert key not in metrics, (
            f"baseline mode unexpectedly produced {key!r}; "
            "should only run when reference_config_name is set"
        )


def test_baseline_mode_still_produces_both_declared_outputs(ctx_ready_for_baseline_metrics):
    """The stage's `produces` declaration is invariant; baseline mode must
    still write both keys to outputs (with agreement_map = None).

    This is the regression test for the bug found 2026-05-19: the stage
    used to conditionally add agreement_map only in comparison mode,
    which the orchestrator rejects with `output mismatch` error.
    """
    ctx, config = ctx_ready_for_baseline_metrics
    result = MetricsStage().run(ctx, config)
    assert set(result.outputs.keys()) == {
        "comparison_metrics", "agreement_map", "confidence"
    }
    assert result.outputs["agreement_map"] is None
    assert result.outputs["confidence"] is None


def test_baseline_mode_passes_orchestrator_validation(ctx_ready_for_baseline_metrics):
    """The orchestrator's strict produced_keys==produces check must accept
    baseline-mode metrics output.

    Why this matters: the bare `MetricsStage().run(ctx, config)` calls in
    other tests bypass the orchestrator. This test routes through Pipeline,
    which means the framework's contract enforcement is exercised end-to-end.
    """
    import tempfile

    from fmu.pipeline import Pipeline

    ctx, config = ctx_ready_for_baseline_metrics
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        # use_cache=False so this is a pure framework-level test, not a
        # cache test — and so we don't pollute the user's GEE asset space.
        pipeline = Pipeline(stage_names=["metrics"], use_cache=False)
        result = pipeline.run(config=config, run_dir=run_dir, initial_context=ctx)

    # If the orchestrator hadn't accepted the output, .run() would have
    # raised a ValueError before getting here.
    assert any(s.name == "metrics" for s in result.stages)
    assert result.context.has("comparison_metrics")
    assert result.context.has("agreement_map")
    assert result.context.has("confidence")
    # agreement_map and confidence should be None in baseline mode
    assert result.context.get("agreement_map") is None
    assert result.context.get("confidence") is None

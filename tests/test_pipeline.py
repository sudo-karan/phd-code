"""
Tests for fmu.pipeline.

The main goal: prove the orchestrator wires together correctly with
synthetic stages, BEFORE any real GEE work happens. If this passes:
  - Stages get looked up in the registry by name
  - validate() is called before run()
  - run() output is merged into the context
  - output-mismatch is caught
  - Manifest is written
  - Failures surface with the right stage name

These tests use trivial stages (numbers, strings) — no GEE. The fast suite.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fmu.pipeline import Pipeline, PipelineResult
from fmu.stages.base import (
    PipelineContext,
    Stage,
    StageResult,
    _clear_registry_for_testing,
    register_stage,
)


@pytest.fixture(autouse=True)
def reset_registry():
    _clear_registry_for_testing()
    yield
    _clear_registry_for_testing()


# Helper: build a minimal-but-valid Config object for tests.
def _make_config(name: str = "test_run"):
    """Construct a Config without going through YAML; cheap and isolated."""
    from fmu.config import Config, DateRange, DatesConfig, ROIConfig

    return Config(
        name=name,
        roi=ROIConfig(name="t", roi_file=Path("aois/t.geojson")),
        dates=DatesConfig(
            phenology=DateRange(start="2020-01-01", end="2024-12-31"),
            radar=DateRange(start="2020-01-01", end="2024-12-31"),
            optical_composite=DateRange(start="2023-01-01", end="2023-12-31"),
        ),
    )


# ---------- Pipeline construction ----------


class TestPipelineConstruction:
    def test_pipeline_requires_at_least_one_stage(self):
        with pytest.raises(ValueError, match="at least one stage"):
            Pipeline(stage_names=[])

    def test_pipeline_resolves_stages_at_construction(self):
        """Unknown stage names should fail at construction, not at run()."""
        with pytest.raises(KeyError, match="No stage registered"):
            Pipeline(stage_names=["does_not_exist"])

    def test_pipeline_holds_stage_classes_in_order(self):
        @register_stage("s_a")
        class A(Stage):
            name = "s_a"
            required_inputs: set[str] = set()
            produces: set[str] = set()

            def run(self, ctx, config):
                return StageResult()

        @register_stage("s_b")
        class B(Stage):
            name = "s_b"
            required_inputs: set[str] = set()
            produces: set[str] = set()

            def run(self, ctx, config):
                return StageResult()

        pipeline = Pipeline(stage_names=["s_a", "s_b"])
        assert pipeline.stage_classes == [A, B]


# ---------- End-to-end happy path ----------


class TestPipelineSmokeRun:
    """The flagship test: build a fake 3-stage pipeline and run it end to end."""

    def test_three_stage_pipeline_runs(self, tmp_path):
        @register_stage("seed")
        class SeedStage(Stage):
            name = "seed"
            required_inputs: set[str] = set()
            produces = {"x"}

            def run(self, ctx, config):
                return StageResult(
                    outputs={"x": 10},
                    metadata={"note": "seeded"},
                )

        @register_stage("double")
        class DoubleStage(Stage):
            name = "double"
            required_inputs = {"x"}
            produces = {"y"}

            def run(self, ctx, config):
                return StageResult(outputs={"y": ctx.get("x") * 2})

        @register_stage("add_one")
        class AddOneStage(Stage):
            name = "add_one"
            required_inputs = {"y"}
            produces = {"z"}

            def run(self, ctx, config):
                return StageResult(
                    outputs={"z": ctx.get("y") + 1},
                    warnings=["just a heads-up"],
                )

        pipeline = Pipeline(stage_names=["seed", "double", "add_one"])
        result = pipeline.run(config=_make_config(), run_dir=tmp_path)

        # Context has all produced keys
        assert result.context.get("x") == 10
        assert result.context.get("y") == 20
        assert result.context.get("z") == 21

        # PipelineResult records all three stages
        assert [s.name for s in result.stages] == ["seed", "double", "add_one"]
        assert result.stages[0].produced == ["x"]
        assert result.stages[2].warnings == ["just a heads-up"]
        assert all(s.elapsed_sec >= 0.0 for s in result.stages)
        assert result.total_elapsed_sec >= sum(s.elapsed_sec for s in result.stages) - 0.01

    def test_pipeline_writes_manifest(self, tmp_path):
        @register_stage("noop")
        class NoOpStage(Stage):
            name = "noop"
            required_inputs: set[str] = set()
            produces: set[str] = set()

            def run(self, ctx, config):
                return StageResult(metadata={"k": "v"})

        pipeline = Pipeline(stage_names=["noop"])
        pipeline.run(config=_make_config(name="manifest_test"), run_dir=tmp_path)

        manifest_path = tmp_path / "manifest.json"
        assert manifest_path.exists()

        manifest = json.loads(manifest_path.read_text())
        assert manifest["config_name"] == "manifest_test"
        assert len(manifest["stages"]) == 1
        assert manifest["stages"][0]["name"] == "noop"
        assert manifest["stages"][0]["metadata"] == {"k": "v"}
        # config is embedded so the manifest is self-describing
        assert manifest["config"]["name"] == "manifest_test"


# ---------- Error paths ----------


class TestPipelineErrorHandling:
    def test_stage_missing_required_input_raises(self, tmp_path):
        @register_stage("needs_a")
        class NeedsA(Stage):
            name = "needs_a"
            required_inputs = {"a"}
            produces: set[str] = set()

            def run(self, ctx, config):
                return StageResult()

        pipeline = Pipeline(stage_names=["needs_a"])
        with pytest.raises(KeyError, match="missing required context inputs"):
            pipeline.run(config=_make_config(), run_dir=tmp_path)

    def test_stage_returning_wrong_outputs_raises(self, tmp_path):
        @register_stage("liar")
        class LiarStage(Stage):
            name = "liar"
            required_inputs: set[str] = set()
            produces = {"declared_key"}  # but doesn't actually produce it

            def run(self, ctx, config):
                return StageResult(outputs={"different_key": 42})

        pipeline = Pipeline(stage_names=["liar"])
        with pytest.raises(ValueError, match="output mismatch"):
            pipeline.run(config=_make_config(), run_dir=tmp_path)

    def test_stage_returning_extra_outputs_raises(self, tmp_path):
        @register_stage("verbose")
        class VerboseStage(Stage):
            name = "verbose"
            required_inputs: set[str] = set()
            produces = {"a"}

            def run(self, ctx, config):
                # Produces 'a' as declared AND an extra 'sneaky' key
                return StageResult(outputs={"a": 1, "sneaky": 2})

        pipeline = Pipeline(stage_names=["verbose"])
        with pytest.raises(ValueError, match="Undeclared outputs.*sneaky"):
            pipeline.run(config=_make_config(), run_dir=tmp_path)

    def test_stage_returning_non_stage_result_raises(self, tmp_path):
        @register_stage("wrong_type")
        class WrongTypeStage(Stage):
            name = "wrong_type"
            required_inputs: set[str] = set()
            produces: set[str] = set()

            def run(self, ctx, config):
                return {"not": "a StageResult"}  # type: ignore[return-value]

        pipeline = Pipeline(stage_names=["wrong_type"])
        with pytest.raises(TypeError, match="expected StageResult"):
            pipeline.run(config=_make_config(), run_dir=tmp_path)

    def test_stage_exception_propagates(self, tmp_path):
        @register_stage("boom")
        class BoomStage(Stage):
            name = "boom"
            required_inputs: set[str] = set()
            produces: set[str] = set()

            def run(self, ctx, config):
                raise RuntimeError("intentional boom")

        pipeline = Pipeline(stage_names=["boom"])
        with pytest.raises(RuntimeError, match="intentional boom"):
            pipeline.run(config=_make_config(), run_dir=tmp_path)

    def test_failing_stage_does_not_prevent_later_recovery(self, tmp_path):
        """After a failed run, the pipeline object can still be reused."""
        @register_stage("flaky")
        class FlakyStage(Stage):
            name = "flaky"
            required_inputs: set[str] = set()
            produces = {"x"}
            calls = 0

            def run(self, ctx, config):
                FlakyStage.calls += 1
                if FlakyStage.calls == 1:
                    raise RuntimeError("first time only")
                return StageResult(outputs={"x": 99})

        pipeline = Pipeline(stage_names=["flaky"])
        with pytest.raises(RuntimeError):
            pipeline.run(config=_make_config(), run_dir=tmp_path)
        # Second time should succeed
        result = pipeline.run(config=_make_config(), run_dir=tmp_path)
        assert result.context.get("x") == 99


# ---------- Manifest details ----------


class TestManifest:
    def test_manifest_uses_json_safe_fallback_for_weird_values(self, tmp_path):
        """A stage that puts unserialisable data in metadata shouldn't crash."""

        class Weird:
            def __str__(self):
                return "weird-thing"

        @register_stage("weird_meta")
        class WeirdMetaStage(Stage):
            name = "weird_meta"
            required_inputs: set[str] = set()
            produces: set[str] = set()

            def run(self, ctx, config):
                return StageResult(metadata={"obj": Weird()})

        pipeline = Pipeline(stage_names=["weird_meta"])
        pipeline.run(config=_make_config(), run_dir=tmp_path)

        manifest = json.loads((tmp_path / "manifest.json").read_text())
        assert manifest["stages"][0]["metadata"]["obj"] == "weird-thing"


# ---------- PipelineResult shape ----------


class TestPipelineResult:
    def test_result_includes_final_context(self, tmp_path):
        @register_stage("produces_things")
        class P(Stage):
            name = "produces_things"
            required_inputs: set[str] = set()
            produces = {"out"}

            def run(self, ctx, config):
                return StageResult(outputs={"out": "hello"})

        pipeline = Pipeline(stage_names=["produces_things"])
        result = pipeline.run(config=_make_config(), run_dir=tmp_path)

        assert isinstance(result, PipelineResult)
        assert isinstance(result.context, PipelineContext)
        assert result.context.get("out") == "hello"


# ---------- Cache-skip regression tests ----------


class TestCacheSkipBehavior:
    """Regression tests for a bug found 2026-05-14: when caching was on
    and `_try_load_cache` returned an empty dict (nothing cached), the
    orchestrator was *skipping* the stage instead of running it live.
    The stage looked like "from cache" in logs and produced nothing —
    no error, no output, downstream stages had no inputs.

    The fix requires `len(cached_outputs) == len(cacheable)` (and cacheable
    must be non-empty) before the skip path is taken.
    """

    def test_use_cache_off_runs_stage_normally(self, tmp_path):
        """Sanity: cache off → stage runs every time, no cache logic."""
        run_log = []

        @register_stage("counts_calls")
        class S(Stage):
            name = "counts_calls"
            required_inputs: set[str] = set()
            produces = {"counter"}

            def run(self, ctx, config):
                run_log.append("ran")
                return StageResult(outputs={"counter": len(run_log)})

        pipeline = Pipeline(stage_names=["counts_calls"], use_cache=False)
        result = pipeline.run(config=_make_config(), run_dir=tmp_path)
        assert run_log == ["ran"]
        assert result.context.get("counter") == 1

    def test_use_cache_on_with_empty_cache_still_runs_stage(self, tmp_path):
        """Cache on, nothing cached → stage MUST run live, not skip.

        This is the explicit regression test for the bug. With the
        broken logic, the stage would be skipped silently and `counter`
        would be missing from the context, or zero.
        """
        run_log = []

        @register_stage("counts_calls_2")
        class S(Stage):
            name = "counts_calls_2"
            required_inputs: set[str] = set()
            produces = {"counter"}

            def run(self, ctx, config):
                run_log.append("ran")
                return StageResult(outputs={"counter": 42})

        # use_cache=True but the stage produces a non-ee.Image value;
        # the cache check will find nothing in GEE (and we don't even
        # touch GEE here because asset_exists short-circuits — actually
        # it tries to hit GEE. We have to mock that.)
        from unittest.mock import patch

        with patch("fmu.pipeline.asset_exists", return_value=False), \
             patch("fmu.pipeline.cached_asset_path", return_value="fake/path"):
            pipeline = Pipeline(stage_names=["counts_calls_2"], use_cache=True)
            result = pipeline.run(config=_make_config(), run_dir=tmp_path)

        # The critical assertions: the stage actually ran, and the output
        # made it into the context.
        assert run_log == ["ran"], "Stage was skipped instead of running"
        assert result.context.get("counter") == 42, "Stage output not in context"

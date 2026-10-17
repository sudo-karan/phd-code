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

These tests use trivial stages (numbers, strings); no GEE. The fast suite.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import ClassVar
from unittest.mock import MagicMock, patch

import ee
import pytest

from fmu.pipeline import Pipeline, PipelineResult
from fmu.stages.base import (
    DisplayLayer,
    LegendEntry,
    PipelineContext,
    Stage,
    StageResult,
    _clear_registry_for_testing,
    _stage_registry,
    register_stage,
)
from fmu.utils.caching import ExportTaskInfo


@pytest.fixture(autouse=True)
def reset_registry():
    """Every test here starts with an empty stage registry, and the registry it
    found is put back afterwards.

    The real stages register themselves once, when their modules are imported.
    A fixture that only empties the registry leaves it empty for every test
    file that runs later in the same process, so whether those pass depends on
    the order of the files (`pytest tests/test_pipeline.py tests/test_merge_stage.py`
    used to fail one test)."""
    found = dict(_stage_registry)
    _clear_registry_for_testing()
    try:
        yield
    finally:
        _clear_registry_for_testing()
        _stage_registry.update(found)


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

    def test_manifest_records_which_code_ran(self, tmp_path):
        """Every run manifest names the git commit it ran from and says whether
        the tree had uncommitted changes (CLAUDE.md, "Results"). The commit
        itself differs from one checkout to the next, so only the shape is
        asserted here; tests/test_provenance.py tests the values."""

        @register_stage("noop")
        class NoOpStage(Stage):
            name = "noop"
            required_inputs: set[str] = set()
            produces: set[str] = set()

            def run(self, ctx, config):
                return StageResult()

        Pipeline(stage_names=["noop"]).run(
            config=_make_config(name="git_test"), run_dir=tmp_path
        )
        git = json.loads((tmp_path / "manifest.json").read_text())["git"]
        assert set(git) == {
            "commit", "dirty", "modified", "modified_truncated",
            "untracked", "untracked_truncated", "root", "error",
        }
        assert git["commit"] is None or len(git["commit"]) == 40
        assert git["dirty"] in (True, False, None)


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
    The stage looked like "from cache" in logs and produced nothing.
    No error, no output, downstream stages had no inputs.

    The fix requires `len(cached_outputs) == len(cacheable)` (and cacheable
    must be non-empty) before the skip path is taken.
    """

    def test_use_cache_off_runs_stage_normally(self, tmp_path):
        """Sanity: cache off to stage runs every time, no cache logic."""
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
        """Cache on, nothing cached to stage MUST run live, not skip.

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
        # touch GEE here because asset_exists short-circuits; actually
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


class TestExplicitNoCaching:
    """Regression test for a bug found 2026-05-14: when a stage declares
    `cacheable_outputs = set()` to mean "nothing in this stage should
    be cached as a GEE asset" (because it produces Python data rather
    than ee.Images), the orchestrator was treating the empty set as
    falsy and falling back to caching ALL produces; which then warned
    about non-ee.Image values being uncacheable.

    The fix: distinguish "stage explicitly set cacheable_outputs to set()"
    from "stage didn't override it at all" via class.__dict__ inspection.
    """

    def test_explicit_empty_cacheable_outputs_skips_export(self, tmp_path):
        """Stage with cacheable_outputs=set() should not attempt export.

        We assert by checking that no export-related code runs even when
        the cached asset path doesn't exist (since the stage isn't trying
        to cache anything).
        """
        run_log = []

        @register_stage("opts_out_of_caching")
        class S(Stage):
            name = "opts_out_of_caching"
            required_inputs: set[str] = set()
            produces = {"py_data"}
            cacheable_outputs: ClassVar[set[str]] = set()  # explicit opt-out

            def run(self, ctx, config):
                run_log.append("ran")
                return StageResult(outputs={"py_data": [1, 2, 3]})

        from unittest.mock import patch

        # If the orchestrator were still trying to cache, it would call
        # asset_exists. We mock it and assert it's NOT called when the
        # stage declares cacheable_outputs=set().
        with patch("fmu.pipeline.asset_exists") as mock_exists, \
             patch("fmu.pipeline.cached_asset_path", return_value="fake/path"):
            pipeline = Pipeline(stage_names=["opts_out_of_caching"], use_cache=True)
            result = pipeline.run(config=_make_config(), run_dir=tmp_path)

        # Stage ran and put data in context
        assert run_log == ["ran"]
        assert result.context.get("py_data") == [1, 2, 3]
        # The orchestrator never tried to check cache existence
        # because cacheable_outputs is explicitly empty
        assert mock_exists.call_count == 0, (
            f"asset_exists called {mock_exists.call_count} times; "
            "orchestrator tried to cache when stage opted out"
        )

    def test_subclass_inherits_cacheable_outputs(self, tmp_path):
        """Regression test for a bug found 2026-05-19: when a subclass
        inherits cacheable_outputs through MRO (rather than redeclaring it
        in its own __dict__), the orchestrator was falling back to the
        "default to caching all produces" behavior; causing it to try
        to cache the parent's non-image outputs.

        The fix: _resolve_cacheable_outputs walks the MRO instead of only
        checking the direct class's __dict__.

        This bit us when the smoke test's _SmokeExport subclass inherited
        ExportStage's cacheable_outputs=set() but had it ignored.
        """
        run_log = []

        @register_stage("parent_opts_out")
        class Parent(Stage):
            name = "parent_opts_out"
            required_inputs: ClassVar[set[str]] = set()
            produces = {"py_data"}
            cacheable_outputs: ClassVar[set[str]] = set()  # opt out

            def run(self, ctx, config):
                run_log.append("parent")
                return StageResult(outputs={"py_data": [1, 2, 3]})

        # Subclass: register under a different name. Note that the subclass
        # does NOT redeclare cacheable_outputs; it inherits the empty set
        # through MRO. The orchestrator must still honor that.
        @register_stage("child_inherits_optout")
        class Child(Parent):
            name = "child_inherits_optout"
            # cacheable_outputs intentionally not declared; inherited

            def run(self, ctx, config):
                run_log.append("child")
                return StageResult(outputs={"py_data": ["a", "b"]})

        from unittest.mock import patch

        with patch("fmu.pipeline.asset_exists") as mock_exists, \
             patch("fmu.pipeline.cached_asset_path", return_value="fake/path"):
            pipeline = Pipeline(stage_names=["child_inherits_optout"], use_cache=True)
            result = pipeline.run(config=_make_config(), run_dir=tmp_path)

        # Child stage ran, inherited opt-out worked
        assert run_log == ["child"]
        assert result.context.get("py_data") == ["a", "b"]
        # The orchestrator never checked cache because cacheable_outputs is
        # the empty set, inherited from Parent through MRO
        assert mock_exists.call_count == 0, (
            f"asset_exists called {mock_exists.call_count} times; "
            "MRO walk didn't find inherited cacheable_outputs=set()"
        )


# ---------- The cache switches: use_cache and submit_exports ----------


class _FakeImage(ee.Image):
    """An ee.Image in type only.

    The orchestrator exports an output only if it is an ee.Image, and building a
    real one needs an initialised client. This passes that isinstance check and
    does nothing else: __init__ deliberately does not call ee.Image's.
    """

    def __init__(self, tag: str) -> None:
        self.tag = tag

    def __repr__(self) -> str:
        return f"<fake image: {self.tag}>"

    __str__ = __repr__


class _FakeGeometry(ee.Geometry):
    """An ee.Geometry in type only, for the `roi` the export path insists on."""

    def __init__(self) -> None:
        pass

    def __repr__(self) -> str:
        return "<fake roi>"

    __str__ = __repr__


def _asset(stage: str, key: str) -> str:
    return f"projects/p/assets/fmu/cfg/{stage}/{key}"


_OLD = _asset("two_images", "old_key")
_NEW = _asset("two_images", "new_key")


@contextmanager
def _fake_cache(existing: set[str]):
    """Replace the orchestrator's four cache calls, as the tests above replace
    two of them. `existing` is the set of asset paths that are "in the cache".

    Yields the mock standing in for `start_export`, so a test can say how many
    export tasks the run tried to submit and for what.
    """
    task_numbers = iter(range(1, 100))

    # crs and crs_transform come only in the per-step layout (an empty cache holds
    # no legacy asset, so a run on it takes that layout).
    def fake_start_export(*, image, asset_path, roi, scale, description, **grid):
        return ExportTaskInfo(
            task_id=f"TASK{next(task_numbers)}",
            asset_path=asset_path,
            description=description,
        )

    with patch(
        "fmu.pipeline.cached_asset_path",
        side_effect=lambda config_name, stage, key, fingerprint=None: _asset(stage, key),
    ), patch(
        "fmu.pipeline.asset_exists", side_effect=lambda path: path in existing
    ), patch(
        "fmu.pipeline.load_cached_image",
        side_effect=lambda path: _FakeImage(f"cached {path}"),
    ), patch(
        "fmu.pipeline.analysis_grid_export_args",
        return_value={"crs": "EPSG:32645", "crs_transform": [10.0, 0.0, 0.0, 0.0, 10.0, 0.0]},
    ), patch(
        "fmu.pipeline.start_export", side_effect=fake_start_export
    ) as start_export:
        yield start_export


def _register_two_image_stage(run_log: list[str]) -> None:
    """A stage with two cacheable image outputs, and one that reads them.

    This is the shape of masking after `mask_provenance` was added: `old_key`
    was cached by earlier runs, `new_key` was not. `new_key` carries a display
    layer so the manifest's asset record can be checked too.
    """

    @register_stage("two_images")
    class TwoImages(Stage):
        name = "two_images"
        required_inputs = {"roi"}
        produces = {"old_key", "new_key"}
        display_layers = (
            DisplayLayer(
                "new_key", "b", "New", "the output added later",
                legend=(LegendEntry(0, "out", "000000"), LegendEntry(1, "in", "ffffff")),
            ),
        )

        def run(self, ctx, config):
            run_log.append("ran")
            return StageResult(
                outputs={
                    "old_key": _FakeImage("live old_key"),
                    "new_key": _FakeImage("live new_key"),
                }
            )

    @register_stage("downstream")
    class Downstream(Stage):
        name = "downstream"
        required_inputs = {"old_key", "new_key"}
        produces = {"received"}
        cacheable_outputs: ClassVar[set[str]] = set()

        def run(self, ctx, config):
            return StageResult(
                outputs={
                    "received": {k: ctx.get(k).tag for k in ("old_key", "new_key")}
                }
            )


def _run_two_images(tmp_path, existing: set[str], **pipeline_kwargs):
    """Run two_images -> downstream against a fake cache holding `existing`.

    Returns (result, manifest, start_export mock, run log).
    """
    run_log: list[str] = []
    _register_two_image_stage(run_log)
    ctx = PipelineContext()
    ctx.set("roi", _FakeGeometry())
    with _fake_cache(existing) as start_export:
        result = Pipeline(
            stage_names=["two_images", "downstream"], use_cache=True, **pipeline_kwargs
        ).run(config=_make_config(), run_dir=tmp_path, initial_context=ctx)
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    return result, manifest, start_export, run_log


class TestSubmitExportsSwitch:
    """`Pipeline(stage_names, use_cache=True, submit_exports=False)` reads the
    cache and adds nothing to the Earth Engine task queue. The default
    (`submit_exports=True`) is the behaviour the cache has always had; each
    read-only test below has a default-run twin that shows the export it
    would otherwise have submitted, so "never called" cannot pass by accident.
    """

    def test_default_exports_everything_that_missed(self, tmp_path):
        result, manifest, start_export, run_log = _run_two_images(tmp_path, set())

        assert run_log == ["ran"]
        assert start_export.call_count == 2
        assert sorted(c.kwargs["asset_path"] for c in start_export.call_args_list) == [
            _NEW, _OLD,
        ]
        record = result.stages[0]
        assert record.cache_status == {
            "old_key": "miss-exported", "new_key": "miss-exported",
        }
        assert sorted(t["asset_path"] for t in record.export_tasks) == [_NEW, _OLD]
        assert all(t["task_id"].startswith("TASK") for t in record.export_tasks)
        assert manifest["use_cache"] is True and manifest["submit_exports"] is True

    def test_read_only_computes_what_missed_and_submits_nothing(self, tmp_path):
        result, manifest, start_export, run_log = _run_two_images(
            tmp_path, set(), submit_exports=False
        )

        # Both outputs missed, so the stage ran live and its outputs are used.
        assert run_log == ["ran"]
        assert result.context.get("old_key").tag == "live old_key"
        assert result.context.get("new_key").tag == "live new_key"
        assert result.context.get("received") == {
            "old_key": "live old_key", "new_key": "live new_key",
        }
        # Nothing was submitted, and the record says so.
        assert start_export.call_count == 0
        record = result.stages[0]
        assert record.cache_status == {"old_key": "miss", "new_key": "miss"}
        assert record.export_tasks == []
        assert manifest["use_cache"] is True and manifest["submit_exports"] is False
        assert manifest["stages"][0]["cache_status"] == {
            "old_key": "miss", "new_key": "miss",
        }
        assert manifest["stages"][0]["export_tasks"] == []

    def test_read_only_still_reads_and_uses_the_cache(self, tmp_path):
        result, manifest, start_export, run_log = _run_two_images(
            tmp_path, {_OLD, _NEW}, submit_exports=False
        )

        # Every output hit: the stage is skipped and the cached images are used.
        assert run_log == []
        assert result.context.get("received") == {
            "old_key": f"cached {_OLD}", "new_key": f"cached {_NEW}",
        }
        record = result.stages[0]
        assert record.metadata == {"source": "cache"}
        assert record.cache_status == {"old_key": "hit", "new_key": "hit"}
        assert record.export_tasks == []
        assert start_export.call_count == 0

    def test_partial_hit_exports_only_the_output_that_missed(self, tmp_path):
        """Default run on a config cached before `new_key` existed: the stage
        runs live, but what goes downstream for `old_key` is the cached asset,
        and only `new_key` is exported."""
        result, manifest, start_export, run_log = _run_two_images(tmp_path, {_OLD})

        assert run_log == ["ran"]
        assert result.context.get("received") == {
            "old_key": f"cached {_OLD}", "new_key": "live new_key",
        }
        assert start_export.call_count == 1
        exported = start_export.call_args.kwargs
        assert exported["asset_path"] == _NEW
        assert exported["image"].tag == "live new_key"
        record = result.stages[0]
        assert record.cache_status == {"old_key": "hit", "new_key": "miss-exported"}
        assert [t["asset_path"] for t in record.export_tasks] == [_NEW]

    def test_partial_hit_read_only_uses_the_cached_output_and_exports_nothing(
        self, tmp_path
    ):
        """The same config read with `submit_exports=False`: downstream still
        gets the cached `old_key`, `new_key` is computed for this run only."""
        result, manifest, start_export, run_log = _run_two_images(
            tmp_path, {_OLD}, submit_exports=False
        )

        assert run_log == ["ran"]
        assert result.context.get("old_key").tag == f"cached {_OLD}"
        assert result.context.get("new_key").tag == "live new_key"
        assert result.context.get("received") == {
            "old_key": f"cached {_OLD}", "new_key": "live new_key",
        }
        assert start_export.call_count == 0
        record = result.stages[0]
        assert record.cache_status == {"old_key": "hit", "new_key": "miss"}
        assert record.export_tasks == []

    @pytest.mark.parametrize(
        ("existing", "kwargs", "status"),
        [
            (set(), {}, "miss-exported"),
            (set(), {"submit_exports": False}, "miss"),
            ({_OLD, _NEW}, {"submit_exports": False}, "hit"),
        ],
        ids=["exported", "read_only_miss", "hit"],
    )
    def test_manifest_says_whether_a_display_layer_has_an_asset(
        self, tmp_path, existing, kwargs, status
    ):
        """A map script reads this to decide between drawing from the asset and
        computing the layer live: under "miss" there is nothing at the path."""
        _, manifest, _, _ = _run_two_images(tmp_path, existing, **kwargs)
        layer = manifest["stages"][0]["transparency"]["display_layers"][0]
        assert layer["key"] == "new_key"
        assert layer["asset"] == _NEW
        assert layer["asset_status"] == status

    def test_read_only_makes_no_earth_engine_write(self, tmp_path):
        """One level down: the real `start_export` is left in place, and the
        two Earth Engine calls it makes (create a folder, start a task) are the
        things watched. The default run makes both; the read-only run neither.
        """

        def run(**pipeline_kwargs):
            _clear_registry_for_testing()
            _register_two_image_stage([])
            ctx = PipelineContext()
            ctx.set("roi", _FakeGeometry())
            task = MagicMock()
            task.id = "TASK1"
            with patch(
                "fmu.pipeline.cached_asset_path",
                side_effect=lambda config_name, stage, key, fingerprint=None: _asset(
                    stage, key
                ),
            ), patch("fmu.pipeline.asset_exists", return_value=False), patch(
                "fmu.utils.caching.asset_exists", return_value=False
            ), patch("fmu.utils.caching.ee.data.createFolder") as create_folder, patch(
                "fmu.utils.caching.ee.batch.Export.image.toAsset", return_value=task
            ) as to_asset, patch(
                "fmu.pipeline.analysis_grid_export_args",
                return_value={"crs": "EPSG:32645", "crs_transform": [10.0, 0, 0, 0, 10.0, 0]},
            ):
                result = Pipeline(
                    stage_names=["two_images"], use_cache=True, **pipeline_kwargs
                ).run(config=_make_config(), run_dir=tmp_path, initial_context=ctx)
            return result, create_folder, to_asset, task

        result, create_folder, to_asset, task = run()
        assert to_asset.call_count == 2
        assert task.start.call_count == 2
        assert create_folder.call_count > 0
        assert len(result.stages[0].export_tasks) == 2

        result, create_folder, to_asset, task = run(submit_exports=False)
        assert to_asset.call_count == 0
        assert task.start.call_count == 0
        assert create_folder.call_count == 0
        assert result.stages[0].export_tasks == []

    def test_read_only_refuses_a_stage_that_submits_its_own_tasks(self):
        """The export stage starts its Drive exports inside run(), where the
        orchestrator cannot stop them. A run that promised to submit nothing
        must not include it."""

        @register_stage("export")
        class FakeExport(Stage):
            name = "export"
            required_inputs: set[str] = set()
            produces: set[str] = set()

            def run(self, ctx, config):
                return StageResult()

        with pytest.raises(ValueError, match="submit their own"):
            Pipeline(stage_names=["export"], use_cache=True, submit_exports=False)
        with pytest.raises(ValueError, match="submit their own"):
            Pipeline(stage_names=["export"], submit_exports=False)
        # The default is unchanged: the stage is accepted, cache on or off.
        Pipeline(stage_names=["export"], use_cache=True)
        Pipeline(stage_names=["export"])

    def test_submit_exports_is_keyword_only(self):
        """`Pipeline(names, True, False)` would not say which switch is which."""

        @register_stage("kw_only")
        class S(Stage):
            name = "kw_only"
            required_inputs: set[str] = set()
            produces: set[str] = set()

            def run(self, ctx, config):
                return StageResult()

        with pytest.raises(TypeError):
            Pipeline(["kw_only"], True, False)  # type: ignore[misc]
        assert Pipeline(["kw_only"], True, submit_exports=False).submit_exports is False

    def test_manifest_records_the_switches_when_left_at_their_defaults(self, tmp_path):
        @register_stage("defaults")
        class S(Stage):
            name = "defaults"
            required_inputs: set[str] = set()
            produces: set[str] = set()

            def run(self, ctx, config):
                return StageResult()

        pipeline = Pipeline(stage_names=["defaults"])
        assert (pipeline.use_cache, pipeline.submit_exports) == (False, True)
        pipeline.run(config=_make_config(), run_dir=tmp_path)

        manifest = json.loads((tmp_path / "manifest.json").read_text())
        assert manifest["use_cache"] is False
        assert manifest["submit_exports"] is True
        assert manifest["stages"][0]["cache_status"] == {}
        assert manifest["stages"][0]["export_tasks"] == []

    def test_read_only_without_the_cache_never_looks_at_it(self, tmp_path):
        run_log: list[str] = []
        _register_two_image_stage(run_log)
        ctx = PipelineContext()
        ctx.set("roi", _FakeGeometry())
        with _fake_cache({_OLD, _NEW}) as start_export, patch(
            "fmu.pipeline.asset_exists"
        ) as exists:
            result = Pipeline(
                stage_names=["two_images"], use_cache=False, submit_exports=False
            ).run(config=_make_config(), run_dir=tmp_path, initial_context=ctx)

        assert run_log == ["ran"]
        assert exists.call_count == 0 and start_export.call_count == 0
        assert result.context.get("old_key").tag == "live old_key"
        assert result.stages[0].cache_status == {}

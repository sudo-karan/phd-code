"""
Tests for fmu.stages.base.

The Stage interface is load-bearing — every future concrete stage builds on
these primitives. Thorough coverage here saves us from architectural
refactors later.
"""

from __future__ import annotations

import pytest

from fmu.stages.base import (
    PipelineContext,
    Stage,
    StageResult,
    _clear_registry_for_testing,
    get_stage_class,
    list_registered_stages,
    register_stage,
)

# ---------- PipelineContext ----------


class TestPipelineContext:
    def test_starts_empty(self):
        ctx = PipelineContext()
        assert ctx.keys() == set()

    def test_set_then_get(self):
        ctx = PipelineContext()
        ctx.set("roi", "fake_geometry")
        assert ctx.get("roi") == "fake_geometry"

    def test_has(self):
        ctx = PipelineContext()
        assert not ctx.has("roi")
        ctx.set("roi", "x")
        assert ctx.has("roi")

    def test_get_missing_raises_with_helpful_message(self):
        ctx = PipelineContext()
        ctx.set("present_key", 1)
        with pytest.raises(KeyError, match="missing_key"):
            ctx.get("missing_key")
        # Error message should list what's available
        try:
            ctx.get("missing_key")
        except KeyError as e:
            assert "present_key" in str(e)

    def test_set_twice_raises(self):
        """Write-once semantics: a stage cannot clobber another stage's output."""
        ctx = PipelineContext()
        ctx.set("ndvi", "first")
        with pytest.raises(KeyError, match="already set"):
            ctx.set("ndvi", "second")

    def test_keys_returns_set(self):
        ctx = PipelineContext()
        ctx.set("a", 1)
        ctx.set("b", 2)
        assert ctx.keys() == {"a", "b"}

    def test_keys_returns_copy_not_view(self):
        """Mutating the returned set must not affect the context."""
        ctx = PipelineContext()
        ctx.set("a", 1)
        keys = ctx.keys()
        keys.add("evil_key")
        # ctx.keys() is a method that returns a fresh set, not a dict-keys view.
        assert "evil_key" not in ctx.keys()  # noqa: SIM118

    def test_repr_lists_keys(self):
        ctx = PipelineContext()
        ctx.set("foo", 1)
        ctx.set("bar", 2)
        r = repr(ctx)
        assert "foo" in r and "bar" in r


# ---------- StageResult ----------


class TestStageResult:
    def test_defaults_are_empty(self):
        r = StageResult()
        assert r.outputs == {}
        assert r.metadata == {}
        assert r.warnings == []

    def test_can_set_outputs(self):
        r = StageResult(outputs={"x": 1})
        assert r.outputs == {"x": 1}

    def test_can_set_metadata(self):
        r = StageResult(metadata={"elapsed_sec": 1.23})
        assert r.metadata["elapsed_sec"] == 1.23

    def test_can_append_warnings(self):
        r = StageResult()
        r.warnings.append("S1 had only 3 images in this window")
        assert len(r.warnings) == 1

    def test_default_factories_isolated(self):
        """Each instance gets fresh dict/list, not shared class-level state."""
        r1 = StageResult()
        r2 = StageResult()
        r1.outputs["x"] = 1
        r1.warnings.append("warn")
        assert r2.outputs == {}
        assert r2.warnings == []


# ---------- Stage subclass declarations ----------


class TestStageSubclassing:
    """Tests around the rules subclasses must follow."""

    def setup_method(self):
        _clear_registry_for_testing()

    def teardown_method(self):
        _clear_registry_for_testing()

    def test_concrete_subclass_must_set_name(self):
        with pytest.raises(TypeError, match="must set class attribute `name`"):

            class BadStage(Stage):
                # No name
                required_inputs: set[str] = set()
                produces: set[str] = set()

                def run(self, ctx, config):
                    return StageResult()

    def test_subclass_with_non_set_required_inputs_raises(self):
        with pytest.raises(TypeError, match="`required_inputs` must be a set"):

            class BadStage(Stage):
                name = "bad"
                required_inputs = ["a", "b"]  # type: ignore[assignment] # list, not set
                produces: set[str] = set()

                def run(self, ctx, config):
                    return StageResult()

    def test_subclass_with_non_set_produces_raises(self):
        with pytest.raises(TypeError, match="`produces` must be a set"):

            class BadStage(Stage):
                name = "bad"
                required_inputs: set[str] = set()
                produces = "x"  # type: ignore[assignment] # str, not set

                def run(self, ctx, config):
                    return StageResult()

    def test_subclass_missing_run_is_still_abstract(self):
        class StillAbstract(Stage):
            # No run() override — this stays abstract; subclass-validation
            # is skipped because abstractmethods are still unimplemented.
            name = "x"

        with pytest.raises(TypeError):
            StillAbstract()  # type: ignore[abstract]

    def test_well_formed_subclass_succeeds(self):
        class Good(Stage):
            name = "good"
            required_inputs = {"a"}
            produces = {"b"}

            def run(self, ctx, config):
                return StageResult(outputs={"b": ctx.get("a") + 1})

        # Class definition does not raise
        instance = Good()
        assert instance.name == "good"


# ---------- Stage.validate() ----------


class TestStageValidate:
    def setup_method(self):
        _clear_registry_for_testing()

    def teardown_method(self):
        _clear_registry_for_testing()

    def test_validate_passes_when_inputs_present(self):
        class S(Stage):
            name = "s"
            required_inputs = {"a", "b"}
            produces: set[str] = set()

            def run(self, ctx, config):
                return StageResult()

        ctx = PipelineContext()
        ctx.set("a", 1)
        ctx.set("b", 2)
        S().validate(ctx, None)  # no raise

    def test_validate_raises_on_missing_input(self):
        class S(Stage):
            name = "s2"
            required_inputs = {"a", "b"}
            produces: set[str] = set()

            def run(self, ctx, config):
                return StageResult()

        ctx = PipelineContext()
        ctx.set("a", 1)
        # missing "b"
        with pytest.raises(KeyError, match="b"):
            S().validate(ctx, None)

    def test_subclass_can_extend_validate(self):
        class StrictStage(Stage):
            name = "strict"
            required_inputs = {"a"}
            produces: set[str] = set()

            def validate(self, ctx, config):
                super().validate(ctx, config)
                a = ctx.get("a")
                if not isinstance(a, int):
                    raise TypeError("a must be int")

            def run(self, ctx, config):
                return StageResult()

        ctx = PipelineContext()
        ctx.set("a", "not an int")
        with pytest.raises(TypeError, match="a must be int"):
            StrictStage().validate(ctx, None)


# ---------- Registry ----------


class TestRegistry:
    def setup_method(self):
        _clear_registry_for_testing()

    def teardown_method(self):
        _clear_registry_for_testing()

    def test_register_and_lookup(self):
        @register_stage("opt_phen")
        class OptPhenStage(Stage):
            name = "opt_phen"
            required_inputs: set[str] = set()
            produces: set[str] = set()

            def run(self, ctx, config):
                return StageResult()

        assert get_stage_class("opt_phen") is OptPhenStage

    def test_list_registered_stages(self):
        @register_stage("stage_a")
        class A(Stage):
            name = "stage_a"
            required_inputs: set[str] = set()
            produces: set[str] = set()

            def run(self, ctx, config):
                return StageResult()

        @register_stage("stage_b")
        class B(Stage):
            name = "stage_b"
            required_inputs: set[str] = set()
            produces: set[str] = set()

            def run(self, ctx, config):
                return StageResult()

        assert list_registered_stages() == ["stage_a", "stage_b"]

    def test_register_non_stage_class_raises(self):
        with pytest.raises(TypeError, match="must subclass Stage"):

            @register_stage("not_a_stage")
            class NotAStage:
                name = "not_a_stage"

    def test_register_name_mismatch_raises(self):
        with pytest.raises(ValueError, match="doesn't match"):

            @register_stage("decorator_says_x")
            class S(Stage):
                name = "class_says_y"  # mismatch
                required_inputs: set[str] = set()
                produces: set[str] = set()

                def run(self, ctx, config):
                    return StageResult()

    def test_register_same_name_twice_raises(self):
        @register_stage("dup")
        class First(Stage):
            name = "dup"
            required_inputs: set[str] = set()
            produces: set[str] = set()

            def run(self, ctx, config):
                return StageResult()

        with pytest.raises(ValueError, match="already registered"):

            @register_stage("dup")
            class Second(Stage):
                name = "dup"
                required_inputs: set[str] = set()
                produces: set[str] = set()

                def run(self, ctx, config):
                    return StageResult()

    def test_re_register_same_class_is_ok(self):
        """Decorating the same class twice (e.g. on import reload) shouldn't fail."""

        @register_stage("idempotent")
        class S(Stage):
            name = "idempotent"
            required_inputs: set[str] = set()
            produces: set[str] = set()

            def run(self, ctx, config):
                return StageResult()

        # Re-register the same class — should be a no-op, not raise
        register_stage("idempotent")(S)
        assert get_stage_class("idempotent") is S

    def test_lookup_unregistered_raises(self):
        with pytest.raises(KeyError, match="No stage registered"):
            get_stage_class("does_not_exist")


# ---------- End-to-end smoke test of the contract ----------


class TestStageContract:
    """A miniature stage exercising the full pattern, end to end."""

    def setup_method(self):
        _clear_registry_for_testing()

    def teardown_method(self):
        _clear_registry_for_testing()

    def test_full_stage_lifecycle(self):
        """Define a stage, register it, look it up, validate, run, merge."""

        @register_stage("doubler")
        class DoublerStage(Stage):
            name = "doubler"
            required_inputs = {"x"}
            produces = {"x_doubled"}

            def run(self, ctx, config):
                return StageResult(
                    outputs={"x_doubled": ctx.get("x") * 2},
                    metadata={"factor": 2},
                )

        # Look it up
        cls = get_stage_class("doubler")
        stage = cls()

        # Set up context with the required input
        ctx = PipelineContext()
        ctx.set("x", 21)

        # Validate (no raise)
        stage.validate(ctx, None)

        # Run
        result = stage.run(ctx, None)
        assert result.outputs == {"x_doubled": 42}
        assert result.metadata == {"factor": 2}

        # Merge into context (simulating what the orchestrator does)
        for k, v in result.outputs.items():
            ctx.set(k, v)
        assert ctx.get("x_doubled") == 42

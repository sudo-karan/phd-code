"""
Tests for fmu.stages.base.

The Stage interface is load-bearing; every future concrete stage builds on
these primitives. Thorough coverage here saves us from architectural
refactors later.
"""

from __future__ import annotations

import pytest

from fmu.stages.base import (
    DisplayLayer,
    LegendEntry,
    PipelineContext,
    Stage,
    StageResult,
    SummaryNumber,
    _clear_registry_for_testing,
    get_stage_class,
    list_registered_stages,
    register_stage,
    transparency_gaps,
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
            # No run() override; this stays abstract; subclass-validation
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
        with pytest.raises(ValueError, match="has name="):

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

        # Re-register the same class; should be a no-op, not raise
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


# ---------- Transparency declarations: the pieces ----------
#
# What a stage may declare about itself (display layers, summary numbers) and
# the checks made on a declaration. Which stages must declare something, and
# what the orchestrator does with it, is in test_transparency_contract.py.


def _two_class_legend() -> tuple[LegendEntry, ...]:
    return (LegendEntry(0, "out", "000000"), LegendEntry(1, "in", "ffffff"))


class TestLegendEntry:
    def test_holds_value_label_colour(self):
        e = LegendEntry(3, "built-up", "d73027")
        assert (e.value, e.label, e.color) == (3, "built-up", "d73027")

    @pytest.mark.parametrize("color", ["#d73027", "d7302", "d73027ff", "red", ""])
    def test_colour_must_be_six_hex_digits(self, color):
        """Earth Engine takes palettes without the '#'; a typo here would
        otherwise only show up when someone draws the layer."""
        with pytest.raises(ValueError, match="six hex digits"):
            LegendEntry(1, "x", color)

    @pytest.mark.parametrize("value", [1.5, "1", True, None])
    def test_value_must_be_an_int(self, value):
        with pytest.raises(TypeError, match="must be an int"):
            LegendEntry(value, "x", "000000")


class TestDisplayLayer:
    def test_categorical_palette_follows_the_legend_value_by_value(self):
        layer = DisplayLayer(
            "k", "b", "T", "d",
            legend=(LegendEntry(1, "one", "aaaaaa"), LegendEntry(4, "four", "bbbbbb")),
        )
        vis = layer.vis_params()
        assert (vis["min"], vis["max"]) == (1, 4)
        # Values 2 and 3 have no legend entry and are drawn black, so 4 still
        # gets its own colour rather than sliding down the palette.
        assert vis["palette"] == ["aaaaaa", "000000", "000000", "bbbbbb"]
        assert vis["bands"] == ["b"]

    def test_palette_does_not_depend_on_the_order_entries_are_listed_in(self):
        a = DisplayLayer("k", "b", "T", "d", legend=_two_class_legend())
        b = DisplayLayer("k", "b", "T", "d", legend=tuple(reversed(_two_class_legend())))
        assert a.vis_params() == b.vis_params()

    def test_a_single_class_still_gets_a_range_earth_engine_can_stretch(self):
        layer = DisplayLayer("k", "b", "T", "d", legend=(LegendEntry(7, "only", "abcdef"),))
        vis = layer.vis_params()
        assert vis["min"] < vis["max"]
        assert vis["palette"][0] == "abcdef"
        assert len(vis["palette"]) == vis["max"] - vis["min"] + 1

    def test_continuous_layer_uses_its_vis_and_names_its_band(self):
        layer = DisplayLayer(
            "k", "height", "T", "d", vis={"min": 0, "max": 30, "palette": ["ffffff", "006400"]}
        )
        assert layer.vis_params() == {
            "bands": ["height"], "min": 0, "max": 30, "palette": ["ffffff", "006400"],
        }

    def test_a_layer_nobody_can_draw_is_rejected(self):
        with pytest.raises(ValueError, match="neither a legend nor vis"):
            DisplayLayer("x", "b", "X", "a layer nobody can draw")

    def test_a_legend_and_vis_together_are_rejected(self):
        """The legend would win silently and the vis would be ignored."""
        with pytest.raises(ValueError, match="both a legend and vis"):
            DisplayLayer(
                "x", "b", "X", "d", legend=_two_class_legend(), vis={"min": 0, "max": 1}
            )

    def test_legend_values_must_be_unique(self):
        with pytest.raises(ValueError, match="must be unique"):
            DisplayLayer(
                "x", "b", "X", "d",
                legend=(LegendEntry(1, "a", "000000"), LegendEntry(1, "b", "ffffff")),
            )

    def test_a_legend_spanning_too_wide_a_range_is_rejected(self):
        with pytest.raises(ValueError, match="Remap the band"):
            DisplayLayer(
                "x", "b", "X", "d",
                legend=(LegendEntry(0, "a", "000000"), LegendEntry(5000, "b", "ffffff")),
            )

    def test_a_legend_given_as_a_list_is_stored_as_a_tuple(self):
        layer = DisplayLayer("x", "b", "X", "d", legend=list(_two_class_legend()))  # type: ignore[arg-type]
        assert layer.legend == _two_class_legend()

    def test_to_manifest_carries_everything_needed_to_draw_and_read_it(self):
        layer = DisplayLayer(
            "x", "b", "A title", "what it shows",
            legend=_two_class_legend(), legend_note="read this first",
        )
        assert layer.to_manifest() == {
            "key": "x",
            "band": "b",
            "title": "A title",
            "description": "what it shows",
            "vis": {"bands": ["b"], "min": 0, "max": 1, "palette": ["000000", "ffffff"]},
            "legend": [
                {"value": 0, "label": "out", "color": "000000"},
                {"value": 1, "label": "in", "color": "ffffff"},
            ],
            "legend_note": "read this first",
        }


class TestStageTransparencyDeclaration:
    """Checks made when a stage class is defined."""

    def setup_method(self):
        _clear_registry_for_testing()

    def teardown_method(self):
        _clear_registry_for_testing()

    def test_a_stage_declares_nothing_by_default(self):
        class Plain(Stage):
            name = "plain"
            produces = {"x"}

            def run(self, ctx, config):
                return StageResult(outputs={"x": 1})

        assert Plain.display_layers == ()
        assert Plain.summary_numbers == ()
        assert Plain().summarise(PipelineContext(), None) == {}

    def test_display_layer_must_name_a_produced_key(self):
        with pytest.raises(TypeError, match="not in `produces`"):

            class Bad(Stage):
                name = "bad_layer"
                produces = {"x"}
                display_layers = (
                    DisplayLayer("y", "b", "Y", "a key the stage does not produce",
                                 vis={"min": 0, "max": 1}),
                )

                def run(self, ctx, config):
                    return StageResult(outputs={"x": 1})

    def test_the_same_key_and_band_cannot_be_listed_twice(self):
        with pytest.raises(TypeError, match="same key and band twice"):

            class Bad(Stage):
                name = "dup_layer"
                produces = {"x"}
                display_layers = (
                    DisplayLayer("x", "b", "One", "d", legend=_two_class_legend()),
                    DisplayLayer("x", "b", "Two", "d", legend=_two_class_legend()),
                )

                def run(self, ctx, config):
                    return StageResult(outputs={"x": 1})

    def test_two_bands_of_one_key_are_two_layers(self):
        class Good(Stage):
            name = "two_bands"
            produces = {"x"}
            display_layers = (
                DisplayLayer("x", "b1", "One", "d", legend=_two_class_legend()),
                DisplayLayer("x", "b2", "Two", "d", legend=_two_class_legend()),
            )

            def run(self, ctx, config):
                return StageResult(outputs={"x": 1})

        assert [layer.band for layer in Good.display_layers] == ["b1", "b2"]

    def test_display_layers_must_be_display_layers(self):
        with pytest.raises(TypeError, match="must hold DisplayLayer"):

            class Bad(Stage):
                name = "bad_type"
                produces = {"x"}
                display_layers = ({"key": "x", "band": "b"},)  # type: ignore[assignment]

                def run(self, ctx, config):
                    return StageResult(outputs={"x": 1})

    def test_summary_numbers_need_a_summarise(self):
        with pytest.raises(TypeError, match="does not implement summarise"):

            class Bad(Stage):
                name = "bad_summary"
                produces = {"x"}
                summary_numbers = (SummaryNumber("n", "a number nobody computes"),)

                def run(self, ctx, config):
                    return StageResult(outputs={"x": 1})

    def test_a_summarise_needs_summary_numbers(self):
        """Without a declaration the orchestrator never calls it, and the
        numbers would be missing from the manifest with nothing to say why."""
        with pytest.raises(TypeError, match="declares no summary_numbers"):

            class Bad(Stage):
                name = "undeclared_summary"
                produces = {"x"}

                def run(self, ctx, config):
                    return StageResult(outputs={"x": 1})

                def summarise(self, ctx, config):
                    return {"n": 1}

    def test_summary_number_names_must_be_unique(self):
        with pytest.raises(TypeError, match="must be unique"):

            class Bad(Stage):
                name = "dup_summary"
                produces = {"x"}
                summary_numbers = (SummaryNumber("n", "one"), SummaryNumber("n", "two"))

                def run(self, ctx, config):
                    return StageResult(outputs={"x": 1})

                def summarise(self, ctx, config):
                    return {"n": 1}

    def test_summary_numbers_must_be_summary_numbers(self):
        with pytest.raises(TypeError, match="must hold SummaryNumber"):

            class Bad(Stage):
                name = "bad_number_type"
                produces = {"x"}
                summary_numbers = ("n",)  # type: ignore[assignment]

                def run(self, ctx, config):
                    return StageResult(outputs={"x": 1})

                def summarise(self, ctx, config):
                    return {"n": 1}

    def test_a_subclass_inherits_both_halves(self):
        class Parent(Stage):
            name = "summary_parent"
            produces = {"x"}
            summary_numbers = (SummaryNumber("n", "a number"),)

            def run(self, ctx, config):
                return StageResult(outputs={"x": 1})

            def summarise(self, ctx, config):
                return {"n": 1}

        class Child(Parent):
            name = "summary_child"

        assert Child.summary_numbers == Parent.summary_numbers
        assert Child().summarise(PipelineContext(), None) == {"n": 1}


class TestTransparencyGaps:
    def setup_method(self):
        _clear_registry_for_testing()

    def teardown_method(self):
        _clear_registry_for_testing()

    def test_a_stage_that_declares_neither_has_a_gap(self):
        class Silent(Stage):
            name = "silent"
            produces = {"x"}

            def run(self, ctx, config):
                return StageResult(outputs={"x": 1})

        gaps = transparency_gaps(Silent)
        assert len(gaps) == 1
        assert "neither display_layers nor summary_numbers" in gaps[0]
        assert gaps[0].startswith("silent:")

    def test_a_layer_alone_is_enough(self):
        class OnlyLayer(Stage):
            name = "only_layer"
            produces = {"x"}
            display_layers = (
                DisplayLayer("x", "b", "X", "what it shows", legend=_two_class_legend()),
            )

            def run(self, ctx, config):
                return StageResult(outputs={"x": 1})

        assert transparency_gaps(OnlyLayer) == []

    def test_a_number_alone_is_enough(self):
        class OnlyNumber(Stage):
            name = "only_number"
            produces = {"x"}
            summary_numbers = (SummaryNumber("n", "what it counts", "count"),)

            def run(self, ctx, config):
                return StageResult(outputs={"x": 1})

            def summarise(self, ctx, config):
                return {"n": 1}

        assert transparency_gaps(OnlyNumber) == []

    def test_a_declaration_that_does_not_say_what_it_is_has_gaps(self):
        class Mute(Stage):
            name = "mute"
            produces = {"x"}
            display_layers = (
                DisplayLayer(
                    "x", "b", "", " ",
                    legend=(LegendEntry(0, "", "000000"), LegendEntry(1, "in", "ffffff")),
                ),
            )
            summary_numbers = (SummaryNumber("n", ""),)

            def run(self, ctx, config):
                return StageResult(outputs={"x": 1})

            def summarise(self, ctx, config):
                return {"n": 1}

        gaps = transparency_gaps(Mute)
        assert any("x.b has no title" in g for g in gaps)
        assert any("x.b has no description" in g for g in gaps)
        assert any("no label for value 0" in g for g in gaps)
        assert any("'n' has no description" in g for g in gaps)
        assert len(gaps) == 4

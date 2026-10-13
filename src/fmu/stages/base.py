"""Stage contract: PipelineContext, StageResult, Stage, registry.

See docs/design_notes.md for the rationale behind the context-dict +
required_inputs/produces pattern.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, ClassVar

# ---------------------------------------------------------------------
# Transparency contract
#
# Each stage can say, in a form a script or a UI can read without knowing the
# stage, what it has to show for itself:
#
#   display_layers   images worth looking at, each with the context key and band
#                    it lives on, how to draw it, and a legend
#   summary_numbers  the few numbers that say what the stage did (what went in,
#                    what came out, what changed), computed by `summarise()`
#
# The orchestrator writes both into the run manifest. The aim is one legible
# account per step, not every band as a toggle: a stage declares the layers that
# explain its decision, not everything it computes.
#
# A declaration that is malformed (a layer on a key the stage does not produce,
# a colour that is not a colour, a number nobody computes) is rejected when the
# class is defined. A declaration that is missing is not an error here:
# `transparency_gaps` reports it, and tests/test_transparency_contract.py lists
# the stages that must have none.
# ---------------------------------------------------------------------

_HEX_COLOR_RE = re.compile(r"^[0-9a-fA-F]{6}$")

# Colour for a value inside a legend's range that no entry names.
_LEGEND_GAP_COLOR = "000000"

# A categorical palette is written out one colour per integer from the lowest
# legend value to the highest. Beyond this span that stops being a legend; remap
# the band to compact codes first.
_MAX_LEGEND_SPAN = 255


@dataclass(frozen=True)
class LegendEntry:
    """One class of a categorical layer: the pixel value, what it means, its colour."""

    value: int
    label: str
    color: str  # six hex digits, no leading '#', as Earth Engine palettes are written

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not isinstance(self.value, int):
            raise TypeError(
                f"LegendEntry {self.label!r}: value must be an int, got {self.value!r}."
            )
        if not _HEX_COLOR_RE.fullmatch(self.color):
            raise ValueError(
                f"LegendEntry {self.label!r}: color must be six hex digits with no "
                f"leading '#', got {self.color!r}."
            )


@dataclass(frozen=True)
class DisplayLayer:
    """One layer a stage offers for display.

    `key` is the context key holding the image and must be one of the stage's
    `produces`; `band` is the band on it. A categorical layer carries `legend`
    and its drawing parameters follow from it; a continuous layer carries `vis`
    (min / max / palette) instead. One or the other, not both.

    `description` says what the layer shows. `legend_note` is for what a reader
    must be told in order not to misread it, and belongs wherever the legend is
    drawn, not only in a tooltip.
    """

    key: str
    band: str
    title: str
    description: str
    legend: tuple[LegendEntry, ...] = ()
    legend_note: str = ""
    vis: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Frozen, so a list passed for `legend` is normalised this way.
        object.__setattr__(self, "legend", tuple(self.legend))
        where = f"DisplayLayer {self.key}.{self.band}"
        if not self.legend and not self.vis:
            raise ValueError(
                f"{where}: has neither a legend nor vis parameters, so nothing "
                f"says how to draw it. Give a legend (categorical layer) or vis "
                f"parameters (continuous layer)."
            )
        if self.legend and self.vis:
            raise ValueError(
                f"{where}: has both a legend and vis parameters. A categorical "
                f"layer is drawn from its legend; give one or the other."
            )
        values = [e.value for e in self.legend]
        if len(values) != len(set(values)):
            raise ValueError(f"{where}: legend values must be unique, got {values}.")
        if values and max(values) - min(values) > _MAX_LEGEND_SPAN:
            raise ValueError(
                f"{where}: legend values span {min(values)}..{max(values)}, more "
                f"than {_MAX_LEGEND_SPAN} apart. Remap the band to compact codes."
            )

    def vis_params(self) -> dict[str, Any]:
        """Earth Engine visualisation parameters for this layer.

        For a categorical layer the palette is laid out over the full value
        range, with gaps (values no legend entry names) drawn black, so a value
        always gets the colour its legend entry states.
        """
        if not self.legend:
            return {"bands": [self.band], **self.vis}
        by_value = {e.value: e.color for e in self.legend}
        lo, hi = min(by_value), max(by_value)
        # A single class would give min == max, which Earth Engine cannot
        # stretch. Widen the range by one; the extra value is a gap.
        hi = max(hi, lo + 1)
        return {
            "bands": [self.band],
            "min": lo,
            "max": hi,
            "palette": [by_value.get(v, _LEGEND_GAP_COLOR) for v in range(lo, hi + 1)],
        }

    def to_manifest(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "band": self.band,
            "title": self.title,
            "description": self.description,
            "vis": self.vis_params(),
            "legend": [
                {"value": e.value, "label": e.label, "color": e.color}
                for e in self.legend
            ],
            "legend_note": self.legend_note,
        }


@dataclass(frozen=True)
class SummaryNumber:
    """One number (or small table of numbers) a stage reports about itself."""

    name: str
    description: str
    unit: str = ""


def transparency_gaps(stage_cls: type[Stage]) -> list[str]:
    """What is missing from a stage's transparency declaration. Empty = complete.

    A stage that declares neither a display layer nor a summary number has
    nothing to show for the step it performs, which is the case this contract
    exists to rule out. What it does declare has to say what it is: a layer or
    a number with no description is not an account of anything. Used by
    tests/test_transparency_contract.py.
    """
    name = stage_cls.name
    gaps: list[str] = []
    if not stage_cls.display_layers and not stage_cls.summary_numbers:
        gaps.append(f"{name}: declares neither display_layers nor summary_numbers")
    for layer in stage_cls.display_layers:
        for attr in ("title", "description"):
            if not getattr(layer, attr).strip():
                gaps.append(
                    f"{name}: display layer {layer.key}.{layer.band} has no {attr}"
                )
        for entry in layer.legend:
            if not entry.label.strip():
                gaps.append(
                    f"{name}: display layer {layer.key}.{layer.band} has no label "
                    f"for value {entry.value}"
                )
    for number in stage_cls.summary_numbers:
        if not number.description.strip():
            gaps.append(f"{name}: summary number {number.name!r} has no description")
    return gaps


class PipelineContext:
    """Shared dict-like state flowing between stages. Write-once per key."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def has(self, key: str) -> bool:
        return key in self._data

    def get(self, key: str) -> Any:
        if key not in self._data:
            raise KeyError(
                f"PipelineContext: {key!r} not found. Have: {sorted(self._data.keys())}"
            )
        return self._data[key]

    def set(self, key: str, value: Any) -> None:
        """Set a key in the context. Write-once: re-setting an existing key
        raises KeyError.

        Write-once enforces the architectural invariant that each context
        key has exactly one producing stage. If two stages produce the
        same key, the conflict is caught at run time rather than silently
        clobbered. To intentionally pre-populate a key (e.g., `roi` from
        the inspect script), do it before any stage runs.

        Raises:
            KeyError: if `key` already exists in the context.
        """
        if key in self._data:
            raise KeyError(f"PipelineContext: {key!r} already set.")
        self._data[key] = value

    def keys(self) -> set[str]:  # type: ignore[valid-type]
        # `set[str]` is builtins.set; mypy mis-resolves it to PipelineContext.set
        # because the class scope shadows the builtin name.
        return set(self._data.keys())

    def __repr__(self) -> str:
        return f"PipelineContext(keys={sorted(self._data.keys())})"


@dataclass
class StageResult:
    """What a stage returns. outputs must match its `produces` declaration."""

    outputs: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


_stage_registry: dict[str, type[Stage]] = {}


def register_stage(name: str) -> Any:
    """Class decorator. Stage name must match the class's `name` attribute."""

    def decorator(cls: type[Stage]) -> type[Stage]:
        if not issubclass(cls, Stage):
            raise TypeError(f"@register_stage: {cls.__name__} must subclass Stage.")
        if getattr(cls, "name", None) != name:
            raise ValueError(
                f"@register_stage({name!r}): class {cls.__name__} has "
                f"name={getattr(cls, 'name', None)!r}"
            )
        if name in _stage_registry:
            existing = _stage_registry[name]
            if existing is not cls:
                raise ValueError(f"@register_stage({name!r}): already registered.")
        _stage_registry[name] = cls
        return cls

    return decorator


def get_stage_class(name: str) -> type[Stage]:
    if name not in _stage_registry:
        raise KeyError(
            f"No stage registered with name {name!r}. "
            f"Registered: {sorted(_stage_registry.keys())}"
        )
    return _stage_registry[name]


def list_registered_stages() -> list[str]:
    return sorted(_stage_registry.keys())


def _clear_registry_for_testing() -> None:
    _stage_registry.clear()


class Stage(ABC):
    """Abstract base for pipeline stages.

    Subclasses must set `name`, `required_inputs`, `produces` and implement
    `run`. Validation of these happens at class-definition time, not later.
    """

    name: ClassVar[str] = ""
    required_inputs: ClassVar[set[str]] = set()
    produces: ClassVar[set[str]] = set()
    # Subset of `produces` that can be cached as GEE assets (ee.Image only).
    # Empty set or unset = all produces are cacheable (default). Stages whose
    # outputs are mostly ee.ImageCollection / non-Image should override this
    # to limit the orchestrator's cache check to the actually-cacheable keys.
    cacheable_outputs: ClassVar[set[str]] = set()
    # Transparency contract (see the top of this module). Both default to empty:
    # a stage opts in by declaring them, and tests/test_transparency_contract.py
    # lists which stages are required to.
    display_layers: ClassVar[tuple[DisplayLayer, ...]] = ()
    summary_numbers: ClassVar[tuple[SummaryNumber, ...]] = ()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # skip validation for still-abstract subclasses
        if getattr(cls, "__abstractmethods__", None):
            return
        if not cls.name:
            raise TypeError(f"{cls.__name__}: must set class attribute `name`.")
        if not isinstance(cls.required_inputs, set):
            raise TypeError(
                f"{cls.__name__}: `required_inputs` must be a set, got "
                f"{type(cls.required_inputs).__name__}."
            )
        if not isinstance(cls.produces, set):
            raise TypeError(
                f"{cls.__name__}: `produces` must be a set, got "
                f"{type(cls.produces).__name__}."
            )
        for layer in cls.display_layers:
            if not isinstance(layer, DisplayLayer):
                raise TypeError(
                    f"{cls.__name__}: `display_layers` must hold DisplayLayer "
                    f"objects, got {type(layer).__name__}."
                )
            if layer.key not in cls.produces:
                raise TypeError(
                    f"{cls.__name__}: display layer {layer.title!r} names context "
                    f"key {layer.key!r}, which is not in `produces` "
                    f"{sorted(cls.produces)}."
                )
        bands = [(layer.key, layer.band) for layer in cls.display_layers]
        if len(bands) != len(set(bands)):
            raise TypeError(
                f"{cls.__name__}: `display_layers` lists the same key and band "
                f"twice: {bands}."
            )
        for number in cls.summary_numbers:
            if not isinstance(number, SummaryNumber):
                raise TypeError(
                    f"{cls.__name__}: `summary_numbers` must hold SummaryNumber "
                    f"objects, got {type(number).__name__}."
                )
        names = [s.name for s in cls.summary_numbers]
        if len(names) != len(set(names)):
            raise TypeError(
                f"{cls.__name__}: `summary_numbers` names must be unique, got {names}."
            )
        # The two halves go together. Numbers nobody computes would fail at run
        # time; a summarise() with nothing declared would never be called, and
        # its numbers would be missing from the manifest without a word.
        overrides_summarise = cls.summarise is not Stage.summarise
        if cls.summary_numbers and not overrides_summarise:
            raise TypeError(
                f"{cls.__name__}: declares summary_numbers {names} but does not "
                f"implement summarise() to compute them."
            )
        if overrides_summarise and not cls.summary_numbers:
            raise TypeError(
                f"{cls.__name__}: implements summarise() but declares no "
                f"summary_numbers, so the orchestrator would never call it."
            )

    def validate(self, ctx: PipelineContext, config: Any) -> None:
        """Validate stage preconditions before `run` is called.

        The default implementation checks that every key in
        `required_inputs` exists in the context. Subclasses may override
        to add additional checks (e.g., band counts, projection match,
        config constraints); but should call super().validate() to keep
        the default check active.

        Override is OPTIONAL. Most stages get away with the default,
        because GEE will surface most preconditions as informative
        errors at run time. Override only when the cost of a late
        failure outweighs the cost of an extra validation call.

        Raises:
            KeyError: missing required_inputs in the context.
        """
        missing = self.required_inputs - ctx.keys()
        if missing:
            raise KeyError(
                f"{self.name}: missing required context inputs: {sorted(missing)}. "
                f"Context has: {sorted(ctx.keys())}"
            )

    @abstractmethod
    def run(self, ctx: PipelineContext, config: Any) -> StageResult:
        ...

    def summarise(self, ctx: PipelineContext, config: Any) -> dict[str, Any]:
        """Compute this stage's declared `summary_numbers`.

        Called by the orchestrator after the stage's outputs are in the context,
        whether they came from a live run or from the asset cache -- so it reads
        from `ctx`, never from state left behind by `run()`. Returns one value
        per declared name, no more and no fewer. The default (nothing declared)
        returns nothing.

        A summary reports on the stage's products; it must not change them. If
        it raises, or returns the wrong names, the orchestrator records that in
        the manifest and carries on: the products are already made.
        """
        return {}

    def __repr__(self) -> str:
        return (
            f"<{type(self).__name__} name={self.name!r} "
            f"requires={sorted(self.required_inputs)} "
            f"produces={sorted(self.produces)}>"
        )

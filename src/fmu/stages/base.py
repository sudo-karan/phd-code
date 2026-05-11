"""
Stage interface — the architectural heart of the pipeline.

Four primitives defined here:

  1. `PipelineContext` — the shared bag of values flowing through the pipeline.
     Stages read from it and write to it. Each stage declares what keys it
     reads (`required_inputs`) and what keys it writes (`produces`), so the
     orchestrator can validate the wiring before running anything.

  2. `StageResult` — what each stage returns: its outputs (which get merged
     into the context) plus metadata for the per-run report.

  3. `Stage` — the abstract base class every concrete stage subclasses.
     Subclasses implement `run(self, ctx, config)` and declare:
        - `name`: short ID used in the registry and logs
        - `required_inputs`: set of context keys this stage reads
        - `produces`: set of context keys this stage writes

  4. `register_stage(name)` — class decorator that registers a Stage subclass
     so the orchestrator can look it up by name from YAML config.

Design choices (locked):
  - Stages communicate via a context dict, NOT explicit named parameters.
    A stage's run() signature is always run(ctx, config), no matter what
    it needs. Rationale: adding new context keys never breaks existing stage
    signatures. The required_inputs declaration replaces type-checking the
    args; the orchestrator validates declarations match what's in the context
    before calling run().
  - Stage failures propagate as exceptions. No soft-fail / continue-on-error
    mode. Research pipelines benefit from "fail loud" — silent partial
    failures cause subtle wrong results that are hard to detect later.
  - Stages must NOT mutate the context in-place. They return a StageResult
    whose `outputs` dict is merged in by the orchestrator. This keeps stages
    purely functional and makes them easier to test in isolation.

What's NOT here:
  - The orchestrator itself (pipeline.py). This module just defines the
    contract; the orchestrator that walks stages in order, validates the
    context, and assembles the run report comes in a later module.
  - Concrete stages (data_load, masking, etc). Each gets its own module.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar

# ---------- PipelineContext ----------


class PipelineContext:
    """
    The shared bag of values flowing through the pipeline.

    A context starts empty. Each stage reads keys from it (e.g. "roi",
    "s2_collection") and writes new keys (e.g. "optical_features"). The
    orchestrator merges each stage's outputs back into the context before
    calling the next stage.

    Why not just a plain dict?
      - We want a clear API (`ctx.get("roi")` vs `ctx["roi"]`) and the option
        to add features later (snapshotting, change-tracking) without
        breaking stage code.
      - The `set` method enforces "write-once" semantics — stages cannot
        overwrite a key another stage already produced. Catches bugs where
        two stages both claim to produce "ndvi" and one silently clobbers
        the other.
    """

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def has(self, key: str) -> bool:
        """Return True if `key` has been set."""
        return key in self._data

    def get(self, key: str) -> Any:
        """
        Get the value for `key`.

        Raises KeyError if `key` was never set — this is a stage wiring bug,
        not a runtime data issue, so failing loudly is the right behaviour.
        """
        if key not in self._data:
            raise KeyError(
                f"PipelineContext: key {key!r} not found. "
                f"Available keys: {sorted(self._data.keys())}"
            )
        return self._data[key]

    def set(self, key: str, value: Any) -> None:
        """
        Set `key` to `value`. Raises if `key` was already set.

        Stages must produce only the keys they declare and must not overwrite
        keys from other stages. The orchestrator uses `set` (not `update`) so
        any collision is loud.
        """
        if key in self._data:
            raise KeyError(
                f"PipelineContext: key {key!r} is already set. "
                "Two stages cannot produce the same key."
            )
        self._data[key] = value

    def keys(self) -> set[str]:
        """Return the set of keys currently in the context."""
        return set(self._data.keys())

    def __repr__(self) -> str:
        return f"PipelineContext(keys={sorted(self._data.keys())})"


# ---------- StageResult ----------


@dataclass
class StageResult:
    """
    What a stage returns from its run() method.

    Fields:
      outputs:    Keys to merge into the PipelineContext. Must exactly match
                  the stage's `produces` declaration — the orchestrator
                  validates this before merging.
      metadata:   Free-form key/value record for the per-run report.
                  Typical entries: rows_processed, n_images, n_pixels_masked,
                  warnings, elapsed_sec.
      warnings:   Human-readable warnings the stage wants surfaced in the
                  report (e.g. "Sentinel-1 had only 3 images in this window").
                  These are non-fatal — fatal issues should raise.
    """

    outputs: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


# ---------- Stage registry ----------

# The registry maps a stage's `name` to its class. Populated by
# @register_stage decorators at import time.
_stage_registry: dict[str, type[Stage]] = {}


def register_stage(name: str) -> Any:
    """
    Class decorator that registers a Stage subclass in the global registry.

    Usage:
        @register_stage("phenology_optical")
        class OpticalPhenologyStage(Stage):
            name = "phenology_optical"
            ...

    The decorator validates that the registered name matches the class's
    `name` attribute — catches the easy bug of registering one name and
    declaring another.
    """

    def decorator(cls: type[Stage]) -> type[Stage]:
        if not issubclass(cls, Stage):
            raise TypeError(
                f"@register_stage: {cls.__name__} must subclass Stage."
            )
        if getattr(cls, "name", None) != name:
            raise ValueError(
                f"@register_stage({name!r}): stage class {cls.__name__} has "
                f"name={getattr(cls, 'name', None)!r}, which doesn't match."
            )
        if name in _stage_registry:
            existing = _stage_registry[name]
            if existing is not cls:
                raise ValueError(
                    f"@register_stage({name!r}): already registered to "
                    f"{existing.__name__}."
                )
        _stage_registry[name] = cls
        return cls

    return decorator


def get_stage_class(name: str) -> type[Stage]:
    """Look up a stage class by its registered name."""
    if name not in _stage_registry:
        raise KeyError(
            f"No stage registered with name {name!r}. "
            f"Registered: {sorted(_stage_registry.keys())}"
        )
    return _stage_registry[name]


def list_registered_stages() -> list[str]:
    """Return all registered stage names, sorted."""
    return sorted(_stage_registry.keys())


def _clear_registry_for_testing() -> None:
    """Reset the registry. Tests use this; normal code should not."""
    _stage_registry.clear()


# ---------- Stage ----------


class Stage(ABC):
    """
    Abstract base class for all pipeline stages.

    Subclasses MUST:
      - Set class attribute `name` to a unique short identifier (lowercase,
        underscores). This is the name used in the registry and in YAML.
      - Set class attribute `required_inputs` to the set of context keys this
        stage reads.
      - Set class attribute `produces` to the set of context keys this stage
        writes.
      - Implement `run(self, ctx, config) -> StageResult`.

    Subclasses MAY:
      - Override `__init__` to accept additional parameters.
      - Override `validate(self, ctx, config)` to do early sanity checks.
        Default validation just confirms required_inputs are present.

    Example:
        @register_stage("masking")
        class MaskingStage(Stage):
            name = "masking"
            required_inputs = {"roi", "s2_image"}
            produces = {"mask"}

            def run(self, ctx, config):
                roi = ctx.get("roi")
                s2 = ctx.get("s2_image")
                mask = _build_mask(s2, config.masking)
                return StageResult(outputs={"mask": mask})
    """

    # Subclasses MUST override these.
    name: ClassVar[str] = ""
    required_inputs: ClassVar[set[str]] = set()
    produces: ClassVar[set[str]] = set()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """
        Validate that subclasses declare the required class attributes.
        Catches forgotten declarations at class-definition time, before
        the orchestrator tries to use the stage.
        """
        super().__init_subclass__(**kwargs)
        # Skip validation for further abstract subclasses (no @abstractmethod
        # left unimplemented means it's concrete).
        if getattr(cls, "__abstractmethods__", None):
            return
        if not cls.name:
            raise TypeError(
                f"{cls.__name__}: must set class attribute `name`."
            )
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

    def validate(self, ctx: PipelineContext, config: Any) -> None:
        """
        Sanity-check inputs before run(). Default: verifies every
        required_inputs key exists in the context.

        Subclasses can override to add stage-specific checks (e.g.
        "required_inputs are an ee.Image, not None"). The orchestrator
        calls validate() before run(); subclasses should call super().
        """
        missing = self.required_inputs - ctx.keys()
        if missing:
            raise KeyError(
                f"{self.name}: missing required context inputs: "
                f"{sorted(missing)}. Context has: {sorted(ctx.keys())}"
            )

    @abstractmethod
    def run(self, ctx: PipelineContext, config: Any) -> StageResult:
        """
        Execute the stage and return a StageResult.

        Args:
            ctx: PipelineContext with at least the stage's required_inputs.
            config: The pipeline Config object (typed as Any here to avoid
                a circular import; orchestrator passes the real Config).

        Returns:
            StageResult whose `outputs` dict has exactly the keys in
            self.produces. The orchestrator validates this match.

        Stages MUST NOT mutate `ctx` directly. The orchestrator merges
        the returned outputs into the context.
        """
        ...

    def __repr__(self) -> str:
        return (
            f"<{type(self).__name__} name={self.name!r} "
            f"requires={sorted(self.required_inputs)} "
            f"produces={sorted(self.produces)}>"
        )

"""Stage contract: PipelineContext, StageResult, Stage, registry.

See docs/design_notes.md for the rationale behind the context-dict +
required_inputs/produces pattern.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar


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
        # write-once: two stages can't both claim to produce the same key
        if key in self._data:
            raise KeyError(f"PipelineContext: {key!r} already set.")
        self._data[key] = value

    def keys(self) -> set[str]:
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

    def validate(self, ctx: PipelineContext, config: Any) -> None:
        missing = self.required_inputs - ctx.keys()
        if missing:
            raise KeyError(
                f"{self.name}: missing required context inputs: {sorted(missing)}. "
                f"Context has: {sorted(ctx.keys())}"
            )

    @abstractmethod
    def run(self, ctx: PipelineContext, config: Any) -> StageResult:
        ...

    def __repr__(self) -> str:
        return (
            f"<{type(self).__name__} name={self.name!r} "
            f"requires={sorted(self.required_inputs)} "
            f"produces={sorted(self.produces)}>"
        )

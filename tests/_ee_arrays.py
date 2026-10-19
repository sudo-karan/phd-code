"""Earth Engine images as numpy arrays, for offline tests that need the numbers, not the calls.

tests/_ee_recorder.py records what a stage asks of Earth Engine; this computes it. An
`Image` is a set of named bands on one grid, each a float array with a boolean mask, and
the operations below act pixel by pixel as Earth Engine's do, for the cases the tests use.
`install(monkeypatch, module)` puts `FakeEE` and `get_info` in place of the module's `ee`
and `safe_get_info`.

Not modelled: projections and scales (every image is on one grid), fractional masks, tiles
and pixel types. An operation the tests do not use raises AttributeError.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np


class Value:
    """A server-side value (a list, a number) that `get_info` hands back as it is."""

    def __init__(self, value: Any):
        self.value = value


def get_info(obj: Any, context: str = "") -> Any:
    """A stand-in for `safe_get_info`: the value of a `Value`, or `obj` itself."""
    return obj.value if isinstance(obj, Value) else obj


def _names(selector: Any) -> list[str] | list[int]:
    if isinstance(selector, Value):
        selector = selector.value
    if isinstance(selector, str):
        return [selector]
    return list(selector)


class Image:
    """Named bands on one grid: {name: float array} and {name: bool mask}, in band order."""

    def __init__(self, bands: dict[str, Any], masks: dict[str, Any] | None = None):
        self.bands = {name: np.asarray(v, dtype=float) for name, v in bands.items()}
        shapes = {v.shape for v in self.bands.values()}
        assert len(shapes) <= 1, f"bands on different grids: {shapes}"
        masks = masks or {}
        self.masks = {
            name: np.asarray(masks[name], dtype=bool) if name in masks else np.ones(v.shape, bool)
            for name, v in self.bands.items()
        }

    # -- reading it back
    def value(self, band: str, at: tuple[int, int]) -> float | None:
        """The band's value at a pixel, or None where it is masked."""
        return float(self.bands[band][at]) if self.masks[band][at] else None

    def pair(self, prefix: str, at: tuple[int, int]) -> tuple[float | None, float | None]:
        """(sin, cos) of a decomposed cyclic band at a pixel."""
        return self.value(f"{prefix}_sin", at), self.value(f"{prefix}_cos", at)

    # -- band bookkeeping
    def bandNames(self) -> Value:  # noqa: N802 - mirrors the ee API
        return Value(list(self.bands))

    def select(self, selector: Any) -> Image:
        names = [list(self.bands)[s] if isinstance(s, int) else s for s in _names(selector)]
        return Image({n: self.bands[n] for n in names}, {n: self.masks[n] for n in names})

    def rename(self, names: Any) -> Image:
        new = _names(names)
        assert len(new) == len(self.bands), (new, list(self.bands))
        return Image(
            {str(n): v for n, v in zip(new, self.bands.values(), strict=True)},
            {str(n): m for n, m in zip(new, self.masks.values(), strict=True)},
        )

    def addBands(self, other: Image) -> Image:  # noqa: N802 - mirrors the ee API
        assert not set(self.bands) & set(other.bands), "band names collide"
        return Image({**self.bands, **other.bands}, {**self.masks, **other.masks})

    # -- pixel by pixel
    def _each(self, fn: Any) -> Image:
        return Image({n: fn(v) for n, v in self.bands.items()}, dict(self.masks))

    def multiply(self, c: float) -> Image:
        return self._each(lambda v: v * c)

    def sin(self) -> Image:
        return self._each(np.sin)

    def cos(self) -> Image:
        return self._each(np.cos)

    def eq(self, c: float) -> Image:
        return self._each(lambda v: (v == c).astype(float))

    def where(self, test: Image, value: float) -> Image:
        """Earth Engine's `where`: `value` where `test` is nonzero; the input where `test`
        is zero or masked, and nothing where the input is masked."""
        ((t, tm),) = zip(test.bands.values(), test.masks.values(), strict=True)
        on = (t != 0) & tm
        return Image(
            {n: np.where(on & self.masks[n], value, v) for n, v in self.bands.items()},
            dict(self.masks),
        )


class _ImageModule:
    @staticmethod
    def cat(images: Sequence[Image]) -> Image:
        out = images[0]
        for image in images[1:]:
            out = out.addBands(image)
        return out


class FakeEE:
    """The parts of the `ee` module the code under test reaches."""

    Image = _ImageModule


def install(monkeypatch: Any, module: Any) -> None:
    """Swap the module's `ee` and `safe_get_info` for these, for one test."""
    monkeypatch.setattr(module, "ee", FakeEE)
    monkeypatch.setattr(module, "safe_get_info", get_info)

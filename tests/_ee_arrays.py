"""Earth Engine images as numpy arrays, for offline tests that need the numbers, not the calls.

tests/_ee_recorder.py records what a stage asks of Earth Engine; this computes it. An
`Image` is a set of named bands on one grid, each a float array with a boolean mask, and
the operations below act pixel by pixel as Earth Engine's do, for the cases the tests use.
Server-side lists, dictionaries and feature collections are plain Python values here.
`install(monkeypatch, module)` puts `FakeEE` and `get_info` in place of the module's `ee`
and `safe_get_info`.

Not modelled: projections and scales (every image is on one grid, and a region is the whole
grid), fractional masks, tiles and pixel types. An operation the tests do not use raises
AttributeError. Where an operation rests on an assumption about Earth Engine, its docstring
says so.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import numpy as np
from scipy import ndimage


class Value:
    """A server-side value (a list, a dictionary, a number) that `get_info` hands back."""

    def __init__(self, value: Any):
        self.value = value

    def get(self, key: str) -> Value:
        return Value(self.value[key])


def get_info(obj: Any, context: str = "") -> Any:
    """A stand-in for `safe_get_info`: the value of a `Value`, or `obj` itself."""
    return obj.value if isinstance(obj, Value) else obj


def _plain(obj: Any) -> Any:
    return obj.value if isinstance(obj, Value) else obj


def _names(selector: Any) -> list[Any]:
    selector = _plain(selector)
    if isinstance(selector, str):
        return [selector]
    return list(selector)


def _pieces(labels: np.ndarray, valid: np.ndarray) -> list[np.ndarray]:
    """The 8-connected pieces of equal label, as boolean masks."""
    out = []
    for value in np.unique(labels[valid]):
        parts, n = ndimage.label(valid & (labels == value), structure=np.ones((3, 3), int))
        out.extend(parts == i for i in range(1, n + 1))
    return out


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

    def values(self, band: str, where: np.ndarray) -> set[float | None]:
        """The distinct values of a band over the pixels `where` is true, None for masked."""
        return {
            float(v) if m else None
            for v, m in zip(self.bands[band][where], self.masks[band][where], strict=True)
        }

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

    def projection(self) -> _Projection:
        return _Projection()

    # -- pixel by pixel
    def _each(self, fn: Callable[[np.ndarray], np.ndarray]) -> Image:
        return Image({n: fn(v) for n, v in self.bands.items()}, dict(self.masks))

    def multiply(self, c: float) -> Image:
        return self._each(lambda v: v * c)

    def sin(self) -> Image:
        return self._each(np.sin)

    def cos(self) -> Image:
        return self._each(np.cos)

    def eq(self, c: float) -> Image:
        return self._each(lambda v: (v == c).astype(float))

    def gt(self, c: float) -> Image:
        return self._each(lambda v: (v > c).astype(float))

    def mask(self) -> Image:
        """Each band's mask as a band of its own: 1 where the band has data, 0 elsewhere."""
        return Image({n: m.astype(float) for n, m in self.masks.items()})

    def unmask(self, value: float) -> Image:
        """`value` where a band is masked, and no mask left."""
        return Image({n: np.where(self.masks[n], v, value) for n, v in self.bands.items()})

    def where(self, test: Image, value: float) -> Image:
        """Earth Engine's `where`: `value` where `test` is nonzero; the input where `test`
        is zero or masked, and nothing where the input is masked."""
        ((t, tm),) = zip(test.bands.values(), test.masks.values(), strict=True)
        on = (t != 0) & tm
        return Image(
            {n: np.where(on & self.masks[n], value, v) for n, v in self.bands.items()},
            dict(self.masks),
        )

    def updateMask(self, mask: Image) -> Image:  # noqa: N802 - mirrors the ee API
        """A one-band mask, applied to every band: masked where it is zero or masked."""
        ((m, mm),) = zip(mask.bands.values(), mask.masks.values(), strict=True)
        on = (m != 0) & mm
        return Image(dict(self.bands), {n: k & on for n, k in self.masks.items()})

    def remap(self, from_: Any, to: Any) -> Image:
        """One band: each value of `from_` becomes the value at the same place in `to`; a
        value not in `from_` is masked (no default)."""
        ((name, v),) = self.bands.items()
        lookup = dict(zip(_plain(from_), _plain(to), strict=True))
        out = np.zeros(v.shape)
        mask = np.zeros(v.shape, bool)
        for at in zip(*np.nonzero(self.masks[name]), strict=True):
            if float(v[at]) in lookup:
                out[at], mask[at] = lookup[float(v[at])], True
        return Image({name: out}, {name: mask})

    # -- reductions
    def reduceConnectedComponents(  # noqa: N802 - mirrors the ee API
        self, reducer: Any, labelBand: str, maxSize: int = 256  # noqa: N803
    ) -> Image:
        """A mean over each 8-connected piece of equal label, each band over the piece's
        pixels where it has data, written to every pixel of the piece (masked where the piece
        has none). That every pixel of the piece holds it is assumed; maxSize is not modelled."""
        pieces = _pieces(self.bands[labelBand], self.masks[labelBand])
        bands, masks = {}, {}
        for name, v in self.bands.items():
            bands[name], masks[name] = np.zeros(v.shape), np.zeros(v.shape, bool)
            for piece in pieces:
                have = piece & self.masks[name]
                if have.any():
                    bands[name][piece], masks[name][piece] = v[have].mean(), True
        return Image(bands, masks)

    def reduceRegion(self, reducer: _Reducer, **kwargs: Any) -> Value:  # noqa: N802
        """A grouped mean or sum by the band at `reducer`'s group field: {"groups": [{group
        name: label, band: value, ...}]}, in label order, each band over the group's pixels
        where it has data. A band with no data in a group is left out of the group's
        dictionary, as a "mode" is (seen on Earth Engine, 19 Oct 2026). The region and grid are
        not modelled.

        An unweighted one refuses a band that is masked anywhere in a group: Earth Engine's
        grouped, unweighted reducers add a band's masked pixels into the sum (and so the mean)
        they give the group, though their count leaves them out (read on Earth Engine, 20 Oct
        2026, round 13), so what it would answer is not what this computes."""
        assert reducer.kind in ("mean", "sum") and reducer.group_field is not None, reducer.__dict__
        names = list(self.bands)
        label = names[reducer.group_field]
        labels, valid = self.bands[label], self.masks[label]
        groups = []
        for value in np.unique(labels[valid]):
            group: dict[str, Any] = {reducer.group_name: float(value)}
            for name in names:
                if name == label:
                    continue
                in_group = valid & (labels == value)
                have = in_group & self.masks[name]
                if reducer.unweighted_ and (have != in_group).any():
                    raise AssertionError(
                        f"band {name!r} is masked on part of group {value:g}: Earth Engine's "
                        "grouped unweighted reducers add masked pixels into the sum"
                    )
                if have.any():
                    v = self.bands[name][have]
                    group[name] = float(v.mean() if reducer.kind == "mean" else v.sum())
            groups.append(group)
        return Value({"groups": groups})


class _Projection:
    def atScale(self, scale: float) -> _Projection:  # noqa: N802 - mirrors the ee API
        return self


class _Reducer:
    """What a reducer was built as: its kind, and the group field and name if grouped."""

    def __init__(self, kind: str):
        self.kind, self.group_field, self.group_name = kind, None, None
        self.unweighted_ = False

    def unweighted(self) -> _Reducer:
        self.unweighted_ = True
        return self

    def forEachBand(self, image: Image) -> _Reducer:  # noqa: N802 - mirrors the ee API
        return self

    def group(self, groupField: int, groupName: str) -> _Reducer:  # noqa: N803
        self.group_field, self.group_name = groupField, groupName
        return self


class _Feature:
    def __init__(self, geometry: Any, properties: Any):
        self.properties = dict(_plain(properties))

    def get(self, name: str) -> Value:
        return Value(self.properties[name])

    def set(self, name: str, value: Any) -> _Feature:
        return _Feature(None, {**self.properties, name: _plain(value)})


class _FeatureCollection:
    def __init__(self, features: Any):
        self.features = list(_plain(features))

    def filter(self, keep: Callable[[_Feature], bool]) -> _FeatureCollection:
        return _FeatureCollection([f for f in self.features if keep(f)])

    def map(self, fn: Callable[[_Feature], _Feature]) -> _FeatureCollection:
        return _FeatureCollection([fn(f) for f in self.features])

    def aggregate_array(self, name: str) -> Value:
        return Value([f.properties[name] for f in self.features if name in f.properties])


class _Number(Value):
    def __init__(self, value: Any):
        super().__init__(float(_plain(value)))

    def divide(self, other: Any) -> _Number:
        return _Number(self.value / float(_plain(other)))


class _List(Value):
    def __init__(self, items: Any):
        super().__init__(list(_plain(items)))

    def map(self, fn: Callable[[Any], Any]) -> _List:
        return _List([fn(item) for item in self.value])


class _ImageModule:
    @staticmethod
    def cat(images: Sequence[Image]) -> Image:
        out = images[0]
        for image in images[1:]:
            out = out.addBands(image)
        return out


class _ReducerModule:
    @staticmethod
    def mean() -> _Reducer:
        return _Reducer("mean")

    @staticmethod
    def sum() -> _Reducer:
        return _Reducer("sum")


class _FilterModule:
    @staticmethod
    def notNull(names: list[str]) -> Callable[[_Feature], bool]:  # noqa: N802
        return lambda f: all(f.properties.get(n) is not None for n in names)

    @staticmethod
    def gt(name: str, value: float) -> Callable[[_Feature], bool]:
        return lambda f: f.properties.get(name) is not None and f.properties[name] > value


class FakeEE:
    """The parts of the `ee` module the code under test reaches."""

    Image = _ImageModule
    Reducer = _ReducerModule
    Filter = _FilterModule
    List = _List
    Number = _Number
    Feature = _Feature
    FeatureCollection = _FeatureCollection


def install(monkeypatch: Any, module: Any) -> None:
    """Swap the module's `ee` and `safe_get_info` for these, for one test."""
    monkeypatch.setattr(module, "ee", FakeEE)
    monkeypatch.setattr(module, "safe_get_info", get_info)

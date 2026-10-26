"""Non-live tests: a stand takes its row's type, and a stand with no row a null type (rounds 12, 13).

Before round 12 the export typed each stand polygon by a vote: the commonest type among the
typed pixels the polygon touches, each weighted by its share inside the polygon. Where the
polygons and the type image lie on different grids (the legacy cache layout) a polygon also
touches slivers of its neighbours' pixels, so a small stand could be outvoted by a neighbour,
and a stand with no typed pixel of its own could take a neighbour's type (issue #44 item 12;
docs/demo/remerge/README.md, section 4). Round 12 gave a stand whose row the fit was trained on
that row's type, read from its own typed pixels grouped by its label, and left every other stand
on the vote. Round 13 (Jaskaran's answers (b) to questions 1 and 2 of
docs/handoff/2026-10-19-round12.md) drops the vote: a stand left out of the fit takes its own
row's type like any stand with a row, and a stand with no row (no typed pixel of its own) gets a
null type, whatever its polygon touches.

The builder runs here on a fake Earth Engine that holds a one-row raster in Python: each pixel
has a stand label and a type (None where it is untyped), and a polygon may be given slivers of
other pixels, with weights, to stand for a grid that does not match. Register entries
`spec-export-stand-type-from-its-fit-row` and `spec-export-stand-type-from-its-own-row-or-null`.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

import fmu.stages.export as export_mod
from fmu.config import load_config
from fmu.stages.base import PipelineContext

REPO_ROOT = Path(__file__).parent.parent
BASELINE_YAML = REPO_ROOT / "configs" / "sanjay_van_baseline.yaml"

# The raster: pixel column -> (stand label, type). One row, so a pixel is its column.
#   10: three pixels of type 2.
#   20: one pixel of type 1, between 10 and 30; its polygon touches slivers of both.
#   30: two pixels of type 2.
#   40: two untyped pixels (no row); its polygon touches a sliver of 30.
#   50: one untyped pixel (no row), no sliver.
#   60: two pixels of type 0; its polygon touches slivers of 70.
#   70: three pixels of type 3.
PIXELS: dict[int, tuple[int, int | None]] = {
    0: (10, 2), 1: (10, 2), 2: (10, 2),
    3: (20, 1),
    4: (30, 2), 5: (30, 2),
    6: (40, None), 7: (40, None),
    8: (50, None),
    9: (60, 0), 10: (60, 0),
    11: (70, 3), 12: (70, 3), 13: (70, 3),
}
# Stand label -> [(pixel, weight)]: the neighbours' pixels its polygon also touches.
SLIVERS: dict[int, list[tuple[int, float]]] = {
    20: [(2, 0.6), (4, 0.6)],   # 1.2 of type 2 against 1.0 of type 1: the vote says 2
    40: [(5, 0.3)],             # no typed pixel of its own: the vote takes 30's type
    60: [(11, 1.0), (12, 1.5)],  # 2.5 of type 3 against 2.0 of type 0: the vote says 3
}
ROW_TYPE = {10: 2, 20: 1, 30: 2, 60: 0, 70: 3}  # 40 and 50 have no row


# ---------------------------------------------------------------------------
# A fake Earth Engine, just enough for _build_merged_feature_collection
# ---------------------------------------------------------------------------


class _Dict(dict):
    def get(self, key, default=None):  # noqa: D401 - mirrors ee.Dictionary.get
        """As Earth Engine's: the value, else the default, else an error. Python builds
        both cases of the fake If, as Earth Engine may, so a lookup there without a
        default would fail here."""
        if key in self:
            return self[key]
        if default is not None:
            return default
        raise KeyError(key)

    def contains(self, key):
        return key in self

    def remove(self, keys, ignore_missing=False):
        drop = set(keys)
        if not ignore_missing and drop - set(self):
            raise KeyError(sorted(drop - set(self)))
        return _Dict({k: v for k, v in self.items() if k not in drop})

    @staticmethod
    def fromLists(keys, values):  # noqa: N802 - mirrors the ee API
        return _Dict(zip(list(keys), list(values), strict=True))


class _List(list):
    def map(self, fn: Callable[[Any], Any], drop_nulls: bool = False):
        out = [fn(x) for x in self]
        return _List(x for x in out if not (drop_nulls and x is None))

    def removeAll(self, other):  # noqa: N802 - mirrors the ee API
        return _List(x for x in self if x not in set(other))


class _Number:
    def __init__(self, value):
        self.value = value

    def format(self, pattern):
        return pattern % self.value


class _Feature:
    def __init__(self, props: dict[str, Any], pixels: list[tuple[int, float]]):
        self.props, self.pixels = dict(props), pixels

    def get(self, name):
        return self.props.get(name)

    def set(self, name, value=None):
        new = dict(name) if isinstance(name, dict) else {name: value}
        return _Feature({**self.props, **new}, self.pixels)


class _FC:
    def __init__(self, features: list[_Feature]):
        self.features = features

    def map(self, fn):
        return _FC([fn(f) for f in self.features])


class _Reducer:
    def __init__(self, name: str, group: dict[str, Any] | None = None):
        self.name, self.group_args = name, group

    @staticmethod
    def mean():
        return _Reducer("mean")

    @staticmethod
    def mode():
        return _Reducer("mode")

    @staticmethod
    def countEvery():  # noqa: N802 - mirrors the ee API
        return _Reducer("countEvery")

    def group(self, groupField, groupName):  # noqa: N803 - mirrors the ee API
        return _Reducer(self.name, {"field": groupField, "name": groupName})

    # The vectorisation's reducer since round 14: countEvery combined with the mean of the pixel
    # centres' coordinates (what it gives is tests/test_export_centroid_from_pixel_centres.py's).
    def combine(self, reducer2, outputPrefix=None, sharedInputs=None):  # noqa: N803
        return _Reducer(f"{self.name}+{reducer2.name}")

    def forEach(self, outputNames):  # noqa: N802, N803 - mirrors the ee API
        return _Reducer(f"{self.name}({','.join(outputNames)})")


def _weighted_mode(values: list[tuple[int | None, float]]) -> int | None:
    """Earth Engine's mode: the commonest value, ties to the smallest; None with no value."""
    weights: Counter = Counter()
    for v, w in values:
        if v is not None:
            weights[v] += w
    if not weights:
        return None
    top = max(weights.values())
    return min(v for v, w in weights.items() if w == top)


class _Image:
    """A band (or two) over PIXELS: 'label' or 'type' values, renamed as the code renames them."""

    def __init__(self, layers: list[str], names: list[str] | None = None):
        self.layers, self.names = layers, names or list(layers)

    def value(self, layer: str, px: int):
        label, kind = PIXELS[px]
        return label if layer == "label" else kind

    def toInt(self):  # noqa: N802 - mirrors the ee API
        return self

    def rename(self, name):
        return _Image(self.layers, [name])

    def addBands(self, other):  # noqa: N802 - mirrors the ee API
        return _Image(self.layers + other.layers, self.names + other.names)

    def bandNames(self):  # noqa: N802 - mirrors the ee API
        return _List(["canopy_height"])

    def select(self, bands):
        return self

    def reduceToVectors(self, **kw):  # noqa: N802 - mirrors the ee API
        # The stand labels, with the pixels' coordinates beside them since round 14.
        assert self.layers == ["label", "lonlat"] and kw["labelProperty"] == "stand_lbl"
        stands: dict[int, list[int]] = {}
        for px, (label, _) in PIXELS.items():
            stands.setdefault(label, []).append(px)
        return _FC([
            _Feature({"stand_lbl": label}, [(px, 1.0) for px in pxs] + SLIVERS.get(label, []))
            for label, pxs in sorted(stands.items())
        ])

    def reduceRegions(self, collection, reducer, scale):  # noqa: N802 - mirrors the ee API
        if reducer.name == "mean":
            return collection
        assert self.layers == ["type"] and reducer.name == "mode"
        return _FC([
            f.set("mode", _weighted_mode([(self.value("type", px), w) for px, w in f.pixels]))
            for f in collection.features
        ])

    def reduceRegion(self, reducer, geometry, scale, maxPixels):  # noqa: N802, N803
        assert self.layers == ["type", "label"] and reducer.name == "mode"
        assert reducer.group_args == {"field": 1, "name": "stand_lbl"}
        by_label: dict[int, list[tuple[int | None, float]]] = {}
        for px in PIXELS:
            by_label.setdefault(self.value("label", px), []).append((self.value("type", px), 1.0))
        groups = []
        for label, values in sorted(by_label.items()):
            mode = _weighted_mode(values)
            # As Earth Engine does: a group whose values are all masked has no "mode".
            groups.append({"stand_lbl": label} if mode is None else {"stand_lbl": label, "mode": mode})
        return _Dict({"groups": groups})


class _Algorithms:
    @staticmethod
    def If(condition, true_case, false_case):  # noqa: N802 - mirrors the ee API
        return true_case if condition else false_case


class _FakeEE:
    Reducer = _Reducer
    Dictionary = _Dict
    Algorithms = _Algorithms

    class Image:  # noqa: N801 - stands in for ee.Image
        @staticmethod
        def pixelLonLat():  # noqa: N802 - mirrors the ee API
            return _Image(["lonlat"])

    @staticmethod
    def List(items):  # noqa: N802 - mirrors the ee API
        return _List(items)

    @staticmethod
    def Number(value):  # noqa: N802 - mirrors the ee API
        return _Number(value)

    @staticmethod
    def Feature(feature):  # noqa: N802 - mirrors the ee API
        return feature


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setattr(export_mod, "ee", _FakeEE)
    monkeypatch.setattr(export_mod, "_feature_source_image", lambda ctx: _Image(["features"]))
    monkeypatch.setattr(export_mod, "_add_geom_attrs", lambda f, scale: f)
    monkeypatch.setattr(
        export_mod, "_drop_internal_properties",
        lambda f: _Feature({k: v for k, v in f.props.items() if k not in ("mode", "count")}, f.pixels),
    )
    monkeypatch.setattr(export_mod, "_renumber_by_centroid", lambda fc, *, id_field: fc)


def _types(*, excludes: bool, provenance: bool) -> dict[int, Any]:
    """{stand label: the cluster_id the merged layer gives it}."""
    cfg = load_config(BASELINE_YAML)
    cfg.clustering.fit_excludes_stands_below_min_area = excludes
    ctx = PipelineContext()
    ctx.set("stand_clusters", _Image(["label"]))
    ctx.set("cluster_labels", _Image(["type"]))
    ctx.set("roi", "<roi>")
    if provenance:
        ctx.set("stand_provenance", {
            label: {"n_superpx": 1, "n_pass1": 0, "n_relaxed": 0, "n_fallback": 0,
                    "below_min": int(label == 60), "below_why": "isolated" if label == 60 else ""}
            for label in (10, 20, 30, 40, 50, 60, 70)
        })
    fc = export_mod._build_merged_feature_collection(ctx=ctx, config=cfg, scale=10)
    out = {f.props["stand_lbl"]: f.props["cluster_id"] for f in fc.features}
    assert -1 not in out.values(), "a stand took the branch that looks up a missing row"
    assert not any("mode" in f.props for f in fc.features)
    return out


def _votes() -> dict[int, int | None]:
    """What the vote alone gives each stand: the layer's types before round 12."""
    polygons = _Image(["label"]).addBands(_FakeEE.Image.pixelLonLat()).reduceToVectors(labelProperty="stand_lbl")
    voted = _Image(["type"]).reduceRegions(collection=polygons, reducer=_Reducer.mode(), scale=10)
    return {f.props["stand_lbl"]: f.props["mode"] for f in voted.features}


# ---------------------------------------------------------------------------
# The tests
# ---------------------------------------------------------------------------


def test_the_scenario_has_the_votes_it_is_meant_to_have():
    """Before round 12 the layer carried these: stand 20 and stand 60 a neighbour's type
    though each has a row of its own, stand 40 a neighbour's type with no row at all."""
    assert _votes() == {10: 2, 20: 2, 30: 2, 40: 2, 50: None, 60: 3, 70: 3}


def test_a_stand_with_a_row_in_the_fit_takes_its_rows_type_not_the_vote(fake):
    """The change itself, and the test that fails on the old behaviour: stand 20's
    polygon is outvoted by its neighbours' slivers (type 2), but its row says 1."""
    types = _types(excludes=False, provenance=True)
    assert types[20] == ROW_TYPE[20] == 1
    assert types[60] == ROW_TYPE[60] == 0
    assert {s: types[s] for s in ROW_TYPE} == ROW_TYPE


def test_a_stand_with_no_row_gets_a_null_type_whatever_its_polygon_touches(fake):
    """Question 1 of round 12, answered (b) in round 13: a stand with no typed pixel of its
    own gets a null type in every layout. Stand 40's polygon touches a sliver of stand 30's
    type 2, which the vote gave it until round 13; stand 50 touches nothing typed."""
    types = _types(excludes=False, provenance=True)
    assert types[40] is None
    assert types[50] is None


def test_a_stand_left_out_of_the_fit_takes_its_own_rows_type(fake):
    """Question 2 of round 12, answered (b) in round 13: with
    fit_excludes_stands_below_min_area on, stand 60 (below the minimum, so left out of the
    fit) takes its own row's type, 0, like any stand with a row, not its vote, 3."""
    types = _types(excludes=True, provenance=True)
    assert types[60] == ROW_TYPE[60] == 0
    assert types == {**ROW_TYPE, 40: None, 50: None}


@pytest.mark.parametrize("excludes, provenance", [(False, True), (False, False), (True, True), (True, False)])
def test_the_types_depend_neither_on_the_setting_nor_on_the_provenance(fake, caplog, excludes, provenance):
    """Until round 13, with the setting on and no stand_provenance, no stand was retyped (the
    stands left out of the fit could not be told apart), with a warning. Since round 13 they
    are typed like every other stand, so neither the setting nor the provenance is read."""
    with caplog.at_level(logging.WARNING):
        types = _types(excludes=excludes, provenance=provenance)
    assert types == {**ROW_TYPE, 40: None, 50: None}
    assert "cannot be told apart" not in caplog.text


def test_the_row_types_leave_out_stands_with_no_typed_pixel(fake):
    """The grouped reduction gives a group for every label, and Earth Engine leaves "mode"
    out of a group whose values are all masked (seen live, 19 Oct 2026): those are dropped."""
    got = export_mod._stand_row_types(_Image(["type"]), _Image(["label"]), "<roi>", 10)
    assert dict(got) == {str(s): t for s, t in ROW_TYPE.items()}


def test_a_stand_whose_pieces_carry_different_types_takes_the_type_most_of_its_pixels_carry(
    fake, monkeypatch
):
    """The clustering stage averages each connected piece of a stand on its own, so the
    pieces of one stand can carry different types (the 10 km tile has one: a piece of one
    pixel beside one of 344). The row is one of them; the type most of the stand's typed
    pixels carry is taken, here 4 over 3."""
    for px, value in {14: (80, 4), 15: (80, 4), 16: (80, 4), 17: (80, 3)}.items():
        monkeypatch.setitem(PIXELS, px, value)
    got = export_mod._stand_row_types(_Image(["type"]), _Image(["label"]), "<roi>", 10)
    assert got["80"] == 4
    assert {k: v for k, v in got.items() if k != "80"} == {str(s): t for s, t in ROW_TYPE.items()}


def test_every_piece_of_a_stand_takes_the_same_type(fake):
    """Looked up by stand_lbl, so the pieces of a stand in several polygons agree."""
    piece = _Feature({"stand_lbl": 20, "cluster_id": 2}, [])
    other = _Feature({"stand_lbl": 20, "cluster_id": None}, [])
    out = export_mod._take_the_fit_rows_types(_FC([piece, other]), _Dict({"20": 1}))
    assert [f.props["cluster_id"] for f in out.features] == [1, 1]


def test_a_polygon_whose_stand_has_no_row_type_is_set_to_null(fake):
    """Whatever cluster_id it had: the vote is not kept (round 13)."""
    fc = _FC([_Feature({"stand_lbl": 40, "cluster_id": 2}, []), _Feature({"stand_lbl": 20, "cluster_id": 2}, [])])
    out = export_mod._take_the_fit_rows_types(fc, _Dict({"20": 1}))
    assert [f.props["cluster_id"] for f in out.features] == [None, 1]

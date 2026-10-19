"""The superpixel pixel counts at the ROI edge (review B17).

The merge reads two pixel counts of each superpixel from Earth Engine: its pixel count, from
the label histogram (`fmu.utils.adjacency.extract_superpixel_graph`), and the valid-pixel
count of each criterion band, from the grouped reduction (`extract_superpixel_attributes`). It
divides the second by the first (`frac_valid`), and the first feeds its 1 ha and 3 ha gates,
the soft ceiling and the fit's below-minimum exclusion. Before round 13 the two counted
different pixels at the ROI edge: some superpixels got 0 pixels, and `frac_valid`, a fraction,
came out above 1.

Earth Engine takes a pixel into a reduction over a region by one of two rules (the guide's
"Pixels in the region", developers.google.com/earth-engine/guides/reducers_reduce_region):

  - an unweighted reducer takes a pixel whose centre is in the region and whose mask is not
    zero, with weight 1;
  - a weighted one, such as `ee.Reducer.frequencyHistogram()` as it comes ("a (weighted)
    frequency table", the reducer's own description), takes a pixel at least about 1/256 in
    the region, with the smaller of its mask and the fraction of it in the region as weight.

The fake Earth Engine here follows those rules on a small scene that the ROI's edge cuts, so
each reduction the code asks for comes out as Earth Engine would give it. How Earth Engine
admits pixels to a reducer that combines a weighted and an unweighted part is not documented;
the fake takes the reducer handed to the reduction as a whole, weighted if any part of it is,
and then counts each pixel it takes once in `count()`. That choice changes only what the code
before round 13 got, not what any test here expects.
"""

from __future__ import annotations

from fractions import Fraction
from typing import Any

import pytest

import fmu.utils.adjacency as adj
from fmu.utils.adjacency import (
    SuperpixelGraph,
    extract_superpixel_attributes,
    extract_superpixel_graph,
)
from fmu.utils.region_merge import merge_superpixels

# The scene, in pixels: x to the right, y down. The ROI is the rectangle from (0, 0) to
# (3.6, 3.3), so its edges cut the last column (0.6 of each pixel inside, centre inside) and
# the last row (0.3 of each pixel inside, centre outside).
ROI_X, ROI_Y = Fraction(18, 5), Fraction(33, 10)
LABELS = [
    [1, 1, 2, 2],
    [1, 1, 2, 2],
    [3, 3, 4, 5],
    [6, 6, 6, 6],
]
# Canopy height, one value per superpixel; pixel (0, 0) has none.
HEIGHT = {1: 10.0, 2: 14.0, 3: 18.0, 4: 22.0, 5: 26.0, 6: 30.0}
NO_HEIGHT = {(0, 0)}


def _cover(y: int, x: int) -> Fraction:
    """The fraction of pixel (y, x) inside the ROI."""
    return min(Fraction(1), max(Fraction(0), ROI_X - x)) * min(
        Fraction(1), max(Fraction(0), ROI_Y - y)
    )


def _centre_inside(y: int, x: int) -> bool:
    return x + Fraction(1, 2) < ROI_X and y + Fraction(1, 2) < ROI_Y


PIXELS = [(y, x) for y in range(len(LABELS)) for x in range(len(LABELS[0]))]


def _weight(y: int, x: int, weighted: bool, mask: Fraction | None = None) -> Fraction:
    """A pixel's weight in a reduction over the ROI; 0 when the reduction leaves it out.

    `mask` is the image's mask there; by default the label image's, which the segmentation
    stage clips to the ROI, so it is the fraction of the pixel inside.
    """
    cover = _cover(y, x)
    mask = cover if mask is None else mask
    if weighted:
        return min(mask, cover) if cover >= Fraction(1, 256) and mask > 0 else Fraction(0)
    return Fraction(1) if _centre_inside(y, x) and mask > 0 else Fraction(0)


class _Reducer:
    def __init__(self, weighted: bool = True, parts: tuple[str, ...] = ()) -> None:
        self.weighted = weighted
        self.parts = parts

    def unweighted(self) -> _Reducer:
        return _Reducer(False, self.parts)

    def combine(self, other: _Reducer, sharedInputs: bool = False) -> _Reducer:  # noqa: N803
        return _Reducer(self.weighted or other.weighted, self.parts + other.parts)

    def group(self, groupField: int = 0, groupName: str = "") -> _Reducer:  # noqa: N803
        return _Reducer(self.weighted, self.parts + ("group",))

    def forEachBand(self, image: Any) -> _Reducer:  # noqa: N802 - mirrors the ee API
        return _Reducer(self.weighted, self.parts + ("forEachBand",))


class _FakeEE:
    class Reducer:
        @staticmethod
        def frequencyHistogram() -> _Reducer:  # noqa: N802 - mirrors the ee API
            return _Reducer(True, ("histogram",))

        @staticmethod
        def mean() -> _Reducer:
            return _Reducer(True, ("mean",))

        @staticmethod
        def sum() -> _Reducer:
            return _Reducer(True, ("sum",))

        @staticmethod
        def count() -> _Reducer:
            # Unweighted by nature: the guide's example of an unweighted reducer.
            return _Reducer(False, ("count",))


class _Reduction:
    def __init__(self, image: _Image, reducer: _Reducer) -> None:
        self.image, self.reducer = image, reducer


class _Image:
    """Any image the code makes from the scene, with what a reduction of it needs to know."""

    def __init__(
        self, kind: str, *, shift: tuple[int, int] | None = None, labels: list[int] | None = None
    ) -> None:
        self.kind, self.shift, self.labels = kind, shift, labels

    def bandNames(self) -> _Image:  # noqa: N802 - mirrors the ee API
        return self

    def select(self, bands: Any) -> _Image:
        return self

    def rename(self, name: str) -> _Image:
        return self

    def remap(self, frm: list[int], to: list[int]) -> _Image:
        assert to == list(range(len(frm)))
        return _Image("dense", labels=list(frm))

    def projection(self) -> _Image:
        return self

    def nominalScale(self) -> _Image:  # noqa: N802 - mirrors the ee API
        return self

    def atScale(self, scale: int) -> _Image:  # noqa: N802 - mirrors the ee API
        return self

    def crs(self) -> str:
        return "EPSG:32645"

    def reproject(self, proj: Any) -> _Image:
        return self

    def translate(self, x: int, y: int, units: str, proj: Any) -> _Image:
        return _Image("neighbour", shift=(x, y), labels=self.labels)

    def toInt64(self) -> _Image:  # noqa: N802 - mirrors the ee API
        return self

    def multiply(self, other: Any) -> _Image:
        return self

    def add(self, other: _Image) -> _Image:
        assert other.kind == "neighbour"
        return _Image("pair", shift=other.shift, labels=self.labels)

    def neq(self, other: Any) -> _Image:
        return self

    def updateMask(self, mask: Any) -> _Image:  # noqa: N802 - mirrors the ee API
        return self

    def unmask(self, value: Any) -> _Image:
        return self

    def mask(self) -> _Image:
        return self

    def gt(self, other: Any) -> _Image:
        return self

    def addBands(self, other: Any) -> _Image:  # noqa: N802 - mirrors the ee API
        return self

    def reduceRegion(self, **kwargs: Any) -> _Reduction:  # noqa: N802 - mirrors the ee API
        return _Reduction(self, kwargs["reducer"])


def _label_histogram(reducer: _Reducer) -> dict[str, float]:
    out: dict[str, Fraction] = {}
    for y, x in PIXELS:
        w = _weight(y, x, reducer.weighted)
        if w:
            key = str(LABELS[y][x])
            out[key] = out.get(key, Fraction(0)) + w
    return {k: float(v) for k, v in out.items()}


def _pair_histogram(reducer: _Reducer, pair: _Image) -> dict[str, float]:
    """The histogram of `dense * n + neighbour` where the two differ.

    `translate(x=dx, y=dy)` moves image content, so at pixel p the neighbour image holds the
    value of p - (dx, dy), with that pixel's mask; a label the remap was not given is masked.
    """
    assert pair.shift is not None and pair.labels is not None
    dx, dy = pair.shift
    dense = {raw: i for i, raw in enumerate(pair.labels)}
    n = len(pair.labels)
    out: dict[str, Fraction] = {}
    for y, x in PIXELS:
        ny, nx = y - dy, x - dx
        inside = 0 <= ny < len(LABELS) and 0 <= nx < len(LABELS[0])
        a, b = LABELS[y][x], LABELS[ny][nx] if inside else None
        if not inside or a == b or a not in dense or b not in dense:
            # A masked pixel of the pair image. An unweighted histogram counts it under
            # "null" where its centre is in the ROI (read on Earth Engine in round 13).
            if not reducer.weighted and _centre_inside(y, x):
                out["null"] = out.get("null", Fraction(0)) + 1
            continue
        w = _weight(y, x, reducer.weighted, mask=min(_cover(y, x), _cover(ny, nx)))
        if w:
            key = str(dense[a] * n + dense[b])
            out[key] = out.get(key, Fraction(0)) + w
    return {k: float(v) for k, v in out.items()}


def _groups(reducer: _Reducer) -> list[dict[str, Any]]:
    """The grouped sums of canopy height (0 where it has no data) and of its band of pixels
    with data, per label, as `extract_superpixel_attributes` asks since round 13; or, for the
    code before, the grouped mean and count of canopy height."""
    if "sum" in reducer.parts:
        sums: dict[int, Fraction] = {}
        with_data: dict[int, Fraction] = {}
        for y, x in PIXELS:
            # Both bands are unmasked: every pixel the reduction takes counts, by the rule.
            w = _weight(y, x, reducer.weighted, mask=_cover(y, x))
            if w:
                label = LABELS[y][x]
                valid = (y, x) not in NO_HEIGHT
                sums[label] = sums.get(label, Fraction(0)) + (w * HEIGHT[label] if valid else 0)
                with_data[label] = with_data.get(label, Fraction(0)) + (w if valid else 0)
        return [
            {"label": label, "value": float(sums[label]), "has_data": float(with_data[label])}
            for label in sorted(sums)
        ]
    total: dict[int, Fraction] = {}
    weight: dict[int, Fraction] = {}
    count: dict[int, int] = {}
    for y, x in PIXELS:
        label = LABELS[y][x]
        valid = (y, x) not in NO_HEIGHT
        mask = _cover(y, x) if valid else Fraction(0)
        w = _weight(y, x, reducer.weighted, mask=mask)
        if w:
            total[label] = total.get(label, Fraction(0)) + w * Fraction(HEIGHT[label])
            weight[label] = weight.get(label, Fraction(0)) + w
            count[label] = count.get(label, 0) + 1
    return [
        {"label": label, "mean": float(total[label] / weight[label]), "count": count[label]}
        for label in sorted(count)
    ]


@pytest.fixture
def scene(monkeypatch):
    """The fake Earth Engine over the scene; returns (labels, features)."""
    monkeypatch.setattr(adj, "ee", _FakeEE)

    def fake_get_info(obj: Any, *, context: str = "") -> Any:
        if context.endswith("band name") or context.endswith("label band"):
            return ["snic_clusters"]
        if context.endswith(" bands"):
            return ["canopy_height"]
        if context.endswith("projection scale"):
            return 10.0
        if context.endswith("label histogram"):
            return {"snic_clusters": _label_histogram(obj.reducer)}
        if context.endswith("-neighbour pairs"):
            return {"pair": _pair_histogram(obj.reducer, obj.image)}
        if context.endswith(": canopy_height"):
            return {"groups": _groups(obj.reducer)}
        raise AssertionError(f"unexpected getInfo context: {context!r}")

    monkeypatch.setattr(adj, "safe_get_info", fake_get_info)
    return _Image("labels"), _Image("features")


def _graph(scene: tuple[_Image, _Image]) -> SuperpixelGraph:
    labels, _ = scene
    return extract_superpixel_graph(labels, None, 10, context="merge adjacency")


def _edges_by_label(graph: SuperpixelGraph) -> dict[tuple[int, int], int]:
    raw = graph.raw_labels
    return {(raw[i], raw[j]): count for (i, j), count in sorted(graph.edges.items())}


def test_a_superpixel_counts_the_whole_pixels_whose_centre_is_in_the_roi(scene):
    """Superpixel 2 has four pixels inside (two of them 0.6 inside), and superpixel 5 one
    (0.6 inside): a coverage-weighted histogram, truncated, gave them 3 and 0. Superpixel 6
    lies in the last row, whose centres are outside the ROI: it has no pixel in it."""
    g = _graph(scene)
    assert dict(zip(g.raw_labels, g.n_pixels, strict=True)) == {1: 4, 2: 4, 3: 2, 4: 1, 5: 1}


def test_the_shared_boundaries_count_whole_pixel_pairs_on_the_same_rule(scene):
    """Each boundary pixel pair once, taken where the pixel's centre is in the ROI: pairs at
    the edge are neither a fraction (truncated to 0) nor counted outside it."""
    assert _edges_by_label(_graph(scene)) == {
        (1, 2): 2,
        (1, 3): 2,
        (2, 4): 1,
        (2, 5): 1,
        (3, 4): 1,
        (4, 5): 1,
    }


def test_no_valid_count_is_above_its_superpixels_pixel_count(scene):
    """frac_valid is valid pixels over pixels, a fraction: both counts on one rule keep it at
    most 1 for every superpixel, and so for every stand. Superpixel 1 has one pixel with no
    height (frac_valid 0.75)."""
    g = _graph(scene)
    _, features = scene
    means, counts = extract_superpixel_attributes(
        features, scene[0], g, None, 10, context="merge criteria"
    )
    by_label = {g.raw_labels[i]: (c["canopy_height"], g.n_pixels[i]) for i, c in counts.items()}
    assert {lab: vc for lab, vc in by_label.items() if vc[0] > vc[1]} == {}
    assert by_label == {1: (3, 4), 2: (4, 4), 3: (2, 2), 4: (1, 1), 5: (1, 1)}

    # Merged with tolerances nothing passes and a minimum nothing is below, each superpixel
    # is a stand of its own: none of 0 pixels, and no frac_valid above 1.
    result = merge_superpixels(
        g,
        means,
        counts,
        criteria={"canopy_height": 0.001},
        relax_factor=1.0,
        min_area_ha=0.0,
        max_area_ha=10.0,
        min_defined_criteria=1,
        min_frac_valid=0.5,
        max_pass2_iterations=1,
    )
    stands = list(result.stand_attributes.values())
    assert result.n_stands == g.n_regions
    assert min(s["n_pixels"] for s in stands) >= 1
    assert max(s["frac_valid_canopy_height"] for s in stands) <= 1.0


# ---------------------------------------------------------------------------
# The check, and the rounding
# ---------------------------------------------------------------------------


def test_a_valid_count_above_the_pixel_count_is_refused(scene):
    """If the two reductions ever count different pixels again (another rule, another grid),
    the merge is stopped rather than given a frac_valid above 1. Superpixel 1 has 3 pixels
    with a height; here the graph gives it 2."""
    graph = SuperpixelGraph(raw_labels=[1, 2], n_pixels=[2, 4], edges={(0, 1): 2}, scale_m=10)
    _, features = scene
    with pytest.raises(ValueError, match="frac_valid"):
        extract_superpixel_attributes(features, scene[0], graph, None, 10, context="merge criteria")


def test_a_count_read_a_hair_below_a_whole_number_is_rounded_not_truncated(monkeypatch):
    """An unweighted histogram holds whole numbers. Read as floats, each is rounded to the
    nearest whole pixel, so a value a hair below one cannot lose a pixel to int()."""
    monkeypatch.setattr(adj, "ee", _FakeEE)

    def fake_get_info(obj: Any, *, context: str = "") -> Any:
        if context.endswith("band name"):
            return ["snic_clusters"]
        if context.endswith("projection scale"):
            return 10.0
        if context.endswith("label histogram"):
            return {"snic_clusters": {"1": 3.9999999999999996, "2": 4.000000000000001}}
        if context.endswith("right-neighbour pairs"):
            return {"pair": {"1": 1.9999999999999998}}  # dense 0 beside dense 1
        if context.endswith("down-neighbour pairs"):
            return {"pair": {}}
        raise AssertionError(f"unexpected getInfo context: {context!r}")

    monkeypatch.setattr(adj, "safe_get_info", fake_get_info)
    g = extract_superpixel_graph(_Image("labels"), None, 10, context="merge adjacency")
    assert g.n_pixels == [4, 4]
    assert g.edges == {(0, 1): 2}


# ---------------------------------------------------------------------------
# The same reductions, built with the real Earth Engine client
# ---------------------------------------------------------------------------


def _invocations(node: Any, out: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(node, dict):
        inv = node.get("functionInvocationValue")
        if isinstance(inv, dict):
            out.append(inv)
        for value in node.values():
            _invocations(value, out)
    elif isinstance(node, list):
        for value in node:
            _invocations(value, out)
    return out


def test_the_reducer_of_every_reduction_is_unweighted_as_a_whole(monkeypatch):
    """Offline, as tests/test_mask_before_snic_ee_graph.py: earthengine-api's own test
    initialisation loads the algorithm signatures it ships and sends nothing. Each of the
    four reductions (the label histogram, the two pair histograms, the grouped mean and
    count) must hand reduceRegion `Reducer.unweighted` itself, not a reducer with an
    unweighted part, so that Earth Engine takes the pixels by the centre rule in each."""
    apitestcase = pytest.importorskip("ee.apitestcase")

    class _Offline(apitestcase.ApiTestCase):
        __test__ = False

        def runTest(self) -> None:  # noqa: N802 - unittest's name
            pass

    case = _Offline()
    case.setUp()
    try:
        import ee

        reducers: dict[str, dict[str, Any]] = {}

        def get_info(obj: Any, *, context: str = "") -> Any:
            encoded = ee.serializer.encode(obj, for_cloud_api=True)
            (reduction,) = [
                i for i in _invocations(encoded, []) if i["functionName"] == "Image.reduceRegion"
            ] or [None]
            if reduction is not None:
                reducers[context] = reduction["arguments"]["reducer"]["functionInvocationValue"]
            if context.endswith("band name") or context.endswith("label band"):
                return ["snic_clusters"]
            if context.endswith(" bands"):
                return ["canopy_height"]
            if context.endswith("projection scale"):
                return 10.0
            if context.endswith("label histogram"):
                return {"snic_clusters": {"11": 4, "22": 4}}
            if context.endswith("-neighbour pairs"):
                return {"pair": {"1": 2}}
            if context.endswith(": canopy_height"):
                return {"groups": [{"label": 11, "mean": 5.0, "count": 4}]}
            raise AssertionError(f"unexpected request: {context!r}")

        monkeypatch.setattr(adj, "safe_get_info", get_info)
        roi = ee.Geometry.Rectangle([82.80, 18.50, 82.85, 18.55])
        labels = ee.Image("projects/fake/assets/snic_clusters")
        graph = extract_superpixel_graph(labels, roi, 10, context="merge adjacency")
        extract_superpixel_attributes(
            ee.Image("projects/fake/assets/criteria"), labels, graph, roi, 10,
            context="merge criteria",
        )
    finally:
        case.tearDown()

    assert sorted(reducers) == [
        "merge adjacency down-neighbour pairs",
        "merge adjacency label histogram",
        "merge adjacency right-neighbour pairs",
        "merge criteria: canopy_height",
    ]
    outermost = {context: r["functionName"] for context, r in reducers.items()}
    assert outermost == dict.fromkeys(reducers, "Reducer.unweighted")


def test_no_masked_band_goes_into_the_grouped_reduction(monkeypatch):
    """Earth Engine's grouped unweighted reducers add a band's masked pixels into the sum (and
    so the mean) they give a group, though their count leaves them out (read on Earth Engine
    in round 13, docs/handoff/2026-10-20-round13.md). So each criterion band goes into the
    grouped reduction unmasked, with 0 where it has no data, beside a band of 1 where it has
    data. On the code before (B17 as first written) the band went in as it is."""
    from _ee_recorder import Rec, calls, made_by

    log: list = []
    monkeypatch.setattr(adj, "ee", Rec("ee", log))

    def fake_get_info(obj: Any, *, context: str = "") -> Any:
        if context.endswith(" bands"):
            return ["canopy_height"]
        if context.endswith("label band"):
            return ["snic_clusters"]
        return {"groups": []}

    monkeypatch.setattr(adj, "safe_get_info", fake_get_info)
    graph = SuperpixelGraph(raw_labels=[1], n_pixels=[4], edges={}, scale_m=10)
    extract_superpixel_attributes(Rec("features", log), Rec("labels", log), graph, None, 10)
    (reduction,) = calls(log, ".reduceRegion")
    with_labels = made_by(log, reduction.owner)
    assert with_labels.attr == "addBands"
    summed = made_by(log, with_labels.owner)
    assert summed.attr == "addBands"
    renamed = made_by(log, summed.owner)
    unmasked = made_by(log, renamed.owner)
    assert (unmasked.attr, unmasked.args) == ("unmask", (0,))
    (has_data,) = summed.args
    above_zero = made_by(log, made_by(log, has_data).owner)
    assert (above_zero.attr, above_zero.args) == ("gt", (0,))
    assert made_by(log, above_zero.owner).attr == "mask"
    assert made_by(log, above_zero.owner).owner is unmasked.owner  # the same band



def test_the_masked_pixels_an_unweighted_histogram_counts_under_null_are_no_superpixel(monkeypatch):
    """An unweighted frequencyHistogram counts the region's masked pixels under the key "null"
    (read on Earth Engine in round 13: 104 masked pixels of a 200-pixel region beside the four
    labels' counts; a weighted one leaves them out). They belong to no superpixel and to no
    boundary pair. On B17 as first written the graph stopped on the key
    (ValueError: could not convert string to float: 'null')."""
    monkeypatch.setattr(adj, "ee", _FakeEE)

    def fake_get_info(obj: Any, *, context: str = "") -> Any:
        if context.endswith("band name"):
            return ["snic_clusters"]
        if context.endswith("projection scale"):
            return 10.0
        if context.endswith("label histogram"):
            return {"snic_clusters": {"1": 4.0, "2": 4.0, "null": 7.0}}
        if context.endswith("-neighbour pairs"):
            return {"pair": {"1": 2.0, "null": 9.0}}
        raise AssertionError(f"unexpected getInfo context: {context!r}")

    monkeypatch.setattr(adj, "safe_get_info", fake_get_info)
    g = extract_superpixel_graph(_Image("labels"), None, 10, context="merge adjacency")
    assert (g.raw_labels, g.n_pixels) == ([1, 2], [4, 4])
    assert g.edges == {(0, 1): 4}  # the right and the down pairs, two each

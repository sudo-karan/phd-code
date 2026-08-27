"""Non-live tests for `fmu.utils.adjacency`.

Earth Engine is faked: a small numpy-free label raster is turned into the exact
histogram payloads the real reductions would return, so the decision logic (dense
relabelling, pair encoding/decoding, 4- vs 8-connectivity, shared-edge lengths,
the size guard) is pinned without a server.

The reference case is a 4x4 raster with a diagonal contact, because that is the
one thing the connectivity choice has to get right: regions 1 and 4 touch only
corner-to-corner, so they share *zero* boundary length and must not appear as an
edge. Counting them would inflate the merge's pass-2 shared-edge tie-break with
pairs that do not actually share an edge.
"""

from __future__ import annotations

import pytest

import fmu.utils.adjacency as adj
from fmu.utils.adjacency import (
    SuperpixelGraph,
    TooManySuperpixelsError,
    extract_superpixel_graph,
)

# A 4x4 label raster:
#
#     1 1 2 2
#     1 1 2 2
#     3 3 4 4
#     3 3 4 4
#
# 4-connected adjacencies: 1-2 (2 px), 1-3 (2 px), 2-4 (2 px), 3-4 (2 px).
# 1-4 and 2-3 touch only diagonally and must NOT be edges.
GRID = [
    [1, 1, 2, 2],
    [1, 1, 2, 2],
    [3, 3, 4, 4],
    [3, 3, 4, 4],
]

# A raster where one region wraps another, to check degree and asymmetric
# boundary lengths:
#
#     5 5 5 5
#     5 9 9 5
#     5 9 9 5
#     5 5 5 5
NESTED = [
    [5, 5, 5, 5],
    [5, 9, 9, 5],
    [5, 9, 9, 5],
    [5, 5, 5, 5],
]


def _label_histogram(grid: list[list[int]]) -> dict[str, float]:
    counts: dict[str, float] = {}
    for row in grid:
        for v in row:
            counts[str(v)] = counts.get(str(v), 0.0) + 1.0
    return counts


def _pair_histogram(
    grid: list[list[int]], raw_labels: list[int], dx: int, dy: int
) -> dict[str, float]:
    """The encoded-pair histogram the server would return for one shift.

    `translate(x=dx, y=dy)` moves image content, so at pixel p the shifted image
    holds the value from p - (dx, dy). The stage uses dx=-1 (right neighbour)
    and dy=-1 (down neighbour).
    """
    n = len(raw_labels)
    dense = {raw: i for i, raw in enumerate(raw_labels)}
    h = len(grid)
    w = len(grid[0])
    out: dict[str, float] = {}
    for y in range(h):
        for x in range(w):
            nx, ny = x - dx, y - dy
            if not (0 <= nx < w and 0 <= ny < h):
                continue  # neighbour outside the ROI is masked
            a, b = dense[grid[y][x]], dense[grid[ny][nx]]
            if a == b:
                continue  # updateMask(dense.neq(neighbour))
            key = str(a * n + b)
            out[key] = out.get(key, 0.0) + 1.0
    return out


class _FakeImage:
    def __init__(self, band: str = "snic_clusters", nominal_scale: float = 10.0) -> None:
        self.band = band
        self.nominal_scale = nominal_scale

    def bandNames(self):  # noqa: N802
        return [self.band]

    def select(self, bands):
        return self

    def rename(self, name):
        return self

    def remap(self, frm, to):
        return self

    def projection(self):
        return self

    def nominalScale(self):  # noqa: N802
        return self.nominal_scale

    def atScale(self, scale):  # noqa: N802 - mirrors the ee API
        return self

    def reproject(self, proj):
        return self

    def translate(self, **kwargs):
        return _Shift(kwargs["x"], kwargs["y"])

    def multiply(self, other):
        return self

    def add(self, other):
        return _Pair(other.dx, other.dy)

    def neq(self, other):
        return self

    def updateMask(self, mask):  # noqa: N802 - mirrors the ee API
        return self

    def toInt64(self):  # noqa: N802 - mirrors the ee API
        return self

    def reduceRegion(self, **kwargs):  # noqa: N802 - mirrors the ee API
        return self


class _Shift:
    def __init__(self, dx: int, dy: int) -> None:
        self.dx, self.dy = dx, dy


class _Pair(_FakeImage):
    def __init__(self, dx: int, dy: int) -> None:
        super().__init__("pair")
        self.dx, self.dy = dx, dy

    def updateMask(self, mask):  # noqa: N802 - mirrors the ee API
        return self

    def rename(self, name):
        return self


class _FakeEE:
    """Just enough of `ee` for this module. Building real reducers needs an
    initialized client, which is the point of not doing it."""

    class Reducer:
        @staticmethod
        def frequencyHistogram():  # noqa: N802
            return object()


@pytest.fixture
def server(monkeypatch):
    """Serve the histograms a given grid would produce."""
    monkeypatch.setattr(adj, "ee", _FakeEE)

    def install(grid: list[list[int]], nominal_scale: float = 10.0):
        raw_labels = sorted({v for row in grid for v in row})

        def fake_get_info(obj, *, context: str = ""):
            if "band name" in context:
                return ["snic_clusters"]
            if "projection scale" in context:
                return nominal_scale
            if "label histogram" in context:
                return {"snic_clusters": _label_histogram(grid)}
            if "right-neighbour" in context:
                return {"pair": _pair_histogram(grid, raw_labels, -1, 0)}
            if "down-neighbour" in context:
                return {"pair": _pair_histogram(grid, raw_labels, 0, -1)}
            raise AssertionError(f"unexpected getInfo context: {context!r}")

        monkeypatch.setattr(adj, "safe_get_info", fake_get_info)
        return _FakeImage(nominal_scale=nominal_scale)

    return install


# ---------- graph extraction ----------


def test_dense_relabelling_preserves_raw_labels(server):
    labels = server(GRID)
    g = extract_superpixel_graph(labels, None, 10)
    assert g.raw_labels == [1, 2, 3, 4]
    assert g.n_regions == 4


def test_pixel_counts_align_with_dense_index(server):
    labels = server(GRID)
    g = extract_superpixel_graph(labels, None, 10)
    assert g.n_pixels == [4, 4, 4, 4]


def test_four_connectivity_finds_the_edge_sharing_pairs(server):
    labels = server(GRID)
    g = extract_superpixel_graph(labels, None, 10)
    # dense indices: 1->0, 2->1, 3->2, 4->3
    assert set(g.edges) == {(0, 1), (0, 2), (1, 3), (2, 3)}


def test_diagonal_contacts_are_not_edges(server):
    """The reason connectivity is 4 here even though SNIC runs 8: a corner
    contact has zero shared boundary length, so counting it would inflate the
    pass-2 shared-edge tie-break."""
    labels = server(GRID)
    g = extract_superpixel_graph(labels, None, 10)
    assert (0, 3) not in g.edges  # 1 and 4 touch only at a corner
    assert (1, 2) not in g.edges  # 2 and 3 likewise
    assert g.shared_edge_m(0, 3) == 0.0


def test_each_boundary_pixel_pair_is_counted_once(server):
    """Right and down shifts only. Taking all four would double every count."""
    labels = server(GRID)
    g = extract_superpixel_graph(labels, None, 10)
    for edge in g.edges:
        assert g.edges[edge] == 2, edge


def test_shared_edge_length_is_pixel_pairs_times_scale(server):
    labels = server(GRID)
    g = extract_superpixel_graph(labels, None, 10)
    assert g.shared_edge_m(0, 1) == 20.0  # 2 pairs x 10 m
    g30 = extract_superpixel_graph(server(GRID), None, 30)
    assert g30.shared_edge_m(0, 1) == 60.0


def test_shared_edge_is_symmetric(server):
    labels = server(GRID)
    g = extract_superpixel_graph(labels, None, 10)
    assert g.shared_edge_m(0, 1) == g.shared_edge_m(1, 0)


def test_neighbours_is_symmetric_and_complete(server):
    labels = server(GRID)
    nb = extract_superpixel_graph(labels, None, 10).neighbours()
    assert nb == {0: {1, 2}, 1: {0, 3}, 2: {0, 3}, 3: {1, 2}}


def test_nested_region_has_the_full_shared_boundary(server):
    """The inner 2x2 block touches the ring on all four sides: 8 pixel pairs."""
    labels = server(NESTED)
    g = extract_superpixel_graph(labels, None, 10)
    assert g.raw_labels == [5, 9]
    assert g.edges == {(0, 1): 8}
    assert g.shared_edge_m(0, 1) == 80.0


def test_area_ha_from_pixel_count(server):
    labels = server(NESTED)
    g = extract_superpixel_graph(labels, None, 10)
    # ring = 12 px, inner = 4 px, at 10 m => 100 m^2 each
    assert g.area_ha(0) == pytest.approx(0.12)
    assert g.area_ha(1) == pytest.approx(0.04)


def test_summary_reports_graph_shape(server):
    labels = server(GRID)
    s = extract_superpixel_graph(labels, None, 10).summary()
    assert s == {
        "n_regions": 4,
        "n_edges": 4,
        "mean_degree": 2.0,
        "n_isolated": 0,
    }


def test_single_region_has_no_edges(server):
    labels = server([[7, 7], [7, 7]])
    g = extract_superpixel_graph(labels, None, 10)
    assert g.n_regions == 1
    assert g.edges == {}
    assert g.summary()["n_isolated"] == 1


def test_empty_roi_returns_an_empty_graph(server):
    labels = server([])
    g = extract_superpixel_graph(labels, None, 10)
    assert g.n_regions == 0
    assert g.edges == {}


# ---------- the size guard ----------


def test_raises_above_max_superpixels(server):
    labels = server(GRID)
    with pytest.raises(TooManySuperpixelsError, match="max_superpixels"):
        extract_superpixel_graph(labels, None, 10, max_superpixels=3)


def test_error_names_the_knob_to_change(server):
    labels = server(GRID)
    with pytest.raises(TooManySuperpixelsError) as exc:
        extract_superpixel_graph(labels, None, 10, max_superpixels=1)
    msg = str(exc.value)
    assert "merge.max_superpixels" in msg
    assert "segmentation.size" in msg


def test_exactly_at_the_limit_passes(server):
    labels = server(GRID)
    assert extract_superpixel_graph(labels, None, 10, max_superpixels=4).n_regions == 4


# ---------- the projection guard ----------


def test_rejects_ees_default_projection(server):
    """An unbaked computed image reports WGS84 at ~111 km. Reprojecting that to
    10 m gives a valid grid in the wrong CRS, so adjacency would be measured on
    a resampled raster and return the wrong neighbours -- silently."""
    labels = server(GRID, nominal_scale=111_319.0)
    with pytest.raises(ValueError, match="default projection"):
        extract_superpixel_graph(labels, None, 10)


def test_accepts_a_real_pixel_grid(server):
    labels = server(GRID, nominal_scale=10.0)
    assert extract_superpixel_graph(labels, None, 10).n_regions == 4


def test_tolerates_modest_scale_mismatch(server):
    """A 30 m label image analysed at 10 m is a real grid, just a coarse one --
    the caller's problem to reconcile, not a silent-corruption case."""
    labels = server(GRID, nominal_scale=30.0)
    assert extract_superpixel_graph(labels, None, 10).n_regions == 4


# ---------- SuperpixelGraph on its own ----------


def test_shared_edge_of_unknown_pair_is_zero():
    g = SuperpixelGraph(raw_labels=[1, 2], n_pixels=[4, 4], edges={}, scale_m=10)
    assert g.shared_edge_m(0, 1) == 0.0


def test_isolated_regions_are_counted():
    g = SuperpixelGraph(
        raw_labels=[1, 2, 3], n_pixels=[1, 1, 1], edges={(0, 1): 3}, scale_m=10
    )
    assert g.summary()["n_isolated"] == 1
    assert g.neighbours()[2] == set()


# ---------- stand geometry ----------


def test_summarize_reports_the_concentration_statistic():
    """The number that makes the dissolve-by-cluster pathology legible: 505
    units where 6% held 68% of the area looks unremarkable in a mean or a
    median, and is obvious in the largest-decile share."""
    from fmu.utils.adjacency import summarize_stand_geometry

    # 9 slivers of 0.1 ha and 1 blob of 91 ha -- the committed layer's shape.
    geometry = {
        i: {"area_ha": 0.1, "polsby_popper": 0.29, "n_pixels": 10, "perimeter_m": 40}
        for i in range(9)
    }
    geometry[9] = {
        "area_ha": 91.0,
        "polsby_popper": 0.29,
        "n_pixels": 9100,
        "perimeter_m": 4000,
    }
    s = summarize_stand_geometry(geometry, min_area_ha=1.0)
    assert s["n_stands"] == 10
    assert s["area_share_largest_decile"] == pytest.approx(91.0 / 91.9, abs=1e-3)
    assert s["stands_below_min_area"] == 9
    assert s["frac_stands_below_min_area"] == pytest.approx(0.9)
    assert s["area_in_undersized_stands_ha"] == pytest.approx(0.9)


def test_summarize_reports_the_area_distribution():
    from fmu.utils.adjacency import summarize_stand_geometry

    geometry = {
        i: {
            "area_ha": float(i + 1),
            "polsby_popper": 0.3,
            "n_pixels": (i + 1) * 100,
            "perimeter_m": 100,
        }
        for i in range(10)
    }
    s = summarize_stand_geometry(geometry, min_area_ha=1.0)
    assert s["area_ha_min"] == 1.0
    assert s["area_ha_max"] == 10.0
    assert s["area_ha_mean"] == pytest.approx(5.5)
    assert s["area_ha_min"] <= s["area_ha_p10"] <= s["area_ha_median"]
    assert s["area_ha_median"] <= s["area_ha_p90"] <= s["area_ha_max"]


def test_summarize_handles_an_empty_partition():
    from fmu.utils.adjacency import summarize_stand_geometry

    assert summarize_stand_geometry({}, min_area_ha=1.0) == {"n_stands": 0}


def test_summarize_reports_polsby_popper_range():
    from fmu.utils.adjacency import summarize_stand_geometry

    geometry = {
        0: {"area_ha": 1.0, "polsby_popper": 0.10, "n_pixels": 100, "perimeter_m": 200},
        1: {"area_ha": 1.0, "polsby_popper": 0.50, "n_pixels": 100, "perimeter_m": 100},
        2: {"area_ha": 1.0, "polsby_popper": 0.90, "n_pixels": 100, "perimeter_m": 80},
    }
    s = summarize_stand_geometry(geometry, min_area_ha=0.5)
    assert s["polsby_popper_min"] == 0.10
    assert s["polsby_popper_max"] == 0.90
    assert s["stands_below_min_area"] == 0


# ---------- the grouped reductions ----------
#
# Both of these were only ever exercised live, which is how a band name EE
# rejects and a silently-inherited CRS got as far as a real run.


def _grouped_reducer_ee():
    """Enough of `ee.Reducer` for the two grouped reductions in this module."""

    class _Reducer:
        def combine(self, other, sharedInputs=False):  # noqa: N803 - mirrors ee
            return self

        def group(self, groupField=None, groupName=None):  # noqa: N803 - mirrors ee
            return self

    class _FakeEE:
        class Reducer:
            @staticmethod
            def mean():
                return _Reducer()

            @staticmethod
            def count():
                return _Reducer()

            @staticmethod
            def sum():
                return _Reducer()

        @staticmethod
        def Image(*a, **k):  # noqa: N802 - mirrors the ee API
            raise AssertionError("not needed by these tests")

    return _FakeEE


class _Reduced:
    def __init__(self, payload, kwargs):
        self.payload = payload
        self.kwargs = kwargs

    def getInfo(self):  # noqa: N802 - mirrors the ee API
        return self.payload


class _FakeFeatures:
    """A feature stack whose own projection is EE's WGS84 default -- the shape
    an uncached computed image really has."""

    def __init__(self, bands, groups, record):
        self._bands = bands
        self._groups = groups
        self._record = record

    def bandNames(self):  # noqa: N802 - mirrors the ee API
        return self._bands

    def select(self, bands):
        return self

    def addBands(self, other):  # noqa: N802 - mirrors the ee API
        return self

    def reduceRegion(self, **kwargs):  # noqa: N802 - mirrors the ee API
        self._record.append(kwargs)
        return _Reduced({"groups": self._groups}, kwargs)


class _FakeLabels:
    def __init__(self, record, crs="EPSG:32643"):
        self._record = record
        self._crs = crs

    def bandNames(self):  # noqa: N802 - mirrors the ee API
        return ["snic_clusters"]

    def select(self, bands):
        return self

    def rename(self, name):
        self._record.append(("rename", name))
        return self

    def projection(self):
        return self

    def crs(self):
        return self._crs


@pytest.fixture
def attribute_server(monkeypatch):
    monkeypatch.setattr(adj, "ee", _grouped_reducer_ee())

    def fake_get_info(obj, *, context: str = ""):
        return obj.getInfo() if hasattr(obj, "getInfo") else obj

    monkeypatch.setattr(adj, "safe_get_info", fake_get_info)


def _attributes(groups, record, bands=("canopy_height",)):
    from fmu.utils.adjacency import extract_superpixel_attributes

    graph = SuperpixelGraph(
        raw_labels=[11, 22], n_pixels=[100, 100], edges={(0, 1): 5}, scale_m=10
    )
    features = _FakeFeatures(list(bands), groups, record)
    return extract_superpixel_attributes(
        features, _FakeLabels(record), graph, None, 10, context="merge criteria"
    )


def test_the_group_band_name_is_one_earth_engine_accepts(attribute_server):
    """`Image.rename: Invalid band name: '_label'` -- EE refuses a leading
    underscore, and only says so at getInfo time, so this failed halfway through
    a live run rather than in CI."""
    record = []
    _attributes([{"label": 11, "mean": 5.0, "count": 100}], record)

    renamed = [
        entry[1] for entry in record if isinstance(entry, tuple) and entry[0] == "rename"
    ]
    assert renamed, "the label band is never renamed"
    for name in renamed:
        assert not name.startswith("_"), f"EE rejects the band name {name!r}"
        assert name[0].isalpha()
        assert all(c.isalnum() or c == "_" for c in name)


def test_the_reduction_is_pinned_to_the_label_grid(attribute_server):
    """`reduceRegion` defaults its CRS to the *first band's* projection, which
    here is a feature band off an uncached computed image. Inheriting it would
    count valid pixels on a geographic grid while `graph.n_pixels` holds label
    grid pixels -- and `min_frac_valid` divides one by the other."""
    record = []
    _attributes([{"label": 11, "mean": 5.0, "count": 100}], record)

    kwargs = [k for k in record if isinstance(k, dict)]
    assert kwargs, "no reduction ran"
    for k in kwargs:
        assert k["crs"] == "EPSG:32643"
        assert k["scale"] == 10


def test_a_feature_band_colliding_with_the_group_band_is_refused(attribute_server):
    with pytest.raises(ValueError, match="collides"):
        _attributes([], [], bands=(adj._GROUP_BAND, "canopy_height"))


def test_a_band_with_no_valid_pixel_reads_as_none_not_zero(attribute_server):
    """14 of the committed baseline's superpixels have no ETH canopy height at
    all. Calling that 0.0 m would invent a clear-cut and merge it into one."""
    record = []
    means, counts = _attributes(
        [
            {"label": 11, "mean": 5.0, "count": 100},
            {"label": 22, "mean": None, "count": 0},
        ],
        record,
    )
    assert means[0]["canopy_height"] == 5.0
    assert means[1]["canopy_height"] is None
    assert counts[1]["canopy_height"] == 0


def test_a_label_the_histogram_never_saw_is_skipped(attribute_server):
    """Different reductions can disagree at the very edge of the ROI."""
    record = []
    means, _ = _attributes(
        [
            {"label": 11, "mean": 5.0, "count": 100},
            {"label": 999, "mean": 7.0, "count": 100},
        ],
        record,
    )
    assert set(means) == {0}

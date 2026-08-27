"""Non-live tests for `fmu.utils.grid`.

The grid is the unit of every raster measurement the pipeline reports -- area,
perimeter, compactness, the component-size cap, and through `max_area_ha` the
merge gate itself. All of that is `pixel count x assumed pixel size`, which is
only true in a CRS whose pixels really are square metres.

The bug these pin: a live run logged `output grid: EPSG:4326 at 10.0 m`. That
reads like a 10 m grid and is not one -- EE's default WGS84 projection put
through `atScale(10)` gives pixels 10 m tall and `10 * cos(lat)` m wide, 8.8 m
at Sanjay Van's 28.5 deg N. Every area was therefore ~14% high, and nothing in
the output said so.
"""

from __future__ import annotations

import pytest

import fmu.utils.grid as grid_mod
from fmu.utils.grid import analysis_grid, utm_epsg_code

# Sanjay Van, New Delhi -- the ROI every committed run uses.
SANJAY_VAN_LON = 77.19
SANJAY_VAN_LAT = 28.51


# ---------- zone arithmetic ----------


def test_sanjay_van_is_utm_43n():
    assert utm_epsg_code(SANJAY_VAN_LON, SANJAY_VAN_LAT) == 32643


def test_southern_hemisphere_gets_the_327xx_family():
    # Same zone, opposite hemisphere: Bangalore's longitude at a southern
    # latitude. UTM numbers the zone identically and swaps the EPSG family.
    assert utm_epsg_code(77.19, -28.51) == 32743


def test_the_equator_counts_as_north():
    # An arbitrary boundary, but it has to be decided somewhere and stay decided
    # -- a run that flipped families at lat 0 would report two grids for one ROI.
    assert utm_epsg_code(0.0, 0.0) == 32631


@pytest.mark.parametrize(
    ("lon", "zone"),
    [
        (-180.0, 1),
        (-179.9, 1),
        (-174.1, 1),
        (-174.0, 2),
        (0.0, 31),
        (5.9, 31),
        (6.0, 32),
        (179.9, 60),
    ],
)
def test_zone_boundaries(lon, zone):
    assert utm_epsg_code(lon, 10.0) == 32600 + zone


def test_the_antimeridian_does_not_invent_a_zone_61():
    """`floor((180 + 180) / 6) + 1` is 61, which is not a UTM zone."""
    assert utm_epsg_code(180.0, 10.0) == 32660


@pytest.mark.parametrize("lat", [84.5, -84.5, 90.0, -90.0])
def test_polar_latitudes_are_refused(lat):
    """UTM is undefined past 84 deg. Picking the nearest zone anyway would hand
    back a badly distorted grid that still reports a plausible nominal scale."""
    with pytest.raises(ValueError, match="outside UTM"):
        utm_epsg_code(0.0, lat)


# ---------- grid construction ----------


class _FakeCoords:
    def __init__(self, ring):
        self.ring = ring

    def getInfo(self):  # noqa: N802 - mirrors the ee API
        return [self.ring]


class _FakeBounds:
    def __init__(self, ring):
        self.ring = ring

    def coordinates(self):
        return _FakeCoords(self.ring)


class _FakeROI:
    def __init__(self, west, south, east, north):
        self.ring = [
            [west, south],
            [east, south],
            [east, north],
            [west, north],
            [west, south],
        ]
        self.max_error = None

    def bounds(self, maxError=None):  # noqa: N803 - mirrors the ee API
        self.max_error = maxError
        return _FakeBounds(self.ring)


class _FakeProjection:
    def __init__(self, crs):
        self.crs = crs
        self.scale = None

    def atScale(self, scale):  # noqa: N802 - mirrors the ee API
        self.scale = scale
        return self


@pytest.fixture
def fake_ee(monkeypatch):
    made = []

    class _FakeEE:
        @staticmethod
        def Projection(crs):  # noqa: N802 - mirrors the ee API
            proj = _FakeProjection(crs)
            made.append(proj)
            return proj

    monkeypatch.setattr(grid_mod, "ee", _FakeEE)
    return made


def test_grid_is_the_rois_utm_zone_at_the_analysis_scale(fake_ee):
    roi = _FakeROI(77.18, 28.50, 77.20, 28.52)
    proj = analysis_grid(roi, 10)

    assert proj.crs == "EPSG:32643"
    assert proj.scale == 10
    assert len(fake_ee) == 1


def test_grid_is_not_geographic(fake_ee):
    """The whole point. EPSG:4326 at a 10 m nominal scale is a different raster
    from a 10 m UTM grid, and only one of them has square pixels."""
    proj = analysis_grid(_FakeROI(77.18, 28.50, 77.20, 28.52), 10)
    assert proj.crs != "EPSG:4326"


def test_grid_follows_a_non_default_analysis_scale(fake_ee):
    proj = analysis_grid(_FakeROI(77.18, 28.50, 77.20, 28.52), 30)
    assert proj.scale == 30


def test_grid_uses_the_bounding_box_midpoint(fake_ee):
    """Zone comes from the middle of the ROI, so distortion is split between the
    east and west edges rather than piled onto one of them."""
    # Straddles the 78 deg boundary between zones 43 and 44, midpoint at 78.0 in
    # zone 44.
    proj = analysis_grid(_FakeROI(77.0, 28.0, 79.0, 29.0), 10)
    assert proj.crs == "EPSG:32644"


def test_a_zone_straddling_roi_warns_but_still_returns_one_grid(fake_ee, caplog):
    """One run has to measure everything in one CRS or nothing in it compares.
    Say so rather than letting it show up as an unexplained area gradient."""
    with caplog.at_level("WARNING"):
        proj = analysis_grid(_FakeROI(77.0, 28.0, 79.0, 29.0), 10)

    assert proj.crs == "EPSG:32644"
    assert "spans UTM zones" in caplog.text
    assert "32643" in caplog.text and "32644" in caplog.text


def test_a_single_zone_roi_does_not_warn(fake_ee, caplog):
    with caplog.at_level("WARNING"):
        analysis_grid(_FakeROI(77.18, 28.50, 77.20, 28.52), 10)
    assert "spans UTM zones" not in caplog.text


def test_bounds_are_requested_with_a_max_error(fake_ee):
    """`bounds()` on an unprojected geometry needs an error margin; omitting it
    raises server-side."""
    roi = _FakeROI(77.18, 28.50, 77.20, 28.52)
    analysis_grid(roi, 10)
    assert roi.max_error == 1


def test_one_round_trip_only(fake_ee):
    """Bounds give the midpoint and the straddle check together. Two getInfos
    for two facts about the same box would be one round trip too many."""
    calls = {"n": 0}
    roi = _FakeROI(77.18, 28.50, 77.20, 28.52)
    real_bounds = roi.bounds

    def counting_bounds(maxError=None):  # noqa: N803 - mirrors the ee API
        calls["n"] += 1
        return real_bounds(maxError=maxError)

    roi.bounds = counting_bounds
    analysis_grid(roi, 10)
    assert calls["n"] == 1

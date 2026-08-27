"""The analysis pixel grid: one projected CRS the whole run measures in.

Every raster measurement the pipeline makes -- superpixel adjacency, stand area,
perimeter, compactness, the component-size cap -- is a count of pixels times an
assumed pixel size. That arithmetic is only true if the pixels really are
`analysis_scale_m` square, which makes the *CRS* as load-bearing as the scale.

They were not. EE gives an unbaked computed image its default WGS84 1-degree
projection, and `atScale(10)` on that yields a geographic grid whose nominal
scale reads 10 m but whose pixels are 10 m tall and `10 * cos(lat)` m wide --
8.8 m at Sanjay Van's 28.5 deg N. Calling those pixels 100 m^2 overstates every
area by about 14%, anisotropically, which lands directly on the merge's
hectare-denominated gates (`min_area_ha`, `max_area_ha`) and on Polsby-Popper.

So the grid is *constructed* from the ROI's UTM zone rather than inherited from
whichever input image happens to be first:

  - **Inherited is not stable.** The first SNIC input band is `B4_median` off the
    S2 composite, which `data_load` does not cache; it is a reduced collection,
    so it reports the WGS84 default. A cached asset in the same slot would report
    a real UTM grid. Same config, different grid depending on cache state -- and
    the numbers would move without the config moving.
  - **Inherited is not shared.** The two arms segment different stacks (six
    hand-crafted bands vs a 64-band embedding). Comparing their stand geometry
    only means something if both were measured on the same pixels.

UTM is metric, locally square, and aligned to the 10 m grid Sentinel-2 and the
AlphaEarth embedding are already distributed on, so pinning to it resamples
nothing in practice.
"""

from __future__ import annotations

import ee

from fmu.utils.gee import safe_get_info
from fmu.utils.logging import get_logger

log = get_logger(__name__)


def utm_epsg_code(lon: float, lat: float) -> int:
    """The WGS84 / UTM EPSG code for a lon/lat, north or south as appropriate.

    Zones are 6 degrees wide numbered 1..60 from -180; 326xx north of the
    equator, 327xx south.
    """
    if not -84.0 <= lat <= 84.0:
        raise ValueError(
            f"analysis grid: latitude {lat:.4f} is outside UTM's -84..84 range. "
            f"A polar ROI needs a polar stereographic CRS chosen explicitly; "
            f"this helper will not silently pick a distorted zone for it."
        )
    zone = int((lon + 180.0) // 6.0) + 1
    # lon == 180 lands in a 61st zone that does not exist; it belongs to 60.
    zone = min(max(zone, 1), 60)
    return (32600 if lat >= 0 else 32700) + zone


def analysis_grid(
    roi: ee.Geometry, scale: int, *, context: str = "analysis grid"
) -> ee.Projection:
    """The projected pixel grid for an ROI at `scale` metres.

    One `getInfo` on the ROI's bounding box, which gives both the zone-selecting
    midpoint and the straddle check in a single round trip.
    """
    ring = safe_get_info(
        roi.bounds(maxError=1).coordinates(), context=f"{context} ROI bounds"
    )[0]
    lons = [float(pt[0]) for pt in ring]
    lats = [float(pt[1]) for pt in ring]
    west, east = min(lons), max(lons)
    south, north = min(lats), max(lats)
    mid_lon, mid_lat = (west + east) / 2.0, (south + north) / 2.0

    code = utm_epsg_code(mid_lon, mid_lat)
    # An ROI wider than one zone still gets a single grid -- a run has to measure
    # everything in one CRS to compare anything -- but the edges of it carry more
    # distortion than the middle, and that is worth saying out loud rather than
    # discovering in an area statistic.
    edge_codes = {utm_epsg_code(west, mid_lat), utm_epsg_code(east, mid_lat)}
    if edge_codes != {code}:
        log.warning(
            "  %s: ROI spans UTM zones %s; using EPSG:%d (its midpoint). Areas "
            "near the east/west edge carry more scale distortion than areas near "
            "the middle.",
            context,
            sorted(edge_codes | {code}),
            code,
        )

    return ee.Projection(f"EPSG:{code}").atScale(scale)

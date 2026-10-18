"""Round 9 Task I's tile (run in round 10): a 10 km x 10 km square, north-up in UTM 45N, centred on the centroid of the Angul boxes.

Writes aois/odisha_tile_angul_10km.geojson. Offline (shapely, pyproj). Rule:
  - the Angul boxes: the polygons of aois/odisha_squares_angul.geojson;
  - their centroid: of their union, in EPSG:32645 (UTM 45N, the zone the boxes and the analysis
    grid are in);
  - the tile: the square with corners at centroid +/- 5,000 m in x and y, in EPSG:32645;
  - written in EPSG:4326 lon/lat with each edge densified every 100 m (a GeoJSON edge is read by
    Earth Engine as a geodesic, so the densified ring follows the UTM square to within millimetres).
"""
import json
import sys
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import Polygon, mapping, shape
from shapely.ops import transform, unary_union

REPO = Path(__file__).resolve().parent.parent
src = json.loads((REPO / "aois" / "odisha_squares_angul.geojson").read_text())
geoms = [shape(f["geometry"]) for f in src["features"]]
to_utm = Transformer.from_crs(4326, 32645, always_xy=True).transform
to_ll = Transformer.from_crs(32645, 4326, always_xy=True).transform
boxes = transform(to_utm, unary_union(geoms))
c = boxes.centroid
half = 5000.0
x0, x1, y0, y1 = c.x - half, c.x + half, c.y - half, c.y + half
step = 100.0
ring = []
for (ax, ay), (bx, by) in [((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))]:
    n = int(round(max(abs(bx - ax), abs(by - ay)) / step))
    for i in range(n):
        ring.append((ax + (bx - ax) * i / n, ay + (by - ay) * i / n))
ring.append(ring[0])
tile_utm = Polygon(ring)
tile_ll = transform(to_ll, tile_utm)
out = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {
    "name": "odisha_tile_angul_10km",
    "rule": "10 km x 10 km, north-up in EPSG:32645, centred on the centroid of the union of the Angul boxes "
            "(aois/odisha_squares_angul.geojson); edges densified every 100 m",
    "centre_epsg32645": [round(c.x, 3), round(c.y, 3)],
    "area_ha_epsg32645": round(tile_utm.area / 1e4, 3)}, "geometry": mapping(tile_ll)}]}
dst = REPO / "aois" / "odisha_tile_angul_10km.geojson"
if "--write" in sys.argv:
    dst.write_text(json.dumps(out) + "\n")
lon, lat = to_ll(c.x, c.y)
print(json.dumps({"centre_utm": [c.x, c.y], "centre_lonlat": [lon, lat], "area_ha": tile_utm.area / 1e4,
                  "boxes_area_ha": boxes.area / 1e4, "n_vertices": len(ring), "written": "--write" in sys.argv}, indent=1))

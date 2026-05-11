# AOIs

Polygons defining areas of interest, in GeoJSON format. Each `roi_file` field in a config YAML points to one of these.

## Why GeoJSON

- Plain text, version-controlled by git
- Human-readable in any editor
- Loadable by any GIS tool (QGIS, geopandas, rasterio)
- No GEE asset upload needed for small AOIs

## When to switch to a GEE asset

GeoJSON works as long as the inline geometry stays under ~5 MB (GEE's payload limit). For very complex polygons or multi-polygon national-park-scale AOIs, upload to GEE as a FeatureCollection and use the `roi_asset` field in the config instead (reserved for v0.3+).

## Files

| File | ROI | Source | Status |
|------|-----|--------|--------|
| `sanjay_van.geojson` | Sanjay Van, Delhi | Placeholder bounding box | **Replace with real polygon** |

## Replacing placeholder bounds with a real polygon

If you have a polygon in another format:
- **From a Shapefile:** open in QGIS, export as GeoJSON in EPSG:4326
- **From a KML:** convert with `ogr2ogr -f GeoJSON output.geojson input.kml`
- **Hand-traced:** use https://geojson.io or QGIS to trace from a satellite basemap
- **From an existing GEE asset:** export the FeatureCollection from the GEE Code Editor

All files in this directory must be in **EPSG:4326** (lon/lat, WGS84).

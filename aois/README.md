# AOIs

GeoJSON polygons (EPSG:4326). Each `roi_file` in a config points here.

GEE inline geometries are capped around 5 MB. For very complex polygons,
upload to GEE as a FeatureCollection and use `roi_asset` in the config
instead (not implemented yet).

## Files

| File | ROI | Status |
|------|-----|--------|
| `sanjay_van.geojson` | Sanjay Van, Delhi | **Placeholder bounding box — replace with real polygon** |

To replace the placeholder: trace from a satellite basemap in QGIS or
[geojson.io](https://geojson.io), export as GeoJSON in EPSG:4326. Or
convert from a Shapefile with `ogr2ogr -f GeoJSON out.geojson in.shp`.

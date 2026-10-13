# AOIs

GeoJSON polygons (EPSG:4326). Each `roi_file` in a config points here.

GEE inline geometries are capped around 5 MB. For very complex polygons,
upload to GEE as a FeatureCollection and use `roi_asset` in the config
instead (not implemented yet).

## Files

| File | ROI | Status |
|------|-----|--------|
| `sanjay_van.geojson` | Sanjay Van, Delhi: the 1,300 ha working rectangle (77.16 to 77.19 E, 28.51 to 28.55 N) around the park, not the park boundary | In use by every Sanjay Van config. Every Sanjay Van number is for this rectangle, which takes in the built-up neighbourhoods around the park. It is kept so that earlier results stay comparable; whether to study the park itself, and by whose boundary, is an open question for the supervisor |

To make a new ROI file: trace from a satellite basemap in QGIS or
[geojson.io](https://geojson.io), export as GeoJSON in EPSG:4326. Or
convert from a Shapefile with `ogr2ogr -f GeoJSON out.geojson in.shp`.

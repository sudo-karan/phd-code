# AOIs

GeoJSON polygons (EPSG:4326). Each `roi_file` in a config points here.

GEE inline geometries are capped around 5 MB. For very complex polygons,
upload to GEE as a FeatureCollection and use `roi_asset` in the config
instead (not implemented yet).

## Files

| File | ROI | Status |
|------|-----|--------|
| `sanjay_van.geojson` | Sanjay Van, Delhi: the 1,300 ha working rectangle (77.16 to 77.19 E, 28.51 to 28.55 N) around the park, not the park boundary | In use by every Sanjay Van config. Every Sanjay Van number is for this rectangle, which takes in the built-up neighbourhoods around the park. It is kept so that earlier results stay comparable; whether to study the park itself, and by whose boundary, is an open question for the supervisor |
| `odisha_dhenkanal_sites.geojson` | Odisha, the Phase 2 pilot: the six Dhenkanal village-forest polygons of `Odisha_sites.csv`, each buffered by 200 m and dissolved; 60 field plots inside | Written by `odisha_script/odisha_phase2_0_aois.py`. Used by the three pilot configs (`odisha_v120_handcrafted.yaml`, `odisha_alphaearth.yaml`, `odisha_current_handcrafted.yaml`) |
| `odisha_habitations.geojson` | Odisha, all four districts: per habitation with 5 or more plots, the convex hull of its plots plus 300 m, overlapping hulls dissolved; 267 plots inside | Written by `odisha_phase2_0_aois.py`. No config runs on it: its bounding box is too large for one Earth Engine export, so the pipeline runs per district |
| `odisha_habitations_{angul,dhenkanal,kendujhar,koraput}.geojson` | The same hulls, one file per district; 267 plots over the four | Written by `odisha_phase2_0_aois.py`. Used by the district configs of Phases 2 and 3 (`odisha_v120_handcrafted_<district>`, `odisha_alphaearth_<district>`, `odisha_current_handcrafted_<district>`, `odisha_v120_3ha_<district>`, and the `_repro` copies) |
| `odisha_squares_{angul,dhenkanal,kendujhar,koraput}.geojson` | The boxes: per habitation with 5 or more plots, the north-up box around its plots widened by 300 m, boxes that meet merged; one file per district, holding every plot its hulls hold | Written by `odisha_script/odisha_squares_0_aois.py`. Used by the box and kept-land configs (`odisha_v120_3ha_squares_<district>*`, `odisha_v120_10ha_squares_<district>_keptland_s1desc_r9`, `odisha_alphaearth_{3,10}ha_squares_<district>_keptland_r9`) |
| `odisha_tile_angul_10km.geojson` | A 10 km by 10 km square, north-up in UTM zone 45N, centred on the Angul boxes | Written by `odisha_script/odisha_tile_0_aoi.py`. Used by `odisha_v120_3ha_tile10km_angul_keptland_s1desc_r9.yaml` |

The Odisha rows were added on 20 Oct 2026 (review C24); the table listed only `sanjay_van.geojson`.

To make a new ROI file: trace from a satellite basemap in QGIS or
[geojson.io](https://geojson.io), export as GeoJSON in EPSG:4326. Or
convert from a Shapefile with `ogr2ogr -f GeoJSON out.geojson in.shp`.

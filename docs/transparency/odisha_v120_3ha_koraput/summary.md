# Koraput district, Odisha: land-cover (habitat) mask of the mapped village forests

The ROI is 2,458.7 ha. The land-cover mask keeps 62.1% of it as habitat and removes the rest: cropland 36.6%, built-up 0.7%, other non-habitat 0.5%. Of the 146 field plots given, 145 are inside the ROI: 137 on a kept pixel and 8 on a removed pixel. 1 lies outside the ROI and is not on the map.

This is a habitat mask, not a strict forest mask. By default it keeps IndiaSAT Trees and Shrubs/Scrub, and WorldCover tree cover, shrubland and grassland where IndiaSAT has no data; the classes a run kept are listed in its masking summary (kept_classes). The definition and the reasoning behind it are in docs/design_notes.md, section "Masking: IndiaSAT-primary, single-phase habitat".

- This map stands for the three pipeline variants run on this district (the three arms: 3 ha, handcrafted, AlphaEarth). Everything the masking stage reads is identical in `odisha_v120_handcrafted_koraput`, `odisha_alphaearth_koraput` and this config (`odisha_v120_3ha_koraput`): the roi block, the masking block, and the datasets entries indiasat, worldcover, water. So all three use the same mask rule on the same ROI. The cached mask of `odisha_v120_handcrafted_koraput` and of `odisha_alphaearth_koraput` is compared with this one, pixel by pixel, below. The datasets block as a whole is not identical; what differs is not read by masking: `datasets.embedding` in `odisha_alphaearth_koraput` ('GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL' against None).
- The field plots are the 146 of the district (`odisha_script/odisha_plots_clean.csv`, coordinates from `plot_key`). Each part of the ROI is the forest around one or two habitations, named after them.
- 1 of the district's 146 field plots lies outside the mapped village forests (the ROI) and is on no map. The Phase 2 step 1 retention table, which samples the same mask rule at every plot, has 138 of 146 plots of this district on a habitat pixel (257 of 274 over the four districts). That count includes the 1 outside the ROI: 1 kept and 0 dropped there. The map and the tables below cover only the 145 inside. Table: `odisha_script/odisha_phase2_1_mask_retention.csv`.

Maps: `habitat_mask_sheet1of2.png`, `habitat_mask_sheet2of2.png`.

## Whole ROI

| Quantity | Value |
| --- | --- |
| Area of the ROI | 2,458.7 ha |
| Kept as habitat (not only forest) | 62.1% |
| Removed: cropland | 36.6% |
| Removed: built-up | 0.7% |
| Removed: water | 0.0% |
| Removed: other non-habitat | 0.5% |
| No land-cover data in either map (not habitat) | 0.0% |

Which map decided. IndiaSAT decided: 100.0% of the area. So every kept pixel was kept on that map's word.

Check against the cached mask: 0.0 ha. That is the area where the reason layer, computed in this run from today's land-cover data, says kept and the cached `habitat_mask` does not, or the reverse. Above zero would mean a land-cover input has changed since the mask was cached, so the stands were built on a mask today's data would not reproduce exactly.

Classes this run kept as habitat: indiasat [6, 12]; worldcover [10, 20, 30].

Other cached masks compared with the `habitat_mask` above, pixel by pixel:

- `odisha_v120_handcrafted_koraput/masking/habitat_mask__4bdfadbe7c` differs over 0.00 ha of 2,458.7 ha (0.0%).
- `odisha_alphaearth_koraput/masking/habitat_mask__f1a8cc9cfa` differs over 0.00 ha of 2,458.7 ha (0.0%).

## By part

Tabulated from the saved rasters, counting the pixels whose centre is inside the part. The whole-ROI table above comes from Earth Engine, which weights edge pixels by how much of them the ROI covers, so the two can differ by a fraction of a percent.

| Part | Area | Kept | cropland | built-up | water | other non-habitat |
| --- | --- | --- | --- | --- | --- | --- |
| HANDAPUR | 98.9 ha | 58.1% | 40.9% | 0.1% | 0.0% | 0.9% |
| BILAPUT + HATIMUNDA | 422.8 ha | 65.4% | 34.3% | 0.0% | 0.0% | 0.3% |
| BARIGUDA | 70.6 ha | 77.4% | 22.4% | 0.0% | 0.0% | 0.3% |
| KONDASRIMUNDA | 37.9 ha | 60.3% | 39.5% | 0.0% | 0.0% | 0.2% |
| KHASUGUDA | 466.8 ha | 58.0% | 41.6% | 0.0% | 0.0% | 0.4% |
| SAKIAGUDA | 45.2 ha | 72.7% | 26.3% | 0.0% | 0.7% | 0.3% |
| BARAKANTI | 1,316.5 ha | 61.7% | 36.2% | 1.4% | 0.0% | 0.7% |

Columns after Kept are shares of the part's area removed for each reason. No part has a pixel without land-cover data. One map decided every pixel of every part (see above).

## Field plots

146 field plots given, 145 inside the ROI: 137 kept, 8 dropped. 1 outside the ROI. A field plot is kept or dropped by the single 10 m pixel it falls on, so a dropped field plot can sit in a patch that is otherwise kept.

| Part | Field plots | Kept | Dropped |
| --- | --- | --- | --- |
| HANDAPUR | 20 | 19 | 1 |
| BILAPUT + HATIMUNDA | 59 | 55 | 4 |
| BARIGUDA | 10 | 10 | 0 |
| KONDASRIMUNDA | 5 | 5 | 0 |
| KHASUGUDA | 11 | 10 | 1 |
| SAKIAGUDA | 9 | 9 | 0 |
| BARAKANTI | 31 | 29 | 2 |

Dropped field plots:

| Field plot | Part | Reason | Decided by | Kept pixels in the 5 x 5 around it |
| --- | --- | --- | --- | --- |
| `18.575806_82.837232` | HANDAPUR | Removed: cropland | IndiaSAT decided | 5 of 25 |
| `18.590809_82.826211` | BILAPUT + HATIMUNDA | Removed: cropland | IndiaSAT decided | 11 of 25 |
| `18.590818_82.825501` | BILAPUT + HATIMUNDA | Removed: cropland | IndiaSAT decided | 8 of 25 |
| `18.596368_82.824083` | BILAPUT + HATIMUNDA | Removed: cropland | IndiaSAT decided | 4 of 25 |
| `18.596726_82.822897` | BILAPUT + HATIMUNDA | Removed: cropland | IndiaSAT decided | 0 of 25 |
| `18.624624_82.933586` | KHASUGUDA | Removed: cropland | IndiaSAT decided | 0 of 25 |
| `18.686431_82.9618` | BARAKANTI | Removed: cropland | IndiaSAT decided | 16 of 25 |
| `18.69107_82.868956` | BARAKANTI | Removed: built-up | IndiaSAT decided | 0 of 25 |

Outside the ROI, so not on the map and not counted above: `18.55814_82.928984`.

## How the maps are drawn

True colour is Sentinel-2 red, green and blue (B4_median, B3_median, B2_median) of `s2_composite`, the image the pipeline segments on (read from the cached asset). All three bands share one linear stretch, from 240 to 1361 (percentiles 1 and 99 of the pixels inside the ROI), then gamma 0.75. Colours and labels of the mask are the masking stage's own display-layer declaration. North is up. White is outside the ROI.

## For the record

- Config: `configs/odisha_v120_3ha_koraput.yaml` (name `odisha_v120_3ha_koraput`, cache fingerprint `030aafaa2c`)
- ROI file: `aois/odisha_habitations_koraput.geojson`, 7 parts
- `habitat_mask`, the mask the rest of the pipeline uses: read from the cached asset
- `mask_provenance`, the reason and deciding-map layer: computed live
- The code, the cached asset ids, the date and the command line are in `run_record.json` beside this file.

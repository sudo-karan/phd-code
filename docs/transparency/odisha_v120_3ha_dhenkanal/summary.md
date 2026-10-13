# Dhenkanal district, Odisha: land-cover (habitat) mask of the mapped village forests

The ROI is 995.6 ha. The land-cover mask keeps 79.4% of it as habitat and removes the rest: cropland 19.2%, water 0.7%, built-up 0.5%, other non-habitat 0.2%. Of the 76 field plots given, 75 are inside the ROI: 72 on a kept pixel and 3 on a removed pixel. 1 lies outside the ROI and is not on the map.

This is a habitat mask, not a strict forest mask. By default it keeps IndiaSAT Trees and Shrubs/Scrub, and WorldCover tree cover, shrubland and grassland where IndiaSAT has no data; the classes a run kept are listed in its masking summary (kept_classes). The definition and the reasoning behind it are in docs/design_notes.md, section "Masking: IndiaSAT-primary, single-phase habitat".

- This map stands for the three pipeline variants run on this district (the three arms: 3 ha, handcrafted, AlphaEarth). Everything the masking stage reads is identical in `odisha_v120_handcrafted_dhenkanal`, `odisha_alphaearth_dhenkanal` and this config (`odisha_v120_3ha_dhenkanal`): the roi block, the masking block, and the datasets entries indiasat, worldcover, water. So all three use the same mask rule on the same ROI. The cached mask of `odisha_v120_handcrafted_dhenkanal` and of `odisha_alphaearth_dhenkanal` is compared with this one, pixel by pixel, below. The datasets block as a whole is not identical; what differs is not read by masking: `datasets.embedding` in `odisha_alphaearth_dhenkanal` ('GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL' against None).
- The field plots are the 76 of the district (`odisha_script/odisha_plots_clean.csv`, coordinates from `plot_key`). Each part of the ROI is the forest around one or two habitations, named after them.
- 1 of the district's 76 field plots lies outside the mapped village forests (the ROI) and is on no map. The Phase 2 step 1 retention table, which samples the same mask rule at every plot, has 73 of 76 plots of this district on a habitat pixel (257 of 274 over the four districts). That count includes the 1 outside the ROI: 1 kept and 0 dropped there. The map and the tables below cover only the 75 inside. Table: `odisha_script/odisha_phase2_1_mask_retention.csv`.

Maps: `habitat_mask_sheet1of2.png`, `habitat_mask_sheet2of2.png`.

## Whole ROI

| Quantity | Value |
| --- | --- |
| Area of the ROI | 995.6 ha |
| Kept as habitat (not only forest) | 79.4% |
| Removed: cropland | 19.2% |
| Removed: built-up | 0.5% |
| Removed: water | 0.7% |
| Removed: other non-habitat | 0.2% |
| No land-cover data in either map (not habitat) | 0.0% |

Which map decided. IndiaSAT decided: 100.0% of the area. So every kept pixel was kept on that map's word.

Check against the cached mask: 0.0 ha. That is the area where the reason layer, computed in this run from today's land-cover data, says kept and the cached `habitat_mask` does not, or the reverse. Above zero would mean a land-cover input has changed since the mask was cached, so the stands were built on a mask today's data would not reproduce exactly.

Classes this run kept as habitat: indiasat [6, 12]; worldcover [10, 20, 30].

Other cached masks compared with the `habitat_mask` above, pixel by pixel:

- `odisha_v120_handcrafted_dhenkanal/masking/habitat_mask__57b7c569b3` differs over 0.00 ha of 995.6 ha (0.0%).
- `odisha_alphaearth_dhenkanal/masking/habitat_mask__6e7046a5ce` differs over 0.00 ha of 995.6 ha (0.0%).

## By part

Tabulated from the saved rasters, counting the pixels whose centre is inside the part. The whole-ROI table above comes from Earth Engine, which weights edge pixels by how much of them the ROI covers, so the two can differ by a fraction of a percent.

| Part | Area | Kept | cropland | built-up | water | other non-habitat |
| --- | --- | --- | --- | --- | --- | --- |
| TULASIPASI | 247.0 ha | 73.0% | 23.1% | 1.2% | 2.6% | 0.1% |
| KANKANA | 68.0 ha | 46.9% | 50.7% | 2.2% | 0.0% | 0.2% |
| BALIKUMA | 144.9 ha | 91.5% | 8.2% | 0.2% | 0.0% | 0.0% |
| NUA SAHI | 189.0 ha | 92.3% | 7.5% | 0.0% | 0.0% | 0.2% |
| ADHAPALLI | 105.6 ha | 86.7% | 13.0% | 0.1% | 0.0% | 0.2% |
| BURUGI BHUIN | 73.8 ha | 87.2% | 12.7% | 0.0% | 0.0% | 0.0% |
| BALI SAHI | 63.9 ha | 65.6% | 33.5% | 0.9% | 0.0% | 0.0% |
| RAIJHARANA | 103.4 ha | 71.7% | 27.9% | 0.0% | 0.0% | 0.4% |

Columns after Kept are shares of the part's area removed for each reason. No part has a pixel without land-cover data. One map decided every pixel of every part (see above).

## Field plots

76 field plots given, 75 inside the ROI: 72 kept, 3 dropped. 1 outside the ROI. A field plot is kept or dropped by the single 10 m pixel it falls on, so a dropped field plot can sit in a patch that is otherwise kept.

| Part | Field plots | Kept | Dropped |
| --- | --- | --- | --- |
| TULASIPASI | 7 | 6 | 1 |
| KANKANA | 8 | 6 | 2 |
| BALIKUMA | 11 | 11 | 0 |
| NUA SAHI | 9 | 9 | 0 |
| ADHAPALLI | 11 | 11 | 0 |
| BURUGI BHUIN | 9 | 9 | 0 |
| BALI SAHI | 10 | 10 | 0 |
| RAIJHARANA | 10 | 10 | 0 |

Dropped field plots:

| Field plot | Part | Reason | Decided by | Kept pixels in the 5 x 5 around it |
| --- | --- | --- | --- | --- |
| `20.926894_85.66691` | TULASIPASI | Removed: cropland | IndiaSAT decided | 23 of 25 |
| `20.968462_85.697621` | KANKANA | Removed: cropland | IndiaSAT decided | 16 of 25 |
| `20.969023_85.695805` | KANKANA | Removed: cropland | IndiaSAT decided | 0 of 25 |

Outside the ROI, so not on the map and not counted above: `20.621695_85.564537`.

## How the maps are drawn

True colour is Sentinel-2 red, green and blue (B4_median, B3_median, B2_median) of `s2_composite`, the image the pipeline segments on (read from the cached asset). All three bands share one linear stretch, from 347 to 1258 (percentiles 1 and 99 of the pixels inside the ROI), then gamma 0.75. Colours and labels of the mask are the masking stage's own display-layer declaration. North is up. White is outside the ROI.

## For the record

- Config: `configs/odisha_v120_3ha_dhenkanal.yaml` (name `odisha_v120_3ha_dhenkanal`, cache fingerprint `a516a24b2d`)
- ROI file: `aois/odisha_habitations_dhenkanal.geojson`, 8 parts
- `habitat_mask`, the mask the rest of the pipeline uses: read from the cached asset
- `mask_provenance`, the reason and deciding-map layer: computed live
- The code, the cached asset ids, the date and the command line are in `run_record.json` beside this file.

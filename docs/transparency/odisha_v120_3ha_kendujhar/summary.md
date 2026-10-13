# Kendujhar district, Odisha: land-cover (habitat) mask of the mapped village forests

The ROI is 404.7 ha. The land-cover mask keeps 58.7% of it as habitat and removes the rest: cropland 40.4%, built-up 0.7%, other non-habitat 0.1%. Of the 12 field plots given, 8 are inside the ROI: 7 on a kept pixel and 1 on a removed pixel. 4 lie outside the ROI and are not on the map.

This is a habitat mask, not a strict forest mask. By default it keeps IndiaSAT Trees and Shrubs/Scrub, and WorldCover tree cover, shrubland and grassland where IndiaSAT has no data; the classes a run kept are listed in its masking summary (kept_classes). The definition and the reasoning behind it are in docs/design_notes.md, section "Masking: IndiaSAT-primary, single-phase habitat".

- This map stands for the three pipeline variants run on this district (the three arms: 3 ha, handcrafted, AlphaEarth). Everything the masking stage reads is identical in `odisha_v120_handcrafted_kendujhar`, `odisha_alphaearth_kendujhar` and this config (`odisha_v120_3ha_kendujhar`): the roi block, the masking block, and the datasets entries indiasat, worldcover, water. So all three use the same mask rule on the same ROI. The cached mask of `odisha_v120_handcrafted_kendujhar` and of `odisha_alphaearth_kendujhar` is compared with this one, pixel by pixel, below. The datasets block as a whole is not identical; what differs is not read by masking: `datasets.embedding` in `odisha_alphaearth_kendujhar` ('GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL' against None).
- The field plots are the 12 of the district (`odisha_script/odisha_plots_clean.csv`, coordinates from `plot_key`). Each part of the ROI is the forest around one or two habitations, named after them.
- 4 of the district's 12 field plots lie outside the mapped village forests (the ROI) and are on no map. The Phase 2 step 1 retention table, which samples the same mask rule at every plot, has 8 of 12 plots of this district on a habitat pixel (257 of 274 over the four districts). That count includes the 4 outside the ROI: 1 kept and 3 dropped there. The map and the tables below cover only the 8 inside. Table: `odisha_script/odisha_phase2_1_mask_retention.csv`.

Maps: `habitat_mask.png`.

## Whole ROI

| Quantity | Value |
| --- | --- |
| Area of the ROI | 404.7 ha |
| Kept as habitat (not only forest) | 58.7% |
| Removed: cropland | 40.4% |
| Removed: built-up | 0.7% |
| Removed: water | 0.0% |
| Removed: other non-habitat | 0.1% |
| No land-cover data in either map (not habitat) | 0.0% |

Which map decided. IndiaSAT decided: 100.0% of the area. So every kept pixel was kept on that map's word.

Check against the cached mask: 0.0 ha. That is the area where the reason layer, computed in this run from today's land-cover data, says kept and the cached `habitat_mask` does not, or the reverse. Above zero would mean a land-cover input has changed since the mask was cached, so the stands were built on a mask today's data would not reproduce exactly.

Classes this run kept as habitat: indiasat [6, 12]; worldcover [10, 20, 30].

Other cached masks compared with the `habitat_mask` above, pixel by pixel:

- `odisha_v120_handcrafted_kendujhar/masking/habitat_mask__5bf920bc83` differs over 0.00 ha of 404.7 ha (0.0%).
- `odisha_alphaearth_kendujhar/masking/habitat_mask__4c14ee1bce` differs over 0.00 ha of 404.7 ha (0.0%).

## Field plots

12 field plots given, 8 inside the ROI: 7 kept, 1 dropped. 4 outside the ROI. A field plot is kept or dropped by the single 10 m pixel it falls on, so a dropped field plot can sit in a patch that is otherwise kept.

Dropped field plots:

| Field plot | Part | Reason | Decided by | Kept pixels in the 5 x 5 around it |
| --- | --- | --- | --- | --- |
| `21.614841_85.407242` | BHANRADI SAHI | Removed: built-up | IndiaSAT decided | 0 of 25 |

Outside the ROI, so not on the map and not counted above: `21.6178_85.381345`, `21.618997_85.379154`, `21.621938_85.383944`, `21.62195_85.383933`.

## How the maps are drawn

True colour is Sentinel-2 red, green and blue (B4_median, B3_median, B2_median) of `s2_composite`, the image the pipeline segments on (read from the cached asset). All three bands share one linear stretch, from 250 to 1358 (percentiles 1 and 99 of the pixels inside the ROI), then gamma 0.75. Colours and labels of the mask are the masking stage's own display-layer declaration. North is up. White is outside the ROI.

## For the record

- Config: `configs/odisha_v120_3ha_kendujhar.yaml` (name `odisha_v120_3ha_kendujhar`, cache fingerprint `9908a3bb6b`)
- ROI file: `aois/odisha_habitations_kendujhar.geojson`, 1 part
- `habitat_mask`, the mask the rest of the pipeline uses: read from the cached asset
- `mask_provenance`, the reason and deciding-map layer: computed live
- The code, the cached asset ids, the date and the command line are in `run_record.json` beside this file.

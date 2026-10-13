# Angul district, Odisha: land-cover (habitat) mask of the mapped village forests

The ROI is 439.0 ha. The land-cover mask keeps 67.1% of it as habitat and removes the rest: cropland 32.3%, built-up 0.4%, other non-habitat 0.2%, water 0.1%. Of the 40 field plots given, 39 are inside the ROI: 37 on a kept pixel and 2 on a removed pixel. 1 lies outside the ROI and is not on the map.

This is a habitat mask, not a strict forest mask. By default it keeps IndiaSAT Trees and Shrubs/Scrub, and WorldCover tree cover, shrubland and grassland where IndiaSAT has no data; the classes a run kept are listed in its masking summary (kept_classes). The definition and the reasoning behind it are in docs/design_notes.md, section "Masking: IndiaSAT-primary, single-phase habitat".

- This map stands for the three pipeline variants run on this district (the three arms: 3 ha, handcrafted, AlphaEarth). Everything the masking stage reads is identical in `odisha_v120_handcrafted_angul`, `odisha_alphaearth_angul` and this config (`odisha_v120_3ha_angul`): the roi block, the masking block, and the datasets entries indiasat, worldcover, water. So all three use the same mask rule on the same ROI. The cached mask of `odisha_v120_handcrafted_angul` and of `odisha_alphaearth_angul` is compared with this one, pixel by pixel, below. The datasets block as a whole is not identical; what differs is not read by masking: `datasets.embedding` in `odisha_alphaearth_angul` ('GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL' against None).
- The field plots are the 40 of the district (`odisha_script/odisha_plots_clean.csv`, coordinates from `plot_key`). Each part of the ROI is the forest around one or two habitations, named after them.
- 1 of the district's 40 field plots lies outside the mapped village forests (the ROI) and is on no map. The Phase 2 step 1 retention table, which samples the same mask rule at every plot, has 38 of 40 plots of this district on a habitat pixel (257 of 274 over the four districts). That count includes the 1 outside the ROI: 1 kept and 0 dropped there. The map and the tables below cover only the 39 inside. Table: `odisha_script/odisha_phase2_1_mask_retention.csv`.

Maps: `habitat_mask.png`.

## Whole ROI

| Quantity | Value |
| --- | --- |
| Area of the ROI | 439.0 ha |
| Kept as habitat (not only forest) | 67.1% |
| Removed: cropland | 32.3% |
| Removed: built-up | 0.4% |
| Removed: water | 0.1% |
| Removed: other non-habitat | 0.2% |
| No land-cover data in either map (not habitat) | 0.0% |

Which map decided. IndiaSAT decided: 100.0% of the area. So every kept pixel was kept on that map's word.

Check against the cached mask: 0.0 ha. That is the area where the reason layer, computed in this run from today's land-cover data, says kept and the cached `habitat_mask` does not, or the reverse. Above zero would mean a land-cover input has changed since the mask was cached, so the stands were built on a mask today's data would not reproduce exactly.

Classes this run kept as habitat: indiasat [6, 12]; worldcover [10, 20, 30].

Other cached masks compared with the `habitat_mask` above, pixel by pixel:

- `odisha_v120_handcrafted_angul/masking/habitat_mask__d6096dce2e` differs over 0.00 ha of 439.0 ha (0.0%).
- `odisha_alphaearth_angul/masking/habitat_mask__34bffb7611` differs over 0.00 ha of 439.0 ha (0.0%).

## By part

Tabulated from the saved rasters, counting the pixels whose centre is inside the part. The whole-ROI table above comes from Earth Engine, which weights edge pixels by how much of them the ROI covers, so the two can differ by a fraction of a percent.

| Part | Area | Kept | cropland | built-up | water | other non-habitat |
| --- | --- | --- | --- | --- | --- | --- |
| KANSAB | 97.9 ha | 87.4% | 12.0% | 0.6% | 0.0% | 0.0% |
| GHANAJODI | 206.1 ha | 73.3% | 26.2% | 0.5% | 0.1% | 0.0% |
| JOGI BANDHA | 65.2 ha | 50.6% | 48.4% | 0.2% | 0.0% | 0.9% |
| ANANDA PUR | 69.7 ha | 35.8% | 63.5% | 0.3% | 0.2% | 0.1% |

Columns after Kept are shares of the part's area removed for each reason. No part has a pixel without land-cover data. One map decided every pixel of every part (see above).

## Field plots

40 field plots given, 39 inside the ROI: 37 kept, 2 dropped. 1 outside the ROI. A field plot is kept or dropped by the single 10 m pixel it falls on, so a dropped field plot can sit in a patch that is otherwise kept.

| Part | Field plots | Kept | Dropped |
| --- | --- | --- | --- |
| KANSAB | 10 | 10 | 0 |
| GHANAJODI | 10 | 9 | 1 |
| JOGI BANDHA | 10 | 10 | 0 |
| ANANDA PUR | 9 | 8 | 1 |

Dropped field plots:

| Field plot | Part | Reason | Decided by | Kept pixels in the 5 x 5 around it |
| --- | --- | --- | --- | --- |
| `20.76408_84.715482` | GHANAJODI | Removed: cropland | IndiaSAT decided | 11 of 25 |
| `20.828198_84.64423` | ANANDA PUR | Removed: cropland | IndiaSAT decided | 12 of 25 |

Outside the ROI, so not on the map and not counted above: `20.767532_84.743722`.

## How the maps are drawn

True colour is Sentinel-2 red, green and blue (B4_median, B3_median, B2_median) of `s2_composite`, the image the pipeline segments on (read from the cached asset). All three bands share one linear stretch, from 316 to 1220 (percentiles 1 and 99 of the pixels inside the ROI), then gamma 0.75. Colours and labels of the mask are the masking stage's own display-layer declaration. North is up. White is outside the ROI.

## For the record

- Config: `configs/odisha_v120_3ha_angul.yaml` (name `odisha_v120_3ha_angul`, cache fingerprint `8c472d39f9`)
- ROI file: `aois/odisha_habitations_angul.geojson`, 4 parts
- `habitat_mask`, the mask the rest of the pipeline uses: read from the cached asset
- `mask_provenance`, the reason and deciding-map layer: computed live
- The code, the cached asset ids, the date and the command line are in `run_record.json` beside this file.

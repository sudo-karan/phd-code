# Habitat mask: odisha_v120_3ha_angul_repro

The ROI is 439.0 ha. The land-cover mask keeps 67.1% of it as habitat and removes the rest: cropland 32.3%, built-up 0.4%, other non-habitat 0.2%, water 0.1%.

This is a habitat mask, not a strict forest mask. By default it keeps IndiaSAT Trees and Shrubs/Scrub, and WorldCover tree cover, shrubland and grassland where IndiaSAT has no data; the classes a run kept are listed in its masking summary (kept_classes). The definition and the reasoning behind it are in docs/design_notes.md, section "Masking: IndiaSAT-primary, single-phase habitat".

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

## By part

Tabulated from the saved rasters, counting the pixels whose centre is inside the part. The whole-ROI table above comes from Earth Engine, which weights edge pixels by how much of them the ROI covers, so the two can differ by a fraction of a percent.

| Part | Area | Kept | cropland | built-up | water | other non-habitat |
| --- | --- | --- | --- | --- | --- | --- |
| part 1 | 97.9 ha | 87.4% | 12.0% | 0.6% | 0.0% | 0.0% |
| part 2 | 206.1 ha | 73.3% | 26.2% | 0.5% | 0.1% | 0.0% |
| part 3 | 65.2 ha | 50.6% | 48.4% | 0.2% | 0.0% | 0.9% |
| part 4 | 69.7 ha | 35.8% | 63.5% | 0.3% | 0.2% | 0.1% |

Columns after Kept are shares of the part's area removed for each reason. No part has a pixel without land-cover data. One map decided every pixel of every part (see above).

## How the maps are drawn

True colour is Sentinel-2 red, green and blue (B4_median, B3_median, B2_median) of `s2_composite`, the image the pipeline segments on (read from the cached asset). All three bands share one linear stretch, from 316 to 1222 (percentiles 1 and 99 of the pixels inside the ROI), then gamma 0.75. Colours and labels of the mask are the masking stage's own display-layer declaration. North is up. White is outside the ROI.

## For the record

- Config: `configs/odisha_v120_3ha_angul_repro.yaml` (name `odisha_v120_3ha_angul_repro`, cache fingerprint `8c472d39f9`)
- ROI file: `aois/odisha_habitations_angul.geojson`, 4 parts
- `habitat_mask`, the mask the rest of the pipeline uses: read from the cached asset
- `mask_provenance`, the reason and deciding-map layer: computed live
- The code, the cached asset ids, the date and the command line are in `run_record.json` beside this file.

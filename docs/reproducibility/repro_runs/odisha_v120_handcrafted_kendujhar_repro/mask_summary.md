# Habitat mask: odisha_v120_handcrafted_kendujhar_repro

The ROI is 404.7 ha. The land-cover mask keeps 58.7% of it as habitat and removes the rest: cropland 40.4%, built-up 0.7%, other non-habitat 0.1%.

This is a habitat mask, not a strict forest mask. By default it keeps IndiaSAT Trees and Shrubs/Scrub, and WorldCover tree cover, shrubland and grassland where IndiaSAT has no data; the classes a run kept are listed in its masking summary (kept_classes). The definition and the reasoning behind it are in docs/design_notes.md, section "Masking: IndiaSAT-primary, single-phase habitat".

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

## How the maps are drawn

True colour is Sentinel-2 red, green and blue (B4_median, B3_median, B2_median) of `s2_composite`, the image the pipeline segments on (read from the cached asset). All three bands share one linear stretch, from 250 to 1360 (percentiles 1 and 99 of the pixels inside the ROI), then gamma 0.75. Colours and labels of the mask are the masking stage's own display-layer declaration. North is up. White is outside the ROI.

## For the record

- Config: `configs/odisha_v120_handcrafted_kendujhar_repro.yaml` (name `odisha_v120_handcrafted_kendujhar_repro`, cache fingerprint `5bf920bc83`)
- ROI file: `aois/odisha_habitations_kendujhar.geojson`, 1 part
- `habitat_mask`, the mask the rest of the pipeline uses: read from the cached asset
- `mask_provenance`, the reason and deciding-map layer: computed live
- The code, the cached asset ids, the date and the command line are in `mask_run_record.json` beside this file.

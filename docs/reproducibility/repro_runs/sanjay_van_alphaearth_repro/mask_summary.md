# Habitat mask: sanjay_van_alphaearth_repro

The ROI is 1,301.6 ha. The land-cover mask keeps 65.1% of it as habitat and removes the rest: built-up 34.2%, cropland 0.4%, water 0.2%, other non-habitat 0.1%.

This is a habitat mask, not a strict forest mask. By default it keeps IndiaSAT Trees and Shrubs/Scrub, and WorldCover tree cover, shrubland and grassland where IndiaSAT has no data; the classes a run kept are listed in its masking summary (kept_classes). The definition and the reasoning behind it are in docs/design_notes.md, section "Masking: IndiaSAT-primary, single-phase habitat".

- The ROI file (`aois/sanjay_van.geojson`) says of itself: "Bbox of the working area used in Notebooks 7-13. Replace with hand-traced polygon if a tighter park boundary is needed."

Maps: `habitat_mask.png`.

## Whole ROI

| Quantity | Value |
| --- | --- |
| Area of the ROI | 1,301.6 ha |
| Kept as habitat (not only forest) | 65.1% |
| Removed: cropland | 0.4% |
| Removed: built-up | 34.2% |
| Removed: water | 0.2% |
| Removed: other non-habitat | 0.1% |
| No land-cover data in either map (not habitat) | 0.0% |

Which map decided. IndiaSAT decided: 100.0% of the area. So every kept pixel was kept on that map's word.

Check against the cached mask: 0.0 ha. That is the area where the reason layer, computed in this run from today's land-cover data, says kept and the cached `habitat_mask` does not, or the reverse. Above zero would mean a land-cover input has changed since the mask was cached, so the stands were built on a mask today's data would not reproduce exactly.

Classes this run kept as habitat: indiasat [6, 12]; worldcover [10, 20, 30].

## How the maps are drawn

True colour is Sentinel-2 red, green and blue (B4_median, B3_median, B2_median) of `s2_composite`, the image the pipeline segments on (read from the cached asset). All three bands share one linear stretch, from 324 to 1924 (percentiles 1 and 99 of the pixels inside the ROI), then gamma 0.75. Colours and labels of the mask are the masking stage's own display-layer declaration. North is up. White is outside the ROI.

## For the record

- Config: `configs/sanjay_van_alphaearth_repro.yaml` (name `sanjay_van_alphaearth_repro`, cache fingerprint `105fc40547`)
- ROI file: `aois/sanjay_van.geojson`, 1 part
- `habitat_mask`, the mask the rest of the pipeline uses: read from the cached asset
- `mask_provenance`, the reason and deciding-map layer: computed live
- The code, the cached asset ids, the date and the command line are in `run_record.json` beside this file.

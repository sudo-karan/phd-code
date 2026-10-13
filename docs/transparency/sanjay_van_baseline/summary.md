# Sanjay Van, Delhi: land-cover (habitat) mask of the rectangle the pipeline runs on

The ROI is 1,301.6 ha. The land-cover mask keeps 65.1% of it as habitat and removes the rest: built-up 34.2%, cropland 0.4%, water 0.2%, other non-habitat 0.1%.

This is a habitat mask, not a strict forest mask. By default it keeps IndiaSAT Trees and Shrubs/Scrub, and WorldCover tree cover, shrubland and grassland where IndiaSAT has no data; the classes a run kept are listed in its masking summary (kept_classes). The definition and the reasoning behind it are in docs/design_notes.md, section "Masking: IndiaSAT-primary, single-phase habitat".

- The ROI is the rectangle the pipeline runs on (77.16 to 77.19 E, 28.51 to 28.55 N), not the park boundary. It takes in the built-up neighbourhoods around the park, so every share here is a share of that rectangle, not of Sanjay Van.
- Nothing is cached under this config's current fingerprint, so the mask here is computed live. The cached assets carry fingerprint bbc3e3d624, from before canopy_height_std was dropped from the config on 10 September; the masking rule did not change then, and that older cached mask is compared with the live one below.
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

The reason layer and `habitat_mask` disagree over 0.0 ha. Both were computed in this run, so this is zero by construction; it is a check only when the mask is read from the cache.

Classes this run kept as habitat: indiasat [6, 12]; worldcover [10, 20, 30].

Other cached masks compared with the `habitat_mask` above, pixel by pixel:

- `sanjay_van_baseline/masking/habitat_mask__bbc3e3d624` differs over 0.00 ha of 1,301.6 ha (0.0%).

## How the maps are drawn

True colour is Sentinel-2 red, green and blue (B4_median, B3_median, B2_median) of `s2_composite`, the image the pipeline segments on (computed live). All three bands share one linear stretch, from 324 to 1924 (percentiles 1 and 99 of the pixels inside the ROI), then gamma 0.75. Colours and labels of the mask are the masking stage's own display-layer declaration. North is up. White is outside the ROI.

## For the record

- Config: `configs/sanjay_van_baseline.yaml` (name `sanjay_van_baseline`, cache fingerprint `7f642cf2ca`)
- ROI file: `aois/sanjay_van.geojson`, 1 part
- `habitat_mask`, the mask the rest of the pipeline uses: computed live
- `mask_provenance`, the reason and deciding-map layer: computed live
- The code, the cached asset ids, the date and the command line are in `run_record.json` beside this file.

# Phase 1, Test 5 on the descending orbit: declared before sampling

**Declared 17 Oct 2026 (round 9, task E), before any descending-orbit value was sampled at the
plots.** Results: `odisha_phase1_12_radar_descending_results.txt`, written by
`odisha_phase1_12_radar_descending.py`.

## Why

Phase 1's radar check (Test 5, `odisha_phase1_4_analyse_v2.py`, results in
`odisha_phase1_tests456_results.txt`) sampled Sentinel-1 on the **ascending** orbit only. In its
sample (`odisha_plots_sampled_v2.csv`) all 146 Koraput plots have `vv_iqr` and `vh_iqr` exactly
0, and no plot of the other three districts has: Koraput's plots see one ascending image, so
their three percentiles coincide. Its best band, `vh_iqr` (R² = 0.210 against Lorey's height),
therefore rests on a contrast between a district with no spread and three with some. The round 7
runs moved to the descending orbit, which has 188 to 204 images over every district
(`spec-odisha-keptland-s1-orbit-descending`). This repeats Test 5 there.

## What is sampled

Exactly Phase 1 step 3's recipe (`odisha_phase1_3_sample_gee_v2.py`, Test 5), with one change,
the orbit:

- the 274 plots of `odisha_plots_sampled.csv` (Phase 1's input), as points at its `lon`, `lat`;
- `COPERNICUS/S1_GRD` over the plots' bounding box widened by 1,000 m, 2017-01-01 to 2023-01-01
  (end exclusive), instrument mode IW, **orbit DESCENDING** (Phase 1: ASCENDING), VV and VH both
  present, bands VV and VH;
- per pixel, the 10th, 50th and 90th percentiles of each: `vv_p10`, `vv_p50`, `vv_p90`, `vh_p10`,
  `vh_p50`, `vh_p90` (dB), and the spread as Phase 1 defines it, `vv_iqr` = `vv_p90` - `vv_p10`
  and `vh_iqr` = `vh_p90` - `vh_p10`;
- sampled at the plot points with `sampleRegions(scale=10, tileScale=4)` of the image as float,
  as Phase 1 sampled it;
- beside them, sampled the same way, how many images have a VV value at each plot (`n_images`).

The descending values go to `odisha_plots_sampled_s1desc.csv` (one row per plot: `plot_key`,
`district`, the eight bands, `n_images`). Nothing else is sampled.

## What is computed

The eight bands: `vv_p10`, `vv_p50`, `vv_p90`, `vv_iqr`, `vh_p10`, `vh_p50`, `vh_p90`, `vh_iqr`.
(Test 5's ninth, `vv_minus_vh_median`, is not among the bands the brief names.)

1. **Each band against each field measure of Test 5**: Lorey's height (`loreys_h_m`), crown cover
   (`crown_cover_pct`) and basal area (`basal_area_cm2`). For each pair: n, Pearson r, R² (r²),
   the slope of the band on the field measure (least squares, x the field measure, y the band,
   as Test 5 fits), and RMSE and bias as `odisha_phase1_9_gedi_recount.py` computes them
   (sqrt(mean((y - x)²)) and mean(y - x)), the statistics of `odisha_phase1_9_results.txt`, which
   the brief names. RMSE and bias compare dB with metres, per cent or cm², so for radar they carry
   no meaning; they are reported because they are named. Test 5 fitted basal area against the
   medians only; here all eight bands are fitted against it, as against the other two.
2. **All eight bands together against Lorey's height**, a linear model left one out: n, r, R²,
   RMSE, as Test 5's multi-band line (there over nine bands).
3. **Each of 1 and 2 twice**: over every plot with values, and without the plots whose spread is
   exactly zero, a plot being left out if `vv_iqr` = 0 or `vh_iqr` = 0 (its percentiles coincide:
   one image, or identical values). The number of plots left out is reported per district.
4. **Image counts per district**: the images of the collection whose footprint meets the
   district's plots' bounding box widened by 1,000 m, and the smallest, median and largest
   `n_images` over the district's plots.
5. **Beside it, the ascending orbit**: 1 to 3 recomputed from Phase 1's own sample
   (`odisha_plots_sampled_v2.csv`, no new sampling), with and without the plots whose spread is
   exactly zero (there, the 146 Koraput plots), so the two orbits are read on the same terms.

No threshold, band or field measure is chosen by its result; nothing here passes or fails. The
result file holds results only, no dates or run times; the run record beside it
(`odisha_phase1_12_radar_descending_run.json`) holds the commit and the date.

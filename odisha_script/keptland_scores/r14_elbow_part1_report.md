# The elbow report of R3's first half (round 14, Task 6)

For Jaskaran to choose k from. For R3, k for each area is his choice, from this report alone, before any R3 field score exists (`odisha_script/PHASE_KEPTLAND_PREDECLARED.md`, the change of 26 Oct 2026; register entry `field-r3-k-chosen-by-jaskaran-from-the-elbow-report`). The report reads no plot and computes no field score, and it recommends no k.

Written by `odisha_script/r14_elbow_report.py` from the records of R3's first half, the runs through the k elbow (`/Users/karan/Desktop/phd-code/docs/reproducibility/r14_runs/first_half`). The numbers behind the figures are in `r14_elbow_part1.csv`, one figure per area is in `r14_elbow_part1/`, and the record of the run that wrote them (the command, when it ran, the git commit, and every input with its SHA-256) is `r14_elbow_part1_run.json`. The areas are each Odisha district at 3 ha and at 10 ha, Sanjay Van (10 ha stands) and the 10 km tile in Angul (3 ha stands), each with its two arms, hand-crafted and AlphaEarth, side by side, and the four districts pooled, for each arm and stand size, in the stated order and with the same rows in reverse order. The tile has one arm, hand-crafted: R3 has no AlphaEarth run of the tile.

Each run's elbow is the run's own (its `_k_elbow.csv`). Each was also made again here from the run's table of stands and preprocessing record, by the code that makes the pooled elbows, and is the run's own in every number (10 of 10 runs with a record), its preprocessing its record.

**No record of 9 of the 19 runs:** `odisha_v120_10ha_squares_angul_keptland_s1desc_r14`, `odisha_alphaearth_10ha_squares_angul_keptland_r14`, `odisha_v120_10ha_squares_dhenkanal_keptland_s1desc_r14`, `odisha_alphaearth_10ha_squares_dhenkanal_keptland_r14`, `odisha_v120_10ha_squares_kendujhar_keptland_s1desc_r14`, `odisha_alphaearth_10ha_squares_kendujhar_keptland_r14`, `odisha_v120_10ha_squares_koraput_keptland_s1desc_r14`, `odisha_alphaearth_10ha_squares_koraput_keptland_r14`, `odisha_v120_3ha_tile10km_angul_keptland_s1desc_r14`. Their areas show the other arm only, and a pool that needs one is not computed.

## How the numbers are made

Each run's elbow is the k elbow step's (`k_elbow.in_fit_space` on; `fmu.stages.k_elbow`). It takes the run's table of stands (one row per stand, its mean in every candidate band) and preprocesses it over every stand by the runs' rule (`clustering.log_rule` right_skew: a band whose IQR is at most 1e-9 is dropped, and an angle's sine and cosine only together, when their shared spread is; only a band skewed to the right, skew above 1.0, is logged, as log1p((x - min) / IQR), and it is then dropped if its IQR after the log is at most 1e-9; the sine and cosine of an angle are never logged; each other band is centred by its median and divided by its IQR (a logged band's after the log), and the sine and cosine of an angle by their medians and by their shared spread, the root mean square of their two IQRs; exact quartiles). It then fits k-means on the fit's own rows in that space (the stands below the merge's minimum area, 1 ha in every R3 config, left out), for each k from 2 to 12: 25 k-means++ starts from seed 42, each refined by Lloyd's algorithm (scikit-learn, one thread), the start with the lowest within-cluster sum of squares kept. That sum, rounded to 6 decimals (as the csv gives it; the tables below, to 2), is the curve, and the knee is the k farthest from the chord between the curve's first and last points (`fmu.stages.k_elbow.knee`). At each k the adjusted Rand index of every pair of the 25 starts (300 pairs) says how much the starts agree with each other: a diagnostic of the clustering, not a field score. Its median and lowest are given, rounded to 6 decimals in the csv and to 4 in the tables, where 1 is given as 1, and an index between -0.00005 and 0.00005 other than 0 with two significant figures, so that its sign shows. The pooled elbow of an arm and stand size puts the four districts' tables of stands together, each row keyed by its district and stand label (labels repeat across districts), in the order Angul, Dhenkanal, Kendujhar, Koraput and within each by stand label, each row keeping whether it is in its run's fit. It preprocesses them together by the runs' own rule, threshold and angle pairs, and sweeps k on the rows in the fit with the same code and the same starts (`fmu.stages.k_elbow.fit_space_sweep`). k-means++ depends on the order of the rows, so each pooled elbow is also made with the same rows in reverse order, with the same preprocessing and the same sweep, and given beside it (the declaration's note of 27 Oct 2026); each run's elbow has one order, the run's. The two arms' sums of squares are in different spaces (different bands), so the figures show each relative to its own value at k = 2, and the tables give them as they are.

## The knees

| Area | Hand-crafted knee | AlphaEarth knee | Stands in the fit, of those in the table |
|---|---:|---:|---|
| Angul, 3 ha stands | 4 | 5 | Hand-crafted 166 of 220; AlphaEarth 181 of 234 |
| Dhenkanal, 3 ha stands | 6 | 5 | Hand-crafted 397 of 544; AlphaEarth 424 of 570 |
| Kendujhar, 3 ha stands | 6 | 6 | Hand-crafted 396 of 539; AlphaEarth 409 of 554 |
| Koraput, 3 ha stands | 5 | 6 | Hand-crafted 1,307 of 1,616; AlphaEarth 1,333 of 1,639 |
| Angul, 10 ha stands | no record | no record | none |
| Dhenkanal, 10 ha stands | no record | no record | none |
| Kendujhar, 10 ha stands | no record | no record | none |
| Koraput, 10 ha stands | no record | no record | none |
| Sanjay Van, 10 ha stands | 5 | 5 | Hand-crafted 189 of 490; AlphaEarth 174 of 560 |
| The 10 km tile in Angul, 3 ha stands (one arm, hand-crafted) | no record | no run (one arm) | none |
| The four districts pooled, 3 ha stands | 5 | 5 | Hand-crafted 2,266 of 2,919; AlphaEarth 2,347 of 2,997 |
| The four districts pooled, 3 ha stands, the same rows in reverse order | 5 | 5 | Hand-crafted 2,266 of 2,919; AlphaEarth 2,347 of 2,997 |
| The four districts pooled, 10 ha stands | not computed | not computed | none |
| The four districts pooled, 10 ha stands, the same rows in reverse order | not computed | not computed | none |

## Angul, 3 ha stands

Hand-crafted: `odisha_v120_3ha_squares_angul_keptland_s1desc_r14`, 166 stands in the fit of 220 in its table of stands. AlphaEarth: `odisha_alphaearth_3ha_squares_angul_keptland_r14`, 181 stands in the fit of 234 in its table of stands.

![Angul, 3 ha stands: the k elbow, hand-crafted and AlphaEarth](r14_elbow_part1/angul_3ha.png)

*Top: each arm's within-cluster sum of squares (the best of the starts) divided by its own value at k = 2, as the two arms' sums are in different spaces, on a scale from 0; each arm's knee is ringed and labelled. Bottom: the adjusted Rand index of the 300 pairs of the 25 starts, the median (solid, with points) and the lowest (dashed), on a scale from 0 to 1 taken down to -0.1580, below the lowest, -0.1080, where an index below 0 means two starts agree less than chance would. Blue: hand-crafted; vermillion: AlphaEarth.*

| k | Hand-crafted: sum of squares | median ARI | lowest ARI | AlphaEarth: sum of squares | median ARI | lowest ARI |
|---:|---:|---:|---:|---:|---:|---:|
| 2 | 1,496.23 | 0.7700 | -0.1080 | 4,790.93 | 0.1967 | -0.0711 |
| 3 | 1,109.47 | 0.8462 | 0.6730 | 3,784.18 | 0.9384 | 0.8454 |
| 4 | 929.14 (knee) | 0.8830 | 0.2700 | 3,357.37 | 0.5288 | 0.2760 |
| 5 | 838.52 | 0.5337 | 0.3786 | 3,003.47 (knee) | 0.5200 | 0.2906 |
| 6 | 778.21 | 0.4955 | 0.2694 | 2,729.05 | 0.5382 | 0.2956 |
| 7 | 728.90 | 0.4736 | 0.2814 | 2,552.04 | 0.5670 | 0.3339 |
| 8 | 682.84 | 0.4368 | 0.2995 | 2,398.00 | 0.5600 | 0.3182 |
| 9 | 655.02 | 0.4351 | 0.2605 | 2,280.06 | 0.5184 | 0.2785 |
| 10 | 620.94 | 0.4370 | 0.2705 | 2,146.83 | 0.5312 | 0.3539 |
| 11 | 595.28 | 0.4358 | 0.2912 | 2,065.34 | 0.5208 | 0.3419 |
| 12 | 573.41 | 0.4457 | 0.2716 | 1,977.65 | 0.4767 | 0.2711 |

## Dhenkanal, 3 ha stands

Hand-crafted: `odisha_v120_3ha_squares_dhenkanal_keptland_s1desc_r14`, 397 stands in the fit of 544 in its table of stands. AlphaEarth: `odisha_alphaearth_3ha_squares_dhenkanal_keptland_r14`, 424 stands in the fit of 570 in its table of stands.

![Dhenkanal, 3 ha stands: the k elbow, hand-crafted and AlphaEarth](r14_elbow_part1/dhenkanal_3ha.png)

*Top: each arm's within-cluster sum of squares (the best of the starts) divided by its own value at k = 2, as the two arms' sums are in different spaces, on a scale from 0; each arm's knee is ringed and labelled. Bottom: the adjusted Rand index of the 300 pairs of the 25 starts, the median (solid, with points) and the lowest (dashed), on a scale from 0 to 1 taken down to -0.0651, below the lowest, -0.0151, where an index below 0 means two starts agree less than chance would. Blue: hand-crafted; vermillion: AlphaEarth.*

| k | Hand-crafted: sum of squares | median ARI | lowest ARI | AlphaEarth: sum of squares | median ARI | lowest ARI |
|---:|---:|---:|---:|---:|---:|---:|
| 2 | 3,105.93 | 0.8539 | -0.0151 | 8,628.44 | 0.9906 | 0.9441 |
| 3 | 2,540.54 | 0.4907 | 0.0002 | 7,576.07 | 0.8389 | 0.6487 |
| 4 | 2,289.99 | 0.5552 | 0.3079 | 6,844.37 | 0.6280 | 0.3681 |
| 5 | 2,063.59 | 0.6289 | 0.3334 | 6,363.77 (knee) | 0.6850 | 0.3561 |
| 6 | 1,883.18 (knee) | 0.6780 | 0.2761 | 6,008.16 | 0.6190 | 0.3580 |
| 7 | 1,750.54 | 0.5970 | 0.3124 | 5,684.40 | 0.6152 | 0.4266 |
| 8 | 1,642.68 | 0.5968 | 0.3864 | 5,425.38 | 0.5358 | 0.3538 |
| 9 | 1,559.92 | 0.5629 | 0.3173 | 5,142.30 | 0.5770 | 0.3839 |
| 10 | 1,487.36 | 0.5831 | 0.4068 | 4,931.58 | 0.5576 | 0.3541 |
| 11 | 1,422.90 | 0.6578 | 0.4297 | 4,725.49 | 0.6228 | 0.4342 |
| 12 | 1,352.96 | 0.6657 | 0.3875 | 4,544.47 | 0.5763 | 0.4053 |

## Kendujhar, 3 ha stands

Hand-crafted: `odisha_v120_3ha_squares_kendujhar_keptland_s1desc_r14`, 396 stands in the fit of 539 in its table of stands. AlphaEarth: `odisha_alphaearth_3ha_squares_kendujhar_keptland_r14`, 409 stands in the fit of 554 in its table of stands.

![Kendujhar, 3 ha stands: the k elbow, hand-crafted and AlphaEarth](r14_elbow_part1/kendujhar_3ha.png)

*Top: each arm's within-cluster sum of squares (the best of the starts) divided by its own value at k = 2, as the two arms' sums are in different spaces, on a scale from 0; each arm's knee is ringed and labelled. Bottom: the adjusted Rand index of the 300 pairs of the 25 starts, the median (solid, with points) and the lowest (dashed), on a scale from 0 to 1 taken down to -0.0518, below the lowest, -0.0018, where an index below 0 means two starts agree less than chance would. Blue: hand-crafted; vermillion: AlphaEarth.*

| k | Hand-crafted: sum of squares | median ARI | lowest ARI | AlphaEarth: sum of squares | median ARI | lowest ARI |
|---:|---:|---:|---:|---:|---:|---:|
| 2 | 2,978.51 | 0.9400 | -0.0018 | 9,708.05 | 0.7274 | 0.0636 |
| 3 | 2,477.36 | 0.8118 | 0.6438 | 8,209.34 | 0.9096 | 0.1993 |
| 4 | 2,201.19 | 0.5564 | 0.3217 | 7,407.03 | 0.4799 | 0.2032 |
| 5 | 1,985.19 | 0.5887 | 0.3572 | 6,761.97 | 0.4680 | 0.2446 |
| 6 | 1,807.81 (knee) | 0.7695 | 0.3587 | 6,215.49 (knee) | 0.4853 | 0.2816 |
| 7 | 1,693.95 | 0.6332 | 0.4466 | 5,717.66 | 0.5381 | 0.3266 |
| 8 | 1,604.00 | 0.6134 | 0.4376 | 5,355.19 | 0.5721 | 0.3129 |
| 9 | 1,531.64 | 0.6373 | 0.4211 | 5,032.87 | 0.6944 | 0.4454 |
| 10 | 1,472.85 | 0.5917 | 0.3927 | 4,831.88 | 0.6277 | 0.4403 |
| 11 | 1,420.57 | 0.5914 | 0.4243 | 4,606.00 | 0.6591 | 0.3940 |
| 12 | 1,373.08 | 0.5434 | 0.3751 | 4,430.57 | 0.6278 | 0.3539 |

## Koraput, 3 ha stands

Hand-crafted: `odisha_v120_3ha_squares_koraput_keptland_s1desc_r14`, 1,307 stands in the fit of 1,616 in its table of stands. AlphaEarth: `odisha_alphaearth_3ha_squares_koraput_keptland_r14`, 1,333 stands in the fit of 1,639 in its table of stands.

![Koraput, 3 ha stands: the k elbow, hand-crafted and AlphaEarth](r14_elbow_part1/koraput_3ha.png)

*Top: each arm's within-cluster sum of squares (the best of the starts) divided by its own value at k = 2, as the two arms' sums are in different spaces, on a scale from 0; each arm's knee is ringed and labelled. Bottom: the adjusted Rand index of the 300 pairs of the 25 starts, the median (solid, with points) and the lowest (dashed), on a scale from 0 to 1. Blue: hand-crafted; vermillion: AlphaEarth.*

| k | Hand-crafted: sum of squares | median ARI | lowest ARI | AlphaEarth: sum of squares | median ARI | lowest ARI |
|---:|---:|---:|---:|---:|---:|---:|
| 2 | 12,030.57 | 0.9217 | 0.8383 | 34,167.22 | 0.9820 | 0.9582 |
| 3 | 10,424.96 | 0.4175 | 0.2205 | 29,188.02 | 0.9590 | 0.9469 |
| 4 | 9,175.51 | 0.9143 | 0.2035 | 26,228.62 | 0.8381 | 0.4031 |
| 5 | 8,441.48 (knee) | 0.6832 | 0.4688 | 24,289.51 | 0.5384 | 0.4061 |
| 6 | 7,863.00 | 0.5490 | 0.3264 | 22,474.09 (knee) | 0.7684 | 0.3878 |
| 7 | 7,374.93 | 0.5853 | 0.3282 | 21,121.25 | 0.6769 | 0.3286 |
| 8 | 6,994.09 | 0.5792 | 0.3211 | 20,103.60 | 0.5586 | 0.3052 |
| 9 | 6,652.19 | 0.5931 | 0.3307 | 19,253.02 | 0.5716 | 0.3429 |
| 10 | 6,363.89 | 0.5490 | 0.3402 | 18,429.95 | 0.5446 | 0.3344 |
| 11 | 6,127.70 | 0.6001 | 0.4267 | 17,791.57 | 0.4951 | 0.3142 |
| 12 | 5,936.88 | 0.5294 | 0.3583 | 17,207.19 | 0.5118 | 0.3295 |

## Angul, 10 ha stands

Hand-crafted: `odisha_v120_10ha_squares_angul_keptland_s1desc_r14`, no record. AlphaEarth: `odisha_alphaearth_10ha_squares_angul_keptland_r14`, no record.

No figure and no table: no arm of this area has an elbow.

## Dhenkanal, 10 ha stands

Hand-crafted: `odisha_v120_10ha_squares_dhenkanal_keptland_s1desc_r14`, no record. AlphaEarth: `odisha_alphaearth_10ha_squares_dhenkanal_keptland_r14`, no record.

No figure and no table: no arm of this area has an elbow.

## Kendujhar, 10 ha stands

Hand-crafted: `odisha_v120_10ha_squares_kendujhar_keptland_s1desc_r14`, no record. AlphaEarth: `odisha_alphaearth_10ha_squares_kendujhar_keptland_r14`, no record.

No figure and no table: no arm of this area has an elbow.

## Koraput, 10 ha stands

Hand-crafted: `odisha_v120_10ha_squares_koraput_keptland_s1desc_r14`, no record. AlphaEarth: `odisha_alphaearth_10ha_squares_koraput_keptland_r14`, no record.

No figure and no table: no arm of this area has an elbow.

## Sanjay Van, 10 ha stands

Hand-crafted: `sanjay_van_baseline_keptland_r14`, 189 stands in the fit of 490 in its table of stands. AlphaEarth: `sanjay_van_alphaearth_keptland_r14`, 174 stands in the fit of 560 in its table of stands.

![Sanjay Van, 10 ha stands: the k elbow, hand-crafted and AlphaEarth](r14_elbow_part1/sanjay_van.png)

*Top: each arm's within-cluster sum of squares (the best of the starts) divided by its own value at k = 2, as the two arms' sums are in different spaces, on a scale from 0; each arm's knee is ringed and labelled. Bottom: the adjusted Rand index of the 300 pairs of the 25 starts, the median (solid, with points) and the lowest (dashed), on a scale from 0 to 1 taken down to -0.0716, below the lowest, -0.0216, where an index below 0 means two starts agree less than chance would. Blue: hand-crafted; vermillion: AlphaEarth.*

| k | Hand-crafted: sum of squares | median ARI | lowest ARI | AlphaEarth: sum of squares | median ARI | lowest ARI |
|---:|---:|---:|---:|---:|---:|---:|
| 2 | 1,268.17 | 1 | 0.2165 | 2,478.46 | 0.9091 | -0.0216 |
| 3 | 999.72 | 0.8382 | 0.2126 | 1,989.14 | 0.8454 | 0.4522 |
| 4 | 876.70 | 0.6214 | 0.2767 | 1,696.72 | 0.8019 | 0.3674 |
| 5 | 749.31 (knee) | 0.5509 | 0.3278 | 1,519.06 (knee) | 0.5224 | 0.3401 |
| 6 | 677.42 | 0.6252 | 0.4080 | 1,404.88 | 0.5781 | 0.2401 |
| 7 | 632.02 | 0.5692 | 0.3612 | 1,322.19 | 0.5291 | 0.2713 |
| 8 | 592.17 | 0.5353 | 0.3043 | 1,245.43 | 0.5490 | 0.3334 |
| 9 | 567.41 | 0.5506 | 0.3496 | 1,187.17 | 0.5299 | 0.3173 |
| 10 | 549.30 | 0.5426 | 0.3517 | 1,118.74 | 0.5015 | 0.3512 |
| 11 | 526.94 | 0.4969 | 0.3267 | 1,071.92 | 0.5012 | 0.3207 |
| 12 | 508.01 | 0.4936 | 0.3276 | 1,045.79 | 0.4831 | 0.3037 |

## The 10 km tile in Angul, 3 ha stands (one arm, hand-crafted)

Hand-crafted: `odisha_v120_3ha_tile10km_angul_keptland_s1desc_r14`, no record. The tile has one arm: R3 has no AlphaEarth run of the tile.

No figure and no table: no arm of this area has an elbow.

## The four districts pooled, 3 ha stands

The four districts' tables of stands put together, each row keyed by its district and stand label: the stands of each table, and in brackets those in the fit.

| District | Hand-crafted: stands (in the fit) | AlphaEarth: stands (in the fit) |
|---|---:|---:|
| Angul | 220 (166) | 234 (181) |
| Dhenkanal | 544 (397) | 570 (424) |
| Kendujhar | 539 (396) | 554 (409) |
| Koraput | 1,616 (1,307) | 1,639 (1,333) |
| Pooled | 2,919 (2,266) | 2,997 (2,347) |

Hand-crafted: preprocessed together by the runs' rule (`right_skew`, skew threshold 1.0; the angles taken as sine and cosine: `ndvi_phase_annual`, `aspect`): 22 of 22 candidate bands kept, 4 logged (`vv_iqr`, `vh_iqr`, `vv_minus_vh_median`, `canopy_height_std`), dropped as constant: none.

AlphaEarth: preprocessed together by the runs' rule (`right_skew`, skew threshold 1.0; the angles taken as sine and cosine: none): 64 of 64 candidate bands kept, 0 logged, dropped as constant: none.

![The four districts pooled, 3 ha stands: the k elbow, hand-crafted and AlphaEarth, the rows in the stated order and in reverse order](r14_elbow_part1/pooled_3ha.png)

*Left: the rows in the stated order; right: the same rows in reverse order, on the same axes. Top: each arm's within-cluster sum of squares (the best of the starts) divided by its own value at k = 2 in that order, as the two arms' sums are in different spaces, on a scale from 0; each arm's knee is ringed and named in each panel's legend. Bottom: the adjusted Rand index of the 300 pairs of the 25 starts, the median (solid, with points) and the lowest (dashed), on a scale from 0 to 1. Blue: hand-crafted; vermillion: AlphaEarth.*

**The rows in the stated order** (Angul, Dhenkanal, Kendujhar, Koraput, each by stand label). Knees: hand-crafted k = 5, AlphaEarth k = 5.

| k | Hand-crafted: sum of squares | median ARI | lowest ARI | AlphaEarth: sum of squares | median ARI | lowest ARI |
|---:|---:|---:|---:|---:|---:|---:|
| 2 | 21,236.25 | 0.9876 | 0.0434 | 56,081.02 | 1 | 0.9829 |
| 3 | 17,099.56 | 1 | 0.9924 | 47,120.33 | 0.9457 | 0.4021 |
| 4 | 15,506.07 | 0.8977 | 0.4638 | 41,783.52 | 0.9903 | 0.9822 |
| 5 | 14,126.58 (knee) | 0.7126 | 0.4957 | 38,703.60 (knee) | 0.6034 | 0.4678 |
| 6 | 13,042.31 | 0.9737 | 0.3746 | 36,156.61 | 0.5860 | 0.3975 |
| 7 | 12,385.66 | 0.6372 | 0.5075 | 34,143.77 | 0.6003 | 0.3861 |
| 8 | 11,831.10 | 0.5857 | 0.3978 | 32,534.49 | 0.6820 | 0.3854 |
| 9 | 11,324.54 | 0.5690 | 0.4119 | 31,150.47 | 0.6210 | 0.3711 |
| 10 | 10,928.13 | 0.5688 | 0.3693 | 29,753.87 | 0.6166 | 0.4313 |
| 11 | 10,535.51 | 0.6064 | 0.4105 | 28,548.84 | 0.6650 | 0.4536 |
| 12 | 10,154.11 | 0.5988 | 0.3386 | 27,585.16 | 0.6084 | 0.4399 |

**The same rows in reverse order** (the same preprocessing and the same sweep). Knees: hand-crafted k = 5, AlphaEarth k = 5.

| k | Hand-crafted: sum of squares | median ARI | lowest ARI | AlphaEarth: sum of squares | median ARI | lowest ARI |
|---:|---:|---:|---:|---:|---:|---:|
| 2 | 21,236.25 | 0.9876 | 0.0434 | 56,081.02 | 1 | 0.9829 |
| 3 | 17,099.56 | 0.9954 | 0.9924 | 47,120.65 | 0.9458 | 0.4026 |
| 4 | 15,506.24 | 0.7678 | 0.4659 | 41,783.52 | 0.9822 | 0.5416 |
| 5 | 14,126.38 (knee) | 0.6641 | 0.5189 | 38,703.60 (knee) | 0.6707 | 0.4809 |
| 6 | 13,042.33 | 0.9772 | 0.7706 | 36,155.79 | 0.5922 | 0.4218 |
| 7 | 12,385.53 | 0.6234 | 0.4213 | 34,137.99 | 0.6477 | 0.3442 |
| 8 | 11,827.53 | 0.5916 | 0.3849 | 32,532.02 | 0.6369 | 0.4005 |
| 9 | 11,324.61 | 0.5903 | 0.4193 | 31,152.08 | 0.6285 | 0.3705 |
| 10 | 10,919.69 | 0.5660 | 0.3816 | 29,759.75 | 0.6645 | 0.5036 |
| 11 | 10,538.28 | 0.5861 | 0.4135 | 28,525.08 | 0.6527 | 0.4521 |
| 12 | 10,148.14 | 0.5994 | 0.3802 | 27,416.46 | 0.5970 | 0.4354 |

## The four districts pooled, 10 ha stands

The four districts' tables of stands put together, each row keyed by its district and stand label: the stands of each table, and in brackets those in the fit.

| District | Hand-crafted: stands (in the fit) | AlphaEarth: stands (in the fit) |
|---|---:|---:|
| Angul | no record | no record |
| Dhenkanal | no record | no record |
| Kendujhar | no record | no record |
| Koraput | no record | no record |
| Pooled | not computed | not computed |

Hand-crafted: not computed, no record of `odisha_v120_10ha_squares_angul_keptland_s1desc_r14`, `odisha_v120_10ha_squares_dhenkanal_keptland_s1desc_r14`, `odisha_v120_10ha_squares_kendujhar_keptland_s1desc_r14`, `odisha_v120_10ha_squares_koraput_keptland_s1desc_r14`.

AlphaEarth: not computed, no record of `odisha_alphaearth_10ha_squares_angul_keptland_r14`, `odisha_alphaearth_10ha_squares_dhenkanal_keptland_r14`, `odisha_alphaearth_10ha_squares_kendujhar_keptland_r14`, `odisha_alphaearth_10ha_squares_koraput_keptland_r14`.

No figure and no table: no arm of this area has an elbow.

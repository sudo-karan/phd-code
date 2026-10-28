# Sanjay Van, R3: distance to water capped at 10 km, checked on the stands' means

Written by `odisha_script/r14_sanjay_van_water_cap_check.py` from R3's committed records of the hand-crafted Sanjay Van run, `sanjay_van_baseline_keptland_r14` (`docs/reproducibility/r14_runs/first_half/`), by the round's own code. Jaskaran's check of 28 Oct 2026, reproduced as he asked: R3 runs without the cap (`features_static.cap_distance_to_water` off, its default), and this says what capping the band would change. Numbers only.

**The limit of this check.** It caps each stand's mean of `distance_to_water`, which is all a committed table of stands allows. The setting caps each pixel before a stand's mean is taken, so a stand with pixels on both sides of the cap reads below it under the setting and at it here. The band's lower quartile stays at the cap only while at most 122 of the 490 stands read below it: 117 do here, and 9 stand means lie from 10,000 m to 10,100 m (35 to 10,200 m). Jaskaran's correction, 28 Oct 2026, beside his reason: "the check capped stand means, but the setting caps pixels, so at Sanjay Van the band would likely be kept with a very small IQR (9 stand means lie between 10,000 and 10,100 m), which the median/IQR scaling would magnify. So capping there would likely be worse, not just negligible." So this check does not show what the setting would do at Sanjay Van; it shows what capping the stands' means does.

His reason for no cap in R3, as he gave it: "capping at 10 km drops the band as constant (373 of 490 stands at the cap) but changes the type of only 5 of 490 stands at k = 5 (ARI 0.974), and the knee stays 5. This was checked offline on R3’s committed stand table, with the round’s own preprocessing and sweep, which reproduce the recorded elbow exactly."

## The run's elbow made again

- Its elbow made again from its table of stands and preprocessing record (`odisha_script/r14_elbow_report.py`'s check): the same in every number.
- Its types at k = 5 by the best start's nearest centre: 490 of 490 stands as in its `_k_elbow_types.csv`.

## `distance_to_water` in the table: each stand's mean, m

| | |
|---|---:|
| stands | 490 |
| smallest | 8,990.0 |
| 25th percentile | 10,040.3 |
| median | 10,687.0 |
| 75th percentile | 11,296.5 |
| largest | 12,331.1 |
| below 10,000 m | 117 |
| at or past 10,000 m | 373 |
| from 10,000 m to 10,100 m | 9 |
| from 10,000 m to 10,200 m | 35 |
| the most below 10,000 m with the lower quartile still at it | 122 |

## The stands' means capped, against not capped

| | not capped (the run's) | capped |
|---|---:|---:|
| bands dropped as constant | none | distance_to_water |
| bands in the fit | 22 | 21 |
| knee | 5 | 5 |

At k = 5, the types of every stand, capped against not: adjusted Rand index 0.9738 over the 490 stands (0.9896 over the 189 in the fit); 5 of the 490 stands change type once the capped types are matched to the others by greatest overlap.

| k | sum of squares, not capped | median ARI | sum of squares, capped | median ARI |
|---:|---:|---:|---:|---:|
| 2 | 1,268.17 | 1.0000 | 1,195.67 | 0.6348 |
| 3 | 999.72 | 0.8382 | 931.10 | 0.8635 |
| 4 | 876.70 | 0.6214 | 796.69 | 0.5778 |
| 5 | 749.31 | 0.5509 | 679.27 | 0.6462 |
| 6 | 677.42 | 0.6252 | 611.56 | 0.6427 |
| 7 | 632.02 | 0.5692 | 569.81 | 0.5899 |
| 8 | 592.17 | 0.5353 | 531.08 | 0.5741 |
| 9 | 567.41 | 0.5506 | 508.59 | 0.5576 |
| 10 | 549.30 | 0.5426 | 486.23 | 0.5139 |
| 11 | 526.94 | 0.4969 | 469.68 | 0.4901 |
| 12 | 508.01 | 0.4936 | 450.94 | 0.4994 |

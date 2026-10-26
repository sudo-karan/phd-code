# The kept-land chance test: AlphaEarth, 3 ha (_r9) beside AlphaEarth, 10 ha

Written by `odisha_script/odisha_keptland_chance_compare.py` from the chance test's result files
(`odisha_script/odisha_keptland_chance.py`). For each score: the observed value, the median of the
rotation null, the observed value's percentile in it, and the one-sided p after Holm over the five
tests of that analysis and set; a test passes at a Holm p of at most 0.05. The three drawing scores
are read against the unconditional null, the two labelling scores against the conditional one.
Numbers only: nothing is tested across sets.

## primary: the primary field types, every plot the join scores

| Score | AlphaEarth, 3 ha (_r9): observed | chance median | percentile | Holm p | AlphaEarth, 10 ha: observed | chance median | percentile | Holm p |
|---|---|---|---|---|---|---|---|---|
| 1 drawing: ARI, all plots | +0.0053 | +0.0064 | 26.3 | 1.000 | +0.0170 | +0.0132 | 86.1 | 0.695 |
| 2 drawing: ARI, stands of 2+ plots | +0.0229 | +0.0285 | 26.2 | 1.000 | +0.0305 | +0.0305 | 49.9 | 1.000 |
| 3 drawing: same-stand pair precision | +0.5130 | +0.5309 | 37.8 | 1.000 | +0.5729 | +0.5269 | 83.0 | 0.695 |
| 4 labelling: ARI, district mean | +0.0411 | +0.0417 | 48.6 | 1.000 | +0.0507 | +0.0621 | 29.1 | 1.000 |
| 5 labelling: far-apart gap | -0.0043 | +0.0074 | 29.6 | 1.000 | -0.0060 | +0.0174 | 14.0 | 1.000 |

Tests that pass after Holm: AlphaEarth, 3 ha (_r9) 0 of 5; AlphaEarth, 10 ha 0 of 5.

## S1: field type 0 (no trees) left out, same realisations

| Score | AlphaEarth, 3 ha (_r9): observed | chance median | percentile | Holm p | AlphaEarth, 10 ha: observed | chance median | percentile | Holm p |
|---|---|---|---|---|---|---|---|---|
| 1 drawing: ARI, all plots | +0.0044 | +0.0058 | 15.8 | 1.000 | +0.0145 | +0.0122 | 77.3 | 1.000 |
| 2 drawing: ARI, stands of 2+ plots | +0.0193 | +0.0255 | 20.8 | 1.000 | +0.0256 | +0.0280 | 35.7 | 1.000 |
| 3 drawing: same-stand pair precision | +0.5484 | +0.5797 | 29.0 | 1.000 | +0.6032 | +0.5730 | 75.8 | 1.000 |
| 4 labelling: ARI, district mean | +0.0567 | +0.0446 | 70.7 | 1.000 | +0.0570 | +0.0644 | 34.9 | 1.000 |
| 5 labelling: far-apart gap | +0.0022 | +0.0117 | 32.2 | 1.000 | +0.0014 | +0.0225 | 17.6 | 1.000 |

Tests that pass after Holm: AlphaEarth, 3 ha (_r9) 0 of 5; AlphaEarth, 10 ha 0 of 5.

## S2: four field types (odisha_phase3_0_field_types_k4.csv), same realisations

| Score | AlphaEarth, 3 ha (_r9): observed | chance median | percentile | Holm p | AlphaEarth, 10 ha: observed | chance median | percentile | Holm p |
|---|---|---|---|---|---|---|---|---|
| 1 drawing: ARI, all plots | +0.0051 | +0.0052 | 47.0 | 1.000 | +0.0114 | +0.0106 | 62.0 | 1.000 |
| 2 drawing: ARI, stands of 2+ plots | +0.0190 | +0.0218 | 34.3 | 1.000 | +0.0215 | +0.0242 | 32.3 | 1.000 |
| 3 drawing: same-stand pair precision | +0.6870 | +0.6441 | 79.6 | 1.000 | +0.6508 | +0.6382 | 60.4 | 1.000 |
| 4 labelling: ARI, district mean | +0.0340 | +0.0348 | 48.5 | 1.000 | +0.0319 | +0.0471 | 21.9 | 1.000 |
| 5 labelling: far-apart gap | -0.0057 | +0.0188 | 12.7 | 1.000 | -0.0138 | +0.0212 | 6.8 | 1.000 |

Tests that pass after Holm: AlphaEarth, 3 ha (_r9) 0 of 5; AlphaEarth, 10 ha 0 of 5.

## Check C1: the labelling mean without Kendujhar, on both sides

Beside the primary's score 4, outside the Holm correction, no pass or fail (`odisha_script/PHASE_KEPTLAND_AMENDMENT_chance_checks.md`); its p is the one-sided p.

| Check | AlphaEarth, 3 ha (_r9): observed | chance median | percentile | p | AlphaEarth, 10 ha: observed | chance median | percentile | p |
|---|---|---|---|---|---|---|---|---|
| C1: labelling ARI, district mean, Kendujhar left out | +0.0332 | +0.0418 | 31.3 | 0.687 | +0.0521 | +0.0629 | 29.2 | 0.709 |

## What each set ran on

| Set | Runs | Declared or rehearsal | Realisations | Seed name | Null built | Plots scored (primary, C1) | Realisations with fewer districts in the labelling mean |
|---|---|---|---|---|---|---|---|
| AlphaEarth, 3 ha (_r9) | `odisha_alphaearth_3ha_squares_angul_keptland_r9`, `odisha_alphaearth_3ha_squares_dhenkanal_keptland_r9`, `odisha_alphaearth_3ha_squares_kendujhar_keptland_r9`, `odisha_alphaearth_3ha_squares_koraput_keptland_r9` | declared | 1999 | `alphaearth_3ha_squares_keptland` | yes | 264, 257 | 451 |
| AlphaEarth, 10 ha | `odisha_alphaearth_10ha_squares_angul_keptland_r9`, `odisha_alphaearth_10ha_squares_dhenkanal_keptland_r9`, `odisha_alphaearth_10ha_squares_kendujhar_keptland_r9`, `odisha_alphaearth_10ha_squares_koraput_keptland_r9` | declared | 1999 | `alphaearth_10ha_squares_keptland` | yes | 264, 257 | 436 |

## Note added 20 Oct 2026 (round 13, review A1, A4, A5, A6, B13, B14, B16, B17 and B18)

The numbers above are as first written. Both sets are on AlphaEarth stands from before the round 13
fixes (`docs/handoff/2026-10-20-round13.md`, Done), and so are the differences between them. A1, A5
and B13 do not reach this arm. A4 reaches its Koraput runs, at both sizes, through the merge's NDVI
amplitude (question 1 of that record; until it is answered, noted as affected, by an amount not
measured), and no other run of it. The merge and clustering fixes B14, B16, B17 and B18 reach every
run. Whether roadmap R3 re-runs this arm is put to Jaskaran in that record. How far any fix moves a
score, a null, a p or a difference was not measured; it needs Earth Engine. The note at the end of
each chance file says more (`keptland_alphaearth_r9_chance.txt`,
`keptland_alphaearth_10ha_r9_chance.txt`). `README.md` here lists every file noted. No number here
is changed.

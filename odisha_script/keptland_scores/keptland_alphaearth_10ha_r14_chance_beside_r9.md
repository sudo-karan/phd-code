# The kept-land chance test: AlphaEarth, 10 ha (_r9) beside AlphaEarth, 10 ha (R3)

Written by `odisha_script/odisha_keptland_chance_compare.py` from the chance test's result files
(`odisha_script/odisha_keptland_chance.py`). For each score: the observed value, the median of the
rotation null, the observed value's percentile in it, and the one-sided p after Holm over the five
tests of that analysis and set; a test passes at a Holm p of at most 0.05. The three drawing scores
are read against the unconditional null, the two labelling scores against the conditional one.
Numbers only: nothing is tested across sets.

## primary: the primary field types, every plot the join scores

| Score | AlphaEarth, 10 ha (_r9): observed | chance median | percentile | Holm p | AlphaEarth, 10 ha (R3): observed | chance median | percentile | Holm p |
|---|---|---|---|---|---|---|---|---|
| 1 drawing: ARI, all plots | +0.0170 | +0.0132 | 86.1 | 0.695 | +0.0172 | +0.0131 | 88.2 | 0.590 |
| 2 drawing: ARI, stands of 2+ plots | +0.0305 | +0.0305 | 49.9 | 1.000 | +0.0302 | +0.0304 | 48.8 | 1.000 |
| 3 drawing: same-stand pair precision | +0.5729 | +0.5269 | 83.0 | 0.695 | +0.5587 | +0.5269 | 74.9 | 1.000 |
| 4 labelling: ARI, district mean | +0.0507 | +0.0621 | 29.1 | 1.000 | +0.0546 | +0.0604 | 40.9 | 1.000 |
| 5 labelling: far-apart gap | -0.0060 | +0.0174 | 14.0 | 1.000 | +0.0021 | +0.0297 | 15.8 | 1.000 |

Tests that pass after Holm: AlphaEarth, 10 ha (_r9) 0 of 5; AlphaEarth, 10 ha (R3) 0 of 5.

## S1: field type 0 (no trees) left out, same realisations

| Score | AlphaEarth, 10 ha (_r9): observed | chance median | percentile | Holm p | AlphaEarth, 10 ha (R3): observed | chance median | percentile | Holm p |
|---|---|---|---|---|---|---|---|---|
| 1 drawing: ARI, all plots | +0.0145 | +0.0122 | 77.3 | 1.000 | +0.0148 | +0.0122 | 80.6 | 0.970 |
| 2 drawing: ARI, stands of 2+ plots | +0.0256 | +0.0280 | 35.7 | 1.000 | +0.0256 | +0.0280 | 35.7 | 1.000 |
| 3 drawing: same-stand pair precision | +0.6032 | +0.5730 | 75.8 | 1.000 | +0.6031 | +0.5723 | 76.8 | 0.970 |
| 4 labelling: ARI, district mean | +0.0570 | +0.0644 | 34.9 | 1.000 | +0.0692 | +0.0655 | 55.6 | 1.000 |
| 5 labelling: far-apart gap | +0.0014 | +0.0225 | 17.6 | 1.000 | +0.0284 | +0.0422 | 32.7 | 1.000 |

Tests that pass after Holm: AlphaEarth, 10 ha (_r9) 0 of 5; AlphaEarth, 10 ha (R3) 0 of 5.

## S2: four field types (odisha_phase3_0_field_types_k4.csv), same realisations

| Score | AlphaEarth, 10 ha (_r9): observed | chance median | percentile | Holm p | AlphaEarth, 10 ha (R3): observed | chance median | percentile | Holm p |
|---|---|---|---|---|---|---|---|---|
| 1 drawing: ARI, all plots | +0.0114 | +0.0106 | 62.0 | 1.000 | +0.0117 | +0.0105 | 67.0 | 1.000 |
| 2 drawing: ARI, stands of 2+ plots | +0.0215 | +0.0242 | 32.3 | 1.000 | +0.0216 | +0.0243 | 32.6 | 1.000 |
| 3 drawing: same-stand pair precision | +0.6508 | +0.6382 | 60.4 | 1.000 | +0.6413 | +0.6376 | 53.2 | 1.000 |
| 4 labelling: ARI, district mean | +0.0319 | +0.0471 | 21.9 | 1.000 | +0.0033 | +0.0371 | 7.6 | 1.000 |
| 5 labelling: far-apart gap | -0.0138 | +0.0212 | 6.8 | 1.000 | -0.0101 | +0.0354 | 7.6 | 1.000 |

Tests that pass after Holm: AlphaEarth, 10 ha (_r9) 0 of 5; AlphaEarth, 10 ha (R3) 0 of 5.

## Check C1: the labelling mean without Kendujhar, on both sides

Beside the primary's score 4, outside the Holm correction, no pass or fail (`odisha_script/PHASE_KEPTLAND_AMENDMENT_chance_checks.md`); its p is the one-sided p.

| Check | AlphaEarth, 10 ha (_r9): observed | chance median | percentile | p | AlphaEarth, 10 ha (R3): observed | chance median | percentile | p |
|---|---|---|---|---|---|---|---|---|
| C1: labelling ARI, district mean, Kendujhar left out | +0.0521 | +0.0629 | 29.2 | 0.709 | +0.0561 | +0.0606 | 42.5 | 0.576 |

## What each set ran on

| Set | Runs | Declared or rehearsal | Realisations | Seed name | Null built | Plots scored (primary, C1) | Realisations with fewer districts in the labelling mean |
|---|---|---|---|---|---|---|---|
| AlphaEarth, 10 ha (_r9) | `odisha_alphaearth_10ha_squares_angul_keptland_r9`, `odisha_alphaearth_10ha_squares_dhenkanal_keptland_r9`, `odisha_alphaearth_10ha_squares_kendujhar_keptland_r9`, `odisha_alphaearth_10ha_squares_koraput_keptland_r9` | declared | 1999 | `alphaearth_10ha_squares_keptland` | yes | 264, 257 | 436 |
| AlphaEarth, 10 ha (R3) | `odisha_alphaearth_10ha_squares_angul_keptland_r14`, `odisha_alphaearth_10ha_squares_dhenkanal_keptland_r14`, `odisha_alphaearth_10ha_squares_kendujhar_keptland_r14`, `odisha_alphaearth_10ha_squares_koraput_keptland_r14` | declared | 1999 | `alphaearth_10ha_squares_keptland` | yes | 264, 257 | 436 |

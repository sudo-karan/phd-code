# The kept-land chance test: AlphaEarth, 3 ha (R3) beside AlphaEarth, 10 ha (R3)

Written by `odisha_script/odisha_keptland_chance_compare.py` from the chance test's result files
(`odisha_script/odisha_keptland_chance.py`). For each score: the observed value, the median of the
rotation null, the observed value's percentile in it, and the one-sided p after Holm over the five
tests of that analysis and set; a test passes at a Holm p of at most 0.05. The three drawing scores
are read against the unconditional null, the two labelling scores against the conditional one.
Numbers only: nothing is tested across sets.

## primary: the primary field types, every plot the join scores

| Score | AlphaEarth, 3 ha (R3): observed | chance median | percentile | Holm p | AlphaEarth, 10 ha (R3): observed | chance median | percentile | Holm p |
|---|---|---|---|---|---|---|---|---|
| 1 drawing: ARI, all plots | +0.0053 | +0.0064 | 25.9 | 1.000 | +0.0172 | +0.0131 | 88.2 | 0.590 |
| 2 drawing: ARI, stands of 2+ plots | +0.0229 | +0.0284 | 25.8 | 1.000 | +0.0302 | +0.0304 | 48.8 | 1.000 |
| 3 drawing: same-stand pair precision | +0.5130 | +0.5316 | 37.4 | 1.000 | +0.5587 | +0.5269 | 74.9 | 1.000 |
| 4 labelling: ARI, district mean | +0.0466 | +0.0618 | 22.9 | 1.000 | +0.0546 | +0.0604 | 40.9 | 1.000 |
| 5 labelling: far-apart gap | -0.0012 | +0.0241 | 16.0 | 1.000 | +0.0021 | +0.0297 | 15.8 | 1.000 |

Tests that pass after Holm: AlphaEarth, 3 ha (R3) 0 of 5; AlphaEarth, 10 ha (R3) 0 of 5.

## S1: field type 0 (no trees) left out, same realisations

| Score | AlphaEarth, 3 ha (R3): observed | chance median | percentile | Holm p | AlphaEarth, 10 ha (R3): observed | chance median | percentile | Holm p |
|---|---|---|---|---|---|---|---|---|
| 1 drawing: ARI, all plots | +0.0044 | +0.0058 | 15.6 | 1.000 | +0.0148 | +0.0122 | 80.6 | 0.970 |
| 2 drawing: ARI, stands of 2+ plots | +0.0193 | +0.0255 | 20.1 | 1.000 | +0.0256 | +0.0280 | 35.7 | 1.000 |
| 3 drawing: same-stand pair precision | +0.5484 | +0.5789 | 28.9 | 1.000 | +0.6031 | +0.5723 | 76.8 | 0.970 |
| 4 labelling: ARI, district mean | +0.0543 | +0.0617 | 38.1 | 1.000 | +0.0692 | +0.0655 | 55.6 | 1.000 |
| 5 labelling: far-apart gap | +0.0074 | +0.0241 | 26.4 | 1.000 | +0.0284 | +0.0422 | 32.7 | 1.000 |

Tests that pass after Holm: AlphaEarth, 3 ha (R3) 0 of 5; AlphaEarth, 10 ha (R3) 0 of 5.

## S2: four field types (odisha_phase3_0_field_types_k4.csv), same realisations

| Score | AlphaEarth, 3 ha (R3): observed | chance median | percentile | Holm p | AlphaEarth, 10 ha (R3): observed | chance median | percentile | Holm p |
|---|---|---|---|---|---|---|---|---|
| 1 drawing: ARI, all plots | +0.0051 | +0.0051 | 46.9 | 1.000 | +0.0117 | +0.0105 | 67.0 | 1.000 |
| 2 drawing: ARI, stands of 2+ plots | +0.0190 | +0.0218 | 33.5 | 1.000 | +0.0216 | +0.0243 | 32.6 | 1.000 |
| 3 drawing: same-stand pair precision | +0.6870 | +0.6442 | 79.1 | 1.000 | +0.6413 | +0.6376 | 53.2 | 1.000 |
| 4 labelling: ARI, district mean | +0.0355 | +0.0496 | 27.3 | 1.000 | +0.0033 | +0.0371 | 7.6 | 1.000 |
| 5 labelling: far-apart gap | -0.0053 | +0.0274 | 11.8 | 1.000 | -0.0101 | +0.0354 | 7.6 | 1.000 |

Tests that pass after Holm: AlphaEarth, 3 ha (R3) 0 of 5; AlphaEarth, 10 ha (R3) 0 of 5.

## Check C1: the labelling mean without Kendujhar, on both sides

Beside the primary's score 4, outside the Holm correction, no pass or fail (`odisha_script/PHASE_KEPTLAND_AMENDMENT_chance_checks.md`); its p is the one-sided p.

| Check | AlphaEarth, 3 ha (R3): observed | chance median | percentile | p | AlphaEarth, 10 ha (R3): observed | chance median | percentile | p |
|---|---|---|---|---|---|---|---|---|
| C1: labelling ARI, district mean, Kendujhar left out | +0.0478 | +0.0622 | 23.9 | 0.761 | +0.0561 | +0.0606 | 42.5 | 0.576 |

## What each set ran on

| Set | Runs | Declared or rehearsal | Realisations | Seed name | Null built | Plots scored (primary, C1) | Realisations with fewer districts in the labelling mean |
|---|---|---|---|---|---|---|---|
| AlphaEarth, 3 ha (R3) | `odisha_alphaearth_3ha_squares_angul_keptland_r14`, `odisha_alphaearth_3ha_squares_dhenkanal_keptland_r14`, `odisha_alphaearth_3ha_squares_kendujhar_keptland_r14`, `odisha_alphaearth_3ha_squares_koraput_keptland_r14` | declared | 1999 | `alphaearth_3ha_squares_keptland` | yes | 264, 257 | 451 |
| AlphaEarth, 10 ha (R3) | `odisha_alphaearth_10ha_squares_angul_keptland_r14`, `odisha_alphaearth_10ha_squares_dhenkanal_keptland_r14`, `odisha_alphaearth_10ha_squares_kendujhar_keptland_r14`, `odisha_alphaearth_10ha_squares_koraput_keptland_r14` | declared | 1999 | `alphaearth_10ha_squares_keptland` | yes | 264, 257 | 436 |

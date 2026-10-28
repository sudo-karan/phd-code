# The kept-land chance test: AlphaEarth, 3 ha (_r9) beside AlphaEarth, 3 ha (R3)

Written by `odisha_script/odisha_keptland_chance_compare.py` from the chance test's result files
(`odisha_script/odisha_keptland_chance.py`). For each score: the observed value, the median of the
rotation null, the observed value's percentile in it, and the one-sided p after Holm over the five
tests of that analysis and set; a test passes at a Holm p of at most 0.05. The three drawing scores
are read against the unconditional null, the two labelling scores against the conditional one.
Numbers only: nothing is tested across sets.

## primary: the primary field types, every plot the join scores

| Score | AlphaEarth, 3 ha (_r9): observed | chance median | percentile | Holm p | AlphaEarth, 3 ha (R3): observed | chance median | percentile | Holm p |
|---|---|---|---|---|---|---|---|---|
| 1 drawing: ARI, all plots | +0.0053 | +0.0064 | 26.3 | 1.000 | +0.0053 | +0.0064 | 25.9 | 1.000 |
| 2 drawing: ARI, stands of 2+ plots | +0.0229 | +0.0285 | 26.2 | 1.000 | +0.0229 | +0.0284 | 25.8 | 1.000 |
| 3 drawing: same-stand pair precision | +0.5130 | +0.5309 | 37.8 | 1.000 | +0.5130 | +0.5316 | 37.4 | 1.000 |
| 4 labelling: ARI, district mean | +0.0411 | +0.0417 | 48.6 | 1.000 | +0.0466 | +0.0618 | 22.9 | 1.000 |
| 5 labelling: far-apart gap | -0.0043 | +0.0074 | 29.6 | 1.000 | -0.0012 | +0.0241 | 16.0 | 1.000 |

Tests that pass after Holm: AlphaEarth, 3 ha (_r9) 0 of 5; AlphaEarth, 3 ha (R3) 0 of 5.

## S1: field type 0 (no trees) left out, same realisations

| Score | AlphaEarth, 3 ha (_r9): observed | chance median | percentile | Holm p | AlphaEarth, 3 ha (R3): observed | chance median | percentile | Holm p |
|---|---|---|---|---|---|---|---|---|
| 1 drawing: ARI, all plots | +0.0044 | +0.0058 | 15.8 | 1.000 | +0.0044 | +0.0058 | 15.6 | 1.000 |
| 2 drawing: ARI, stands of 2+ plots | +0.0193 | +0.0255 | 20.8 | 1.000 | +0.0193 | +0.0255 | 20.1 | 1.000 |
| 3 drawing: same-stand pair precision | +0.5484 | +0.5797 | 29.0 | 1.000 | +0.5484 | +0.5789 | 28.9 | 1.000 |
| 4 labelling: ARI, district mean | +0.0567 | +0.0446 | 70.7 | 1.000 | +0.0543 | +0.0617 | 38.1 | 1.000 |
| 5 labelling: far-apart gap | +0.0022 | +0.0117 | 32.2 | 1.000 | +0.0074 | +0.0241 | 26.4 | 1.000 |

Tests that pass after Holm: AlphaEarth, 3 ha (_r9) 0 of 5; AlphaEarth, 3 ha (R3) 0 of 5.

## S2: four field types (odisha_phase3_0_field_types_k4.csv), same realisations

| Score | AlphaEarth, 3 ha (_r9): observed | chance median | percentile | Holm p | AlphaEarth, 3 ha (R3): observed | chance median | percentile | Holm p |
|---|---|---|---|---|---|---|---|---|
| 1 drawing: ARI, all plots | +0.0051 | +0.0052 | 47.0 | 1.000 | +0.0051 | +0.0051 | 46.9 | 1.000 |
| 2 drawing: ARI, stands of 2+ plots | +0.0190 | +0.0218 | 34.3 | 1.000 | +0.0190 | +0.0218 | 33.5 | 1.000 |
| 3 drawing: same-stand pair precision | +0.6870 | +0.6441 | 79.6 | 1.000 | +0.6870 | +0.6442 | 79.1 | 1.000 |
| 4 labelling: ARI, district mean | +0.0340 | +0.0348 | 48.5 | 1.000 | +0.0355 | +0.0496 | 27.3 | 1.000 |
| 5 labelling: far-apart gap | -0.0057 | +0.0188 | 12.7 | 1.000 | -0.0053 | +0.0274 | 11.8 | 1.000 |

Tests that pass after Holm: AlphaEarth, 3 ha (_r9) 0 of 5; AlphaEarth, 3 ha (R3) 0 of 5.

## Check C1: the labelling mean without Kendujhar, on both sides

Beside the primary's score 4, outside the Holm correction, no pass or fail (`odisha_script/PHASE_KEPTLAND_AMENDMENT_chance_checks.md`); its p is the one-sided p.

| Check | AlphaEarth, 3 ha (_r9): observed | chance median | percentile | p | AlphaEarth, 3 ha (R3): observed | chance median | percentile | p |
|---|---|---|---|---|---|---|---|---|
| C1: labelling ARI, district mean, Kendujhar left out | +0.0332 | +0.0418 | 31.3 | 0.687 | +0.0478 | +0.0622 | 23.9 | 0.761 |

## What each set ran on

| Set | Runs | Declared or rehearsal | Realisations | Seed name | Null built | Plots scored (primary, C1) | Realisations with fewer districts in the labelling mean |
|---|---|---|---|---|---|---|---|
| AlphaEarth, 3 ha (_r9) | `odisha_alphaearth_3ha_squares_angul_keptland_r9`, `odisha_alphaearth_3ha_squares_dhenkanal_keptland_r9`, `odisha_alphaearth_3ha_squares_kendujhar_keptland_r9`, `odisha_alphaearth_3ha_squares_koraput_keptland_r9` | declared | 1999 | `alphaearth_3ha_squares_keptland` | yes | 264, 257 | 451 |
| AlphaEarth, 3 ha (R3) | `odisha_alphaearth_3ha_squares_angul_keptland_r14`, `odisha_alphaearth_3ha_squares_dhenkanal_keptland_r14`, `odisha_alphaearth_3ha_squares_kendujhar_keptland_r14`, `odisha_alphaearth_3ha_squares_koraput_keptland_r14` | declared | 1999 | `alphaearth_3ha_squares_keptland` | yes | 264, 257 | 451 |

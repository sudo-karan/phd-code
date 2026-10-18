# The kept-land chance test: hand-crafted (_r9) beside AlphaEarth (_r9) beside rehearsal, pre-fix stands

Written by `odisha_script/odisha_keptland_chance_compare.py` from the chance test's result files
(`odisha_script/odisha_keptland_chance.py`). For each score: the observed value, the median of the
rotation null, the observed value's percentile in it, and the one-sided p after Holm over the five
tests of that analysis and set; a test passes at a Holm p of at most 0.05. The three drawing scores
are read against the unconditional null, the two labelling scores against the conditional one.
Numbers only: nothing is tested across sets.

## primary: the primary field types, every plot the join scores

| Score | hand-crafted (_r9): observed | chance median | percentile | Holm p | AlphaEarth (_r9): observed | chance median | percentile | Holm p | rehearsal, pre-fix stands: observed | chance median | percentile | Holm p |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 drawing: ARI, all plots | +0.0068 | +0.0069 | 46.9 | 1.000 | +0.0053 | +0.0064 | 26.3 | 1.000 | +0.0048 | +0.0068 | 13.1 | 1.000 |
| 2 drawing: ARI, stands of 2+ plots | +0.0277 | +0.0282 | 47.1 | 1.000 | +0.0229 | +0.0285 | 26.2 | 1.000 | +0.0179 | +0.0286 | 9.0 | 1.000 |
| 3 drawing: same-stand pair precision | +0.5290 | +0.5345 | 45.5 | 1.000 | +0.5130 | +0.5309 | 37.8 | 1.000 | +0.4692 | +0.5319 | 12.2 | 1.000 |
| 4 labelling: ARI, district mean | +0.0468 | +0.0561 | 32.7 | 1.000 | +0.0411 | +0.0417 | 48.6 | 1.000 | +0.0440 | +0.0488 | 40.5 | 1.000 |
| 5 labelling: far-apart gap | +0.0024 | +0.0106 | 36.7 | 1.000 | -0.0043 | +0.0074 | 29.6 | 1.000 | -0.0112 | +0.0037 | 23.5 | 1.000 |

Tests that pass after Holm: hand-crafted (_r9) 0 of 5; AlphaEarth (_r9) 0 of 5; rehearsal, pre-fix stands 0 of 5.

## S1: field type 0 (no trees) left out, same realisations

| Score | hand-crafted (_r9): observed | chance median | percentile | Holm p | AlphaEarth (_r9): observed | chance median | percentile | Holm p | rehearsal, pre-fix stands: observed | chance median | percentile | Holm p |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 drawing: ARI, all plots | +0.0050 | +0.0062 | 24.2 | 1.000 | +0.0044 | +0.0058 | 15.8 | 1.000 | +0.0046 | +0.0060 | 17.7 | 1.000 |
| 2 drawing: ARI, stands of 2+ plots | +0.0191 | +0.0253 | 19.6 | 1.000 | +0.0193 | +0.0255 | 20.8 | 1.000 | +0.0159 | +0.0254 | 9.6 | 1.000 |
| 3 drawing: same-stand pair precision | +0.5789 | +0.5806 | 48.4 | 1.000 | +0.5484 | +0.5797 | 29.0 | 1.000 | +0.5510 | +0.5783 | 30.5 | 1.000 |
| 4 labelling: ARI, district mean | +0.0566 | +0.0639 | 37.0 | 1.000 | +0.0567 | +0.0446 | 70.7 | 1.000 | +0.0512 | +0.0596 | 35.1 | 1.000 |
| 5 labelling: far-apart gap | +0.0264 | +0.0212 | 56.4 | 1.000 | +0.0022 | +0.0117 | 32.2 | 1.000 | +0.0093 | +0.0173 | 38.0 | 1.000 |

Tests that pass after Holm: hand-crafted (_r9) 0 of 5; AlphaEarth (_r9) 0 of 5; rehearsal, pre-fix stands 0 of 5.

## S2: four field types (odisha_phase3_0_field_types_k4.csv), same realisations

| Score | hand-crafted (_r9): observed | chance median | percentile | Holm p | AlphaEarth (_r9): observed | chance median | percentile | Holm p | rehearsal, pre-fix stands: observed | chance median | percentile | Holm p |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 drawing: ARI, all plots | +0.0048 | +0.0055 | 30.6 | 1.000 | +0.0051 | +0.0052 | 47.0 | 1.000 | +0.0036 | +0.0054 | 7.8 | 1.000 |
| 2 drawing: ARI, stands of 2+ plots | +0.0182 | +0.0219 | 29.8 | 1.000 | +0.0190 | +0.0218 | 34.3 | 1.000 | +0.0121 | +0.0222 | 5.0 | 1.000 |
| 3 drawing: same-stand pair precision | +0.6232 | +0.6444 | 33.3 | 1.000 | +0.6870 | +0.6441 | 79.6 | 1.000 | +0.5769 | +0.6420 | 9.4 | 1.000 |
| 4 labelling: ARI, district mean | +0.0221 | +0.0453 | 14.9 | 1.000 | +0.0340 | +0.0348 | 48.5 | 1.000 | +0.0125 | +0.0439 | 9.6 | 1.000 |
| 5 labelling: far-apart gap | -0.0017 | +0.0227 | 17.2 | 1.000 | -0.0057 | +0.0188 | 12.7 | 1.000 | -0.0141 | +0.0154 | 12.5 | 1.000 |

Tests that pass after Holm: hand-crafted (_r9) 0 of 5; AlphaEarth (_r9) 0 of 5; rehearsal, pre-fix stands 0 of 5.

## Check C1: the labelling mean without Kendujhar, on both sides

Beside the primary's score 4, outside the Holm correction, no pass or fail (`odisha_script/PHASE_KEPTLAND_AMENDMENT_chance_checks.md`); its p is the one-sided p.

| Check | hand-crafted (_r9): observed | chance median | percentile | p | AlphaEarth (_r9): observed | chance median | percentile | p | rehearsal, pre-fix stands: observed | chance median | percentile | p |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| C1: labelling ARI, district mean, Kendujhar left out | +0.0481 | +0.0566 | 34.5 | 0.655 | +0.0332 | +0.0418 | 31.3 | 0.687 | +0.0398 | +0.0487 | 32.2 | 0.678 |

## What each set ran on

| Set | Runs | Declared or rehearsal | Realisations | Seed name | Null built | Plots scored (primary, C1) | Realisations with fewer districts in the labelling mean |
|---|---|---|---|---|---|---|---|
| hand-crafted (_r9) | `odisha_v120_3ha_squares_angul_keptland_s1desc_r9`, `odisha_v120_3ha_squares_dhenkanal_keptland_s1desc_r9`, `odisha_v120_3ha_squares_kendujhar_keptland_s1desc_r9`, `odisha_v120_3ha_squares_koraput_keptland_s1desc_r9` | declared | 1999 | `v120_3ha_squares_keptland_s1desc` | yes | 264, 257 | 411 |
| AlphaEarth (_r9) | `odisha_alphaearth_3ha_squares_angul_keptland_r9`, `odisha_alphaearth_3ha_squares_dhenkanal_keptland_r9`, `odisha_alphaearth_3ha_squares_kendujhar_keptland_r9`, `odisha_alphaearth_3ha_squares_koraput_keptland_r9` | declared | 1999 | `alphaearth_3ha_squares_keptland` | yes | 264, 257 | 451 |
| rehearsal, pre-fix stands | `odisha_v120_3ha_squares_angul_keptland_s1desc`, `odisha_v120_3ha_squares_dhenkanal_keptland_s1desc`, `odisha_v120_3ha_squares_kendujhar_keptland_s1desc`, `odisha_v120_3ha_squares_koraput_keptland_s1desc` | rehearsal | 1999 | `v120_3ha_squares_keptland_s1desc` | yes | 264, 257 | 411 |

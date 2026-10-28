# The kept-land chance test: hand-crafted, 3 ha (R3) beside AlphaEarth, 3 ha (R3)

Written by `odisha_script/odisha_keptland_chance_compare.py` from the chance test's result files
(`odisha_script/odisha_keptland_chance.py`). For each score: the observed value, the median of the
rotation null, the observed value's percentile in it, and the one-sided p after Holm over the five
tests of that analysis and set; a test passes at a Holm p of at most 0.05. The three drawing scores
are read against the unconditional null, the two labelling scores against the conditional one.
Numbers only: nothing is tested across sets.

## primary: the primary field types, every plot the join scores

| Score | hand-crafted, 3 ha (R3): observed | chance median | percentile | Holm p | AlphaEarth, 3 ha (R3): observed | chance median | percentile | Holm p |
|---|---|---|---|---|---|---|---|---|
| 1 drawing: ARI, all plots | +0.0076 | +0.0069 | 62.6 | 1.000 | +0.0053 | +0.0064 | 25.9 | 1.000 |
| 2 drawing: ARI, stands of 2+ plots | +0.0269 | +0.0285 | 42.7 | 1.000 | +0.0229 | +0.0284 | 25.8 | 1.000 |
| 3 drawing: same-stand pair precision | +0.5580 | +0.5342 | 66.7 | 1.000 | +0.5130 | +0.5316 | 37.4 | 1.000 |
| 4 labelling: ARI, district mean | +0.0193 | +0.0326 | 26.2 | 1.000 | +0.0466 | +0.0618 | 22.9 | 1.000 |
| 5 labelling: far-apart gap | -0.0159 | +0.0155 | 10.7 | 1.000 | -0.0012 | +0.0241 | 16.0 | 1.000 |

Tests that pass after Holm: hand-crafted, 3 ha (R3) 0 of 5; AlphaEarth, 3 ha (R3) 0 of 5.

## S1: field type 0 (no trees) left out, same realisations

| Score | hand-crafted, 3 ha (R3): observed | chance median | percentile | Holm p | AlphaEarth, 3 ha (R3): observed | chance median | percentile | Holm p |
|---|---|---|---|---|---|---|---|---|
| 1 drawing: ARI, all plots | +0.0057 | +0.0062 | 35.8 | 1.000 | +0.0044 | +0.0058 | 15.6 | 1.000 |
| 2 drawing: ARI, stands of 2+ plots | +0.0195 | +0.0254 | 21.3 | 1.000 | +0.0193 | +0.0255 | 20.1 | 1.000 |
| 3 drawing: same-stand pair precision | +0.6020 | +0.5824 | 62.6 | 1.000 | +0.5484 | +0.5789 | 28.9 | 1.000 |
| 4 labelling: ARI, district mean | +0.0373 | +0.0449 | 36.2 | 1.000 | +0.0543 | +0.0617 | 38.1 | 1.000 |
| 5 labelling: far-apart gap | +0.0012 | +0.0359 | 12.4 | 1.000 | +0.0074 | +0.0241 | 26.4 | 1.000 |

Tests that pass after Holm: hand-crafted, 3 ha (R3) 0 of 5; AlphaEarth, 3 ha (R3) 0 of 5.

## S2: four field types (odisha_phase3_0_field_types_k4.csv), same realisations

| Score | hand-crafted, 3 ha (R3): observed | chance median | percentile | Holm p | AlphaEarth, 3 ha (R3): observed | chance median | percentile | Holm p |
|---|---|---|---|---|---|---|---|---|
| 1 drawing: ARI, all plots | +0.0054 | +0.0055 | 45.2 | 1.000 | +0.0051 | +0.0051 | 46.9 | 1.000 |
| 2 drawing: ARI, stands of 2+ plots | +0.0171 | +0.0216 | 24.1 | 1.000 | +0.0190 | +0.0218 | 33.5 | 1.000 |
| 3 drawing: same-stand pair precision | +0.6522 | +0.6471 | 53.7 | 1.000 | +0.6870 | +0.6442 | 79.1 | 1.000 |
| 4 labelling: ARI, district mean | +0.0038 | +0.0174 | 32.3 | 1.000 | +0.0355 | +0.0496 | 27.3 | 1.000 |
| 5 labelling: far-apart gap | -0.0251 | +0.0269 | 11.1 | 1.000 | -0.0053 | +0.0274 | 11.8 | 1.000 |

Tests that pass after Holm: hand-crafted, 3 ha (R3) 0 of 5; AlphaEarth, 3 ha (R3) 0 of 5.

## Check C1: the labelling mean without Kendujhar, on both sides

Beside the primary's score 4, outside the Holm correction, no pass or fail (`odisha_script/PHASE_KEPTLAND_AMENDMENT_chance_checks.md`); its p is the one-sided p.

| Check | hand-crafted, 3 ha (R3): observed | chance median | percentile | p | AlphaEarth, 3 ha (R3): observed | chance median | percentile | p |
|---|---|---|---|---|---|---|---|---|
| C1: labelling ARI, district mean, Kendujhar left out | +0.0181 | +0.0328 | 23.8 | 0.762 | +0.0478 | +0.0622 | 23.9 | 0.761 |

## What each set ran on

| Set | Runs | Declared or rehearsal | Realisations | Seed name | Null built | Plots scored (primary, C1) | Realisations with fewer districts in the labelling mean |
|---|---|---|---|---|---|---|---|
| hand-crafted, 3 ha (R3) | `odisha_v120_3ha_squares_angul_keptland_s1desc_r14`, `odisha_v120_3ha_squares_dhenkanal_keptland_s1desc_r14`, `odisha_v120_3ha_squares_kendujhar_keptland_s1desc_r14`, `odisha_v120_3ha_squares_koraput_keptland_s1desc_r14` | declared | 1999 | `v120_3ha_squares_keptland_s1desc` | yes | 264, 257 | 411 |
| AlphaEarth, 3 ha (R3) | `odisha_alphaearth_3ha_squares_angul_keptland_r14`, `odisha_alphaearth_3ha_squares_dhenkanal_keptland_r14`, `odisha_alphaearth_3ha_squares_kendujhar_keptland_r14`, `odisha_alphaearth_3ha_squares_koraput_keptland_r14` | declared | 1999 | `alphaearth_3ha_squares_keptland` | yes | 264, 257 | 451 |

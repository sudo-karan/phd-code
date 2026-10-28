# The kept-land chance test: hand-crafted, 3 ha (_r9) beside hand-crafted, 3 ha (R3)

Written by `odisha_script/odisha_keptland_chance_compare.py` from the chance test's result files
(`odisha_script/odisha_keptland_chance.py`). For each score: the observed value, the median of the
rotation null, the observed value's percentile in it, and the one-sided p after Holm over the five
tests of that analysis and set; a test passes at a Holm p of at most 0.05. The three drawing scores
are read against the unconditional null, the two labelling scores against the conditional one.
Numbers only: nothing is tested across sets.

## primary: the primary field types, every plot the join scores

| Score | hand-crafted, 3 ha (_r9): observed | chance median | percentile | Holm p | hand-crafted, 3 ha (R3): observed | chance median | percentile | Holm p |
|---|---|---|---|---|---|---|---|---|
| 1 drawing: ARI, all plots | +0.0068 | +0.0069 | 46.9 | 1.000 | +0.0076 | +0.0069 | 62.6 | 1.000 |
| 2 drawing: ARI, stands of 2+ plots | +0.0277 | +0.0282 | 47.1 | 1.000 | +0.0269 | +0.0285 | 42.7 | 1.000 |
| 3 drawing: same-stand pair precision | +0.5290 | +0.5345 | 45.5 | 1.000 | +0.5580 | +0.5342 | 66.7 | 1.000 |
| 4 labelling: ARI, district mean | +0.0468 | +0.0561 | 32.7 | 1.000 | +0.0193 | +0.0326 | 26.2 | 1.000 |
| 5 labelling: far-apart gap | +0.0024 | +0.0106 | 36.7 | 1.000 | -0.0159 | +0.0155 | 10.7 | 1.000 |

Tests that pass after Holm: hand-crafted, 3 ha (_r9) 0 of 5; hand-crafted, 3 ha (R3) 0 of 5.

## S1: field type 0 (no trees) left out, same realisations

| Score | hand-crafted, 3 ha (_r9): observed | chance median | percentile | Holm p | hand-crafted, 3 ha (R3): observed | chance median | percentile | Holm p |
|---|---|---|---|---|---|---|---|---|
| 1 drawing: ARI, all plots | +0.0050 | +0.0062 | 24.2 | 1.000 | +0.0057 | +0.0062 | 35.8 | 1.000 |
| 2 drawing: ARI, stands of 2+ plots | +0.0191 | +0.0253 | 19.6 | 1.000 | +0.0195 | +0.0254 | 21.3 | 1.000 |
| 3 drawing: same-stand pair precision | +0.5789 | +0.5806 | 48.4 | 1.000 | +0.6020 | +0.5824 | 62.6 | 1.000 |
| 4 labelling: ARI, district mean | +0.0566 | +0.0639 | 37.0 | 1.000 | +0.0373 | +0.0449 | 36.2 | 1.000 |
| 5 labelling: far-apart gap | +0.0264 | +0.0212 | 56.4 | 1.000 | +0.0012 | +0.0359 | 12.4 | 1.000 |

Tests that pass after Holm: hand-crafted, 3 ha (_r9) 0 of 5; hand-crafted, 3 ha (R3) 0 of 5.

## S2: four field types (odisha_phase3_0_field_types_k4.csv), same realisations

| Score | hand-crafted, 3 ha (_r9): observed | chance median | percentile | Holm p | hand-crafted, 3 ha (R3): observed | chance median | percentile | Holm p |
|---|---|---|---|---|---|---|---|---|
| 1 drawing: ARI, all plots | +0.0048 | +0.0055 | 30.6 | 1.000 | +0.0054 | +0.0055 | 45.2 | 1.000 |
| 2 drawing: ARI, stands of 2+ plots | +0.0182 | +0.0219 | 29.8 | 1.000 | +0.0171 | +0.0216 | 24.1 | 1.000 |
| 3 drawing: same-stand pair precision | +0.6232 | +0.6444 | 33.3 | 1.000 | +0.6522 | +0.6471 | 53.7 | 1.000 |
| 4 labelling: ARI, district mean | +0.0221 | +0.0453 | 14.9 | 1.000 | +0.0038 | +0.0174 | 32.3 | 1.000 |
| 5 labelling: far-apart gap | -0.0017 | +0.0227 | 17.2 | 1.000 | -0.0251 | +0.0269 | 11.1 | 1.000 |

Tests that pass after Holm: hand-crafted, 3 ha (_r9) 0 of 5; hand-crafted, 3 ha (R3) 0 of 5.

## Check C1: the labelling mean without Kendujhar, on both sides

Beside the primary's score 4, outside the Holm correction, no pass or fail (`odisha_script/PHASE_KEPTLAND_AMENDMENT_chance_checks.md`); its p is the one-sided p.

| Check | hand-crafted, 3 ha (_r9): observed | chance median | percentile | p | hand-crafted, 3 ha (R3): observed | chance median | percentile | p |
|---|---|---|---|---|---|---|---|---|
| C1: labelling ARI, district mean, Kendujhar left out | +0.0481 | +0.0566 | 34.5 | 0.655 | +0.0181 | +0.0328 | 23.8 | 0.762 |

## What each set ran on

| Set | Runs | Declared or rehearsal | Realisations | Seed name | Null built | Plots scored (primary, C1) | Realisations with fewer districts in the labelling mean |
|---|---|---|---|---|---|---|---|
| hand-crafted, 3 ha (_r9) | `odisha_v120_3ha_squares_angul_keptland_s1desc_r9`, `odisha_v120_3ha_squares_dhenkanal_keptland_s1desc_r9`, `odisha_v120_3ha_squares_kendujhar_keptland_s1desc_r9`, `odisha_v120_3ha_squares_koraput_keptland_s1desc_r9` | declared | 1999 | `v120_3ha_squares_keptland_s1desc` | yes | 264, 257 | 411 |
| hand-crafted, 3 ha (R3) | `odisha_v120_3ha_squares_angul_keptland_s1desc_r14`, `odisha_v120_3ha_squares_dhenkanal_keptland_s1desc_r14`, `odisha_v120_3ha_squares_kendujhar_keptland_s1desc_r14`, `odisha_v120_3ha_squares_koraput_keptland_s1desc_r14` | declared | 1999 | `v120_3ha_squares_keptland_s1desc` | yes | 264, 257 | 411 |

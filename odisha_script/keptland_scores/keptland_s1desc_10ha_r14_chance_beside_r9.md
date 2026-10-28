# The kept-land chance test: hand-crafted, 10 ha (_r9) beside hand-crafted, 10 ha (R3)

Written by `odisha_script/odisha_keptland_chance_compare.py` from the chance test's result files
(`odisha_script/odisha_keptland_chance.py`). For each score: the observed value, the median of the
rotation null, the observed value's percentile in it, and the one-sided p after Holm over the five
tests of that analysis and set; a test passes at a Holm p of at most 0.05. The three drawing scores
are read against the unconditional null, the two labelling scores against the conditional one.
Numbers only: nothing is tested across sets.

## primary: the primary field types, every plot the join scores

| Score | hand-crafted, 10 ha (_r9): observed | chance median | percentile | Holm p | hand-crafted, 10 ha (R3): observed | chance median | percentile | Holm p |
|---|---|---|---|---|---|---|---|---|
| 1 drawing: ARI, all plots | +0.0146 | +0.0132 | 66.4 | 1.000 | +0.0162 | +0.0139 | 76.0 | 1.000 |
| 2 drawing: ARI, stands of 2+ plots | +0.0319 | +0.0305 | 56.5 | 1.000 | +0.0331 | +0.0313 | 57.9 | 1.000 |
| 3 drawing: same-stand pair precision | +0.5108 | +0.5337 | 30.9 | 1.000 | +0.5487 | +0.5362 | 61.2 | 1.000 |
| 4 labelling: ARI, district mean | +0.0572 | +0.0638 | 37.0 | 1.000 | +0.0503 | +0.0537 | 43.7 | 1.000 |
| 5 labelling: far-apart gap | +0.0122 | +0.0156 | 45.4 | 1.000 | -0.0217 | +0.0204 | 11.8 | 1.000 |

Tests that pass after Holm: hand-crafted, 10 ha (_r9) 0 of 5; hand-crafted, 10 ha (R3) 0 of 5.

## S1: field type 0 (no trees) left out, same realisations

| Score | hand-crafted, 10 ha (_r9): observed | chance median | percentile | Holm p | hand-crafted, 10 ha (R3): observed | chance median | percentile | Holm p |
|---|---|---|---|---|---|---|---|---|
| 1 drawing: ARI, all plots | +0.0137 | +0.0123 | 66.2 | 1.000 | +0.0147 | +0.0129 | 72.8 | 1.000 |
| 2 drawing: ARI, stands of 2+ plots | +0.0287 | +0.0282 | 53.2 | 1.000 | +0.0296 | +0.0291 | 53.0 | 1.000 |
| 3 drawing: same-stand pair precision | +0.6140 | +0.5823 | 76.5 | 1.000 | +0.6016 | +0.5804 | 67.4 | 1.000 |
| 4 labelling: ARI, district mean | +0.0666 | +0.0732 | 38.9 | 1.000 | +0.0669 | +0.0655 | 51.9 | 1.000 |
| 5 labelling: far-apart gap | +0.0345 | +0.0302 | 54.6 | 1.000 | -0.0032 | +0.0414 | 13.5 | 1.000 |

Tests that pass after Holm: hand-crafted, 10 ha (_r9) 0 of 5; hand-crafted, 10 ha (R3) 0 of 5.

## S2: four field types (odisha_phase3_0_field_types_k4.csv), same realisations

| Score | hand-crafted, 10 ha (_r9): observed | chance median | percentile | Holm p | hand-crafted, 10 ha (R3): observed | chance median | percentile | Holm p |
|---|---|---|---|---|---|---|---|---|
| 1 drawing: ARI, all plots | +0.0101 | +0.0106 | 41.6 | 1.000 | +0.0111 | +0.0109 | 52.2 | 1.000 |
| 2 drawing: ARI, stands of 2+ plots | +0.0231 | +0.0244 | 40.6 | 1.000 | +0.0241 | +0.0254 | 41.9 | 1.000 |
| 3 drawing: same-stand pair precision | +0.6000 | +0.6439 | 14.6 | 1.000 | +0.6331 | +0.6429 | 39.8 | 1.000 |
| 4 labelling: ARI, district mean | +0.0288 | +0.0582 | 11.5 | 1.000 | +0.0375 | +0.0346 | 53.8 | 1.000 |
| 5 labelling: far-apart gap | +0.0177 | +0.0307 | 34.8 | 1.000 | -0.0230 | +0.0287 | 18.2 | 1.000 |

Tests that pass after Holm: hand-crafted, 10 ha (_r9) 0 of 5; hand-crafted, 10 ha (R3) 0 of 5.

## Check C1: the labelling mean without Kendujhar, on both sides

Beside the primary's score 4, outside the Holm correction, no pass or fail (`odisha_script/PHASE_KEPTLAND_AMENDMENT_chance_checks.md`); its p is the one-sided p.

| Check | hand-crafted, 10 ha (_r9): observed | chance median | percentile | p | hand-crafted, 10 ha (R3): observed | chance median | percentile | p |
|---|---|---|---|---|---|---|---|---|
| C1: labelling ARI, district mean, Kendujhar left out | +0.0588 | +0.0638 | 40.4 | 0.597 | +0.0500 | +0.0542 | 42.4 | 0.576 |

## What each set ran on

| Set | Runs | Declared or rehearsal | Realisations | Seed name | Null built | Plots scored (primary, C1) | Realisations with fewer districts in the labelling mean |
|---|---|---|---|---|---|---|---|
| hand-crafted, 10 ha (_r9) | `odisha_v120_10ha_squares_angul_keptland_s1desc_r9`, `odisha_v120_10ha_squares_dhenkanal_keptland_s1desc_r9`, `odisha_v120_10ha_squares_kendujhar_keptland_s1desc_r9`, `odisha_v120_10ha_squares_koraput_keptland_s1desc_r9` | declared | 1999 | `v120_10ha_squares_keptland_s1desc` | yes | 264, 257 | 404 |
| hand-crafted, 10 ha (R3) | `odisha_v120_10ha_squares_angul_keptland_s1desc_r14`, `odisha_v120_10ha_squares_dhenkanal_keptland_s1desc_r14`, `odisha_v120_10ha_squares_kendujhar_keptland_s1desc_r14`, `odisha_v120_10ha_squares_koraput_keptland_s1desc_r14` | declared | 1999 | `v120_10ha_squares_keptland_s1desc` | yes | 264, 257 | 404 |

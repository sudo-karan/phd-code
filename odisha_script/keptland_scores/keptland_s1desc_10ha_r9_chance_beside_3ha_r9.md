# The kept-land chance test: hand-crafted, 3 ha (_r9) beside hand-crafted, 10 ha

Written by `odisha_script/odisha_keptland_chance_compare.py` from the chance test's result files
(`odisha_script/odisha_keptland_chance.py`). For each score: the observed value, the median of the
rotation null, the observed value's percentile in it, and the one-sided p after Holm over the five
tests of that analysis and set; a test passes at a Holm p of at most 0.05. The three drawing scores
are read against the unconditional null, the two labelling scores against the conditional one.
Numbers only: nothing is tested across sets.

## primary: the primary field types, every plot the join scores

| Score | hand-crafted, 3 ha (_r9): observed | chance median | percentile | Holm p | hand-crafted, 10 ha: observed | chance median | percentile | Holm p |
|---|---|---|---|---|---|---|---|---|
| 1 drawing: ARI, all plots | +0.0068 | +0.0069 | 46.9 | 1.000 | +0.0146 | +0.0132 | 66.4 | 1.000 |
| 2 drawing: ARI, stands of 2+ plots | +0.0277 | +0.0282 | 47.1 | 1.000 | +0.0319 | +0.0305 | 56.5 | 1.000 |
| 3 drawing: same-stand pair precision | +0.5290 | +0.5345 | 45.5 | 1.000 | +0.5108 | +0.5337 | 30.9 | 1.000 |
| 4 labelling: ARI, district mean | +0.0468 | +0.0561 | 32.7 | 1.000 | +0.0572 | +0.0638 | 37.0 | 1.000 |
| 5 labelling: far-apart gap | +0.0024 | +0.0106 | 36.7 | 1.000 | +0.0122 | +0.0156 | 45.4 | 1.000 |

Tests that pass after Holm: hand-crafted, 3 ha (_r9) 0 of 5; hand-crafted, 10 ha 0 of 5.

## S1: field type 0 (no trees) left out, same realisations

| Score | hand-crafted, 3 ha (_r9): observed | chance median | percentile | Holm p | hand-crafted, 10 ha: observed | chance median | percentile | Holm p |
|---|---|---|---|---|---|---|---|---|
| 1 drawing: ARI, all plots | +0.0050 | +0.0062 | 24.2 | 1.000 | +0.0137 | +0.0123 | 66.2 | 1.000 |
| 2 drawing: ARI, stands of 2+ plots | +0.0191 | +0.0253 | 19.6 | 1.000 | +0.0287 | +0.0282 | 53.2 | 1.000 |
| 3 drawing: same-stand pair precision | +0.5789 | +0.5806 | 48.4 | 1.000 | +0.6140 | +0.5823 | 76.5 | 1.000 |
| 4 labelling: ARI, district mean | +0.0566 | +0.0639 | 37.0 | 1.000 | +0.0666 | +0.0732 | 38.9 | 1.000 |
| 5 labelling: far-apart gap | +0.0264 | +0.0212 | 56.4 | 1.000 | +0.0345 | +0.0302 | 54.6 | 1.000 |

Tests that pass after Holm: hand-crafted, 3 ha (_r9) 0 of 5; hand-crafted, 10 ha 0 of 5.

## S2: four field types (odisha_phase3_0_field_types_k4.csv), same realisations

| Score | hand-crafted, 3 ha (_r9): observed | chance median | percentile | Holm p | hand-crafted, 10 ha: observed | chance median | percentile | Holm p |
|---|---|---|---|---|---|---|---|---|
| 1 drawing: ARI, all plots | +0.0048 | +0.0055 | 30.6 | 1.000 | +0.0101 | +0.0106 | 41.6 | 1.000 |
| 2 drawing: ARI, stands of 2+ plots | +0.0182 | +0.0219 | 29.8 | 1.000 | +0.0231 | +0.0244 | 40.6 | 1.000 |
| 3 drawing: same-stand pair precision | +0.6232 | +0.6444 | 33.3 | 1.000 | +0.6000 | +0.6439 | 14.6 | 1.000 |
| 4 labelling: ARI, district mean | +0.0221 | +0.0453 | 14.9 | 1.000 | +0.0288 | +0.0582 | 11.5 | 1.000 |
| 5 labelling: far-apart gap | -0.0017 | +0.0227 | 17.2 | 1.000 | +0.0177 | +0.0307 | 34.8 | 1.000 |

Tests that pass after Holm: hand-crafted, 3 ha (_r9) 0 of 5; hand-crafted, 10 ha 0 of 5.

## Check C1: the labelling mean without Kendujhar, on both sides

Beside the primary's score 4, outside the Holm correction, no pass or fail (`odisha_script/PHASE_KEPTLAND_AMENDMENT_chance_checks.md`); its p is the one-sided p.

| Check | hand-crafted, 3 ha (_r9): observed | chance median | percentile | p | hand-crafted, 10 ha: observed | chance median | percentile | p |
|---|---|---|---|---|---|---|---|---|
| C1: labelling ARI, district mean, Kendujhar left out | +0.0481 | +0.0566 | 34.5 | 0.655 | +0.0588 | +0.0638 | 40.4 | 0.597 |

## What each set ran on

| Set | Runs | Declared or rehearsal | Realisations | Seed name | Null built | Plots scored (primary, C1) | Realisations with fewer districts in the labelling mean |
|---|---|---|---|---|---|---|---|
| hand-crafted, 3 ha (_r9) | `odisha_v120_3ha_squares_angul_keptland_s1desc_r9`, `odisha_v120_3ha_squares_dhenkanal_keptland_s1desc_r9`, `odisha_v120_3ha_squares_kendujhar_keptland_s1desc_r9`, `odisha_v120_3ha_squares_koraput_keptland_s1desc_r9` | declared | 1999 | `v120_3ha_squares_keptland_s1desc` | yes | 264, 257 | 411 |
| hand-crafted, 10 ha | `odisha_v120_10ha_squares_angul_keptland_s1desc_r9`, `odisha_v120_10ha_squares_dhenkanal_keptland_s1desc_r9`, `odisha_v120_10ha_squares_kendujhar_keptland_s1desc_r9`, `odisha_v120_10ha_squares_koraput_keptland_s1desc_r9` | declared | 1999 | `v120_10ha_squares_keptland_s1desc` | yes | 264, 257 | 404 |

## Note added 20 Oct 2026 (round 13, review A1, A4, A5, A6, B13, B14, B16, B17 and B18)

The numbers above are as first written. Both sets are on hand-crafted stands from before the round
13 fixes (`docs/handoff/2026-10-20-round13.md`, Done), and so are the differences between them. The
runs' inputs were affected by A1, A4 and A5, and B13 and the merge and clustering fixes B14, B16,
B17 and B18 reach them too. The runs of both sizes are to be re-run (roadmap R3). How far any fix
moves a score, a null, a p or a difference was not measured; it needs Earth Engine. The note at the
end of each chance file says more (`keptland_s1desc_r9_chance.txt`,
`keptland_s1desc_10ha_r9_chance.txt`). `README.md` here lists every file noted. No number here is
changed.

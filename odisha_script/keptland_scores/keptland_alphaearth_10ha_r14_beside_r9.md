# The kept-land field check: AlphaEarth, 10 ha (R3) against AlphaEarth, 10 ha (_r9)

Written by `odisha_script/odisha_keptland_compare.py` from the committed scores files and run
records. Numbers only: as the declaration fixes, no chance test is run and no difference is
tested (`odisha_script/PHASE_KEPTLAND_PREDECLARED.md`).

## The five scores

| Analysis | Score | AlphaEarth, 10 ha (_r9) | AlphaEarth, 10 ha (R3) | R3 minus _r9 |
|---|---|---|---|---|
| primary | 1 drawing: ARI, all plots | +0.0170 | +0.0172 | +0.0002 |
| primary | 2 drawing: ARI, stands of 2+ plots | +0.0305 | +0.0302 | -0.0002 |
| primary | 3 drawing: same-stand pair precision | +0.5729 | +0.5587 | -0.0142 |
| primary | 4 labelling: ARI, district mean | +0.0507 | +0.0546 | +0.0039 |
| primary | 5 labelling: far-apart gap | -0.0060 | +0.0021 | +0.0082 |
| primary | plots scored | 264 | 264 | +0 |
| S1 | 1 drawing: ARI, all plots | +0.0145 | +0.0148 | +0.0003 |
| S1 | 2 drawing: ARI, stands of 2+ plots | +0.0256 | +0.0256 | -0.0000 |
| S1 | 3 drawing: same-stand pair precision | +0.6032 | +0.6031 | -0.0001 |
| S1 | 4 labelling: ARI, district mean | +0.0570 | +0.0692 | +0.0123 |
| S1 | 5 labelling: far-apart gap | +0.0014 | +0.0284 | +0.0270 |
| S1 | plots scored | 248 | 248 | +0 |
| S2 | 1 drawing: ARI, all plots | +0.0114 | +0.0117 | +0.0003 |
| S2 | 2 drawing: ARI, stands of 2+ plots | +0.0215 | +0.0216 | +0.0001 |
| S2 | 3 drawing: same-stand pair precision | +0.6508 | +0.6413 | -0.0096 |
| S2 | 4 labelling: ARI, district mean | +0.0319 | +0.0033 | -0.0286 |
| S2 | 5 labelling: far-apart gap | -0.0138 | -0.0101 | +0.0037 |
| S2 | plots scored | 264 | 264 | +0 |
| covered_only | 1 drawing: ARI, all plots | +0.0173 | +0.0174 | +0.0001 |
| covered_only | 2 drawing: ARI, stands of 2+ plots | +0.0305 | +0.0301 | -0.0004 |
| covered_only | 3 drawing: same-stand pair precision | +0.5704 | +0.5603 | -0.0101 |
| covered_only | 4 labelling: ARI, district mean | +0.0465 | +0.0524 | +0.0058 |
| covered_only | 5 labelling: far-apart gap | -0.0118 | -0.0026 | +0.0092 |
| covered_only | plots scored | 252 | 252 | +0 |
| box_runs (the 13 Oct box stands: a comparison, not a declared score) | 1 drawing: ARI, all plots | +0.0051 | +0.0051 | +0.0000 |
| box_runs (the 13 Oct box stands: a comparison, not a declared score) | 2 drawing: ARI, stands of 2+ plots | +0.0225 | +0.0225 | +0.0000 |
| box_runs (the 13 Oct box stands: a comparison, not a declared score) | 3 drawing: same-stand pair precision | +0.5185 | +0.5185 | +0.0000 |
| box_runs (the 13 Oct box stands: a comparison, not a declared score) | 4 labelling: ARI, district mean | +0.0504 | +0.0504 | +0.0000 |
| box_runs (the 13 Oct box stands: a comparison, not a declared score) | 5 labelling: far-apart gap | -0.0165 | -0.0165 | +0.0000 |
| box_runs (the 13 Oct box stands: a comparison, not a declared score) | plots scored | 264 | 264 | +0 |

## How the plots join

| District | Inside the boxes | On a stand (old, new) | By the 30 m rule (old, new) | Left out (old, new) |
|---|---|---|---|---|
| angul | 39 | 37, 37 | 2, 2 | 0, 0 |
| dhenkanal | 75 | 72, 72 | 2, 2 | 1, 1 |
| kendujhar | 8 | 7, 7 | 0, 0 | 1, 1 |
| koraput | 145 | 136, 136 | 8, 8 | 1, 1 |
| all | 267 | 252, 252 | 12, 12 | 3, 3 |

## Stand counts, from the run records

| Run | Superpixels (old, new) | Stands (old, new) | Stand polygons (old, new) | Stands below the minimum area (old, new) | Superpixel polygons (old, new) | Same-type regions (old, new) |
|---|---|---|---|---|---|---|
| angul | 466, 464 | 129, 127 | 127, 127 | 54, 53 | 464, 464 | 60, 60 |
| dhenkanal | 1119, 1114 | 334, 328 | 329, 328 | 151, 146 | 1115, 1115 | 104, 105 |
| kendujhar | 1088, 1086 | 352, 350 | 350, 350 | 145, 143 | 1087, 1087 | 94, 91 |
| koraput | 3332, 3327 | 943, 938 | 940, 940 | 306, 301 | 3330, 3330 | 291, 268 |

## Labelling ARI by district (primary analysis)

| District | AlphaEarth, 10 ha (_r9) (n) | AlphaEarth, 10 ha (R3) (n) |
|---|---|---|
| ANGUL | +0.0733 (39) | +0.1482 (39) |
| DHENKANAL | +0.1724 (74) | +0.1541 (74) |
| KENDUJHAR | +0.0000 (7) | +0.0000 (7) |
| KORAPUT | -0.0155 (144) | -0.0192 (144) |

## Inputs: each scores file's stand layers, by SHA-256

| Scores file | Run | SHA-256 |
|---|---|---|
| AlphaEarth, 10 ha (_r9) | `odisha_alphaearth_10ha_squares_angul_keptland_r9` | `dedcacf09be04e03aaa1c58b7e04a3b7085d3ef1f4000eba763cfc3822b3bc90` |
| AlphaEarth, 10 ha (_r9) | `odisha_alphaearth_10ha_squares_dhenkanal_keptland_r9` | `25f9c7fafc7e917753c55c39155c4459aeebe7b916b415dd5bc9a5243af45164` |
| AlphaEarth, 10 ha (_r9) | `odisha_alphaearth_10ha_squares_kendujhar_keptland_r9` | `77797f387a72ec59a196e4187b65c942c519e9b5f1ba18f401252404d6510f1d` |
| AlphaEarth, 10 ha (_r9) | `odisha_alphaearth_10ha_squares_koraput_keptland_r9` | `9598b423c76b2a296380dc45cfc5d683f9347c8a7e09155d8cde7326679d35f7` |
| AlphaEarth, 10 ha (_r9) | `odisha_v120_3ha_squares_angul` | `8f9eb3efd28df919a3c037256851f95e817e799b843f7a4cd19d67d1ce8dcb06` |
| AlphaEarth, 10 ha (_r9) | `odisha_v120_3ha_squares_dhenkanal` | `a2afbc6481abb455c6d5d4a4698ff4d335541895796012acab4e9364d2ffb771` |
| AlphaEarth, 10 ha (_r9) | `odisha_v120_3ha_squares_kendujhar` | `5d2b1d2d61d115bd18214931027a5c5967bfbe78f91f9c2ffb5b5ef42fb8615e` |
| AlphaEarth, 10 ha (_r9) | `odisha_v120_3ha_squares_koraput` | `6d9ebeb5689219d1ef86722c8479a4465f8c18f68e470ff5ed5555024f089fc1` |
| AlphaEarth, 10 ha (R3) | `odisha_alphaearth_10ha_squares_angul_keptland_r14` | `fb63be17571d9179815d671c9d7ed45ff0f8faccc068cdfefac5d4b320499949` |
| AlphaEarth, 10 ha (R3) | `odisha_alphaearth_10ha_squares_dhenkanal_keptland_r14` | `2d7c491debe7e9b4d2cd8232ea05930551a6785216476c73bebd85fbcc4ef65a` |
| AlphaEarth, 10 ha (R3) | `odisha_alphaearth_10ha_squares_kendujhar_keptland_r14` | `70bfe8e3c84fa35422b8c67f8a45bc16b0c1d93a7db822b24c564421eedf255c` |
| AlphaEarth, 10 ha (R3) | `odisha_alphaearth_10ha_squares_koraput_keptland_r14` | `76dd33c66bdb85dbec46476650c5a1ce1957baff015e60fc4ca4faf492b2fca0` |
| AlphaEarth, 10 ha (R3) | `odisha_v120_3ha_squares_angul` | `8f9eb3efd28df919a3c037256851f95e817e799b843f7a4cd19d67d1ce8dcb06` |
| AlphaEarth, 10 ha (R3) | `odisha_v120_3ha_squares_dhenkanal` | `a2afbc6481abb455c6d5d4a4698ff4d335541895796012acab4e9364d2ffb771` |
| AlphaEarth, 10 ha (R3) | `odisha_v120_3ha_squares_kendujhar` | `5d2b1d2d61d115bd18214931027a5c5967bfbe78f91f9c2ffb5b5ef42fb8615e` |
| AlphaEarth, 10 ha (R3) | `odisha_v120_3ha_squares_koraput` | `6d9ebeb5689219d1ef86722c8479a4465f8c18f68e470ff5ed5555024f089fc1` |

## The plots each side scores

- scored (the join with the 30 m rule): 264 (AlphaEarth, 10 ha (_r9)), 264 (AlphaEarth, 10 ha (R3)), 264 in both.
  - only AlphaEarth, 10 ha (_r9): none
  - only AlphaEarth, 10 ha (R3): none
- covered by a stand (no 30 m rule): 252 (AlphaEarth, 10 ha (_r9)), 252 (AlphaEarth, 10 ha (R3)), 252 in both.
  - only AlphaEarth, 10 ha (_r9): none
  - only AlphaEarth, 10 ha (R3): none

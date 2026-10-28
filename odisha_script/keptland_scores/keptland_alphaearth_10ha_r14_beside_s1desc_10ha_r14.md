# The kept-land field check: AlphaEarth, 10 ha (R3) against hand-crafted, 10 ha (R3)

Written by `odisha_script/odisha_keptland_compare.py` from the committed scores files and run
records. Numbers only: as the declaration fixes, no chance test is run and no difference is
tested (`odisha_script/PHASE_KEPTLAND_PREDECLARED.md`).

## The five scores

| Analysis | Score | hand-crafted, 10 ha (R3) | AlphaEarth, 10 ha (R3) | AlphaEarth minus hand-crafted |
|---|---|---|---|---|
| primary | 1 drawing: ARI, all plots | +0.0162 | +0.0172 | +0.0010 |
| primary | 2 drawing: ARI, stands of 2+ plots | +0.0331 | +0.0302 | -0.0028 |
| primary | 3 drawing: same-stand pair precision | +0.5487 | +0.5587 | +0.0100 |
| primary | 4 labelling: ARI, district mean | +0.0503 | +0.0546 | +0.0043 |
| primary | 5 labelling: far-apart gap | -0.0217 | +0.0021 | +0.0239 |
| primary | plots scored | 264 | 264 | +0 |
| S1 | 1 drawing: ARI, all plots | +0.0147 | +0.0148 | +0.0001 |
| S1 | 2 drawing: ARI, stands of 2+ plots | +0.0296 | +0.0256 | -0.0040 |
| S1 | 3 drawing: same-stand pair precision | +0.6016 | +0.6031 | +0.0016 |
| S1 | 4 labelling: ARI, district mean | +0.0669 | +0.0692 | +0.0023 |
| S1 | 5 labelling: far-apart gap | -0.0032 | +0.0284 | +0.0315 |
| S1 | plots scored | 248 | 248 | +0 |
| S2 | 1 drawing: ARI, all plots | +0.0111 | +0.0117 | +0.0006 |
| S2 | 2 drawing: ARI, stands of 2+ plots | +0.0241 | +0.0216 | -0.0025 |
| S2 | 3 drawing: same-stand pair precision | +0.6331 | +0.6413 | +0.0082 |
| S2 | 4 labelling: ARI, district mean | +0.0375 | +0.0033 | -0.0342 |
| S2 | 5 labelling: far-apart gap | -0.0230 | -0.0101 | +0.0129 |
| S2 | plots scored | 264 | 264 | +0 |
| covered_only | 1 drawing: ARI, all plots | +0.0172 | +0.0174 | +0.0002 |
| covered_only | 2 drawing: ARI, stands of 2+ plots | +0.0340 | +0.0301 | -0.0040 |
| covered_only | 3 drawing: same-stand pair precision | +0.5612 | +0.5603 | -0.0009 |
| covered_only | 4 labelling: ARI, district mean | +0.0494 | +0.0524 | +0.0030 |
| covered_only | 5 labelling: far-apart gap | -0.0249 | -0.0026 | +0.0223 |
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
| angul | 464, 464 | 128, 127 | 129, 127 | 53, 53 | 466, 464 | 62, 60 |
| dhenkanal | 1114, 1114 | 328, 328 | 328, 328 | 148, 146 | 1121, 1115 | 86, 105 |
| kendujhar | 1086, 1086 | 351, 350 | 356, 350 | 145, 143 | 1094, 1087 | 100, 91 |
| koraput | 3326, 3327 | 968, 938 | 974, 940 | 302, 301 | 3339, 3330 | 266, 268 |

## Labelling ARI by district (primary analysis)

| District | hand-crafted, 10 ha (R3) (n) | AlphaEarth, 10 ha (R3) (n) |
|---|---|---|
| ANGUL | +0.1284 (39) | +0.1482 (39) |
| DHENKANAL | +0.1198 (74) | +0.1541 (74) |
| KENDUJHAR | +0.0625 (7) | +0.0000 (7) |
| KORAPUT | -0.0072 (144) | -0.0192 (144) |

## Inputs: each scores file's stand layers, by SHA-256

| Scores file | Run | SHA-256 |
|---|---|---|
| hand-crafted, 10 ha (R3) | `odisha_v120_10ha_squares_angul_keptland_s1desc_r14` | `0603f79b4b02b1cbdc2039fe07baa2a991f123502e045e605fca3865ba33f1fb` |
| hand-crafted, 10 ha (R3) | `odisha_v120_10ha_squares_dhenkanal_keptland_s1desc_r14` | `339093df42227e8dff21378403a3e09ca94321792ad90b9b1b124a7a73b73295` |
| hand-crafted, 10 ha (R3) | `odisha_v120_10ha_squares_kendujhar_keptland_s1desc_r14` | `0ff6342da8489a7f388ae0f9f8fe63861fbd2eebffbf976fd588cd706f93150c` |
| hand-crafted, 10 ha (R3) | `odisha_v120_10ha_squares_koraput_keptland_s1desc_r14` | `7cdd3345d89a6ca0682b6d7c920646e15d14573b7161501355fdc6e1d2918632` |
| hand-crafted, 10 ha (R3) | `odisha_v120_3ha_squares_angul` | `8f9eb3efd28df919a3c037256851f95e817e799b843f7a4cd19d67d1ce8dcb06` |
| hand-crafted, 10 ha (R3) | `odisha_v120_3ha_squares_dhenkanal` | `a2afbc6481abb455c6d5d4a4698ff4d335541895796012acab4e9364d2ffb771` |
| hand-crafted, 10 ha (R3) | `odisha_v120_3ha_squares_kendujhar` | `5d2b1d2d61d115bd18214931027a5c5967bfbe78f91f9c2ffb5b5ef42fb8615e` |
| hand-crafted, 10 ha (R3) | `odisha_v120_3ha_squares_koraput` | `6d9ebeb5689219d1ef86722c8479a4465f8c18f68e470ff5ed5555024f089fc1` |
| AlphaEarth, 10 ha (R3) | `odisha_alphaearth_10ha_squares_angul_keptland_r14` | `fb63be17571d9179815d671c9d7ed45ff0f8faccc068cdfefac5d4b320499949` |
| AlphaEarth, 10 ha (R3) | `odisha_alphaearth_10ha_squares_dhenkanal_keptland_r14` | `2d7c491debe7e9b4d2cd8232ea05930551a6785216476c73bebd85fbcc4ef65a` |
| AlphaEarth, 10 ha (R3) | `odisha_alphaearth_10ha_squares_kendujhar_keptland_r14` | `70bfe8e3c84fa35422b8c67f8a45bc16b0c1d93a7db822b24c564421eedf255c` |
| AlphaEarth, 10 ha (R3) | `odisha_alphaearth_10ha_squares_koraput_keptland_r14` | `76dd33c66bdb85dbec46476650c5a1ce1957baff015e60fc4ca4faf492b2fca0` |
| AlphaEarth, 10 ha (R3) | `odisha_v120_3ha_squares_angul` | `8f9eb3efd28df919a3c037256851f95e817e799b843f7a4cd19d67d1ce8dcb06` |
| AlphaEarth, 10 ha (R3) | `odisha_v120_3ha_squares_dhenkanal` | `a2afbc6481abb455c6d5d4a4698ff4d335541895796012acab4e9364d2ffb771` |
| AlphaEarth, 10 ha (R3) | `odisha_v120_3ha_squares_kendujhar` | `5d2b1d2d61d115bd18214931027a5c5967bfbe78f91f9c2ffb5b5ef42fb8615e` |
| AlphaEarth, 10 ha (R3) | `odisha_v120_3ha_squares_koraput` | `6d9ebeb5689219d1ef86722c8479a4465f8c18f68e470ff5ed5555024f089fc1` |

## The plots each side scores

- scored (the join with the 30 m rule): 264 (hand-crafted, 10 ha (R3)), 264 (AlphaEarth, 10 ha (R3)), 264 in both.
  - only hand-crafted, 10 ha (R3): none
  - only AlphaEarth, 10 ha (R3): none
- covered by a stand (no 30 m rule): 252 (hand-crafted, 10 ha (R3)), 252 (AlphaEarth, 10 ha (R3)), 252 in both.
  - only hand-crafted, 10 ha (R3): none
  - only AlphaEarth, 10 ha (R3): none

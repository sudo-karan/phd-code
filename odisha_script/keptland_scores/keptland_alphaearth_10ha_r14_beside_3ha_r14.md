# The kept-land field check: AlphaEarth, 10 ha (R3) against AlphaEarth, 3 ha (R3)

Written by `odisha_script/odisha_keptland_compare.py` from the committed scores files and run
records. Numbers only: as the declaration fixes, no chance test is run and no difference is
tested (`odisha_script/PHASE_KEPTLAND_PREDECLARED.md`).

## The five scores

| Analysis | Score | AlphaEarth, 3 ha (R3) | AlphaEarth, 10 ha (R3) | 10 ha minus 3 ha |
|---|---|---|---|---|
| primary | 1 drawing: ARI, all plots | +0.0053 | +0.0172 | +0.0119 |
| primary | 2 drawing: ARI, stands of 2+ plots | +0.0229 | +0.0302 | +0.0074 |
| primary | 3 drawing: same-stand pair precision | +0.5130 | +0.5587 | +0.0457 |
| primary | 4 labelling: ARI, district mean | +0.0466 | +0.0546 | +0.0081 |
| primary | 5 labelling: far-apart gap | -0.0012 | +0.0021 | +0.0033 |
| primary | plots scored | 264 | 264 | +0 |
| S1 | 1 drawing: ARI, all plots | +0.0044 | +0.0148 | +0.0105 |
| S1 | 2 drawing: ARI, stands of 2+ plots | +0.0193 | +0.0256 | +0.0063 |
| S1 | 3 drawing: same-stand pair precision | +0.5484 | +0.6031 | +0.0547 |
| S1 | 4 labelling: ARI, district mean | +0.0543 | +0.0692 | +0.0149 |
| S1 | 5 labelling: far-apart gap | +0.0074 | +0.0284 | +0.0210 |
| S1 | plots scored | 248 | 248 | +0 |
| S2 | 1 drawing: ARI, all plots | +0.0051 | +0.0117 | +0.0066 |
| S2 | 2 drawing: ARI, stands of 2+ plots | +0.0190 | +0.0216 | +0.0026 |
| S2 | 3 drawing: same-stand pair precision | +0.6870 | +0.6413 | -0.0457 |
| S2 | 4 labelling: ARI, district mean | +0.0355 | +0.0033 | -0.0322 |
| S2 | 5 labelling: far-apart gap | -0.0053 | -0.0101 | -0.0047 |
| S2 | plots scored | 264 | 264 | +0 |
| covered_only | 1 drawing: ARI, all plots | +0.0056 | +0.0174 | +0.0118 |
| covered_only | 2 drawing: ARI, stands of 2+ plots | +0.0241 | +0.0301 | +0.0060 |
| covered_only | 3 drawing: same-stand pair precision | +0.5189 | +0.5603 | +0.0414 |
| covered_only | 4 labelling: ARI, district mean | +0.0447 | +0.0524 | +0.0077 |
| covered_only | 5 labelling: far-apart gap | -0.0003 | -0.0026 | -0.0024 |
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
| angul | 1203, 464 | 234, 127 | 234, 127 | 53, 53 | 1204, 464 | 75, 60 |
| dhenkanal | 2883, 1114 | 570, 328 | 570, 328 | 146, 146 | 2885, 1115 | 114, 105 |
| kendujhar | 2745, 1086 | 554, 350 | 555, 350 | 145, 143 | 2746, 1087 | 101, 91 |
| koraput | 8737, 3327 | 1639, 938 | 1640, 940 | 306, 301 | 8742, 3330 | 382, 268 |

## Labelling ARI by district (primary analysis)

| District | AlphaEarth, 3 ha (R3) (n) | AlphaEarth, 10 ha (R3) (n) |
|---|---|---|
| ANGUL | +0.0978 (39) | +0.1482 (39) |
| DHENKANAL | +0.1433 (74) | +0.1541 (74) |
| KENDUJHAR | +0.0000 (7) | +0.0000 (7) |
| KORAPUT | -0.0148 (144) | -0.0192 (144) |

## Inputs: each scores file's stand layers, by SHA-256

| Scores file | Run | SHA-256 |
|---|---|---|
| AlphaEarth, 3 ha (R3) | `odisha_alphaearth_3ha_squares_angul_keptland_r14` | `94bb15c18ec9a33e004e0603c2ee8e3c278a8ab8f294a08efcf1a6375491ed0d` |
| AlphaEarth, 3 ha (R3) | `odisha_alphaearth_3ha_squares_dhenkanal_keptland_r14` | `ff845a3b74f1b759f10d40664dd720e142024eb21d5017c83978a3fd82eaa65e` |
| AlphaEarth, 3 ha (R3) | `odisha_alphaearth_3ha_squares_kendujhar_keptland_r14` | `6ae328e9a863cceef210e0c1f2b731537576f862dc32306f92e143cdf6be1d51` |
| AlphaEarth, 3 ha (R3) | `odisha_alphaearth_3ha_squares_koraput_keptland_r14` | `7d584ebaa9975c22737bfcca2ae2a4c7aa288531e324a1023dd57b0b6efa7dce` |
| AlphaEarth, 3 ha (R3) | `odisha_v120_3ha_squares_angul` | `8f9eb3efd28df919a3c037256851f95e817e799b843f7a4cd19d67d1ce8dcb06` |
| AlphaEarth, 3 ha (R3) | `odisha_v120_3ha_squares_dhenkanal` | `a2afbc6481abb455c6d5d4a4698ff4d335541895796012acab4e9364d2ffb771` |
| AlphaEarth, 3 ha (R3) | `odisha_v120_3ha_squares_kendujhar` | `5d2b1d2d61d115bd18214931027a5c5967bfbe78f91f9c2ffb5b5ef42fb8615e` |
| AlphaEarth, 3 ha (R3) | `odisha_v120_3ha_squares_koraput` | `6d9ebeb5689219d1ef86722c8479a4465f8c18f68e470ff5ed5555024f089fc1` |
| AlphaEarth, 10 ha (R3) | `odisha_alphaearth_10ha_squares_angul_keptland_r14` | `fb63be17571d9179815d671c9d7ed45ff0f8faccc068cdfefac5d4b320499949` |
| AlphaEarth, 10 ha (R3) | `odisha_alphaearth_10ha_squares_dhenkanal_keptland_r14` | `2d7c491debe7e9b4d2cd8232ea05930551a6785216476c73bebd85fbcc4ef65a` |
| AlphaEarth, 10 ha (R3) | `odisha_alphaearth_10ha_squares_kendujhar_keptland_r14` | `70bfe8e3c84fa35422b8c67f8a45bc16b0c1d93a7db822b24c564421eedf255c` |
| AlphaEarth, 10 ha (R3) | `odisha_alphaearth_10ha_squares_koraput_keptland_r14` | `76dd33c66bdb85dbec46476650c5a1ce1957baff015e60fc4ca4faf492b2fca0` |
| AlphaEarth, 10 ha (R3) | `odisha_v120_3ha_squares_angul` | `8f9eb3efd28df919a3c037256851f95e817e799b843f7a4cd19d67d1ce8dcb06` |
| AlphaEarth, 10 ha (R3) | `odisha_v120_3ha_squares_dhenkanal` | `a2afbc6481abb455c6d5d4a4698ff4d335541895796012acab4e9364d2ffb771` |
| AlphaEarth, 10 ha (R3) | `odisha_v120_3ha_squares_kendujhar` | `5d2b1d2d61d115bd18214931027a5c5967bfbe78f91f9c2ffb5b5ef42fb8615e` |
| AlphaEarth, 10 ha (R3) | `odisha_v120_3ha_squares_koraput` | `6d9ebeb5689219d1ef86722c8479a4465f8c18f68e470ff5ed5555024f089fc1` |

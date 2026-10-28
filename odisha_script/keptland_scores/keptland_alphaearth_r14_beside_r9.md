# The kept-land field check: AlphaEarth, 3 ha (R3) against AlphaEarth, 3 ha (_r9)

Written by `odisha_script/odisha_keptland_compare.py` from the committed scores files and run
records. Numbers only: as the declaration fixes, no chance test is run and no difference is
tested (`odisha_script/PHASE_KEPTLAND_PREDECLARED.md`).

## The five scores

| Analysis | Score | AlphaEarth, 3 ha (_r9) | AlphaEarth, 3 ha (R3) | R3 minus _r9 |
|---|---|---|---|---|
| primary | 1 drawing: ARI, all plots | +0.0053 | +0.0053 | +0.0000 |
| primary | 2 drawing: ARI, stands of 2+ plots | +0.0229 | +0.0229 | +0.0000 |
| primary | 3 drawing: same-stand pair precision | +0.5130 | +0.5130 | +0.0000 |
| primary | 4 labelling: ARI, district mean | +0.0411 | +0.0466 | +0.0054 |
| primary | 5 labelling: far-apart gap | -0.0043 | -0.0012 | +0.0031 |
| primary | plots scored | 264 | 264 | +0 |
| S1 | 1 drawing: ARI, all plots | +0.0044 | +0.0044 | +0.0000 |
| S1 | 2 drawing: ARI, stands of 2+ plots | +0.0193 | +0.0193 | +0.0000 |
| S1 | 3 drawing: same-stand pair precision | +0.5484 | +0.5484 | +0.0000 |
| S1 | 4 labelling: ARI, district mean | +0.0567 | +0.0543 | -0.0024 |
| S1 | 5 labelling: far-apart gap | +0.0022 | +0.0074 | +0.0052 |
| S1 | plots scored | 248 | 248 | +0 |
| S2 | 1 drawing: ARI, all plots | +0.0051 | +0.0051 | +0.0000 |
| S2 | 2 drawing: ARI, stands of 2+ plots | +0.0190 | +0.0190 | +0.0000 |
| S2 | 3 drawing: same-stand pair precision | +0.6870 | +0.6870 | +0.0000 |
| S2 | 4 labelling: ARI, district mean | +0.0340 | +0.0355 | +0.0015 |
| S2 | 5 labelling: far-apart gap | -0.0057 | -0.0053 | +0.0004 |
| S2 | plots scored | 264 | 264 | +0 |
| covered_only | 1 drawing: ARI, all plots | +0.0056 | +0.0056 | +0.0000 |
| covered_only | 2 drawing: ARI, stands of 2+ plots | +0.0241 | +0.0241 | +0.0000 |
| covered_only | 3 drawing: same-stand pair precision | +0.5189 | +0.5189 | +0.0000 |
| covered_only | 4 labelling: ARI, district mean | +0.0349 | +0.0447 | +0.0098 |
| covered_only | 5 labelling: far-apart gap | -0.0069 | -0.0003 | +0.0066 |
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
| angul | 1205, 1203 | 237, 234 | 235, 234 | 54, 53 | 1204, 1204 | 79, 75 |
| dhenkanal | 2889, 2883 | 574, 570 | 570, 570 | 152, 146 | 2885, 2885 | 126, 114 |
| kendujhar | 2747, 2745 | 555, 554 | 555, 555 | 147, 145 | 2746, 2746 | 111, 101 |
| koraput | 8743, 8737 | 1644, 1639 | 1641, 1640 | 311, 306 | 8742, 8742 | 340, 382 |

## Labelling ARI by district (primary analysis)

| District | AlphaEarth, 3 ha (_r9) (n) | AlphaEarth, 3 ha (R3) (n) |
|---|---|---|
| ANGUL | +0.1174 (39) | +0.0978 (39) |
| DHENKANAL | +0.0740 (74) | +0.1433 (74) |
| KENDUJHAR | +0.3333 (7) | +0.0000 (7) |
| KORAPUT | -0.0106 (144) | -0.0148 (144) |

## Inputs: each scores file's stand layers, by SHA-256

| Scores file | Run | SHA-256 |
|---|---|---|
| AlphaEarth, 3 ha (_r9) | `odisha_alphaearth_3ha_squares_angul_keptland_r9` | `58dd99a802db20926d0b06e5e2f3b597484dac892646a7a0ac5276c3a565e93b` |
| AlphaEarth, 3 ha (_r9) | `odisha_alphaearth_3ha_squares_dhenkanal_keptland_r9` | `406e3d860100072d8e76e7c2275d7a51c0142203ac725558ea13d9cc6aee5c99` |
| AlphaEarth, 3 ha (_r9) | `odisha_alphaearth_3ha_squares_kendujhar_keptland_r9` | `0adfb6bc14c2d338bd9a606e3a4dcc42ba01eaa3bffa5a10440e8e1f3600d115` |
| AlphaEarth, 3 ha (_r9) | `odisha_alphaearth_3ha_squares_koraput_keptland_r9` | `acc709e78be7b88a2ad1a48a31cfb91340c42e6983009a6863ac7ea2a36fbc5c` |
| AlphaEarth, 3 ha (_r9) | `odisha_v120_3ha_squares_angul` | `8f9eb3efd28df919a3c037256851f95e817e799b843f7a4cd19d67d1ce8dcb06` |
| AlphaEarth, 3 ha (_r9) | `odisha_v120_3ha_squares_dhenkanal` | `a2afbc6481abb455c6d5d4a4698ff4d335541895796012acab4e9364d2ffb771` |
| AlphaEarth, 3 ha (_r9) | `odisha_v120_3ha_squares_kendujhar` | `5d2b1d2d61d115bd18214931027a5c5967bfbe78f91f9c2ffb5b5ef42fb8615e` |
| AlphaEarth, 3 ha (_r9) | `odisha_v120_3ha_squares_koraput` | `6d9ebeb5689219d1ef86722c8479a4465f8c18f68e470ff5ed5555024f089fc1` |
| AlphaEarth, 3 ha (R3) | `odisha_alphaearth_3ha_squares_angul_keptland_r14` | `94bb15c18ec9a33e004e0603c2ee8e3c278a8ab8f294a08efcf1a6375491ed0d` |
| AlphaEarth, 3 ha (R3) | `odisha_alphaearth_3ha_squares_dhenkanal_keptland_r14` | `ff845a3b74f1b759f10d40664dd720e142024eb21d5017c83978a3fd82eaa65e` |
| AlphaEarth, 3 ha (R3) | `odisha_alphaearth_3ha_squares_kendujhar_keptland_r14` | `6ae328e9a863cceef210e0c1f2b731537576f862dc32306f92e143cdf6be1d51` |
| AlphaEarth, 3 ha (R3) | `odisha_alphaearth_3ha_squares_koraput_keptland_r14` | `7d584ebaa9975c22737bfcca2ae2a4c7aa288531e324a1023dd57b0b6efa7dce` |
| AlphaEarth, 3 ha (R3) | `odisha_v120_3ha_squares_angul` | `8f9eb3efd28df919a3c037256851f95e817e799b843f7a4cd19d67d1ce8dcb06` |
| AlphaEarth, 3 ha (R3) | `odisha_v120_3ha_squares_dhenkanal` | `a2afbc6481abb455c6d5d4a4698ff4d335541895796012acab4e9364d2ffb771` |
| AlphaEarth, 3 ha (R3) | `odisha_v120_3ha_squares_kendujhar` | `5d2b1d2d61d115bd18214931027a5c5967bfbe78f91f9c2ffb5b5ef42fb8615e` |
| AlphaEarth, 3 ha (R3) | `odisha_v120_3ha_squares_koraput` | `6d9ebeb5689219d1ef86722c8479a4465f8c18f68e470ff5ed5555024f089fc1` |

## The plots each side scores

- scored (the join with the 30 m rule): 264 (AlphaEarth, 3 ha (_r9)), 264 (AlphaEarth, 3 ha (R3)), 264 in both.
  - only AlphaEarth, 3 ha (_r9): none
  - only AlphaEarth, 3 ha (R3): none
- covered by a stand (no 30 m rule): 252 (AlphaEarth, 3 ha (_r9)), 252 (AlphaEarth, 3 ha (R3)), 252 in both.
  - only AlphaEarth, 3 ha (_r9): none
  - only AlphaEarth, 3 ha (R3): none

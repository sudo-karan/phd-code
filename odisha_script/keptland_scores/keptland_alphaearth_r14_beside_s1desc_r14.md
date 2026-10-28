# The kept-land field check: AlphaEarth, 3 ha (R3) against hand-crafted, 3 ha (R3)

Written by `odisha_script/odisha_keptland_compare.py` from the committed scores files and run
records. Numbers only: as the declaration fixes, no chance test is run and no difference is
tested (`odisha_script/PHASE_KEPTLAND_PREDECLARED.md`).

## The five scores

| Analysis | Score | hand-crafted, 3 ha (R3) | AlphaEarth, 3 ha (R3) | AlphaEarth minus hand-crafted |
|---|---|---|---|---|
| primary | 1 drawing: ARI, all plots | +0.0076 | +0.0053 | -0.0023 |
| primary | 2 drawing: ARI, stands of 2+ plots | +0.0269 | +0.0229 | -0.0040 |
| primary | 3 drawing: same-stand pair precision | +0.5580 | +0.5130 | -0.0449 |
| primary | 4 labelling: ARI, district mean | +0.0193 | +0.0466 | +0.0272 |
| primary | 5 labelling: far-apart gap | -0.0159 | -0.0012 | +0.0147 |
| primary | plots scored | 264 | 264 | +0 |
| S1 | 1 drawing: ARI, all plots | +0.0057 | +0.0044 | -0.0013 |
| S1 | 2 drawing: ARI, stands of 2+ plots | +0.0195 | +0.0193 | -0.0002 |
| S1 | 3 drawing: same-stand pair precision | +0.6020 | +0.5484 | -0.0537 |
| S1 | 4 labelling: ARI, district mean | +0.0373 | +0.0543 | +0.0170 |
| S1 | 5 labelling: far-apart gap | +0.0012 | +0.0074 | +0.0062 |
| S1 | plots scored | 248 | 248 | +0 |
| S2 | 1 drawing: ARI, all plots | +0.0054 | +0.0051 | -0.0003 |
| S2 | 2 drawing: ARI, stands of 2+ plots | +0.0171 | +0.0190 | +0.0019 |
| S2 | 3 drawing: same-stand pair precision | +0.6522 | +0.6870 | +0.0348 |
| S2 | 4 labelling: ARI, district mean | +0.0038 | +0.0355 | +0.0317 |
| S2 | 5 labelling: far-apart gap | -0.0251 | -0.0053 | +0.0198 |
| S2 | plots scored | 264 | 264 | +0 |
| covered_only | 1 drawing: ARI, all plots | +0.0072 | +0.0056 | -0.0016 |
| covered_only | 2 drawing: ARI, stands of 2+ plots | +0.0257 | +0.0241 | -0.0016 |
| covered_only | 3 drawing: same-stand pair precision | +0.5447 | +0.5189 | -0.0258 |
| covered_only | 4 labelling: ARI, district mean | +0.0190 | +0.0447 | +0.0257 |
| covered_only | 5 labelling: far-apart gap | -0.0167 | -0.0003 | +0.0164 |
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
| angul | 1202, 1203 | 221, 234 | 222, 234 | 55, 53 | 1204, 1204 | 80, 75 |
| dhenkanal | 2881, 2883 | 545, 570 | 549, 570 | 148, 146 | 2888, 2885 | 95, 114 |
| kendujhar | 2744, 2745 | 540, 554 | 541, 555 | 144, 145 | 2747, 2746 | 122, 101 |
| koraput | 8735, 8737 | 1616, 1639 | 1620, 1640 | 309, 306 | 8750, 8742 | 287, 382 |

## Labelling ARI by district (primary analysis)

| District | hand-crafted, 3 ha (R3) (n) | AlphaEarth, 3 ha (R3) (n) |
|---|---|---|
| ANGUL | +0.0698 (39) | +0.0978 (39) |
| DHENKANAL | +0.0773 (74) | +0.1433 (74) |
| KENDUJHAR | +0.0625 (7) | +0.0000 (7) |
| KORAPUT | -0.0262 (144) | -0.0148 (144) |

## Inputs: each scores file's stand layers, by SHA-256

| Scores file | Run | SHA-256 |
|---|---|---|
| hand-crafted, 3 ha (R3) | `odisha_v120_3ha_squares_angul` | `8f9eb3efd28df919a3c037256851f95e817e799b843f7a4cd19d67d1ce8dcb06` |
| hand-crafted, 3 ha (R3) | `odisha_v120_3ha_squares_angul_keptland_s1desc_r14` | `9cce67875d6df8cde38d22ae49ddf17fae508aff0d44f432553702d90ffa976e` |
| hand-crafted, 3 ha (R3) | `odisha_v120_3ha_squares_dhenkanal` | `a2afbc6481abb455c6d5d4a4698ff4d335541895796012acab4e9364d2ffb771` |
| hand-crafted, 3 ha (R3) | `odisha_v120_3ha_squares_dhenkanal_keptland_s1desc_r14` | `a8f04d47cfe8b0d5d83887918507ab5629933c28baaa81692611af9ea9d5cb39` |
| hand-crafted, 3 ha (R3) | `odisha_v120_3ha_squares_kendujhar` | `5d2b1d2d61d115bd18214931027a5c5967bfbe78f91f9c2ffb5b5ef42fb8615e` |
| hand-crafted, 3 ha (R3) | `odisha_v120_3ha_squares_kendujhar_keptland_s1desc_r14` | `267a1b0b140dad8af06f79e443873c1ffab2a154c4eb80bf6514dbc5ab8acf7d` |
| hand-crafted, 3 ha (R3) | `odisha_v120_3ha_squares_koraput` | `6d9ebeb5689219d1ef86722c8479a4465f8c18f68e470ff5ed5555024f089fc1` |
| hand-crafted, 3 ha (R3) | `odisha_v120_3ha_squares_koraput_keptland_s1desc_r14` | `deb7f888650902fc89a3e007094497218b4acd499c7892312b3e37cfb68d9788` |
| AlphaEarth, 3 ha (R3) | `odisha_alphaearth_3ha_squares_angul_keptland_r14` | `94bb15c18ec9a33e004e0603c2ee8e3c278a8ab8f294a08efcf1a6375491ed0d` |
| AlphaEarth, 3 ha (R3) | `odisha_alphaearth_3ha_squares_dhenkanal_keptland_r14` | `ff845a3b74f1b759f10d40664dd720e142024eb21d5017c83978a3fd82eaa65e` |
| AlphaEarth, 3 ha (R3) | `odisha_alphaearth_3ha_squares_kendujhar_keptland_r14` | `6ae328e9a863cceef210e0c1f2b731537576f862dc32306f92e143cdf6be1d51` |
| AlphaEarth, 3 ha (R3) | `odisha_alphaearth_3ha_squares_koraput_keptland_r14` | `7d584ebaa9975c22737bfcca2ae2a4c7aa288531e324a1023dd57b0b6efa7dce` |
| AlphaEarth, 3 ha (R3) | `odisha_v120_3ha_squares_angul` | `8f9eb3efd28df919a3c037256851f95e817e799b843f7a4cd19d67d1ce8dcb06` |
| AlphaEarth, 3 ha (R3) | `odisha_v120_3ha_squares_dhenkanal` | `a2afbc6481abb455c6d5d4a4698ff4d335541895796012acab4e9364d2ffb771` |
| AlphaEarth, 3 ha (R3) | `odisha_v120_3ha_squares_kendujhar` | `5d2b1d2d61d115bd18214931027a5c5967bfbe78f91f9c2ffb5b5ef42fb8615e` |
| AlphaEarth, 3 ha (R3) | `odisha_v120_3ha_squares_koraput` | `6d9ebeb5689219d1ef86722c8479a4465f8c18f68e470ff5ed5555024f089fc1` |

## The plots each side scores

- scored (the join with the 30 m rule): 264 (hand-crafted, 3 ha (R3)), 264 (AlphaEarth, 3 ha (R3)), 264 in both.
  - only hand-crafted, 3 ha (R3): none
  - only AlphaEarth, 3 ha (R3): none
- covered by a stand (no 30 m rule): 252 (hand-crafted, 3 ha (R3)), 252 (AlphaEarth, 3 ha (R3)), 252 in both.
  - only hand-crafted, 3 ha (R3): none
  - only AlphaEarth, 3 ha (R3): none

# The kept-land field check: hand-crafted, 10 ha (R3) against hand-crafted, 3 ha (R3)

Written by `odisha_script/odisha_keptland_compare.py` from the committed scores files and run
records. Numbers only: as the declaration fixes, no chance test is run and no difference is
tested (`odisha_script/PHASE_KEPTLAND_PREDECLARED.md`).

## The five scores

| Analysis | Score | hand-crafted, 3 ha (R3) | hand-crafted, 10 ha (R3) | 10 ha minus 3 ha |
|---|---|---|---|---|
| primary | 1 drawing: ARI, all plots | +0.0076 | +0.0162 | +0.0086 |
| primary | 2 drawing: ARI, stands of 2+ plots | +0.0269 | +0.0331 | +0.0062 |
| primary | 3 drawing: same-stand pair precision | +0.5580 | +0.5487 | -0.0093 |
| primary | 4 labelling: ARI, district mean | +0.0193 | +0.0503 | +0.0310 |
| primary | 5 labelling: far-apart gap | -0.0159 | -0.0217 | -0.0058 |
| primary | plots scored | 264 | 264 | +0 |
| S1 | 1 drawing: ARI, all plots | +0.0057 | +0.0147 | +0.0090 |
| S1 | 2 drawing: ARI, stands of 2+ plots | +0.0195 | +0.0296 | +0.0101 |
| S1 | 3 drawing: same-stand pair precision | +0.6020 | +0.6016 | -0.0005 |
| S1 | 4 labelling: ARI, district mean | +0.0373 | +0.0669 | +0.0296 |
| S1 | 5 labelling: far-apart gap | +0.0012 | -0.0032 | -0.0044 |
| S1 | plots scored | 248 | 248 | +0 |
| S2 | 1 drawing: ARI, all plots | +0.0054 | +0.0111 | +0.0057 |
| S2 | 2 drawing: ARI, stands of 2+ plots | +0.0171 | +0.0241 | +0.0070 |
| S2 | 3 drawing: same-stand pair precision | +0.6522 | +0.6331 | -0.0191 |
| S2 | 4 labelling: ARI, district mean | +0.0038 | +0.0375 | +0.0336 |
| S2 | 5 labelling: far-apart gap | -0.0251 | -0.0230 | +0.0021 |
| S2 | plots scored | 264 | 264 | +0 |
| covered_only | 1 drawing: ARI, all plots | +0.0072 | +0.0172 | +0.0100 |
| covered_only | 2 drawing: ARI, stands of 2+ plots | +0.0257 | +0.0340 | +0.0083 |
| covered_only | 3 drawing: same-stand pair precision | +0.5447 | +0.5612 | +0.0164 |
| covered_only | 4 labelling: ARI, district mean | +0.0190 | +0.0494 | +0.0304 |
| covered_only | 5 labelling: far-apart gap | -0.0167 | -0.0249 | -0.0082 |
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
| angul | 1202, 464 | 221, 128 | 222, 129 | 55, 53 | 1204, 466 | 80, 62 |
| dhenkanal | 2881, 1114 | 545, 328 | 549, 328 | 148, 148 | 2888, 1121 | 95, 86 |
| kendujhar | 2744, 1086 | 540, 351 | 541, 356 | 144, 145 | 2747, 1094 | 122, 100 |
| koraput | 8735, 3326 | 1616, 968 | 1620, 974 | 309, 302 | 8750, 3339 | 287, 266 |

## Labelling ARI by district (primary analysis)

| District | hand-crafted, 3 ha (R3) (n) | hand-crafted, 10 ha (R3) (n) |
|---|---|---|
| ANGUL | +0.0698 (39) | +0.1284 (39) |
| DHENKANAL | +0.0773 (74) | +0.1198 (74) |
| KENDUJHAR | +0.0625 (7) | +0.0625 (7) |
| KORAPUT | -0.0262 (144) | -0.0072 (144) |

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
| hand-crafted, 10 ha (R3) | `odisha_v120_10ha_squares_angul_keptland_s1desc_r14` | `0603f79b4b02b1cbdc2039fe07baa2a991f123502e045e605fca3865ba33f1fb` |
| hand-crafted, 10 ha (R3) | `odisha_v120_10ha_squares_dhenkanal_keptland_s1desc_r14` | `339093df42227e8dff21378403a3e09ca94321792ad90b9b1b124a7a73b73295` |
| hand-crafted, 10 ha (R3) | `odisha_v120_10ha_squares_kendujhar_keptland_s1desc_r14` | `0ff6342da8489a7f388ae0f9f8fe63861fbd2eebffbf976fd588cd706f93150c` |
| hand-crafted, 10 ha (R3) | `odisha_v120_10ha_squares_koraput_keptland_s1desc_r14` | `7cdd3345d89a6ca0682b6d7c920646e15d14573b7161501355fdc6e1d2918632` |
| hand-crafted, 10 ha (R3) | `odisha_v120_3ha_squares_angul` | `8f9eb3efd28df919a3c037256851f95e817e799b843f7a4cd19d67d1ce8dcb06` |
| hand-crafted, 10 ha (R3) | `odisha_v120_3ha_squares_dhenkanal` | `a2afbc6481abb455c6d5d4a4698ff4d335541895796012acab4e9364d2ffb771` |
| hand-crafted, 10 ha (R3) | `odisha_v120_3ha_squares_kendujhar` | `5d2b1d2d61d115bd18214931027a5c5967bfbe78f91f9c2ffb5b5ef42fb8615e` |
| hand-crafted, 10 ha (R3) | `odisha_v120_3ha_squares_koraput` | `6d9ebeb5689219d1ef86722c8479a4465f8c18f68e470ff5ed5555024f089fc1` |

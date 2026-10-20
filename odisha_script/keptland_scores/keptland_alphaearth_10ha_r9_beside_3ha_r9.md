# The kept-land field check: AlphaEarth, 10 ha against AlphaEarth, 3 ha (_r9)

Written by `odisha_script/odisha_keptland_compare.py` from the committed scores files and run
records. Numbers only: as the declaration fixes, no chance test is run and no difference is
tested (`odisha_script/PHASE_KEPTLAND_PREDECLARED.md`).

## The five scores

| Analysis | Score | AlphaEarth, 3 ha (_r9) | AlphaEarth, 10 ha | 10 ha minus 3 ha |
|---|---|---|---|---|
| primary | 1 drawing: ARI, all plots | +0.0053 | +0.0170 | +0.0117 |
| primary | 2 drawing: ARI, stands of 2+ plots | +0.0229 | +0.0305 | +0.0076 |
| primary | 3 drawing: same-stand pair precision | +0.5130 | +0.5729 | +0.0598 |
| primary | 4 labelling: ARI, district mean | +0.0411 | +0.0507 | +0.0096 |
| primary | 5 labelling: far-apart gap | -0.0043 | -0.0060 | -0.0017 |
| primary | plots scored | 264 | 264 | +0 |
| S1 | 1 drawing: ARI, all plots | +0.0044 | +0.0145 | +0.0102 |
| S1 | 2 drawing: ARI, stands of 2+ plots | +0.0193 | +0.0256 | +0.0063 |
| S1 | 3 drawing: same-stand pair precision | +0.5484 | +0.6032 | +0.0548 |
| S1 | 4 labelling: ARI, district mean | +0.0567 | +0.0570 | +0.0002 |
| S1 | 5 labelling: far-apart gap | +0.0022 | +0.0014 | -0.0008 |
| S1 | plots scored | 248 | 248 | +0 |
| S2 | 1 drawing: ARI, all plots | +0.0051 | +0.0114 | +0.0063 |
| S2 | 2 drawing: ARI, stands of 2+ plots | +0.0190 | +0.0215 | +0.0025 |
| S2 | 3 drawing: same-stand pair precision | +0.6870 | +0.6508 | -0.0361 |
| S2 | 4 labelling: ARI, district mean | +0.0340 | +0.0319 | -0.0021 |
| S2 | 5 labelling: far-apart gap | -0.0057 | -0.0138 | -0.0081 |
| S2 | plots scored | 264 | 264 | +0 |
| covered_only | 1 drawing: ARI, all plots | +0.0056 | +0.0173 | +0.0117 |
| covered_only | 2 drawing: ARI, stands of 2+ plots | +0.0241 | +0.0305 | +0.0064 |
| covered_only | 3 drawing: same-stand pair precision | +0.5189 | +0.5704 | +0.0515 |
| covered_only | 4 labelling: ARI, district mean | +0.0349 | +0.0465 | +0.0116 |
| covered_only | 5 labelling: far-apart gap | -0.0069 | -0.0118 | -0.0049 |
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
| angul | 1205, 466 | 237, 129 | 235, 127 | 54, 54 | 1204, 464 | 79, 60 |
| dhenkanal | 2889, 1119 | 574, 334 | 570, 329 | 152, 151 | 2885, 1115 | 126, 104 |
| kendujhar | 2747, 1088 | 555, 352 | 555, 350 | 147, 145 | 2746, 1087 | 111, 94 |
| koraput | 8743, 3332 | 1644, 943 | 1641, 940 | 311, 306 | 8742, 3330 | 340, 291 |

## Labelling ARI by district (primary analysis)

| District | AlphaEarth, 3 ha (_r9) (n) | AlphaEarth, 10 ha (n) |
|---|---|---|
| ANGUL | +0.1174 (39) | +0.0733 (39) |
| DHENKANAL | +0.0740 (74) | +0.1724 (74) |
| KENDUJHAR | +0.3333 (7) | +0.0000 (7) |
| KORAPUT | -0.0106 (144) | -0.0155 (144) |

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
| AlphaEarth, 10 ha | `odisha_alphaearth_10ha_squares_angul_keptland_r9` | `dedcacf09be04e03aaa1c58b7e04a3b7085d3ef1f4000eba763cfc3822b3bc90` |
| AlphaEarth, 10 ha | `odisha_alphaearth_10ha_squares_dhenkanal_keptland_r9` | `25f9c7fafc7e917753c55c39155c4459aeebe7b916b415dd5bc9a5243af45164` |
| AlphaEarth, 10 ha | `odisha_alphaearth_10ha_squares_kendujhar_keptland_r9` | `77797f387a72ec59a196e4187b65c942c519e9b5f1ba18f401252404d6510f1d` |
| AlphaEarth, 10 ha | `odisha_alphaearth_10ha_squares_koraput_keptland_r9` | `9598b423c76b2a296380dc45cfc5d683f9347c8a7e09155d8cde7326679d35f7` |
| AlphaEarth, 10 ha | `odisha_v120_3ha_squares_angul` | `8f9eb3efd28df919a3c037256851f95e817e799b843f7a4cd19d67d1ce8dcb06` |
| AlphaEarth, 10 ha | `odisha_v120_3ha_squares_dhenkanal` | `a2afbc6481abb455c6d5d4a4698ff4d335541895796012acab4e9364d2ffb771` |
| AlphaEarth, 10 ha | `odisha_v120_3ha_squares_kendujhar` | `5d2b1d2d61d115bd18214931027a5c5967bfbe78f91f9c2ffb5b5ef42fb8615e` |
| AlphaEarth, 10 ha | `odisha_v120_3ha_squares_koraput` | `6d9ebeb5689219d1ef86722c8479a4465f8c18f68e470ff5ed5555024f089fc1` |

## Note added 20 Oct 2026 (round 13, review A1, A4, A5, A6, B13, B14, B16, B17 and B18)

The numbers above are as first written. Both sides are AlphaEarth runs from before the round 13
fixes (`docs/handoff/2026-10-20-round13.md`, Done), and so are the differences between them. A1, A5
and B13 do not reach this arm. A4 reaches its Koraput runs, at both sizes, through the merge's NDVI
amplitude (question 1 of that record; until it is answered, noted as affected, by an amount not
measured), and no other run of it. The merge and clustering fixes B14, B16, B17 and B18 reach every
run, and the stand counts above, from the run records, are from before them. Whether roadmap R3
re-runs this arm is put to Jaskaran in that record. How far any fix moves a stand, a type, a score
or a difference was not measured; it needs Earth Engine. The note at the end of each scores file
says more (`keptland_alphaearth_r9_scores.txt`, `keptland_alphaearth_10ha_r9_scores.txt`).
`README.md` here lists every file noted. No number here is changed.

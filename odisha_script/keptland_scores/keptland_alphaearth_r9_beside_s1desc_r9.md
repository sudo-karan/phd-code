# The kept-land field check: AlphaEarth (_r9) against hand-crafted (_r9)

Written by `odisha_script/odisha_keptland_compare.py` from the committed scores files and run
records. Numbers only: as the declaration fixes, no chance test is run and no difference is
tested (`odisha_script/PHASE_KEPTLAND_PREDECLARED.md`).

## The five scores

| Analysis | Score | hand-crafted (_r9) | AlphaEarth (_r9) | AlphaEarth minus hand-crafted |
|---|---|---|---|---|
| primary | 1 drawing: ARI, all plots | +0.0068 | +0.0053 | -0.0015 |
| primary | 2 drawing: ARI, stands of 2+ plots | +0.0277 | +0.0229 | -0.0048 |
| primary | 3 drawing: same-stand pair precision | +0.5290 | +0.5130 | -0.0159 |
| primary | 4 labelling: ARI, district mean | +0.0468 | +0.0411 | -0.0057 |
| primary | 5 labelling: far-apart gap | +0.0024 | -0.0043 | -0.0067 |
| primary | plots scored | 264 | 264 | +0 |
| S1 | 1 drawing: ARI, all plots | +0.0050 | +0.0044 | -0.0007 |
| S1 | 2 drawing: ARI, stands of 2+ plots | +0.0191 | +0.0193 | +0.0003 |
| S1 | 3 drawing: same-stand pair precision | +0.5789 | +0.5484 | -0.0306 |
| S1 | 4 labelling: ARI, district mean | +0.0566 | +0.0567 | +0.0002 |
| S1 | 5 labelling: far-apart gap | +0.0264 | +0.0022 | -0.0242 |
| S1 | plots scored | 248 | 248 | +0 |
| S2 | 1 drawing: ARI, all plots | +0.0048 | +0.0051 | +0.0003 |
| S2 | 2 drawing: ARI, stands of 2+ plots | +0.0182 | +0.0190 | +0.0008 |
| S2 | 3 drawing: same-stand pair precision | +0.6232 | +0.6870 | +0.0638 |
| S2 | 4 labelling: ARI, district mean | +0.0221 | +0.0340 | +0.0119 |
| S2 | 5 labelling: far-apart gap | -0.0017 | -0.0057 | -0.0040 |
| S2 | plots scored | 264 | 264 | +0 |
| covered_only | 1 drawing: ARI, all plots | +0.0062 | +0.0056 | -0.0006 |
| covered_only | 2 drawing: ARI, stands of 2+ plots | +0.0266 | +0.0241 | -0.0025 |
| covered_only | 3 drawing: same-stand pair precision | +0.5124 | +0.5189 | +0.0065 |
| covered_only | 4 labelling: ARI, district mean | +0.0475 | +0.0349 | -0.0126 |
| covered_only | 5 labelling: far-apart gap | +0.0008 | -0.0069 | -0.0077 |
| covered_only | plots scored | 252 | 252 | +0 |
| box_runs | 1 drawing: ARI, all plots | +0.0051 | +0.0051 | +0.0000 |
| box_runs | 2 drawing: ARI, stands of 2+ plots | +0.0225 | +0.0225 | +0.0000 |
| box_runs | 3 drawing: same-stand pair precision | +0.5185 | +0.5185 | +0.0000 |
| box_runs | 4 labelling: ARI, district mean | +0.0504 | +0.0504 | +0.0000 |
| box_runs | 5 labelling: far-apart gap | -0.0165 | -0.0165 | +0.0000 |
| box_runs | plots scored | 264 | 264 | +0 |

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
| angul | 1205, 1205 | 221, 237 | 219, 235 | 55, 54 | 1205, 1204 | 63, 79 |
| dhenkanal | 2889, 2889 | 552, 574 | 552, 570 | 157, 152 | 2886, 2885 | 91, 126 |
| kendujhar | 2747, 2747 | 547, 555 | 547, 555 | 147, 147 | 2749, 2746 | 111, 111 |
| koraput | 8743, 8743 | 1616, 1644 | 1616, 1641 | 316, 311 | 8749, 8742 | 330, 340 |

## Labelling ARI by district (primary analysis)

| District | hand-crafted (_r9) (n) | AlphaEarth (_r9) (n) |
|---|---|---|
| ANGUL | +0.1360 (39) | +0.1174 (39) |
| DHENKANAL | +0.0985 (74) | +0.0740 (74) |
| KENDUJHAR | +0.0000 (7) | +0.3333 (7) |
| KORAPUT | -0.0016 (144) | -0.0106 (144) |

## Inputs: each scores file's stand layers, by SHA-256

| Scores file | Run | SHA-256 |
|---|---|---|
| hand-crafted (_r9) | `odisha_v120_3ha_squares_angul` | `8f9eb3efd28df919a3c037256851f95e817e799b843f7a4cd19d67d1ce8dcb06` |
| hand-crafted (_r9) | `odisha_v120_3ha_squares_angul_keptland_s1desc_r9` | `6fc85bf6a85722c2f67e059a6c9a56ef970879c6bee00d777c547b4c1b0b7505` |
| hand-crafted (_r9) | `odisha_v120_3ha_squares_dhenkanal` | `a2afbc6481abb455c6d5d4a4698ff4d335541895796012acab4e9364d2ffb771` |
| hand-crafted (_r9) | `odisha_v120_3ha_squares_dhenkanal_keptland_s1desc_r9` | `b62b618963fe4501b2532c12b246000ce19737e49aec991bee67561f264dbd63` |
| hand-crafted (_r9) | `odisha_v120_3ha_squares_kendujhar` | `5d2b1d2d61d115bd18214931027a5c5967bfbe78f91f9c2ffb5b5ef42fb8615e` |
| hand-crafted (_r9) | `odisha_v120_3ha_squares_kendujhar_keptland_s1desc_r9` | `b2d1e7d1daab895c3512c1b0a8cd5e014c0a0abefb6619e79316ad5247e58002` |
| hand-crafted (_r9) | `odisha_v120_3ha_squares_koraput` | `6d9ebeb5689219d1ef86722c8479a4465f8c18f68e470ff5ed5555024f089fc1` |
| hand-crafted (_r9) | `odisha_v120_3ha_squares_koraput_keptland_s1desc_r9` | `57cb55a0690b72344a7c88e8d9544b3cccc69b352364e432a7b411ab6cf69780` |
| AlphaEarth (_r9) | `odisha_alphaearth_3ha_squares_angul_keptland_r9` | `58dd99a802db20926d0b06e5e2f3b597484dac892646a7a0ac5276c3a565e93b` |
| AlphaEarth (_r9) | `odisha_alphaearth_3ha_squares_dhenkanal_keptland_r9` | `406e3d860100072d8e76e7c2275d7a51c0142203ac725558ea13d9cc6aee5c99` |
| AlphaEarth (_r9) | `odisha_alphaearth_3ha_squares_kendujhar_keptland_r9` | `0adfb6bc14c2d338bd9a606e3a4dcc42ba01eaa3bffa5a10440e8e1f3600d115` |
| AlphaEarth (_r9) | `odisha_alphaearth_3ha_squares_koraput_keptland_r9` | `acc709e78be7b88a2ad1a48a31cfb91340c42e6983009a6863ac7ea2a36fbc5c` |
| AlphaEarth (_r9) | `odisha_v120_3ha_squares_angul` | `8f9eb3efd28df919a3c037256851f95e817e799b843f7a4cd19d67d1ce8dcb06` |
| AlphaEarth (_r9) | `odisha_v120_3ha_squares_dhenkanal` | `a2afbc6481abb455c6d5d4a4698ff4d335541895796012acab4e9364d2ffb771` |
| AlphaEarth (_r9) | `odisha_v120_3ha_squares_kendujhar` | `5d2b1d2d61d115bd18214931027a5c5967bfbe78f91f9c2ffb5b5ef42fb8615e` |
| AlphaEarth (_r9) | `odisha_v120_3ha_squares_koraput` | `6d9ebeb5689219d1ef86722c8479a4465f8c18f68e470ff5ed5555024f089fc1` |

## The plots each side scores

- scored (the join with the 30 m rule): 264 (hand-crafted (_r9)), 264 (AlphaEarth (_r9)), 264 in both.
  - only hand-crafted (_r9): none
  - only AlphaEarth (_r9): none
- covered by a stand (no 30 m rule): 252 (hand-crafted (_r9)), 252 (AlphaEarth (_r9)), 252 in both.
  - only hand-crafted (_r9): none
  - only AlphaEarth (_r9): none

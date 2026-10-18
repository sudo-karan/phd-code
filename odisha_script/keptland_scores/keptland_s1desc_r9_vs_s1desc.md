# The kept-land field check: re-run (_r9) against old (round 7)

Written by `odisha_script/odisha_keptland_compare.py` from the committed scores files and run
records. Numbers only: as the declaration fixes, no chance test is run and no difference is
tested (`odisha_script/PHASE_KEPTLAND_PREDECLARED.md`).

## The five scores

| Analysis | Score | old (round 7) | re-run (_r9) | new minus old |
|---|---|---|---|---|
| primary | 1 drawing: ARI, all plots | +0.0048 | +0.0068 | +0.0020 |
| primary | 2 drawing: ARI, stands of 2+ plots | +0.0179 | +0.0277 | +0.0098 |
| primary | 3 drawing: same-stand pair precision | +0.4692 | +0.5290 | +0.0598 |
| primary | 4 labelling: ARI, district mean | +0.0440 | +0.0468 | +0.0028 |
| primary | 5 labelling: far-apart gap | -0.0112 | +0.0024 | +0.0136 |
| primary | plots scored | 264 | 264 | +0 |
| S1 | 1 drawing: ARI, all plots | +0.0046 | +0.0050 | +0.0004 |
| S1 | 2 drawing: ARI, stands of 2+ plots | +0.0159 | +0.0191 | +0.0032 |
| S1 | 3 drawing: same-stand pair precision | +0.5510 | +0.5789 | +0.0279 |
| S1 | 4 labelling: ARI, district mean | +0.0512 | +0.0566 | +0.0054 |
| S1 | 5 labelling: far-apart gap | +0.0093 | +0.0264 | +0.0171 |
| S1 | plots scored | 248 | 248 | +0 |
| S2 | 1 drawing: ARI, all plots | +0.0036 | +0.0048 | +0.0012 |
| S2 | 2 drawing: ARI, stands of 2+ plots | +0.0121 | +0.0182 | +0.0062 |
| S2 | 3 drawing: same-stand pair precision | +0.5769 | +0.6232 | +0.0463 |
| S2 | 4 labelling: ARI, district mean | +0.0125 | +0.0221 | +0.0096 |
| S2 | 5 labelling: far-apart gap | -0.0141 | -0.0017 | +0.0125 |
| S2 | plots scored | 264 | 264 | +0 |
| covered_only | 1 drawing: ARI, all plots | +0.0048 | +0.0062 | +0.0014 |
| covered_only | 2 drawing: ARI, stands of 2+ plots | +0.0179 | +0.0266 | +0.0087 |
| covered_only | 3 drawing: same-stand pair precision | +0.4622 | +0.5124 | +0.0502 |
| covered_only | 4 labelling: ARI, district mean | +0.0379 | +0.0475 | +0.0097 |
| covered_only | 5 labelling: far-apart gap | -0.0148 | +0.0008 | +0.0156 |
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
| angul | 1202, 1205 | 224, 221 | 225, 219 | 54, 55 | 1209, 1205 | 65, 63 |
| dhenkanal | 2884, 2889 | 560, 552 | 559, 552 | 152, 157 | 2889, 2886 | 85, 91 |
| kendujhar | 2747, 2747 | 558, 547 | 557, 547 | 145, 147 | 2751, 2749 | 108, 111 |
| koraput | 8739, 8743 | 1620, 1616 | 1631, 1616 | 310, 316 | 8744, 8749 | 324, 330 |
| sanjay_van_baseline_keptland | 1202, 1205 | 578, 583 | 576, 578 | 390, 394 | 1202, 1202 | 284, 259 |
| sanjay_van_alphaearth_keptland | 1202, 1205 | 561, 565 | 559, 560 | 389, 391 | 1200, 1200 | 263, 244 |

## Labelling ARI by district (primary analysis)

| District | old (round 7) (n) | re-run (_r9) (n) |
|---|---|---|
| ANGUL | +0.1915 (39) | +0.1360 (39) |
| DHENKANAL | +0.0995 (74) | +0.0985 (74) |
| KENDUJHAR | +0.2000 (7) | +0.0000 (7) |
| KORAPUT | -0.0321 (144) | -0.0016 (144) |

## Inputs: each scores file's stand layers, by SHA-256

| Scores file | Run | SHA-256 |
|---|---|---|
| old (round 7) | `odisha_v120_3ha_squares_angul` | `8f9eb3efd28df919a3c037256851f95e817e799b843f7a4cd19d67d1ce8dcb06` |
| old (round 7) | `odisha_v120_3ha_squares_angul_keptland_s1desc` | `28659e76b414ab236acbfb2735ff69383ba98d2d3cc31d82ae2b52b617bdff8f` |
| old (round 7) | `odisha_v120_3ha_squares_dhenkanal` | `a2afbc6481abb455c6d5d4a4698ff4d335541895796012acab4e9364d2ffb771` |
| old (round 7) | `odisha_v120_3ha_squares_dhenkanal_keptland_s1desc` | `26ba31b2a8a15c002a11e7cdb847d35bc401ab3fb6bdf9380f44f2a2eed41561` |
| old (round 7) | `odisha_v120_3ha_squares_kendujhar` | `5d2b1d2d61d115bd18214931027a5c5967bfbe78f91f9c2ffb5b5ef42fb8615e` |
| old (round 7) | `odisha_v120_3ha_squares_kendujhar_keptland_s1desc` | `6ce44ad5a26a357f8c7463caf405754da0bc9d61ec58c228eb173f35a2a53c3c` |
| old (round 7) | `odisha_v120_3ha_squares_koraput` | `6d9ebeb5689219d1ef86722c8479a4465f8c18f68e470ff5ed5555024f089fc1` |
| old (round 7) | `odisha_v120_3ha_squares_koraput_keptland_s1desc` | `072dbb7db380f8ec9fd4839c59c3cc3fbaa7a4ed3110f426f3413f5766634fce` |
| re-run (_r9) | `odisha_v120_3ha_squares_angul` | `8f9eb3efd28df919a3c037256851f95e817e799b843f7a4cd19d67d1ce8dcb06` |
| re-run (_r9) | `odisha_v120_3ha_squares_angul_keptland_s1desc_r9` | `6fc85bf6a85722c2f67e059a6c9a56ef970879c6bee00d777c547b4c1b0b7505` |
| re-run (_r9) | `odisha_v120_3ha_squares_dhenkanal` | `a2afbc6481abb455c6d5d4a4698ff4d335541895796012acab4e9364d2ffb771` |
| re-run (_r9) | `odisha_v120_3ha_squares_dhenkanal_keptland_s1desc_r9` | `b62b618963fe4501b2532c12b246000ce19737e49aec991bee67561f264dbd63` |
| re-run (_r9) | `odisha_v120_3ha_squares_kendujhar` | `5d2b1d2d61d115bd18214931027a5c5967bfbe78f91f9c2ffb5b5ef42fb8615e` |
| re-run (_r9) | `odisha_v120_3ha_squares_kendujhar_keptland_s1desc_r9` | `b2d1e7d1daab895c3512c1b0a8cd5e014c0a0abefb6619e79316ad5247e58002` |
| re-run (_r9) | `odisha_v120_3ha_squares_koraput` | `6d9ebeb5689219d1ef86722c8479a4465f8c18f68e470ff5ed5555024f089fc1` |
| re-run (_r9) | `odisha_v120_3ha_squares_koraput_keptland_s1desc_r9` | `57cb55a0690b72344a7c88e8d9544b3cccc69b352364e432a7b411ab6cf69780` |

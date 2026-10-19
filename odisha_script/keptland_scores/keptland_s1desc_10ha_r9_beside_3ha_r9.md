# The kept-land field check: hand-crafted, 10 ha against hand-crafted, 3 ha (_r9)

Written by `odisha_script/odisha_keptland_compare.py` from the committed scores files and run
records. Numbers only: as the declaration fixes, no chance test is run and no difference is
tested (`odisha_script/PHASE_KEPTLAND_PREDECLARED.md`).

## The five scores

| Analysis | Score | hand-crafted, 3 ha (_r9) | hand-crafted, 10 ha | 10 ha minus 3 ha |
|---|---|---|---|---|
| primary | 1 drawing: ARI, all plots | +0.0068 | +0.0146 | +0.0079 |
| primary | 2 drawing: ARI, stands of 2+ plots | +0.0277 | +0.0319 | +0.0042 |
| primary | 3 drawing: same-stand pair precision | +0.5290 | +0.5108 | -0.0182 |
| primary | 4 labelling: ARI, district mean | +0.0468 | +0.0572 | +0.0104 |
| primary | 5 labelling: far-apart gap | +0.0024 | +0.0122 | +0.0098 |
| primary | plots scored | 264 | 264 | +0 |
| S1 | 1 drawing: ARI, all plots | +0.0050 | +0.0137 | +0.0086 |
| S1 | 2 drawing: ARI, stands of 2+ plots | +0.0191 | +0.0287 | +0.0096 |
| S1 | 3 drawing: same-stand pair precision | +0.5789 | +0.6140 | +0.0351 |
| S1 | 4 labelling: ARI, district mean | +0.0566 | +0.0666 | +0.0100 |
| S1 | 5 labelling: far-apart gap | +0.0264 | +0.0345 | +0.0081 |
| S1 | plots scored | 248 | 248 | +0 |
| S2 | 1 drawing: ARI, all plots | +0.0048 | +0.0101 | +0.0053 |
| S2 | 2 drawing: ARI, stands of 2+ plots | +0.0182 | +0.0231 | +0.0048 |
| S2 | 3 drawing: same-stand pair precision | +0.6232 | +0.6000 | -0.0232 |
| S2 | 4 labelling: ARI, district mean | +0.0221 | +0.0288 | +0.0067 |
| S2 | 5 labelling: far-apart gap | -0.0017 | +0.0177 | +0.0194 |
| S2 | plots scored | 264 | 264 | +0 |
| covered_only | 1 drawing: ARI, all plots | +0.0062 | +0.0151 | +0.0089 |
| covered_only | 2 drawing: ARI, stands of 2+ plots | +0.0266 | +0.0322 | +0.0056 |
| covered_only | 3 drawing: same-stand pair precision | +0.5124 | +0.5230 | +0.0106 |
| covered_only | 4 labelling: ARI, district mean | +0.0475 | +0.0521 | +0.0046 |
| covered_only | 5 labelling: far-apart gap | +0.0008 | +0.0129 | +0.0121 |
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
| angul | 1205, 466 | 221, 136 | 219, 134 | 55, 54 | 1205, 465 | 63, 60 |
| dhenkanal | 2889, 1119 | 552, 334 | 552, 330 | 157, 153 | 2886, 1123 | 91, 79 |
| kendujhar | 2747, 1088 | 547, 354 | 547, 355 | 147, 147 | 2749, 1095 | 111, 96 |
| koraput | 8743, 3332 | 1616, 988 | 1616, 990 | 316, 306 | 8749, 3339 | 330, 263 |

## Labelling ARI by district (primary analysis)

| District | hand-crafted, 3 ha (_r9) (n) | hand-crafted, 10 ha (n) |
|---|---|---|
| ANGUL | +0.1360 (39) | +0.1443 (39) |
| DHENKANAL | +0.0985 (74) | +0.1445 (74) |
| KENDUJHAR | +0.0000 (7) | +0.0000 (7) |
| KORAPUT | -0.0016 (144) | -0.0085 (144) |

## Inputs: each scores file's stand layers, by SHA-256

| Scores file | Run | SHA-256 |
|---|---|---|
| hand-crafted, 3 ha (_r9) | `odisha_v120_3ha_squares_angul` | `8f9eb3efd28df919a3c037256851f95e817e799b843f7a4cd19d67d1ce8dcb06` |
| hand-crafted, 3 ha (_r9) | `odisha_v120_3ha_squares_angul_keptland_s1desc_r9` | `6fc85bf6a85722c2f67e059a6c9a56ef970879c6bee00d777c547b4c1b0b7505` |
| hand-crafted, 3 ha (_r9) | `odisha_v120_3ha_squares_dhenkanal` | `a2afbc6481abb455c6d5d4a4698ff4d335541895796012acab4e9364d2ffb771` |
| hand-crafted, 3 ha (_r9) | `odisha_v120_3ha_squares_dhenkanal_keptland_s1desc_r9` | `b62b618963fe4501b2532c12b246000ce19737e49aec991bee67561f264dbd63` |
| hand-crafted, 3 ha (_r9) | `odisha_v120_3ha_squares_kendujhar` | `5d2b1d2d61d115bd18214931027a5c5967bfbe78f91f9c2ffb5b5ef42fb8615e` |
| hand-crafted, 3 ha (_r9) | `odisha_v120_3ha_squares_kendujhar_keptland_s1desc_r9` | `b2d1e7d1daab895c3512c1b0a8cd5e014c0a0abefb6619e79316ad5247e58002` |
| hand-crafted, 3 ha (_r9) | `odisha_v120_3ha_squares_koraput` | `6d9ebeb5689219d1ef86722c8479a4465f8c18f68e470ff5ed5555024f089fc1` |
| hand-crafted, 3 ha (_r9) | `odisha_v120_3ha_squares_koraput_keptland_s1desc_r9` | `57cb55a0690b72344a7c88e8d9544b3cccc69b352364e432a7b411ab6cf69780` |
| hand-crafted, 10 ha | `odisha_v120_10ha_squares_angul_keptland_s1desc_r9` | `ba9e0b37b574a99dd8a70211b190a731a8379e79deef80835a9fa2888c8a9955` |
| hand-crafted, 10 ha | `odisha_v120_10ha_squares_dhenkanal_keptland_s1desc_r9` | `f07a6932dcae01b285995f1540f6a465765995bfcecc393e6e568101c5fd6091` |
| hand-crafted, 10 ha | `odisha_v120_10ha_squares_kendujhar_keptland_s1desc_r9` | `b1e2e23e9693d2be796e181813dfdd4005530afba2bed44cea71a5afb52f863e` |
| hand-crafted, 10 ha | `odisha_v120_10ha_squares_koraput_keptland_s1desc_r9` | `85af0e0dfb9a7250266159811193f38d8f0705784d54d194f046259bca2ee678` |
| hand-crafted, 10 ha | `odisha_v120_3ha_squares_angul` | `8f9eb3efd28df919a3c037256851f95e817e799b843f7a4cd19d67d1ce8dcb06` |
| hand-crafted, 10 ha | `odisha_v120_3ha_squares_dhenkanal` | `a2afbc6481abb455c6d5d4a4698ff4d335541895796012acab4e9364d2ffb771` |
| hand-crafted, 10 ha | `odisha_v120_3ha_squares_kendujhar` | `5d2b1d2d61d115bd18214931027a5c5967bfbe78f91f9c2ffb5b5ef42fb8615e` |
| hand-crafted, 10 ha | `odisha_v120_3ha_squares_koraput` | `6d9ebeb5689219d1ef86722c8479a4465f8c18f68e470ff5ed5555024f089fc1` |

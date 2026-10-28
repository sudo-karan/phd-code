# The kept-land field check: hand-crafted, 10 ha (R3) against hand-crafted, 10 ha (_r9)

Written by `odisha_script/odisha_keptland_compare.py` from the committed scores files and run
records. Numbers only: as the declaration fixes, no chance test is run and no difference is
tested (`odisha_script/PHASE_KEPTLAND_PREDECLARED.md`).

## The five scores

| Analysis | Score | hand-crafted, 10 ha (_r9) | hand-crafted, 10 ha (R3) | R3 minus _r9 |
|---|---|---|---|---|
| primary | 1 drawing: ARI, all plots | +0.0146 | +0.0162 | +0.0016 |
| primary | 2 drawing: ARI, stands of 2+ plots | +0.0319 | +0.0331 | +0.0012 |
| primary | 3 drawing: same-stand pair precision | +0.5108 | +0.5487 | +0.0379 |
| primary | 4 labelling: ARI, district mean | +0.0572 | +0.0503 | -0.0069 |
| primary | 5 labelling: far-apart gap | +0.0122 | -0.0217 | -0.0339 |
| primary | plots scored | 264 | 264 | +0 |
| S1 | 1 drawing: ARI, all plots | +0.0137 | +0.0147 | +0.0010 |
| S1 | 2 drawing: ARI, stands of 2+ plots | +0.0287 | +0.0296 | +0.0010 |
| S1 | 3 drawing: same-stand pair precision | +0.6140 | +0.6016 | -0.0125 |
| S1 | 4 labelling: ARI, district mean | +0.0666 | +0.0669 | +0.0003 |
| S1 | 5 labelling: far-apart gap | +0.0345 | -0.0032 | -0.0377 |
| S1 | plots scored | 248 | 248 | +0 |
| S2 | 1 drawing: ARI, all plots | +0.0101 | +0.0111 | +0.0010 |
| S2 | 2 drawing: ARI, stands of 2+ plots | +0.0231 | +0.0241 | +0.0010 |
| S2 | 3 drawing: same-stand pair precision | +0.6000 | +0.6331 | +0.0331 |
| S2 | 4 labelling: ARI, district mean | +0.0288 | +0.0375 | +0.0087 |
| S2 | 5 labelling: far-apart gap | +0.0177 | -0.0230 | -0.0407 |
| S2 | plots scored | 264 | 264 | +0 |
| covered_only | 1 drawing: ARI, all plots | +0.0151 | +0.0172 | +0.0021 |
| covered_only | 2 drawing: ARI, stands of 2+ plots | +0.0322 | +0.0340 | +0.0019 |
| covered_only | 3 drawing: same-stand pair precision | +0.5230 | +0.5612 | +0.0382 |
| covered_only | 4 labelling: ARI, district mean | +0.0521 | +0.0494 | -0.0028 |
| covered_only | 5 labelling: far-apart gap | +0.0129 | -0.0249 | -0.0378 |
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
| angul | 466, 464 | 136, 128 | 134, 129 | 54, 53 | 465, 466 | 60, 62 |
| dhenkanal | 1119, 1114 | 334, 328 | 330, 328 | 153, 148 | 1123, 1121 | 79, 86 |
| kendujhar | 1088, 1086 | 354, 351 | 355, 356 | 147, 145 | 1095, 1094 | 96, 100 |
| koraput | 3332, 3326 | 988, 968 | 990, 974 | 306, 302 | 3339, 3339 | 263, 266 |

## Labelling ARI by district (primary analysis)

| District | hand-crafted, 10 ha (_r9) (n) | hand-crafted, 10 ha (R3) (n) |
|---|---|---|
| ANGUL | +0.1443 (39) | +0.1284 (39) |
| DHENKANAL | +0.1445 (74) | +0.1198 (74) |
| KENDUJHAR | +0.0000 (7) | +0.0625 (7) |
| KORAPUT | -0.0085 (144) | -0.0072 (144) |

## Inputs: each scores file's stand layers, by SHA-256

| Scores file | Run | SHA-256 |
|---|---|---|
| hand-crafted, 10 ha (_r9) | `odisha_v120_10ha_squares_angul_keptland_s1desc_r9` | `ba9e0b37b574a99dd8a70211b190a731a8379e79deef80835a9fa2888c8a9955` |
| hand-crafted, 10 ha (_r9) | `odisha_v120_10ha_squares_dhenkanal_keptland_s1desc_r9` | `f07a6932dcae01b285995f1540f6a465765995bfcecc393e6e568101c5fd6091` |
| hand-crafted, 10 ha (_r9) | `odisha_v120_10ha_squares_kendujhar_keptland_s1desc_r9` | `b1e2e23e9693d2be796e181813dfdd4005530afba2bed44cea71a5afb52f863e` |
| hand-crafted, 10 ha (_r9) | `odisha_v120_10ha_squares_koraput_keptland_s1desc_r9` | `85af0e0dfb9a7250266159811193f38d8f0705784d54d194f046259bca2ee678` |
| hand-crafted, 10 ha (_r9) | `odisha_v120_3ha_squares_angul` | `8f9eb3efd28df919a3c037256851f95e817e799b843f7a4cd19d67d1ce8dcb06` |
| hand-crafted, 10 ha (_r9) | `odisha_v120_3ha_squares_dhenkanal` | `a2afbc6481abb455c6d5d4a4698ff4d335541895796012acab4e9364d2ffb771` |
| hand-crafted, 10 ha (_r9) | `odisha_v120_3ha_squares_kendujhar` | `5d2b1d2d61d115bd18214931027a5c5967bfbe78f91f9c2ffb5b5ef42fb8615e` |
| hand-crafted, 10 ha (_r9) | `odisha_v120_3ha_squares_koraput` | `6d9ebeb5689219d1ef86722c8479a4465f8c18f68e470ff5ed5555024f089fc1` |
| hand-crafted, 10 ha (R3) | `odisha_v120_10ha_squares_angul_keptland_s1desc_r14` | `0603f79b4b02b1cbdc2039fe07baa2a991f123502e045e605fca3865ba33f1fb` |
| hand-crafted, 10 ha (R3) | `odisha_v120_10ha_squares_dhenkanal_keptland_s1desc_r14` | `339093df42227e8dff21378403a3e09ca94321792ad90b9b1b124a7a73b73295` |
| hand-crafted, 10 ha (R3) | `odisha_v120_10ha_squares_kendujhar_keptland_s1desc_r14` | `0ff6342da8489a7f388ae0f9f8fe63861fbd2eebffbf976fd588cd706f93150c` |
| hand-crafted, 10 ha (R3) | `odisha_v120_10ha_squares_koraput_keptland_s1desc_r14` | `7cdd3345d89a6ca0682b6d7c920646e15d14573b7161501355fdc6e1d2918632` |
| hand-crafted, 10 ha (R3) | `odisha_v120_3ha_squares_angul` | `8f9eb3efd28df919a3c037256851f95e817e799b843f7a4cd19d67d1ce8dcb06` |
| hand-crafted, 10 ha (R3) | `odisha_v120_3ha_squares_dhenkanal` | `a2afbc6481abb455c6d5d4a4698ff4d335541895796012acab4e9364d2ffb771` |
| hand-crafted, 10 ha (R3) | `odisha_v120_3ha_squares_kendujhar` | `5d2b1d2d61d115bd18214931027a5c5967bfbe78f91f9c2ffb5b5ef42fb8615e` |
| hand-crafted, 10 ha (R3) | `odisha_v120_3ha_squares_koraput` | `6d9ebeb5689219d1ef86722c8479a4465f8c18f68e470ff5ed5555024f089fc1` |

## The plots each side scores

- scored (the join with the 30 m rule): 264 (hand-crafted, 10 ha (_r9)), 264 (hand-crafted, 10 ha (R3)), 264 in both.
  - only hand-crafted, 10 ha (_r9): none
  - only hand-crafted, 10 ha (R3): none
- covered by a stand (no 30 m rule): 252 (hand-crafted, 10 ha (_r9)), 252 (hand-crafted, 10 ha (R3)), 252 in both.
  - only hand-crafted, 10 ha (_r9): none
  - only hand-crafted, 10 ha (R3): none

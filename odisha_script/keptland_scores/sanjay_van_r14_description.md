# Sanjay Van: stand counts, sizes, k and the types' shares

Written by `odisha_script/r14_sanjay_van_description.py` from the runs' committed files. Sanjay
Van has no field plots: as declared, its runs get stand counts, sizes, k and the types' shares
only (`odisha_script/PHASE_KEPTLAND_PREDECLARED.md`). Numbers only: no difference is tested.

## The runs, k and the stand counts

The stands of the merge are those of each run record's `stand_attributes`; the merged layer's
are counted by their `stand_lbl`, a stand split into pieces once.

| | hand-crafted (R3) | AlphaEarth (R3) | hand-crafted (_r9) | AlphaEarth (_r9) |
|---|---:|---:|---:|---:|
| run | `sanjay_van_baseline_keptland_r14` | `sanjay_van_alphaearth_keptland_r14` | `sanjay_van_baseline_keptland_r9` | `sanjay_van_alphaearth_keptland_r9` |
| k | 5 | 5 | 6 | 6 |
| stands (the merge) | 576 | 560 | 583 | 565 |
| of them with no pixel (0 ha) | 0 | 0 | 8 | 8 |
| of them with no polygon in the merged layer | 0 | 0 | 5 | 5 |
| stands in the merged layer | 576 | 560 | 578 | 560 |
| their polygons | 576 | 560 | 578 | 560 |
| stands split into pieces | 0 | 0 | 0 | 0 |
| stands without a type | 86 | 0 | 0 | 0 |
| the minimum size, ha (merge.min_area_ha) | 1 | 1 | 1 | 1 |
| stands below the minimum size | 387 | 386 | 394 | 391 |
| of them isolated | 387 | 386 | 392 | 391 |
| of them blocked by area | 0 | 0 | 2 | 0 |
| stands left out of the k-means fit | 301 | 386 | 389 | 386 |
| their area, ha | 31.2 | 31.98 | 34.11 | 31.74 |
| the maximum size, ha (merge.max_area_ha) | 10 | 10 | 10 | 10 |
| stands over the maximum size | 7 | 7 | 6 | 7 |

## Sizes, ha: all the stands of the merge

The stands' areas from the merge (each run record's `stand_attributes`); percentiles by
numpy's linear rule.

| | hand-crafted (R3) | AlphaEarth (R3) | hand-crafted (_r9) | AlphaEarth (_r9) |
|---|---:|---:|---:|---:|
| stands | 576 | 560 | 583 | 565 |
| smallest | 0.01 | 0.01 | 0 | 0 |
| 10th percentile | 0.01 | 0.01 | 0.01 | 0.01 |
| 25th percentile | 0.02 | 0.02 | 0.02 | 0.02 |
| 50th percentile | 0.08 | 0.08 | 0.08 | 0.08 |
| 75th percentile | 1.7325 | 1.7825 | 1.71 | 1.7 |
| 90th percentile | 5.58 | 6.17 | 5.604 | 6.158 |
| largest | 10.95 | 10.76 | 10.97 | 10.76 |
| mean | 1.4721 | 1.5141 | 1.4529 | 1.4992 |
| total | 847.92 | 847.92 | 847.05 | 847.03 |

## Sizes, ha: the stands at or above the minimum size

The stands' areas from the merge (each run record's `stand_attributes`); percentiles by
numpy's linear rule.

| | hand-crafted (R3) | AlphaEarth (R3) | hand-crafted (_r9) | AlphaEarth (_r9) |
|---|---:|---:|---:|---:|
| stands | 189 | 174 | 189 | 174 |
| smallest | 1.04 | 1 | 1.04 | 1 |
| 10th percentile | 1.218 | 1.305 | 1.19 | 1.305 |
| 25th percentile | 1.82 | 2.13 | 1.82 | 2.1325 |
| 50th percentile | 3.3 | 4.175 | 3.3 | 4.175 |
| 75th percentile | 6.59 | 6.775 | 6.59 | 6.775 |
| 90th percentile | 8.882 | 9.372 | 8.842 | 9.384 |
| largest | 10.95 | 10.76 | 10.97 | 10.76 |
| mean | 4.3137 | 4.6893 | 4.3013 | 4.6856 |
| total | 815.28 | 815.94 | 812.94 | 815.29 |

## The types' shares

Each type's stands in the merged layer and their share of its stands, and the type's area and
share of the habitat as the export pass recorded them (`cluster_distribution`, from the type
raster's pixels; a type it does not list has no pixel). The type numbers are the clustering's
labels; a type number in one run names no type in another.

### hand-crafted (R3): `sanjay_van_baseline_keptland_r14`, k = 5

| type | stands | share of the stands, % | area, ha | share of the habitat, % |
|---:|---:|---:|---:|---:|
| 0 | 211 | 36.63 | 249.81 | 29.52 |
| 1 | 45 | 7.81 | 70.32 | 8.31 |
| 2 | 22 | 3.82 | 4.97 | 0.59 |
| 3 | 95 | 16.49 | 219.07 | 25.89 |
| 4 | 117 | 20.31 | 302 | 35.69 |

### AlphaEarth (R3): `sanjay_van_alphaearth_keptland_r14`, k = 5

| type | stands | share of the stands, % | area, ha | share of the habitat, % |
|---:|---:|---:|---:|---:|
| 0 | 376 | 67.14 | 135.86 | 16.03 |
| 1 | 40 | 7.14 | 197.24 | 23.27 |
| 2 | 32 | 5.71 | 149.97 | 17.69 |
| 3 | 38 | 6.79 | 27.62 | 3.26 |
| 4 | 74 | 13.21 | 336.89 | 39.75 |

### hand-crafted (_r9): `sanjay_van_baseline_keptland_r9`, k = 6

| type | stands | share of the stands, % | area, ha | share of the habitat, % |
|---:|---:|---:|---:|---:|
| 0 | 43 | 7.44 | 75.97 | 8.96 |
| 1 | 40 | 6.92 | 72.56 | 8.56 |
| 2 | 18 | 3.11 | 32.54 | 3.84 |
| 3 | 34 | 5.88 | 12.4 | 1.46 |
| 4 | 93 | 16.09 | 193.85 | 22.87 |
| 5 | 350 | 60.55 | 460.27 | 54.3 |

### AlphaEarth (_r9): `sanjay_van_alphaearth_keptland_r9`, k = 6

| type | stands | share of the stands, % | area, ha | share of the habitat, % |
|---:|---:|---:|---:|---:|
| 0 | 34 | 6.07 | 27.52 | 3.25 |
| 1 | 25 | 4.46 | 128.99 | 15.22 |
| 2 | 31 | 5.54 | 144.63 | 17.06 |
| 3 | 23 | 4.11 | 114.07 | 13.46 |
| 4 | 61 | 10.89 | 296.87 | 35.02 |
| 5 | 386 | 68.93 | 135.52 | 15.99 |

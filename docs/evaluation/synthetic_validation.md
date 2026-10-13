# Synthetic validation of the evaluation metrics

This file is written by `scripts/evaluation_synthetic_validation.py`. Do not edit it by hand: run the script again. It holds results only, no run times and no dates.

## The answer in short

- **False alarms.** The map was made unrelated to the field data, the field data were left spatially smooth (nearby plots alike), and each test was run at the 0.05 level on 300 data sets. A sound test gives a false alarm in about 5% of them. What was measured, per way of simulating chance:
  - `free_permutation`: false-alarm rates from 0.000 to 0.990, 0.311 on average over the twelve statistics. Too high for 8 of 12: `ari_drawing` (0.990), `ari_labelling` (0.163), `mantel_stand` (0.953), `mantel_type` (0.267), `partial_mantel_stand` (0.650), `partial_mantel_type` (0.170), `anosim_type` (0.170), `permanova_type` (0.300).
  - `within_group_permutation`: false-alarm rates from 0.057 to 0.930, 0.401 on average over the twelve statistics. Too high for 10 of 12: `ari_drawing` (0.343), `pair_stand` (0.143), `mantel_stand` (0.913), `mantel_type` (0.180), `partial_mantel_stand` (0.663), `partial_mantel_type` (0.137), `anosim_stand` (0.903), `anosim_type` (0.187), `permanova_stand` (0.930), `permanova_type` (0.280).
  - `rotation`: false-alarm rates from 0.030 to 0.083, 0.059 on average over the twelve statistics. Too high for 1 of 12: `anosim_stand` (0.083).
  - `torus_translation`: false-alarm rates from 0.040 to 0.110, 0.064 on average over the twelve statistics. Too high for 2 of 12: `ari_drawing` (0.110), `mantel_stand` (0.083).
  - Fewest failures: `rotation` (1 of 12). A small p-value from a statistic x null pair marked too high does not mean the map agrees with the field: with these data it turns up that often when the map is unrelated to the field.
- **Recovery.** With a strong planted effect (effect 2: the map accounts for 73% of the variance of each measurement), not every statistic prefers the planted map: `ari_drawing` does not put the planted map above the merged one; `anosim_stand` does not put the planted map above the split one; `permanova_stand` does not put the planted map above the split one. Section 1 says why.
- **Power** with this layout, under `rotation`, on 80 data sets per effect: at effect 0.25 (the map accounts for 4% of the variance) 0 of the 11 readable statistics reach a power of 0.8; at effect 0.5 (the map accounts for 14% of the variance) 3 of the 11 readable statistics reach a power of 0.8; at effect 1 (the map accounts for 40% of the variance) 10 of the 11 readable statistics reach a power of 0.8; at effect 2 (the map accounts for 73% of the variance) 11 of the 11 readable statistics reach a power of 0.8. Section 3 has every cell.
- **Reference polygons** (section 4): the combined over- and under-segmentation measure D is best for the planted map. **No reference data** (section 5): the Global Score is best for the planted map; explained variance alone does not tell the planted map from one with every stand cut in two.
- The parameters of the generator and the rules for reading the tables were fixed before the pilot and the full run and were not changed after seeing a result. One fault in the generator was corrected before those runs; the last section says what and why.

## What was run

Command, from the repo root:

```
.venv/bin/python scripts/evaluation_synthetic_validation.py
```

`--jobs N` and `--cache-dir DIR` may be added. They change how long the run takes and nothing in the two result files.

- **Root seed**: 20261013. Data set `k` of an experiment is seeded with `numpy.random.SeedSequence(root, spawn_key=(experiment, k))` (for power: `(experiment, effect number, k)`), experiments numbered recovery 0, size 1, power 2, reference polygons 3, no reference 4. A data set is therefore the same whatever else is run, and a smaller run is the first part of a larger one.
- **Layout**: 267 plots in 20 groups (villages) in 4 super-groups (districts). Plots per group, largest first: 49, 31, 20, 14, 12, 12, 11, 11, 10, 10, 10, 10, 10, 10, 9, 8, 8, 8, 7, 7. These counts are the only thing taken from a real site: they are how many plots each village has, counted from the district and village columns of the plot table. No measurement, stand or polygon of a real site was read.
- **Numbers of data sets used**: recovery 10 (effect 2, 999 relabellings per test); size 300 (effect 0, 99 relabellings); power 80 at each of the effects 0.25, 0.5, 1, 2 (99 relabellings); reference polygons 10; no reference 10.
- **Statistics** (twelve, all one-sided: larger means the map agrees better with the field): the adjusted Rand index of field type against stand (`ari_drawing`) and against stand type within district (`ari_labelling`); the pair comparison within village and distance band (`pair_stand`, `pair_type`; bands 0, 100, 200, 400, 800 m and beyond, a property of this synthetic layout only); Mantel and partial Mantel (distance held fixed) on within-village pairs; ANOSIM and PERMANOVA within villages. "stand" statistics test where the boundaries are drawn; "type" statistics test the types given to the stands.
- **Null models** (what "chance" means): `free_permutation` shuffles the stand labels over all plots; `within_group_permutation` shuffles them inside each village; `rotation` moves each village's plots as one rigid shape to a random place and angle over the map; `torus_translation` slides the map under the plots and wraps it round at the edges. The last two keep the plots' spacing and the map's shapes; the first two do not. p = (b + 1) / (R + 1), with b of R relabellings at least as large as the observed value.

### The generated data

Each village's plots lie in a square of 4 ha per plot, at least 30 m apart. The village forest is the convex hull of its plots widened by 300 m. The planted stand map is a raster of 20 m pixels: stands are the cells nearest to the points of a 160 m grid, each point moved at random by up to 50 m (stands of about 2.6 ha). Each stand gets one of 5 types at random.

Each plot has 4 attributes: a shift shared by its village (variance 0.5), a spatially smooth part (variance 0.5, correlation falling to 37% at 200 m), independent noise (variance 0.5), and `effect` times a planted signal of variance 1. 50% of the signal comes from the stand's type (type means are drawn separately in each district, so a type number means a different forest in each) and the rest from the stand itself. At effect 0 the attributes do not depend on the map at all, but nearby plots are still alike and villages still differ. The share of an attribute's variance that the map accounts for is: 0.04 at effect 0.25, 0.14 at effect 0.5, 0.40 at effect 1, 0.73 at effect 2. Field types are k-means with 5 clusters on the robust-scaled attributes.

The four other maps: **shifted** (every boundary moved by half a stand spacing in x and y), **merged** (stands joined four at a time), **split** (every stand cut in two by a straight line; both halves keep the type), **unrelated** (a second map made the same way from an independent random stream).

**How little the plots say about stands.** On average over the recovery data sets the 267 plots fall in 213 stands; only 47 stands hold two or more plots, which gives 62 pairs of plots in the same stand out of 35,511 pairs. Everything a "stand" statistic knows comes from those pairs. The highest value `ari_drawing` could reach with these group sizes is 0.014 (not 1), because stands are much finer than field types.

## 1. Recovery: does each statistic prefer the planted map?

Effect 2, 10 data sets. Mean value of each statistic on each map (standard error over data sets in brackets).

| statistic | planted | shifted | merged | split | unrelated |
|---|---|---|---|---|---|
| `ari_drawing` | 0.008748 (0.0006) | 0.00411 (0.0004) | 0.01275 (0.0008) | 0.004481 (0.0003) | 0.00411 (0.0005) |
| `ari_labelling` | 0.1545 (0.0155) | 0.01315 (0.0040) | 0.02157 (0.0039) | 0.1545 (0.0155) | 0.006778 (0.0024) |
| `pair_stand` | 1.003 (0.0301) | -0.04277 (0.0492) | 0.1667 (0.0238) | 0.8204 (0.0300) | 0.02053 (0.0444) |
| `pair_type` | 0.3715 (0.0208) | 0.02151 (0.0180) | 0.0514 (0.0166) | 0.4006 (0.0207) | 0.001472 (0.0139) |
| `mantel_stand` | 0.2377 (0.0070) | 0.08496 (0.0065) | 0.1324 (0.0130) | 0.1693 (0.0059) | 0.09112 (0.0093) |
| `mantel_type` | 0.2795 (0.0140) | 0.03846 (0.0093) | 0.08225 (0.0126) | 0.2795 (0.0140) | 0.02909 (0.0079) |
| `partial_mantel_stand` | 0.2276 (0.0048) | 0.06988 (0.0065) | 0.113 (0.0082) | 0.1599 (0.0041) | 0.07698 (0.0062) |
| `partial_mantel_type` | 0.2774 (0.0141) | 0.03435 (0.0087) | 0.06955 (0.0117) | 0.2774 (0.0141) | 0.02436 (0.0081) |
| `anosim_stand` | 0.8753 (0.0098) | 0.3034 (0.0216) | 0.2579 (0.0154) | 0.8838 (0.0099) | 0.3298 (0.0302) |
| `anosim_type` | 0.3882 (0.0189) | 0.04994 (0.0161) | 0.1152 (0.0135) | 0.3882 (0.0189) | 0.037 (0.0124) |
| `permanova_stand` | 7.176 (0.2986) | 1.564 (0.0620) | 1.71 (0.0768) | 7.178 (0.3666) | 1.628 (0.0950) |
| `permanova_type` | 3.328 (0.1297) | 1.204 (0.0461) | 1.556 (0.0427) | 3.328 (0.1297) | 1.186 (0.0545) |

Share of data sets in which the planted map scores strictly above each other map, and share in which the planted map is rejected at 0.05 ("no agreement" is rejected, 999 relabellings).

| statistic | above shifted | above merged | above split | above unrelated | rejected, within_group_permutation | rejected, rotation |
|---|---|---|---|---|---|---|
| `ari_drawing` | 1.00 | 0.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| `ari_labelling` | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | 1.00 |
| `pair_stand` | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| `pair_type` | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | 1.00 |
| `mantel_stand` | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| `mantel_type` | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | 1.00 |
| `partial_mantel_stand` | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| `partial_mantel_type` | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | 1.00 |
| `anosim_stand` | 1.00 | 1.00 | 0.40 | 1.00 | 1.00 | 1.00 |
| `anosim_type` | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | 1.00 |
| `permanova_stand` | 1.00 | 1.00 | 0.50 | 1.00 | 1.00 | 1.00 |
| `permanova_type` | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | 1.00 |

Expectations, declared before the run. "Above" means in at least 90% of the data sets.

1. Planted above unrelated, shifted and merged, for all twelve statistics: **NOT met**. Not above: `ari_drawing` against merged (0.00).
2. Planted above split, for the six "stand" statistics: **NOT met**. Not above: `anosim_stand` (0.40), `permanova_stand` (0.50).
3. `ari_labelling` exactly equal on planted and split (splitting a stand leaves every plot's type as it was): **met**. The other "type" statistics are not expected to separate planted from split either; that is not a failure.
4. The planted map rejected in at least 90% of data sets, every statistic, both nulls: **met**.

Why, for the expectations not met:

- `ari_drawing` scores the merged map (stands four times too large) ABOVE the planted one in every data set (0.0128 against 0.0087). This is a property of the adjusted Rand index, not a fault in the code (the index is checked against scikit-learn's in the unit tests). The index compares the stands and the field types as two groupings of equal standing. With stands far finer than field types, its size is set mostly by how many pairs of plots share a stand. Larger stands put more pairs together, a fair number of them are of one field type, and the index goes up although 41% of the planted boundary length is gone (section 4). So `ari_drawing` must not be used to compare maps with different stand sizes, and its value says little on its own. As a test against chance it still works (expectation 4 and section 3).
- `anosim_stand`, `permanova_stand` do not score the planted map above the split one (0.875 against 0.884; 7.176 against 7.178). This too is a property of the statistics. They ask whether plots in the same stand are more alike than plots in different stands of the village. Cutting a stand in two leaves each half as pure as the whole, so they lose nothing. They cannot see a boundary that should not be there (over-segmentation). `pair_stand` and the Mantel statistics do fall under splitting, because the two halves of a stand now count as "different stands" and are alike.

## 2. Size: false alarms when the map is unrelated to the field

Effect 0, 300 data sets, 99 relabellings per test. Each cell is the share of data sets with p <= 0.05, with its 95% Wilson interval. A sound test gives 0.05. Declared rule: **too high** if the whole interval lies above 0.05; otherwise acceptable (marked "below" if the whole interval lies under 0.05: the test is then cautious, which costs power but not honesty).

| statistic | free_permutation | within_group_permutation | rotation | torus_translation |
|---|---|---|---|---|
| `ari_drawing` | 0.990 [0.971, 0.997] **too high** | 0.343 [0.292, 0.399] **too high** | 0.063 [0.041, 0.097] | 0.110 [0.079, 0.150] **too high** |
| `ari_labelling` | 0.163 [0.126, 0.209] **too high** | 0.073 [0.049, 0.109] | 0.057 [0.036, 0.089] | 0.067 [0.044, 0.101] |
| `pair_stand` | 0.000 [0.000, 0.013] below | 0.143 [0.108, 0.188] **too high** | 0.053 [0.033, 0.085] | 0.040 [0.023, 0.069] |
| `pair_type` | 0.067 [0.044, 0.101] | 0.057 [0.036, 0.089] | 0.060 [0.038, 0.093] | 0.053 [0.033, 0.085] |
| `mantel_stand` | 0.953 [0.923, 0.972] **too high** | 0.913 [0.876, 0.940] **too high** | 0.070 [0.046, 0.105] | 0.083 [0.057, 0.120] **too high** |
| `mantel_type` | 0.267 [0.220, 0.319] **too high** | 0.180 [0.141, 0.227] **too high** | 0.053 [0.033, 0.085] | 0.070 [0.046, 0.105] |
| `partial_mantel_stand` | 0.650 [0.594, 0.702] **too high** | 0.663 [0.608, 0.714] **too high** | 0.060 [0.038, 0.093] | 0.073 [0.049, 0.109] |
| `partial_mantel_type` | 0.170 [0.132, 0.217] **too high** | 0.137 [0.102, 0.180] **too high** | 0.063 [0.041, 0.097] | 0.063 [0.041, 0.097] |
| `anosim_stand` | 0.000 [0.000, 0.013] below | 0.903 [0.865, 0.932] **too high** | 0.083 [0.057, 0.120] **too high** | 0.057 [0.036, 0.089] |
| `anosim_type` | 0.170 [0.132, 0.217] **too high** | 0.187 [0.147, 0.235] **too high** | 0.053 [0.033, 0.085] | 0.057 [0.036, 0.089] |
| `permanova_stand` | 0.007 [0.002, 0.024] below | 0.930 [0.895, 0.954] **too high** | 0.067 [0.044, 0.101] | 0.050 [0.031, 0.081] |
| `permanova_type` | 0.300 [0.251, 0.354] **too high** | 0.280 [0.232, 0.333] **too high** | 0.030 [0.016, 0.056] | 0.047 [0.028, 0.077] |

Monte Carlo error: a true rate of 0.05 measured on 300 data sets has a standard error of 0.013. A sound test is marked too high by this rule in 2.9% of runs. So if all 48 tests were sound, about 1.4 marks would be expected in the whole table and about 0.4 in one column (fewer than these counts suggest are independent, because the twelve statistics share data sets). One isolated "too high" among acceptable neighbours is weak evidence; a whole column is not.

Reading:

- `free_permutation`: **not sound** for `ari_drawing`, `ari_labelling`, `mantel_stand`, `mantel_type`, `partial_mantel_stand`, `partial_mantel_type`, `anosim_type`, `permanova_type`; acceptable for `pair_stand`, `pair_type`, `anosim_stand`, `permanova_stand`.
- `within_group_permutation`: **not sound** for `ari_drawing`, `pair_stand`, `mantel_stand`, `mantel_type`, `partial_mantel_stand`, `partial_mantel_type`, `anosim_stand`, `anosim_type`, `permanova_stand`, `permanova_type`; acceptable for `ari_labelling`, `pair_type`.
- `rotation`: **not sound** for `anosim_stand`; acceptable for `ari_drawing`, `ari_labelling`, `pair_stand`, `pair_type`, `mantel_stand`, `mantel_type`, `partial_mantel_stand`, `partial_mantel_type`, `anosim_type`, `permanova_stand`, `permanova_type`.
- `torus_translation`: **not sound** for `ari_drawing`, `mantel_stand`; acceptable for `ari_labelling`, `pair_stand`, `pair_type`, `mantel_type`, `partial_mantel_stand`, `partial_mantel_type`, `anosim_stand`, `anosim_type`, `permanova_stand`, `permanova_type`.

Average false-alarm rate over the twelve statistics: `free_permutation` 0.311, `within_group_permutation` 0.401, `rotation` 0.059, `torus_translation` 0.064. (The twelve are computed on the same data sets, so they rise and fall together and this average is not twelve times as precise as one cell; its standard error is somewhere between 0.004 and 0.013.)

What lies behind these numbers. The first five points are reasoning from how the data were generated and how the statistics are defined; no separate experiment was run to prove each one.

- **Shuffling over all plots** treats a plot in one village as interchangeable with a plot in another. Villages differ, and a stand lies in one village, so any statistic that looks across villages finds "agreement" that is only the village difference (`ari_drawing`: 0.990). For the stand statistics that work inside villages it fails the other way (`pair_stand` 0.000, `anosim_stand` 0.000): after such a shuffle hardly any two plots of a village share a stand, the shuffled values swing wildly, and the real value almost never stands out. Neither is a usable test.
- **Shuffling inside villages** removes the village difference but not the smoothness. Two plots in the same stand are close together, and close plots are alike whatever the map says. The shuffle breaks that link, so the real map looks better than chance: `mantel_stand` 0.913, `anosim_stand` 0.903, `permanova_stand` 0.930.
- **Holding distance fixed does not cure it.** The partial Mantel statistic still gives 0.663 under the within-village shuffle, and the pair comparison inside distance bands 0.143: better, not sound. Inside a distance band the same-stand pairs are still the closer ones. This is the warning of Guillot and Rousset (2013, doi:10.1111/2041-210x.12018) about Mantel tests on spatially smooth data, seen here for the other statistics as well.
- **Type statistics** built from Mantel, ANOSIM and PERMANOVA also fail under the within-village shuffle (`mantel_type` 0.180, `anosim_type` 0.187, `permanova_type` 0.280), because their "same type" pairs include the pairs in the same stand, which are the close ones. `pair_type` leaves same-stand pairs out and holds (0.057); `ari_labelling` gives 0.073.
- **The torus translation** wraps the map round at the edges of each village's raster. The raster is not much larger than the plot layout, so many shifts put the seam through the plots, and plots that are neighbours on the ground are read from opposite edges of the map. That is the likely reason it gives 0.110 for `ari_drawing`. It is offered for comparison with the published method (Harms et al. 2001, doi:10.1111/j.1365-2745.2001.00615.x), not as the default.
- **The rotation null** moves each village's plots as one rigid shape, so close plots stay close and land in the same stand about as often as they really do. Its rates run from 0.030 to 0.083, and by the declared rule `anosim_stand` (0.083) is marked too high. If the rotation null were exactly sound, about 0.4 such marks would be expected among its twelve cells, so one mark is not surprising but is not nothing either. The other statistics under this null are within error of 0.05, and this run cannot say whether that excess is real. The rotation null is not exact in theory: the placements it may use are crowded round the real one, so the real placement is not just one more draw, and a small excess of false alarms is possible. The average over the twelve (0.059) is a little above 0.05 and the same caution applies. It is reported as measured; more data sets under this null alone would settle it.

## 3. Power: how much planted agreement is needed

80 data sets per effect, 99 relabellings per test. Each cell is the share of data sets with p <= 0.05. A cell in brackets belongs to a statistic whose false-alarm rate under that null was too high in section 2: its "power" is partly false alarms and must not be read as power.

### `free_permutation`

| statistic | effect 0.25 | effect 0.5 | effect 1 | effect 2 | smallest effect with power >= 0.8 |
|---|---|---|---|---|---|
| `ari_drawing` | (0.99) | (1.00) | (1.00) | (1.00) | not read |
| `ari_labelling` | (0.33) | (0.80) | (1.00) | (1.00) | not read |
| `pair_stand` | 0.00 | 0.00 | 0.45 | 1.00 | 2 |
| `pair_type` | 0.25 | 0.79 | 1.00 | 1.00 | 1 |
| `mantel_stand` | (0.99) | (1.00) | (1.00) | (1.00) | not read |
| `mantel_type` | (0.53) | (0.95) | (1.00) | (1.00) | not read |
| `partial_mantel_stand` | (0.80) | (1.00) | (1.00) | (1.00) | not read |
| `partial_mantel_type` | (0.40) | (0.94) | (1.00) | (1.00) | not read |
| `anosim_stand` | 0.00 | 0.07 | 0.76 | 1.00 | 2 |
| `anosim_type` | (0.45) | (0.95) | (1.00) | (1.00) | not read |
| `permanova_stand` | 0.03 | 0.19 | 0.93 | 1.00 | 1 |
| `permanova_type` | (0.64) | (0.97) | (1.00) | (1.00) | not read |

### `within_group_permutation`

| statistic | effect 0.25 | effect 0.5 | effect 1 | effect 2 | smallest effect with power >= 0.8 |
|---|---|---|---|---|---|
| `ari_drawing` | (0.57) | (0.76) | (0.97) | (1.00) | not read |
| `ari_labelling` | 0.23 | 0.70 | 1.00 | 1.00 | 1 |
| `pair_stand` | (0.26) | (0.84) | (1.00) | (1.00) | not read |
| `pair_type` | 0.20 | 0.78 | 1.00 | 1.00 | 1 |
| `mantel_stand` | (0.97) | (1.00) | (1.00) | (1.00) | not read |
| `mantel_type` | (0.42) | (0.93) | (1.00) | (1.00) | not read |
| `partial_mantel_stand` | (0.76) | (1.00) | (1.00) | (1.00) | not read |
| `partial_mantel_type` | (0.36) | (0.93) | (1.00) | (1.00) | not read |
| `anosim_stand` | (0.97) | (1.00) | (1.00) | (1.00) | not read |
| `anosim_type` | (0.45) | (0.94) | (1.00) | (1.00) | not read |
| `permanova_stand` | (0.99) | (1.00) | (1.00) | (1.00) | not read |
| `permanova_type` | (0.62) | (0.97) | (1.00) | (1.00) | not read |

### `rotation`

| statistic | effect 0.25 | effect 0.5 | effect 1 | effect 2 | smallest effect with power >= 0.8 |
|---|---|---|---|---|---|
| `ari_drawing` | 0.07 | 0.23 | 0.79 | 1.00 | 2 |
| `ari_labelling` | 0.16 | 0.66 | 1.00 | 1.00 | 1 |
| `pair_stand` | 0.14 | 0.62 | 1.00 | 1.00 | 1 |
| `pair_type` | 0.16 | 0.72 | 1.00 | 1.00 | 1 |
| `mantel_stand` | 0.15 | 0.74 | 1.00 | 1.00 | 1 |
| `mantel_type` | 0.20 | 0.82 | 1.00 | 1.00 | 0.5 |
| `partial_mantel_stand` | 0.14 | 0.75 | 1.00 | 1.00 | 1 |
| `partial_mantel_type` | 0.20 | 0.82 | 1.00 | 1.00 | 0.5 |
| `anosim_stand` | (0.11) | (0.64) | (1.00) | (1.00) | not read |
| `anosim_type` | 0.20 | 0.76 | 1.00 | 1.00 | 1 |
| `permanova_stand` | 0.14 | 0.79 | 1.00 | 1.00 | 1 |
| `permanova_type` | 0.23 | 0.85 | 1.00 | 1.00 | 0.5 |

### `torus_translation`

| statistic | effect 0.25 | effect 0.5 | effect 1 | effect 2 | smallest effect with power >= 0.8 |
|---|---|---|---|---|---|
| `ari_drawing` | (0.16) | (0.36) | (0.86) | (1.00) | not read |
| `ari_labelling` | 0.17 | 0.65 | 1.00 | 1.00 | 1 |
| `pair_stand` | 0.12 | 0.66 | 1.00 | 1.00 | 1 |
| `pair_type` | 0.15 | 0.75 | 1.00 | 1.00 | 1 |
| `mantel_stand` | (0.15) | (0.78) | (1.00) | (1.00) | not read |
| `mantel_type` | 0.19 | 0.84 | 1.00 | 1.00 | 0.5 |
| `partial_mantel_stand` | 0.14 | 0.78 | 1.00 | 1.00 | 1 |
| `partial_mantel_type` | 0.19 | 0.84 | 1.00 | 1.00 | 0.5 |
| `anosim_stand` | 0.09 | 0.56 | 1.00 | 1.00 | 1 |
| `anosim_type` | 0.25 | 0.81 | 1.00 | 1.00 | 0.5 |
| `permanova_stand` | 0.10 | 0.74 | 1.00 | 1.00 | 1 |
| `permanova_type` | 0.25 | 0.86 | 1.00 | 1.00 | 0.5 |

Monte Carlo error: with 80 data sets the standard error of a power is at most 0.056 (at a power of 0.5), so differences between two cells of less than about 0.16 are not established.

For scale, the share of an attribute's variance that the planted map accounts for is 4% at effect 0.25, 14% at effect 0.5, 40% at effect 1, 73% at effect 2. That share counts the differences between villages. The pair comparison, Mantel, ANOSIM and PERMANOVA statistics work inside villages, where the village shift plays no part; inside a village the map's share is 6% at effect 0.25, 20% at effect 0.5, 50% at effect 1, 80% at effect 2.

## 4. Reference polygons: segmentation accuracy against the planted polygons

10 data sets; in each, the planted map (as polygons) of each of the first 4 villages is the reference and each of the five maps is scored against it; the figure is the mean over those villages, then over data sets. (These measures look at maps, not plots, so the plot layout does not matter to them; a few villages keep the cost down.) Over- and under-segmentation and their combination D are 0 for a perfect match (lower is better). Boundary precision, recall and F are 1 for a perfect match (higher is better), with a tolerance of 20 m (one pixel) and the outer edge of the raster left out.

| measure | planted | shifted | merged | split | unrelated |
|---|---|---|---|---|---|
| `over` | 0.000 | 0.579 | 0.000 | 0.467 | 0.459 |
| `under` | 0.000 | 0.579 | 0.676 | 0.000 | 0.461 |
| `d` | 0.000 | 0.607 | 0.478 | 0.330 | 0.492 |
| `boundary_precision` | 1.000 | 0.347 | 1.000 | 0.735 | 0.523 |
| `boundary_recall` | 1.000 | 0.349 | 0.590 | 1.000 | 0.523 |
| `boundary_f` | 1.000 | 0.348 | 0.741 | 0.847 | 0.523 |

Expectations, declared before the run:

1. The planted map scores a perfect match (0, 0, 0 and F = 1): **met**.
2. Every other map has a worse D and a worse boundary F: **met**.
   Note the unrelated map: boundary F 0.523, D 0.492. A map that has nothing to do with the reference still gets these, because with stands this small a good share of any boundary lies within one pixel of some reference boundary. These measures need that baseline beside them; 0 and 1 are not the values of a useless map.
3. Splitting shows as over-segmentation and not as under-segmentation: **met**. Merging shows as under-segmentation and not as over-segmentation: **met**.

## 5. No reference data: likeness inside stands

10 data sets; in each of the first 4 villages a raster layer of 2 bands is generated that follows the planted map (stand means of variance 1, pixel noise of variance 1), and the five maps are scored on it as one declared set of candidates. Explained variance (`r2`): higher is better. Area-weighted variance, Moran's I between adjacent stands and the Global Score: lower is better. `n_segments` is the mean number of stands per village raster.

| measure | planted | shifted | merged | split | unrelated |
|---|---|---|---|---|---|
| `r2` | 0.495 | 0.172 | 0.144 | 0.505 | 0.234 |
| `weighted_variance` | 0.978 | 1.617 | 1.672 | 0.960 | 1.495 |
| `morans_i` | -0.024 | 0.276 | -0.040 | 0.155 | 0.191 |
| `global_score` | 0.174 | 1.892 | 1.124 | 0.663 | 1.483 |
| `n_segments` | 64.400 | 65.325 | 20.625 | 121.100 | 64.875 |
| `pixel_ari_with_planted` | 1.000 | 0.304 | 0.412 | 0.681 | 0.439 |

Expectations, declared before the run:

1. The Global Score is best (lowest) for the planted map: **met**.
2. Explained variance is higher for the planted map than for the shifted, merged and unrelated maps: **met**.
3. Explained variance does NOT prefer the planted map to the split one (cutting stands in two can only raise it, because it rises with the number of stands whatever the layer): **met**. This is a property of the measure and the reason it is never read without the number of stands. Moran's I is what catches the split: the two halves of a stand are alike (0.155 against -0.024 for the planted map).
4. `pixel_ari_with_planted` is the adjusted Rand index between each map and the planted map, pixel against pixel. It is 1 for the planted map against itself: **met**. Note the unrelated map: 0.439, not 0. Two maps of compact stands of the same size share many pairs of neighbouring pixels by geometry alone, and the index's allowance for chance knows nothing about geometry. When two stand maps are compared pixel by pixel with this index, the value to beat is the one an unrelated map of the same grain gets, not 0.

## What this does and does not show

- **Checked in every data set**: each null model starts from exactly the stand and type labels the statistic was observed on. This held throughout.
- **Nothing was tuned.** The generator, its parameters, the distance bands, the numbers of relabellings and the rules used to read the tables (too high, recovered, power of 0.8) were fixed before the run. Where an expectation is marked NOT met, that is reported as a finding; the generator was not changed to make it go away.
- **One fault in the generator was corrected, before the pilot and the full run.** In the first draft the planted map and the "unrelated" map of a village were built on the same grid of seed points and differed only by the random jitter of each point, so the unrelated map was not unrelated. It was noticed while writing a unit test that compares the two rasters. Each map's grid now sits at its own random place. The change was made because the map did not mean what its name says, not because of any score, and the small trial run made before it is used nowhere in this file.
- **One synthetic world.** The rates hold for this layout, this stand size, this smoothness and this mix of village, smooth and noise variance. A real site with stands much larger or smaller than the plot spacing, or smoother field data, can behave differently. Sensitivity to those parameters was not run.
- **The village forest is generous here.** It is the hull of the plots widened by 300 m, and every pixel in it has a stand. A real village forest can be thin or full of holes, which leaves the rotation null few places to move the plots to. How the rotation null behaves then was not tested.
- **99 relabellings** per test in the size and power experiments. That puts 0.05 exactly on a possible p-value (the 5 largest of 100), so no rate here is off because of rounding; whether a test is sound still depends on its null model. A real analysis would use more, and its power would be slightly higher.
- **Not validated here**: Holm's correction across several tests; the Spearman form of the Mantel statistics; ANOSIM with equal village weights; the all-pairs Mantel test (without villages); polygon stand maps under the rotation null (rasters were used); plots that fall outside any stand; missing measurements. These are covered by unit tests with known answers, not by this study.
- **Not a result about any real site.** No metric was run on real data, and nothing here says whether a real map agrees with real field data.

# Phase 3 summary deck: the single source of numbers

Every number the deck may quote is here, with where it comes from and how to say it.
If a number is not on this page, it does not go in the deck.

Conventions:
- "file:N" means line N of that file (all paths relative to `odisha_script/` unless they start with `configs/`, `aois/` or `docs/`).
- "computed" means a one-off calculation made for this deck. The script is quoted so it can be re-run from the repo root with `.venv/bin/python`. None of them write inside the repo.
- Scratch scripts used for this page: `stands.py`, `field.py`, `bench.py`, `dump_nulls.py` in the session scratchpad (`.../scratchpad/deck/`). What each one computes is given at the point of use.
- Two stand-size arms: **"stands up to 10 hectares"** (`configs/odisha_v120_handcrafted_<district>.yaml`, joined table `phase2_plots_joined_districts.csv`, columns `v120_*`) and **"stands up to 3 hectares"** (`configs/odisha_v120_3ha_<district>.yaml`, joined table `phase3_3ha/phase2_plots_joined_districts.csv`, columns `v120_3ha_*`).

---

## 1. The field data

| Fact | Value | Source | Say it like this |
|---|---|---|---|
| Plant records in the raw field sheet | **5,910** | `Odisha_samples.csv`: `len(pd.read_csv(...))` = 5910; also `odisha_phase2_3_results_districts.txt:5` ("records: 5910 raw") | "5,910 plant records" |
| ...of which trees | 2,872 raw; **2,729** after the location filter | raw: `Odisha_samples.csv` `Habit` counts (Tree 2872, SaplingSeedling 1613, Shrub 964, Climber 286+5, Stump 169, Seedling 1); filtered: `odisha_phase2_3_results_districts.txt:6` | "about 2,700 of them are trees; the rest are saplings, shrubs, climbers and stumps" |
| Records kept after the location (GPS) filter | 5,679 | `odisha_phase2_3_results_districts.txt:5` | speaker notes only |
| Field plots | **274** | `odisha_phase3_0_results.txt:4`; `phase2_plots_joined_districts.csv` has 274 rows | "274 field plots" |
| Plots per district (all 274) | Koraput **146**, Dhenkanal **76**, Angul **40**, Kendujhar **12** | computed: `p.district.value_counts()` on `phase2_plots_joined_districts.csv` | as is |
| Districts | **4** (Angul, Dhenkanal, Kendujhar, Koraput) | same table | "four districts of Odisha" |
| Village forests (separate study-area polygons) | **20**: Angul 4, Dhenkanal 8, Kendujhar 1, Koraput 7 | `odisha_phase3_3_results.txt:24` ("villages: 20"); per district computed: exploded parts of `aois/odisha_habitations_<district>.geojson` = 4 / 8 / 1 / 7 | "20 village forests" |
| Named habitations in the field sheet | 30 (Angul 5, Dhenkanal 12, Kendujhar 3, Koraput 10) | computed: `p.habitation.nunique()` and per district | speaker notes only; the deck unit is the 20 village forests (several habitations share one forest polygon) |
| Study-area size | Angul 439, Dhenkanal 995, Kendujhar 405, Koraput 2,468 hectares; **about 4,300 hectares** in total | computed: area of the exploded AOI parts in UTM 45N (`field.py`) | "about 4,300 hectares of village forest" |
| Plots inside the study areas (scored) | **267**: Koraput 145, Dhenkanal 75, Angul 39, Kendujhar 8 | `odisha_phase3_3_results.txt:24`; per district `odisha_phase3_1_score_v120_merged_districts.txt:42-45` | "267 of the 274 plots fall inside the mapped village forests; these are the ones I score" |
| Plots per village forest (of the 267) | smallest 5, median 10, largest 59 | computed: `plots.aoi_part.value_counts()` after `odisha_phase3_3_significance.load_all()` (`bench.py`) | "most village forests hold about 10 plots" |
| Plot pairs scored | **35,511** (= 267 x 266 / 2) | `odisha_phase3_1_score_v120_merged_districts.txt:19` | "35,511 pairs of plots" |
| Survey dates | **25 April 2022 to 5 April 2023** | computed: min/max of `Creation Date` in `Odisha_samples.csv`; also `PHASE1_STATUS.md:198` | "surveyed between April 2022 and April 2023" |
| Plot radius | **still unknown**; asked of the field team (FES), not yet answered | `docs/phase1_supervisor_memo.md:178`; `odisha_phase3_0_results.txt:6-8` | "we do not yet know the plot size, so trunk area is a per-plot total, not per hectare" |
| Species recorded | 179 (after cleaning names) | `odisha_phase2_3_results_districts.txt:7`; `explain_field_types.py` output ("274 plots x 179 species") | "179 species" |

## 2. Why species could not sort the forests

Source: `python odisha_script/explain_field_types.py` (run from `odisha_script/`; output reproduced for this page).

| Fact | Value | Say it like this |
|---|---|---|
| Plots in the biggest species group | **259 of 274 (94.5%)** | "Grouping by species put 259 of 274 plots in one group" |
| The other 15 | split into 5 tiny groups (11, 1, 1, 1, 1) | |
| What the 15 are | **13 are scrub or bushland** under 5 metres tall (10 in Koraput; top species lantana, bael, cipadessa, "indirabuta" shrub, vitex, date palm, salai); **2** are ordinary low forest led by an unusual species (Angul, 10.4 m, Bridelia; Dhenkanal, 9.3 m, Cassia fistula) | "The 15 that broke away are almost all scrub, not a different kind of forest" |
| Average share of Sal in a plot's trunk area | **12.1%** | "Sal makes up only about an eighth of the trunk area in an average plot" |
| Next most common | mango 9.2%, jamun 8.3%, kendu 4.4% | "mango and jamun are everywhere" |
| Plots with any Sal / Sal-dominated (over half the trunk area) | 80 / 32 of 274 | computed from `sal_ba_frac` | "only 32 plots are Sal-dominated" |

Method, for notes: average-linkage clustering on Bray-Curtis dissimilarity of relative trunk area, cut at 6 groups (`explain_field_types.py:18,43-45`).

## 3. The five forest types from structure (the "truth" used for scoring)

Source: `odisha_phase3_0_results.txt` (script `odisha_phase3_0_field_structure_types.py`); medians recomputed from `odisha_phase3_0_field_types.csv` + trunk area from `sp_ba_json` (`bench.py`). Inputs: average tree height (Lorey's height), crown cover, trunk area (log of plot total), number of trees; robust scaling; automatic grouping (k-means, seed 42).

| Plain name (`phase3_figstyle.TYPE_NAME`) | Type no. | Plots (all 274) | Plots (267 scored) | Median height | Median crown cover | Median trees per plot | Median trunk area per plot |
|---|---|---|---|---|---|---|---|
| Scrub (almost no trees) | 2 | **20** | 18 | **1.4 m** | **1%** (1.25) | **0** | 27 cm² |
| Low forest, few trees | 4 | **114** | 111 | **7.0 m** | **40%** (40.5) | **6.5** | 688 cm² |
| Low forest, many trees | 0 | **78** | 77 | **7.8 m** | **33%** | **14** | 2,990 cm² |
| Tall forest, few big trees | 1 | **47** | 46 | **18.1 m** | **48%** | **8** | 3,005 cm² |
| Tall forest, many trees | 3 | **15** | 15 | **15.3 m** | **48%** | **29** | 5,576 cm² |

Lines: sizes and medians `odisha_phase3_0_results.txt:37-43`; 267-plot counts `odisha_phase3_3_results.txt:24`. Note the results file prints the "few trees" median as 6 (integer cut); the true median is 6.5. Scrub height is 1.4 m because height there is measured on shrubs and saplings, not trees.

- Largest type holds 114 of 274 (41.6%) against 94.5% for species: `odisha_phase3_0_results.txt:44`. Say: "structure spreads the plots across five types instead of one".
- Types by district (`odisha_phase3_0_results.txt:47-52`): Koraput is mostly low forest (75 low-few + 53 low-many of 146); Dhenkanal has most of the tall forest (30 tall-few-big + 8 tall-many of 76).

**Choosing five** (`odisha_phase3_0_results.txt:13-32`), all from field data only, tried 2 to 12 types:

| Rule | Picks | Line |
|---|---|---|
| Elbow (bend in the within-group spread curve) | **5**, used | :26 |
| Silhouette (best separation) | 3 (score 0.350) | :27 |
| Calinski-Harabasz | 9 | :28 |
| Davies-Bouldin | 8 | :29 |

Say: "I used the elbow rule, which is the one my supervisor asked for. The other rules disagree (3, 8 and 9), so the number of types is a choice, not a fact of the data." Sensitivity: adding average trunk diameter keeps the elbow at 5 (:54).

## 4. How many stand types (from the satellite features)

Source: `odisha_phase3_2_k_elbow_odisha_v120_handcrafted.txt`, computed on the 10-hectare arm's stands, 22 satellite features, no field data (:6-7).

| Where | Elbow picks | Line |
|---|---|---|
| Angul (99 stands) | 6 | :12 |
| Dhenkanal (232) | 6 | :13 |
| Kendujhar (108) | 6 | :14 |
| Koraput (629) | **5** | :15 |
| All four districts together (1,068) | **5** | :20 |
| Middle value of those five answers | **6**, the value already in use | :40-41 |

- Silhouette over all districts peaks at **0.212 (at 4 types)**: `:25`. Silhouette runs from -1 to 1; 0.21 means the stand types are only weakly separated.
- CORRECTION to the brief: the elbow is **not** 6 "per district and pooled". It is 6 in three districts and 5 in Koraput and pooled; 6 is the middle value. Say: "The elbow rule points to 5 or 6 stand types in every district; the middle answer is 6, which is what the method already used."
- The "stands" counts on this line (99/232/108/629 = 1,068) are map-polygon counts (see section 5).

## 5. The stands

Source: computed from `phase2_vectors/odisha_v120_{handcrafted,3ha}_<district>_stands_{merged,snic}.geojson` (`stands.py`). Stand area = `area_ha` summed over polygons sharing a stand label (`stand_lbl` for stands, `snic_label` for patches), which is how the join identifies a stand (`odisha_phase2_3_join.py:126-127`).

**Definitions.**
- *Map polygons* = features in the stand file. A few stands appear as two features because a single stray 10-metre pixel sits beside the stand (checked in Angul: the 3 duplicate labels are each one 1-pixel sliver 10-20 m from its stand).
- *Stands* = distinct stand labels per district. **Use this count in the deck.**
- *Small patches* = the building blocks (superpixels) that stands are joined from.

### Stand counts

| District | 10 hectares: polygons | 10 hectares: stands | 3 hectares: polygons | 3 hectares: stands |
|---|---|---|---|---|
| Angul | 99 | 96 | 203 | 200 |
| Dhenkanal | 232 | 224 | 473 | 462 |
| Kendujhar | 108 | 105 | 186 | 183 |
| Koraput | 629 | 614 | 1,131 | 1,109 |
| **Total** | **1,068** | **1,039** | **1,993** | **1,954** |

Say: "Capping stands at 3 hectares roughly doubles the number of stands, from about 1,040 to about 1,950."

Stands that hold at least one plot (from the scorers): 144 (10 hectares), 198 (3 hectares): `odisha_phase3_1_score_v120_merged_districts.txt:6`, `odisha_phase3_1_score_v120_3ha_merged_districts_3ha.txt:6`.

### Stand size (all four districts, by stand)

| | Median | 9 in 10 stands are smaller than | Largest | Share over 3 hectares |
|---|---|---|---|---|
| Up to 10 hectares | **3.09 hectares (say "about 3 hectares")** | **9.18 hectares** | 10.08 hectares | **50.9%** (529 of 1,039) |
| Up to 3 hectares | **2.35 hectares** | **2.94 hectares** | 3.04 hectares | 2.1% (41 of 1,954), all by at most 0.04 hectares |

Per district medians (10 / 3 hectares): Angul 3.62 / 2.37, Dhenkanal 3.26 / 2.29, Kendujhar 2.69 / 2.36, Koraput 2.95 / 2.38. The 10-hectare median and 90th percentile match the config comment `configs/odisha_v120_3ha_angul.yaml:10`.
Say: "With the 10-hectare cap, half the stands were bigger than the 2-3 hectares my supervisor asked for. With the 3-hectare cap, practically all are within it (41 of 1,954 go over, each by less than one twentieth of a hectare)." Why they go over slightly is not established; do not explain it on a slide.

Total area in stands: 4,314 hectares in both arms (same forest, cut differently).

### Small patches and why the patch spacing changed

| | Patch spacing | Number of patches (distinct) | Median patch | 9 in 10 smaller than | Largest patch |
|---|---|---|---|---|---|
| 10-hectare arm | **10 pixels, about 100 metres** | 3,596 | 0.85 hectares | 2.00 hectares | **6.74 hectares** (Dhenkanal) |
| 3-hectare arm | **6 pixels, about 60 metres** | 9,488 | 0.32 hectares | 0.67 hectares | **2.02 hectares** (Dhenkanal) |

- Pixel = 10 metres (`analysis_scale_m: 10`, `configs/odisha_v120_handcrafted_angul.yaml:135`), so 10 pixels = 100 m and 6 pixels = 60 m. Setting: `segmentation.size` 10 (`configs/odisha_v120_handcrafted_angul.yaml:92`) -> 6 (`configs/odisha_v120_3ha_angul.yaml:99`); stand cap `merge.max_area_ha` 10.0 -> 3.0 (`configs/odisha_v120_3ha_angul.yaml:122`). These are the only two settings that differ (commit 2eab33a message).
- Largest patch per district at the old spacing: Angul 4.49, Dhenkanal 6.74, Kendujhar 5.20, Koraput 5.08 hectares (computed; same as commit 2eab33a).
- Why: stands are built by joining small patches and a patch can never be split, so a single patch bigger than 3 hectares can never fit under a 3-hectare cap. At 100 m spacing some patches were already 6.74 hectares, so a 3-hectare cap was impossible; the first 3-hectare run stopped with an error ("largest component is 519 px but maxSize is 360 px", `configs/odisha_v120_3ha_angul.yaml:19-21`). At 60 m spacing the largest patch is 2.02 hectares, under the cap.
- Say: "To make 3-hectare stands possible I had to cut the forest into smaller building blocks first: from about 100 metres apart to about 60 metres apart."
- Caution: the two arms therefore differ in two settings, not one. Any difference between them could come from either.

## 6. Testing power: how many plots share a stand

A stand only tells us something about "are alike plots put together" if it holds two or more plots.

| | Stands holding 2 or more plots | Plots in those stands | Plot pairs that share a stand | Source |
|---|---|---|---|---|
| Up to 10 hectares | **61** | **184** of 267 | **247** of 35,511 (0.7%) | `odisha_phase3_1_score_v120_merged_districts.txt:6,21-22`; `odisha_phase3_3_results.txt:28` |
| Up to 3 hectares | **44** | **113** of 267 | **113** of 35,511 (0.3%) | `odisha_phase3_1_score_v120_3ha_merged_districts_3ha.txt:6,21-22`; `odisha_phase3_3_results.txt:31` |

Say: "Smaller stands mean fewer plots share a stand: 184 plots could be tested at 10 hectares, only 113 at 3 hectares."

## 7. The scores

**Two questions**, scored over every pair of plots:
1. *Stand drawing* ("delineation"): do plots that are alike on the ground end up in the same stand?
2. *Stand labelling*: do alike plots get the same stand type, even far apart? Scored within each district, because the automatic grouping is run separately in each district, so "type 3" in Angul has nothing to do with "type 3" in Koraput.

**Agreement score** (Adjusted Rand Index): 1 = perfect, 0 = what random grouping would give on average. **Here chance is not zero**: plots in the same village forest are more alike (43.1% of same-village pairs are the same forest type, against 27.8% of pairs in different villages and 29.1% overall; computed `bench.py`, 3,032 same-village pairs) and stands never cross a village boundary, so even a meaningless stand map scores above zero.

**Random-shift test** (rotation null): for each village forest, the whole set of plots is rotated and moved to a random position inside that village, 1,999 times, and the score is recomputed each time. This keeps the real stand map and the real plots and only breaks the link between them. The score must beat these random maps to count. `odisha_phase3_3_results.txt:5-10`. For labelling the random plots are made to land on stands that have a type (`:11-13`).

"Beats N of 1,999" = number of random maps whose score is strictly below ours. Computed by re-running the committed random-shift test with its fixed seeds (`dump_nulls.py`: imports `odisha_phase3_3_significance`, calls `load_all()` and `analyse_arm(..., 1999)` for both arms, saves the arrays to the scratchpad; nothing in the repo is written). The re-run passed both identity checks and reproduced every middle value, 90% range, percentile and one-sided chance in `odisha_phase3_3_results.txt` to the printed precision. "Ties" = random maps scoring exactly the same.

### Stand drawing (delineation)

| | Our score | Random maps: middle value | Random maps: middle 90% | Beats N of 1,999 random maps | One-sided chance | Source line in `odisha_phase3_3_results.txt` |
|---|---|---|---|---|---|---|
| 10 hectares, all plots | **0.0115** | 0.0097 | 0.0073 to 0.0124 | **1,727** | 0.137 | :39 |
| 10 hectares, plots in shared stands | **0.0236** | 0.0221 | 0.0165 to 0.0292 | **1,311** | 0.344 | :40 |
| 3 hectares, all plots | **0.0066** | 0.0047 | 0.0033 to 0.0064 | **1,928** (+4 ties) | 0.036 | :59 |
| 3 hectares, plots in shared stands | **0.0253** | 0.0218 | 0.0144 to 0.0311 | **1,497** | 0.252 | :60 |

Supporting rate (share of same-stand pairs that are alike on the ground, "same-stand pair precision"): 10 hectares 53.4% vs random 54.6% (:41); 3 hectares 59.3% vs random 55.0% (:61). Compare 29.1% for all pairs. Beats 747 (10 hectares) and 1,672 +4 ties (3 hectares) of 1,999 random maps; one-sided chance 0.626 and 0.164. Say: "About half the plot pairs that share a stand are the same forest type, but that is also what a randomly placed map gets, because neighbours tend to be alike anyway."

### Stand labelling

| | Our score | Random maps: middle value | Random maps: middle 90% | Beats N of 1,999 random maps | One-sided chance | Line |
|---|---|---|---|---|---|---|
| 10 hectares | **0.0354** | 0.0368 | 0.0164 to 0.0608 | **908** | 0.546 | :42 |
| 3 hectares | **0.0560** | 0.0566 | 0.0342 to 0.0822 | **977** | 0.511 | :62 |

Per district labelling score, 10 / 3 hectares (descriptive only; Kendujhar is 8 plots in one village): Angul 0.009 / 0.060, Dhenkanal 0.065 / 0.159, Kendujhar 0.072 / 0.181, Koraput 0.025 / -0.006 (`:47-50`, `:67-70`). None is outside its own random range.

Far-apart pairs (same district, more than 2 km apart): alike pairs get the same stand type 1.8 percentage points LESS often than differing pairs at 10 hectares (-0.0185, random middle -0.0119) and 1.4 percentage points more often at 3 hectares (+0.0140, random middle +0.0113) (`:43`, `:63`). Beats 639 (10 hectares) and 1,167 (3 hectares) of 1,999 random maps; one-sided chance 0.680 and 0.416. Say: "Far apart, alike plots are no more likely to get the same stand type than unlike plots."

### After correcting for running ten tests

- 10 headline tests (5 measures x 2 arms). **0 of 10** beat chance after Holm correction (`odisha_phase3_3_results.txt:109-126`).
- The smallest one-sided chance is 3 hectares, stand drawing, all plots: **0.036, which becomes 0.360 after correction** (`:112`). Say: "One of ten tests looked promising on its own, but with ten tries one result like this can easily turn up by luck; after allowing for that, it is not."

### 3 hectares against 10 hectares (same 267 plots)

Difference = 3-hectare score minus 10-hectare score. Two readings (`odisha_phase3_3_results.txt:79-95`):

| Measure | Difference | Difference expected from chance alone (middle 95%) | Village resampling range (95%, 4,000 draws) | Line |
|---|---|---|---|---|
| Stand drawing, all plots | **-0.0050** | -0.0050 (-0.0086 to -0.0016) | -0.0129 to -0.0009 | :80, :90 |
| Stand drawing, plots in shared stands | **+0.0018** | -0.0003 (-0.0126 to +0.0132) | -0.0167 to +0.0171 | :81, :93 |
| Same-stand pair precision | +0.0585 | +0.0055 (-0.1017 to +0.1144) | -0.0217 to +0.2271 | :82, :94 |
| Labelling | **+0.0206** | +0.0190 (-0.0199 to +0.0602) | -0.0766 to +0.0956 | :83, :95 |
| Far-apart labelling rate | +0.0324 | +0.0233 (-0.0133 to +0.0627) | (not computed) | :84 |

- The all-plots drawing difference is below zero even after resampling villages, but it is **exactly the difference in the two arms' chance levels** (sits at the 50th percentile of the chance difference, `:91-92`). It says smaller stands group fewer pairs, not that they draw worse.
- All 5 measures differ by no more than chance already makes them differ (`:129-130`).
- Say: "The 3-hectare and 10-hectare stands cannot be told apart. With only 20 village forests as independent units, this test has little power to separate them."

### Benchmark: knowing only the village

Computed for this deck (`bench.py`: `adjusted_rand_score(field_type, village)` over the 267 plots; labelling version = plot-weighted mean over districts of the per-district score with village as the label). Not in any committed results file.

| | "Stand" = the whole village forest | 10 hectares | 3 hectares |
|---|---|---|---|
| Stand drawing, all plots | **0.074** | 0.0115 | 0.0066 |
| Labelling (within district) | **0.089** (Angul 0.146, Dhenkanal 0.194, Kendujhar 0.000, Koraput 0.025) | 0.0354 | 0.0560 |

Say: "Just knowing which village a plot is in groups alike plots better than either stand map does." Caveat for notes: the village is a much coarser grouping than a stand, and the agreement score is not strictly comparable across groupings of very different sizes, so this is a sense-of-scale benchmark, not a test.

## 8. Speaker notes only: the scorer correction

The first version of the scorer treated stand 62 in Angul and stand 62 in Koraput as one stand, and compared stand types across districts, although each district is a separate run. Fixed in commit e261f3d (stands keyed by district; labelling scored within district); the earlier numbers (0.0093 / 0.0179 / 0.0293 for 10 hectares) were wrong and are replaced by those above. One line: "An early bug mixed up stand numbers between districts; it was caught by the significance check and every number here is after the fix."

## 9. Headline sentences (first person, plain)

1. "Species could not sort these forests: 259 of 274 plots fell into one group."
2. "So I grouped plots by structure instead (height, crown cover, trunk area, number of trees) into five forest types."
3. "I cut the forest into stands of at most 10 hectares and at most 3 hectares, and gave each stand one of six types automatically from the satellite data."
4. "Neither stand map puts alike plots together, or gives them the same type, more often than a randomly shifted map does. 0 of 10 tests survive."
5. "The 3-hectare and 10-hectare stands cannot be told apart with this data."

---

## WORDS TO USE

| Technical term | Say instead |
|---|---|
| ARI, Adjusted Rand Index | agreement score (1 = perfect, 0 = random guessing) |
| superpixel, SNIC segment | small patch (building block of a stand) |
| SNIC seed spacing, `segmentation.size` | patch spacing (about 100 metres -> about 60 metres) |
| k-means | automatic grouping |
| k | number of types |
| elbow method | elbow rule: the point where adding more types stops helping much |
| silhouette / Calinski-Harabasz / Davies-Bouldin | other rules for choosing the number of types |
| rotation null, spatial null | random-shift test |
| null distribution | scores of randomly shifted maps |
| percentile, p-value | "beats N of 1,999 random maps"; "chance of doing this well by luck" |
| Holm correction, multiple comparisons | "after allowing for running ten tests" |
| cluster bootstrap CI | "range if the villages had been different" |
| delineation | stand drawing: do alike plots end up in the same stand |
| labelling | stand labelling: do alike plots get the same stand type |
| stand type, cluster_id | stand type |
| field type, structural type | forest type (from the field) |
| Lorey's height | average tree height (metres) |
| basal area | trunk area |
| crown cover | crown cover (share of the ground under tree crowns) |
| merged layer | stands |
| AOI, AOI part, habitation polygon | village forest / study area |
| arm | "stands up to 10 hectares" / "stands up to 3 hectares" |
| max_area_ha | stand size cap |
| ha | hectares (never abbreviate) |
| UPGMA, Bray-Curtis | grouping by species |
| multi-plot stands | stands holding two or more plots |
| precision | share of same-stand pairs that are the same forest type |
| FES | the field team (FES; spell out only if the full name is confirmed) |

## DO NOT CLAIM

- **"5,910 trees."** It is 5,910 plant records; about 2,700 are trees.
- **"The elbow gives 6 stand types everywhere."** It gives 6 in three districts and 5 in Koraput and all districts together; 6 is the middle answer.
- **"All 15 plots outside the big species group are scrub."** 13 are; 2 are low forest led by an unusual species.
- **"The scores are above zero, so the method works."** Chance is above zero here; only beating the random-shift maps counts.
- **"3-hectare stand drawing is significant" (0.036), or "beats 1,928 of 1,999 random maps" without the next clause.** Not after allowing for ten tests (0.360); and on the plots that actually share a stand it beats only 1,497.
- **"3-hectare stands draw worse than 10-hectare" (the -0.0050 difference).** That gap is the difference in chance levels.
- **"3-hectare stands label better" (0.056 vs 0.035).** Both sit at the middle of their random maps; the difference is inside chance.
- **"The method is proven wrong / useless."** With 267 plots in 20 village forests the test has little power; "no evidence it beats chance" is the claim, not "evidence it fails".
- **"The only change between the arms is the stand cap."** Patch spacing also changed (10 -> 6 pixels).
- **"Every 3-hectare stand is under 3 hectares."** 41 of 1,954 are just over, by at most 0.04 hectares.
- **Any per-hectare density or trunk area per hectare.** Plot radius is unknown.
- **Any plot-level p-value or plot-level bootstrap.** Plots in a village are not independent; none are reported.
- **Per-district labelling scores as findings.** Kendujhar is 8 plots in one village; per-district rows are descriptive only.
- **The village benchmark as a formal test.** It is a sense-of-scale comparison computed for this deck.
- **The pre-fix scorer numbers** (0.0093, 0.0179, 0.0293; 0.0042, 0.0115, 0.0474; "55 stands holding 149 plots").

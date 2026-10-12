# Phase 3 status

How well do the pipeline's stands match the Odisha field data when stands are held to the 2-3
hectares the supervisor asked for? This note says what was run, what it found and how firm that
is.

Written 2026-10-07 and completed 2026-10-08. **Every result below is final.** Every score is
copied from a results file in this folder, named beside it. Two kinds of number are not, and each
is marked where it appears: the stand counts and sizes (computed from the stand files), and two
figures worked out for this note from the field-type files and the plot table. Numbers for the
3 hectare stands on 6 stand types, PR #40's included, are from the runs kept in
`phase3_before_regroup/`.

The one primary analysis and the three checks were fixed in `PHASE3_PREDECLARED.md` (commit
`845c22c`) **after the scores of PR #40 were known and before any score was recomputed on the new
field types.**

**Words used**

- **PR #40**: the first Phase 3 analysis, merged on 2026-09-24. Every "before" number is from it.
- **10 hectare stands, 3 hectare stands**: the two versions of the stand map, named after the
  *largest* stand each allows, not the typical one. The middle stand is 3.09 hectares in the
  first and 2.35 in the second. Only the second meets the 2-3 hectare request: half of the
  "10 hectare" stands are larger than 3 hectares. File names call these two versions *arms*
  (`v120` and `v120_3ha`).
- **Field type**: the kind of forest a plot is, from the field measurements. **Stand type**: the
  kind of forest a stand is, from the satellite features (assigned by k-means, the standard
  method for sorting items into a chosen number of groups).
- **Regroup**: giving the 3 hectare stands their types again, 5 instead of 6, without moving
  any stand boundary.
- **Elbow rule**: sort the items into 2, 3, ... up to 12 groups and plot how tightly the groups
  fit against the number of groups. More groups always fit tighter, but at some point the curve
  bends and extra groups add little. That bend, the elbow, is the number taken.

---

## The answer

*The supervisor's question: run the hand-crafted pipeline on the Odisha sites, merge stands to at
most 2-3 hectares, give each stand a type with k-means, and find a way to say how well the stands
are drawn and how well they are labelled, taking the field data as truth.*

**At neither stand size can the stands be shown to group plots that are alike on the ground
better than a randomly placed copy of the same stand map does, and at neither size can the stand
types be shown to match the field types better than chance.** None of the ten planned tests
survives the correction for running several tests, and the same is true under each of the three
checks declared in advance. This is the answer PR #40 gave; it now rests on a cleaner field truth
and on the number of stand types the 3 hectare stands should have had.

This says the stands cannot be told from chance *with this field data*. It does not say they are
shown to be poor: with 20 villages the data could miss a real effect of modest size.

| What is scored | 10 hectare stands | 3 hectare stands (the size asked for) |
|---|---|---|
| **Drawing**, all 267 plots: do plots of the same field type share a stand? | 0.0121, at the 94th percentile of chance | 0.0060, 92nd percentile |
| **Drawing**, only stands that hold two or more plots | 0.0257, 77th percentile | 0.0244, 66th percentile |
| **Labelling**: do plots of the same field type get the same stand type? | 0.0389, 67th percentile | 0.0793, 83rd percentile |

**How to read a cell.** The first number is an agreement score (the adjusted Rand index): 1 means
the two groupings match perfectly, and 0 is what two unrelated groupings would score if every
plot were independent of every other. Here zero is not the chance level, because the plots are
not independent: plots in one village are alike and also sit in neighbouring stands, so a stand
map that knows nothing about the forest still scores above zero. The chance level is therefore
measured. Each village's plots are moved together 1,999 times to a random position and angle
inside the village, and the score is recomputed each time. The percentile says where the real
score falls among those 1,999.

**What counts as beating chance.** Above the 95th percentile is the bar for one test read on its
own. Several tests are run here, so a result counts only if it also survives a correction for
that. Five scores are tested for each stand size, ten tests in all; the table shows the three
main ones and [Results](#results) has all five. The best of the ten is the 94th percentile above,
which means 6.3% of randomly placed maps score as well (p = 0.063). After the correction it is
0.630. A test would have needed p below about 0.005 (0.05 divided by ten) to count.

**Where the data leans, so that nobody has to find it.**

- *Drawing on all plots* sits between the 86th and the 97th percentile in all eight combinations
  of stand size and analysis (the primary and the three checks), and in three of them it passes
  the 95th when read alone: 95.7 at 10 hectares with four field types, and 96.7 and 96.5 at
  3 hectares with four field types and with PR #40's.
- *Labelling at 3 hectares* sits above the middle of chance in all four analyses (percentiles
  83.1, 84.4, 62.6 and 94.7). Its best is p = 0.053, which does not pass even when read alone.
  It depends on the number of stand types: with 6 types the same stands sat below the middle in
  all four (28.0, 31.3, 16.9 and 48.9).
- *Labelling by district at 3 hectares* (descriptive rows, outside the ten tests). Angul sits at
  percentiles 91.7, 93.9, 76.3 and 96.0 across the four analyses, and Kendujhar, with 8 plots, at
  92.0, 86.5, 92.0 and 96.2. Under PR #40's field types both pass the 95th when read alone
  (p = 0.041 and 0.048). Koraput, with 145 of the 267 plots, sits at 28.0, 16.6, 22.4 and 25.0.
- None of these survives the correction, and they are not independent of one another (same
  plots, same stands, overlapping field types). On the fairer drawing test, which uses only
  stands that hold two or more plots, nothing is above the 91st percentile.

This is why the answer says "cannot be shown" and not "no effect".

For scale: treat each village as if it were one stand, with no stand map at all, and the
agreement score with the field types is 0.076 (0.089 worked out within districts, as labelling
is). Both are printed in the header of `odisha_phase3_3_results.txt`. Each is higher than the
matching score in the table. This is for scale only: the score is lower for any map with smaller
groups, so it does not show that villages are more informative than stands.

---

## What was run

1. **A field truth built from forest structure** (`odisha_phase3_0_field_structure_types.py`).
   Grouping the plots by species does not work here: it puts 259 of the 274 plots in one group
   (`explain_field_types.py`), which leaves nothing to test against. Grouping by height, crown
   cover, trunk area and number of trees gives five groups, the largest holding 111 plots.
2. **Stands at two sizes.** The 10 hectare stands are the ones Phase 2 reported. The 3 hectare
   stands are new in Phase 3 (`configs/odisha_v120_3ha_<district>.yaml`).
3. **The number of types, by the elbow rule** (`odisha_phase3_2_stand_k_elbow.py` for stands).
   The number of field types was chosen from the field data alone and the number of stand types
   from the satellite data alone. Neither choice looked at the scores: picking the number that
   gives the best agreement would manufacture the result. For the 3 hectare stands the rule
   chose the number (5). For the 10 hectare stands 6 was already in the Phase 2 configs and the
   rule was run afterwards as a check; see [The stands](#the-stands).
4. **A score for every pair of plots** (`odisha_phase3_1_pairwise_score.py`): does the field say
   the two plots are alike, and did the pipeline put them together?
5. **A chance test** (`odisha_phase3_3_significance.py`), using the rotation test of Phase 2
   unchanged (the moving of plots described above).
6. **Three checks fixed in advance.** S1: the same scores without the no-tree plots. S2: the
   field plots sorted into four types instead of five. S3: the field types as PR #40 had them, to
   show that nothing else moved.

Phase 3 changed no pipeline code. `src/` and `tests/` are identical to `main`.

---

## The field truth

**Source.** `Odisha_samples.csv` has 5,910 plant records. 5,679 remain after dropping records whose
GPS accuracy is worse than 20 metres, in 274 plots. 267 of the plots fall inside the mapped village
forests and are the ones scored. The sheet gives no position for individual trees, only for the
plot, and the plot radius is still unknown (asked of the field team, not yet answered).

**Four measurements per plot.**

| Measurement | How it is computed | Rows used |
|---|---|---|
| Tree height | average `Height`, each tree weighted by its trunk area | rows marked `Tree` |
| Trunk area | sum of π × (`DBH` / 2)² in square centimetres; a plot total, not per hectare, because the plot size is unknown | rows marked `Tree` |
| Number of trees | count | rows marked `Tree` |
| Crown cover | the plot's `Crown Cover` band, taken at its midpoint | one reading per plot |

**What changed from PR #40: the first two rows.** In PR #40 height and trunk area used every row of
the sheet, which includes 168 stumps, 290 climbers, 953 shrubs and 1,539 saplings and seedlings,
while the tree count used only the 2,729 `Tree` rows. A plot could show no trees and still have a
height. All three now use `Tree` rows only, and a plot with no `Tree` row gets height 0 and trunk
area 0. `Tree` rows carry 95.5% of all recorded trunk area, so little wood is lost. `--rows all`
still reproduces the PR #40 grouping label for label.

**The five field types** (`odisha_phase3_0_results.txt`; the values are group medians):

| Type | Plots (of 274) | Tree height | Crown cover | Trees per plot | Trunk area per plot |
|---|---|---|---|---|---|
| 0, no trees | 18 | 0 m | 0% | 0 | 0 cm² |
| 1, short, few trees | 111 | 7.1 m | 38% | 6 | 625 cm² |
| 2, short, many trees | 77 | 8.1 m | 33% | 14 | 2,850 cm² |
| 3, tall, crowded | 15 | 15.4 m | 48% | 29 | 4,771 cm² |
| 4, tall, few big trees | 53 | 18.3 m | 53% | 8 | 2,552 cm² |

Among the 267 scored plots the counts are 16, 108, 76, 15 and 52. Type 0 holds all 15 plots that
have no `Tree` row plus 3 plots with one or two very thin trees. The new grouping is close to the
old one: 265 of 274 plots stay in the matching group (agreement 0.914).

**The types are numbered differently from PR #40.** They now run from shortest to tallest, so
type 0 is "no trees". In PR #40's file (`odisha_phase3_0_field_types_allrows.csv`) the scrub
group is type 2 and type 0 is "short, many trees". A command that leaves out type 0 means
something else on that file.

**How firm is "five"?** Not very, and this note should not pretend otherwise. Five is what the
elbow rule gives, and the elbow rule is the one the supervisor named. But on the field data alone
(`odisha_phase3_0_results.txt`, mostly its section "HOW FIRM IS THE CHOICE OF k"):

- The bend is shallow. Measured as how far the curve bows away from a straight line joining its
  two ends, it is 0.263 at five groups, 0.250 at six and 0.249 at four.
- The answer depends on how many group counts are tried, because that moves the straight line:
  4 if the search stops at 8, 5 if it stops at 10 or 12 (12 was used), 6 if it runs to 16.
- Picking 274 plots at random from the 274, repeats allowed, and redoing the whole procedure,
  100 times over, gives five 81 times and six 19 times.
- The three other standard rules do not agree with it: two prefer 2 groups and one prefers 4.
- Without the 15 no-tree plots the elbow moves to six.
- The grouping also depends on which measurements go in. Adding average trunk diameter still
  gives five types, but a grouping that agrees with this one at only 0.453. No check covers that.

A fair description is **one real gap, trees against no trees, and a continuum of forest with
trees that this rule cuts into four.** The plots with trees fall into almost the same four groups
whether or not the no-tree plots are included (agreement 0.959), but asked on their own the same
rule would cut them into six. Any agreement the stands showed could therefore have rested on the
one easy contrast, which is why check S1 exists.

---

## The stands

| | 10 hectare stands | 3 hectare stands |
|---|---|---|
| Configs | `configs/odisha_v120_handcrafted_<district>.yaml` | `configs/odisha_v120_3ha_<district>.yaml` |
| Largest stand allowed (`merge.max_area_ha`) | 10 | 3 |
| Spacing of the building blocks (`segmentation.size`) | 10 pixels, about 100 m | 6 pixels, about 60 m |
| Number of stand types (`clustering.k`) | 6 | 5 |
| Stands in the four districts | 1,039 | 1,954 |
| Median stand size | 3.09 hectares | 2.35 hectares |
| Stands larger than 3 hectares | 529 of 1,039 (50.9%) | 41 of 1,954 (2.1%), each by at most 0.04 hectares |
| Stands holding at least one plot | 144 | 198 |
| Stands holding two or more plots | 61, holding 184 plots | 44, holding 113 plots |

Counts and sizes are computed from the stand files in `phase2_vectors/`
(`<config>_stands_merged.geojson`; a stand's area is `area_ha` summed over the polygons that share
a `stand_lbl`). The last two rows are from the score files. The size limit is slightly soft at
both sizes: 10 of the 10 hectare stands exceed 10 hectares, by at most 0.08.

**Why the building blocks had to shrink.** Stands are made by joining small patches (superpixels),
and a patch can never be split. At 100 m spacing single patches already reach 6.74 hectares
(Dhenkanal; recorded in the 3 hectare config header), so a 3 hectare limit could not be met: the
first attempt stopped with an error. Spacing went to 60 m. This is a change the supervisor did
not name. It was forced by the data and chosen after the alternatives were laid out (2026-09-24).

**So the two stand sizes differ in three settings, not one.** A difference between them cannot be
put down to stand size alone.

**The cost of smaller stands.** Fewer plots share a stand: 113 plots in 44 stands against 184 in
61. The test of whether a stand holds plots that are alike has less to work with at 3 hectares.

**Number of stand types.** The elbow rule on each stand size's own stands, satellite features only:

| | Angul | Dhenkanal | Kendujhar | Koraput | All four pooled | Used |
|---|---|---|---|---|---|---|
| 10 hectare stands (`odisha_phase3_2_k_elbow_odisha_v120_handcrafted.txt`) | 6 | 6 | 6 | 5 | 5 | 6 |
| 3 hectare stands (`odisha_phase3_2_k_elbow_odisha_v120_3ha.txt`) | 5 | 5 | 5 | 5 | 5 | 5 |

- **10 hectare stands: 6 was not chosen by the rule.** It was in the Phase 2 configs from
  2026-09-14. The elbow was run ten days later and 6, the middle of its five answers, was kept.
  Koraput holds 145 of the 267 scored plots and its own elbow is 5, yet it is run at 6.
- **3 hectare stands: 5 was chosen by the rule.** PR #40 ran them with 6, carried over from the
  10 hectare configs without checking it on the 3 hectare stands themselves. On those the rule
  gives 5 everywhere, so by the rule 6 was the wrong number. Only the labelling depends on it.
  The stand boundaries do not, and the regroup left every one of them where it was
  (`odisha_phase3_stands_unchanged.txt`; see [How the regroup was run](#how-the-regroup-was-run-and-checked)).
- The elbow is fitted on the polygons in the stand files (1,068 and 1,993). A stand that lies in
  two separate pieces enters twice, which is why those files show more "stands" than the table
  above.

Neither stand size gives well separated stand types. Pooled over the four districts, the best
silhouette value (a measure of how cleanly groups separate, from −1 to 1) is 0.212 for the
10 hectare stands and 0.217 for the 3 hectare stands, and that is at the number of types where
it is highest.

Stand types are fitted separately in each district, so "type 3" in Angul and "type 3" in Koraput
are unrelated. Stand numbers also restart in each district. Every score below respects that.

---

## The scores

For each pair of plots there are two questions: does the field say they are alike (same field
type), and did the pipeline put them together?

| Score | What it measures |
|---|---|
| Drawing, all plots | Agreement between "which stand is the plot in" and "which field type is it", over all 267 plots |
| Drawing, shared stands | The same, using only plots whose stand holds at least one other plot. This is the fairer test: a stand with a single plot can say nothing about whether a stand holds plots that are alike |
| Same-stand precision | Of the pairs of plots that share a stand, the share that have the same field type |
| Labelling | Agreement between field type and stand type, worked out inside each district and averaged with each district weighted by its number of plots. At 10 hectares it uses 266 of the 267 plots (one plot's stand has no type); at 3 hectares all 267 |
| Far-apart labelling | Among pairs more than 2 km apart in the same district: how much more often do two plots get the same stand type when the field says they are alike than when it says they differ? Positive is good. The 2 km rule removes the easy explanation that the two plots are simply neighbours |

## The chance test

Each village's plots are moved together, as a rigid shape, to a random position and angle inside
that village, and take whatever stand lies under them. A placement is kept only if every plot
still lands on a stand. This is done 1,999 times. It keeps everything real (the stand map, the
spacing of the plots, the mix of field types in the village) and breaks only the link between
where a plot actually is and which stand it is in.

- **Percentile**: where the real score falls among the 1,999. **p**: the share of them that score
  at least as well as the real map. The two say the same thing: the 94th percentile is p = 0.063.
- **Labelling uses a stricter version**, in which plots must land on a stand that has a type,
  because about a fifth of Koraput's stand layer has none.
- **Many tests are run, so one small p is expected by luck.** The ten headline tests, five for
  each stand size, are corrected together (Holm's method: the smallest p is multiplied by the
  number of tests, the next by one fewer, and so on). A result counts only if it survives that.
  The correction uses the unrounded p, so a corrected value can differ in the third decimal from
  the rounded p times the number of tests (0.080 times 9 appears as 0.716).
- **The 20 village forests are the independent units**, not the 267 plots. Tests that shuffle
  individual plots look far more convincing than they should here and are not reported.

---

## Results

### Primary analysis

Field types from trees only, five types. 10 hectare stands with 6 stand types, 3 hectare stands
with 5. Files: `odisha_phase3_3_results.txt` (chance test, both sizes),
`odisha_phase3_1_score_v120_merged_districts.txt` and
`odisha_phase3_1_score_v120_3ha_merged_districts_3ha.txt` (scores).

**10 hectare stands**

| Score | Real stand map | Randomly placed map: middle value (range holding 90% of them) | Percentile | p |
|---|---|---|---|---|
| Drawing, all plots | 0.0121 | 0.0096 (0.0073 to 0.0124) | 93.7 | 0.063 |
| Drawing, shared stands | 0.0257 | 0.0228 (0.0172 to 0.0299) | 77.0 | 0.230 |
| Same-stand precision | 0.5385 | 0.5337 (0.4817 to 0.5901) | 55.2 | 0.451 |
| Labelling | 0.0389 | 0.0337 (0.0139 to 0.0564) | 66.8 | 0.332 |
| Far-apart labelling | −0.0118 | −0.0108 (−0.0301 to 0.0118) | 46.6 | 0.534 |

**3 hectare stands**

| Score | Real stand map | Randomly placed map: middle value (range holding 90% of them) | Percentile | p |
|---|---|---|---|---|
| Drawing, all plots | 0.0060 | 0.0045 (0.0031 to 0.0062) | 92.1 | 0.080 |
| Drawing, shared stands | 0.0244 | 0.0223 (0.0143 to 0.0321) | 65.7 | 0.344 |
| Same-stand precision | 0.5575 | 0.5306 (0.4607 to 0.6079) | 71.7 | 0.284 |
| Labelling | 0.0793 | 0.0665 (0.0475 to 0.0902) | 83.1 | 0.169 |
| Far-apart labelling | 0.0143 | 0.0095 (−0.0082 to 0.0336) | 64.0 | 0.360 |

**Nothing reaches the 95th percentile at either size, and 0 of the 10 tests survive the
correction.** The two smallest p-values are 0.063 and 0.080 (drawing on all plots, at 10 and at
3 hectares); corrected they are 0.630 and 0.716, and every other test corrects to 1.

- **Drawing.** On the fairer test, shared stands, the real map sits at the 77th percentile at
  10 hectares and the 66th at 3: one randomly placed map in four, or in three, does as well. Of
  the pairs of plots that share a stand, 53.8% have the same field type at 10 hectares and 55.8%
  at 3; randomly placed maps give 53.4% and 53.1%.
- **Labelling at 10 hectares** sits at the 67th percentile, and the far-apart score is slightly
  negative: plots the field calls alike are, if anything, a little less likely to get the same
  stand type than plots it calls different.
- **Labelling at 3 hectares** scores twice as high (0.0793 against 0.0389), but so does a
  randomly placed map (0.0665 against 0.0337). Against its own chance level it sits at the 83rd
  percentile, p = 0.169.
- **By district at 3 hectares** (descriptive only; a district is 1 to 8 villages): Angul 0.1461
  (percentile 91.7), Dhenkanal 0.1849 (54.5), Kendujhar 0.2265 (92.0, on 8 plots), Koraput
  −0.0014 (28.0). Koraput holds 145 of the 267 plots and shows nothing. Dhenkanal, with 75
  plots, has a high score but so does its chance level (0.1845). The two high percentiles, Angul
  and Kendujhar, come from 39 and 8 plots.

### The three checks declared in advance

Each was fixed in `PHASE3_PREDECLARED.md` before any score was recomputed, to be reported whatever
it showed. Each score is followed by its percentile of chance. Files:
`odisha_phase3_3_results_excl0.txt` (S1), `odisha_phase3_3_results_ft-k4.txt` (S2),
`odisha_phase3_3_results_ft-allrows.txt` (S3), and the matching `odisha_phase3_1_score_*` files.

**10 hectare stands**

| Score | Primary | S1: without the no-tree type | S2: four field types | S3: the PR #40 field types |
|---|---|---|---|---|
| Drawing, all plots | 0.0121 (93.7) | 0.0107 (91.9) | 0.0094 (95.7) | 0.0115 (86.4) |
| Drawing, shared stands | 0.0257 (77.0) | 0.0225 (72.1) | 0.0217 (90.4) | 0.0236 (65.6) |
| Same-stand precision | 0.5385 (55.2) | 0.5854 (54.7) | 0.6599 (61.9) | 0.5344 (37.4) |
| Labelling | 0.0389 (66.8) | 0.0229 (34.3) | 0.0340 (57.4) | 0.0354 (45.4) |
| Far-apart labelling | −0.0118 (46.6) | −0.0318 (12.3) | −0.0053 (35.9) | −0.0185 (32.0) |
| Plots in shared stands | 184 in 61 stands | 168 in 59 stands | 184 in 61 stands | 184 in 61 stands |

**3 hectare stands**

| Score | Primary | S1: without the no-tree type | S2: four field types | S3: the PR #40 field types |
|---|---|---|---|---|
| Drawing, all plots | 0.0060 (92.1) | 0.0048 (86.6) | 0.0049 (96.7) | 0.0066 (96.5) |
| Drawing, shared stands | 0.0244 (65.7) | 0.0190 (54.7) | 0.0197 (75.5) | 0.0253 (74.9) |
| Same-stand precision | 0.5575 (71.7) | 0.5955 (61.0) | 0.6991 (81.5) | 0.5929 (83.7) |
| Labelling | 0.0793 (83.1) | 0.0822 (84.4) | 0.0726 (62.6) | 0.0930 (94.7) |
| Far-apart labelling | 0.0143 (64.0) | 0.0202 (65.2) | 0.0131 (39.0) | 0.0121 (64.1) |
| Plots in shared stands | 113 in 44 stands | 100 in 40 stands | 113 in 44 stands | 113 in 44 stands |

**Both sizes together**

| | Primary | S1 | S2 | S3 |
|---|---|---|---|---|
| Plots scored | 267 | 251 | 267 | 267 |
| Smallest p of the ten, and corrected | 0.063, 0.630 | 0.082, 0.815 | 0.034, 0.340 | 0.036, 0.360 |
| Tests surviving the correction | 0 of 10 | 0 of 10 | 0 of 10 | 0 of 10 |

**No check changes the conclusion.** What each one shows:

- **S1, without the no-tree type** (16 of the 267 scored plots dropped; one Koraput village is left
  with no plot, so 19 villages). The question was whether any agreement rested on the easy
  contrast of trees against no trees.
  - Drawing moves a little at both sizes (at 10 hectares from 93.7 and 77.0 to 91.9 and 72.1; at
    3 hectares from 92.1 and 65.7 to 86.6 and 54.7).
  - Labelling at 10 hectares falls from 0.0389 to 0.0229, from the 67th to the 34th percentile.
    Both positions are inside what chance gives, so this does not show that labelling depended
    on the no-tree plots: no labelling agreement had been shown in the first place, so none can
    be shown to have been lost. The fall comes
    entirely from Koraput (0.0248 to −0.0139), where 11 of the 16 dropped plots sit in two
    villages (counted from the plot table); Dhenkanal is unchanged, and Angul and Kendujhar rise.
  - Labelling at 3 hectares does not move (0.0793 to 0.0822, 83rd to 84th percentile).
- **S2, four field types.** All 274 plots sorted into four: the no-tree group stays (18 plots) and
  the plots with trees form three groups (155, 42 and 59) instead of four. This grouping agrees
  with the primary one at only 0.544 (computed from the two field-type files), so it is a real
  change of truth. Drawing on all plots passes the 95th percentile at both sizes when read alone
  (95.7, p = 0.043 at 10 hectares; 96.7, p = 0.034 at 3). Corrected over the ten tests they are
  0.391 and 0.340. It is the strongest hint in the data that the stand boundaries carry some
  information about forest structure, and it is not a finding. Labelling at 3 hectares drops to
  the 63rd percentile.
- **S3, the PR #40 field types.** Everything that should reproduce PR #40 does, exactly: all five
  10 hectare scores, and the three 3 hectare scores that depend only on where the boundaries
  are. The two 3 hectare labelling scores differ from PR #40 because the stand types changed
  from 6 to 5, which is the next subsection.

Across the four analyses there are 40 tests. Three have p below 0.05 when read alone (0.034, 0.036
and 0.043), all three on drawing with all plots. None survives the correction. Outside these 40,
the by-district rows, which are descriptive and not tests, hold two more under S3 at 3 hectares:
labelling in Angul (p = 0.041, 39 plots) and in Kendujhar (p = 0.048, 8 plots).

### What the number of stand types does

**This comparison was not in the plan.** It is a description made after the results were seen,
not an eleventh test.

The 3 hectare stands have been scored with 6 stand types and with 5, on identical stands. The
6-type runs were made on PR #40's stand files before the regroup and are kept in
`phase3_before_regroup/`; the one under S3 is PR #40's own result. Each cell is the labelling
score and its percentile of chance.

| 3 hectare labelling | 6 stand types | 5 stand types |
|---|---|---|
| Primary | 0.0444 (28.0) | 0.0793 (83.1) |
| S1: without the no-tree type | 0.0512 (31.3) | 0.0822 (84.4) |
| S2: four field types | 0.0384 (16.9) | 0.0726 (62.6) |
| S3: the PR #40 field types | 0.0560 (48.9) | 0.0930 (94.7) |
| Randomly placed map under the primary analysis, middle value | 0.0523 | 0.0665 |

**One change in a judgement call moved 3 hectare labelling from below the middle of chance to
above it in all four analyses, by 46 to 55 percentile points.** Under PR #40's field types it
went from the middle (48.9, p = 0.511) to just under the 5% bar (94.7, p = 0.053, and 0.477
after correction).

- **Neither number of stand types gives a finding.** With 6, nothing; with 5, nothing that passes
  even when read alone.
- **Against chance, the rise comes from two small districts.** Under the primary analysis Angul
  goes from 0.0786 to 0.1461 (39 plots, percentile 51.0 to 91.7) and Kendujhar from −0.0829 to
  0.2265 (8 plots, 53.7 to 92.0). Dhenkanal's score rises too (0.1520 to 0.1849), but its chance
  level rises with it (percentile 53.6 to 54.5), and Koraput, with 145 plots, stays at zero
  (−0.0135 to −0.0014).
- **So the labelling result is less settled than the drawing result.** It depends on a number,
  5 or 6, that only the elbow rule separates: on the 3 hectare stands the three other rules
  prefer 2 to 4 types, and the pooled silhouette is 0.203 at 5 against 0.208 at 6. A third number
  has not been tried.
- **What can be said for 5** is that it was fixed by the elbow rule and committed (`ef9b510`)
  before any labelling score was computed with it.

### Comparing the two stand sizes

The question is not "which stand size scores higher" but "do they differ by more than randomly
placed maps of the two sizes differ". From `odisha_phase3_3_results.txt`.

| Score | 3 hectare minus 10 hectare | The same difference for randomly placed maps: middle value (range holding 95% of them) | Percentile |
|---|---|---|---|
| Drawing, all plots | −0.0061 | −0.0050 (−0.0086 to −0.0016) | 27.7 |
| Drawing, shared stands | −0.0013 | −0.0006 (−0.0129 to 0.0137) | 44.8 |
| Same-stand precision | +0.0191 | −0.0024 (−0.1108 to 0.1118) | 65.6 |
| Labelling | +0.0404 | +0.0334 (−0.0003 to 0.0694) | 64.3 |
| Far-apart labelling | +0.0260 | +0.0202 (−0.0134 to 0.0569) | 62.2 |

(Differences are taken before rounding, so the last digit can differ by one from subtracting the
tables above.)

**The data cannot tell the two stand sizes apart, on drawing or on labelling.** All five
differences sit inside what chance gives. Under the three checks the labelling difference sits at
the 85th (S1), 54th (S2) and 90th (S3) percentile, against the 64th under the primary analysis:
higher under S1 and S3, lower under S2, and inside what chance gives in all three. The test is a
cautious one: it sets the difference against two independently placed maps, because a version
that moved both maps together cannot be built.

Two traps. The first is flagged in the results file beside the number.

- At 3 hectares the all-plots drawing score is lower (0.0060 against 0.0121), and it stays lower
  whichever villages are included: repeating the comparison on random re-selections of the 20
  villages puts the difference between −0.0153 and −0.0014 in 95% of them. That looks like worse
  drawing and cannot be shown to be. Smaller stands hold fewer pairs of plots, which lowers this
  score for any map: randomly placed maps drop by almost as much (−0.0050 against −0.0061).
- At 3 hectares the labelling score is twice as high. That looks like better labelling and
  cannot be shown to be: randomly placed maps rise by almost as much (+0.0334 against +0.0404).

### What I said beforehand, and what happened

From `PHASE3_PREDECLARED.md`: *"I expect the primary scores to move in the third decimal and the
conclusion of PR #40 (neither stand size beats chance on drawing or labelling) to stand. I have no
expectation for S1 and S2. If any primary headline test survives the Holm correction, that is a
change of conclusion and will be reported as one."*

- **The conclusion: as expected.** No primary test survives the correction, at either size.
- **The 10 hectare scores: as expected.** They moved in the third or fourth decimal (0.0115 to
  0.0121, 0.0236 to 0.0257, 0.0354 to 0.0389).
- **The 3 hectare drawing scores: partly.** The two agreement scores moved as expected (0.0066 to
  0.0060, 0.0253 to 0.0244). Same-stand precision moved more than I predicted, in the second
  decimal (0.5929 to 0.5575).
- **The 3 hectare labelling score: wrong.** It moved in the second decimal (0.0560 to 0.0793).
  Going from 6 stand types to 5 raised it by 0.037 and the change of field truth lowered it by
  0.014 (0.0560, then 0.0930, then 0.0793). I did not anticipate how much the number of stand
  types would matter.
- **Also not expected:** the percentiles moved much more than the scores (10 hectare drawing on
  all plots 86.4 to 93.7, labelling 45.4 to 66.8). The chance level hardly moved (0.0097 to
  0.0096 for drawing), and randomly placed maps all score within a very narrow band, so a change
  of 0.0006 in the score shifts its position among them by seven points. Percentiles near the top
  of that band are fragile, which is one more reason to read them only after the correction.

---

## What changed since PR #40

The numbers are already in the tables above: PR #40's are the **S3** columns and the new ones are
the **Primary** columns, at both stand sizes. The exception is 3 hectare labelling, where the S3
column is on 5 stand types and PR #40 was on 6: PR #40 gave 0.0560 at the 49th percentile and
0.0140 at the 58th for the far-apart score (`phase3_before_regroup/odisha_phase3_3_results_ft-allrows.txt`,
which reproduces PR #40's file).

| | PR #40 | Now |
|---|---|---|
| Field truth | height and trunk area from every row | trees only |
| Stand types at 3 hectares | 6 | 5 |
| Tests surviving the correction | 0 of 10 | 0 of 10 |
| Smallest p of the ten | 0.036 (3 hectare drawing, all plots) | 0.063 (10 hectare drawing, all plots) |
| 3 hectare labelling | 0.0560, 49th percentile | 0.0793, 83rd percentile |

The cleaner field truth moved the two stand sizes in opposite directions: comparing S3 with
Primary, every 10 hectare percentile went up and every 3 hectare percentile went down or stayed
put. The one number in PR #40 that passed a 5% test when read alone, 3 hectare drawing on all
plots at p = 0.036, is now at p = 0.080. That is consistent with scores that sit at chance level:
a small change in the truth moves them either way.

---

## How the regroup was run and checked

Changing the number of stand types from 6 to 5 should not move any stand: no step before the one
that assigns stand types reads that number. It was checked, not assumed.

- **The run.** 8 Earth Engine tasks that assign the stand types, 2 per district (the stand-type
  image and its feature stack), on 2026-10-08; all four districts completed on the first pass in
  about half an hour (`run_3ha_k5_<district>.log`, not committed). The export step then
  submitted its usual 9 Drive exports per district, which nothing here reads. A first
  attempt on 2026-10-07 was cancelled after about twelve hours in the queue: the project was over
  its monthly compute allowance and in Earth Engine's "restricted mode", behind another job.
- **The stands did not move** (`odisha_phase3_stands_unchanged.txt`, from
  `check_stands_unchanged.py`). Compared outline by outline with PR #40's stand files: all 9,572
  building blocks and all 1,993 stand polygons are there with the same outline, and every stand
  has the same number and the same area (to within 0.00000005 hectares). Only the stand type
  differs, on 709 polygons, and each district goes from 6 kinds to 5. The check also confirms
  the files on disk are from the new run.
- **The plots sit in the same stands.** In the new join every one of the 267 plots has the same
  stand and the same building block as in PR #40's join, and the same distance to a boundary.
- **The scores carry over.** With the PR #40 field types the two drawing scores come out at
  0.0066 and 0.0253, as in PR #40, and the chance test reproduces all three boundary-only rows.
- **The elbow is unchanged.** Run again on the new stand files it writes the same file, 5 in
  every district.
- **The runs made before the regroup agree** (`phase3_before_regroup/`). Computed on PR #40's
  stand files while the regroup was queued, every 10 hectare number and every 3 hectare number
  that depends only on the boundaries is identical to the final one in every digit. Only the
  rows that involve 3 hectare labelling differ (its two headline rows, the by-district rows, the
  labelling rows of the comparison of the two sizes and those tests' places in the correction
  table), as they should.

---

## Corrections and departures from plan

Listed so that nothing has to be discovered later.

1. **The first scorer pooled stand numbers and stand types across districts** (fixed in `e261f3d`,
   before PR #40 merged). Both restart in each district, so 18 of the 10 hectare stands' 58
   apparent shared stands, and 24 of the 3 hectare stands' 55, were different stands with the
   same number. No chance-test result had been reported yet, but one reading changed: the
   3 hectare stands hold 113 plots in 44 shared stands, not 149 in 55 as I first reported, so smaller stands cost more
   testing power than I first said.
2. **The 3 hectare stands were given 6 stand types without checking** (fixed in `ef9b510`). Their
   own elbow gives 5. The 3 hectare labelling numbers of PR #40 are superseded, and the change
   turned out to matter: see "What the number of stand types does".
3. **The field measurements did not count the same rows** (fixed in `845c22c`), as described under
   "The field truth".
4. **The scorer and the chance test were edited after the plan was fixed.** `fe80260` added the
   options the three checks need; later commits changed printed text only (the two "for scale"
   lines, a comment, the wording of the closing sentences). The plan had said the two scripts
   would be used "as it stands". With the old field types and PR #40's stand files they
   reproduce PR #40 exactly, at both stand sizes; on the regrouped stands everything except the
   3 hectare labelling rows still does.
5. **The regroup reused stored results instead of recomputing them** (`copy_upstream_cache.py`,
   `43e8c1d`). Changing the number of stand types changes the cache key of every stage, although
   no step before the one that assigns stand types reads that number. The script copies the
   earlier stages' stored results to the new key, and refuses to run unless the two configs
   differ in nothing but the number of stand types. **What this gave up:** redrawing the stands
   from scratch would have confirmed independently that they come out the same. The outline by
   outline check above replaces that.
6. **An attempt to jump the Earth Engine queue was refused and undone** (`cc23866`, reverted in
   `255f3dc`). Task priority is available only to commercially registered projects. The setting
   was removed again; `src/` and `tests/` are identical to `main`.
7. **Verification of the new options found one error before it reached a result.** With field
   type 0 left out, one Koraput village (5 plots, all type 0) has no plot left to score. The
   comparison of the two stand sizes still counted it as a village. It now counts the 19 villages
   that have a scored plot. The effect on the numbers was very small.
8. **The header of the four 3 hectare configs said only the size limit differed** from the
   10 hectare configs. Three settings differ. Corrected in the comment (`e767c8d`); the cache keys
   are unchanged (`9908a3bb6b`, `8c472d39f9`, `a516a24b2d`, `030aafaa2c` before and after).

---

## Limits

- **20 villages, unevenly filled.** One Koraput village holds 59 of the 267 plots and the median
  village holds 10 (village sizes are listed in `odisha_phase2_5_results_districts.txt`). The data
  has little power to show a real effect if there is one, and less still to separate the two
  stand sizes.
- **The number of stand types matters and is only weakly determined.** At 3 hectares, 6 against
  5 moves labelling from the 28th to the 83rd percentile under the primary analysis, and from
  the 49th to just under the 95th (48.9 to 94.7, p = 0.053) under PR #40's field types. No other
  number was tried, at either size. Koraput, with over half the plots, is run at 6 at 10 hectares
  although its own elbow gives 5.
- **One k-means run per district.** Stand types come from a single random start (seed 42 in
  every config). Whether another start would move the labelling result, as the number of types
  does, was not tested.
- **The comparison of the two stand sizes is cautious**, for the reason given under it, as well
  as short of villages. "Cannot tell them apart" is the most it can say.
- **Five field types is a judgement**, as set out above. The checks cover four types and the old
  grouping. Six types, the more frequent alternative, is not checked, because the six-type
  grouping changes with the random start of the method (`PHASE3_PREDECLARED.md`). A different
  choice of measurements is not checked either.
- **No plot radius.** Trunk area is a plot total, not per hectare. It is comparable between plots
  only if every plot is the same size.
- **No tree positions.** A plot is a single point. A plot that straddles a stand boundary cannot
  be seen as such.
- **Three no-tree plots carry crown cover readings above 10%** (98%, 43% and 18%, in
  `odisha_phase3_0_field_types.csv`). They are left as recorded. Two of them are among the scored
  plots.
- **The two stand sizes differ in three settings**, so they are two versions of the method, not a
  clean experiment on stand size.

---

## Reproducing

All offline except the stands themselves. Run from the repo root. (Pasting into a zsh terminal:
run `setopt interactivecomments` first, or the `#` notes are read as commands.)

```bash
# field truth
python odisha_script/explain_field_types.py                                 # species grouping: 259 of 274 in one group
python odisha_script/odisha_phase3_0_field_structure_types.py               # primary: trees only, elbow picks 5
python odisha_script/odisha_phase3_0_field_structure_types.py --k 4         # check S2: four types
python odisha_script/odisha_phase3_0_field_structure_types.py --rows all    # check S3: the PR #40 grouping

# number of stand types, from satellite features only
python odisha_script/odisha_phase3_2_stand_k_elbow.py --arm odisha_v120_handcrafted
python odisha_script/odisha_phase3_2_stand_k_elbow.py --arm odisha_v120_3ha

# scores, 10 hectare stands: primary, then S1, S2, S3
S=odisha_script/odisha_phase3_1_pairwise_score.py
K4=odisha_script/odisha_phase3_0_field_types_k4.csv
OLD=odisha_script/odisha_phase3_0_field_types_allrows.csv
python $S --arm v120
python $S --arm v120 --exclude-types 0
python $S --arm v120 --field-types $K4
python $S --arm v120 --field-types $OLD

# scores, 3 hectare stands: primary, then S1, S2, S3
score3() { python $S --arm v120_3ha --tag _3ha \
               --joined odisha_script/phase3_3ha/phase2_plots_joined_districts.csv "$@"; }
score3
score3 --exclude-types 0
score3 --field-types $K4
score3 --field-types $OLD

# chance test, both stand sizes together: primary, then S1, S2, S3
G=odisha_script/odisha_phase3_3_significance.py
python $G
python $G --exclude-types 0
python $G --field-types $K4
python $G --field-types $OLD

# the stands did not move when the 3 hectare stands went from 6 types to 5
# (cff45d9 is the merge of PR #40; it holds the 6-type stand files, which f4ca143 replaced)
python odisha_script/check_stands_unchanged.py --ref cff45d9 --expect-new-run
```

One chance test of both stand sizes takes about six minutes alone on an idle machine (PR #40's
file records 61 s + 107 s and 63 s + 106 s for the two sizes) and several times that when runs
share the machine.

A check never overwrites a primary file: the scripts add a suffix worked out from the options
(`_excl0`, `_ft-k4`, `_ft-allrows`, `_v120` or `_v120_3ha` for one stand size alone, `_rot120`
for a short test run).

The stands need Earth Engine. `odisha_script/run_config_passes.sh <logfile> <config.yaml> [...]`
runs a config through segmentation, type assignment and export in up to three passes; a first
pass on an empty cache usually hits Earth Engine's memory limit and the next pass completes from
what the first one stored. **Do not start it again while tasks from an earlier start are still
queued:** it looks only for finished results, so it would submit a second copy of each.
Re-joining the plots after a new run:
`python odisha_script/odisha_phase2_3_join.py --set districts --arms v120_3ha --out-dir odisha_script/phase3_3ha/`.

## Files

| File | What it is |
|---|---|
| `PHASE3_PREDECLARED.md` | The primary analysis and the three checks, fixed before any score was recomputed |
| `odisha_phase3_0_field_types.csv`, `odisha_phase3_0_results.txt` | Primary field types (trees only, five) and how they were chosen |
| `odisha_phase3_0_field_types_k4.csv`, `odisha_phase3_0_results_k4.txt` | Field types for check S2 |
| `odisha_phase3_0_field_types_allrows.csv`, `odisha_phase3_0_results_allrows.txt` | Field types for check S3 (PR #40's) |
| `odisha_phase3_2_k_elbow_odisha_v120_handcrafted.txt`, `odisha_phase3_2_k_elbow_odisha_v120_3ha.txt` | Elbow for the number of stand types, per stand size |
| `odisha_phase3_1_score_v120_merged_districts.txt`, and the same name ending `_excl0`, `_ft-k4`, `_ft-allrows` | 10 hectare scores: primary, S1, S2, S3 |
| `odisha_phase3_1_score_v120_3ha_merged_districts_3ha.txt`, and the same name ending `_excl0`, `_ft-k4`, `_ft-allrows` | 3 hectare scores: primary, S1, S2, S3 |
| `odisha_phase3_3_results.txt`, `odisha_phase3_3_results_excl0.txt`, `odisha_phase3_3_results_ft-k4.txt`, `odisha_phase3_3_results_ft-allrows.txt` | Chance tests of both stand sizes: primary, S1, S2, S3 |
| `phase3_3ha/` | The 3 hectare stands joined to the plots |
| `phase3_before_regroup/` | Chance tests run on 2026-10-07 on PR #40's stand files (6 stand types at 3 hectares). Not results; see its README |
| `phase2_vectors/odisha_v120_3ha_*` | The 3 hectare stand files, now with 5 stand types |
| `odisha_phase3_stands_unchanged.txt`, `check_stands_unchanged.py` | The outline by outline comparison of the stand files before and after the regroup (the script's printed output, saved from a run with `--ref main` before this branch was merged), and the script |
| `copy_upstream_cache.py`, `run_config_passes.sh` | The two helpers for Earth Engine runs |

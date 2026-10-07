# Phase 3 status

How well do the pipeline's stands match the Odisha field data when stands are held to the 2-3
hectares the supervisor asked for? This note says what was run, what it found, how firm that is,
and what is still running.

Written 2026-10-07. Every score is copied from a results file in this folder, named beside it.
Four kinds of number are not, and each is marked where it appears: the provisional 3 hectare
numbers (from runs whose output is not committed; the commands are under
[Reproducing](#reproducing)), the stand counts and sizes (computed from the stand files), two
figures worked out for this note from the field-type files and the plot table, and the state of
the Earth Engine queue (as seen on 2026-10-07).

The one primary analysis and the three checks were fixed in `PHASE3_PREDECLARED.md` (commit
`845c22c`) **after the scores of PR #40 were known and before any score was recomputed on the new
field types.**

**State of the results**

| Part | State |
|---|---|
| 10 hectare stands: every score, percentile and p-value, in the primary analysis and all three checks | **Final** |
| 10 hectare stands: the p-values after correction for running several tests | **Interim.** Corrected over this stand size's five tests for now; the plan corrects over ten. The final values can only be larger |
| 3 hectare stands, how well they are drawn | **Provisional.** Computed on the stand files of PR #40. Final once a check confirms that the regroup left every stand where it was |
| 3 hectare stands, how well they are labelled | **Not available yet.** Needs the regroup into 5 stand types, which is waiting in the Earth Engine queue |
| Comparing the two stand sizes | Drawing: provisional. Labelling: not available yet |

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
- **Regroup**: giving the 3 hectare stands their types again, 5 instead of 6. It should not
  move any stand boundary.
- **Elbow rule**: sort the items into 2, 3, ... up to 12 groups and plot how tightly the groups
  fit against the number of groups. More groups always fit tighter, but at some point the curve
  bends and extra groups add little. That bend, the elbow, is the number taken.

---

## The answer

*The supervisor's question: run the hand-crafted pipeline on the Odisha sites, merge stands to at
most 2-3 hectares, give each stand a type with k-means, and find a way to say how well the stands
are drawn and how well they are labelled, taking the field data as truth.*

**Neither stand size can be shown to group plots that are alike on the ground better than a
randomly placed copy of the same stand map does (3 hectares: provisional), and the 10 hectare
stand types cannot be shown to match the field types better than chance.** This is the answer
PR #40 gave. It now rests on a cleaner field truth, and it holds under the three checks declared
in advance: finally at 10 hectares, provisionally at 3.

This says the stands cannot be told from chance *with this field data*. It does not say they are
shown to be poor: with 20 villages the data could miss a real effect of modest size.

| What is scored | 10 hectare stands | 3 hectare stands |
|---|---|---|
| **Drawing**, all 267 plots: do plots of the same field type share a stand? | 0.0121, at the 94th percentile of chance | 0.0060, 92nd percentile (provisional) |
| **Drawing**, only stands that hold two or more plots | 0.0257, 77th percentile | 0.0244, 66th percentile (provisional) |
| **Labelling**: do plots of the same field type get the same stand type? | 0.0389, 67th percentile | not available yet |

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
main ones and [Results](#results) has all five. Eight are computed: five final at 10 hectares and
three provisional at 3 hectares. The best of them is the 94th percentile above, which means 6.3%
of randomly placed maps score as well (p = 0.063). The two still to come are the 3 hectare
labelling tests. With ten tests, one would need p below about 0.005 (0.05 divided by ten) to
change the conclusion.

**Where the data leans, so that nobody has to find it.** Drawing on all plots sits between the
86th and the 97th percentile in all eight combinations of stand size and field typing, and in
three of them it passes the 95th when read alone (95.7 at 10 hectares with four field types; 96.7
and 96.5 at 3 hectares, provisional). None survives the correction, and the eight are not
independent of one another (same plots, same stands, overlapping field types). On the fairer
drawing test, which uses only stands that hold two or more plots, nothing is above the 91st. This
is why the answer says "cannot be shown" and not "no effect".

**Two things are still open, both at 3 hectares:** how the stands are labelled (not available
yet), and the check that re-running with 5 stand types left every stand outline where it was.
The outlines should not change, because no step before the one that gives stands their type reads
that number. Until the check is done every 3 hectare number here is called provisional.

For scale: treat each village as if it were one stand, with no stand map at all, and the
agreement score with the field types is 0.076 (0.089 worked out within districts, as labelling
is). Both are printed in the header of `odisha_phase3_3_results_v120.txt`. This is for scale
only. The score is lower for any map with smaller groups, so it does not show that villages are
more informative than stands.

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
a `stand_lbl`). The last two rows are from the score files. The 3 hectare column describes the
stand files of PR #40, which the regroup should leave unchanged. The size limit is slightly soft
at both sizes: 10 of the 10 hectare stands exceed 10 hectares, by at most 0.08.

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
  gives 5 everywhere, so 6 was the wrong number. Only the labelling depends on it. The stand
  boundaries do not.
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
| Labelling | Agreement between field type and stand type, worked out inside each district and averaged with each district weighted by its number of plots. Uses 266 of the 267 plots: one plot's stand has no type |
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
- **Many tests are run, so one small p is expected by luck.** The headline tests are corrected
  together (Holm's method: the smallest p is multiplied by the number of tests, the next by one
  fewer, and so on). A result counts only if it survives that.
- **Ten tests in the plan, five in the files so far.** The plan corrects over ten tests, five
  for each stand size, in one run of both. Until the 3 hectare labelling is in, the 10 hectare
  files (`..._v120.txt`) correct over that size's five tests only, and say of themselves that
  they are not the primary analysis for that reason. Over ten tests the corrected values are
  1.6 to 2 times as large (0.315 becomes between 0.50 and 0.63, depending on the two tests still
  to come), so the conclusion can only get firmer. The scores, percentiles and uncorrected p are
  final; the corrected p is not.
- **The 20 village forests are the independent units**, not the 267 plots. Tests that shuffle
  individual plots look far more convincing than they should here and are not reported.

---

## Results

### Primary analysis, 10 hectare stands (scores final, correction interim)

Field types from trees only, five types. 10 hectare stands with 6 stand types.
Files: `odisha_phase3_1_score_v120_merged_districts.txt`, `odisha_phase3_3_results_v120.txt`.

| Score | Real stand map | Randomly placed map: middle value (range holding 90% of them) | Percentile | p |
|---|---|---|---|---|
| Drawing, all plots | 0.0121 | 0.0096 (0.0073 to 0.0124) | 93.7 | 0.063 |
| Drawing, shared stands | 0.0257 | 0.0228 (0.0172 to 0.0299) | 77.0 | 0.230 |
| Same-stand precision | 0.5385 | 0.5337 (0.4817 to 0.5901) | 55.2 | 0.451 |
| Labelling | 0.0389 | 0.0337 (0.0139 to 0.0564) | 66.8 | 0.332 |
| Far-apart labelling | −0.0118 | −0.0108 (−0.0301 to 0.0118) | 46.6 | 0.534 |

**Nothing reaches the 95th percentile, and 0 of the 5 tests survive the correction.**

- The closest is drawing on all plots, at 93.7 (p = 0.063). Corrected over this stand size's
  five tests it is 0.315; over the plan's ten it will be between 0.50 and 0.63.
- On the fairer drawing test, shared stands, the real map sits at 77.0. About one randomly placed
  map in four does as well.
- Of the pairs of plots that share a stand, 53.8% have the same field type. A randomly placed map
  gives 53.4%.
- Labelling sits at 66.8. The far-apart score is slightly negative: plots the field calls alike
  are, if anything, a little less likely to get the same stand type than plots it calls different.
  A randomly placed map gives the same.

### Primary analysis, 3 hectare stands: drawing (provisional)

Same field types. These three scores depend only on where the stand boundaries are, not on the
stand types, so they can be computed before the regroup, on the stand files of PR #40. They are
provisional until the regrouped stands are confirmed identical to those. Not from a committed
file.

| Score | Real stand map | Randomly placed map: middle value (range holding 90% of them) | Percentile | p |
|---|---|---|---|---|
| Drawing, all plots | 0.0060 | 0.0045 (0.0031 to 0.0062) | 92.1 | 0.080 |
| Drawing, shared stands | 0.0244 | 0.0223 (0.0143 to 0.0321) | 65.7 | 0.344 |
| Same-stand precision | 0.5575 | 0.5306 (0.4607 to 0.6079) | 71.7 | 0.284 |

Nothing reaches the 95th percentile here either. On the fairer test, shared stands, about one
randomly placed map in three does as well as the real one.

### Primary analysis, 3 hectare stands: labelling

Not available yet. See [Still running](#still-running).

### The three checks declared in advance

Each was fixed in `PHASE3_PREDECLARED.md` before any score was recomputed, to be reported whatever
it showed. 10 hectare stands; each score is followed by its percentile of chance.

| Score | Primary | S1: without the no-tree type | S2: four field types | S3: the PR #40 field types |
|---|---|---|---|---|
| Drawing, all plots | 0.0121 (93.7) | 0.0107 (91.9) | 0.0094 (95.7) | 0.0115 (86.4) |
| Drawing, shared stands | 0.0257 (77.0) | 0.0225 (72.1) | 0.0217 (90.4) | 0.0236 (65.6) |
| Same-stand precision | 0.5385 (55.2) | 0.5854 (54.7) | 0.6599 (61.9) | 0.5344 (37.4) |
| Labelling | 0.0389 (66.8) | 0.0229 (34.3) | 0.0340 (57.4) | 0.0354 (45.4) |
| Far-apart labelling | −0.0118 (46.6) | −0.0318 (12.3) | −0.0053 (35.9) | −0.0185 (32.0) |
| Plots scored (labelling uses one fewer) | 267 | 251 | 267 | 267 |
| Plots in shared stands | 184 in 61 stands | 168 in 59 stands | 184 in 61 stands | 184 in 61 stands |
| Smallest p of the five, and corrected over the five | 0.063, 0.315 | 0.082, 0.408 | 0.043, 0.217 | 0.137, 0.683 |
| Tests surviving the correction | 0 of 5 | 0 of 5 | 0 of 5 | 0 of 5 |

Files: `odisha_phase3_3_results_excl0_v120.txt` (S1), `odisha_phase3_3_results_ft-k4_v120.txt`
(S2), `odisha_phase3_3_results_ft-allrows_v120.txt` (S3), and the matching
`odisha_phase3_1_score_v120_merged_districts_*.txt`.

**No check changes the conclusion.** What each one shows:

- **S1, without the no-tree type** (16 of the 267 scored plots dropped; one Koraput village is left
  with no plot, so 19 villages). The question was whether any agreement rested on the easy
  contrast of trees against no trees. Drawing barely moves: the percentiles go from 93.7 and 77.0
  to 91.9 and 72.1. Labelling falls from 0.0389 to 0.0229, from the 67th to the 34th percentile,
  and the far-apart score falls to the 12th. Both labelling positions are inside what chance
  gives, so this does not show that labelling depended on the no-tree plots. It shows there was
  no labelling agreement to lose. The fall comes entirely from Koraput (0.0248 to −0.0139),
  where 11 of the 16 dropped plots sit in two villages (counted from the plot table); Dhenkanal
  is unchanged, and Angul and Kendujhar rise.
- **S2, four field types.** All 274 plots sorted into four: the no-tree group stays (18 plots) and
  the plots with trees form three groups (155, 42 and 59) instead of four. This grouping agrees
  with the primary one at only 0.544 (computed from the two field-type files), so it is a real
  change of truth. The drawing scores sit
  higher against chance than with five types: 95.7 on all plots and 90.4 on shared stands. The
  first, read alone, passes a 5% test (p = 0.043). It is one of five tests in one of four
  analyses, and corrected within its own analysis it is 0.217. Among the final numbers it is the
  strongest hint that the stand boundaries carry some information about forest structure. It is
  not a finding.
- **S3, the PR #40 field types.** Every 10 hectare number of PR #40 is reproduced exactly, so
  nothing in the scoring or the chance test moved when the options for the checks were added.

Across the four analyses there are 20 tests on the 10 hectare stands. The smallest p among them is
0.043, which is unremarkable among 20 tests.

**The same checks on the 3 hectare stands, drawing only (provisional, not from a committed file):**

| Score | Primary | S1: without the no-tree type | S2: four field types | S3: the PR #40 field types |
|---|---|---|---|---|
| Drawing, all plots | 0.0060 (92.1) | 0.0048 (86.6) | 0.0049 (96.7) | 0.0066 (96.5) |
| Drawing, shared stands | 0.0244 (65.7) | 0.0190 (54.7) | 0.0197 (75.5) | 0.0253 (74.9) |
| Same-stand precision | 0.5575 (71.7) | 0.5955 (61.0) | 0.6991 (81.5) | 0.5929 (83.7) |
| Plots in shared stands | 113 in 44 stands | 100 in 40 stands | 113 in 44 stands | 113 in 44 stands |

One thing repeats at both sizes: drawing on all plots passes the 95th percentile under four field
types (p = 0.043 at 10 hectares, 0.034 at 3). At 3 hectares it also passes under the PR #40 field
types (p = 0.036, the number PR #40 reported); at 10 hectares it does not (86.4). None comes near
surviving a correction over ten tests. On shared stands nothing at 3 hectares is above the 76th
percentile. The S3 column equals PR #40 exactly, which it must, because these are PR #40's stand
files.

### Comparing the two stand sizes

Drawing only, and provisional (not from a committed file). The question is not "which stand size
scores higher" but "do they differ by more than randomly placed maps of the two sizes differ".

| Score | 3 hectare minus 10 hectare | The same difference for randomly placed maps: middle value (range holding 95% of them) | Percentile |
|---|---|---|---|
| Drawing, all plots | −0.0061 | −0.0050 (−0.0086 to −0.0016) | 27.7 |
| Drawing, shared stands | −0.0013 | −0.0006 (−0.0129 to 0.0137) | 44.8 |
| Same-stand precision | +0.0191 | −0.0024 (−0.1108 to 0.1118) | 65.6 |

(Differences are taken before rounding, so the last digit can differ by one from subtracting the
tables above.)

**The data cannot tell the two stand sizes apart on drawing.** All three differences sit well
inside what chance gives.

One trap. At 3 hectares the all-plots drawing score is lower (0.0060 against 0.0121), and it
stays lower whichever villages are included: repeating the comparison on random re-selections of
the 20 villages puts the difference between −0.0153 and −0.0014 in 95% of them. That looks like
worse drawing and is not. Smaller stands hold fewer pairs of plots, which lowers this score for
any map: randomly placed maps drop by almost as much (−0.0050 against −0.0061). The two-size
results file prints this warning beside the number. (PR #40's committed file,
`odisha_phase3_3_results.txt`, carries the same warning with its own numbers.)

Labelling cannot be compared until the regroup finishes.

### What I said beforehand, and what happened

From `PHASE3_PREDECLARED.md`: *"I expect the primary scores to move in the third decimal and the
conclusion of PR #40 (neither stand size beats chance on drawing or labelling) to stand. I have no
expectation for S1 and S2. If any primary headline test survives the Holm correction, that is a
change of conclusion and will be reported as one."*

- **10 hectare stands: as expected for the scores and the conclusion.** The scores moved in the
  third or fourth decimal (0.0115 to 0.0121, 0.0236 to 0.0257, 0.0354 to 0.0389) and no primary
  test survives the correction.
- **3 hectare stands, drawing (provisional): partly.** The two agreement scores moved as expected
  (0.0066 to 0.0060, 0.0253 to 0.0244). Same-stand precision moved more than I predicted, in the
  second decimal (0.5929 to 0.5575). The conclusion stands so far. The labelling half cannot be
  judged until the regroup finishes.
- **What I did not expect:** the percentiles moved much more than the scores (10 hectare drawing
  on all plots 86.4 to 93.7, labelling 45.4 to 66.8). The chance level hardly moved (0.0097 to
  0.0096 for drawing), and randomly placed maps all score within a very narrow band, so a change
  of 0.0006 in the score shifts its position among them by seven points. Percentiles near the top
  of that band are fragile, which is one more reason to read them only after the correction.

---

## What changed since PR #40

The numbers are already in the tables above: PR #40's are the **S3** columns and the new ones are
the **Primary** columns, at both stand sizes. The one number with no counterpart yet is 3 hectare
labelling, which PR #40 gave as 0.0560 at the 49th percentile on 6 stand types.

The cleaner field truth moved the two stand sizes in opposite directions: every 10 hectare
percentile went up and every 3 hectare drawing percentile went down (provisional). The one number
in PR #40 that passed a 5% test when read alone, 3 hectare drawing on all plots at p = 0.036, is
now at p = 0.080. That is consistent with scores that sit at chance level: a small change in the
truth moves them either way.

---

## Corrections and departures from plan

Listed so that nothing has to be discovered later.

1. **The first scorer pooled stand numbers and stand types across districts** (fixed in `e261f3d`,
   before PR #40 merged). Both restart in each district, so 18 of the 10 hectare stands' 58
   apparent shared stands, and 24 of the 3 hectare stands' 55, were different stands with the
   same number. No test had been run yet, but one reading changed: the 3 hectare stands hold 113
   plots in 44 shared stands, not 149 in 55 as I first reported, so smaller stands cost more
   testing power than I first said.
2. **The 3 hectare stands were given 6 stand types without checking** (fixed in `ef9b510`). Their
   own elbow gives 5. The 3 hectare labelling numbers in PR #40 are on 6 types and are superseded
   once the regroup finishes.
3. **The field measurements did not count the same rows** (fixed in `845c22c`), as described under
   "The field truth".
4. **The scorer and the chance test were edited after the plan was fixed** (`fe80260`), to add
   the options the three checks need. The plan had said the two scripts would be used "as it
   stands". With the old field types they reproduce PR #40 exactly, at both stand sizes.
5. **The regroup reuses stored results instead of recomputing them** (`copy_upstream_cache.py`,
   `43e8c1d`). Changing the number of stand types changes the cache key of every stage, although
   no step before the one that assigns stand types reads that number. With the project's Earth
   Engine queue as slow as it is, recomputing everything meant about a day for work that could
   not change. The script copies the earlier stages' stored results to the new key, and refuses
   to run unless the two configs differ in nothing but the number of stand types. **What this
   gives up:** redrawing the stands from scratch would have confirmed independently that they
   come out the same. `check_stands_unchanged.py` replaces that; see "Still running".
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
- **No plot radius.** Trunk area is a plot total, not per hectare. It is comparable between plots
  only if every plot is the same size.
- **No tree positions.** A plot is a single point. A plot that straddles a stand boundary cannot
  be seen as such.
- **Five field types is a judgement**, as set out above. The checks cover four types and the old
  grouping. Six types, the more frequent alternative, is not checked, because the six-type
  grouping changes with the random start of the method (`PHASE3_PREDECLARED.md`). A different
  choice of measurements is not checked either.
- **The number of stand types is not varied.** Scores are given for 6 at 10 hectares and, once
  the regroup finishes, 5 at 3 hectares. Koraput, with over half the plots, is run at 6 at
  10 hectares although its own elbow gives 5.
- **Three no-tree plots carry crown cover readings above 10%** (98%, 43% and 18%, in
  `odisha_phase3_0_field_types.csv`). They are left as recorded. Two of them are among the scored
  plots.
- **The two stand sizes differ in three settings**, so they are two versions of the method, not a
  clean experiment on stand size.

---

## Still running

The 3 hectare stands are being regrouped into 5 types on Earth Engine: 8 tasks, 2 per district.

**Why it is slow.** The project is over its free monthly compute allowance, and Earth Engine has
put it in "restricted mode" (the warning is printed in every `run_3ha_k5_<district>.log`).
Tasks still run, but fewer at a time and on fewer machines. The allowance resets on the first of
each month. On 2026-10-07 at 10:30 the 8 tasks were queued behind 31 tasks of another job in the
same project, which was finishing about one every half hour. That puts the start of the regroup
some 15 hours later, if nothing else joins the queue. No firmer time can be given.

**Do not start the runs again while the tasks are still queued.** The four
`run_config_passes.sh` runs started on 2026-10-07 are waiting on the tasks and go on to export
the stand files by themselves. If the machine was restarted, wait until the 8 tasks
(`odisha_v120_3ha_<district>_clustering_...`) show as completed on the Earth Engine task page,
and only then run the command below: started earlier, it does not see the queued tasks and
submits a second copy of each. (It handles the districts one after another.)

```bash
for d in kendujhar angul dhenkanal koraput; do
  odisha_script/run_config_passes.sh odisha_script/run_3ha_k5_$d.log configs/odisha_v120_3ha_$d.yaml
done
```

Then, in this order:

1. **Confirm the export has landed and the stands did not move.** Every
   `odisha_script/run_3ha_k5_<district>.log` must end with `=== run_config_passes FINISHED ok ===`.
   Then:

   ```bash
   python odisha_script/check_stands_unchanged.py --ref main --expect-new-run
   ```

   It compares the stand files on disk with the committed ones outline by outline: every
   building block must have the same outline, every stand the same outline, stand number and
   area, and only the stand type may differ (it prints how many kinds there are before and
   after; expect 6 and 5). `--expect-new-run` makes it fail if the
   files on disk are still the old run's, which is what they are today. Without that flag the
   check would pass before the regroup had exported anything. **If it fails, the stands changed,
   the provisional numbers above are void, and the work stops there until the reason is known.**
   A `git diff` cannot do this job: each stand file is a single line.

2. **Join the plots to the new stand files, and confirm the scores carry over.** With the PR #40
   field types the two drawing scores must come out at exactly **0.0066** and **0.0253**.

   ```bash
   python odisha_script/odisha_phase2_3_join.py --set districts --arms v120_3ha --out-dir odisha_script/phase3_3ha/
   score3() { python odisha_script/odisha_phase3_1_pairwise_score.py --arm v120_3ha --tag _3ha \
                  --joined odisha_script/phase3_3ha/phase2_plots_joined_districts.csv "$@"; }
   score3 --field-types odisha_script/odisha_phase3_0_field_types_allrows.csv    # S3: must print 0.0066 and 0.0253
   ```

3. **Score the 3 hectare stands.**

   ```bash
   score3                                                                       # primary
   score3 --exclude-types 0                                                     # S1
   score3 --field-types odisha_script/odisha_phase3_0_field_types_k4.csv        # S2
   ```

4. **Run the chance test on both stand sizes together.** The first command replaces
   `odisha_phase3_3_results.txt`, which until then is PR #40's file.

   ```bash
   G=odisha_script/odisha_phase3_3_significance.py
   python $G                                                                    # primary: ten tests
   python $G --exclude-types 0                                                  # S1
   python $G --field-types odisha_script/odisha_phase3_0_field_types_k4.csv     # S2
   python $G --field-types odisha_script/odisha_phase3_0_field_types_allrows.csv  # S3
   ```

5. **Update this note**: the 3 hectare columns, the comparison of the two sizes, the count out of
   ten tests with the corrected p-values, and the 3 hectare half of the prediction. Then remove
   the one-size files (`..._v120.txt`), which the two-size files replace.

Why the provisional numbers are expected to hold: the regroup reuses the stored building blocks,
and the step that joins them into stands has no randomness. The runs of 2026-10-07 have already
re-joined them and report the same number of stands as PR #40 in every district (183, 200, 462
and 1,109). Step 1 checks the outlines themselves instead of assuming it.

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
python $S --arm v120
python $S --arm v120 --exclude-types 0
python $S --arm v120 --field-types odisha_script/odisha_phase3_0_field_types_k4.csv
python $S --arm v120 --field-types odisha_script/odisha_phase3_0_field_types_allrows.csv

# chance test, 10 hectare stands: primary, then S1, S2, S3
G=odisha_script/odisha_phase3_3_significance.py
python $G --arms v120
python $G --arms v120 --exclude-types 0
python $G --arms v120 --field-types odisha_script/odisha_phase3_0_field_types_k4.csv
python $G --arms v120 --field-types odisha_script/odisha_phase3_0_field_types_allrows.csv

# the PROVISIONAL 3 hectare numbers and the comparison of the two sizes.
# Valid only while phase2_vectors/ still holds PR #40's 3 hectare stand files. Written outside the
# repo on purpose: in these files the 3 hectare LABELLING rows score the old 6 stand types and
# must not be used.
P=/tmp/phase3_provisional
python $G --out-dir $P
python $G --out-dir $P --exclude-types 0
python $G --out-dir $P --field-types odisha_script/odisha_phase3_0_field_types_k4.csv
python $G --out-dir $P --field-types odisha_script/odisha_phase3_0_field_types_allrows.csv
```

One chance test for one stand size takes about 3 minutes alone on an idle machine (PR #40's file
records 61 s + 107 s) and several times that when runs share the machine.

A check never overwrites a primary file: the scripts add a suffix worked out from the options
(`_excl0`, `_ft-k4`, `_ft-allrows`, `_v120` for one stand size, `_rot120` for a short test run).

The stands need Earth Engine. `odisha_script/run_config_passes.sh <logfile> <config.yaml> [...]`
runs a config through segmentation, type assignment and export in up to three passes; a first
pass on an empty cache usually hits Earth Engine's memory limit and the next pass completes from
what the first one stored. Read the warning under "Still running" before starting it again.

## Files

| File | What it is |
|---|---|
| `PHASE3_PREDECLARED.md` | The primary analysis and the three checks, fixed before any score was recomputed |
| `odisha_phase3_0_field_types.csv`, `odisha_phase3_0_results.txt` | Primary field types (trees only, five) and how they were chosen |
| `odisha_phase3_0_field_types_k4.csv`, `odisha_phase3_0_results_k4.txt` | Field types for check S2 |
| `odisha_phase3_0_field_types_allrows.csv`, `odisha_phase3_0_results_allrows.txt` | Field types for check S3 (PR #40's) |
| `odisha_phase3_2_k_elbow_odisha_v120_handcrafted.txt`, `odisha_phase3_2_k_elbow_odisha_v120_3ha.txt` | Elbow for the number of stand types, per stand size |
| `odisha_phase3_1_score_v120_merged_districts.txt`, and the same name ending `_excl0`, `_ft-k4`, `_ft-allrows` | 10 hectare scores: primary, S1, S2, S3 |
| `odisha_phase3_3_results_v120.txt`, `odisha_phase3_3_results_excl0_v120.txt`, `odisha_phase3_3_results_ft-k4_v120.txt`, `odisha_phase3_3_results_ft-allrows_v120.txt` | 10 hectare chance tests: primary, S1, S2, S3. Each says it is "not the primary analysis" because it holds one stand size and corrects over five tests |
| `odisha_phase3_3_results.txt` | **Still the PR #40 file** (both stand sizes, old field types, 6 stand types at 3 hectares). Replaced by the primary two-size run when the regroup finishes |
| `odisha_phase3_1_score_v120_3ha_merged_districts_3ha.txt`, `phase3_3ha/` | **Still the PR #40 files** for the 3 hectare stands. Replaced when the regroup finishes |
| `check_stands_unchanged.py` | Compares stand files on disk with committed ones, outline by outline |
| `copy_upstream_cache.py`, `run_config_passes.sh` | The two helpers for Earth Engine runs described above |

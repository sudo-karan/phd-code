# Evaluation metrics: the list for approval

How should a stand map be scored against whatever reference data a site has? This note lists the
metrics proposed, says what each one measures and what can make it mislead, names the papers
behind each, and reports how the metrics behaved on generated data where the right answer is
known.

Drafted 2026-10-13 for Jaskaran and his supervisor. **Nothing here has been run on Odisha or
Sanjay Van data.** The list is for approval first.

## Summary

1. **The list.** With field plots: the adjusted Rand index, a pair-by-pair comparison inside
   villages and distance bands, the Mantel and partial Mantel tests, ANOSIM and PERMANOVA, each
   asked once about where the stand boundaries are drawn and once about the types given to the
   stands. With reference polygons: over- and under-segmentation and a boundary match. With no
   reference data: explained variance and the Global Score, on layers the pipeline did not use.
2. **Only one way of simulating chance was sound on generated data.** When the map had nothing to
   do with the field data, the rotation null gave a false alarm in 3.0% to 8.3% of data sets
   (5% is correct; average 5.9%; one statistic of twelve flagged). A separately declared
   follow-up on 600 fresh data sets gave 4.2% to 6.7%, average 5.1%, none flagged. Shuffling plots inside villages
   gave false alarms in 90% to 93% of data sets for three of the stand statistics. So every
   p-value should come from the rotation null, and the rotation null is a test behind an
   established statistic, never a score of its own.
3. **The field data can only see a fairly strong map.** On a generated layout of 267 plots in 20
   villages, only about 62 pairs of plots shared a stand. A map that accounts for 14% of the variance of the field
   measurements is detected four times in five by 3 of the 11 readable statistics; one that
   accounts for 40% by 10 of 11.
4. **Three statistics have a blind spot.** The adjusted Rand index for the drawing scores a map
   with stands four times too large above the right map. ANOSIM and PERMANOVA on stands do not
   notice when every stand is cut in two. Both are properties of the statistics, not code faults.
5. **What is needed now.** The supervisor approves, strikes or adds to the list and answers the
   questions in section 6. Then the analysis is written down in advance (section 8). The run
   script refuses to start without that written statement. An independent statistical review of
   the module has been done; section 7 says what it checked and what it changed.

## The metrics at a glance

| Metric | Needs | What it asks, in one line | Name in the code | Paper support |
|---|---|---|---|---|
| Rand index, adjusted Rand index: drawing | field plots | Do plots of the same field type share a stand? | `ari_drawing` | source papers; one comparison favours the adjusted form; a methods paper recommends it |
| Adjusted Rand index: labelling | field plots, stand types | Do plots of the same field type get the same stand type, inside a district? | `ari_labelling` | as above |
| Pair comparison in villages and distance bands | field plots, coordinates | At the same distance and in the same village, are two plots the map puts together more alike than two it keeps apart? | `pair_stand`, `pair_type` | none: a stratified difference of means, built for the brief |
| Mantel test | field plots | Are pairs the map calls different more different in the field? | `mantel_stand`, `mantel_type` | used in a related study; simulation studies argue against it with spatial data |
| Partial Mantel test | field plots, coordinates | The same, with geographic distance held fixed | `partial_mantel_stand`, `partial_mantel_type` | source paper (title only); two studies show it does not cure the spatial problem |
| ANOSIM | field plots | Are plots of one stand (or type) closer in rank to each other than to other plots of the village? | `anosim_stand`, `anosim_type` | source papers; used on mapped forest classes |
| PERMANOVA | field plots | Analysis of variance from distances: how much of the spread lies between stands (or types)? | `permanova_stand`, `permanova_type` | source paper read in full; one comparison favours it over ANOSIM and Mantel, for balanced designs only |
| Rotation null | stand map, coordinates | Not a metric. The chance test behind every statistic above. | `rotation` | no paper validates this exact procedure; three published relatives |
| Over- and under-segmentation, D | reference polygons | Is a reference polygon cut into several stands, or does a stand run across its edge? | `over`, `under`, `d` | source paper (abstract; formulas from secondary description); used for forest stands |
| Boundary match | reference polygons | What share of the boundary length do the two maps have in common, within a tolerance? | `boundary_precision`, `boundary_recall`, `boundary_f` | source paper read in full (computer vision); our vector adaptation |
| Explained variance | a layer the pipeline did not use | What share of a layer's variation lies between stands? | `r2` | used for forest stands |
| Global Score | the same, and a set of candidate maps | Are stands alike inside and different from their neighbours? | `global_score` | source (title only); used for forest stands; one paper states a serious limit |

## How to read this note

**Words used**

- **Stand**: one polygon of the pipeline's map. **Stand type**: the kind of forest the pipeline
  gives a stand (k-means on satellite features). **Field type**: the kind of forest a plot is,
  from the field measurements.
- **Drawing** and **labelling**: the two things a stand map does. It draws boundaries, and it
  labels each stand with a type. A statistic with `stand` or `drawing` in its name tests the
  first, one with `type` or `labelling` the second.
- **Village** (in the code, *group*): the unit the plots were laid out in. **District** (*super-
  group*): the unit the stand types were fitted in.
- **Pair**: two plots. 267 plots make 35,511 pairs, but they are still only 267 plots, so pairs
  are never treated as independent measurements here.
- **Null model**: a way of simulating "the map knows nothing about the forest", many times, to
  see what scores chance alone produces. **p-value**: the share of those simulations that score
  at least as well as the real map. **False alarm**: a small p-value when the map really does know
  nothing. A sound test gives a false alarm 5% of the time at the 0.05 level.
- **Power**: how often a test detects agreement that is really there.

**Strength of support.** For every paper the note says one of three things, as the working rules
ask: (a) **used**: others use the method, or the paper is its source; (b) **recommended**: a
review or methods paper recommends it; (c) **shown better**: a comparison shows it beats
alternatives. The weakest one that can be defended is given. A paper that introduces a method
and applies it is counted as *used*, not as *recommended*: its authors are not an independent
voice. Several papers are cited for a limit, not in favour; the text says so each time.

**Verified** means the DOI was looked up on Crossref and the title and first author returned
match. It does not mean the paper was read: beside each paper the note says what was read (title
only, abstract, or full text). A formula not read in the paper itself is marked "from secondary
description". Papers that could not be verified are marked **UNVERIFIED**. The full reference
list, with everything that was considered and left out, is at the end.

**Where the code is.** `src/fmu/evaluation/`, committed as `ab1e286`, with 255 tests that check
each function against answers worked out by hand or by an independent library. It is general:
functions take arrays, and nothing in it names a site.

---

## 1. Sites with field plots that have measurements

All statistics in this section are oriented so that **larger means the map agrees better with the
field**, and every test is one-sided in that direction. This was fixed in the specification before
anything was run. A map worse than chance is not rewarded with a small p-value.

Every statistic comes in two forms:

- **stand / drawing**: about which plots share a stand;
- **type / labelling**: about which plots share a stand type. Types are only ever compared inside
  one district (section 5).

None of the values below should be read without its chance test (section 1.6). On generated data
several of these statistics take clearly positive values for a map that has nothing to do with
the field.

### 1.1 Rand index and adjusted Rand index

**What it measures.** Take two ways of grouping the same plots, for example "by stand" and "by
field type". For every pair of plots ask whether the two groupings agree: both put the pair
together, or both keep it apart. The Rand index is the share of pairs on which they agree. The
adjusted Rand index subtracts the agreement two unrelated groupings of the same sizes would reach
by chance, so that 0 means "no better than chance" and 1 means "the same grouping".

- *Drawing* (`ari_drawing`): field type against stand.
- *Labelling* (`ari_labelling`): field type against stand type, worked out inside each district
  and pooled over districts by pair counts.

**Why it is on the list.** It is the supervisor's first request (Rand index and the like), and it
is the index Phase 3 used.

**How to read a value.** For the adjusted index, 0 is chance under the textbook assumption that
plots are independent, and 1 is a perfect match. Neither end applies as it stands here:

- *The ceiling is far below 1 for the drawing.* The index treats the two groupings as equals.
  When stands are much finer than field types it cannot get near 1 even if every stand is pure.
  On the generated layout the highest reachable value was 0.014. The code returns this ceiling
  (`adjusted_rand_max`) and it must be printed beside every drawing index, with the number of
  same-stand pairs, the number of stands holding two or more plots, and the pair table. A low
  index with a low ceiling says "the map is finer than the field typology", not "the map is
  wrong".
- *Zero is not the chance level.* Nearby plots are alike and also share stands, so an unrelated
  map scores above zero. The chance level is measured with the null model.

**What can make it mislead**

- **It rewards larger stands.** On generated data `ari_drawing` scored a map with stands four
  times too large above the planted map in 10 of 10 data sets (0.0128 against 0.0087). Larger
  stands put more pairs together and the index goes up. So it **must not be used to compare maps
  of different stand sizes** (for example the 10 hectare and 3 hectare maps). As a test against
  chance under the rotation null it still held its false-alarm rate (0.063) but was the weakest
  of the twelve (section 4).
- **The raw Rand index is close to useless here.** Its value is driven largely by pairs that are
  apart in both groupings (Warrens and van der Hoef 2022). With many small stands nearly all
  pairs are of that kind, so the raw index sits near its top whatever the map does. It is
  reported for completeness and never alone.
- **Unequal group sizes.** The overall index mainly reflects agreement on the large groups and
  says little about small ones (Warrens and van der Hoef 2022). The per-district table is printed
  beside the pooled labelling index for that reason.
- **The chance correction assumes one particular model of chance**: group numbers and sizes fixed
  and plots shuffled freely. Other models can change which of two groupings ranks higher, and the
  choice "should be carefully justified" (Gates and Ahn 2017). Here the correction is not relied
  on: the chance level is measured by the rotation null.
- **Thin evidence for this use.** The one comparison that favours the adjusted index is about
  recovering a known cluster structure, not about maps (Milligan and Cooper 1986). The only verified
  use in a nearby field compares two classifications of vegetation plots (Asadi et al. 2021).
  **No verified paper was found that uses the index to compare delineated forest stands with
  field plot types.**
- **Not estimable cases.** If both groupings put all plots together, or both put every plot
  alone, the code returns "not estimable" where scikit-learn returns 1.0, because nothing was
  tested.
- **Pooling differs from Phase 3.** The labelling index is pooled over districts by pair counts.
  Phase 3 used a plot-weighted mean of per-district indices. The two give different numbers
  (question 8).

**Where it is implemented.** `fmu.evaluation.agreement`: `rand_index`, `adjusted_rand_index`,
`agreement` (returns the ceiling and the pair table), `stratified_agreement` (per district and
pooled), `drawing_statistic`, `labelling_statistic`. Checked against scikit-learn's
`rand_score` and `adjusted_rand_score` in the tests.

**Papers**

- Rand 1971, doi:10.1080/01621459.1971.10482356, verified. *Used* (source of the Rand index).
  Read: abstract only. The abstract says the paper proposes criteria for judging clustering
  methods based on how each pair of points is assigned in two clusterings. The formula above is
  from secondary description.
- Hubert and Arabie 1985, doi:10.1007/bf01908075, verified. *Used* (source of the adjusted
  index). Read: title and record only. That it is the source rests on two abstracts that name it
  (Milligan and Cooper 1986; Steinley 2004). The formula is from secondary description.
- Milligan and Cooper 1986, doi:10.1207/s15327906mbr2104_5, verified. *Shown better*. Read:
  abstract. A comparison of five indices (the Rand index and two adjusted forms among them) for
  recovering a cluster structure known to be in the data; it concludes that the Hubert and Arabie
  adjusted index was best suited to comparison across the levels of a hierarchical clustering,
  and notes deficiencies in the other four. Cluster data, not maps.
- Steinley 2004, doi:10.1037/1082-989x.9.3.386, verified. *Recommended*. Read: abstract. A
  methods paper that calls the index "the cluster validation measure of choice", giving Milligan
  and Cooper 1986 as its authority, and gives a method for testing an observed value. So it
  repeats that comparison's verdict and adds no comparison of its own.
- Warrens and van der Hoef 2022, doi:10.1007/s00357-022-09413-z, verified. *Used*, for two
  limits (above). Read: abstract.
- Gates and Ahn 2017, doi:10.1101/196840, verified. *Used*, for a limit (above). Read: abstract.
  The DOI is the bioRxiv preprint; no journal record with a DOI was found.
- Asadi et al. 2021, doi:10.1007/s13595-020-01017-0, verified. *Used* (a use in vegetation
  classification, in a forest science journal: classifications of the same vegetation plots,
  before and after plots were reassigned, compared with the adjusted Rand index). Read: abstract
  (the copy on the HAL open archive; Crossref holds none).

### 1.2 The pair comparison, inside villages and distance bands

**What it measures.** About every pair of plots the map makes one of three claims: same stand;
different stands of the same type; different types. If the map is useful, two plots it puts
together should be more alike on the ground than two it keeps apart. "How different on the
ground" is the distance between the two plots on their field measurements (height, crown cover,
trunk area, tree count), each first put on a common scale: centred on the median and divided by
the interquartile range, the rule of the Phase 3 field-type script.

Two things besides the map make plots alike, and both are held fixed:

- **distance**: nearby plots are alike whatever the map says, and plots in one stand are nearly
  always nearby. So a pair is compared only with pairs in the same **distance band**;
- **village**: villages differ as wholes. So a pair is compared only with pairs in the same
  village, and two plots from different villages are never paired.

Inside each village and band the result is a difference of two means:

- `pair_stand`: mean field distance of pairs in different stands minus that of pairs in the same
  stand. This reads the drawing.
- `pair_type`: among pairs in *different* stands, mean field distance of different-type pairs
  minus same-type pairs. Same-stand pairs are left out, so it reads the labelling and not the
  drawing a second time.

The village-and-band results are pooled with a declared weight (pairs in one set times pairs in
the other, over their sum), so a village with one same-stand pair counts little.

**Why it is on the list.** The brief asks for it. It is the most direct statement of the claim a
stand map makes, and it shows its working: every village and every band is in the table.

**How to read a value.** The unit is one interquartile range on one measurement. Zero means the
map's claim makes no difference; positive means it goes the way the field does. On generated data
with a strong planted map `pair_stand` was 1.00 for the right map and 0.02 for an unrelated one.
The table also gives the *crude* figure with no bands and no villages, so a reader sees how much
the two controls removed.

**What can make it mislead**

- **It is not from a paper.** It is a stratified difference of means, built for this project. No
  reference is attached to it, to the weighting rule or to the scaling. Among "established
  methods first" it is the one item that is not established.
- **Bands do not fully remove distance.** Inside a band the same-stand pairs are still the closer
  ones. With plots shuffled inside villages, `pair_stand` gave false alarms in 14.3% of generated
  data sets. It is sound only under the rotation null (5.3%).
- **The bands are a choice.** There is no default in the code. They must be written down before
  the run (section 8), or they could be picked to suit a result.
- **Few same-stand pairs.** About 62 on the generated layout. Many villages and bands hold none
  and contribute nothing. The table says how many strata each figure rests on.
- **Missing data.** A plot with a missing measurement, or in no stand, is in no pair.

**Where it is implemented.** `fmu.evaluation.pairs`: `field_distance`, `geographic_distance`,
`PairComparison` (`table`, `effect`, `statistic`), `pair_comparison`. The three claims are
`fmu.evaluation._common.pair_claims`.

**Papers.** None. The descriptive pair comparisons made on Odisha data in chat before this work
are the reason the two controls are on the list. They were not used to choose, tune or rank any
metric.

### 1.3 Mantel test and partial Mantel test

**What it measures.** Make two tables of all pairs of plots. One holds the field distance of each
pair. The other holds what the map says: 0 for "same", 1 for "different". The Mantel statistic is
the correlation between the two tables. The partial Mantel statistic is the same correlation
after the part explained by geographic distance has been taken out of both.

**Why it is on the list.** The brief names them as the established tests for relating one
distance table to another with distance held fixed.

**How to read a value.** A correlation from -1 to 1. Positive: pairs the map calls different are
more different in the field. Values are small even for a good map, because most pairs are
"different" on both tables: with a strong planted map `mantel_stand` was 0.24, and 0.09 for an
unrelated map. That 0.09 is why the value means nothing without its chance test.

**What can make it mislead**

- **With spatial data the standard test is not valid, and holding distance fixed does not cure
  it.** This is the main caution of the whole list. When both tables carry spatial structure the
  tests reject far too often. Reported false-alarm rates at a nominal 5%: 25% to 40% at the
  strongest spatial structure those authors simulated, up to 55% at 200 samples (Guillot and
  Rousset 2013; these figures are from the authors' preprint and were not checked against the
  journal version; the journal abstract adds that strong bias is also expected under a sampling
  design and spatial parameter taken from a real study); up to about 40% for the simple and 30% for the
  partial test (Quilodrán et al. 2023); inflated in both, and the partial test "did not control
  for the spatial autocorrelation effect" (Crabot et al. 2019). Guillot and Rousset conclude the
  tests "should not be used in case autocorrelation is suspected in both variables". Field
  structure and stand membership are both spatial, so that is the case here.
- **Our generated data agree.** With plots shuffled inside villages, false alarms were 91.3% for
  `mantel_stand` and 66.3% for `partial_mantel_stand`. Under the rotation null they were 7.0% and
  6.0%. So the Mantel *statistic* is kept, and the Mantel *permutation test* is not used.
- **When the standard test is safe**: no spatial structure, or structure in only one of the two
  tables (Quilodrán et al. 2023; Guillot and Rousset 2013); a plain linear trend alone can be
  handled by the partial test (Guillot and Rousset 2013).
- **A simulation study argues against this kind of use.** Legendre, Fortin and Borcard (2015)
  call using the Mantel test to control for spatial correlation between two data sets "an
  incorrect use of that test", find its power always lower than an alternative (distance-based
  Moran's eigenvector maps), call its R-squared smaller than the alternative's and
  uninterpretable, and
  show that regressing on geographic distance does not remove spatial structure. Their main
  conclusion is that Mantel tests should be kept for questions that concern distance tables
  only. The question asked here is posed on
  pairs, which is the case those authors leave open, but the spatial-control use is the one they
  reject.
- **How to permute a partial Mantel test.** Legendre (2000) recommends permuting the residuals of
  a null model. The module does not do that: it relabels plots (or moves them) and recomputes the
  partial correlation. Guillot and Rousset found all four permutation variants fail alike under
  spatial structure, so this choice is not what protects the test; the rotation null is.
- **Published remedies were not adopted.** A spatially constrained permutation restored the
  false-alarm rate to about 0.05 but gave 0.115 when its spatial weights were wrong and handles
  only continuous variables (Crabot et al. 2019; the authors of the remedy, so not an independent
  comparison). A stricter significance threshold is suggested as a conservative way to keep using
  the tests: the usual 0.05 divided by eight for the simple test and by six for the partial test
  (Quilodrán et al. 2023). It is a rule of thumb from that paper's simulations, not a test built
  for the data in hand. Shifting one table against the other needs a regular grid (Guillot and Rousset 2013;
  Crabot et al. 2019), which field plots are not.
- **Pairs used.** When villages are given, only pairs inside one village are used. Two plots in
  different villages are always in different stands, so those pairs say nothing about the drawing
  and carry the between-village differences. This is not the textbook all-pairs test
  (question 7).
- **Unequal spread.** The Mantel test is very sensitive to groups that differ in spread
  (Anderson and Walsh 2013).

**Where it is implemented.** `fmu.evaluation.permutation`: `mantel_r`, `partial_mantel_r`,
`claim_dissimilarity`, `mantel_statistic`. Pearson correlation by default; the Spearman (rank)
form is available and was not part of the synthetic validation.

**Papers**

- Mantel 1967, *The detection of disease clustering and a generalized regression approach*,
  Cancer Research 27(2), 209-220. **UNVERIFIED**: Crossref holds no DOI for it and the paper was
  not read. Three papers read in full attribute the test to it.
- Smouse, Long and Sokal 1986, doi:10.2307/2413122, verified. *Used* (source of the partial
  test). Read: title only. That it is the three-table test rests on papers read in full. The
  formula is from secondary description.
- Guillot and Rousset 2013, doi:10.1111/2041-210x.12018, verified. *Used*, as a limit: it argues
  against the use made here unless one table has no spatial structure. Read: journal abstract and
  the full text of the authors' preprint (arXiv 1112.0651, version 2). The quotation above is in
  the journal abstract; the percentages are in the preprint only.
- Legendre 2000, doi:10.1080/00949650008812035, verified. *Recommended* (how to permute a partial
  Mantel test). Read: abstract. It is a simulation comparison of four ways of permuting; the
  abstract does not mention spatial structure.
- Legendre, Fortin and Borcard 2015, doi:10.1111/2041-210x.12425, verified. *Used*, as a limit: a
  simulation study that argues against using the test to control for space. Read: abstract.
- Crabot et al. 2019, doi:10.1111/2041-210x.13141, verified. *Used*: cited here mainly as a
  limit (it finds both tests inflated when both tables are spatially structured), and as the
  source of a spatially constrained permutation that its authors propose in place of both tests.
  That proposal comes from the method's own authors, so it is not counted as a recommendation by
  a review or as an independent comparison. Read: abstract and full text (the copy on the HAL
  open archive).
- Quilodrán, Currat and Montoya-Burgos 2023, doi:10.1111/1755-0998.13898, verified. *Used*: a
  benchmark of the existing tests that sets the condition under which they are safe. Read: abstract and full text.
- Chaves et al. 2020, doi:10.1111/jvs.12938, verified. *Used*: a study that relates a
  map-derived difference to a field difference with Mantel tests (Landsat reflectance against
  floristic turnover among forest inventory sites), and tests mapped forest classes with ANOSIM.
  Read: abstract.

### 1.4 ANOSIM (analysis of similarities)

**What it measures.** Rank all the field distances between plots of a village from smallest to
largest. ANOSIM's R compares the average rank of pairs in the same stand (or of the same type)
with the average rank of pairs that are not. It uses only the order of the distances, not their
size.

**Why it is on the list.** The brief names it. It needs no assumption about the shape of the
data, and it has a published form for working inside blocks, here villages.

**How to read a value.** R runs from -1 to 1. It is 1 when every same-stand pair is closer than
every other pair, and near 0 when stands make no difference. But "near 0" is again the textbook
chance level: on generated data an unrelated map scored 0.33 on `anosim_stand`, against 0.88 for
the planted map.

**What can make it mislead**

- **It cannot see needless boundaries.** A map with every stand cut in two scored the same as the
  planted map (0.884 against 0.875). Each half is as pure as the whole, so R loses nothing. It
  cannot be used to choose between stand sizes.
- **Plots must be exchangeable for the textbook test, and nearby plots are not.** Somerfield,
  Clarke and Gorley (2021) call the test that shuffles labels inside the strata "always an
  'exact' test". What any such test assumes is stated by Anderson (2001) for the related
  method: that the observations can be exchanged when there is no difference, which in general
  means they are independent. Plots near each other are alike, so they cannot be exchanged. Measured: 90.3% false alarms for `anosim_stand` under the
  within-village shuffle.
- **Under the rotation null `anosim_stand` was the one statistic flagged**: 8.3% false alarms,
  with a 95% interval of 5.7% to 12.0%. A sound test is flagged by this rule in 2.9% of runs, so
  about 0.4 flags are expected among the rotation null's twelve cells and about 1.4 in the whole
  table of 48. One flag is not surprising, and that run could not say whether the excess was
  real. The follow-up check on 600 fresh data sets gave `anosim_stand` 4.2% (interval 2.8% to
  6.1%), so the excess looks like chance (section 4).
- **It can reject because groups differ in spread, not in level** (Somerfield, Clarke and Gorley
  2021). ANOSIM was the most sensitive of three methods to unequal spread; with groups of unequal
  size none of the three "behaved reliably" (Anderson and Walsh 2013). Stands and types hold very
  unequal numbers of plots.
- **A departure from the published form.** In the published two-way layout R is worked out in
  each block and the plain average taken (Somerfield, Clarke and Gorley 2021, p. 912). The module
  by default weights each village by its pair counts, because villages here hold from a handful
  of plots to about 50 and a village with one same-stand pair would otherwise count as much as
  one with hundreds. The plain average is available (`stratum_weights="equal"`) and the run
  script prints both. The plain average was not part of the synthetic validation (question 6).
- **Restricting the shuffle to villages can cost a good deal of power** (Anderson and ter Braak
  2003), so "not significant" inside villages is weak evidence of no effect.

**Where it is implemented.** `fmu.evaluation.permutation`: `anosim`, `anosim_statistic`.

**Papers**

- Clarke 1993, doi:10.1111/j.1442-9993.1993.tb00438.x, verified. *Used* (the standard citation).
  Read: abstract, which describes rank-based tests for differences among groups of samples and
  does not use the name ANOSIM. That it is the citation rests on Anderson 2001 and Somerfield et
  al. 2021, both read in full. The formula is from secondary description (Somerfield et al.
  2021, p. 912).
- Somerfield, Clarke and Gorley 2021, doi:10.1111/aec.13059, verified. *Used*: states the
  statistic, how to test it within strata, and how it differs from PERMANOVA. Read: full text.
  Written by the authors of ANOSIM, so a source and not an independent comparison.
- Chaves et al. 2020 (above): a use of ANOSIM on two mapped forest classes against inventory
  plots.

### 1.5 PERMANOVA

**What it measures.** An analysis of variance worked out from the field distances. It splits the
spread among the plots of a village into a part between stands (or types) and a part inside
them. The statistic is the pseudo-F: the between part over the within part, each divided by its
degrees of freedom. An R-squared (share of spread between stands) is returned with it.

**Why it is on the list.** The brief names it. It uses the sizes of the distances, where ANOSIM
uses only their order, so the two are complementary.

**How to read a value.** F near 1 means stands explain nothing; larger is better. On generated
data: 7.2 for the planted map, 1.6 for an unrelated one.

**What can make it mislead**

- **It cannot see needless boundaries either.** The map with every stand cut in two scored the
  same as the planted map (7.18 against 7.18).
- **Exchangeability.** The paper's only assumption is that observations can be exchanged under
  "no difference", which in general means independent and with similar spread; and the units
  shuffled must be the ones that can be exchanged (Anderson 2001; Anderson and ter Braak 2003).
  Nearby plots are not independent. Measured: 93.0% false alarms for `permanova_stand` under the
  within-village shuffle; 6.7% under the rotation null.
- **Unequal group sizes.** PERMANOVA was largely unaffected by unequal spread only for balanced
  designs; with unbalanced groups all three methods were too liberal when the smaller group was
  the more spread out and too conservative in the opposite case (Anderson and Walsh 2013). Our
  stands are as unbalanced as a design can be. Anderson 2001 itself treats balanced designs only.
- **`permanova_type` under the rotation null was cautious**: 3.0% false alarms where 5% is
  correct. That costs a little power, not honesty.

**Where it is implemented.** `fmu.evaluation.permutation`: `permanova`, `permanova_statistic`.
Checked against the ordinary one-way analysis of variance (`scipy.stats.f_oneway`) in the tests.

**Papers**

- Anderson 2001, doi:10.1111/j.1442-9993.2001.01070.pp.x, verified. *Used* (source; the paper
  calls the method non-parametric MANOVA). Read: abstract and full text.
- Anderson and Walsh 2013, doi:10.1890/12-2010.1, verified. *Shown better*: PERMANOVA over ANOSIM
  and the Mantel test, **for balanced designs only**. Read: abstract.
- Anderson and ter Braak 2003, doi:10.1080/00949650215733, verified. *Recommended* (how to build
  a permutation test with blocks and nesting). Read: abstract.
- Somerfield, Clarke and Gorley 2021 (above), for the contrast with ANOSIM.

### 1.6 The significance test: null models, with the rotation null last

**This section is about tests, not metrics.** A null model here produces relabelled plots and
nothing else. A number only appears when one of the named statistics above is computed on them.
The code is built so that there is no such thing as a "rotation score".

**The p-value.** Compute the statistic on the real map and on each of R simulated relabellings.
If b of them score at least as well as the real map, p = (b + 1) / (R + 1). The real map counts
as one of the relabellings, so p is never 0. If a statistic cannot be computed in more than 10%
of the relabellings, no p-value is given.

**Four ways of simulating chance are in the code.**

| Null model | What it does | What it keeps | False alarms on generated data (5% is correct) |
|---|---|---|---|
| Free permutation | shuffles the map's labels over all plots | nothing | 0% to 99%; not usable |
| Permutation inside villages | shuffles them inside each village | village differences | 5.7% to 93%; sound for 2 of 12 statistics |
| Torus translation | slides a gridded map under the plots, wrapping round at the edges | the plot layout and the map's shapes, except at the seam | 4.0% to 11.0%; too high for 2 of 12 |
| **Rotation null** | moves each village's plots as one rigid shape to a random place and angle inside the village forest | the plot layout, the map, the field values | 3.0% to 8.3%; too high for 1 of 12. Follow-up on 600 fresh data sets: 4.2% to 6.7%, none too high |

**Why the rotation null is the default.** Two plots in the same stand are close together, and
close plots are alike whatever the map says. A shuffle breaks that link, so the real map looks
better than chance even when it is not. The rotation null keeps the plots' spacing and the
stands' shapes and breaks only where the layout sits on the map. Section 4 has the measured
rates.

**What can make it mislead**

- **No paper validates this exact procedure.** Its nearest published relatives are the torus
  translation (Harms et al. 2001; that it also uses 180-degree rotation and mirroring is
  UNVERIFIED, see the paper's entry below), a random shift null
  with rotation and reflection (Deblauwe et al. 2012) and random rotation of brain maps on a
  sphere (Alexander-Bloch et al. 2018). None is the same as rotating scattered field plots over a
  stand map. **Only this project's own check on generated data stands behind it.**
- **That check covers one generated world.** Field data smooth over about 200 m, stands of about
  2.6 hectares, a generous village forest with no holes. Shift-type nulls are known to reject too
  often when spatial structure is strong and long-ranged (Deblauwe et al. 2012, on gridded data);
  a later benchmark of ten published spatial nulls for brain maps found that nulls which ignore
  spatial structure give too many false positives, and that spatially constrained nulls are
  more conservative but still "suffer from inflated false positive rates" in some analyses
  (Markello and Misic 2021). Longer ranges were not tried here.
- **Its false-alarm rate, measured twice.** Main run, 300 data sets: 3.0% to 8.3%, average
  5.9%, one statistic flagged. Follow-up declared before it was run, 600 fresh data sets: 4.2% to
  6.7%, average 5.1%, none flagged (`docs/evaluation/rotation_size_followup.md`). In this
  generated world the rate is close to 5%.
- **It is not exact in theory.** A shuffle is exact because every reordering is as likely as the
  real order. Here the placements the plots may be moved to are crowded round the real one (they
  must stay inside the village forest), so the real placement is not just one more draw. When
  the forest leaves room, as in the generated data, this did not show. When it leaves little
  room it could, in either tail, and that was not measured: with the forest only 50 m wider than
  the plots, the null could not be drawn at all (next point).
- **A thin or holed village forest** leaves few places to move the plots to. The code then stops
  and says the null cannot be drawn; it does not drop the village or relax the rule. This
  happened in 200 of 200 generated data sets when the forest was made only 50 m wider than the
  hull of the plots: a village of 49 plots found about one allowed placement in 70,000 tries. How
  the null behaves when placements are few but not zero was not tested.
- **Plots that are in no stand** at their real position stay in no stand in every relabelling, so
  that the real map and the relabellings are scored on the same plots. This goes slightly beyond
  the rule as first written (question 10).
- **Torus translation** was built for complete maps on a regular grid (Harms et al. 2001). The
  wrap joins opposite edges of the map, a seam that does not exist on the ground. Periodic
  boundaries are called "highly unrealistic for geographical observations" (Deblauwe et al.
  2012). The module's version uses translations only, as Kyle Harms's own script of 2011 does;
  whether the 2001 paper also used mirror images and half-turns is UNVERIFIED (the paper's entry
  below). It is offered for comparison with the published method. The rotation null is the
  default.
- **Permutation inside villages** is the published way to test inside strata (Somerfield,
  Clarke and Gorley 2021). It is exact only when plots inside a village can be swapped freely
  (the exchangeability assumption, Anderson 2001). They cannot when nearby plots are alike. Whether it
  should remain as a fallback when only a plot table exists is question 3.

**Several tests at once.** When several tests are reported together their p-values are corrected
with Holm's step-down method (`holm_adjust`): the smallest is multiplied by the number of tests,
the next by one fewer, and so on. No Crossref record was found for Holm's 1979 paper, so the
citation is **UNVERIFIED**; the method is standard and is described here without a reference. It
is a correction, not a metric.

**Where it is implemented.** `fmu.evaluation.spatial_null`: `rotation_null`,
`torus_translation_null`, `RasterStandMap`, `PolygonStandMap`. `fmu.evaluation.permutation`:
`free_permutation`, `within_group_permutation`, `run_test`, `run_tests`, `holm_adjust`.

**Papers**

- Harms et al. 2001, doi:10.1111/j.1365-2745.2001.00615.x, verified. *Used* (source of the torus
  translation, the closest published relative). Read: abstract and full text. In that paper the
  test gave 171 significant species-habitat associations against 317 from tests that treat stems
  as independent, and the authors call their methods more conservative. It was built for fully
  mapped plots, not scattered sample plots.
  *Note added 20 Oct 2026 (round 13, review C5).* Crossref, checked again on 20 Oct 2026, gives
  the title "Habitat associations of trees and shrubs in a 50-ha neotropical forest plot", first
  author Kyle E. Harms (with Condit, Hubbell and Foster), *Journal of Ecology* 89(6), 947-959,
  issued December 2001; every record in the repo cites it so. The records disagree on what was
  read. This entry (13 Oct 2026) says the full text was read, and this section stated the
  rotations and mirror images as the paper's in two places, marked UNVERIFIED since 20 Oct.
  `src/fmu/evaluation/spatial_null.py` said the opposite, that the paper's test slides the map
  without turning it. `src/fmu/evaluation/torus_shift.py`
  and `docs/handoff/2026-10-17-round9-chat.md` (17 Oct 2026) say the full text was not read there;
  they take the procedure from Kyle Harms's own R script of 2011, which translates the map only,
  and leave open whether the 2001 paper also turned and mirrored it (that handoff's question 11,
  waiting for the PDF). The full text could not be read on 20 Oct 2026 either: the publisher's
  page refused the request. Until it is read, that the paper uses rotations and mirror images is
  UNVERIFIED, and so is the 171 against 317, which was not checked again after 13 Oct.
- Deblauwe, Kennel and Couteron 2012, doi:10.1371/journal.pone.0048766, verified. *Used*, as a
  limit of shift-type nulls. Read: full text. The authors propose a rival method (wavelet-based
  surrogates, for gridded data), so their comparison is not an independent one. Fully random reassignment gave false association
  over 36% of the time at a nominal 5% under fairly low spatial structure. The paper does not
  assess power.
- Alexander-Bloch et al. 2018, doi:10.1016/j.neuroimage.2018.05.070, verified. *Used*: a
  published random-rotation null for testing correspondence between two maps. Read: abstract.
  Neuroimaging, on a sphere: the authors introduce the null (random rotations of one map of the
  brain surface) and apply it. It shows that a rotation null of this kind has been published
  and used, and no more than that.
- Markello and Misic 2021, doi:10.1016/j.neuroimage.2021.118052, verified. *Used*, as a limit:
  a benchmark of ten published spatial nulls for brain maps, on simulations with a known answer
  and on two real data sets. Read: abstract. It did not test this project's rotation null.

---

## 2. Sites with reference polygons

For a site with a compartment map or other trusted polygons. Both measures compare shapes; no
field measurement is involved, and there is no chance test. On generated data **a map with
nothing to do with the reference still scored D 0.49 and boundary F 0.52**, because with small
compact stands much of any boundary lies near some reference boundary. Those, not 1 and 0, are
the values of a useless map of that grain. A baseline of this kind should be worked out and shown
beside any real score.

### 2.1 Over-segmentation, under-segmentation and D

**What it measures.** For a reference polygon and a stand that overlap:

- **over-segmentation** = the share of the reference polygon this stand does *not* cover. High
  when the reference is cut into several stands.
- **under-segmentation** = the share of the stand that lies *outside* the reference. High when a
  stand runs across the reference boundary.
- **D** = the two combined: the square root of half the sum of their squares.

All three are 0 for a perfect match and stay below 1. They are averaged over the matched pairs,
per reference polygon, and weighted by area; all three summaries are returned.

**Why it is on the list.** The brief asks for standard segmentation-accuracy measures. These two
separate the two ways a delineation goes wrong, which one number cannot.

**How to read a value.** Lower is better. On generated data: the planted map 0, 0, 0; stands cut
in two, over 0.47 and under 0; stands merged four at a time, over 0 and under 0.68; an unrelated
map 0.46, 0.46 and D 0.49.

**What can make it mislead**

- **The formulas are from secondary description and are UNVERIFIED against the 2010 paper.** The
  journal paper usually cited (Clinton et al. 2010) was read by abstract only. Two open texts
  were read and they disagree: the authors' 2008 conference paper (no DOI, so not citable as
  verified) matches a stand to a reference by four rules and gives D without the division by two;
  Sanchez-Lopez et al. 2018 use only the two half-overlap rules, divide by two, and set over =
  under = 1 for a reference no stand matches. The module uses the four rules and divides by two,
  so D runs from 0 to 1. The two forms of D differ by a constant factor, so they rank maps the
  same (question 11).
- **Missed reference polygons.** A reference polygon no stand matches gets over = 1 and no value
  for under and D, so it drops out of those averages. A map that misses many reference polygons
  looks no worse on D unless the count of unmatched polygons is read with it. The count is
  always returned and must always be shown.
- **The measures disagree with each other.** They "have divergent performance" in which
  segmentation they pick (Clinton et al. 2010), so one measure alone should not rank maps.
- **Slivers.** A minimum-overlap rule exists to drop digitising slivers. Its default is 0 (off);
  any other value must be declared, not tuned.
- **A reference map is not truth.** Compartment boundaries follow management as well as forest.

**Where it is implemented.** `fmu.evaluation.segmentation_accuracy.segmentation_accuracy`.

**Papers**

- Clinton et al. 2010, doi:10.14358/pers.76.3.289, verified. *Used* (the source that
  Sanchez-Lopez et al. 2018 cite for the three measures). Read: abstract only, which says the
  paper reviews and compares area-based and location-based measures and does not name these
  three. Formulas from secondary description, as above.
- Sanchez-Lopez, Boschetti and Hudak 2018, doi:10.3390/rs10101622, verified. *Used*: a forest
  stand delineation from LiDAR over more than 54,000 hectares, evaluated without reference data
  by a Global Score and then against reference harvest polygons by over-segmentation,
  under-segmentation and D. Read: full text.
- Costa, Foody and Boyd 2018, doi:10.1016/j.rse.2017.11.024, verified. *Used*: a review of
  segmentation accuracy assessment in land cover mapping. Among papers in three remote sensing
  journals in 2014 and 2015 it found methods that use reference data the most frequently used
  approach, with judging by eye also widely used. Read: abstract, which does not say which
  measures it recommends, so no such claim is made here.

### 2.2 Boundary match

**What it measures.** Draw all stand boundaries and all reference boundaries.

- **precision** = the share of stand boundary length that lies within a set distance of a
  reference boundary: how much of what the map draws is also in the reference.
- **recall** = the share of reference boundary length within that distance of a stand boundary:
  how much of the reference the map found.
- **F** = their harmonic mean.

**Why it is on the list.** The brief asks for a boundary match. It answers a forester's question
directly: are the lines in the right place?

**How to read a value.** 1 is a perfect match. On generated data, with a tolerance of one 20 m
pixel: stands cut in two, precision 0.74 and recall 1.00; stands merged, precision 1.00 and
recall 0.59; an unrelated map 0.52 on all three.

**What can make it mislead**

- **It is our adaptation.** Martin, Fowlkes and Malik (2004) define the measures for image
  pixels and match detected to reference boundary pixels one to one. The module uses buffers on
  vector lines and has **no one-to-one matching**, so two stand lines running side by side within
  the tolerance of one reference line both count as matched. Those authors match one to one for
  exactly this reason. Precision and recall must be read together, never recall alone.
- **The tolerance decides the score.** It has no default. It must be fixed in advance, in
  metres, for example at the positional accuracy of the reference map.
- **The outer edge** of the study area is shared by both maps and matches trivially. It can be
  left out (`ignore`), and that choice must be declared too.
- **No remote-sensing validation of the measure was verified.** The source is a computer-vision
  paper on photographs.
- **Cost.** About 0.6 seconds of processor time for a village of about 65 stands; a whole
  district may take minutes.

**Where it is implemented.** `fmu.evaluation.segmentation_accuracy.boundary_match`.

**Papers**

- Martin, Fowlkes and Malik 2004, doi:10.1109/tpami.2004.1273918, verified. *Used* (source of
  boundary precision, recall and F with a distance tolerance). Read: full text.

---

## 3. Sites with no reference data

Here the only question that can be asked is whether stands are alike inside and different from
each other, **on layers the pipeline did not use to draw them**. On a layer the pipeline did use,
these measures mostly show that the segmentation ran.

### 3.1 Explained variance

**What it measures.** For one layer, the share of its variation over all pixels that lies between
stands: 1 minus (variation inside stands over total variation).

**Why it is on the list.** It is already reported by the pipeline's metrics stage, and it is the
simplest statement of "stands are alike inside".

**How to read a value.** 0: stands explain nothing. 1: every stand is perfectly uniform. On
generated data, on a layer that followed the planted map: 0.50 for the planted map, 0.23 for an
unrelated one.

**What can make it mislead**

- **It rises as stands get smaller, whatever the layer.** One stand per pixel scores 1. On
  generated data the map with every stand cut in two scored *higher* than the planted map (0.505
  against 0.495). It can never be read without the number of stands, which is returned in the
  same row, and it can only compare maps of similar stand size. (This is arithmetic, not a
  finding from a paper.)
- **The layer must be independent of the pipeline.** The verified forest example computes it
  partly on variables used to draw the stands (Xiong et al. 2024). Which layers count as "not
  used" has to be named before the run (section 8).
- **An unrelated map does not score 0** (0.23 above): any compact stands capture some local
  smoothness.

**Where it is implemented.** `fmu.utils.components.explained_variance_r2`, reported by
`fmu.stages.metrics` (Earth Engine). The same definition on arrays, for offline use:
`fmu.evaluation.unsupervised.explained_variance`.

**Papers**

- Xiong et al. 2024, doi:10.14214/sf.23014, verified with a caveat. *Used*: a forest stand
  delineation evaluated by explained variance (equations 4 to 6 of that paper) and by overlap
  with reference stands. Read: full text. Caveat: Crossref lists an affiliation string as the
  first author of this record; the first *person* listed is Xiong and the title matches exactly.
  Read strictly, the rule "first author must match" would mark it UNVERIFIED (question 13).

### 3.2 Global Score

**What it measures.** Two things added together, for a *set* of candidate maps of the same area:

- **area-weighted variance**: the average variance of the layer inside a stand, larger stands
  counting more. Low when stands are alike inside.
- **Moran's I between neighbouring stands**: whether stands that touch have similar averages.
  Low (or negative) when neighbours differ, which is what a good map does. High when neighbours
  are alike, the mark of needless boundaries.

Each is rescaled from 0 (best candidate) to 1 (worst) across the candidates and the two are
added. Lower is better; the range is 0 to 2.

**Why it is on the list.** The brief names it. It is the natural partner of explained variance:
variance alone always prefers smaller stands, and Moran's I pulls the other way.

**How to read a value.** Only as a ranking inside one declared set of candidates. On generated
data the planted map scored best (0.17), then the map cut in two (0.66), merged (1.12), unrelated
(1.48) and shifted (1.89). Moran's I is what caught the needless boundaries: 0.155 for the cut map against -0.024 for
the planted one.

**What can make it mislead**

- **The score depends on which other maps were tried.** Because both parts are rescaled by their
  smallest and largest values over the candidates, changing the set changes the values, moves the
  optimum and can reverse the order of two maps (Böck, Immitzer and Atzberger 2017). That paper
  proposes rescaling to fixed limits instead. **The module implements the original form only.**
  The fixed-limit form is not implemented (question 12). Until it is: declare the candidate set
  in advance, always show the two raw parts beside the score, and never compare scores across
  sites.
- **It has no meaning for one map.** With one candidate the code returns the two raw parts and no
  score.
- **Sources.** The paper that named the score was read by title only (Johnson and Xie 2011) and
  the paper it builds on by abstract (Espindola et al. 2006). The formula is the one given by
  Böck et al. 2017 (their equations 1, 2, 4 and 5), so it is from secondary description. Whether
  Johnson and Xie rescale each band and then average, as the module does, or average the bands
  first, is UNVERIFIED.
- **The layer must be independent of the pipeline**, as for explained variance.

**Where it is implemented.** `fmu.evaluation.unsupervised`: `weighted_variance`,
`segment_adjacency`, `morans_i`, `segment_morans_i`, `global_score`.

**Papers**

- Johnson and Xie 2011, doi:10.1016/j.isprsjprs.2011.02.006, verified. *Used* (source of the
  name). Read: title and record only. That the name is theirs rests on Sanchez-Lopez et al.
  2018, read in full; Böck et al. 2017, read in full, credit the method itself to Espindola et
  al. 2006 and one form of the rescaling to Johnson and Xie.
- Espindola et al. 2006, doi:10.1080/01431160600617194, verified. *Used* (origin of the idea: a
  variance indicator combined with a spatial autocorrelation indicator to choose segmentation
  parameters). Read: abstract.
- Böck, Immitzer and Atzberger 2017, doi:10.3390/rs9080769, verified. *Used*, for the limit
  above and for the formulas. Read: full text.
- Sanchez-Lopez, Boschetti and Hudak 2018 (above): a forest stand delineation ranked by a Global
  Score with fixed-limit rescaling.

---

## 4. What the check on generated data showed

Before any real data are touched, the metrics were run on data made by a random generator, where
the right answer is known because it was planted. The layout copies only the *numbers* of the
Odisha plots: 267 plots in 20 villages in 4 districts, unevenly filled. Nearby plots were made
alike and villages were made to differ, as on a real site. Full tables, the generator and the
exact command are in `docs/evaluation/synthetic_validation.md` (and `.csv`); the script is
`scripts/evaluation_synthetic_validation.py`. The run reproduced byte for byte when repeated.

### False alarms: the map knows nothing, how often does each test say it does?

Share of 300 generated data sets with p at or below 0.05. A sound test gives 0.05. **Monte Carlo
error**: a true rate of 0.05 measured on 300 data sets has a standard error of 0.013. A cell is
starred when its whole 95% interval lies above 0.05.

| Statistic | Free permutation | Permutation inside villages | Rotation null | Torus translation |
|---|---|---|---|---|
| `ari_drawing` | 0.990* | 0.343* | 0.063 | 0.110* |
| `ari_labelling` | 0.163* | 0.073 | 0.057 | 0.067 |
| `pair_stand` | 0.000 | 0.143* | 0.053 | 0.040 |
| `pair_type` | 0.067 | 0.057 | 0.060 | 0.053 |
| `mantel_stand` | 0.953* | 0.913* | 0.070 | 0.083* |
| `mantel_type` | 0.267* | 0.180* | 0.053 | 0.070 |
| `partial_mantel_stand` | 0.650* | 0.663* | 0.060 | 0.073 |
| `partial_mantel_type` | 0.170* | 0.137* | 0.063 | 0.063 |
| `anosim_stand` | 0.000 | 0.903* | 0.083* | 0.057 |
| `anosim_type` | 0.170* | 0.187* | 0.053 | 0.057 |
| `permanova_stand` | 0.007 | 0.930* | 0.067 | 0.050 |
| `permanova_type` | 0.300* | 0.280* | 0.030 | 0.047 |
| Average of the twelve | 0.311 | 0.401 | 0.059 | 0.064 |
| Starred | 8 of 12 | 10 of 12 | 1 of 12 | 2 of 12 |

Plainly:

- **Only the rotation null holds.** Its rates run from 0.030 to 0.083.
- **It is not perfect.** Eleven of its twelve rates are above 0.05 and the average is 0.059. The
  twelve statistics were computed on the same data sets, so they rise and fall together and this
  is weaker evidence than twelve separate results; but it leans one way. `anosim_stand` (0.083)
  is flagged.
- **A follow-up settled most of that.** It was declared before it was run: 600 fresh data sets,
  the rotation null only, its own seed, not pooled with the table above. Rates ran from 0.042 to
  0.067, average 0.051, none flagged; `anosim_stand` gave 0.042. Standard error 0.009. So the
  excess in the table above looks like chance. The file is
  `docs/evaluation/rotation_size_followup.md`.
- **Twelve tests side by side need a correction.** In the follow-up, 27% of data sets had at
  least one of the twelve statistics at p <= 0.05 although the map knew nothing. Holm's
  correction (section 1.6) is for this.
- **Shuffling inside villages is not sound for anything that touches stands.** 0.90 to 0.93 for
  `mantel_stand`, `anosim_stand` and `permanova_stand`. Only `pair_type` (0.057) and
  `ari_labelling` (0.073) hold.
- **Holding distance fixed did not rescue the shuffle**: 0.663 for the partial Mantel statistic
  and 0.143 for the pair comparison in distance bands.
- **Free permutation is unusable in both directions**: 0.99 for `ari_drawing`, 0.00 for the
  within-village stand statistics.

### Power: the map does know something, how often is it detected?

Share of 80 generated data sets with p at or below 0.05 **under the rotation null**. The effect is
given as the share of the variance of each field measurement that the planted map accounts for.
That share counts the differences between villages. Inside a village, where the pair comparison,
Mantel, ANOSIM and PERMANOVA statistics work, the map's share is larger: 6%, 20%, 50% and 80%.
**Monte Carlo error**: the standard error of a cell is at most 0.056, so two cells closer than
about 0.16 cannot be told apart.

| Statistic | Map accounts for 4% | 14% | 40% | 73% |
|---|---|---|---|---|
| `ari_drawing` | 0.07 | 0.23 | 0.79 | 1.00 |
| `ari_labelling` | 0.16 | 0.66 | 1.00 | 1.00 |
| `pair_stand` | 0.14 | 0.62 | 1.00 | 1.00 |
| `pair_type` | 0.16 | 0.72 | 1.00 | 1.00 |
| `mantel_stand` | 0.15 | 0.74 | 1.00 | 1.00 |
| `mantel_type` | 0.20 | 0.82 | 1.00 | 1.00 |
| `partial_mantel_stand` | 0.14 | 0.75 | 1.00 | 1.00 |
| `partial_mantel_type` | 0.20 | 0.82 | 1.00 | 1.00 |
| `anosim_stand` (false-alarm rate flagged; not read) | (0.11) | (0.64) | (1.00) | (1.00) |
| `anosim_type` | 0.20 | 0.76 | 1.00 | 1.00 |
| `permanova_stand` | 0.14 | 0.79 | 1.00 | 1.00 |
| `permanova_type` | 0.23 | 0.85 | 1.00 | 1.00 |

Plainly:

- **A weak map would be missed.** If the map accounts for 4% of the variance, no statistic
  detects it more than about one time in four. At 14%, three of the eleven readable statistics
  reach the usual target of 0.8. At 40%, ten of eleven do.
- **The drawing index is the weakest**: 0.79 at 40%, where the other ten reach 1.00.
- **The differences among the other statistics are mostly inside the error.** This table does
  not show that one of them is better than another, and it must not be used to pick one.
- So a "cannot be told from chance" result on a layout like this says the map does not account
  for a large share of the field variation. It does not say the map is useless.
- The 267 plots fell in 213 stands on average; only 47 stands held two or more plots. Everything
  a stand statistic knows comes from about 62 pairs.

### Recovery: does each statistic prefer the right map?

With a strong planted map (73% of variance), each statistic was computed on the planted map and
on four others: boundaries shifted by half a stand, stands merged four at a time, every stand cut
in two, and an unrelated map of the same grain. Ten data sets.

- All twelve statistics scored the planted map above the shifted and the unrelated map in 10 of
  10 data sets, and every test rejected "no agreement" for the planted map in 10 of 10.
- **`ari_drawing` scored the merged map above the planted one in 10 of 10** (section 1.1).
- **`anosim_stand` and `permanova_stand` did not separate the planted map from the cut one** (4
  and 5 of 10; sections 1.4 and 1.5). `pair_stand` and the Mantel statistics did, in 10 of 10.
- The type statistics do not, and should not, tell the planted map from the cut one: cutting a
  stand leaves every plot's type as it was.
- Reference polygons and no reference data: figures are quoted in sections 2 and 3. All declared
  expectations for those were met.

### How far this check can be trusted

- **One generated world.** One stand size, one smoothness, one mix of village, smooth and noise
  variation. Sensitivity to these was not run.
- **The village forest was generous**: the hull of the plots widened by 300 m, with a stand under
  every pixel. Real village forests can be thin or holed.
- **99 relabellings** per test. That puts 0.05 exactly on a possible p-value, so no rate is off
  because of rounding; it is fewer than a real run would use.
- **A fault in the generator was corrected before the pilot and the full run.** In the first
  draft the "unrelated" map shared its grid of stand centres with the planted map, so it was not
  unrelated. A trial of 2 to 6 data sets had been seen before the change and is used nowhere.
  Nothing was changed after the pilot or the full run.
- **The explanations of why** (in the validation file) were written after seeing the results.
  The rules that mark a cell (too high, recovered, power of 0.8) were fixed before.
- **Not covered**: Holm's correction, the rank form of the Mantel statistics, ANOSIM with equal
  village weights, the all-pairs Mantel test, polygon stand maps under the rotation null (rasters
  were used), plots outside any stand, missing measurements. These have unit tests with known
  answers but were not part of this study.
- **A pixel-level note for other comparisons.** Two unrelated maps of compact stands of the same
  size score about 0.44 on the adjusted Rand index pixel against pixel, not 0. Anyone comparing
  two stand maps that way needs that baseline.

---

## 5. The open design question: stand types across districts

**Stand types are fitted separately in each district. So "type 3" in one district and "type 3" in
another are different forests.**

What the module does about it: every type comparison is made inside one district. The labelling
index is worked out per district and pooled; a pair of plots from two districts is marked "type
unknown" and used in no type statistic. The generated data were built the same way (type means
drawn separately per district), and the labelling statistics worked under it.

What it costs: types cannot be compared across districts at all; a district with few plots gives
a labelling result of its own that rests on very little; and the pooled figure is dominated by
the district with most plots.

The alternative is to fit one typology for all districts, so a type means the same forest
everywhere.

| | Per district (now) | One typology for all |
|---|---|---|
| For | types fit each district's forests more closely | a type means one thing; all plots can be compared; one labelling result |
| Against | no comparison across districts; small districts give weak results | types fit each district less well; between-district differences may dominate the typology |

This is a decision about the pipeline, not about the evaluation, and it is **not decided here**.
It must not be decided by which option scores better on any site.

---

## 6. Questions for the supervisor

Each says what was done, the options, and a recommendation. None has been decided.

1. **Is the list right?** Anything to strike or add? In particular the pair comparison (1.2) is
   our own construction, not an established method.
2. **Should the drawing index (`ari_drawing`) stay a headline?** It rewards larger stands, its
   ceiling on a layout like Odisha's is about 0.014, and it is the weakest test. *Keep*: it is
   the method asked for, and the note shows what it can and cannot do. *Demote*: report it but
   make another statistic the primary one. Recommendation: keep it on the list, always printed
   with its ceiling and pair counts, never used to compare stand sizes; choose the primary
   statistic separately (section 8).
3. **When a site has only a plot table (no stand map), should any test be offered?** Only the
   within-village shuffle is possible then, and it failed for ten of twelve statistics. *Offer it
   with a warning*: simple, but a "significant" stand result means nothing. *Offer it only for
   `pair_type` and `ari_labelling`*: matches what was measured, in one generated world.
   Recommendation: the second. The run script currently allows it for all and writes a caution
   into the results.
4. **The rotation null's false-alarm rate: is the follow-up enough?** The main run measured
   5.9% on average with `anosim_stand` at 8.3%. The statistical review ran a follow-up that was
   declared first (600 fresh data sets, its own seed, reported on its own): 5.1% on average,
   `anosim_stand` 4.2%, nothing flagged. *Accept*: in this generated world the rate is close to
   5%. *Ask for more*: other generated worlds (smoother field data, thinner village forests,
   other stand sizes), which were not tried; a first try with a forest only 50 m wider than the
   plots could not draw the null at all. Recommendation: accept for this layout, and decide
   whether a thin-forest check is wanted before real data are used.
5. **Distance bands.** None is set in the code. *Fixed edges declared in advance*: simple and
   comparable across sites, but arbitrary. *Bands from the quantiles of plot spacing inside
   villages*: adapts to the site using plot positions only, but the number of bands is still a
   choice. Recommendation: fixed edges, written down first.
6. **ANOSIM across villages**: pair-count weights (the module's default; steadier with villages
   of very different size, but our departure) or the plain average (the published form)?
   Recommendation: declare one as primary and report both.
7. **Mantel pairs**: inside villages only (the default when villages are given; follows the
   brief) or all pairs (the textbook test, dominated by cross-village pairs)? Recommendation:
   inside villages.
8. **Pooling the labelling index over districts**: by pair counts (done; one coherent index, no
   district skipped) or the plot-weighted mean Phase 3 used (continuity, but it skips districts
   with one field type)? The two give different numbers. Recommendation: pair counts, with the
   per-district table.
9. **Phase 3's "only stands with two or more plots" drawing index** is not in the module, because
   it is not on the brief's list. The pair table and the ceiling show the same thing. Add it for
   continuity, or leave it out? Recommendation: leave it out unless wanted.
10. **Plots in no stand, under the rotation null**: they stay in no stand in every relabelling
    (done; real and simulated maps are scored on the same plots), or they may land on a stand
    (the rule as first written; simulated maps are then scored on more plots)? Recommendation:
    as done.
11. **Over- and under-segmentation**: the matching rule and the form of D follow secondary
    descriptions that disagree (2.1), and a missed reference polygon is left out of D rather than
    scored 1. Recommendation: someone reads Clinton et al. 2010 before the note cites it for a
    formula; keep the current treatment of missed polygons and always print their count.
12. **Global Score**: the module has the original rescaling, which depends on the set of maps
    tried. Add the fixed-limit form of Böck et al. 2017 before any use on real data?
    Recommendation: yes. It is a small addition, and it is the only form that gives a score for a
    single map.
13. **Three citations are not clean.** Mantel 1967 and Holm 1979 have no Crossref record
    (UNVERIFIED). Xiong et al. 2024 is verified only if an affiliation string in Crossref's
    author list is overlooked. Accept, or find other sources?
14. **ANOSIM and PERMANOVA cannot see needless boundaries.** Keep them for the question "are
    stands purer than chance", and use `pair_stand` or the Mantel statistic when stand sizes are
    compared? Recommendation: yes, and say so wherever they are reported.
15. **The 20-village layout of the generated data** assumes three small villages of the largest
    district (7, 5 and 2 plots) form one forest of 14. If the true 20 sizes are known, the study
    can be re-run with them (about 25 minutes of computing).
16. **Which layers count as "not used by the pipeline"** for section 3? They must be named.

---

## 7. What has not been done

- **Nothing was run on Odisha or Sanjay Van data.** No field measurement, stand id, stand type or
  stand polygon of a real site was read into any computation, test, example or figure. The only
  site-derived numbers are how many plots each village has.
- **An independent statistical review of the module has been done.** Every statistic was written
  a second time from its textbook definition, with plain loops and without reading the module's
  code path, and compared with the module on random inputs: unbalanced groups, one-member groups,
  ties, constant columns and missing values. All agreed to rounding (more than 20,000 comparisons, no
  mismatch). The R package vegan was not installed, so its Mantel, ANOSIM and PERMANOVA were not
  compared. The null models were checked directly: shuffles move whole plots, stand and type
  together, and stay inside villages when asked; the rotation null keeps every distance between
  plots, turns through all angles, never mirrors, and stays inside the village forest.
- **The review changed two things in the code. Neither changes a number in this note.**
  - The Mantel statistics, explained variance and Moran's I could differ in their last binary
    digit from one run to the next on the same inputs (the linear-algebra library adds in a
    different order depending on where an array sits in memory). They now use a sum that does
    not. The full check on generated data was run again afterwards and reproduced.
  - The Global Score gave the same map entered twice, with its stands numbered differently,
    scores of 0 and 1 in more than half of trials: a last-digit difference in one component was
    stretched to the full range by the rescaling. Components that are equal up to rounding now
    count as equal.
- **The review corrected one statement.** An earlier draft said two or three "too high" flags
  were expected by chance among the 48 false-alarm cells. The right figure is about 1.4 in the
  table and about 0.4 among the twelve cells of one null model.
- **The fixed-limit Global Score is not implemented** (question 12).
- **The run script does not compute the no-reference measures.** They need rasters; explained
  variance comes from the pipeline's metrics stage. The script also does not offer the torus
  translation, which needs a gridded map.
- **The run script has only been run on generated data**, in its own test.
- **No sensitivity study** of the rotation null (longer-range smoothness, thin forests, other
  stand sizes).
- **Not every paper was read.** What was read is stated beside each. Three source papers were
  read by title only (Hubert and Arabie 1985; Smouse, Long and Sokal 1986; Johnson and Xie 2011).

---

## 8. Before running on real data

The rule of the project is that analyses are declared before they are run (CLAUDE.md, "Results";
the pattern is `odisha_script/PHASE3_PREDECLARED.md`). The run script enforces the mechanical
part: it refuses to start without `--predeclared <file>`, records that file's sha256 in the
manifest and in the results, records whether the file is committed, has no default for the null
model, the number of relabellings, the seed or the distance bands, and will not overwrite an
existing result.

**This note does not make the choices below.** They are for Jaskaran and the supervisor, and they
must be written down and committed before the first run, so that none is made after seeing a
result. The earlier descriptive pair comparisons on Odisha data must play no part in them.

To be declared:

1. **The primary statistic**: one, by its name in the code, for the drawing and one for the
   labelling if both are primary. Everything else is secondary and is reported whatever it shows.
2. **The null model** behind every p-value, and that no p-value from another null will be
   offered as evidence.
3. **What counts as support, and what does not**: the level (0.05?), the family of tests the
   Holm correction runs over (which statistics, which stand maps, which sites), and the wording
   of the conclusion in each case, including "cannot be told from chance".
4. **The distance bands**, in metres, and the rule that gave them.
5. **The number of relabellings and the seed.**
6. **The field side**: which plots count, which measurements, how they are scaled, and how the
   field types are made (method and number of types), fixed before any score.
7. **The map side**: which stand map or maps (stand size, number of stand types), where the
   stand ids come from, the village forest polygons the plots may be moved in, and whether a
   plot must land on a stand that has a type (`--require-type`).
8. **Villages and districts**: the grouping columns, and that types are compared inside
   districts only.
9. **Settings with more than one defensible value**: ANOSIM village weights; Pearson or rank
   form of the Mantel statistics; the Mantel pair set.
10. **What happens when something cannot be computed**: a statistic not estimable, a village
    where the rotation null cannot be drawn. Decided now, so that no village is dropped later
    because of how it scores.
11. **For reference polygons**: which polygons are the reference, the boundary tolerance in
    metres, the sliver rule, what is left out of the boundary match, and the baseline map the
    scores will be set against.
12. **For no reference data**: the layers, and the set of candidate maps for the Global Score.
13. **Sensitivity checks**, listed now and reported whatever they show.
14. **What is expected, stated so that it can be wrong.**

Not to be done at any point: choosing a statistic, a band, a stand size or a number of types by
which gives the better score on any site.

---

## 9. How the metrics will be run

`scripts/run_evaluation.py` (tested end to end on generated data in
`tests/test_evaluation_run_script.py`). It reads a plot table (CSV) with columns named on the
command line, and optionally stand polygons, village forest polygons and reference polygons
(GeoJSON, projected metres). It writes two files:

- `evaluation_results.json`: results only. Every test with its observed value, the summary of the
  chance values, p and Holm-corrected p; and the working behind each statistic (pair counts and
  ceiling, the village-and-band table, per-village ANOSIM, the PERMANOVA table, per-reference
  segmentation accuracy). No run times, dates or paths, so a re-run can be compared byte for
  byte.
- `evaluation_manifest.json`: the git commit and whether the tree had uncommitted changes, the
  predeclaration and its sha256, the sha256 of every input file, the arguments and library
  versions.

When stand polygons are given, the stand of each plot is read from the polygons and checked
against the plot table; the script refuses to run if they disagree, because a test on labels that
are not the map's labels tests something else.

The command and every option are described at the top of the script. It has not been run on any
real data.

---

## References

### Cited

Verified means: DOI resolved on Crossref, title and first author match. "Read" says how much of
the paper was actually read.

| Paper | DOI | Verified | Read | Cited in |
|---|---|---|---|---|
| Rand 1971, J. Am. Stat. Assoc. 66, 846-850 | 10.1080/01621459.1971.10482356 | yes | abstract | 1.1 |
| Hubert and Arabie 1985, J. Classification 2, 193-218 | 10.1007/bf01908075 | yes | title only | 1.1 |
| Milligan and Cooper 1986, Multivariate Behav. Res. 21, 441-458 | 10.1207/s15327906mbr2104_5 | yes | abstract | 1.1 |
| Steinley 2004, Psychol. Methods 9, 386-396 | 10.1037/1082-989x.9.3.386 | yes | abstract | 1.1 |
| Warrens and van der Hoef 2022, J. Classification 39, 487-509 | 10.1007/s00357-022-09413-z | yes | abstract | 1.1 |
| Gates and Ahn 2017, bioRxiv preprint | 10.1101/196840 | yes (preprint) | abstract | 1.1 |
| Asadi et al. 2021, Ann. For. Sci. 78, 13 | 10.1007/s13595-020-01017-0 | yes | abstract | 1.1 |
| Mantel 1967, Cancer Res. 27, 209-220 | none registered | **UNVERIFIED** | nothing | 1.3 |
| Smouse, Long and Sokal 1986, Syst. Zool. 35, 627 | 10.2307/2413122 | yes | title only | 1.3 |
| Guillot and Rousset 2013, Methods Ecol. Evol. 4, 336-344 | 10.1111/2041-210x.12018 | yes | abstract; preprint in full | 1.3 |
| Legendre 2000, J. Stat. Comput. Simul. 67, 37-73 | 10.1080/00949650008812035 | yes | abstract | 1.3 |
| Legendre, Fortin and Borcard 2015, Methods Ecol. Evol. 6, 1239-1247 | 10.1111/2041-210x.12425 | yes | abstract | 1.3 |
| Crabot et al. 2019, Methods Ecol. Evol. 10, 532-540 | 10.1111/2041-210x.13141 | yes | full text | 1.3 |
| Quilodrán, Currat and Montoya-Burgos 2023, Mol. Ecol. Resour. 25, e13898 | 10.1111/1755-0998.13898 | yes | full text | 1.3 |
| Chaves et al. 2020, J. Veg. Sci. 32, e12938 | 10.1111/jvs.12938 | yes | abstract | 1.3, 1.4 |
| Clarke 1993, Aust. J. Ecol. 18, 117-143 | 10.1111/j.1442-9993.1993.tb00438.x | yes | abstract | 1.4 |
| Somerfield, Clarke and Gorley 2021, Austral Ecol. 46, 911-926 | 10.1111/aec.13059 | yes | full text | 1.4, 1.5, 1.6 |
| Anderson 2001, Austral Ecol. 26, 32-46 | 10.1111/j.1442-9993.2001.01070.pp.x | yes | full text | 1.5 |
| Anderson and Walsh 2013, Ecol. Monogr. 83, 557-574 | 10.1890/12-2010.1 | yes | abstract | 1.3, 1.4, 1.5 |
| Anderson and ter Braak 2003, J. Stat. Comput. Simul. 73, 85-113 | 10.1080/00949650215733 | yes | abstract | 1.4, 1.5 |
| Harms et al. 2001, J. Ecol. 89, 947-959 | 10.1111/j.1365-2745.2001.00615.x | yes | full text, 13 Oct; not read again on 17 or 20 Oct (section 1.6, note of 20 Oct) | 1.6 |
| Deblauwe, Kennel and Couteron 2012, PLoS ONE 7, e48766 | 10.1371/journal.pone.0048766 | yes | full text | 1.6 |
| Alexander-Bloch et al. 2018, NeuroImage 178, 540-551 | 10.1016/j.neuroimage.2018.05.070 | yes | abstract | 1.6 |
| Markello and Misic 2021, NeuroImage 236, 118052 | 10.1016/j.neuroimage.2021.118052 | yes | abstract | 1.6 |
| Clinton et al. 2010, Photogramm. Eng. Remote Sens. 76, 289-299 | 10.14358/pers.76.3.289 | yes | abstract | 2.1 |
| Sanchez-Lopez, Boschetti and Hudak 2018, Remote Sens. 10, 1622 | 10.3390/rs10101622 | yes | full text | 2.1, 3.2 |
| Costa, Foody and Boyd 2018, Remote Sens. Environ. 205, 338-351 | 10.1016/j.rse.2017.11.024 | yes | abstract | 2.1 |
| Martin, Fowlkes and Malik 2004, IEEE Trans. PAMI 26, 530-549 | 10.1109/tpami.2004.1273918 | yes | full text | 2.2 |
| Xiong et al. 2024, Silva Fennica 58(2) | 10.14214/sf.23014 | yes, with a caveat (3.1) | full text | 3.1 |
| Johnson and Xie 2011, ISPRS J. Photogramm. Remote Sens. 66, 473-483 | 10.1016/j.isprsjprs.2011.02.006 | yes | title only | 3.2 |
| Espindola et al. 2006, Int. J. Remote Sens. 27, 3035-3040 | 10.1080/01431160600617194 | yes | abstract | 3.2 |
| Böck, Immitzer and Atzberger 2017, Remote Sens. 9, 769 | 10.3390/rs9080769 | yes | full text | 3.2 |

Every DOI on this page, cited or not, was fetched again from Crossref in a separate citation
check after the note was drafted (63 DOIs; all resolved; every title and first author matched,
with the one caveat on Xiong et al. 2024). That check also re-read the abstract or open text
behind each statement about a cited paper and corrected the note where it said more than the
source. The records are kept outside the repository. To repeat the check for one DOI:

    curl -s https://api.crossref.org/works/<doi>

and compare `message.title`, `message.author[0].family` and `message.issued` with the row.

**The ten candidate references named in the brief**: Rand 1971, Hubert and Arabie 1985, Smouse,
Long and Sokal 1986, Guillot and Rousset 2013, Clarke 1993, Anderson 2001, Harms et al. 2001,
Johnson and Xie 2011 and Clinton et al. 2010 are verified and cited above. Mantel 1967 is cited
as UNVERIFIED.

### Considered and not cited

Each was looked up. "Verified" here again means the DOI record matches, not that the paper
supports anything. None is relied on in this note.

| Candidate | DOI | Why it is not cited |
|---|---|---|
| Holm 1979 (step-down correction) | none found | No Crossref record was found. The method is described in 1.6 without a reference. UNVERIFIED. |
| Clinton, Holt, Yan and Gong 2008, ISPRS Archives XXXVII-B4 | none found | Cannot be verified. Its open text was read and is one source of the formulas in 2.1. |
| De Cáceres et al. 2019, Ann. For. Sci. | 10.1007/s13595-019-0824-0 | Verified, but its abstract does not mention the Rand index and the full text could not be fetched. |
| Vinh, Epps and Bailey 2009, ICML | 10.1145/1553374.1553511 | Verified, abstract read. Held in reserve: a second source for the many-small-groups caution. |
| Sundqvist, Chiquet and Rigaill 2022, Comput. Stat. | 10.1007/s00180-022-01230-7 | Verified, abstract read. Held in reserve: makes the same point as Gates and Ahn 2017. |
| Lei et al. 2017, Pattern Recognit. | 10.1016/j.patcog.2016.12.003 | Verified, abstract read. Held in reserve: about bias of the raw Rand index. |
| de Souto et al. 2012, Brazilian Symp. Neural Networks | 10.1109/sbrn.2012.25 | Verified, abstract read. Held in reserve: a small conference comparison on unbalanced groups. |
| Warrens 2008, J. Classification | 10.1007/s00357-008-9023-7 | Verified, title only. |
| Stewart et al. 2021, IEEE JSTARS; Unnikrishnan, Pantofaru and Hebert 2007, IEEE TPAMI | 10.1109/jstars.2021.3122345; 10.1109/tpami.2007.1046 | Verified, abstracts read. They use modified Rand indices, not the plain one. |
| Severiano et al. 2011, J. Clin. Microbiol. | 10.1128/jcm.00624-11 | Verified. A different coefficient; not needed. |
| Pont-Tuset and Marques 2016, IEEE TPAMI | 10.1109/tpami.2015.2481406 | Verified, abstract read. Computer vision, not remote sensing. Held in reserve. |
| Oden and Sokal 1992, J. Classification | 10.1007/bf02621410 | Verified, abstract read. The earliest verified statement of the spatial problem with three-table tests; the cited papers agree with it. |
| Raufaste and Rousset 2001, Evolution | 10.1111/j.0014-3820.2001.tb00689.x | Verified, abstract read. Superseded for this purpose by Guillot and Rousset 2013. |
| Legendre and Fortin 2010, Mol. Ecol. Resour. | 10.1111/j.1755-0998.2010.02866.x | Verified, abstract read. Legendre et al. 2015 covers the same ground. |
| Borcard and Legendre 2012; Somers and Jackson 2022; Meirmans 2012 | 10.1890/11-1737.1; 10.1002/ecy.3780; 10.1111/j.1365-294x.2012.05578.x | Verified, abstracts read. About other things (the Mantel correlogram, a different distance, population genetics). |
| Fortin and Payette 2002, Écoscience | 10.1080/11956860.2002.11682707 | Verified, abstract read. Held in reserve, and a good candidate to add: fire and forest maps, compares complete and restricted randomisations with Mantel tests. |
| Tuomisto et al. 2003, J. Ecol.; Tuomisto et al. 2003, Ecol. Appl. | 10.1046/j.1365-2745.2003.00802.x; 10.1890/1051-0761(2003)013[0352:lfpwsh]2.0.co;2 | Verified, abstracts read. Further uses of the kind Chaves et al. 2020 is cited for. |
| Wynn et al. 2016, Cancer Res. (a commentary on Mantel 1967) | 10.1158/0008-5472.can-16-0883 | Verified, title only. It cannot stand in for Mantel 1967. |
| Itoh et al. 2010, For. Ecol. Manage. | 10.1016/j.foreco.2009.10.022 | Verified, abstract read. Held in reserve: a comparison of habitat-association tests that all use torus shifts. |
| Roxburgh and Matsuki 1999; Palmer and van der Maarel 1995; Roxburgh and Chesson 1998; Fortin, Drapeau and Jacquez 1996; Clifford, Richardson and Hémon 1989; Lotwick and Silverman 1982 | 10.2307/3546792; 10.2307/3545909; 10.1890/0012-9658(1998)079[2180:anmfds]2.0.co;2; 10.2307/3545584; 10.2307/2532039; 10.1111/j.2517-6161.1982.tb01221.x | Verified, abstracts read. The older literature on shift, rotation and restricted randomisation. Held in reserve. |
| Clarke and Green 1988, Mar. Ecol. Prog. Ser. | 10.3354/meps046213 | Verified, abstract read. Where one-way ANOSIM was first described, according to Somerfield et al. 2021. |
| McArdle and Anderson 2001, Ecology | 10.1890/0012-9658(2001)082[0290:fmmtcd]2.0.co;2 | Verified, abstract read. The companion to Anderson 2001; not needed for a one-way test. |
| Zhang, Fritts and Goldman 2008, Comput. Vis. Image Underst. | 10.1016/j.cviu.2007.08.003 | Verified, preprint read. A computer-vision survey of unsupervised measures; does not cover the Global Score. Without it this note has no general review of such measures. |
| Radoux and Defourny 2007, Remote Sens. Environ. | 10.1016/j.rse.2007.02.031 | Verified, abstract read. Boundary displacement for forest stands; formulas not read. Held in reserve. |
| Moran 1950, Biometrika | 10.2307/2332142 | Verified, title only. The origin of Moran's I; the form used is the one defined in the segmentation papers. |

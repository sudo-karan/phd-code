# The elbow behind the number of stand types, in the clustering stage's space (review A7)

Written 20 Oct 2026 (round 13, Task 6). This compares the two committed elbow files with the
elbow recomputed in the clustering stage's space. It chooses no k: k is unchanged in every config
(6 at 10 hectares, 5 at 3 hectares, as `PHASE3_PREDECLARED.md` fixed them), and no score changes.
The two committed files are unchanged except for a dated note at their end.

## The finding

`odisha_phase3_2_stand_k_elbow.py` said its preprocessing "mirrors the clustering stage". It does
not (review A7, `docs/reviews/2026-10-19-review.md`). Compared with `src/fmu/stages/clustering.py`
(its preprocessing lines were the same at `c368eb7`, where this comparison was made, as at
`4f3f04e`, 26 Aug 2026, so the same as when the stands of record were typed; their run records
date from 15 Sept and 8 Oct 2026. Corrected 20 Oct 2026: this said "the same at HEAD". Later in
round 13 four fixes change those lines, the phase pair kept out of the skew test (B13), one mean
per stand over all its pieces (B14), exact quartiles (B16) and a flat cell's aspect pair (0, 0)
(A5); the two stage spaces below rebuild the stage before them, the stage that typed the stands
of record, so their numbers stand, but for stands typed by the stage as fixed they would have to
follow those four):

1. it keeps `annual_rainfall` and `ndvi_residual_variance`, which the stage leaves out
   (`_EXCLUDE_BANDS`);
2. it logs only non-negative bands, by `log1p`, where the stage logs every band whose |skew| over
   its rows is above 1, by log(x − min + 0.001);
3. it keeps bands with no spread, which the stage drops;
4. it fits every polygon of the stand file, including the stands with no type and each piece of a
   stand in several pieces, where the stage fits one row per stand with a type;
5. it takes sin and cos of the layers' mean angles, where the stage takes them per pixel, before
   the mean.

Also, neither committed elbow is in the geometry k-means is fitted in: `wekaKMeans` min-max
normalises each band over its training rows, which undoes the median/IQR scaling (review A2).

## What was computed

The script keeps its own space as the default (`--space script`), which still writes the two
committed files byte for byte. Two new spaces write new files beside them:

- **`--space stage`** rebuilds the stage's rows from the committed stand files of record
  (`phase2_vectors/<arm>_<district>_stands_merged.geojson`). It uses the stage's bands, with
  aspect and the NDVI phase as sin/cos pairs, and one row per stand with a type (its largest
  piece). It applies the stage's log rule and offset over those rows and drops bands with IQR 0.
  Files: `odisha_phase3_2_k_elbow_odisha_v120_handcrafted_stage.txt` (10 ha) and
  `odisha_phase3_2_k_elbow_odisha_v120_3ha_stage.txt` (3 ha).
- **`--space stage-rows`** reads the clustering stage's own k-means rows, the only exact rows
  available offline. They belong to the `_repro` runs of 13 Oct 2026, whose configs differ from
  those of record only in `name`. `scripts/remerge_demo_set.py` fitted the stage to them again,
  with every input read from the cache (`docs/demo/remerge/README.md`). So these are not the
  stands of record (at 3 ha the `_repro` stand files have 207, 474, 184 and 1,145 polygons,
  against 203, 473, 186 and 1,131), nor the fit that typed them. They are off git, in
  `outputs/demo/` on the Mac, and the result files give each input's size and SHA-256. Each
  district's rows give back exactly the elbow committed in `docs/demo/remerge/<run>.json`, or the
  script stops. The same file checks the rebuild's rules against these rows and rebuilds the same
  stands from their own stand files. Files:
  `odisha_phase3_2_k_elbow_odisha_v120_handcrafted_stage_rows.txt` and
  `odisha_phase3_2_k_elbow_odisha_v120_3ha_stage_rows.txt`.

Both report the elbow in two geometries side by side, and name neither as the one of record:

- **(i) declared**: the stage's preprocessing, then (x − median)/IQR (DEC-003), with exact
  quantiles. The stage's own rows are also given as the stage scaled them, with Earth Engine's
  percentiles (review B16).
- **(ii) the fit's**: the stage's preprocessing, then each band min-max normalised over the fit
  rows, as `wekaKMeans` does (review A2).

The sweep is the script's own throughout: scikit-learn k-means, seed 42, 25 starts, k from 2 to
12, the knee of the inertia curve. Every elbow is given again with the same rows in reverse order,
because k-means' best of 25 starts depends on the order of the rows (commit `91f4287`).

## The elbows

Each cell gives the elbow with the rows in their declared order (stand id; the stage's own rows
in the order the stage sampled them). In brackets is the elbow with the same rows in reverse
order, where it differs. "Pooled" is the four districts' rows put through the same preprocessing
together. The pipeline never fits them together, and the stage's own rows, scaled district by
district, cannot be pooled.

**10 hectare stands** (k = 6 in the configs)

| | Angul | Dhenkanal | Kendujhar | Koraput | Pooled |
|---|---|---|---|---|---|
| Script's own space (`odisha_phase3_2_k_elbow_odisha_v120_handcrafted.txt`) | 6 | 6 | 6 | 5 | 5 |
| Stage's space, stand files of record, (i) | 5 | 6 | 7 | 5 | 5 |
| Stage's space, stand files of record, (ii) | 6 | 6 | 5 | 5 | 5 |
| Stage's own rows, `_repro` stands, (i) as the stage scaled them | 6 | 5 | 6 | 5 | |
| Stage's own rows, `_repro` stands, (i) exact quantiles | 6 (7) | 5 | 6 | 5 | |
| Stage's own rows, `_repro` stands, (ii) | 5 | 6 | 6 | 5 | |
| Rebuilt from the `_repro` stand files, (i) | 6 | 6 | 6 | 5 | |
| Rebuilt from the `_repro` stand files, (ii) | 6 | 6 | 5 | 5 | |

**3 hectare stands** (k = 5 in the configs)

| | Angul | Dhenkanal | Kendujhar | Koraput | Pooled |
|---|---|---|---|---|---|
| Script's own space (`odisha_phase3_2_k_elbow_odisha_v120_3ha.txt`) | 5 | 5 | 5 | 5 | 5 |
| Stage's space, stand files of record, (i) | 6 | 6 | 6 (8) | 5 | 5 |
| Stage's space, stand files of record, (ii) | 5 | 6 | 6 | 6 | 5 |
| Stage's own rows, `_repro` stands, (i) as the stage scaled them | 5 | 6 | 6 | 5 | |
| Stage's own rows, `_repro` stands, (i) exact quantiles | 6 (5) | 6 | 6 | 5 | |
| Stage's own rows, `_repro` stands, (ii) | 5 | 6 | 6 | 5 | |
| Rebuilt from the `_repro` stand files, (i) | 4 | 5 | 5 (7) | 5 | |
| Rebuilt from the `_repro` stand files, (ii) | 5 | 6 | 6 | 6 | |

In the 10 ha Kendujhar stand file of record, the two common skewness estimators (G1, g1) disagree
on whether `vh_iqr` is logged. With g1 the elbow is 6 in (i) and still 5 in (ii) (the `_stage`
file gives both).

## How far each route can be trusted

**The stage's own rows** are exact for what the stage computed. On them, the rebuild's rules
reproduce the stage's own decisions: every log decision on the active bands, by G1 and by g1
alike, and every log offset (−min over the rows + 0.001), in all eight runs. Of the 47 stands in
several typed pieces with a row in the fit, the stage's row is the largest piece's in 41, another
piece's in none, and 6 could not be told apart. The stage's spreads are 0.888 to 1.167 times the
exact IQR of its own rows (review B16). Scaling by exact quantiles instead moves the elbow in one
district of eight (3 ha Angul, 5 to 6), and with the rows reversed it is 5 again. These rows have
two limits: they are the `_repro` stands, not the stands of record, and a fit from the cache, not
the fit that typed the stands of record.

**The rebuild from the stand files** is on the stands of record, but it is approximate:

- the stage takes sin and cos of aspect and of the phase per pixel, then the mean; the stand files
  hold the arithmetic mean of each angle (review C10), so the angle bands differ most, and with
  them which bands are logged;
- a stand file's values are the export's mean over each polygon, by pixel share. On the legacy
  cache layout, which these runs used, the features lay on another grid than the polygons, so a
  polygon's mean takes in slivers of its neighbours;
- a stand file of that layout types some stands that had no row in the fit, through the export's
  vote (`docs/demo/remerge/README.md`, section 4), and does not say which. On the `_repro` stands
  that is 3 to 32 stands per district (for example 906 rows against the stage's 879 at 3 ha
  Koraput), and one stand with a row is untyped in its file (10 ha Angul);
- the stage's percentiles and its skewness estimator are Earth Engine's (above).

On the `_repro` stands, where both routes exist, the rebuild gives the stage's own elbow in 9 of
the 16 district and geometry cells (rows in their declared order; (i) against exact quantiles).

**The order of the rows** alone moves 4 of the 60 elbows given in both orders, by one or two:
10 ha Angul on the stage's rows (i) exact, 3 ha Angul on the same, 3 ha Kendujhar on the stand
file of record (i), and 3 ha Kendujhar rebuilt from its `_repro` file (i). A difference of one
between two lines of these tables can therefore come from the order of the rows alone.

## What it shows

Descriptive only. No line here is named the elbow of record, and no k is chosen.

- **3 hectares: "5 in every district" holds only in the script's own space.** In the stage's
  space no line gives 5 in every district. On the stage's own rows, Dhenkanal and Kendujhar give 6
  in every line and in both orders, Angul 5 or 6, and Koraput 5. On the stand files of record,
  Dhenkanal gives 6 and Kendujhar 6 (8 in reverse order, (i)); Angul gives 6 in (i) and 5 in (ii),
  and Koraput 5 in (i) and 6 in (ii).
- **10 hectares**: the committed 6, 6, 6, 5 becomes 5, 6, 7, 5 in (i) and 6, 6, 5, 5 in (ii) on
  the stand files of record. On the stage's own rows it is 6, 5, 6, 5 in (i) and 5, 6, 6, 5 in
  (ii). Koraput, which holds 145 of the 267 scored plots, gives 5 in every line.
- **Pooled**: 5 in every line that has a pooled elbow, both stand sizes, both geometries, both
  orders, as in the committed files.
- **The committed files' own rule**, the median of the four district elbows and the pooled one,
  would give 5 at 10 ha and 6 at 3 ha on the stand files of record, in both geometries and both
  orders. That is the reverse of the configs' 6 and 5. The rule is not applied here.
- **The two geometries disagree** in some districts on either route (for example 10 ha Kendujhar
  on the stand files of record, 7 against 5). Which geometry is of record depends on A2.

## What does not change

- k: 6 at 10 hectares and 5 at 3 hectares, as `PHASE3_PREDECLARED.md` fixed them before any
  score was computed.
- Every score and chance test: none reads the elbow.
- The two committed elbow files: the default space still writes them byte for byte, up to the
  dated note now at their end, which the script does not write.
- Which geometry is the one of record: that is A2, a method decision left to Jaskaran and
  Prof. Seth.

## Commands

From the repo root:

```bash
python odisha_script/odisha_phase3_2_stand_k_elbow.py --arm odisha_v120_handcrafted --space stage
python odisha_script/odisha_phase3_2_stand_k_elbow.py --arm odisha_v120_3ha --space stage
python odisha_script/odisha_phase3_2_stand_k_elbow.py --arm odisha_v120_handcrafted --space stage-rows --demo-dir outputs/demo
python odisha_script/odisha_phase3_2_stand_k_elbow.py --arm odisha_v120_3ha --space stage-rows --demo-dir outputs/demo
```

The last two need the off-git `outputs/demo/` of the Mac (written by
`scripts/remerge_demo_set.py --all`). Their result files list each input's size and SHA-256.
`tests/test_phase3_stand_k_elbow_stage_space.py` tests the rebuild's rules. Its slow tests
(`pytest -m slow`) write all six files again and compare them byte for byte, the two committed
files up to their dated note.

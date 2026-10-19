# The demo set, re-merged under the second-pass rule

Task A2 of `docs/handoff/2026-10-13-round2.md`. The demo set is the 14 Earth Engine runs of
13 Oct 2026 (`docs/demo/demo_set.json`). Their stands were merged by the code as it was then.
`scripts/remerge_demo_set.py` merges the same saved superpixels again, from the same saved
feature assets, twice: under that rule ("old"), to check that a re-merge gives back the stands
each run exported, and under the rule of `spec-merge-pass2-skip-at-minimum` ("new"), in which a
region that has already reached the minimum stand size by the time its turn comes in the second
pass is skipped. It then fits the stand types again for each rule (the clustering stage, live)
and builds the stand layer with the export stage's own code. It reads Earth Engine and submits
nothing. Each run was made from a clean clone pinned to commit `5c8dcad`.

One file per run, `<run_id>.json`: results only. The stand files themselves are on the Mac, in
the git-ignored `outputs/demo/` (`vectors_new/`, `vectors_old/`, `remerge/<run_id>/`).

## 1. The old rule gives back the stands of all 14 runs

For every run: the merge totals and every stand's pixel count and means equal the run's own
record; every pixel is in the same stand as in the polygons the run exported; and the stand
layer built here has the same number of polygons, with every stand's outline and area equal to
the exported one. So what differs under the new rule is the rule.

| Run | Old rule gives the run's stands | Live fit gives the run's stand types | Stands, old to new | Stand area that changed stand | Plots that changed stand | k in the config | Elbow, old / new stands |
|---|---|---|---|---|---|---|---|
| `odisha_alphaearth_angul_repro` | yes | no: 34 of 91 stands differ (ARI 0.36) | 97 to 99 | 2.9% (12.6 of 439.4 ha) | 0 of 39 | 6 | 5 / 5 |
| `odisha_alphaearth_dhenkanal_repro` | yes | yes (203 stands) | 215 to 220 | 3.0% (30.2 of 995.6 ha) | 1 of 75 | 6 | 5 / 5 |
| `odisha_alphaearth_kendujhar_repro` | yes | no: 29 of 107 stands differ (ARI 0.50) | 118 to 122 | 6.1% (24.9 of 404.8 ha) | 1 of 8 | 6 | 6 / 6 |
| `odisha_alphaearth_koraput_repro` | yes | no: 199 of 455 stands differ (ARI 0.38) | 623 to 642 | 4.1% (100.2 of 2459.5 ha) | 1 of 145 | 6 | 5 / 5 |
| `odisha_v120_3ha_angul_repro` | yes | no: 4 of 195 stands differ (ARI 0.95) | 204 to 211 | 6.3% (27.6 of 439.4 ha) | 0 of 39 | 5 | 5 / 6 |
| `odisha_v120_3ha_dhenkanal_repro` | yes | no: 89 of 445 stands differ (ARI 0.60) | 462 to 475 | 5.0% (50.1 of 995.6 ha) | 1 of 75 | 5 | 6 / 6 |
| `odisha_v120_3ha_kendujhar_repro` | yes | yes (173 stands) | 180 to 198 | 16.5% (66.7 of 404.8 ha) | 0 of 8 | 5 | 6 / 6 |
| `odisha_v120_3ha_koraput_repro` | yes | no: 76 of 905 stands differ (ARI 0.82) | 1125 to 1187 | 10.2% (251.8 of 2459.5 ha) | 4 of 145 | 5 | 5 / 5 |
| `odisha_v120_handcrafted_angul_repro` | yes | no: 6 of 93 stands differ (ARI 0.84) | 96 to 103 | 8.8% (38.7 of 439.4 ha) | 1 of 39 | 6 | 6 / 7 |
| `odisha_v120_handcrafted_dhenkanal_repro` | yes | no: 43 of 215 stands differ (ARI 0.62) | 231 to 236 | 1.9% (19.2 of 995.6 ha) | 2 of 75 | 6 | 5 / 5 |
| `odisha_v120_handcrafted_kendujhar_repro` | yes | yes (96 stands) | 103 to 108 | 7.3% (29.4 of 404.8 ha) | 0 of 8 | 6 | 6 / 6 |
| `odisha_v120_handcrafted_koraput_repro` | yes | no: 9 of 473 stands differ (ARI 0.96) | 617 to 637 | 3.7% (91.8 of 2459.5 ha) | 2 of 145 | 6 | 5 / 5 |
| `sanjay_van_alphaearth_repro` | yes | no: 76 of 260 stands differ (ARI 0.44) | 290 to 296 | 2.6% (33.3 of 1302.2 ha) | no field plots | 6 | 5 / 5 |
| `sanjay_van_baseline_repro` | yes | no: 77 of 265 stands differ (ARI 0.51) | 291 to 299 | 3.7% (48.2 of 1302.2 ha) | no field plots | 6 | 5 / 5 |

The second column is the check the brief asks for. "Stand area that changed stand" counts a
pixel as changed when its new stand is not the one that best matches its old stand.

## 2. What the new rule changes

- More stands in every run, from 2 more (`odisha_alphaearth_angul_repro`) to 62 more
  (`odisha_v120_3ha_koraput_repro`), and fewer second-pass merges in every run. That is what
  happened in these 14 runs, not a property of the rule: skipping one merge can leave room for
  another, and a hand-built case in `tests/test_region_merge_provenance.py` ends with fewer
  stands under the new rule.
- Between 1.9% and 16.5% of the stand area is in another stand.
- Field plots whose stand changed: 3 of 267 (AlphaEarth, 10 ha), 5 of 267 (hand-crafted, 3 ha), 5 of 267 (hand-crafted, 10 ha).

## 3. The stand types the runs saved are not the types a second fit gives

The clustering stage was run again on each run's own stands (the old rule), from the same saved
features. The result is repeatable: two such runs gave identical types, stand for stand
(checked on `odisha_alphaearth_kendujhar_repro` and `odisha_v120_3ha_angul_repro`). It agrees
with the types the run saved in 3 of the 14 runs. In the other 11 it does not:

| Run | Computed live in the pass that fitted the saved types | Stands the saved fit counted | Stands the run exported | Typed stands whose type differs, after the best renumbering | Agreement over pixels (adjusted Rand index) |
|---|---|---|---|---|---|
| `odisha_alphaearth_angul_repro` | `optical_features`, `structure_features` | 102 | 97 | 34 of 91 | 0.42 |
| `odisha_alphaearth_dhenkanal_repro` | nothing (all read from the cache) | 215 | 215 | 0 of 203 | 1.00 |
| `odisha_alphaearth_kendujhar_repro` | `optical_features`, `structure_features` | 115 | 118 | 29 of 107 | 0.44 |
| `odisha_alphaearth_koraput_repro` | `optical_features`, `structure_features` | 621 | 623 | 199 of 455 | 0.38 |
| `odisha_v120_3ha_angul_repro` | `static_features` | 204 | 204 | 4 of 195 | 0.96 |
| `odisha_v120_3ha_dhenkanal_repro` | `static_features` | 462 | 462 | 89 of 445 | 0.55 |
| `odisha_v120_3ha_kendujhar_repro` | `static_features` | 180 | 180 | 0 of 173 | 1.00 |
| `odisha_v120_3ha_koraput_repro` | `static_features` | 1125 | 1125 | 76 of 905 | 0.78 |
| `odisha_v120_handcrafted_angul_repro` | `static_features` | 96 | 96 | 6 of 93 | 0.81 |
| `odisha_v120_handcrafted_dhenkanal_repro` | `static_features` | 231 | 231 | 43 of 215 | 0.52 |
| `odisha_v120_handcrafted_kendujhar_repro` | `static_features` | 103 | 103 | 0 of 96 | 1.00 |
| `odisha_v120_handcrafted_koraput_repro` | `static_features` | 617 | 617 | 9 of 473 | 0.97 |
| `sanjay_van_alphaearth_repro` | `optical_features`, `structure_features` | 294 | 290 | 76 of 260 | 0.39 |
| `sanjay_van_baseline_repro` | `static_features` | 291 | 291 | 77 of 265 | 0.38 |

Types are compared as groupings, whatever their numbers: k-means numbers its types afresh on
every fit. "The best renumbering" pairs the types of the two fits one to one so that as many
stands as possible agree.

**The cause is in the run logs** (`docs/reproducibility/clustering_route.json`, made by
`scripts/segmentation_route.py --stage clustering --output cluster_labels` from the run
manifests). A run goes through the pipeline in three passes: segmentation, clustering, export.
A feature stage that an earlier pass did not need is computed live, on the analysis grid, the
first time a pass needs it, and is read back from the cache, on the geographic grid, by every
later pass. The merge is not cached: each pass merges again from whatever it reads.

- In the hand-crafted runs the clustering pass computed `static_features` live (segmentation
  does not use them). The types were fitted with those; a later fit reads them from the cache.
- In the AlphaEarth runs the clustering pass computed `optical_features` and
  `structure_features` live. Those hold the merge criteria. So that pass merged the superpixels
  on other values than the export pass did, and **the saved types were fitted on stands that are
  not the stands the run exported**: 102 against 97 in Angul, 115 against 118 in Kendujhar, 621
  against 623 in Koraput, 294 against 290 at Sanjay Van.
- In the one run whose clustering pass read everything from the cache
  (`odisha_alphaearth_dhenkanal_repro`), the second fit gives the saved types exactly.

This is the open cache-grid question (PR #42, question 1) reaching the stand types. It is not
fixed here. The demo's types are those of the fit made here, on the re-merged stands, with
every input read from the cache: the stands shown and the stands typed are the same stands.

## 4. The export stage gives some stands with no habitat pixel a neighbour's type

The export stage takes, for each stand polygon, the commonest type among the typed pixels it
touches, each weighted by the share of the pixel inside the polygon. The types sit on the
geographic grid and the polygons on the UTM grid, so a polygon also touches slivers of its
neighbours' pixels. A stand with no habitat pixel of its own, which the fit never typed, can
take a neighbour's type that way: between 3 of 475 stands (`odisha_v120_3ha_dhenkanal_repro`) and 33 of
637 (`odisha_v120_handcrafted_koraput_repro`) under the new rule (`stands_typed_by_the_export_only` in each file). The
demo keeps the export's types, because they are what a run writes.

Note of 19 Oct 2026 (round 12): the first sentence of this section describes the export as it was. Since round 12
a stand with a row in the k-means fit takes its row's type (register entry
`spec-export-stand-type-from-its-fit-row`); the stands counted here have no row, keep the vote, and are counted as
before (question 1 of `docs/handoff/2026-10-19-round12.md`).

Note of 20 Oct 2026 (round 13): since round 13 they no longer keep the vote. A stand with no typed pixel of its own
gets a null type in every layout (question 1, answered (b); register entry
`spec-export-stand-type-from-its-own-row-or-null`). Counted offline from the re-merge's per-stand files (off git,
`outputs/demo/remerge/<run>/clustering_new.json`, `stand_type_by_pixel_centres`), a re-export would give every
stand counted here a null type but one of the 33 of `odisha_v120_handcrafted_koraput_repro`, which holds typed pixel
centres of its own and keeps the type it had; and two stands with a row in the fit that hold no typed pixel centre
on the type grid, one in `odisha_v120_3ha_dhenkanal_repro` and one in `odisha_v120_handcrafted_dhenkanal_repro`,
would lose the type the vote gave them, which was their row's. The counts above are of the layers as built at
`5c8dcad`, and stay as they are.

## 5. The type map moves a great deal when the stands move a little

The two fits made here, on the old stands and on the new, share their inputs and differ only
in the 1.9% to 16.5% of stand area that changed stand. Over the pixels typed in both, their
agreement (adjusted Rand index) runs from 0.31 (`sanjay_van_alphaearth_repro`) to 0.94
(`odisha_v120_handcrafted_dhenkanal_repro`), with a median of 0.53.

## 6. k and the elbow

k is as each config sets it and was not changed. The elbow is computed on the rows the
pipeline's own k-means was fitted on (one row per stand, scaled), for k = 2 to 12, with the
knee definition of `odisha_script/odisha_phase3_2_stand_k_elbow.py`. On the new stands it
differs from the config's k in 11 of the 14 runs. This is listed under "Questions for
Jaskaran" in PR #43.

| Run | k in the config | Elbow, old stands | Elbow, new stands | New stands against the config |
|---|---|---|---|---|
| `odisha_alphaearth_angul_repro` | 6 | 5 | 5 | differs |
| `odisha_alphaearth_dhenkanal_repro` | 6 | 5 | 5 | differs |
| `odisha_alphaearth_kendujhar_repro` | 6 | 6 | 6 | same |
| `odisha_alphaearth_koraput_repro` | 6 | 5 | 5 | differs |
| `odisha_v120_3ha_angul_repro` | 5 | 5 | 6 | differs |
| `odisha_v120_3ha_dhenkanal_repro` | 5 | 6 | 6 | differs |
| `odisha_v120_3ha_kendujhar_repro` | 5 | 6 | 6 | differs |
| `odisha_v120_3ha_koraput_repro` | 5 | 5 | 5 | same |
| `odisha_v120_handcrafted_angul_repro` | 6 | 6 | 7 | differs |
| `odisha_v120_handcrafted_dhenkanal_repro` | 6 | 5 | 5 | differs |
| `odisha_v120_handcrafted_kendujhar_repro` | 6 | 6 | 6 | same |
| `odisha_v120_handcrafted_koraput_repro` | 6 | 5 | 5 | differs |
| `sanjay_van_alphaearth_repro` | 6 | 5 | 5 | differs |
| `sanjay_van_baseline_repro` | 6 | 5 | 5 | differs |

## How to make it again

```bash
python scripts/remerge_demo_set.py --all        # Earth Engine, read-only; about 1 hour 20 minutes for the 14
python scripts/remerge_demo_set.py --saved-fit  # Earth Engine, read-only: one property read per run
python scripts/remerge_demo_set.py --recheck    # offline: the old-rule checks again, from the saved files
python scripts/remerge_demo_set.py --table      # offline: the two tables above
python scripts/segmentation_route.py --stage clustering --output cluster_labels \
    --config configs/*_repro.yaml --runs-dir outputs/repro_runs/runs \
    --out docs/reproducibility/clustering_route.json   # offline, from the run manifests
```

The files here were written by `--all` at commit `5c8dcad`; their `old_rule_check` was then
rewritten by `--recheck` and `--saved-fit` with the comparisons of the stand types added in the
commit after it. `tests/test_remerge_demo_set.py` checks that the tables above are the tables
the tool prints from these files.

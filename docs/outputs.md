# Outputs

What each fmu run produces, where it lives, and how to interpret it.
This is the reproducibility surface: if the manifest is complete, the
run can be reproduced exactly.

## The run directory

Every pipeline run creates a fresh directory:

```
outputs/runs/<config_name>_<YYYYMMDD-HHMMSS>/
```

Inside, depending on which stages ran:

```
fmu.log                                 always
manifest.json                           always
export_manifest_<config>.json           after export stage
cluster_profiles.csv                    after profiling stage
metrics_<config>.json                   after metrics stage (via inspect script)
merge_provenance.csv, .json             after scripts/inspect_merge.py
input_images.json                       when a stage computed an output live
<stage>_*.csv, <stage>_*.json           a stage's result files (round 14), below
```

A stage can hand the orchestrator result files (`StageResult.files`, round 14): tables too
large for the manifest, such as the k-means rows of the clustering stage with
`clustering.fit_outside_earth_engine` on (`clustering_stand_table.csv`,
`clustering_fit_rows.csv`, `clustering_kmeans.json`) and of the k elbow step with
`k_elbow.in_fit_space` on (`k_elbow.csv`, `k_elbow_stand_table.csv`, `k_elbow_fit_rows.csv`,
`k_elbow_types.csv`, `k_elbow_preprocessing.json`; `docs/configs.md`, `k_elbow`). They are written into the run folder as the stage returns, and the stage's manifest entry
names each under `files`, with its size and SHA-256; a stage that wrote none has no `files`
key. They hold results only, no dates or times. A stage served from the cache does not run
and writes none.

The directory is gitignored; checking outputs into git is not the
intended workflow. Reproducibility is via `manifest.json` (the inputs)
plus the cached GEE assets (the outputs).

### What is committed and what is not

| Where | In git? | What |
|---|---|---|
| `outputs/runs/<config>_<timestamp>/` | ignored (`outputs/`) | run directories: log, manifests, CSVs |
| `outputs/transparency/<config>/` | ignored (`outputs/`) | rasters and GeoJSON behind the mask maps (see "Transparency outputs") |
| `runs/`, `fmu_exports_clean/`, `reports/` | ignored | what `scripts/report.py` reads and writes (see "Reports") |
| `docs/transparency/<config>/` | **committed** | the mask maps, `summary.md`, `run_record.json` |
| `docs/reproducibility/`, `docs/evaluation/` | **committed** | results of the asset comparisons, of the cached-versus-live superpixel test (each with a `_run.json` run record) and of the synthetic validation |
| `odisha_script/phase2_vectors/` | **committed** | Odisha stand layers and `<config>_run.json` run records |
| `*.log`, `logs/` | ignored | run times and pass logs |
| Earth Engine assets, Google Drive files | not in the repo | cached stage outputs; exported rasters and vectors |

## `fmu.log`

Plain-text log, identical to what was printed to terminal during the
run. Useful for:
- Diagnosing a run after the fact ("did stage X complete or did it fail?")
- Per-band preprocessing values (DEBUG level only)
- Cache hit/miss decisions
- Stage timing

Logging is configured in `src/fmu/utils/logging.py`. Level controlled
via `LOG_LEVEL` in `.env` (`INFO` default; `DEBUG` for verbose).

## `manifest.json`

Written by the orchestrator at the end of every run. Captures
everything needed to know what happened:

```json
{
  "config_name": "sanjay_van_baseline",
  "run_dir": "outputs/runs/sanjay_van_baseline_20260520-013522",
  "total_elapsed_sec": 142.815,
  "use_cache": true,
  "submit_exports": true,
  "summaries": true,
  "git": {
    "commit": "<full hash of HEAD>",
    "dirty": false,
    "modified": [],
    "modified_truncated": false,
    "untracked_code": [],
    "untracked_code_truncated": false,
    "untracked": [],
    "untracked_truncated": false,
    "root": "/path/to/the/checkout",
    "error": null
  },
  "stages": [
    {
      "name": "masking",
      "elapsed_sec": 18.244,
      "produced": ["habitat_mask", "landcover_summary", "mask_provenance", "water_mask"],
      "warnings": [],
      "metadata": { "...stage-specific..." },
      "cache_status": {
        "habitat_mask": "hit",
        "water_mask": "hit",
        "landcover_summary": "hit",
        "mask_provenance": "hit"
      },
      "export_tasks": [],
      "transparency": {
        "display_layers": [
          {
            "key": "mask_provenance",
            "band": "reason",
            "title": "Habitat mask, by reason",
            "description": "...",
            "vis": { "bands": ["reason"], "min": 0, "max": 5, "palette": ["000000", "1a9850", "..."] },
            "legend": [
              { "value": 0, "label": "No land-cover data in either map (not habitat)", "color": "000000" },
              { "value": 1, "label": "Kept as habitat (not only forest)", "color": "1a9850" }
            ],
            "legend_note": "This is a habitat mask, not a strict forest mask. ...",
            "asset": "projects/.../sanjay_van_baseline/masking/mask_provenance__<fingerprint>",
            "asset_status": "hit"
          }
        ],
        "summary_numbers": [
          { "name": "area_ha", "description": "Area of the ROI the mask was tabulated over", "unit": "ha", "value": 0.0 },
          { "name": "share_kept", "description": "Share of that area kept as habitat", "unit": "fraction", "value": 0.0 }
        ]
      }
    },
    {
      "name": "data_load",
      "elapsed_sec": 12.91,
      "produced": ["s1_collection", "s2_collection", "s2_composite"],
      "warnings": [],
      "metadata": { "s2_count": 287, "s1_count": 142 },
      "cache_status": { "s2_composite": "miss-exported" },
      "export_tasks": [
        {
          "task_id": "ABCDEF123456",
          "asset_path": "projects/.../sanjay_van_baseline/data_load/s2_composite__<fingerprint>",
          "description": "sanjay_van_baseline_data_load_s2_composite"
        }
      ],
      "transparency": { "display_layers": [], "summary_numbers": [] }
    }
  ],
  "config": {
    "name": "sanjay_van_baseline",
    "description": "...",
    "roi": { "...": "..." },
    "dates": { "...": "..." },
    "datasets": { "...": "..." }
  }
}
```

### Field reference

| Field | Meaning |
|---|---|
| `config_name` | The `name` field from the input YAML |
| `total_elapsed_sec` | Wall-clock time for the full pipeline run |
| `use_cache` | The `use_cache` argument given to `Pipeline()` |
| `submit_exports` | The `submit_exports` argument given to `Pipeline()`. `false` means the run read the cache and submitted no cache export. It has no effect unless `use_cache` is on |
| `summaries` | The `summaries` argument given to `Pipeline()`. `false` means no stage's summary numbers were computed |
| `git` | Which code ran: commit and uncommitted changes, as the run started. See "The `git` block" below |
| `git_at_end` | The same block read again as the manifest is written (round 13): a commit or an edit made while the run ran shows as a difference from `git` |
| `stages[].name` | Stage name (matches the `@register_stage` decorator) |
| `stages[].elapsed_sec` | Wall-clock time for this stage |
| `stages[].produced` | Sorted list of context keys this stage actually wrote |
| `stages[].warnings` | Stage-emitted warnings (non-fatal) |
| `stages[].metadata` | Stage-specific stats: band counts, sample sizes, etc. |
| `stages[].cache_status` | Per-output-key: `"hit"`, `"miss"`, `"miss-exported"`, or `"off"` |
| `stages[].export_tasks` | Async GEE export tasks submitted during this stage |
| `stages[].transparency` | What the stage declares about itself, filled in: display layers and summary numbers. See "The transparency record" below |
| `config` | The entire input config, serialized. Proves what was run. |

### Cache status values

- `"hit"`: asset was already cached; cached version loaded into context
- `"miss"`: asset wasn't cached; live computation used and nothing was
  submitted. This is what every uncached output of a read-only run
  (`submit_exports=False`) records
- `"miss-exported"`: asset wasn't cached; live computation used AND an
  export task was started so next run will hit
- Key absent: output is not cacheable (e.g., a Python dict, an
  `ee.ImageCollection`). With caching off (`use_cache=False`, see the
  top-level key) `cache_status` is empty for every stage

### The `git` block

Written by `git_state()` in `src/fmu/utils/provenance.py`. It describes the
checkout the `fmu` package was imported from, not the working directory. The
same block is in `export_manifest_<config>.json`, in the Odisha
`<config>_run.json` records, in `docs/transparency/<config>/run_record.json`
and in `evaluation_manifest.json`. Result files do not carry it.

`git_state()` remembers its first answer for the life of the process, so the
block describes the tree as it was when the process first asked. Since round 13
the pipeline asks when `Pipeline.run` starts, before any stage, and the kept-land
scorer and chance test and Phase 1 step 12 ask at the start of `main()`, before
they write a result; each also records `git_at_end`, the block read again
(`git_state_now()`) when the record is written (review C32). Before round 13 the
first asking came after the stages, or after the results were written: a commit
made during a run was recorded as the run's commit, and a script that rewrote a
tracked result recorded its own output as a dirty tree.

| Key | Meaning |
|---|---|
| `commit` | Full hash of HEAD, or `null` |
| `dirty` | `true` if any tracked file is modified, staged, deleted or renamed relative to HEAD, or if there is untracked code under `src/`, `scripts/`, `odisha_script/` or `configs/` (`untracked_code`); `false` if neither; `null` if it could not be determined. Untracked code counts since round 14 (round 13 question 30 (c)); a record written before counts tracked files only |
| `modified` | The tracked paths behind `dirty`, sorted, at most 50 |
| `modified_truncated` | `true` if there were more than 50 |
| `untracked_code` | Since round 14: the untracked code behind `dirty`, sorted, at most 50. That is every untracked, non-ignored file under `src/`, `scripts/`, `odisha_script/` or `configs/` with a source or config file's suffix (`.py`, `.sh`, `.yaml` and the like: `_CODE_SUFFIXES` in `src/fmu/utils/provenance.py`), in an untracked folder or not, and a repository inside one of those folders, by its folder (git does not list its files). A folder counts by what it holds, so a `__pycache__` folder or a folder of run outputs does not. Untracked code elsewhere (`tests/`, the top level) is in `untracked` only. The batch wrapper refuses a run tree by the same rule (`docs/running.md`) |
| `untracked_code_truncated` | `true` if there were more than 50 |
| `untracked` | Untracked, non-ignored paths, at most 50, whether they make the tree dirty or not: an untracked source file can change what ran. Until round 14 none of them made the tree dirty; since then the code among them under the four folders above does (`untracked_code`). Since round 13 (review C34) the code (source and config files, by suffix) and untracked folders come first, then the rest, each sorted, so that run outputs cannot push an untracked source file off the list; before, the list was sorted as a whole, and 50 untracked outputs in `odisha_script/phase2_vectors/` sorted before `scripts/` and `src/` |
| `untracked_truncated` | `true` if there were more than 50 |
| `root` | The checkout's root directory, or `null` |
| `error` | `null`, or why the state could not be read (git not installed, the code is not in a git checkout, a git command failed) |

### The transparency record

Each stage can declare display layers and summary numbers
(`Stage.display_layers`, `Stage.summary_numbers` and `Stage.summarise()` in
`src/fmu/stages/base.py`). The orchestrator writes them into
`stages[].transparency`, the same whether the stage ran live or was read from
the cache. Ten stages declare something today: masking, data load, the five
feature stages, segmentation, merge and clustering. Profiling, export and
metrics have an empty record (`tests/test_transparency_contract.py` lists which
stages must declare and which are still pending).

`display_layers` has one entry per declared layer:

| Key | Meaning |
|---|---|
| `key`, `band` | The context key holding the image, and the band on it |
| `bands` | Only on a colour composite (true colour, the embedding view): its three bands, as red, green and blue. `band` is the first of them. A single-band layer has no such key |
| `title`, `description` | What the layer shows |
| `vis` | Earth Engine visualisation parameters (`bands`, `min`, `max`, `palette`). `bands` is filled in from `band` or `bands` above; a declaration cannot set it. For a categorical layer the palette covers every integer from the lowest legend value to the highest. A composite has `min` and `max` and no palette. One value is not Earth Engine's: `"style": "outline"` (the superpixels) asks the reader to draw the boundaries between labels in the palette's one colour, because a label's value means nothing as a colour. `min` and `max` of a continuous layer are a starting stretch, not the range of the data |
| `legend` | For a categorical layer, one `{value, label, color}` per class; empty for a continuous layer |
| `legend_note` | What a reader must be told in order not to misread the layer. Show it wherever the legend is drawn |
| `asset` | The cache asset the layer belongs at; `null` when caching is off or the stage does not cache that key (the merge layer) |
| `asset_status` | That asset's cache status for this run. Under `"miss"` there is no asset to draw from, and under `"miss-exported"` not until the task finishes. `null` when `asset` is |

`summary_numbers` has one `{name, description, unit, value}` per declared
number. It is empty, with a reason beside it, in two cases: `summary_skipped`
when the run was made with `Pipeline(summaries=False)`, and `summary_error`
when the numbers could not be computed (the error is also in the stage's
`warnings`; the run carries on, because the stage's products are already made).

The layers each stage declares. Only masking, merge and clustering also report
numbers: a declaration costs nothing on a run, and a summary is a request to
Earth Engine on every run.

| Stage | Key | Band or bands | Drawn as |
|---|---|---|---|
| masking | `mask_provenance` | `reason`; `source` | Two categorical layers |
| data_load | `s2_composite` | `B4_median`, `B3_median`, `B2_median` | True colour, 0 to 3000 |
| features_optical | `optical_features` | `ndvi_amplitude_annual` | Continuous, 0 to 0.4 |
| features_radar | `radar_features` | `vv_minus_vh_median` | Continuous, 3 to 12 dB |
| features_structure | `structure_features` | `canopy_height`; `canopy_height_std` | Continuous, 0 to 30 m and 0 to 3 m |
| features_static | `static_features` | `elevation` | Continuous, 0 to 1500 m |
| features_embedding | `embedding_features` | `A00`, `A01`, `A02` | Colour composite of three of the 64 bands, -0.3 to 0.3 |
| segmentation | `snic_clusters` | `snic_clusters` | Outlines |
| merge | `merge_provenance` | `merge_kind` | Categorical |
| clustering | `cluster_labels` | `cluster_id` | Categorical, stand types 0 to 9 |

A declaration is fixed in the code, and three band names are not: the true
colour bands carry the compositing reducer (`median` by default), the optical
band carries the index (`ndvi` by default), and the embedding bands are
AlphaEarth's. Every config under `configs/` writes the declared bands except
two: `sanjay_van_nirv_dual`, whose optical band is `nirv_amplitude_annual`,
and `sanjay_van_tessera`, whose embedding is an uploaded Tessera image (128
channels, not AlphaEarth's 64), so the embedding layer's title, bands and
description are not those of its runs. Tests in
`tests/test_transparency_contract.py` hold both lists and fail for a third
config. The layer descriptions speak of the defaults in the same way: "by
default" in a description means the default segmentation bands and merge
criteria, which a config can replace. The stand-type legend names ten types
and a run uses the first `clustering.k` of them.

**Clustering** reports seven counts, read from the `clustering_metadata`
property of `cluster_labels` (one small request, no reduction): `k`,
`units_total`, `units_in_habitat`, `units_fitted`,
`units_dropped_missing_band`, `units_with_no_pixel_centre_in_roi` (since round
14) and `units_left_out_of_fit`. A unit is a stand, or
a superpixel in a run without merge. On a cached `cluster_labels` made before
the fit recorded its coverage, the counts are absent and the record carries a
`summary_error`. `units_left_out_of_fit` is the number of stands below
`merge.min_area_ha` left out of the fit with
`clustering.fit_excludes_stands_below_min_area` on (`n_stands_left_out_of_fit`
in `clustering_metadata`), and 0 when `clustering_metadata` does not record the
setting as on: the setting off, or an asset made before it existed. So
`units_in_habitat` is `units_fitted` plus `units_dropped_missing_band` plus
`units_with_no_pixel_centre_in_roi` plus `units_left_out_of_fit`; with the
setting on, the stage's log warns when its samples do not add up to that. On an
asset made before round 14 `units_with_no_pixel_centre_in_roi` is null and
`units_dropped_missing_band` holds both causes (below). The area of the stands
left out, and how many stands the merge marked below the minimum, are in
`clustering_metadata` (under `export_manifest_<config>.json` below), not among
these seven.

**What `units_dropped_missing_band` has counted** (review C15). Its name and its
description say: units inside the habitat mask that the fit left out because a
feature band has no data over them. In every per-step run of record
(`docs/reproducibility/r9_runs`, `round12_runs` and `round9_cache_test`) it
equals instead the number of stands with no polygon in `stands_merged`, 2 to 5
per box run and 10 in the 10 km tile: stands at the ROI's edge with no pixel
whose centre is inside the ROI (0 to 2 pixels in the merge's `stand_attributes`,
which until round 13 counted a pixel the edge cuts by its share, review B17).
The unit counts come from a frequency histogram that counts a pixel by its
share inside the ROI, so they list such a stand; the fit's one-pixel sample and
`reduceToVectors` take pixel centres inside the ROI, so it gets neither a row
nor a polygon. No stand with a band gap is among them: until round 13 the unit
means gave a unit with no data in a band 0 there, so it kept its row (round 13,
review B14). Since round 13 such a unit is masked in that band, has no row and
is counted here too, and the merge puts a superpixel with no pixel whose centre
is inside the ROI in no stand (review B17); neither has run on Earth Engine yet.
The legacy-layout runs (`docs/demo/remerge`) were not checked.

**With `clustering.fit_outside_earth_engine` on** (round 14,
`docs/configs.md`), `clustering_metadata` holds the same keys, computed off
Earth Engine on the table of units, and also `fit_outside_earth_engine` (true),
`log_rule`, `kmeans_wcss` (the best start's within-cluster sum of squares, in
the scaled space the fit used), `kmeans_starts_ari_median` and
`kmeans_starts_ari_min` (the median and lowest adjusted Rand index over the 300
pairs of the 25 starts: how much the starts agree, a diagnostic of the
clustering, not a field score) and `kmeans` (the library, the number of starts,
the seed, which start was kept and each start's sum of squares). With
`clustering.log_rule: right_skew` it holds `log1p_params` (the minimum and IQR
of each logged band) in place of `log_offsets`, `skew_before` and `skew_after`
(the skew, g1, of each band tested, before and after the log) and
`angle_pairs` (each angle's sin and cos with their IQRs and the shared spread
both are divided by). The units
without a row are counted against the rows of the table, which have data in
every candidate band; on Earth Engine they are counted against the training
rows, which need data in the active bands only, so a unit with a gap only in a
band the scaling drops as constant has a row there and none here. And a unit
with no habitat pixel centre inside the ROI, at its edge, is typed pixel by
pixel by `cluster()` on Earth Engine, though it has no row and no polygon; here
it has no row, so its pixels have no type. The run
folder holds the stage's three files (`clustering_stand_table.csv`: each unit's
label, whether it is a row of the fit, and its mean in each candidate band;
`clustering_fit_rows.csv`: the same rows after the preprocessing, with each
unit's type; `clustering_kmeans.json`: the centres and the starts).

**Since round 14 the two causes are counted apart** (round 13's question 35,
answered (a) by the round 14 brief's rule; register entry
`spec-clustering-units-dropped-counted-by-cause`). The stage counts, with an
unweighted histogram of the habitat-masked unit labels, the units with a
habitat pixel whose centre is inside the ROI. The units inside the habitat
mask without one are `n_units_no_pixel_centre_in_roi` in `clustering_metadata`
(the summary number `units_with_no_pixel_centre_in_roi`), and
`n_units_dropped_null_band` (`units_dropped_missing_band`) counts only the
units with such a pixel and no row: the band gaps. Each count is clamped at 0,
as the counts come from different reductions. On an asset made before round 14
the first is absent (the summary number is null) and the second is as recorded,
both causes together. Clustering's step revision is 5, so the clustering and
k_elbow keys of every config moved.

These counts are distinct unit labels on the analysis grid, as the fit saw
them. They are not counts of the polygons in the exported stand layer, and the
two do not agree: in the 14 re-runs of 13 Oct 2026 the exported
`stands_merged` layer holds between 4 fewer and 20 more stands than
`units_total`, and in every one of the 14 more stands with a `cluster_id` than
`units_in_habitat`
(`sanjay_van_baseline_repro`: 291 units and 257 in habitat, against 295 stands
of which 269 carry a type; `odisha_alphaearth_angul_repro`: 102 and 86, against
100 and 92). Three causes are known (`docs/demo/remerge/README.md`): a stand in
several pieces is several polygons; the export stage types a stand from the
typed pixels its polygon touches, weighted by the share of each pixel inside
it, so a stand with no habitat pixel of its own can take a neighbour's type
(so it did when these runs were made; since round 13 such a stand, which has no
row in the fit, gets a null type in every cache layout: question 1 of
`docs/handoff/2026-10-19-round12.md`, answered (b));
and the merge is not cached, so the pass that fits the types and the pass that
exports the stands each merge again, and where one of them computed a merge
criterion live they did not get the same stands (`odisha_alphaearth_angul_repro`:
the fit counted 102 stands, the run exported 97). Do not show these counts
beside a count of stands without saying so.

**Masking** declares two layers on `mask_provenance` (bands `reason` and
`source`; the codes are under "Cached GEE assets") and these numbers, from one
grouped area sum over the ROI:

| Name | Meaning |
|---|---|
| `area_ha` | Area of the ROI the mask was tabulated over |
| `share_kept` | Share of that area kept as habitat, read off `habitat_mask` |
| `share_by_reason` | Share under each reason: `kept`, `cropland`, `built_up`, `water`, `other_non_habitat`, `no_data`. Adds up to 1 |
| `share_kept_by_source` | Share of the whole area kept as habitat, by the map that decided it (`indiasat`, `worldcover`, `none`). Adds up to `share_kept` |
| `share_decided_by_source` | Share of the area each map decided, kept or removed. Adds up to 1 |
| `area_ha_by_reason_and_source` | Hectares under each reason, split by deciding map |
| `area_ha_reason_disagrees_with_habitat_mask` | Hectares where the reason layer says kept and `habitat_mask` does not, or the reverse. Zero when both come from the same inputs; anything else means the cached `habitat_mask` predates a change in a land-cover input |
| `kept_classes` | The classes this run kept as habitat, from the config: `indiasat` and `worldcover` lists |

**Merge** declares one layer, `merge_provenance.merge_kind`: each stand coloured
by the weakest kind of merge it contains.

| `merge_kind` | Meaning |
|---|---|
| 0 | A single superpixel: it merged with nothing |
| 1 | First-pass merges only: every merge passed every criterion at its configured tolerance |
| 2 | Contains a relaxed second-pass merge |
| 3 | Contains a shared-edge fallback merge, which no criterion justified |

It is a remap of the SNIC label image and is not cached, so its `asset` and
`asset_status` are `null`. The merge's numbers are read from
`merge_diagnostics` with no Earth Engine call:

| Name | Meaning |
|---|---|
| `superpixels_in`, `stands_out` | SNIC superpixels the merge started from; stands left after both passes |
| `merges_first_pass` | Merges where the neighbours pass every criterion at its configured tolerance |
| `merges_second_pass_relaxed` | Second-pass merges where a neighbour passed the relaxed tolerances |
| `merges_second_pass_shared_edge_fallback` | Second-pass merges made on shared-edge length alone |
| `stands_below_min_area` | Stands still below `merge.min_area_ha` after both passes |
| `stands_below_min_area_by_cause` | Those stands by cause: `isolated`, `area_blocked`, `iteration_cap` |
| `area_ha_in_stands_below_min_area` | Area in those stands |

The three merge counts add up to `superpixels_in - stands_out`.

### Stage source

If `stages[i].metadata.source == "cache"`, the stage was skipped entirely
because all its cacheable outputs were cached. The stage's `run()`
method didn't execute; the cached assets were loaded into the context
and the stage was marked done.

### Clustering stage metadata: unit sizes and the reduction neighbourhood (until round 13)

Recorded on every live clustering run made before round 13, including when every
check passed:

| Key | Meaning |
|---|---|
| `n_components` | Distinct unit labels in the ROI (stands, or superpixels without merge) |
| `largest_component_px` | Pixel count of the largest label |
| `max_component_px_cap` | `Config.max_component_pixels()`: the count cap the labels were checked against |
| `widest_unit_extent_px` | Widest per-label pixel-coordinate extent. The larger of the feature band-0 grid and label grid measurements |
| `rcc_neighbourhood_px` | `maxSize` actually passed to `reduceConnectedComponents`: `ceil(widest x 1.2) + 2`, never above the cap |

`rcc_neighbourhood_px == max_component_px_cap` means the measurement did not
narrow the neighbourhood. That happens with an elongated stand, or a label
reused across disjoint places, which logs a WARNING. A wide band stack may then
run out of memory, as it did before the measurement existed. These keys are in
the stage metadata only, not in `clustering_metadata`.

Since round 13 the clustering stage takes one mean per unit label with a grouped
reduction and calls `reduceConnectedComponents` no longer (review B14), so a run
records none of the five keys; manifests of earlier runs keep them. The number of
distinct unit labels is in `clustering_metadata` as `n_units_total`.

The stage metadata also holds `fit_excludes_stands_below_min_area`, true or
false, on every run that computes the clustering stage: whether the stands
below `merge.min_area_ha` were left out of the k-means fit (`docs/configs.md`,
`clustering`). A run that reads the stage from the cache records only
`source: cache` there ("Stage source" above); the setting is still in the
manifest's `config`, as `clustering.fit_excludes_stands_below_min_area`.

## `export_manifest_<config>.json` (after export stage)

A standalone copy of the export-stage's manifest. The same data is also
embedded in `manifest.json` under `stages[?(@.name=='export')].metadata.manifest`,
but the standalone file is convenient for collaborators who only need
the artifact list.

Structure:

```json
{
  "config_name": "sanjay_van_baseline",
  "pipeline_version": "1.1.0",
  "git": { "commit": "<full hash of HEAD>", "dirty": false, "...": "as in manifest.json" },
  "run_timestamp": "2026-05-20T01:35:22+00:00",
  "roi": {
    "name": "sanjay_van",
    "area_km2": 6.831,
    "geojson_path": "aois/sanjay_van.geojson"
  },
  "config_snapshot": { "...entire YAML...": "..." },
  "asset_paths": {
    "habitat_mask": "projects/.../sanjay_van_baseline/masking/habitat_mask__bbc3e3d624",
    "water_mask":   "projects/.../sanjay_van_baseline/masking/water_mask__bbc3e3d624",
    "landcover_summary": "projects/.../sanjay_van_baseline/masking/landcover_summary__bbc3e3d624",
    "mask_provenance": "projects/.../sanjay_van_baseline/masking/mask_provenance__bbc3e3d624",
    "s2_composite": "projects/.../sanjay_van_baseline/data_load/s2_composite__bbc3e3d624",
    "optical_features": "projects/.../sanjay_van_baseline/features_optical/optical_features__bbc3e3d624",
    "radar_features":   "projects/.../sanjay_van_baseline/features_radar/radar_features__bbc3e3d624",
    "structure_features": "projects/.../sanjay_van_baseline/features_structure/structure_features__bbc3e3d624",
    "static_features":  "projects/.../sanjay_van_baseline/features_static/static_features__bbc3e3d624",
    "snic_clusters":    "projects/.../sanjay_van_baseline/segmentation/snic_clusters__bbc3e3d624",
    "snic_means":       "projects/.../sanjay_van_baseline/segmentation/snic_means__bbc3e3d624",
    "cluster_labels":   "projects/.../sanjay_van_baseline/clustering/cluster_labels__bbc3e3d624",
    "feature_stack":    "projects/.../sanjay_van_baseline/clustering/feature_stack__bbc3e3d624"
  },
  "clustering": {
    "k": 6,
    "seed": 42,
    "n_training_units": 289,
    "n_units_total": 327,
    "n_units_in_habitat": 303,
    "n_units_outside_habitat": 24,
    "n_units_dropped_null_band": 14,
    "training_unit_key": "stand_clusters",
    "normalization_method": "robust",
    "skewness_threshold": 1.0,
    "log_transformed_bands": ["distance_to_water", "vh_iqr"],
    "log_offsets": { "distance_to_water": 4.234 },
    "scaling": {
      "ndvi_mean": { "center": 0.342, "spread": 0.071 },
      "elevation": { "center": 218.0, "spread": 14.0 }
    },
    "active_bands": ["..."],
    "dropped_constant_bands": ["..."],
    "raw_band_names": ["..."],
    "cyclic_decomposition_log": ["aspect", "ndvi_phase_annual"],
    "cluster_distribution": [
      { "cluster_id": 0, "pixel_count": 12431, "area_ha": 12.43, "percent_of_habitat": 18.2 },
      { "cluster_id": 1, "pixel_count": 9882,  "area_ha":  9.88, "percent_of_habitat": 14.5 }
    ]
  },
  "drive_exports": {
    "raster_cluster_labels": {
      "folder": "fmu_exports",
      "filename": "sanjay_van_baseline_cluster_labels.tif",
      "format": "GeoTIFF",
      "task_id": "ABCDEF123456",
      "submitted_at": "2026-05-20T01:35:22+00:00",
      "task_submitted": true
    },
    "raster_features_raw": {
      "folder": "fmu_exports",
      "filename": "sanjay_van_baseline_features_raw.tif",
      "format": "GeoTIFF",
      "task_id": "BCDEFG234567",
      "submitted_at": "2026-05-20T01:35:22+00:00",
      "task_submitted": true
    },
    "raster_features_scaled": {
      "folder": "fmu_exports",
      "filename": "sanjay_van_baseline_features_scaled.tif",
      "format": "GeoTIFF",
      "task_id": "CDEFGH345678",
      "submitted_at": "2026-05-20T01:35:22+00:00",
      "task_submitted": true
    },
    "vector_stands_merged_shp": {
      "folder": "fmu_exports",
      "filename": "sanjay_van_baseline_stands_merged.zip",
      "format": "SHP",
      "task_id": "ABCDEF123456",
      "submitted_at": "2026-05-20T01:35:22+00:00",
      "task_submitted": true
    },
    "vector_stands_merged_geojson":   { "...": "..." },
    "vector_stands_snic_shp": {
      "folder": "fmu_exports",
      "filename": "sanjay_van_baseline_stands_snic.zip",
      "format": "SHP",
      "task_id": "GHIJKL234567",
      "submitted_at": "2026-05-20T01:35:22+00:00",
      "task_submitted": true
    },
    "vector_stands_snic_geojson": {
      "folder": "fmu_exports",
      "filename": "sanjay_van_baseline_stands_snic.geojson",
      "format": "GEOJSON",
      "task_id": "MNOPQR345678",
      "submitted_at": "2026-05-20T01:35:22+00:00",
      "task_submitted": true
    },
    "vector_stands_dissolved_shp":    { "...": "..." },
    "vector_stands_dissolved_geojson":{ "...": "..." }
  },
  "vector_layers": {
    "stands_merged": {
      "description": "One polygon per merged stand ...",
      "n_features": 327,
      "geometry_type": "Polygon",
      "id_field": "stand_id",
      "id_renumbering": "1..N, sorted by centroid lat desc then lon asc.",
      "unclustered_stands_retained": true,
      "shp_attributes": ["stand_id", "stand_lbl", "cluster_id", "area_ha", "perim_m", "n_pixels", "n_superpx", "n_pass1", "n_relaxed", "n_fallback", "below_min", "below_why"],
      "provenance_attributes": ["n_superpx", "n_pass1", "n_relaxed", "n_fallback", "below_min", "below_why"],
      "geojson_attributes": "all SHP attributes plus per-stand means of every features_* band"
    },
    "stands_snic": {
      "description": "One polygon per SNIC superpixel ...",
      "n_features": 1529,
      "geometry_type": "Polygon",
      "id_field": "stand_id",
      "id_renumbering": "1..N, sorted by centroid lat desc then lon asc.",
      "shp_attributes": ["stand_id", "snic_label", "cluster_id", "area_ha", "perim_m", "n_pixels"],
      "geojson_attributes": "all SHP attributes plus per-superpixel means of every features_* band"
    },
    "stands_dissolved": {
      "description": "One polygon per connected same-cluster region ...",
      "n_features": 47,
      "geometry_type": "Polygon",
      "id_field": "unit_id",
      "id_renumbering": "1..M, sorted by centroid lat desc then lon asc, after min-pixel filtering.",
      "min_stand_pixels": 4,
      "shp_attributes": ["unit_id", "cluster_id", "area_ha", "perim_m", "n_pixels"],
      "geojson_attributes": "all SHP attributes plus profile_<band>_p50 columns from cluster_profiles.csv"
    }
  },
  "decisions_source": "phd-notebook/decisions.md"
}
```

> **v1.1.0 schema change:** the previous singular `drive_export` field has
> been removed; all Drive tasks are now keyed under `drive_exports` (dict).
> Past on-disk manifests are unaffected (archival), but any code reading
> `manifest["drive_export"]["task_id"]` must migrate to
> `manifest["drive_exports"]["raster_cluster_labels"]["task_id"]`.

`git` is the block described under `manifest.json`. `asset_paths` lists only
the assets that exist, so `mask_provenance` is absent until a run has exported
it. `provenance_attributes` names the merge-provenance properties on
`stands_merged`; it is empty, and `shp_attributes` has only the first six names,
when the context held no `stand_provenance`.

`clustering` is the `clustering_metadata` property of `cluster_labels`, as the
clustering stage wrote it, with `cluster_distribution` added by the export
stage. With `clustering.fit_excludes_stands_below_min_area` on it has five more
keys; with the setting off none of them is there, and the property is key for
key what it was before the setting existed:

| Key | Meaning |
|---|---|
| `fit_excludes_stands_below_min_area` | `true`: the stands the merge left below `merge.min_area_ha` were left out of the k-means training rows. They were still typed, by the nearest fitted cluster |
| `n_stands_below_min_area` | Stands the merge marked below the minimum (`below_min` 1 in `stand_provenance`), whatever the cause |
| `area_ha_in_stands_below_min_area` | Their area, from `area_ha` in `stand_attributes` |
| `n_stands_left_out_of_fit` | Those of them that had a training row, and so were left out of the fit. A stand below the minimum that lies outside the habitat mask, or has no data in an active band, had no row to leave out |
| `area_ha_in_stands_left_out_of_fit` | Their area |

With the setting on, `n_training_units` counts the rows the fit was trained on,
the stands left out not among them, and `n_units_dropped_null_band` is still
counted against every row, so the stands left out are not counted as missing
band data. Normally `n_units_in_habitat` is then `n_training_units` +
`n_units_dropped_null_band` + `n_units_no_pixel_centre_in_roi` (since round 14)
+ `n_stands_left_out_of_fit`; the stage logs a
warning when the rows of the fit and the rows of the stands left out do not add
up to the rows of every unit.

### How to use this

- **Reproduce a past run.** The `config_snapshot` is verbatim what was
  fed in. Save it as `replay.yaml`, run the pipeline against it; the
  cache asset paths derive from `config_name`, so an identical config
  with the same `name` will hit the same cache.
- **Build downstream analysis.** `asset_paths` are GEE asset references.
  Load `cluster_labels` with `ee.Image(path)` in any other GEE notebook.
- **Interpret cluster IDs.** `clustering.cluster_distribution` tells you
  the area of each cluster. `cluster_profiles.csv` (next section) tells
  you what each cluster's pixels look like in feature space.

## `cluster_profiles.csv` (after profiling stage)

One row per cluster ID. Columns:

```
cluster_id, pixel_count, area_ha,
<band1>_mean, <band1>_p25, <band1>_p50, <band1>_p75,
<band2>_mean, <band2>_p25, <band2>_p50, <band2>_p75,
...
```

Where `<band>` is each input feature band: `ndvi_mean`, `ndvi_amplitude_annual`,
`vv_p50`, `canopy_height`, `elevation`, etc.

**Critical: values are in ORIGINAL UNITS**, not the scaled values that
went into k-means. So `ndvi_mean` for a cluster is in NDVI units (the
band is the harmonic fit's intercept: with the trend term, the trend line's
value on `features_optical.time_reference`, not the mean NDVI over the
window; review C9; with `features_optical.mean_over_window` on, round 14, the
fitted curve's mean over the window); `elevation` is real meters;
`canopy_height` is real meters.
This is what makes clusters interpretable: cluster 3 might be "dense
canopy, low NDVI amplitude, high elevation". That's the ecological
interpretation, and it comes from the original-unit profiles, not the
z-scored ones.

Load in pandas:
```python
import pandas as pd
df = pd.read_csv("outputs/runs/sanjay_van_baseline_*/cluster_profiles.csv")
# Plot ndvi_mean vs canopy_height per cluster, etc.
```

## `metrics_<config>.json` (after metrics stage)

Written whenever `inspect_metrics.py` runs. The comparison fields (`ari`,
`nmi`, `correspondence`, `confusion_matrix`, `confidence_summary`) additionally
require `metrics.reference_config_name` to name another config; the
stand-geometry and explained-variance sections are always present.

```json
{
  "current_config": "sanjay_van_nirv_dual",
  "k": 6,
  "unit_key": "stand_clusters",
  "stand_geometry": {
    "unit_key": "stand_clusters",
    "n_stands": 299,
    "total_area_ha": 1301.4,
    "area_ha_min": 0.25, "area_ha_p10": 1.23, "area_ha_median": 3.39,
    "area_ha_p90": 9.49, "area_ha_max": 10.0, "area_ha_mean": 4.35,
    "stands_below_min_area": 9,
    "frac_stands_below_min_area": 0.0301,
    "area_in_undersized_stands_ha": 5.08,
    "area_share_largest_decile": 0.225,
    "polsby_popper_min": 0.08,
    "polsby_popper_median": 0.24,
    "polsby_popper_max": 0.51
  },
  "explained_variance": {
    "n_stands": 269,
    "unit_key": "stand_clusters",
    "level": "pixel",
    "attributes": {
      "canopy_height":     { "r2": 0.926, "held_out": false, "ss_within": 1.2e5, "ss_total": 1.6e6, "n_pixels": 84190 },
      "ndvi_trend":        { "r2": 0.581, "held_out": true,  "ss_within": 3.4e2, "ss_total": 8.1e2, "n_pixels": 84190 },
      "canopy_height_max": { "r2": 0.712, "held_out": true,  "ss_within": 2.9e5, "ss_total": 1.0e6, "n_pixels": 84190 }
    }
  },
  "merge": {
    "n_superpixels": 1298, "n_stands": 299, "reduction_factor": 4.341,
    "pass1_rounds": 6, "pass1_merges": 762,
    "pass2_iterations": 2, "pass2_merges": 237, "pass2_fallback_merges": 126,
    "stands_below_min_area": 9,
    "orphans_isolated": 0, "orphans_area_blocked": 9,
    "orphans_no_attribute_match": 0,
    "stands_with_incomplete_criteria": 97,
    "adjacency": { "n_regions": 1298, "n_edges": 3615, "mean_degree": 5.57, "n_isolated": 0 },
    "threshold_calibration": { "joint_admit_rate_pct": 45.2, "per_band": { "...": "..." } },
    "warnings": ["..."]
  },
  "silhouette_current": 0.4127,
  "silhouette_reference": 0.3892,
  "reference_config": "sanjay_van_baseline",
  "ari": 0.6512,
  "nmi": 0.7234,
  "agreement_rate": 0.781,
  "n_samples_used": 9847,
  "correspondence": { "0": 2, "1": 4, "2": 0, "3": 5, "4": 1, "5": 3 },
  "confusion_matrix": [
    [3201,   12,  178,   34,    9,   22],
    [  44, 2876,    8,   91,   12,   17]
  ],
  "confidence_summary": {
    "mean": 0.842,
    "frac_area_ge_high": 0.713,
    "high_threshold": 0.8
  }
}
```

The `merge` block and the size numbers of `stand_geometry` in this example are the demo
set's: Sanjay Van, hand-crafted features, the Earth Engine run of 13 Oct 2026, with the
stands re-merged under `spec-merge-pass2-skip-at-minimum` (`docs/demo/remerge/`). Before
the re-merge the same run had 291 stands. The other numbers in the example (shape, explained
variance, silhouette, the comparison with a reference) are illustrative and from an earlier
run, so the blocks do not describe one run. The demo set carries the open cache-grid issue
(`docs/reproducibility.md`, "Superpixels depend on whether the features were cached when
SNIC ran").

### Interpreting the numbers

| Field | Meaning | Range / direction |
|---|---|---|
| `unit_key` | Which label image everything was reduced over: `stand_clusters` when merge ran, `snic_clusters` when `merge.enabled: false`. **A silhouette over stands and a profile over superpixels are not comparable, and no other number in this file would reveal the difference** | string |
| `stand_geometry` | Distribution of the thing the pipeline produces. See below | object |
| `stand_geometry.area_share_largest_decile` | Fraction of total area held by the largest 10% of stands. The concentration check — a mean or median hides both failure modes (thousands of slivers; a handful of blobs holding the landscape). The layer this replaced scored ~0.68 | 0 to 1; lower is more even |
| `stand_geometry.polsby_popper_*` | Shape compactness `4πA/P²` from the **raster** boundary. Comparable between stands at the same scale; **not** comparable to a published vector-derived figure, since a staircase boundary is longer than the shape it approximates | 0 to 1 |
| `explained_variance.attributes.<band>.r2` | `1 − SS_within/SS_total` over raster cells within stands (Xiong et al. 2024 Eq. 4–6). The headline | -inf to 1; higher is better |
| `explained_variance.attributes.<band>.held_out` | `false` = this attribute helped draw the boundaries, so R² on it is partly circular — reported because it is what the literature quotes, **not as evidence**. `true` = neither segmentation nor merge used it. Checked at config load, not trusted | bool |
| `explained_variance.n_stands` | **Read every R² against this.** R² rises monotonically with stand count and is 1.0 in the limit of one stand per pixel, so two arms at different stand counts cannot be compared on it | int |
| `explained_variance.level` | Always `"pixel"`. Scoring at region level makes any partition score 1.000 by construction | string |
| `merge.orphans_area_blocked` | Undersized stands whose every neighbour is already too big to absorb them under the ceiling: `merge.max_area_ha`, or `merge.max_area_ha + merge.min_area_ha` with `merge.pass2_soft_ceiling` on. **A signal `max_area_ha` is too tight**, not a fact about the forest | int |
| `merge.pass2_fallback_merges` | Pass-2 merges no relaxed criterion could justify, decided by shared-edge length alone. The honest count of "surrounded by genuinely different forest"; look here first if stand geometry looks wrong | int |
| `merge.pass2_relaxed_merges_over_max_area`, `merge.pass2_fallback_merges_over_max_area` | Present only when `merge.pass2_soft_ceiling` is on, like the five keys below. Pass-2 merges that took a region over `merge.max_area_ha`: by a relaxed match (step 2 of the order of choice, part of `pass2_merges - pass2_fallback_merges`) and by the shared-edge fallback (step 4, part of `pass2_fallback_merges`). Whether a merge goes over is decided as the hard ceiling decides it, in whole pixels (the two regions' pixels added, against `merge.max_area_ha` in pixels; review B18), so a merge that ends exactly on `merge.max_area_ha` is not over it and is counted neither here nor in `stands_over_max_area` | int |
| `merge.stands_over_max_area` | Stands whose area as reported in `stand_attributes` (`area_ha`, 6 decimals) is over `merge.max_area_ha` taken to the same 6 decimals, so a stand exactly at `merge.max_area_ha` is not counted. None is over `merge.max_area_ha + merge.min_area_ha` unless it is a single superpixel that came in larger | int |
| `merge.stands_over_max_area_never_merged` | Of `stands_over_max_area`, those made of a single superpixel (`n_superpx` 1): a superpixel that came in larger than `merge.max_area_ha` and that nothing joined. The setting did not make them, and with it off they are over `merge.max_area_ha` too, unreported. The rest were made by merging, which only the setting allows past `merge.max_area_ha` | int |
| `merge.excess_over_max_area_total_ha`, `merge.excess_over_max_area_largest_ha` | Those stands' area over `merge.max_area_ha`, added up, and the largest of them (0.0 when no stand is over), rounded to 4 decimals | ha |
| `merge.excess_over_max_area_each_ha` | Each of those stands' area over `merge.max_area_ha`, largest first, rounded to 4 decimals (so an excess under 0.00005 ha shows as 0.0) | list of ha |
| `merge.threshold_calibration.joint_admit_rate_pct` | Share of adjacent pairs the gate admits, of the `n_pairs_with_any_defined_criterion` pairs with at least one criterion defined on both sides: every criterion defined on both sides within its tolerance, and at least `merge.min_defined_criteria` of them defined. The gate is conjunctive, so the per-band marginals do not describe it. **Not a tuning target** — pass rate is a diagnostic, and pass 1 iterates to convergence so a per-round rate is not the share of total merging. Since 20 Oct 2026 (round 13, review C14): before, a pair with fewer than `merge.min_defined_criteria` criteria defined that passed the ones it had was counted as admitted, though the gate rejects it. Every committed record is from before the fix. Its rate is above the fixed one by at most `pass1_pairs_blocked_by_undefined_criteria_round1` plus `pass1_pairs_blocked_by_area_round1` over `n_pairs_with_any_defined_criterion`, from the same record: 0 (the same rate) in 83 of the 122 committed records under `docs/reproducibility/`, `odisha_script/phase2_vectors/` and `ui_data/`, and at most 0.38 points in the others; `odisha_script/gate_effect_results.txt` overstates by up to 8.97 and 10.19 points (its dated note) | 0 to 100 |
| `merge.kept_land` | Present only when `segmentation.mask_before_snic` is on, and then SNIC and the merge see only kept land: where `habitat_mask` is 1, inside the ROI (the mask on the analysis grid clipped to the ROI as the stage's outputs are), less, with `segmentation.drop_kept_patches_below_min_area`, each patch smaller than `merge.min_area_ha` that touches no other kept land. `kept_land_ha`: that land, in the ROI. `small_patches_ha`: land `habitat_mask` keeps but left out as patches below the minimum (0 without the option). `kept_land_ha_without_superpixel`: kept land SNIC left with no superpixel, so in no stand; the seeds of `fmu.utils.kept_land` should make it 0. `superpixel_ha_off_kept_land`: superpixel area off kept land, 0 against the mask SNIC read. Both shortfalls are measured against the mask the merge reads, on the superpixel image's own pixels; if SNIC ran on the mask computed live and the merge reads the cached copy, the two differ a little along the edges of kept land (`docs/reproducibility.md`, "Superpixels depend on whether the features were cached when SNIC ran"), which gives a little of both. Areas are pixel count × scale² | ha; both shortfalls should be 0 |
| `silhouette_current` | Intrinsic cohesion/separation of current clustering. **Demoted to an internal diagnostic for the labelling step**: it is computed in each arm's own feature space (21-D vs 64-D) and is strongly dimensionality-dependent, so it was never valid across arms, and under two independent segmentations it is doubly invalid | -1 to 1; higher is better |
| `silhouette_reference` | Same for the reference (only if reference's `feature_stack` is cached) | -1 to 1; higher is better |
| `ari` | Adjusted Rand Index between current and reference partitions | -1 to 1; 0 = random, 1 = identical |
| `nmi` | Normalized Mutual Information | 0 to 1; higher = more information shared |
| `agreement_rate` | After Hungarian-matching cluster IDs, fraction of pixels that agree | 0 to 1; higher = more agreement |
| `correspondence` | Best mapping: `current_id -> reference_id` (Hungarian on confusion matrix) | k mappings |
| `confusion_matrix` | k x k pixel-overlap counts (rows = current, cols = reference) | non-negative ints |
| `n_samples_used` | Number of paired pixels used for ARI/NMI | int (target was `metrics.n_comparison_samples`) |
| `confidence_summary` | Scalar roll-up of the per-stand `confidence` image (see below). Comparison mode only; absent in baseline mode | object (fields below) |
| `confidence_summary.mean` | Area-weighted mean per-stand confidence | 0 to 1; `null` if unavailable |
| `confidence_summary.frac_area_ge_high` | Fraction of habitat area sitting in high-agreement stands (per-stand confidence >= `high_threshold`) | 0 to 1; `null` if unavailable |
| `confidence_summary.high_threshold` | Cutoff that defines a "high-agreement" stand | fixed at `0.8` |

**How to read explained variance (the headline):** compare the `held_out: true`
rows, at matched `n_stands`. The `held_out: false` row exists so the number can
be set beside published figures (Xiong et al. 2024 report 81.80% on mean canopy
height; Jia et al. 2019 84.7–94.2%; Sun et al. 2021 >80%; Pukkala 2018 66–87%),
not as evidence about this partition — canopy height is a merge criterion, so
R² on it is partly circular by construction. Explained variance rises as stands
get smaller whatever the layer; see `docs/evaluation_metrics.md`, section 3.1.

**How to read silhouette:** values around 0 indicate overlapping
clusters; values approaching 1 indicate well-separated, tight clusters.
A difference of 0.05 between variants is meaningful when the AOI is
heterogeneous; differences below 0.01 are noise. **Do not compare it across
arms** — see the field table above.

**On ARI/NMI across arms:** these compare label partitions over a *shared*
support. Once two arms segment independently they no longer share one, so the
numbers stop meaning what they mean between two runs of the same tessellation.
They remain valid for comparing two clusterings of the same stand map (a seed
sweep, a `k` sweep).

**How to read ARI:** ARI = 0.65 means current and reference agree on
about 65% of pairwise pixel relationships (after correcting for
random-chance agreement). For two clusterings of the same AOI with the
same k, ARI > 0.7 is "very similar partitions"; ARI < 0.4 is "the two
clusterings disagree substantially".

**How to read NMI:** NMI = 0.72 means the two clusterings share ~72%
of the information about which pixels go together. NMI > ARI usually
because NMI doesn't penalize size mismatches between clusters.

**How to read the correspondence:** `{"0": 2, ...}` means "current
config's cluster 0 best matches reference config's cluster 2 in terms
of pixel overlap." The agreement_rate is computed AFTER this remapping;
it answers "if we relabel current's clusters to match reference's,
what fraction of pixels end up with the same label?"

### The `confidence` and `agreement_map` images (comparison mode)

Alongside the JSON scalars, the metrics stage produces two server-side
images as context outputs (not files on disk): an `agreement_map` (per
pixel: `1` where the two configs' Hungarian-aligned labels match, `0`
where they differ) and a per-stand `confidence` image. `confidence` rolls
the agreement map up to SNIC superpixels (`reduceConnectedComponents`
mean), so every stand carries a single value: the **fraction of its
pixels that agree with the reference**, 0..1. Both are `None` in baseline
mode (there is no reference to compare against), which is why
`confidence_summary` is absent from the JSON there too.

Read `confidence` as **consensus / stability, not correctness**: there is
no ground-truth stand map to score against. High values mark stands whose
boundary is robust to the choice of feature source (handcrafted vs.
embedding); low values flag stands that should be read with caution. The
`confidence_summary` fields above summarise this image, and
`inspect_metrics.py` emits GEE Code Editor JS that renders it as a
red-to-green layer.

## The raster GeoTIFFs (in Google Drive)

The export stage submits three GeoTIFF exports to your Drive:

- **Folder:** `fmu_exports/`
- **Filenames:**
  - `<config_name>_cluster_labels.tif` — single-band `uint8` cluster-label
    map. **Values:** `0` to `k-1` (cluster IDs), with masked (non-habitat)
    pixels having the default uint8 nodata.
  - `<config_name>_features_raw.tif` — every feature band in **original
    units** (metres, dB, NDVI, ...) plus a `cluster_id` band. Multiband
    float; human-readable / GIS-ready.
  - `<config_name>_features_scaled.tif` — the preprocessed `feature_stack`
    exactly as k-means saw it (log/robust-scaled, cyclic-decomposed) plus a
    `cluster_id` band. Multiband float.
- **Projection:** EPSG:4326 (GEE's default for export to Drive)
- **Pixel scale:** `export.analysis_scale_m` (default 10 m)

Submit-and-forget. The task IDs are in the manifest. Monitor progress at
https://code.earthengine.google.com/tasks. Typical wait: 5-15 min each.

### Loading in Python

```python
import rasterio

# Cluster-label map: single band, uint8
with rasterio.open("sanjay_van_baseline_cluster_labels.tif") as src:
    labels = src.read(1)              # numpy array, shape (H, W), dtype uint8
    bounds = src.bounds
    transform = src.transform

# Feature rasters (features_raw / features_scaled): multiband float,
# one band per feature plus a cluster_id band
with rasterio.open("sanjay_van_baseline_features_raw.tif") as src:
    stack = src.read()                # shape (n_bands, H, W)
    band_names = src.descriptions     # feature band names, incl. "cluster_id"
```

### Loading in QGIS

Drag-drop the `cluster_labels` `.tif`. Right-click, Properties, Symbology,
Singleband pseudocolor, discrete. Build a color ramp with k stops. Use
`cluster_profiles.csv` to label each cluster by its dominant feature
(e.g., "dense canopy", "edge", "open vegetation").

## Vector outputs (in Google Drive)

The export stage emits three vector layers, each in every format listed in
`export.vector_formats` (default both SHP and GeoJSON). SHP files arrive
zipped (GEE bundles the .shp/.shx/.dbf/.prj). GeoJSON files are single
text files.

| Layer | Filename pattern | What it is |
|---|---|---|
| **stands_merged** | `<config>_stands_merged.{zip,geojson}` | One polygon per merged stand. **The deliverable** — the unit SNIC + merge delineate. |
| **stands_snic** | `<config>_stands_snic.{zip,geojson}` | One polygon per SNIC superpixel. Debugging / methodology layer, and the pre-merge side of a pre/post comparison. |
| **stands_dissolved** | `<config>_stands_dissolved.{zip,geojson}` | One polygon per connected same-cluster region. Kept for continuity with the pre-merge outputs; superseded by `stands_merged`. |

`stands_merged` is written only when `merge.enabled`. Without merge the
stand *is* the superpixel, so the layer would duplicate `stands_snic`
exactly, and the stage logs a skip instead.

**Which layer to use.** `stands_merged` is the stand map. `stands_dissolved`
is not: dissolving by cluster id merges every same-type region that happens
to touch, whatever its extent, which is how a committed pre-merge run ended
up with 6% of units holding 68% of the area. It remains in the export so
old and new runs stay comparable, not because it is a second answer.

For a typical Sanjay Van run: ~330 merged stands, ~1,200 SNIC polygons,
~460 dissolved polygons. All three layers in EPSG:4326.

**Areas and pixel counts.** Since round 13 (review A6) `n_pixels` is each
polygon's pixel count at the analysis scale, the `count` `reduceToVectors`
gives it, and `area_ha` is that count × `analysis_scale_m`² / 10,000: the area
on the analysis grid. Until then both came from the geometry's area
(`n_pixels` = area / `analysis_scale_m`²), and Earth Engine's `area()` adds
instead of subtracting the hole of some polygons whose hole touches the outer
ring at a vertex (`sanjay_van_alphaearth_keptland_r9`, stand 83: 18.27 ha and
1,827 pixels in its layer, 8.23 ha and 823 pixels on the grid); the layers
exported before round 13 carry those values. `perim_m` is the geometry's, and
right on those polygons. Since round 14 (round 13's question 21, answered (a))
`centroid_lat` and `centroid_lon` are the mean position of the polygon's pixel
centres: the same `reduceToVectors` call that counts the pixels averages
`ee.Image.pixelLonLat()` over them. Until then the centroid was the geometry's,
which has the same hole error as the area: it is the centroid with the hole
counted as area (up to 35 m off on the committed merged layers of `_r9` and round
12, where 54 of 7,371 centroids are more than 1 m off; stand 83 above, 35.1 m,
whose 823 pixel centres average to within 1 cm of its centroid with the hole
subtracted). `stand_id` and `unit_id` are numbered by the centroid, so in the
layers exported before round 14 a few ids follow the error, and a layer exported
since can number a few polygons differently from an earlier export of the same
geometry (numbered by their pixel centres, 88 of the 14,371 polygons of the
merged layers of `_r9` and round 12 would take another `stand_id`; register
entry `spec-export-centroid-from-pixel-centres`). On the legacy cache layout `stands_dissolved` is vectorised from a
type image on a geographic grid, whose pixels are smaller than
`analysis_scale_m`² away from the equator (about 93 m² at 10 m and 21° N), so
there its `area_ha` overstates the area (by about 7.5% at 21° N).

**Stands and superpixels in pieces** (review C17). A stand or a superpixel can
come out as more than one polygon, so a layer can hold more polygons than
stands. SNIC labels every pixel the ROI clip keeps, those the ROI only partly
covers at its edge included, while `reduceToVectors` keeps only the pixels whose
centre is inside the ROI; a label drawn through such edge pixels is then cut. In a
large ROI a label can also have a stray piece of a few pixels against a line a
multiple of 256 pixels from the ROI's south-west pixel corner, which the review
reads as a line between Earth Engine's computation tiles. In the layers of the
per-step runs of record (`docs/reproducibility/r9_runs` and `round12_runs`,
committed or off git with their SHA-256 checked), 0 to 7 stands and 0 to 14
superpixels per run are in more than one polygon: two, but for one superpixel in
three in each of the 10 ha hand-crafted runs of Dhenkanal and Kendujhar. Every
smaller piece lies within 5.2 m
of the ROI's edge, but the stray pieces, of 1 to 41 pixels, of 4 superpixels and
2 stands in the 10 km tile and of 1 superpixel in each of three AlphaEarth layers
(Dhenkanal 3 ha, Koraput 3 ha and 10 ha). The kept-land checks that found no
superpixel in pieces (register entry `spec-segmentation-mask-before-snic`)
counted pieces on the label raster, which still holds those edge pixels. The
joins key on `stand_lbl`, so no score changes. A stand with no pixel whose
centre is inside the ROI gets no polygon at all (2 to 10 per run; "What
`units_dropped_missing_band` has counted", above).

### Attribute schemas

#### `stands_merged`

SHP attributes (capped at 10-char field-name limit):

| Field | Type | Meaning |
|---|---|---|
| `stand_id` | int | Sequential 1..N. Sorted by centroid lat desc / lon asc, the centroid being the mean of the polygon's pixel centres since round 14 (see "Areas and pixel counts" above). **Deterministic** — the same merged geometry always produces the same numbering. |
| `stand_lbl` | int | Raw merge label. Use to cross-reference with the `stand_clusters` raster. `stand_id` is a renumbering and cannot be joined back to the raster; this can. |
| `cluster_id` | int | The k-means cluster (0 to k-1) assigned to this stand: the commonest type over the stand's own typed pixels, which on the analysis grid is the type the fitted clusters give its row (since round 12; for a stand whose pieces carry different types, see question 3 of `docs/handoff/2026-10-19-round12.md`). Since round 13 this holds for a stand left out of the fit too (`clustering.fit_excludes_stands_below_min_area`), and a stand with no typed pixel of its own has a null type; until then both took the commonest type among the typed pixels their polygon touches. **May be null** — see below. |
| `area_ha` | float | Polygon area in hectares on the analysis grid: `n_pixels × (analysis_scale_m)² / 10,000` (since round 13; see "Areas and pixel counts" above). |
| `perim_m` | float | Polygon perimeter in metres. |
| `n_pixels` | int | The polygon's pixels at the analysis scale: the `count` `reduceToVectors` gives it (since round 13; until then `area_m² / (analysis_scale_m)²` from the geometry's area). |
| `n_superpx` | int | Superpixels the stand is made of (1 = it never merged). |
| `n_pass1` | int | Merges inside the stand made by the first pass: every criterion within its configured tolerance. |
| `n_relaxed` | int | Merges inside the stand made by the second pass under tolerances multiplied by `merge.relax_factor`. |
| `n_fallback` | int | Merges inside the stand made by the second pass's shared-edge fallback: no criterion justified them, even relaxed. These are the merges to look at first. |
| `below_min` | int (0/1) | 1 if the stand ended below `merge.min_area_ha`. |
| `below_why` | string | Empty unless `below_min` is 1; then `isolated` (shares no edge with another stand: no 4-connected neighbour in the merge's graph, so a stand that meets another only at a corner is isolated too; corrected 20 Oct 2026, review C16, from "touches no other stand"), `area_blocked` (every neighbour is too big to take it under `merge.max_area_ha`, or under `merge.max_area_ha + merge.min_area_ha` with `merge.pass2_soft_ceiling` on) or `iteration_cap` (it still had a neighbour it could have joined when the second pass stopped at `merge.max_pass2_iterations`). |

The last six are the merge provenance (`PROVENANCE_FIELDS` in
`src/fmu/utils/region_merge.py`). A stand of m superpixels contains exactly
m - 1 merges, so `n_pass1 + n_relaxed + n_fallback = n_superpx - 1`. Over all
stands the counts add up to the totals in `merge_diagnostics`. The values are
looked up by `stand_lbl`, so every polygon of a stand that was split into
pieces carries the same values. Both formats carry all six; in the shapefile
they follow the six columns above. Unless `merge.pass2_skip_at_min_area` is
true, a second-pass merge does not always add a piece that was below the minimum
size at that moment: each sweep lists the undersized pieces once, and a piece
that reaches the minimum earlier in a sweep still takes its turn in that
sweep. With the setting on, such a piece is skipped (register entry
`spec-merge-pass2-skip-at-minimum`). With `merge.pass2_soft_ceiling` on, a piece
still below the minimum when its turn comes may join a neighbour even if the
stand is then over `merge.max_area_ha`, up to `merge.max_area_ha +
merge.min_area_ha` (register entry `spec-merge-pass2-soft-ceiling`). Such a
merge is counted in `n_relaxed` or `n_fallback` like any other second-pass
merge; `merge_diagnostics` says how many there were, and how many stands ended
over `merge.max_area_ha` and by how much. The layer is written without the six
(and the stage logs a warning) only when the context holds no
`stand_provenance`, which a pipeline run always does.

The same per-stand table, with `area_ha`, `n_pixels` and the `merge_kind` code
of the display layer, is what `scripts/inspect_merge.py` writes to the run
directory as `merge_provenance.csv` and `merge_provenance.json`: one row per
stand in `stand_lbl` order, results only (no times or dates). The JSON also
carries the config name, the cache fingerprint, the merge summary numbers, the
stand-size distribution and the stands and area under each `merge_kind`.

GeoJSON attributes: every SHP attribute, **plus** per-stand means of every
features_* band, plus `centroid_lat` and `centroid_lon` (the mean position of
the polygon's pixel centres since round 14, the geometry's centroid before; see
"Areas and pixel counts" above). Each feature mean is the plain mean of the band's
pixel values over the polygon (`ee.Reducer.mean()` in `reduceRegions`), the
angle bands too: `aspect` (degrees, 0 to 360) and `<index>_phase_annual`
(radians, −π to π; `<index>_phase_semi` too in a dual-harmonic run) are
arithmetic means of angles, not circular means. So a stand whose pixels face
350° and 10° reads 180°, and one whose phases lie on both sides of ±π reads near
0 (review C10). The clustering does not read these columns: it takes the sine
and cosine of each angle per pixel. The export is unchanged; whether it should
give circular means is a question for Jaskaran (round 13).

**Null `cluster_id` is meaningful, not missing data.** Unlike `stands_snic`,
this layer keeps stands that clustering could not type. Under the merge
design SNIC + merge produce the stand and clustering only attaches a type
label to a finished one, so a stand without a label is still a stand —
dropping it would delete real delineated area from the deliverable while
leaving the file looking complete. Two reasons a stand is untyped: it lies
outside the habitat mask, or at least one active feature band has no data
over it. The clustering stage logs the split, and the counts are in the run
manifest as `n_units_outside_habitat` and `n_units_dropped_null_band`. In the
runs of record the second counted stands at the ROI's edge with no polygon, not
stands with a band gap ("What `units_dropped_missing_band` has counted", above;
review C15); since round 14 those stands are `n_units_no_pixel_centre_in_roi`
and the second counts the band gaps only. Note
that SHP cannot represent a null integer — read the GeoJSON if you need to
tell null from 0. Such a stand has no row in the k-means fit, and since round 13
its type is null in every cache layout, whatever typed pixels its polygon
touches (question 1 of `docs/handoff/2026-10-19-round12.md`, answered (b);
register entry `spec-export-stand-type-from-its-own-row-or-null`). Until then it
kept the commonest type among the typed pixels its polygon touches: null on the
analysis grid (every run since round 9), but on the legacy cache layout, where
the types lay on another grid, its polygon could take in slivers of a
neighbour's pixels and so a neighbour's type (`docs/demo/remerge/README.md`,
section 4). On the legacy layout the stand's own pixels are those whose centres
it holds on the type grid, so a stand with a row in the fit that holds none has
a null type too.

#### `stands_snic`

SHP attributes (capped at 10-char field-name limit):

| Field | Type | Meaning |
|---|---|---|
| `stand_id` | int | Sequential 1..N. Sorted by centroid lat desc / lon asc, the centroid being the mean of the polygon's pixel centres since round 14. **Deterministic** — same SNIC geometry always produces the same numbering. Use as a stable ID across runs of the same config. |
| `snic_label` | int | Raw SNIC superpixel hash. Use to cross-reference with the `snic_clusters` raster asset. |
| `cluster_id` | int | The k-means cluster (0 to k-1) that this superpixel was assigned to. |
| `area_ha` | float | As in `stands_merged`: `n_pixels × (analysis_scale_m)² / 10,000` (since round 13). |
| `perim_m` | float | Polygon perimeter in metres. |
| `n_pixels` | int | As in `stands_merged`: the `count` `reduceToVectors` gives the polygon (since round 13). |

GeoJSON attributes: every SHP attribute, **plus** per-superpixel means
of every features_* band (ndvi_mean, ndvi_amplitude_annual, vv_p50,
canopy_height, elevation, etc.) — typically 25-30 additional columns.
The angle bands (`aspect`, `<index>_phase_*`) are arithmetic means of angles
here too, as in `stands_merged` (review C10).
Centroid lat/lon are also included for convenience: the mean position of
the polygon's pixel centres since round 14, as in `stands_merged`.

#### `stands_dissolved`

SHP attributes:

| Field | Type | Meaning |
|---|---|---|
| `unit_id` | int | Sequential 1..M, after `vector_min_stand_pixels` filtering. Same lat-desc/lon-asc renumbering as stand_id; deterministic. |
| `cluster_id` | int | The k-means cluster ID this unit corresponds to. |
| `area_ha` | float | As in `stands_merged` (since round 13; on the legacy cache layout see "Areas and pixel counts" above). |
| `perim_m` | float | Polygon perimeter in metres. |
| `n_pixels` | int | As in `stands_merged` (since round 13). Used by the min-pixel filter. |

GeoJSON attributes: every SHP attribute, **plus** `profile_<band>_p50`
columns for every feature band, looked up from `cluster_profiles.csv`
by `cluster_id`. These are the per-cluster medians in original units,
so e.g. `profile_canopy_height_p50` = median canopy height (in metres)
of pixels in this unit's cluster.

### Why both layers

The two layers serve different audiences. `stands_snic` is for the
researcher: every polygon traces back to a SNIC label and carries the
exact feature vector that fed clustering. `stands_dissolved` is for the
end user (forester, manager): one polygon per real-world management
unit, with cluster-level summary statistics attached for symbology.

### Renumbering caveat

Both layers carry a sequential id (`stand_id`, `unit_id`) that is
**deterministic but not stable across config changes**. If you change
SNIC parameters, the superpixel boundaries shift, centroids shift, and
the numbering changes. Nor across the round 14 change of centroid (the
mean of the pixel centres in place of the geometry's): a layer exported
since numbers a polygon whose old centroid was off, and those it passes
in the order, differently from an earlier export of the same geometry.
Use `snic_label` (raw SNIC hash) for stable
cross-run reference within the same SNIC configuration, and the
sequential IDs for display / printable maps where 1..N is more
readable than the raw hash.

### Loading in Python

```python
import geopandas as gpd
gdf = gpd.read_file("sanjay_van_baseline_stands_dissolved.geojson")
gdf.plot(column="cluster_id", categorical=True, legend=True)
```

### Loading in QGIS

For SHP: unzip first, then drag the `.shp` in. For GeoJSON: drag in
directly. Symbolize by `cluster_id` (categorical). For the dissolved
layer, use `profile_<band>_p50` columns to construct labels like "high
canopy / low elevation" per cluster.

### SHP attribute caveat

SHP's 10-char field-name limit means **only the SHP-safe subset** above
is in the .dbf. GEE would otherwise truncate longer names and risk
collisions. If you need the full attribute schema, use the GeoJSON
output instead.

## Cached GEE assets

Persistent across runs. Located at:

```
projects/<your-gcp-project>/assets/fmu/<config_name>/<stage_name>/<output_key>__<fingerprint>
```

`<fingerprint>` is a 10-character hash of the config *contents* — see
`config_fingerprint()` in `src/fmu/utils/caching.py`. That is the legacy layout,
of every run before round 9 (17 Oct 2026). A config run since, with no asset of
that layout, uses the per-step one: `<output_key>__s<step key>`, one key per
step, and its assets are on the analysis grid ([running.md](running.md#the-cache-layer)). It exists because the
path used to be name-only, so editing a threshold and re-running the same
config silently reused the old asset. Two runs of the same config name with
different parameters now get different assets.

Practical consequence: **editing almost any config block invalidates that
config's cached assets and they will be recomputed.** Changes that cannot
affect a raster do not — `name`, `description`, the whole `metrics` block, and
the output-plumbing half of `export` (Drive folder, formats, which layers to
emit). `export.analysis_scale_m` does invalidate, since it governs every
reduction.

Listed in `export_manifest_<config>.json` under `asset_paths`. Load any
of them in another GEE script via `ee.Image(path)`.

Which assets exist depends on the config, not on a fixed list. An
embedding-arm run has no `features_radar` or `features_static` asset and does
have `embedding_features`; it still has `features_optical` and
`features_structure`, because the merge criteria read them and the merge rule
is held identical across arms. The `merge` stage caches nothing at all — its
`stand_clusters` output is a `remap` of a cached image, cheap to rebuild, and
caching it would need the merge thresholds hashed into the key when those
thresholds are exactly what a run is iterating on. The same holds for its
`merge_provenance` image (band `merge_kind`, another remap of the SNIC labels);
`stand_provenance` is a Python dict and is not an asset at all.

`mask_provenance` (masking stage) says why each pixel is in or out of
`habitat_mask`. Two `uint8` bands:

| Band | Code | Meaning |
|---|---|---|
| `reason` | 0 | No land-cover data in either map (not habitat) |
| | 1 | Kept as habitat |
| | 2 | Removed: cropland |
| | 3 | Removed: built-up |
| | 4 | Removed: water |
| | 5 | Removed: other non-habitat (every remaining class) |
| `source` | 0 | Neither map has data |
| | 1 | IndiaSAT decided |
| | 2 | WorldCover decided (IndiaSAT has no data) |

`reason == 1` exactly where `habitat_mask == 1`, by construction. A pixel
IndiaSAT removed takes the reason of its most recent non-habitat year. The layer
is derived beside the mask and never feeds it. The code-to-name tables are also
in the masking stage's `metadata` as `mask_provenance_reason_codes` and
`mask_provenance_source_codes`.

`mask_provenance` was added after the other three masking outputs had been
cached for the configs run so far. For such a config the next cached run reads
those three back, computes `mask_provenance` live and (unless
`submit_exports=False`) exports only it; downstream stages keep receiving the
cached `habitat_mask`. The summary number
`area_ha_reason_disagrees_with_habitat_mask` is the check on that pairing.

Special property on `cluster_labels`: the asset carries a JSON-encoded
`clustering_metadata` property listing every preprocessing parameter
used to produce it (log offsets, scaling params, dropped bands, etc.).
The export stage reads it back to populate the manifest's `clustering`
section. To read it from a separate GEE script:

```python
import ee
import json
labels = ee.Image("projects/.../sanjay_van_baseline/clustering/cluster_labels__<fingerprint>")
meta = json.loads(labels.get("clustering_metadata").getInfo())
print(meta["scaling"])           # per-band center/spread
```

## What's NOT an output

- Intermediate `ee.ImageCollection` objects (`s2_collection`, `s1_collection`).
  They're cheap to rebuild and not cacheable as single assets.
- Stage `metadata` dicts whose values are not JSON-serializable.
  `_json_safe` in pipeline.py falls back to `str()` for unknown types.
  This means a `metadata` value that's an `ee.Image` will appear as a
  string in `manifest.json`, not a usable reference. Use `asset_paths`
  for that.
- The `feature_stack` is cached as a GEE asset, but it's the *preprocessed*
  feature stack (post-log-transform, post-scaling). It's not directly
  human-interpretable. Use it for downstream ML, not visualization.

## Reports (`scripts/report.py`)

A mentor-facing report is generated *from* the artifacts above — no Earth
Engine access needed. Install the extra (`pip install -e ".[report]"`;
matplotlib + shapely, numpy/pandas are already core) and run:

```bash
# single config
python scripts/report.py --config sanjay_van_baseline
# with the baseline-vs-variant comparison
python scripts/report.py --config sanjay_van_nirv_dual --reference sanjay_van_baseline
```

It discovers `cluster_profiles.csv`, `export_manifest_<config>.json`, and
`metrics_<config>.json` under `runs/<config>_*/`, plus the exported
`stands_dissolved` / `stands_snic` vectors under `fmu_exports_clean/`, and
writes to `reports/<config>/`. **All three of those directories are local and
gitignored** — populate them by running the pipeline and
`scripts/fetch_drive_vectors.py` before running `report.py`:

- **PNG figures** — stand map, cluster fingerprint (z-scored heatmap),
  feature separating-power, stand composition, per-stand phenology curves,
  and structural / terrain / radar signatures.
- **`report.html`** — a single self-contained dashboard embedding all of
  the above (figures inlined as base64; opens in any browser).

With `--reference`, a comparison section is added (row-normalised confusion
matrix with the Hungarian best-match rings, plus ARI / NMI / agreement /
silhouette). Colours follow the validated categorical palette; stand
identity is always carried by a legend + direct labels, never colour alone.

`runs/`, `fmu_exports_clean/` and `reports/` are all gitignored, regenerable
from a live run. They were tracked until v1.2.1; the numbers in the committed
copies predate the merge stage, so keeping them presented superseded results as
current. Recover them from history if needed:
`git checkout b24fad3 -- runs/ fmu_exports_clean/ reports/`.

## Transparency outputs: the land-cover mask

`scripts/transparency_masking.py` writes, for one config, what the masking stage
did and why. It is read-only on Earth Engine: it reads cached assets, computes
the rest live and submits no export.

```
docs/transparency/<config>/            COMMITTED
  habitat_mask.png                     true colour beside the mask coloured by reason, one panel pair per ROI part
  habitat_mask_sheet<i>of<n>.png       the same, when the ROI has more than four parts
  summary.md                           the numbers only; no date, so git diff after a re-run shows real changes
  run_record.json                      config, cache fingerprint, the layers read and their cached asset ids,
                                       the git block, git blob ids of the scripts that ran, date, command line;
                                       --redraw appends an entry under redraws_since_this_run
outputs/transparency/<config>/         IGNORED BY GIT
  <part>_mask_provenance.tif           uint8, band 1 reason, band 2 source (codes under "Cached GEE assets");
                                       255 outside the part
  <part>_habitat_mask.tif              uint8, 1 habitat, 0 not; 255 outside the part or where the mask has no value
  <part>_landcover_summary.tif         uint8; the most recent usable year's IndiaSAT class where it is a habitat
                                       class (6, 12 by default), 80 where JRC water, 0 elsewhere; 255 outside the
                                       part. It can differ from the mask, which is a majority vote over years
  <part>_true_colour.tif               uint16, the red, green and blue bands of s2_composite; 0 outside the part
  roi_outline.geojson                  one feature per ROI part
  points.geojson                       only with --points: per point the part, kept, reason code, name and label,
                                       source code, name and label, and kept pixels in the 5 x 5 window around it
  masking_transparency.json            what --redraw reads: the config name and fingerprint, the masking stage's
                                       transparency record from the run manifest, each layer's cache status,
                                       the true-colour band names and any --compare-mask-asset results
```

`--docs-dir` and `--data-dir` change the two folders (defaults `docs/transparency`
and `outputs/transparency`). `<part>` is the name of one polygon of the ROI
file, in lower case with underscores (`part_N` when the file gives no name).

All rasters are EPSG:4326 at the analysis scale (`export.analysis_scale_m`),
on a grid anchored at (0, 0). At 10 m that is the grid the legacy layout's cache
exports land on, so for a config of that layout (every committed one here) a
cached mask is read pixel for pixel. In the per-step layout, every run since
round 9, cache exports land on the ROI's UTM grid, and a cached mask is
resampled onto these rasters (review C31). Whole-ROI numbers in `summary.md` come
from the run manifest (the masking stage's `transparency.summary_numbers`).
The stage tabulates those on the same EPSG:4326 grid, so in the per-step layout
the pass that computed the masks and the passes that read them from the cache
record slightly different `area_ha` and `share_kept`: in the runs of record
`area_ha` is 0.008% to 0.074% lower, and `share_kept` 1e-6 to 3e-4 higher, in
the passes that read the cache (`docs/reproducibility/r9_runs/README.md`).
Per-part numbers are tabulated from the saved rasters with the stage's own
arithmetic, and can differ slightly from the manifest at the edges of a part.
The colours, labels and the note on what "habitat" means are read from the
stage's display-layer declaration, not typed in the script.

Committed: `sanjay_van_baseline` and `odisha_v120_3ha_<district>` for
Angul, Dhenkanal, Kendujhar and Koraput (the Odisha ones are written by
`odisha_script/odisha_transparency_masking.py`, which adds the field plots as
points).

## `<config>_run.json` (Odisha run records)

`odisha_script/odisha_phase2_2_run_pipeline.py --through export` writes one run
record per config to `odisha_script/phase2_vectors/` (committed), beside the
stand layers it pulls down. Keys: `config`, `fingerprint`, `git`, `run_dir`,
`cache_status`, `pulled_polygon_counts`, `export_vector_layers`,
`drive_exports`, `snic_distance_scale`, `merge_diagnostics`,
`stand_attributes`, `stand_provenance`.

- `git` is the block described under `manifest.json`.
- `stand_provenance` maps each stand id (the `stand_lbl` of `stands_merged`, the
  same ids as `stand_attributes`) to the six provenance fields listed under
  `stands_merged`.
- `snic_distance_scale` is SNIC's distance normaliser for the superpixels the run
  used. The export pass reads segmentation from the cache, so since round 13 the
  value is read from the manifest of the segmentation pass that exported the
  superpixel asset the export pass read, and `snic_distance_scale_from` says so
  (or that no such manifest was found). Every record committed before round 13
  holds null there (review C36); the value is in the segmentation pass's
  manifest, `<run>_manifest_segmentation.json` where it is committed.

The run records committed so far were written before these two keys existed and
have neither. A record written from the current code has both.

`drive_exports` holds the Drive tasks the export stage submitted, not how they
ended: nothing in a batch waits on them (review C39). Since round 14,
`scripts/drive_export_states.py`, run after the batch, reads each task's state
(read-only) and writes it beside the record (`docs/running.md`):
`<config>_drive_exports.json`, results only (`what`, `config`; `files`, for each
file of `drive_exports` under the same key its `filename`, `folder`, `task_id`,
`description`, `state` and `error_message`; `states`, the count of each state;
`all_completed`; and `files_with_no_task_id`), and
`<config>_drive_exports_run.json` (`result_file`, `run_record`, `command_line`,
`read_at` and `git`).

## Evaluation outputs (`scripts/run_evaluation.py`)

Written to `--out-dir`. The script has not been run on any real site; see
`docs/evaluation_metrics.md`.

- `evaluation_results.json`: results only (no run times, dates or paths; numbers
  to 10 significant digits; `null` means not estimable). Keys: `about` and
  `predeclared_sha256` always; when `--statistics` is given, `inputs`,
  `label_check`, `null`, `tests` (under `rows`, one row per statistic: `observed`,
  `p_value`, `n_draws`, `n_valid`, the mean, standard deviation and quantiles of
  the chance values, and `p_holm`) and `descriptive` (the working behind each
  statistic); `reference_polygons` when `--reference-polygons` was given. The
  same inputs, arguments and seed give the same file byte for byte. The script
  refuses to replace an existing results file unless `--overwrite` is given.
- `evaluation_manifest.json`: the `git` block, the predeclaration's path, sha256
  and git status, the sha256 of every input file, the command line and
  arguments, library versions, and the sha256 of the results file.

`scripts/evaluation_synthetic_validation.py` writes
`docs/evaluation/synthetic_validation.md` and `.csv` (committed), and since round 13
`synthetic_validation_run.json` beside them: the command, the date, the `git` block (read
before the run) and the `environment` block, as a run record (review C37). The committed
`.md` and `.csv` were written before that, so no run record of theirs is committed.

## Run times go to logs

Result files hold results only, so that `git diff` after a re-run shows whether
it reproduced. The Odisha chance test (`odisha_phase3_3_significance.py`) and
the Phase 2 statistics (`odisha_phase2_5_stats.py`) print their run times and
append them to a `.log` file beside the results file; `*.log` is git-ignored.

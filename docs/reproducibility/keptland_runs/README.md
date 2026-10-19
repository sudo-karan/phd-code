# The kept-land runs: results and manifests

The two Sanjay Van kept-land runs of 15 Oct 2026 (round 5, `docs/handoff/2026-10-15-round5.md`):
`configs/sanjay_van_baseline_keptland.yaml` and `configs/sanjay_van_alphaearth_keptland.yaml`,
SNIC and the merge on kept land only (`segmentation.mask_before_snic`), run in batch with
`odisha_script/run_passes_safely.py` from a run tree pinned to `5027a48`, after the copy of
their upstream assets (`docs/reproducibility/keptland_reuse.json`).

The four Odisha box kept-land runs of 15 Oct 2026 (round 6, `docs/handoff/2026-10-15-round6.md`):
`configs/odisha_v120_3ha_squares_<district>_keptland.yaml` for Kendujhar, Angul, Dhenkanal and
Koraput, SNIC and the merge on kept land only, and distance to water capped at 10 km
(`features_static.cap_distance_to_water`). They were run in one batch with
`odisha_script/run_passes_safely.py` from a run tree pinned to `d180cb8`, after the copy of their
upstream assets except the static features, which each run computed
(`docs/reproducibility/keptland_reuse_odisha.json`).

The four descending-orbit kept-land runs of 15 Oct 2026 (round 7,
`docs/handoff/2026-10-15-round7.md`): `configs/odisha_v120_3ha_squares_<district>_keptland_s1desc.yaml`,
the round-6 configs with the radar from the descending Sentinel-1 orbit
(`spec-odisha-keptland-s1-orbit-descending`), the runs the declared field check scores. They were run
in one batch from a run tree pinned to `da7ab30`, after the copy of their upstream assets except the
radar features, which each run computed (`docs/reproducibility/keptland_reuse_s1desc.json`). Their
files were copied by `scripts/copy_run_results.py`. **Files over 5 MB are not in the repo**
(`spec-files-over-5-mb-off-git`, from round 7): `<run>_files_off_git.json` gives each such file's
name, size in bytes, SHA-256 and where it is (on the Mac, under `outputs/keptland_runs_s1desc/results/`).
`scripts/build_ui_early_data.py` and `odisha_script/odisha_keptland_score.py` read such a file there,
after checking its SHA-256.

**Note of 19 Oct 2026 (round 11):** the field check's scores of record are now those on these runs'
`_r9` copies, run again from empty caches (`docs/reproducibility/r9_runs/`; register entry
`field-keptland-scores-of-record-are-the-r9-re-runs`); the scores on these runs stay as history.

Per run `<run>`:

- `<run>_stands_merged.geojson`, `<run>_stands_snic.geojson`, `<run>_stands_dissolved.geojson`:
  the three vector layers, as `odisha_script/odisha_phase2_2_run_pipeline.py` pulls them in the
  export pass (the export stage's own feature-collection builders): the stands with every feature
  mean, their type (`cluster_id`) and the merge's provenance (`below_min`, `below_why`, ...); the
  superpixels; same-type regions.
- `<run>_run.json`: the run record the export pass writes (config, fingerprint, the git commit
  and whether the tree had uncommitted changes, cache status, polygon counts, Drive exports,
  merge diagnostics, stand attributes and provenance).
- `<run>_manifest_segmentation.json`, `_clustering.json`, `_export.json`: the pipeline manifest
  of each of the three passes (`runs/<run>_<date>_<time>/manifest.json` in the run tree): every
  stage's metadata, cache status, export tasks and summary numbers, and the git state.

Results only: no run times or dates. Left out of the copies, and nothing else: `run_dir` (a path
holding the run's date and time), `total_elapsed_sec`, each stage's `elapsed_sec`, the export
manifest's `run_timestamp` and each Drive export's `submitted_at`. The times are in the batch logs
on the Mac (`outputs/keptland_runs/logs/keptland_sanjay_van.log`, and for the box runs
`outputs/keptland_runs_odisha/logs/keptland_odisha_boxes.log`). `<run>_raster_at_plots.csv` is not
copied. For Sanjay Van it is empty: there are no field plots there. For the box runs it samples
the stand rasters at the FES plots, which joins the plots to the stands, and round 6 shows the
plots without any comparison; the field check declared for these runs
(`odisha_script/PHASE_KEPTLAND_PREDECLARED.md`) joins them on the stand polygons instead. Those
files are on the Mac, in the run tree's `odisha_script/phase2_vectors/`.

`python scripts/describe_keptland_runs.py` prints each run's descriptive numbers from these files.

**Note added 20 Oct 2026 (round 13, review C16; the manifests here are as first written).** Each
`_manifest_*.json` here glosses the summary number `stands_below_min_area_by_cause` as "isolated:
it touches no other stand". `isolated` means no 4-connected neighbour in the merge's graph, which
counts shared edges only, so a stand that meets another stand only at a corner is isolated too.
Counted from the merged layers here and Koraput's `_s1desc` layer off git (hash-checked against
its record): 23 of the 2,065 stands filed `isolated` that have a polygon (2,091 in the ten run
records) touch another stand at a corner only, and none along an edge; in Sanjay Van baseline,
2 of 388 (390 in its record, which `docs/handoff/2026-10-15-round5.md` calls "all isolated
(no kept-land neighbour)"). No result changes: no step of the pipeline reads `below_why`. Since round 13 the
merge stage writes "isolated: it shares no edge with another stand (no 4-connected neighbour; it
may meet one at a corner)".

**Note added 20 Oct 2026 (round 13, review C14; the records here are as first written).**
`threshold_calibration.joint_admit_rate_pct` in the run records and manifests here was computed
before round 13's fix: it counted as admitted a pair with fewer than `merge.min_defined_criteria`
criteria defined on both sides that passed the ones it had, a pair the gate rejects. A record's
rate is above the fixed one by at most `pass1_pairs_blocked_by_undefined_criteria_round1` plus
`pass1_pairs_blocked_by_area_round1` over `n_pairs_with_any_defined_criterion`, all from the same
record: 0, the same rate, in 15 of the 30 records here, and at most 0.22 points in the others
(Dhenkanal's round 6 run, 1 + 14 of 6,809 pairs). The copies in `ui_data/` are left as they are.

**Note of 20 Oct 2026 (round 13, review C30): the two Koraput records written by the read-back
tool.** `odisha_v120_3ha_squares_koraput_keptland_run.json` and
`odisha_v120_3ha_squares_koraput_keptland_s1desc_run.json` were written by
`odisha_script/odisha_read_back_export.py`, as their `read_back` block says: each export pass ended
after it wrote the stands layer (`read_back.layers_the_run_wrote` lists `stands_merged` only). In
both, `export_vector_layers` holds the tool's own counts of what it read back, not the export
stage's. Checked against the export stage's manifest beside each record
(`<run>_manifest_export.json`, `vector_layers`): every `n_features`, and the stands layer's
`n_stands` and `n_stands_split_into_pieces`, are equal to the export stage's. But under
`stands_snic`, `n_stands` (8,723 in both) and `n_stands_split_into_pieces` (14 and 19) are counts
the export stage never makes: its manifest has none there, and a record the runner writes holds
null. Since round 13 the tool writes the export stage's counts under `export_vector_layers` and
its own under `read_back.layer_counts`. The two records are kept as written; no number changed.

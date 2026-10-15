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

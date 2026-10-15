# The kept-land runs: results and manifests

The two Sanjay Van kept-land runs of 15 Oct 2026 (round 5, `docs/handoff/2026-10-15-round5.md`):
`configs/sanjay_van_baseline_keptland.yaml` and `configs/sanjay_van_alphaearth_keptland.yaml`,
SNIC and the merge on kept land only (`segmentation.mask_before_snic`), run in batch with
`odisha_script/run_passes_safely.py` from a run tree pinned to `5027a48`, after the copy of
their upstream assets (`docs/reproducibility/keptland_reuse.json`).

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
manifest's `run_timestamp` and each Drive export's `submitted_at`. The times are in the batch log
on the Mac (`outputs/keptland_runs/logs/keptland_sanjay_van.log`). `<run>_raster_at_plots.csv`
is not copied: there are no field plots in Sanjay Van, and it is empty.

`python scripts/describe_keptland_runs.py` prints each run's descriptive numbers from these files.

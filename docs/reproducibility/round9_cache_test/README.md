# Round 9, task D: the cache test on Kendujhar

The test as declared before it ran is in `docs/handoff/2026-10-17-round9.md` (Done, "Task D: the
cache test, as declared before it ran"); its verdict and every difference are there too. This
folder holds the evidence: results only, apart from the one `_run.json` run record.

Two configs, copies of `configs/odisha_v120_3ha_squares_kendujhar_keptland_s1desc.yaml` with only
the name changed, each run from an empty cache in the per-step cache layout (round 9) from a clean
run tree at `fb8e8ce`:

- run 1, `odisha_v120_3ha_squares_kendujhar_keptland_s1desc_r9`, 17 Oct 23:41 to 23:57 IST;
- run 2, `odisha_v120_3ha_squares_kendujhar_keptland_s1desc_r9_check`, 17 Oct 23:59 to 18 Oct
  00:16 IST;
- run 3, run 1's config again, reading everything back from its cache, 18 Oct 00:21 to 00:27 IST.

| File | What |
|---|---|
| `<run>_stands_merged.geojson`, `_stands_dissolved.geojson` | the run's stand and same-type-region layers, as its export pass wrote them |
| `<run>_files_off_git.json` | the superpixel layer, kept off git (over 5 MB): size, SHA-256, where it is |
| `<run>_run.json` | the run record: merge diagnostics, per-stand attributes and provenance, the export counts, cache layout, step keys, git, environment |
| `<run>_manifest_features_computed.json` | the first features pass, which computed and exported the nine feature-stage assets, with their input images |
| `<run>_manifest_features.json`, `_segmentation`, `_clustering`, `_export` | the wrapper's four passes (its features pass found everything cached) |
| `run1_r9_grid_check.txt`, `run2_r9_check_grid_check.txt` | read-only, after each features pass: every asset on the analysis grid, with its input-images record |
| `cache_test_assets_r9_vs_r9_check.json` (and `_run.json`) | runs 1 and 2, every cached asset pixel for pixel (`scripts/compare_cached_assets.py`, on the assets' own grid) |
| `cache_test_layers_r9_vs_r9_check.json` | runs 1 and 2, the three layers polygon for polygon, byte identity, counts, the run records |
| `cache_test_run3_read_back.json` | run 3: every cached output read back, no task, and the three layers against run 1's |

Timings are in the logs on the Mac (`outputs/round9/logs/`), not here.

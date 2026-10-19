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

**Note of 20 Oct 2026 (round 13; review A1, A4, A5, A6, B13, B14, B16, B17 and B18): both runs are
from before the round 13 fixes.** The test compares two runs of the same code and a read-back, and
its verdict on them stands; whether the code after the fixes reproduces as well was not tested. The
files here are kept as the runs wrote them; no number is changed. Run 1's files are the `_r9`
record's Kendujhar files, also in `docs/reproducibility/r9_runs/` (see the note at the end of its
README). What reaches both runs (the round 13 brief, `docs/handoff/2026-10-20-round13.md`, Done):
- A1: each distance to water is to water inside the ROI only, so an upper bound (none is at the 10
  km cap; the largest is 5,029.7 m).
- A4: one Sentinel-1 scene of 31 Dec 2022 over the Kendujhar box was left out (read-only call 4 of
  the brief). The 188 Sentinel-1 images in the grid checks are what the runs used; the 10 manifests
  give the windows as 2017-01-01 to 2022-12-31, though the filters stopped on 30 Dec 2022.
- A5 (slope and aspect in whole degrees, a flat cell read as facing north), B13 (the NDVI phase's
  cosine log-transformed), B14 (2 stands whose label has more than one polygon, in each run), B16,
  B17 (each run record has stands with a `frac_valid_<band>` up to 2, and 2 stands of 0 pixels) and
  B18.
- A6: in the four layers here, 36 of 1,316 polygons are off by more than 1% (+2.33 ha; 18 in each
  run), counted offline as the brief counts the other run folders, and every other polygon's area
  moves by 0.1% to 0.3% on the export's new measure.
- How far any fix moves a stand, a type or a score was not measured; it needs Earth Engine.

**Note added 20 Oct 2026 (round 13, review C16; the manifests here are as first written).** Each
manifest here glosses the summary number `stands_below_min_area_by_cause` as "isolated: it
touches no other stand". `isolated` means no 4-connected neighbour in the merge's graph, which
counts shared edges only, so a stand that meets another stand only at a corner is isolated too.
In these two Kendujhar runs none does: 0 of the 143 stands filed `isolated` that have a polygon in
each layer (145 in each run record). Since round 13 the merge stage writes "isolated: it shares
no edge with another stand (no 4-connected neighbour; it may meet one at a corner)".

# Round 12's runs (Task 4: the 10 ha box runs; Task 5, the 30 km tile, was not run)

The runs of round 12 (`docs/handoff/2026-10-19-round12.md`), each from an empty cache in the
per-step cache layout, one config at a time, through `odisha_script/run_passes_safely.py`, from
the clean run tree `outputs/round12/run_tree` on the Mac. Results only, apart from each run's
`_run.json` record; copied by `scripts/copy_run_results.py`, which strips run times. Timings are
in the logs on the Mac (`outputs/round12/logs/`), not here.

Task 4, the 10 ha size check on the boxes, both arms (the change of 19 Oct 2026 to
`odisha_script/PHASE_KEPTLAND_PREDECLARED.md`): each config a copy of a 3 ha `_r9` box run
changing only `segmentation.size` (6 to 10) and `merge.max_area_ha` (3 to 10)
(`tests/test_r9_configs.py`).

| Run | Copy of | Run tree at | Superpixels | Stands | Stand polygons |
|---|---|---|---|---|---|
| `odisha_v120_10ha_squares_kendujhar_keptland_s1desc_r9` | `odisha_v120_3ha_squares_kendujhar_keptland_s1desc_r9` | `3db501b` | 1,088 | 354 | 355 (352 stands) |
| `odisha_v120_10ha_squares_angul_keptland_s1desc_r9` | `odisha_v120_3ha_squares_angul_keptland_s1desc_r9` | `3db501b` | 466 | 136 | 134 |
| `odisha_v120_10ha_squares_koraput_keptland_s1desc_r9` | `odisha_v120_3ha_squares_koraput_keptland_s1desc_r9` | `3db501b` | 3,332 | 988 | 990 (983 stands) |
| `odisha_v120_10ha_squares_dhenkanal_keptland_s1desc_r9` | `odisha_v120_3ha_squares_dhenkanal_keptland_s1desc_r9` | `3db501b` | 1,119 | 334 | 330 (329 stands) |
| `odisha_alphaearth_10ha_squares_kendujhar_keptland_r9` | `odisha_alphaearth_3ha_squares_kendujhar_keptland_r9` | `3db501b` | 1,088 | 352 | 350 |
| `odisha_alphaearth_10ha_squares_angul_keptland_r9` | `odisha_alphaearth_3ha_squares_angul_keptland_r9` | `3db501b` | 466 | 129 | 127 |
| `odisha_alphaearth_10ha_squares_koraput_keptland_r9` | `odisha_alphaearth_3ha_squares_koraput_keptland_r9` | `3db501b` | 3,332 | 943 | 940 (938 stands) |
| `odisha_alphaearth_10ha_squares_dhenkanal_keptland_r9` | `odisha_alphaearth_3ha_squares_dhenkanal_keptland_r9` | `3db501b` | 1,119 | 334 | 329 |

| File | What |
|---|---|
| `<run>_stands_merged.geojson`, `_stands_snic.geojson`, `_stands_dissolved.geojson` | the run's stands, superpixels and same-type regions, as its export pass wrote them |
| `<run>_files_off_git.json` | where a run has a layer over 5 MB: its size, SHA-256 and where it is on the Mac (`outputs/round12/results/`) |
| `cost_<run>.json` (and `_run.json`) | the run's EECU-hours, batch by stage and online by pass, and per 1,000 ha (`scripts/eecu_by_stage.py`); the record holds the pass spans and when they were read |
| `<run>_run.json` | the run record: merge diagnostics, per-stand attributes and provenance, export counts, cache layout, step keys, git, environment |
| `<run>_manifest_features.json`, `_segmentation`, `_clustering`, `_export` | the manifests of the wrapper's four passes |

**Note of 20 Oct 2026 (round 13; review A1, A4, A5, A6, B13, B14, B16, B17 and B18): these runs are
from before the round 13 fixes.** Their files here are kept as the runs wrote them, the record from
before the fixes; no number is changed. The round 13 brief (`docs/handoff/2026-10-20-round13.md`,
Done) says what each fix changes, and that the hand-crafted 10 ha runs will be re-run (roadmap R3);
whether R3 re-runs the AlphaEarth 10 ha runs is put to Jaskaran there. Which fixes reach which run
(the 3 ha runs' note, in `docs/reproducibility/r9_runs/README.md`, says more):
- **The four hand-crafted runs** (`odisha_v120_10ha_squares_<district>_keptland_s1desc_r9`): A1
  (Angul's 134 stand polygons all read the 10 km cap, and the band was dropped as constant; in
  Dhenkanal 145 of 330 and in Koraput 673 of 990 are at the cap, upper bounds), A4 (one Sentinel-1
  scene of 31 Dec 2022 left out over the Angul, Dhenkanal and Kendujhar boxes, two Sentinel-2 scenes
  over the Koraput boxes; read-only call 4 of the brief), A5 (slope and aspect in whole degrees, a
  flat cell read as facing north) and B13 (the NDVI phase's cosine log-transformed in every run, its
  sine too in Angul).
- **The four AlphaEarth runs** (`odisha_alphaearth_10ha_squares_<district>_keptland_r9`): A1, A5 and
  B13 do not reach them. A4 reaches the Koraput run only, through the merge's NDVI amplitude
  (question 1 of the brief; noted as affected until it is answered, by an amount not measured).
- **All eight runs:**
  - B14: stands whose label has more than one polygon in the merged layer, hand-crafted Angul 0,
    Dhenkanal 1, Kendujhar 3, Koraput 7; AlphaEarth Angul 0, Dhenkanal 0, Kendujhar 0, Koraput 2. A
    unit with no data in a band was given 0 there; whether these runs had such a unit was not
    checked.
  - B16: where it was checked, no drop decision of these runs changes; the recorded centres and
    spreads do.
  - B17: every run record here has stands with a `frac_valid_<band>` above 1 (the largest 2 to 4 per
    run) and 1 to 13 stands of 0 pixels.
  - B18: at 10 ha the float sum judged 32 of the 999 ways to split exactly 10 ha into two
    whole-pixel areas as over the limit (review); not checked for these runs.
  - A6: in the committed layers here, 137 of 9,951 polygons are off by more than 1% (+63.10 ha in
    all; 47 of the 3,555 stand polygons, +8.73 ha; the brief's count), and every other polygon's
    area moves by 0.1% to 0.3% on the export's new measure. No score reads them.
  - The 32 manifests give the three windows as 2017-01-01 to 2022-12-31; the runs' filters stopped
    on 30 Dec 2022 (A4).
- How far any fix moves a stand, a type or a score was not measured; it needs Earth Engine. Round
  13's Task 1 changes no type of these runs. The cost files record what the runs cost and are not
  affected.

**Note added 20 Oct 2026 (round 13, review C16; the manifests here are as first written).** Each
`_manifest_*.json` here glosses the summary number `stands_below_min_area_by_cause` as "isolated:
it touches no other stand". `isolated` means no 4-connected neighbour in the merge's graph, which
counts shared edges only, so a stand that meets another stand only at a corner is isolated too.
Counted from the merged layers here: 7 of the 1,283 stands filed `isolated` that have a polygon
(1,311 in the eight run records) touch another stand at a corner only, and none along an edge.
No result changes: no step of the pipeline reads `below_why` (the fit leaves out stands by
`below_min`, whatever the cause). Since round 13 the merge stage writes "isolated: it shares no
edge with another stand (no 4-connected neighbour; it may meet one at a corner)".

**Note of 20 Oct 2026 (round 13, review C36): `snic_distance_scale` is null in all eight run
records here.** The record is written by the export pass, which reads the superpixels from the
cache, so the segmentation stage's metadata there holds no scale. The scale each run's superpixels
were drawn with is in `<run>_manifest_segmentation.json` beside its record (the segmentation
stage's `metadata.distance_scale`), and it is there for all eight. Since round 13 the runner reads
it from that pass's manifest, and `snic_distance_scale_from` says where. The records are kept as
written; no number changed.

**Note of 20 Oct 2026 (round 13, review C38): the git block of the eight cost records.** Until
round 13 `scripts/eecu_by_stage.py` read git in the working directory, after it had written the
cost file, as `{commit, tracked_files_modified}`. For the eight cost records here that did no
harm: each command line gives relative paths, so it was run from the repo root, and each cost
file was new when it was written (first committed after its `read_at`), so writing it changed no
tracked file. Two of them, Dhenkanal and Koraput of the AlphaEarth arm, hold
`tracked_files_modified: true`: other tracked files of the checkout were modified when they were
read, and the record does not say which. Since round 13 the script records the block every run
record has (`fmu.utils.provenance.git_state` of its own checkout, read before it writes). The
records are kept as written; no number changed.

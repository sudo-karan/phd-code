# Round 9's Task G and H runs (run in round 10)

The re-runs of round 9's Task G (`docs/handoff/2026-10-17-round9.md`, run in round 10,
`docs/handoff/2026-10-18-round10.md`): each config a copy named `<name>_r9` that changes only the
name (`tests/test_r9_configs.py`), run from an empty cache in the per-step cache layout (round 9),
one config at a time, through `odisha_script/run_passes_safely.py`, from a clean run tree. Results
only, apart from each run's `_run.json` record; copied by `scripts/copy_run_results.py`, which
strips run times. Timings are in the logs on the Mac (`outputs/round10/logs/`), not here.

| Run | Copy of | Run tree at | Superpixels | Stands | Stand polygons |
|---|---|---|---|---|---|
| `odisha_v120_3ha_squares_angul_keptland_s1desc_r9` | `odisha_v120_3ha_squares_angul_keptland_s1desc` | `acb5f8d` | 1,205 | 221 | 219 |
| `odisha_v120_3ha_squares_dhenkanal_keptland_s1desc_r9` | `odisha_v120_3ha_squares_dhenkanal_keptland_s1desc` | `acb5f8d` | 2,889 | 552 | 552 |
| `odisha_v120_3ha_squares_kendujhar_keptland_s1desc_r9` | `odisha_v120_3ha_squares_kendujhar_keptland_s1desc` | `fb8e8ce` | 2,747 | 547 | 547 |
| `odisha_v120_3ha_squares_koraput_keptland_s1desc_r9` | `odisha_v120_3ha_squares_koraput_keptland_s1desc` | `acb5f8d` | 8,743 | 1,616 | 1,616 |
| `sanjay_van_baseline_keptland_r9` | `sanjay_van_baseline_keptland` | `acb5f8d` | 1,205 | 583 | 578 |
| `sanjay_van_alphaearth_keptland_r9` | `sanjay_van_alphaearth_keptland` | `acb5f8d` | 1,205 | 565 | 560 |

Task H's AlphaEarth arm (the change of 18 Oct 2026 to `odisha_script/PHASE_KEPTLAND_PREDECLARED.md`):
each config a copy of the district's `_r9` run changing only the feature description to AlphaEarth
(`tests/test_r9_configs.py`), run the same way.

| Run | Copy of | Run tree at | Superpixels | Stands | Stand polygons |
|---|---|---|---|---|---|
| `odisha_alphaearth_3ha_squares_angul_keptland_r9` | `odisha_v120_3ha_squares_angul_keptland_s1desc_r9` | `fcfc169` | 1,205 | 237 | 235 |
| `odisha_alphaearth_3ha_squares_dhenkanal_keptland_r9` | `odisha_v120_3ha_squares_dhenkanal_keptland_s1desc_r9` | `fcfc169` | 2,889 | 574 | 570 |
| `odisha_alphaearth_3ha_squares_kendujhar_keptland_r9` | `odisha_v120_3ha_squares_kendujhar_keptland_s1desc_r9` | `fcfc169` | 2,747 | 555 | 555 |
| `odisha_alphaearth_3ha_squares_koraput_keptland_r9` | `odisha_v120_3ha_squares_koraput_keptland_s1desc_r9` | `fcfc169` | 8,743 | 1,644 | 1,641 |

Task I's cost pilot: the Angul `_r9` config with only the ROI changed, to one 10 km square on the
Angul boxes' centroid (`aois/odisha_tile_angul_10km.geojson`), run the same way and not scored.

| Run | Copy of | Run tree at | Superpixels | Stands | Stand polygons |
|---|---|---|---|---|---|
| `odisha_v120_3ha_tile10km_angul_keptland_s1desc_r9` | `odisha_v120_3ha_squares_angul_keptland_s1desc_r9` | `be36f74` | 21,263 | 3,748 | 3,743 |

Kendujhar's re-run is round 9's Task D run 1 (`docs/reproducibility/round9_cache_test/`): its
files here are byte-for-byte copies of those, so that the field check reads all four districts
from one folder. Its features were computed by a features pass of its own before the wrapper
ran (`_manifest_features_computed.json`), so the wrapper's features pass found them cached.

The stands and stand polygons are from each run's record (`merge_diagnostics` and
`export_vector_layers`). Corrected on 19 Oct 2026 (round 12): this said that a stand under
`export.vector_min_stand_pixels` (4) pixels has no polygon, but that setting filters
`stands_dissolved` only. The stands with no polygon (2 to 10 per run) are fragments of one
superpixel, each isolated, with no pixel, or one or two, inside the ROI on the analysis grid
(`stand_attributes`); in Angul's hand-crafted run 27 of the 29 stands under 4 pixels have a
polygon.

| File | What |
|---|---|
| `<run>_stands_merged.geojson`, `_stands_snic.geojson`, `_stands_dissolved.geojson` | the run's stands, superpixels and same-type regions, as its export pass wrote them |
| `<run>_files_off_git.json` | where a run has a layer over 5 MB: its size, SHA-256 and where it is on the Mac (`outputs/round10/results/`; Kendujhar's in `outputs/round9/results/`) |
| `stand_types_from_fit_rows.json` | Round 12, Task 2: per run, the stands whose type would change under round 12's export (a stand with a row in the k-means fit takes that row's type), counted offline (`scripts/stand_types_from_fit_rows.py`) |
| `cost_<run>.json` (and `_run.json`) | Task I: the run's EECU-hours, batch by stage and online by pass, and per 1,000 ha (`scripts/eecu_by_stage.py`); the record holds the pass spans and when they were read |
| `<run>_run.json` | the run record: merge diagnostics, per-stand attributes and provenance, export counts, cache layout, step keys, git, environment |
| `<run>_manifest_features.json`, `_segmentation`, `_clustering`, `_export` | the manifests of the wrapper's four passes; the features pass computed and exported every feature asset |

**Note of 20 Oct 2026 (round 13; review A1, A4, A5, A6, B13, B14, B16, B17 and B18): these runs are
from before the round 13 fixes.** Their files here (the layers, the run records and the manifests)
are kept as the runs wrote them, the record from before the fixes; no number is changed. The round
13 brief (`docs/handoff/2026-10-20-round13.md`, Done) says what each fix changes, and that the
hand-crafted `_r9` runs will be re-run (roadmap R3); whether R3 re-runs the AlphaEarth runs is put
to Jaskaran there. Which fixes reach which run:
- **The six hand-crafted runs** (the four `odisha_v120_3ha_squares_<district>_keptland_s1desc_r9`,
  the tile and `sanjay_van_baseline_keptland_r9`):
  - A1, distance to water saw no water outside the ROI. Angul's 219 stand polygons all read the 10
    km cap, and Sanjay Van's 578 all read 463,409.5 m, the transform's fill value where it finds no
    water (that config sets no cap); both runs dropped the band as constant. In Dhenkanal (279 of
    552 at the cap) and Koraput (1,149 of 1,616, by the review) the capped values are upper bounds.
  - A4, the Sentinel-1 and Sentinel-2 date windows stopped on 30 Dec 2022, not 31 Dec. Left out
    (read-only call 4 of the brief): one Sentinel-1 scene of 31 Dec 2022 over the Angul, Dhenkanal
    and Kendujhar boxes and the tile, two Sentinel-2 scenes over the Koraput boxes, and none at
    Sanjay Van. The Sentinel-1 scene reaches `vv_minus_vh_median`, one of SNIC's six input bands,
    and the radar bands the clustering reads; the Sentinel-2 scenes reach `B4_median`, `B8_median`
    and `ndvi_amplitude_annual` (SNIC's inputs; the last is also one of the merge's criteria) and
    the NDVI bands the clustering reads.
  - A5, slope and aspect in whole degrees, and a flat cell read as facing north.
  - B13, the NDVI phase's cosine log-transformed in every run, its sine too in Angul.
- **The five AlphaEarth runs** (the four `odisha_alphaearth_3ha_squares_<district>_keptland_r9` and
  `sanjay_van_alphaearth_keptland_r9`): A1, A5 and B13 do not reach them. SNIC and k-means read the
  64 embedding bands, the merge reads canopy height and the NDVI amplitude (on the boxes also the
  canopy height's spread), and the layers carry the embedding bands only. A4 reaches the Koraput run
  only, through the merge's NDVI amplitude (question 1 of the brief; noted as affected until it is
  answered, by an amount not measured). The other four read no image that A4 left out.
- **All eleven runs:**
  - B14, a stand in several pieces got one mean per piece, not one per stand. Stands whose label has
    more than one polygon in the merged layer: hand-crafted Angul 0, Dhenkanal 5, Kendujhar 2,
    Koraput 5, the tile 5, Sanjay Van 0; AlphaEarth Angul 0, Dhenkanal 1, Kendujhar 2, Koraput 2,
    Sanjay Van 0 (the Koraput and tile layers read off git, SHA-256 checked against
    `<run>_files_off_git.json`). A unit with no data in a band was given 0 there; whether these runs
    had such a unit was not checked.
  - B16, the constant-band test and the scaling used histogram quartiles, not exact ones. Where it
    was checked, no drop decision of these runs changes; the recorded centres and spreads do.
  - B17, the merge counted a superpixel's pixels and its valid pixels by different rules at the
    ROI's edge. Every run record here has stands with a `frac_valid_<band>` above 1 (the largest 2
    to 5 per run, 5 on the tile) and 1 to 13 stands of 0 pixels. The review names six edge stands
    (hand-crafted Angul 32 and 218, Koraput 47; AlphaEarth Angul 33, Dhenkanal 255 and 431) that the
    merge counted at 1 ha or more and that hold 97 to 99 whole pixels by its count (not checked
    here); none holds a scored plot.
  - B18, the merge tested its area limits on a sum of floats. The review rebuilt the graphs of three
    runs (the tile pilot, the Angul box and the Sanjay Van baseline) and found no stand that
    changes; this was not checked again, nor for the other runs.
  - A6, `area_ha` and `n_pixels` came from the polygon's area, which counted some holes as area. In
    the committed layers here, 104 of 10,381 polygons are off by more than 1% (+29.50 ha in all; 52
    of the 3,816 stand polygons, +15.97 ha; the brief's count), and every other polygon's area moves
    by 0.1% to 0.3% on the export's new measure. No score reads them.
  - The 45 manifests give `s2_phenology_window`, `s2_composite_window` and `s1_radar_window` as
    2017-01-01 to 2022-12-31; the runs' filters stopped on 30 Dec 2022 (A4).
- How far any fix moves a stand, a type or a score was not measured; it needs Earth Engine. Round
  13's Task 1 changes no type of these runs. The cost files record what the runs cost and are not
  affected. The review's method questions (A2, A3, B12, B15) are not fixes of this round and are not
  covered here.

**Note added 20 Oct 2026 (round 13, review C16; the manifests here are as first written).** Each
`_manifest_*.json` here glosses the summary number `stands_below_min_area_by_cause` as "isolated:
it touches no other stand". `isolated` means no 4-connected neighbour in the merge's graph, which
counts shared edges only, so a stand that meets another stand only at a corner is isolated too.
Counted from the merged layers here and the off-git ones their records name (hash-checked), of
the stands filed `isolated` that have a polygon: 21 of 1,293 in the eight box runs (1,321 in
their run records) touch another stand at a corner only, 10 of 578 in the 10 km tile (588), 1 of
387 in Sanjay Van baseline (392) and 0 of 386 in Sanjay Van AlphaEarth (391); none touches one
along an edge. No result changes: no step of the pipeline reads `below_why` (the fit leaves out
stands by `below_min`, whatever the cause). Since round 13 the merge stage writes "isolated: it
shares no edge with another stand (no 4-connected neighbour; it may meet one at a corner)".

**Note added 20 Oct 2026 (round 13, review C14; the records here are as first written).**
`threshold_calibration.joint_admit_rate_pct` in the run records and manifests here was computed
before round 13's fix: it counted as admitted a pair with fewer than `merge.min_defined_criteria`
criteria defined on both sides that passed the ones it had, a pair the gate rejects. A record's
rate is above the fixed one by at most `pass1_pairs_blocked_by_undefined_criteria_round1` plus
`pass1_pairs_blocked_by_area_round1` over `n_pairs_with_any_defined_criterion`, all from the same
record: 0, the same rate, in 21 of the 33 records here, and at most 0.16 points in the others
(Sanjay Van baseline, 3 of 1,890 pairs).

**Note of 20 Oct 2026 (round 13, review C36): `snic_distance_scale` is null in all eleven run
records here.** The record is written by the export pass, which reads the superpixels from the
cache, so the segmentation stage's metadata there holds no scale. The scale each run's superpixels
were drawn with is in `<run>_manifest_segmentation.json` beside its record (the segmentation
stage's `metadata.distance_scale`), and it is there for all eleven. Since round 13 the runner reads
it from that pass's manifest, and `snic_distance_scale_from` says where. The records are kept as
written; no number changed.

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
```

The directory is gitignored; checking outputs into git is not the
intended workflow. Reproducibility is via `manifest.json` (the inputs)
plus the cached GEE assets (the outputs).

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
  "stages": [
    {
      "name": "masking",
      "elapsed_sec": 18.244,
      "produced": ["habitat_mask", "landcover_summary", "water_mask"],
      "warnings": [],
      "metadata": { "...stage-specific..." },
      "cache_status": {
        "habitat_mask": "hit",
        "water_mask": "hit",
        "landcover_summary": "hit"
      },
      "export_tasks": []
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
          "asset_path": "projects/.../sanjay_van_baseline/data_load/s2_composite",
          "description": "sanjay_van_baseline_data_load_s2_composite"
        }
      ]
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
| `stages[].name` | Stage name (matches the `@register_stage` decorator) |
| `stages[].elapsed_sec` | Wall-clock time for this stage |
| `stages[].produced` | Sorted list of context keys this stage actually wrote |
| `stages[].warnings` | Stage-emitted warnings (non-fatal) |
| `stages[].metadata` | Stage-specific stats: band counts, sample sizes, etc. |
| `stages[].cache_status` | Per-output-key: `"hit"`, `"miss"`, `"miss-exported"`, or `"off"` |
| `stages[].export_tasks` | Async GEE export tasks submitted during this stage |
| `config` | The entire input config, serialized. Proves what was run. |

### Cache status values

- `"hit"`: asset was already cached; cached version loaded into context
- `"miss"`: asset wasn't cached; live computation used
- `"miss-exported"`: asset wasn't cached; live computation used AND an
  export task was started so next run will hit
- `"off"`: caching was disabled for this run (`use_cache=False`)
- Key absent: output is not cacheable (e.g., a Python dict, an
  `ee.ImageCollection`)

### Stage source

If `stages[i].metadata.source == "cache"`, the stage was skipped entirely
because all its cacheable outputs were cached. The stage's `run()`
method didn't execute; the cached assets were loaded into the context
and the stage was marked done.

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
  "run_timestamp": "2026-05-20T01:35:22+00:00",
  "roi": {
    "name": "sanjay_van",
    "area_km2": 6.831,
    "geojson_path": "aois/sanjay_van.geojson"
  },
  "config_snapshot": { "...entire YAML...": "..." },
  "asset_paths": {
    "habitat_mask": "projects/.../sanjay_van_baseline/masking/habitat_mask",
    "water_mask":   "projects/.../sanjay_van_baseline/masking/water_mask",
    "landcover_summary": "projects/.../sanjay_van_baseline/masking/landcover_summary",
    "s2_composite": "projects/.../sanjay_van_baseline/data_load/s2_composite",
    "optical_features": "projects/.../sanjay_van_baseline/features_optical/optical_features",
    "radar_features":   "projects/.../sanjay_van_baseline/features_radar/radar_features",
    "structure_features": "projects/.../sanjay_van_baseline/features_structure/structure_features",
    "static_features":  "projects/.../sanjay_van_baseline/features_static/static_features",
    "snic_clusters":    "projects/.../sanjay_van_baseline/segmentation/snic_clusters__bbc3e3d624",
    "snic_means":       "projects/.../sanjay_van_baseline/segmentation/snic_means__bbc3e3d624",
    "cluster_labels":   "projects/.../sanjay_van_baseline/clustering/cluster_labels__bbc3e3d624",
    "feature_stack":    "projects/.../sanjay_van_baseline/clustering/feature_stack__bbc3e3d624"
  },
  "clustering": {
    "k": 6,
    "seed": 42,
    "n_training_units": 269,
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
went into k-means. So `ndvi_mean` for a cluster is a real NDVI between
-1 and 1; `elevation` is real meters; `canopy_height` is real meters.
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
    "n_stands": 269,
    "total_area_ha": 841.9,
    "area_ha_min": 0.12, "area_ha_p10": 1.04, "area_ha_median": 2.31,
    "area_ha_p90": 7.88, "area_ha_max": 9.97, "area_ha_mean": 3.13,
    "stands_below_min_area": 11,
    "frac_stands_below_min_area": 0.0409,
    "area_in_undersized_stands_ha": 6.4,
    "area_share_largest_decile": 0.271,
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
    "n_superpixels": 1249, "n_stands": 269, "reduction_factor": 4.643,
    "pass1_rounds": 7, "pass1_merges": 941,
    "pass2_iterations": 3, "pass2_merges": 39, "pass2_fallback_merges": 6,
    "stands_below_min_area": 11,
    "orphans_isolated": 0, "orphans_area_blocked": 11,
    "orphans_no_attribute_match": 0,
    "stands_with_incomplete_criteria": 4,
    "adjacency": { "n_regions": 1249, "n_edges": 3128, "mean_degree": 5.009, "n_isolated": 0 },
    "threshold_calibration": { "joint_admit_rate_pct": 38.7, "per_band": { "...": "..." } },
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
| `merge.orphans_area_blocked` | Undersized stands whose every neighbour is already too big to absorb them. **A signal `max_area_ha` is too tight**, not a fact about the forest | int |
| `merge.pass2_fallback_merges` | Pass-2 merges no relaxed criterion could justify, decided by shared-edge length alone. The honest count of "surrounded by genuinely different forest"; look here first if stand geometry looks wrong | int |
| `merge.threshold_calibration.joint_admit_rate_pct` | Share of adjacent pairs passing **all** criteria at once. The gate is conjunctive, so the per-band marginals do not describe it. **Not a tuning target** — pass rate is a diagnostic, and pass 1 iterates to convergence so a per-round rate is not the share of total merging | 0 to 100 |
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
R² on it is partly circular by construction.

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

As of v1.1.0 the export stage emits two vector layers, each in every
format listed in `export.vector_formats` (default both SHP and GeoJSON).
SHP files arrive zipped (GEE bundles the .shp/.shx/.dbf/.prj). GeoJSON
files are single text files.

| Layer | Filename pattern | What it is |
|---|---|---|
| **stands_snic** | `<config>_stands_snic.{zip,geojson}` | One polygon per SNIC superpixel. Debugging / methodology layer. |
| **stands_dissolved** | `<config>_stands_dissolved.{zip,geojson}` | One polygon per connected same-cluster region. Forester-facing management units. |

For a typical Sanjay Van run: ~1,500 SNIC polygons, ~10-100 dissolved
polygons depending on cluster fragmentation. Both layers in EPSG:4326.

### Attribute schemas

#### `stands_snic`

SHP attributes (capped at 10-char field-name limit):

| Field | Type | Meaning |
|---|---|---|
| `stand_id` | int | Sequential 1..N. Sorted by centroid lat desc / lon asc. **Deterministic** — same SNIC geometry always produces the same numbering. Use as a stable ID across runs of the same config. |
| `snic_label` | int | Raw SNIC superpixel hash. Use to cross-reference with the `snic_clusters` raster asset. |
| `cluster_id` | int | The k-means cluster (0 to k-1) that this superpixel was assigned to. |
| `area_ha` | float | Polygon area in hectares. |
| `perim_m` | float | Polygon perimeter in metres. |
| `n_pixels` | int | `area_m² / (analysis_scale_m)²`. Derived from area, consistent with `area_ha`. |

GeoJSON attributes: every SHP attribute, **plus** per-superpixel means
of every features_* band (ndvi_mean, ndvi_amplitude_annual, vv_p50,
canopy_height, elevation, etc.) — typically 25-30 additional columns.
Centroid lat/lon are also included for convenience.

#### `stands_dissolved`

SHP attributes:

| Field | Type | Meaning |
|---|---|---|
| `unit_id` | int | Sequential 1..M, after `vector_min_stand_pixels` filtering. Same lat-desc/lon-asc renumbering as stand_id; deterministic. |
| `cluster_id` | int | The k-means cluster ID this unit corresponds to. |
| `area_ha` | float | Polygon area in hectares. |
| `perim_m` | float | Polygon perimeter in metres. |
| `n_pixels` | int | Used by the min-pixel filter. |

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
the numbering changes. Use `snic_label` (raw SNIC hash) for stable
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
`config_fingerprint()` in `src/fmu/utils/caching.py`. It exists because the
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
thresholds are exactly what a run is iterating on.

Special property on `cluster_labels`: the asset carries a JSON-encoded
`clustering_metadata` property listing every preprocessing parameter
used to produce it (log offsets, scaling params, dropped bands, etc.).
The export stage reads it back to populate the manifest's `clustering`
section. To read it from a separate GEE script:

```python
import ee
import json
labels = ee.Image("projects/.../sanjay_van_baseline/clustering/cluster_labels")
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

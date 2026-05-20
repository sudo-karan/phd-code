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
    "snic_clusters":    "projects/.../sanjay_van_baseline/segmentation/snic_clusters",
    "snic_means":       "projects/.../sanjay_van_baseline/segmentation/snic_means",
    "cluster_labels":   "projects/.../sanjay_van_baseline/clustering/cluster_labels",
    "feature_stack":    "projects/.../sanjay_van_baseline/clustering/feature_stack"
  },
  "clustering": {
    "k": 6,
    "seed": 42,
    "n_training_samples": 5000,
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

Only present if `inspect_metrics.py` was run AND the config has
`metrics.reference_config_name` set to another config's name.

```json
{
  "current_config": "sanjay_van_nirv_dual",
  "k": 6,
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
  ]
}
```

### Interpreting the numbers

| Field | Meaning | Range / direction |
|---|---|---|
| `silhouette_current` | Intrinsic cohesion/separation of current clustering | -1 to 1; higher is better |
| `silhouette_reference` | Same for the reference (only if reference's `feature_stack` is cached) | -1 to 1; higher is better |
| `ari` | Adjusted Rand Index between current and reference partitions | -1 to 1; 0 = random, 1 = identical |
| `nmi` | Normalized Mutual Information | 0 to 1; higher = more information shared |
| `agreement_rate` | After Hungarian-matching cluster IDs, fraction of pixels that agree | 0 to 1; higher = more agreement |
| `correspondence` | Best mapping: `current_id -> reference_id` (Hungarian on confusion matrix) | k mappings |
| `confusion_matrix` | k x k pixel-overlap counts (rows = current, cols = reference) | non-negative ints |
| `n_samples_used` | Number of paired pixels used for ARI/NMI | int (target was `metrics.n_comparison_samples`) |

**How to read silhouette:** values around 0 indicate overlapping
clusters; values approaching 1 indicate well-separated, tight clusters.
A difference of 0.05 between variants is meaningful when the AOI is
heterogeneous; differences below 0.01 are noise.

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

## The cluster_labels GeoTIFF (in Google Drive)

The export stage submits a GeoTIFF export to your Drive:

- **Folder:** `fmu_exports/`
- **Filename:** `<config_name>_cluster_labels.tif`
- **Format:** `uint8`, single band
- **Values:** `0` to `k-1` (cluster IDs), with masked (non-habitat) pixels
  having the default uint8 nodata
- **Projection:** EPSG:4326 (GEE's default for export to Drive)
- **Pixel scale:** `export.analysis_scale_m` (default 10 m)

Submit-and-forget. The task ID is in the manifest. Monitor progress at
https://code.earthengine.google.com/tasks. Typical wait: 5-15 min.

### Loading in Python

```python
import rasterio
with rasterio.open("sanjay_van_baseline_cluster_labels.tif") as src:
    labels = src.read(1)              # numpy array, shape (H, W), dtype uint8
    bounds = src.bounds
    transform = src.transform
```

### Loading in QGIS

Drag-drop the `.tif`. Right-click, Properties, Symbology, Singleband
pseudocolor, discrete. Build a color ramp with k stops. Use
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
projects/<your-gcp-project>/assets/fmu/<config_name>/<stage_name>/<output_key>
```

Listed in `export_manifest_<config>.json` under `asset_paths`. Load any
of them in another GEE script via `ee.Image(path)`.

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

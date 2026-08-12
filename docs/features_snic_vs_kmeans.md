# Which features go where — SNIC vs k-means

Every band the pipeline computes, and whether it is used for **SNIC segmentation**
(drawing boundaries), **k-means clustering** (deciding what each region *is*), **both**,
or **neither** (computed as a diagnostic but never clustered).

Derived from the code, not from the decks:

| What | Source of truth |
|---|---|
| SNIC's input bands | `src/fmu/stages/segmentation.py` → `_SNIC_INPUT_BAND_NAMES` |
| Clustering's exclude-list | `src/fmu/stages/clustering.py` → `_EXCLUDE_BANDS` |
| Clustering's stack assembly | `src/fmu/stages/clustering.py` → `_build_raw_feature_stack()` |
| Cyclic (sin/cos) expansion | `src/fmu/stages/clustering.py` → `_decompose_cyclic_bands()` |
| Band names | `src/fmu/stages/features_{optical,radar,structure,static}.py` |

Counts below are for the `sanjay_van_baseline` config (NDVI, single harmonic, `include_trend: true`)
and the `sanjay_van_nirv_dual` variant (NIRv, dual harmonic). Verified against
`runs/sanjay_van_baseline_*/manifest.json`.

---

## 1. TL;DR

| Role | Count | Bands |
|---|---|---|
| **SNIC only** | 3 | `B4_median`, `B8_median`, `composite_nirv` |
| **Both SNIC and k-means** | 2 | `canopy_height`, `vv_minus_vh_median` |
| **k-means only** | 20 (baseline) | everything else in the clustering stack |
| **Neither** (diagnostic) | 3 | `*_obs_count`, `*_residual_variance`, `annual_rainfall` |

- **SNIC input: 5 bands** (fixed, identical across every config — the experimental control)
- **k-means input: 22 bands** (baseline) / **25 bands** (variant), after sin/cos expansion
- **AlphaEarth arm: 64 bands** (`A00`–`A63`) — replaces the whole hand-crafted stack for k-means only; SNIC is unchanged

---

## 2. SNIC — the 5 boundary bands

Defined in `segmentation.py::_SNIC_INPUT_BAND_NAMES`. All 10 m native, z-scored per band
over the ROI before SNIC (so `B4_median` at 0–3000 can't dominate `canopy_height` at 0–30).

| # | Band | Where it comes from | Axis | Also used by k-means? |
|---|---|---|---|---|
| 1 | `B4_median` | `s2_composite` (data_load) | Optical colour — red | **No** |
| 2 | `B8_median` | `s2_composite` (data_load) | Optical colour — NIR | **No** |
| 3 | `composite_nirv` | computed *inside* `segmentation.py` from B4/B8 | Optical productivity | **No** |
| 4 | `canopy_height` | `features_structure` | Vertical structure | **Yes** |
| 5 | `vv_minus_vh_median` | `features_radar` | Radar structure | **Yes** |

Two things worth knowing:

- **`B4_median`, `B8_median`, `composite_nirv` never reach k-means.** They come from the
  Sentinel-2 composite (and a derived NIRv), which is *not* one of the four feature images
  the clustering stack is assembled from. `composite_nirv` in particular is computed locally
  in `segmentation.py` — it is not the same thing as the optical `nirv_*` harmonic features.
- **`canopy_height` and `vv_minus_vh_median` are the only genuine overlap** — the same bands
  feed both boundary-drawing and cluster-assignment.

SNIC parameters (`configs/*.yaml → segmentation`): `size 10 · compactness 0.5 · connectivity 8 ·
neighbourhood 128`, held identical across configs.

---

## 3. k-means — the clustering stack

### 3.1 How the 22 is reached (baseline)

```
raw stack = optical_features + radar_features + structure_features + static_features
          = 6 + 9 + 3 + 5                                    = 23 bands
  − exclude-list (obs_count, residual_variance, annual_rainfall) = 20 bands
  + cyclic sin/cos expansion (ndvi_phase_annual, aspect: 2 → 4)  = 22 bands  ← what k-means sees
```

Variant (`nirv_dual`): optical is 8 instead of 6 (adds `amplitude_semi` + `phase_semi`),
and there are 3 cyclic bands instead of 2 → **25 bands**.

### 3.2 Optical — `features_optical.py`

Prefix is `ndvi` (baseline) or `nirv` (variant).

| Band | In k-means? | Note |
|---|---|---|
| `<idx>_mean` | ✅ | overall greenness level (`a`) |
| `<idx>_amplitude_annual` | ✅ | yearly swing, √(b²+c²) |
| `<idx>_phase_annual` | ✅ *(as sin/cos)* | cyclic → replaced by `_sin` + `_cos` |
| `<idx>_trend` | ✅ | inter-annual greening/browning (`f`) |
| `<idx>_amplitude_semi` | ✅ *(variant only)* | dual-harmonic only |
| `<idx>_phase_semi` | ✅ *(variant only, as sin/cos)* | cyclic |
| `<idx>_residual_variance` | ❌ **excluded** | harmonic fit-quality diagnostic, not ecology |
| `<idx>_obs_count` | ❌ **excluded** | metadata (observation density) |

### 3.3 Radar — `features_radar.py` (9 bands, all clustered)

| Band | In k-means? | In SNIC? |
|---|---|---|
| `vv_p10`, `vv_p50`, `vv_p90` | ✅ | ❌ |
| `vh_p10`, `vh_p50`, `vh_p90` | ✅ | ❌ |
| `vv_iqr` (= p90 − p10) | ✅ | ❌ |
| `vh_iqr` (= p90 − p10) | ✅ | ❌ |
| `vv_minus_vh_median` | ✅ | ✅ **both** |

> Naming note: `vv_iqr` / `vh_iqr` keep the historical name but are computed as **p90 − p10**
> (temporal spread), not a true interquartile range.

### 3.4 Structure — `features_structure.py` (3 bands, all clustered)

| Band | In k-means? | In SNIC? |
|---|---|---|
| `canopy_height` | ✅ | ✅ **both** |
| `canopy_height_std` (3×3) | ✅ | ❌ |
| `canopy_height_max` (3×3) | ✅ | ❌ |

### 3.5 Static — `features_static.py` (5 bands, 4 clustered)

| Band | In k-means? | Note |
|---|---|---|
| `elevation` | ✅ | |
| `slope` | ✅ | |
| `aspect` | ✅ *(as sin/cos)* | cyclic → `aspect_sin` + `aspect_cos` |
| `distance_to_water` | ✅ | capped at 1000 px |
| `annual_rainfall` | ❌ **excluded** | CHIRPS ~5.5 km ⇒ near-constant inside the AOI |

### 3.6 The exact 22 bands k-means sees (baseline)

After exclusions and sin/cos expansion:

```
ndvi_mean, ndvi_amplitude_annual, ndvi_trend,
ndvi_phase_annual_sin, ndvi_phase_annual_cos,
vv_p10, vv_p50, vv_p90, vh_p10, vh_p50, vh_p90,
vv_iqr, vh_iqr, vv_minus_vh_median,
canopy_height, canopy_height_std, canopy_height_max,
elevation, slope, distance_to_water,
aspect_sin, aspect_cos
```

Preprocessing applied before k-means (in order): cyclic sin/cos → log-transform of
right-skewed bands (skewness > 1.0) → robust median/IQR scaling → standardise.
Then `k = 6`, `seed = 42`, 10,000-superpixel training sample, on **superpixel means**
(not pixels).

---

## 4. Computed but never clustered

These three exist in the exports/profiles but are dropped by
`clustering.py::_EXCLUDE_BANDS` before k-means:

| Band | Why excluded |
|---|---|
| `ndvi_obs_count` / `nirv_obs_count` | Metadata — observation density, not a property of the forest |
| `ndvi_residual_variance` / `nirv_residual_variance` | Harmonic **fit-quality** diagnostic; clustering on it would split identical phenology by noise (cloud, sparse observations) rather than ecology |
| `annual_rainfall` | Near-constant within a small AOI (CHIRPS ≈ 5.5 km cells); kept in `features_static` for cross-AOI generality |

---

## 5. Profiling sees a slightly different set (24 bands)

`profiling.py` has its **own, smaller** exclude-list — only `*_obs_count`. So the per-cluster
profiles (`cluster_profiles.csv`) describe **24** bands for the baseline: the 22 k-means bands
**plus** `ndvi_residual_variance` and `annual_rainfall`, reported for interpretation only.

| Stage | Excludes | Baseline band count |
|---|---|---|
| SNIC (`segmentation.py`) | — (explicit 5-band whitelist) | **5** |
| k-means (`clustering.py`) | obs_count, residual_variance, annual_rainfall | **22** |
| Profiling (`profiling.py`) | obs_count only | **24** |

---

## 6. The embedding arm (AlphaEarth)

When `clustering.feature_source: embedding`:

- **k-means input** becomes the 64 embedding bands `A00 … A63` — the entire hand-crafted
  stack is replaced (the `features_optical` and `features_static` stages don't even run).
- **SNIC input is unchanged** — still the same 5 bands, still byte-identical. This is exactly
  what makes the baseline-vs-AlphaEarth comparison controlled: only the clustering feature
  vector differs.
- No exclude-list and no cyclic decomposition apply (there are no metadata or angular bands).

---

## 7. Why the split exists

SNIC and k-means do different jobs, so they get different inputs:

- **SNIC only draws boundaries** — where the landscape changes. It uses a deliberately reduced,
  high-SNR set for four reasons: **redundancy** (correlated bands let the sensor with the most
  columns dominate the distance), **noise** (phase/trend/residual-variance/IQR bands would make
  SNIC carve superpixels around fitting artifacts), **dimensionality** (SNIC trades feature
  distance against a spatial-compactness term; more bands swamp the spatial term), and
  **experimental control** (boundaries must be identical across configs, so the band set must
  be fixed and must not include the variant's extra harmonics).
- **k-means decides what each region is** — that is where the full stack belongs.

**Caveat:** the exact five SNIC bands were chosen by reasoning, **not ablated** against some other
four or six. Same status as the SNIC parameters and `k = 6` — it sits under the open
"no sensitivity analysis" gap, and the planned test is full-stack vs reduced-stack scored with
ARI/NMI at **both** AOIs (Sanjay Van and Mudumalai).

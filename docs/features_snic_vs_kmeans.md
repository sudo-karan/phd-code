# Which features go where — SNIC vs k-means

Every band the pipeline computes, and whether it is used for **SNIC segmentation**
(drawing boundaries), **k-means clustering** (deciding what each region *is*), **both**,
or **neither** (computed as a diagnostic but never clustered).

Derived from the code, not from the decks:

| What | Source of truth |
|---|---|
| SNIC's input bands | `configs/*.yaml` → `segmentation.input_bands`, defaulting to `_DEFAULT_SNIC_INPUT_BANDS` in `src/fmu/config.py` |
| Clustering's exclude-list | `src/fmu/stages/clustering.py` → `_EXCLUDE_BANDS` |
| Clustering's stack assembly | `src/fmu/stages/clustering.py` → `_build_raw_feature_stack()` |
| Cyclic (sin/cos) expansion | `src/fmu/stages/clustering.py` → `_decompose_cyclic_bands()` |
| Band names | `src/fmu/stages/features_{optical,radar,structure,static}.py` |

Counts below are for the `sanjay_van_baseline` config (NDVI, single harmonic, `include_trend: true`)
and the `sanjay_van_nirv_dual` variant (NIRv, dual harmonic). Verified against
`runs/sanjay_van_baseline_*/manifest.json`.

---

## 1. TL;DR

For the **hand-crafted baseline** arm:

| Role | Count | Bands |
|---|---|---|
| **SNIC only** | 3 | `B4_median`, `B8_median`, `canopy_height_std` |
| **Both SNIC and k-means** | 3 | `canopy_height`, `vv_minus_vh_median`, `ndvi_amplitude_annual` |
| **k-means only** | 19 (baseline) | everything else in the clustering stack |
| **Neither** (diagnostic) | 3 | `*_obs_count`, `*_residual_variance`, `annual_rainfall` |

- **SNIC input: 6 bands** in the baseline arm — but this is **config-driven, not fixed**
  (`segmentation.input_bands`), and it is **not** the same across arms any more.
- **k-means input: 22 bands** (baseline) / **25 bands** (variant), after sin/cos expansion
- **AlphaEarth arm: 64 bands** (`A00`–`A63`) for **both** SNIC and k-means — the embedding
  replaces the hand-crafted stack everywhere, and the hand-crafted feature stages do not run
  at all.

> **This reverses the earlier design**, in which SNIC was held byte-identical across arms and
> that was called the experiment's control. See §6 and §7 for why.

---

## 2. SNIC — the boundary bands

Set by `segmentation.input_bands` in config; the default (`_DEFAULT_SNIC_INPUT_BANDS` in
`src/fmu/config.py`) is what the baseline arm uses and is **not** repeated in
`sanjay_van_baseline.yaml`, so the default and the shipped experiment cannot drift apart.

All 10 m native. Two normalisation steps run before SNIC:

1. **z-score per band** over the ROI, so `B4_median` at 0–3000 can't dominate
   `canopy_height` at 0–30 (`segmentation.normalize_inputs`).
2. **divide by the RMS 4-neighbour feature distance** over the ROI
   (`segmentation.normalize_distance_scale`). SNIC trades a summed squared colour distance
   against a spatial-compactness term, and that sum grows with the number of *effective* axes
   — so `compactness: 0.5` in a 6-band arm and a 64-band arm would buy very different spatial
   weights. Dividing by √n_bands would assume the bands are independent; for an embedding they
   are not, and it over-corrects. The empirical RMS distance handles band count and correlation
   together. The value used is recorded in the manifest as `distance_scale`.

**Baseline arm (the default), 6 bands over ~four independent axes:**

| # | Band | Where it comes from | Axis | Also used by k-means? |
|---|---|---|---|---|
| 1 | `B4_median` | `s2_composite` (data_load) | Optical colour — red | **No** |
| 2 | `B8_median` | `s2_composite` (data_load) | Optical colour — NIR | **No** |
| 3 | `canopy_height` | `features_structure` | Vertical structure | **Yes** |
| 4 | `canopy_height_std` | `features_structure` | Canopy completeness — separates a smooth plantation-like canopy from a gap-rich natural one at the same mean height | **No** |
| 5 | `ndvi_amplitude_annual` | `features_optical` | Phenology — the deciduous/evergreen axis | **Yes** |
| 6 | `vv_minus_vh_median` | `features_radar` | Radar structure (sensor-independent) | **Yes** |

**AlphaEarth / Tessera arm:** `- {source: embedding_features, band: "*"}` — every embedding
dimension. `"*"` expands server-side at run time, so it keeps working if the embedding's
dimensionality changes.

Notes:

- **`composite_nirv` was dropped from the default.** It is `(B8/10000) × NDVI`, an algebraic
  function of `B4` and `B8`, so carrying all three spent three columns on two degrees of
  freedom and inflated optical weight in SNIC's distance metric. It remains *available* —
  declare `{source: s2_composite, band: composite_nirv}` and `segmentation.py` computes it.
- **`ndvi_amplitude_annual` was added.** SNIC runs on a multi-year *median* composite, so
  without a phenology band it sees no seasonality at all, and cannot separate deciduous from
  evergreen stands of similar height and colour.
- **`B4_median` and `B8_median` never reach k-means.** They come from the Sentinel-2
  composite, which is not one of the four feature images the clustering stack is assembled
  from.
- **The `nirv_dual` arm must spell its stack out.** `features_optical.index: nirv` renames the
  harmonic bands `nirv_*`, so the default's `ndvi_amplitude_annual` does not exist there. A
  config-load validator rejects that mismatch rather than letting it surface as a GEE
  band-not-found error partway through a paid run.

SNIC parameters (`configs/*.yaml → segmentation`): `size 10 · compactness 0.5 · connectivity 8 ·
neighbourhood 128`, held identical across configs. It is the *feature space*, not the
hyperparameters, that differs between arms.

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
| SNIC (`segmentation.input_bands`) | — (explicit config whitelist) | **6** (baseline default) |
| k-means (`clustering.py`) | obs_count, residual_variance, annual_rainfall | **22** |
| Profiling (`profiling.py`) | obs_count only | **24** |

---

## 6. The embedding arm (AlphaEarth)

`configs/sanjay_van_alphaearth.yaml` is a **fully independent pipeline**, not a variant of the
baseline:

- **k-means input** becomes the 64 embedding bands `A00 … A63`.
- **SNIC input** becomes the same 64 bands (`{source: embedding_features, band: "*"}`).
- Consequently **none of the hand-crafted feature stages run** — not `features_optical`, not
  `features_static`, and (unlike before) not `features_radar` or `features_structure` either.
  `default_stage_names()` derives the stage list from the union of what clustering and
  segmentation actually ask for, so this follows from config rather than from a hardcoded branch.
- No exclude-list and no cyclic decomposition apply (there are no metadata or angular bands).

**Why this changed.** Under the merge design, SNIC + `merge` *produces the stand* — clustering
is demoted to attaching a type label to a finished stand. Holding SNIC identical across arms
therefore reduced the embedding arm to *"which labels does k-means give inside boundaries the
hand-crafted stack drew"*. The delineation question — which representation finds better stand
boundaries — is the thesis question, and the old design never actually put it to the embedding.

**What is still controlled:** everything that is not the feature representation — same AOI,
same 2017–2022 window, same SNIC hyperparameters, same `k = 6` / `seed = 42`, same merge rules,
same masking, same analysis scale. And `normalize_distance_scale` makes `compactness: 0.5` mean
the same thing at 6 bands and at 64.

**What this costs:** the two arms now produce two *different stand maps*, so ARI/NMI against a
shared tessellation is no longer the comparison. There is **no ground truth**, so neither map
can be declared correct. They are compared on stability (shifted-window, leave-one-year-out),
held-out predictive power (R² at matched stand count) and geometry — never on agreement with a
reference.

---

## 7. Why the split exists

SNIC and k-means do different jobs, so in the hand-crafted arm they get different inputs:

- **SNIC + merge produce the stand** — the deliverable. In the hand-crafted arm it uses a
  deliberately reduced, high-SNR set for three reasons: **redundancy** (correlated bands let
  the sensor with the most columns dominate the distance — the reason `composite_nirv` was
  dropped), **noise** (phase/trend/residual-variance/IQR bands would make SNIC carve
  superpixels around fitting artifacts), and **dimensionality** (SNIC trades feature distance
  against a spatial-compactness term; more bands swamp the spatial term unless the distance
  scale is normalised, which is what `normalize_distance_scale` now does).
- **k-means attaches a type label** to a finished stand — that is where the full stack belongs.

Note the fourth reason that used to be listed here — **experimental control**, "boundaries must
be identical across configs" — is **no longer operative**, and was in fact the flaw: it made the
band set an unquestionable constant and kept the delineation question away from the embedding
arm entirely. The band set is now `segmentation.input_bands`, a first-class experimental
variable, which is why it moved out of a code literal and into config.

**Caveat:** the six baseline SNIC bands were chosen by reasoning, **not ablated** against some
other five or seven. Same status as the SNIC parameters and `k = 6` — it sits under the open
"no sensitivity analysis" gap. Now that the band set is config-driven, the ablation is a set of
YAML files rather than a code change; scored on held-out R² at matched stand count and on
stability, **not** on ARI against a reference tessellation (there isn't one).

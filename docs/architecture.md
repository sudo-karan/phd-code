# Architecture

How the code is organized internally: the Stage contract, the
PipelineContext, the registry, the caching layer, and how to add or
swap a module. For why the architecture is this shape, see
[design_notes.md](design_notes.md). For what each stage does, see
[current_flow.md](current_flow.md).

## Source tree

```
src/fmu/
├── __init__.py          (pipeline version)
├── config.py            Pydantic schema for configs (one model per block)
├── settings.py          .env-driven per-machine settings (threading-safe singleton)
├── pipeline.py          Pipeline orchestrator: walks stages, caches, manifest
├── stages/
│   ├── __init__.py
│   ├── base.py          Stage abstract class, PipelineContext, StageResult, registry
│   ├── masking.py
│   ├── data_load.py
│   ├── features_optical.py
│   ├── features_radar.py
│   ├── features_structure.py
│   ├── features_static.py
│   ├── features_embedding.py  (optional embedding feature source; see clustering.feature_source)
│   ├── segmentation.py
│   ├── merge.py         SNIC superpixels -> forest stands (Xiong et al. 2024)
│   ├── clustering.py
│   ├── profiling.py
│   ├── export.py
│   └── metrics.py
└── utils/
    ├── __init__.py
    ├── gee.py           init_gee, safe_get_info, safe_call, load_roi_geometry, asset_path
    ├── logging.py       init_logging, per-run dir, Rich + file handler
    ├── caching.py       cached_asset_path, asset_exists, start_export, load_cached_image
    ├── components.py    guards around reduceConnectedComponents' silent maxSize masking
    ├── adjacency.py     pulls the superpixel region-adjacency graph out of GEE
    └── region_merge.py  Xiong's two-pass merge, pure Python (no ee import)
```

Plus:

```
tests/                   Per-stage live tests (`*_live.py`) + unit tests
scripts/                 inspect_*.py, one per stage, drives the pipeline
configs/                 YAML configs
aois/                    GeoJSON polygons
docs/                    This documentation
```

## The three concepts you have to know

### 1. `Stage` (abstract base class)

Defined in `src/fmu/stages/base.py`. Every concrete stage extends it
and declares four things:

```python
@register_stage("clustering")
class ClusteringStage(Stage):
    name = "clustering"
    required_inputs = {"roi", "habitat_mask"}  # invariant subset; validate() adds the feature source's keys AND the unit key
    produces = {"cluster_labels", "feature_stack"}
    cacheable_outputs = {"cluster_labels", "feature_stack"}

    def run(self, ctx: PipelineContext, config: Config) -> StageResult:
        ...
```

- **`name`**: unique identifier, used by the orchestrator to look up the
  class and to construct cache asset paths.
- **`required_inputs`**: set of context keys the stage reads. Validated
  by the orchestrator before calling `run()`. Failure raises `KeyError`.
- **`produces`**: set of context keys the stage writes. The orchestrator
  validates that `run()` actually produces exactly these keys (no more,
  no less) and refuses to continue otherwise.
- **`cacheable_outputs`**: subset of `produces` that can be cached as
  GEE assets. Defaults to "cache everything in produces" if not declared;
  declare `set()` to opt out entirely; declare a non-empty subset for
  mixed-output stages.
- **`run(ctx, config) -> StageResult`**: the actual logic. Reads from `ctx`,
  reads from `config`, returns `StageResult(outputs={...}, metadata={...},
  warnings=[...])`.

The optional `validate(ctx, config)` method runs before `run()`. The
default checks that every `required_inputs` key is present in the
context; override to add custom checks (e.g., projection sanity).
`ClusteringStage` uses this to require its feature-source-specific inputs
on top of the invariant `required_inputs`: the four hand-crafted feature
images when `clustering.feature_source == "handcrafted"`, or the single
`embedding_features` image (from `features_embedding`) when `"embedding"`.
Keeping `required_inputs` static and branching in `validate()` means an
embedding run isn't forced to produce the hand-crafted stack it never uses.

It also checks the **unit key** the same way. Which label image a stage reduces
over — `stand_clusters` when the merge stage runs, `snic_clusters` when it does
not — comes from `Config.unit_label_key()`, one definition shared by clustering
and metrics. A static class attribute cannot see the config, and a silhouette
over stands next to a profile over superpixels is not comparable in a way any
number would reveal.

`SegmentationStage` and `MergeStage` do the same for their config-declared band
sources (`segmentation.input_bands`, `merge.criteria`).

### 2. `PipelineContext`

Shared dict-like state between stages. Defined in `base.py`.

```python
ctx = PipelineContext()
ctx.set("roi", roi_geometry)
ctx.set("habitat_mask", masking_image)   # write-once
ctx.has("habitat_mask")                  # True
ctx.get("habitat_mask")                  # the image
```

**Write-once invariant:** calling `ctx.set("habitat_mask", ...)` again
raises `KeyError`. This enforces "every context key has exactly one
producing stage". Accidental clobbering is caught at runtime, not
silently swallowed.

To pre-populate (e.g., load `roi` before the pipeline runs), call
`ctx.set("roi", ...)` once before passing the context into `Pipeline.run()`.

### 3. Stage registry

A module-level dict in `base.py` mapping `name` to class. Populated by the
`@register_stage("name")` decorator.

```python
from fmu.stages.base import get_stage_class
cls = get_stage_class("clustering")     # ClusteringStage
```

**Importing a stage module triggers registration.** So the inspect
scripts (and the smoke test) have to `import` every stage module before
calling `Pipeline(stage_names=[...])`. The orchestrator's eager
resolution then catches typos at construction time, not after 10
minutes of GEE work:

```python
Pipeline(stage_names=["maskng"])   # KeyError immediately
```

## The orchestrator

`Pipeline` lives in `src/fmu/pipeline.py`. ~330 lines, single class.

### Construction

```python
Pipeline(stage_names=["masking", "data_load", ...], use_cache=True)
```

Resolves each name via the registry and stores the class list. Caching
is opt-in (default `False`).

The canonical stage order is composed by `default_stage_names(config)` in
`pipeline.py`, which branches on `config.clustering.feature_source`:

- **`"handcrafted"`** (default): `masking`, `data_load`, `features_optical`,
  `features_radar`, `features_structure`, `features_static`, `segmentation`,
  `clustering`, `metrics`.
- **`"embedding"`**: asks for `features_embedding` alone.

That is only part of the input. `default_stage_names()` takes the **union of
three independent consumers**: clustering (via `feature_source`, above),
segmentation (via `segmentation.input_bands`), and merge (via
`merge.criteria`) — the latter two name their sources explicitly.

The shipped embedding configs segment on the embedding as well as cluster on it,
so `features_radar` and `features_static` drop out. `features_optical` and
`features_structure` remain, because the merge criteria are held identical
across arms and read `canopy_height`, `canopy_height_std` and
`ndvi_amplitude_annual`. A config that clustered on the embedding but segmented
on hand-crafted bands would pull the other stages back in automatically.

Segmentation is **not** held identical across arms. Under the merge design SNIC
+ `merge` produces the stand and clustering only attaches a type label, so a
shared tessellation would have reduced the embedding arm to "which labels does
k-means give inside boundaries the hand-crafted stack drew" — never putting the
delineation question to the embedding. What is controlled is everything that is
not the feature representation: SNIC hyperparameters, `k`, `seed`, masking,
analysis scale, merge rules.

Callers still pass the resulting list explicitly to `Pipeline(...)` (and must
import the stage modules so `@register_stage` has run).

### Execution

`Pipeline.run(config, run_dir, initial_context)` loops over the stage
classes. For each stage:

1. Instantiate it (`stage_cls()`).
2. Call `stage.validate(ctx, config)`. Fails fast on missing inputs.
3. If `use_cache=True`:
   a. Check each cacheable output's asset path via `asset_exists`.
   b. If all cacheable outputs hit AND `cacheable == produces`, skip the
      live run entirely; load the cached assets into context; mark the
      stage record with `metadata.source = "cache"`.
4. Otherwise: call `stage.run(ctx, config)`.
5. Validate that `result.outputs.keys() == stage.produces` (output
   contract); raise `ValueError` if not.
6. Merge cache hits into the result (prefer cached version for downstream).
7. Write all outputs to `ctx`.
8. If `use_cache=True`: submit async export tasks for any cacheable
   outputs that missed the cache.

After all stages, write `run_dir/manifest.json` summarizing every
stage's runtime, produced keys, cache status, export tasks, and the
full input config.

### Resolving `cacheable_outputs`

Subtle but important. The orchestrator walks the MRO when deciding
which set to use:

```python
@staticmethod
def _resolve_cacheable_outputs(stage: Stage) -> set[str]:
    for klass in type(stage).__mro__:
        if klass is Stage:
            break
        if "cacheable_outputs" in klass.__dict__:
            return klass.__dict__["cacheable_outputs"]
    return stage.produces
```

This matters because subclasses (e.g., test mocks like `_SmokeExport(ExportStage)`)
inherit `cacheable_outputs` from the parent without redeclaring it.
A naive `"cacheable_outputs" in stage.__class__.__dict__` would miss
the inherited declaration and incorrectly default to "cache everything".

Regression test: `tests/test_pipeline.py::test_subclass_inherits_cacheable_outputs`.

## The caching layer

`src/fmu/utils/caching.py`. Three operations:

| Function | What it does |
|---|---|
| `cached_asset_path(config_name, stage_name, key, fingerprint)` | Build a deterministic GEE asset path: `{asset_root}/{config_name}/{stage_name}/{key}__{fingerprint}` |
| `config_fingerprint(config)` | Short hash of the config content that can change a cached raster, so editing a threshold does not silently reuse the old asset |
| `asset_exists(path) -> bool` | True if the asset exists. Tries the underlying HttpError status (401/403 propagates, 404 returns False), falls back to message-text matching for older GEE client versions |
| `start_export(image, asset_path, roi, scale)` | Submit an async export-to-asset task; return `ExportTaskInfo(task_id, asset_path, description)` |
| `load_cached_image(path) -> ee.Image` | Trivial wrapper for `ee.Image(path)` |

**Stages don't know about caching.** They just produce `ee.Image`
outputs as usual; the orchestrator wraps cache check / export around
each `run()` call.

### Asset path format

```
projects/<gcp-project>/assets/fmu/<config_name>/<stage_name>/<output_key>
```

Stable across runs. Same config name + same output key always maps to
the same asset. Changing config thresholds without renaming the config
overwrites the asset. See [running.md](running.md#stable-paths-not-hashes).

### What's cacheable

Only `ee.Image` outputs can be cached as GEE assets. So:

- `ee.ImageCollection` outputs (e.g., `data_load.s2_collection`) are NOT
  cacheable. They get rebuilt every run (cheap, filtering is metadata).
- Python dicts (e.g., `profiling.cluster_profiles`, `export.export_manifest`,
  `metrics.comparison_metrics`) are NOT cacheable. The producing stages
  declare `cacheable_outputs = set()` to opt out.
- Images that exist on disk but not in GEE (none in this pipeline) would
  also not be cacheable via this layer.

`data_load` is the canonical mixed case. It declares
`cacheable_outputs = {"s2_composite"}` even though `produces =
{"s1_collection", "s2_collection", "s2_composite"}`.

### Export inventory in the manifest

`src/fmu/stages/export.py::_inventory_cached_assets` walks the stage
registry, asks each stage for its `cacheable_outputs` (via the same MRO
helper the orchestrator uses), and probes each path. Whatever exists
goes into the manifest's `asset_paths`. The list is dynamic and never
goes stale.

## How a stage typically runs

Anatomy of a stage's `run()` method, using `ClusteringStage` as an example:

```python
@safe_call("running k-means clustering")
def run(self, ctx: PipelineContext, config: Config) -> StageResult:
    # 1. Pull inputs from context
    roi = ctx.get("roi")
    snic_clusters: ee.Image = ctx.get("snic_clusters")
    habitat_mask: ee.Image = ctx.get("habitat_mask")
    params = config.clustering

    # 2. Server-side GEE computation
    raw_stack = _build_raw_feature_stack(...)
    decomposed, log = _decompose_cyclic_bands(raw_stack)
    ...

    # 3. Materialize anything you need with safe_get_info
    skewed_bands = _identify_skewed_bands(sample, candidate_bands, ...)

    # 4. Return outputs
    return StageResult(
        outputs={"cluster_labels": labels, "feature_stack": stack},
        metadata={"k": params.k, "n_active_bands": len(active_bands)},
    )
```

Three patterns to follow:

1. **`@safe_call("description")`** decorator wraps the whole method so
   any GEE error gets a useful context label. The wrapping is in
   `utils/gee.py`.

2. **`safe_get_info(server_obj, context="...")`** is the only sanctioned
   way to call `.getInfo()` (i.e., to materialize a server-side value to
   the client). Same wrapping reason: GEE errors fire at materialization,
   not at construction, and `safe_get_info` attaches the context label.

3. **Step helpers** (`_build_raw_feature_stack`, `_decompose_cyclic_bands`,
   etc.) at module level. Keeps `run()` itself a thin coordinator;
   individual steps are testable in isolation.

## Two-tier testing

| Tier | Command | What it tests | Auth needed |
|---|---|---|---|
| Fast | `pytest` | Pure Python: config schema, pipeline orchestrator with mocked stages, registry, base classes, utility functions, export inventory | None |
| Live | `pytest -m live_gee` | Each stage against real GEE: actual asset loads, actual GEE computations | `earthengine authenticate` |

**CI runs only the fast tier.** Live tests are run locally before
locking a stage. Both must pass before a `MODULES.md` row flips to Locked.

Per-stage test files: `tests/test_<stage>_live.py`. End-to-end
chain test: `tests/test_pipeline_smoke_live.py`. Uses the cache layer
and skips if baseline assets aren't populated. Runs all 10 production
stages back-to-back and asserts which ones came from cache vs ran live.

## Adding a new stage

Concrete example: add `features_canopy_volume` between `features_structure`
and `features_static`.

1. **Create the module** `src/fmu/stages/features_canopy_volume.py`:

   ```python
   from __future__ import annotations
   from typing import ClassVar
   import ee
   from fmu.config import Config
   from fmu.stages.base import PipelineContext, Stage, StageResult, register_stage
   from fmu.utils.gee import safe_call

   @register_stage("features_canopy_volume")
   class FeaturesCanopyVolumeStage(Stage):
       name = "features_canopy_volume"
       required_inputs: ClassVar[set[str]] = {"roi", "structure_features"}
       produces: ClassVar[set[str]] = {"canopy_volume_features"}
       # cacheable_outputs defaults to produces, caches everything

       @safe_call("computing canopy volume features")
       def run(self, ctx: PipelineContext, config: Config) -> StageResult:
           canopy = ctx.get("structure_features").select("canopy_height")
           volume = canopy.multiply(...)  # your logic here
           return StageResult(
               outputs={"canopy_volume_features": volume},
               metadata={"n_bands": 1},
           )
   ```

2. **Add config knobs (if any)** to `src/fmu/config.py`:

   ```python
   class FeaturesCanopyVolumeParams(BaseModel):
       model_config = ConfigDict(extra="forbid")
       integration_height: float = Field(default=2.0, gt=0)

   class Config(BaseModel):
       ...
       features_canopy_volume: FeaturesCanopyVolumeParams = Field(
           default_factory=FeaturesCanopyVolumeParams
       )
   ```

3. **Add a live test** at `tests/test_features_canopy_volume_live.py`,
   mirroring `tests/test_features_structure_live.py`.

4. **Add an inspect script** at `scripts/inspect_features_canopy_volume.py`,
   importing every stage up to and including the new one.

5. **Update `docs/current_flow.md`** with a section describing the new stage,
   its inputs/outputs, datasets, and config knobs.

6. **Wire it into the pipeline run order**. Update the `FULL_PIPELINE_STAGES`
   constant in `tests/test_pipeline_smoke_live.py` if the new stage should
   be part of the smoke test, and update any inspect scripts whose
   downstream stages now depend on it.

## Swapping an existing stage

Two ways:

### A. Subclass and re-register

```python
from fmu.stages.clustering import ClusteringStage
from fmu.stages.base import _stage_registry

class MyClusteringVariant(ClusteringStage):
    name = "clustering"   # keep the same name, orchestrator looks up by name
    def run(self, ctx, config):
        # custom logic
        ...

# Replace registry entry before constructing Pipeline
_stage_registry["clustering"] = MyClusteringVariant
```

The smoke test uses this pattern via `monkeypatch.setitem` to swap
`ExportStage` for a no-Drive-submission variant.

### B. New module, new name, new config

If the new stage is a substantial rewrite, give it a different `name`
and don't replace the original:

```python
@register_stage("clustering_hdbscan")
class HDBSCANClusteringStage(Stage):
    name = "clustering_hdbscan"
    required_inputs: ClassVar[set[str]] = {...}
    produces: ClassVar[set[str]] = {"cluster_labels"}    # same key downstream
    ...
```

Then pick stages by name in `Pipeline(stage_names=[..., "clustering_hdbscan", ...])`.
This is the pattern when you want both versions runnable for comparison.

## Adding a new utility

Utilities in `src/fmu/utils/` are shared across stages. Three live there
today:

- `gee.py`: GEE init, safe wrappers, asset path, ROI loader
- `logging.py`: per-run dir, Rich + file handler
- `caching.py`: cache primitives used by the orchestrator

Add new utilities here when you have logic shared between two or more
stages. If it's used by exactly one stage, keep it in that stage's
module as a private `_helper`.

## Where to put what

| You want to ... | Put it in |
|---|---|
| Add a config field | `src/fmu/config.py` |
| Change a default value | `src/fmu/config.py` (field default) |
| Add a new dataset reference | `Config.datasets` + `configs/*.yaml` |
| Add a stage | `src/fmu/stages/<new_stage>.py` |
| Add a helper used by multiple stages | `src/fmu/utils/<helper>.py` |
| Add a helper used by one stage | private `_function` in that stage's module |
| Change cache path format | `src/fmu/utils/caching.py::cached_asset_path` |
| Change orchestrator behavior | `src/fmu/pipeline.py` |
| Add an inspection / driver | `scripts/inspect_<thing>.py` |
| Add fast tests | `tests/test_<module>.py` (no `_live` suffix) |
| Add live tests | `tests/test_<stage>_live.py` (with `pytestmark = pytest.mark.live_gee`) |
| Document why | `docs/design_notes.md` |
| Document what + flow | `docs/current_flow.md` |
| Document how to run | `docs/running.md` |
| Document outputs | `docs/outputs.md` |

## Decision logging

When a non-trivial change goes into the locked baseline, it gets a
`DEC-NNN` (scientific decision) or `ENG-NNN` (engineering decision)
entry in `phd-notebook/decisions.md` (a sibling repo). The export
stage's manifest records the source of truth path (`decisions_source`);
it doesn't enumerate the IDs (they'd drift).

Soft rule: if a future-you would ask "why does the code do this?", and
the answer isn't obvious from the code or design_notes, it deserves a
decisions.md entry.

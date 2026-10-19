"""Asset caching for stage outputs. See docs/design_notes.md, MODULES.md.

Stage outputs (ee.Image) can be cached as GEE assets at stable paths derived
from (config name, stage name, output key). Subsequent runs reuse the asset
instead of recomputing; visualization in the Code Editor reads the static
raster instead of recomputing live (which avoids per-tile memory limits).

Three operations:
  - cached_asset_path(config_name, stage, key) to stable asset path
  - asset_exists(path) to bool
  - start_export(image, path, roi, scale) to submit async export task

The orchestrator wires these together. On cache miss, the stage runs live
and the export task starts in the background; the live output is returned
so the run doesn't block. Subsequent runs find the asset.

Two cache layouts (round 9, issue #44 items 1 and 2), told apart by the names of
their assets:

  legacy    `{key}__{config_fingerprint}`: one fingerprint over most of the
            config, and every asset exported with no CRS, so Earth Engine writes
            a computed image on a geographic grid. Every run before 17 Oct 2026
            used it, and a config whose cache already holds such an asset keeps
            it, so that the record of those runs can still be read.
  per_step  `{key}__s{step key}`: one key per step, over what that step reads
            (`STEP_SETTINGS`, and the keys of the steps whose outputs it reads),
            and every asset exported on the analysis grid segmentation uses (the
            ROI's UTM zone at export.analysis_scale_m; fmu.utils.grid). Cached
            and live features are then the same pixels.

`fmu.pipeline.cache_layout_for` decides which a config uses.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import ee

from fmu.utils.gee import asset_path
from fmu.utils.logging import get_logger

log = get_logger(__name__)


# Config blocks whose contents can change a stage's raster output, and so must
# change its cache key. Everything NOT listed here is declared unable to affect
# a cached asset -- see `_CACHE_IRRELEVANT_BLOCKS`. A completeness test asserts
# the two sets together cover every top-level field, so adding a config block
# without deciding which side it falls on fails the suite rather than silently
# reintroducing stale-cache bugs.
_CACHE_RELEVANT_BLOCKS: frozenset[str] = frozenset(
    {
        "roi",
        "dates",
        "datasets",
        "cloud_mask",
        "data_load",
        "masking",
        "features_optical",
        "features_radar",
        "features_structure",
        "features_static",
        "features_embedding",
        "features",
        "segmentation",
        "merge",
        "clustering",
        "normalization",
    }
)

# Blocks that provably cannot change a cached asset:
#   name/description  identity, not content (name is already in the path)
#   metrics           a pure consumer; the stage declares no cacheable outputs
#   k_elbow           read only by the k_elbow step, which is cached under the
#                     per-step layout only (its stage refuses the legacy one), so
#                     no asset of the legacy layout can depend on it
_CACHE_IRRELEVANT_BLOCKS: frozenset[str] = frozenset(
    {"name", "description", "metrics", "k_elbow"}
)

# `export` is split: analysis_scale_m governs every reduction and every export
# resolution, so it belongs in the fingerprint. The rest is output plumbing
# (Drive folder, formats, which layers to emit) and changing it should not throw
# away an expensive raster.
_CACHE_RELEVANT_EXPORT_FIELDS: tuple[str, ...] = ("analysis_scale_m",)

# Settings added after assets had been cached, keyed (block, field) -> default.
# The fingerprint is taken over the dumped config, defaults included, so a new
# field in a relevant block changes the fingerprint of every config at once and
# their saved assets can no longer be found by name. A field listed here is left
# out of the hash while it holds its default, which is by definition the
# behaviour the saved assets were made with; any other value is hashed, so a
# config that switches the setting on gets a new fingerprint. A test pins each
# default here to the one in the config model, and another pins the
# fingerprints of the 14 `_repro` configs (tests/test_repro_fingerprints.py).
_OMITTED_AT_DEFAULT: dict[tuple[str, str], Any] = {
    ("merge", "pass2_skip_at_min_area"): False,
    ("merge", "pass2_soft_ceiling"): False,
    ("segmentation", "mask_before_snic"): False,
    ("segmentation", "drop_kept_patches_below_min_area"): False,
    ("clustering", "fit_excludes_stands_below_min_area"): False,
    ("features_static", "cap_distance_to_water"): False,
}


def config_fingerprint(config: Any) -> str:
    """Short stable hash of the config content that can change a cached asset.

    The cache used to be keyed on the config *name* alone, which meant editing a
    threshold and re-running the same config silently reused the old asset. That
    is not a performance bug, it is a correctness bug: the committed run has two
    arms whose SNIC tessellations differ (1249 vs 1312 superpixels, 0.2% of
    centroids matching), and under the merge design the segmentation IS the
    primary output. Threshold tuning is the main activity now, so a stale cache
    would poison precisely the thing being iterated on.

    Deliberately coarse: one fingerprint over most of the config rather than a
    per-stage dependency map. A narrow map is cheaper -- editing `merge` would
    not invalidate `masking` -- but a *wrong* narrow map silently reintroduces
    the bug it exists to prevent, for one stage only, and nothing in the output
    would say so. Over-invalidation costs compute; under-invalidation costs a
    result. Narrowing it per stage is a worthwhile follow-up with the
    completeness test already in place to keep it honest.
    """
    dumped = config.model_dump(mode="json")
    payload: dict[str, Any] = {
        block: dumped.get(block) for block in sorted(_CACHE_RELEVANT_BLOCKS)
    }
    for (block, field), default in _OMITTED_AT_DEFAULT.items():
        values = payload.get(block)
        if isinstance(values, dict) and field in values and values[field] == default:
            payload[block] = {k: v for k, v in values.items() if k != field}
    payload["export"] = {
        f: getattr(config.export, f) for f in _CACHE_RELEVANT_EXPORT_FIELDS
    }
    encoded = json.dumps(payload, sort_keys=True, default=str).encode()
    return hashlib.sha256(encoded).hexdigest()[:10]


def cached_asset_path(
    config_name: str, stage_name: str, key: str, fingerprint: str | None = None
) -> str:
    """Build a stable cache asset path.

    Layout:
      {asset_root}/{config_name}/{stage_name}/{key}__{fingerprint}

    The fingerprint makes the path depend on the config *content*, so two runs
    of the same config name with different parameters get different assets
    instead of the second silently reusing the first. Omitting it reproduces the
    old name-only layout; that is for reading pre-fingerprint assets, not for
    writing new ones.

    `config_name` and `stage_name` may not contain slashes or whitespace;
    they're already constrained by config validation. We re-check `key`
    here because it comes from a stage's `produces` set and is otherwise
    unvalidated.
    """
    if not re.match(r"^[a-zA-Z0-9_]+$", key):
        raise ValueError(
            f"cached_asset_path: key must be alphanumeric/underscore. Got: {key!r}"
        )
    if fingerprint is not None:
        if not re.match(r"^[a-zA-Z0-9]+$", fingerprint):
            raise ValueError(
                f"cached_asset_path: fingerprint must be alphanumeric. "
                f"Got: {fingerprint!r}"
            )
        key = f"{key}__{fingerprint}"
    return asset_path(key, subdir=f"{config_name}/{stage_name}")


def asset_exists(path: str) -> bool:
    """True if the given GEE asset path exists and is readable.

    Distinguishes "not found" (returns False) from permission errors and
    other failures (re-raises). Tries the underlying HTTP status first
    (most reliable across GEE client versions); falls back to string-
    matching the EE error message for older versions where the wrapped
    cause is unreachable.
    """
    try:
        ee.data.getAsset(path)
        return True
    except ee.EEException as e:
        # Prefer the underlying HttpError status when available; GEE's
        # Python client wraps googleapiclient HttpError into EEException,
        # and the cause's response status is more reliable than message
        # text.
        cause = getattr(e, "__cause__", None)
        if cause is not None:
            status = getattr(getattr(cause, "resp", None), "status", None)
            if status == 404:
                return False
            if status in (401, 403):
                # Permission issue; propagate so the user fixes it.
                raise

        # Fallback: match the message text. GEE's "not found" / "does not
        # exist" / "404" phrasing has been stable across the versions we
        # support, but it's not formally guaranteed.
        msg = str(e).lower()
        if "not found" in msg or "does not exist" in msg or "404" in msg:
            return False
        # Permission or other error; propagate
        raise


def ensure_parent_folders(asset_path: str) -> None:
    """Create any missing parent FOLDER assets for `asset_path`.

    GEE's ``Export.image.toAsset`` fails if the target's parent folder doesn't
    exist and does NOT auto-create the hierarchy. A brand-new config's cache
    path (``{root}/{config}/{stage}/{key}``) therefore has no folders yet, so the
    first run's exports all fail with
    ``Asset '.../{config}/{stage}' does not exist or doesn't allow this
    operation`` and nothing ever caches. Walk the ancestors below the project
    assets root and create each missing folder.

    Best-effort: log and continue on any error. A genuine permission problem
    still surfaces later as an export failure, but a plain "folder missing"
    (the common case for a new config) is fixed transparently.
    """
    parts = asset_path.split("/")
    if "assets" not in parts:
        return  # unrecognized layout; nothing safe to do
    base = parts.index("assets") + 1  # first component below projects/<p>/assets
    for i in range(base, len(parts) - 1):  # ancestors only, excluding the leaf asset
        folder = "/".join(parts[: i + 1])
        try:
            if asset_exists(folder):
                continue
        except ee.EEException:
            # Permission/other error checking existence; try to create anyway.
            pass
        try:
            ee.data.createFolder(folder)
            log.info("Created cache folder %s", folder)
        except ee.EEException as e:
            # Already exists (benign race) or a real permission issue.
            log.debug("ensure_parent_folders: %s not created (%s)", folder, e)


@dataclass
class ExportTaskInfo:
    """Info about a submitted export task."""

    task_id: str
    asset_path: str
    description: str


def start_export(
    image: ee.Image,
    *,
    asset_path: str,
    roi: ee.Geometry,
    scale: int = 10,
    max_pixels: int = 1_000_000_000,
    description: str | None = None,
    crs: str | None = None,
    crs_transform: list[float] | None = None,
) -> ExportTaskInfo:
    """Submit an async export-to-asset task. Returns immediately.

    The task runs in the GEE backend queue; check status at
    https://code.earthengine.google.com/tasks. The asset becomes available
    when the task completes.

    Without `crs` (the legacy layout, and every export before round 9) only
    `scale` is given, and Earth Engine puts the asset on a grid of its own
    choosing: for a computed image, a geographic one. With `crs` and
    `crs_transform` (the per-step layout) the asset is written on exactly that
    grid; `scale` is then not passed, as Earth Engine takes one or the other.
    """
    if description is None:
        # Asset path may exceed GEE's 100-char task description limit; use
        # the last two segments only.
        parts = asset_path.split("/")
        description = "_".join(parts[-2:])[:100]

    # A new config's cache folders don't exist yet; toAsset won't create them
    # and would fail every export. Create the parent hierarchy first.
    ensure_parent_folders(asset_path)

    grid: dict[str, Any] = {"scale": scale}
    if crs is not None:
        grid = {"crs": crs}
        if crs_transform is not None:
            grid["crsTransform"] = [float(v) for v in crs_transform]
        else:
            grid["scale"] = scale
    task = ee.batch.Export.image.toAsset(
        image=image,
        description=description,
        assetId=asset_path,
        region=roi,
        maxPixels=max_pixels,
        **grid,
    )
    task.start()

    if task.id is None:
        # A started task with no id is not something to paper over: every caller
        # records the id to poll the task later, so an empty one silently loses
        # the export.
        raise RuntimeError(
            f"export task for {asset_path} started but Earth Engine returned no "
            f"task id; the export cannot be tracked"
        )
    info = ExportTaskInfo(
        task_id=task.id,
        asset_path=asset_path,
        description=description,
    )
    log.info(
        "Started cache export to %s (task %s). Check progress at "
        "https://code.earthengine.google.com/tasks",
        asset_path,
        task.id,
    )
    return info


def load_cached_image(path: str) -> ee.Image:
    """Load a cached asset as ee.Image."""
    return ee.Image(path)


def load_cached_table(path: str) -> ee.FeatureCollection:
    """Load a cached table asset (a stage's `table_outputs`) as ee.FeatureCollection."""
    return ee.FeatureCollection(path)


def start_table_export(
    table: ee.FeatureCollection,
    *,
    asset_path: str,
    description: str | None = None,
) -> ExportTaskInfo:
    """Submit an async export of a small table to an asset. Returns immediately.

    For the outputs a stage lists in `table_outputs` (the k elbow), which are
    FeatureCollections, not images: they have no grid.
    """
    if description is None:
        parts = asset_path.split("/")
        description = "_".join(parts[-2:])[:100]
    ensure_parent_folders(asset_path)
    task = ee.batch.Export.table.toAsset(
        collection=table, description=description, assetId=asset_path
    )
    task.start()
    if task.id is None:
        raise RuntimeError(
            f"table export task for {asset_path} started but Earth Engine returned "
            f"no task id; the export cannot be tracked"
        )
    log.info("Started cache table export to %s (task %s)", asset_path, task.id)
    return ExportTaskInfo(task_id=task.id, asset_path=asset_path, description=description)


# ---------------------------------------------------------------------
# Cache layouts and per-step keys (round 9, issue #44 items 1 and 2)
# ---------------------------------------------------------------------

LEGACY_LAYOUT = "legacy"
PER_STEP_LAYOUT = "per_step"
CacheLayout = Literal["legacy", "per_step"]
CACHE_LAYOUTS: tuple[str, ...] = (LEGACY_LAYOUT, PER_STEP_LAYOUT)

# Raised to change every per-step key at once, if what a key means changes.
STEP_KEY_VERSION = 1
# A per-step key starts with a letter that is not a hex digit, so it can never be
# read as a legacy fingerprint (ten hex digits): habitat_mask__s1a2b3c4d5e is of
# the per-step layout, habitat_mask__1a2b3c4d5e of the legacy one.
STEP_KEY_PREFIX = "s"

# The property a per-step asset carries: the count and SHA-256 of the image ids
# of each input collection its stage read (fmu.stages.base.Stage.input_collections).
INPUT_IMAGES_PROPERTY = "fmu_input_images"

# Every cached asset of the per-step layout depends on these, whatever its step
# reads: the ROI (which pixels, and which UTM zone the grid is in) and the
# analysis scale (the grid's pixel size).
_EVERY_STEP: tuple[str, ...] = ("roi", "export.analysis_scale_m")

# What each cached step reads from the config: a block, or one field of a block
# ("datasets.indiasat"). The per-step key of a step hashes these values, the
# ROI file's content, and the keys of the steps whose outputs it reads
# (`step_upstream`), so a setting changes the key of the step that reads it and
# of every step downstream of it, and of nothing upstream.
#
# A setting missing here would leave a step's key unchanged when it changes:
# the stale-cache bug the fingerprint was made to prevent, for one step.
# tests/test_cache_layout.py reads each stage's module and fails on any config
# setting it reads that is not listed for it (or for the steps upstream of it).
# The k_elbow step reads the clustering settings but `k`: what the elbow is
# computed for does not depend on the k a config fits, so a config's elbow is
# computed once and found again whatever its k (a test checks this list holds
# every other field of the clustering block).
STEP_SETTINGS: dict[str, tuple[str, ...]] = {
    "masking": (
        "datasets.indiasat", "datasets.worldcover", "datasets.water", "masking",
    ),
    "data_load": (
        "dates.phenology", "dates.radar", "dates.optical_composite",
        "datasets.phenology_collection", "datasets.optical_composite_collection",
        "datasets.radar_collection", "cloud_mask", "data_load",
    ),
    "features_optical": ("features_optical",),
    "features_radar": ("features_radar",),
    "features_structure": ("datasets.canopy_height", "features_structure"),
    # The water settings: features_static builds its own water input since round 13
    # (review A1), with masking's definition, and reads no masking output.
    "features_static": (
        "dates.climate", "datasets.dem", "datasets.climate", "datasets.water",
        "masking.jrc_water_occurrence_threshold", "features_static",
    ),
    "features_embedding": ("dates.phenology", "datasets.embedding", "features_embedding"),
    "segmentation": (
        "segmentation", "data_load.s2_composite_reducer", "merge.min_area_ha",
    ),
    "merge": (
        "merge", "segmentation.mask_before_snic", "segmentation.connectivity",
        "segmentation.drop_kept_patches_below_min_area",
    ),
    # merge.max_area_ha, min_area_ha and pass2_soft_ceiling for
    # Config.max_component_pixels(), which clustering read, with the merge on or
    # off, until round 13 (review B14 took its reduceConnectedComponents call
    # out). They stay listed: taking them out would change every config's
    # clustering key, which tests/test_step_keys_of_record.py pins with the
    # revisions emptied; with the merge on, the merge's own key covers them too.
    "clustering": (
        "clustering", "normalization", "merge.enabled", "merge.max_area_ha",
        "merge.min_area_ha", "merge.pass2_soft_ceiling",
    ),
    "k_elbow": (
        "clustering.seed", "clustering.feature_source", "clustering.skewness_threshold",
        "clustering.fit_excludes_stands_below_min_area", "normalization", "merge.enabled",
        "merge.max_area_ha", "merge.min_area_ha", "merge.pass2_soft_ceiling", "k_elbow",
    ),
}

# Settings added after round 9 to a block or field that STEP_SETTINGS lists, keyed
# (block, field) -> default, where the block may be a sub-block ("dates.phenology").
# The per-step layout's counterpart of `_OMITTED_AT_DEFAULT` (review B11): a step's
# key hashes what STEP_SETTINGS lists for it as dumped, defaults included, so a
# field added to one of those blocks would move the key of that step and of every
# step downstream of it, in every config at once, and the assets they cached could
# no longer be found by name. A field listed here is left out of the hash while it
# holds its default, which must be the behaviour the saved assets were made with;
# any other value is hashed. A field added to a block both layouts hash goes in
# both tables. Empty: no field has been added since round 9, so no key moves;
# tests/test_step_keys_of_record.py pins the keys the runs recorded.
_STEP_OMITTED_AT_DEFAULT: dict[tuple[str, str], Any] = {}

# A step's revision, raised when what the step computes changes for configs whose
# settings do not (round 13): its key, and through `step_upstream` the key of every
# step downstream of it, then moves, so that the assets cached before the change
# are not read back. Review A4 notes that its fix would otherwise move no key. A
# step not listed is at revision 0 and its payload carries none, so its key is the
# one it had before round 13; STEP_KEY_VERSION, above, would move every key of every
# step at once. Each raise has a register entry (docs/decisions.yaml).
STEP_REVISION: dict[str, int] = {
    "data_load": 1,  # A4, round 13: the date windows' end is inclusive
    # A1, round 13: water seen past the ROI, out to the transform's reach (1);
    # A5, round 13: slope and aspect in fractional degrees, on the DEM as float (2)
    "features_static": 2,
    # Round 13. 1, A5: a flat cell's aspect sin and cos are both 0. 2, B13: a harmonic
    # phase's sin and cos are kept out of the skew test and the log. 3, B14: one mean
    # per unit label, not per connected piece. 4, B16: the robust scaling's median and
    # IQR are exact quartiles, for the constant-band test as for the scaling.
    "clustering": 4,
    # Round 13: 1, B17, the superpixel pixel counts on one inclusion rule;
    # 2, B18, the area bounds compared in whole pixels.
    "merge": 2,
}

# Steps that read another step's output without having it upstream, and so take
# that step's revision with their own: k_elbow reads clustering's cached scaled
# feature stack (fmu.stages.k_elbow.training_rows), but its key leaves k out, so
# clustering's key cannot be one of its inputs.
_REVISION_ALSO_FROM: dict[str, tuple[str, ...]] = {"k_elbow": ("clustering",)}


# Which step produces each context key that a SNIC input band or a merge
# criterion can name (SnicInputBand.source, MergeCriterion.source).
SOURCE_STEP: dict[str, str] = {
    "s2_composite": "data_load",
    "optical_features": "features_optical",
    "radar_features": "features_radar",
    "structure_features": "features_structure",
    "static_features": "features_static",
    "embedding_features": "features_embedding",
}

_HANDCRAFTED_STEPS: tuple[str, ...] = (
    "features_optical", "features_radar", "features_structure", "features_static",
)


def step_upstream(config: Any, step: str) -> tuple[str, ...]:
    """The steps whose outputs `step` reads, for this config. Sorted.

    Follows each stage's own reads: the feature images segmentation is given
    (`segmentation.input_bands`), the merge criteria's sources, the feature
    source of clustering, and the habitat mask wherever it is read (always by
    clustering, by segmentation and merge only with
    segmentation.mask_before_snic). The merge is not cached, but it is a step:
    clustering reads its stands, so its settings reach clustering's key through
    it. The k_elbow step reads what clustering reads (it re-samples clustering's
    scaled feature image, which does not depend on k).
    """
    # features_static read masking's water_mask until round 13; it now builds its
    # own water input (review A1), so a masking setting it does not read (the
    # habitat classes, say) no longer moves its key.
    if step in (
        "masking", "data_load", "features_structure", "features_static", "features_embedding",
    ):
        return ()
    if step in ("features_optical", "features_radar"):
        return ("data_load",)
    ups: set[str]
    if step == "segmentation":
        ups = {SOURCE_STEP[s] for s in config.segmentation.input_sources()}
        if config.segmentation.mask_before_snic:
            ups.add("masking")
    elif step == "merge":
        ups = {"segmentation"} | {SOURCE_STEP[s] for s in config.merge.input_sources()}
        if config.segmentation.mask_before_snic:
            ups.add("masking")
    elif step in ("clustering", "k_elbow"):
        ups = {"masking", "merge" if config.merge.enabled else "segmentation"}
        if config.clustering.feature_source == "embedding":
            ups.add("features_embedding")
        else:
            ups |= set(_HANDCRAFTED_STEPS)
    else:
        raise KeyError(f"step_upstream: {step!r} is not a cached step of the pipeline")
    return tuple(sorted(ups))


def _setting(dumped: dict[str, Any], path: str) -> Any:
    value: Any = dumped
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            raise KeyError(f"per-step key: the config has no setting {path!r}")
        value = value[part]
    return value


def _roi_file_sha256(config: Any) -> str | None:
    """SHA-256 of the ROI file, so that a changed outline changes every key.

    The legacy fingerprint hashes the ROI file's path only. None when the file
    cannot be read (an ROI given as an asset, or a test config whose file does
    not exist).
    """
    roi_file = getattr(config.roi, "roi_file", None)
    if roi_file is None:
        return None
    try:
        return hashlib.sha256(Path(roi_file).read_bytes()).hexdigest()
    except OSError:
        return None


def step_key(config: Any, step: str) -> str:
    """The per-step cache key of `step` for `config`: "s" and ten hex digits.

    A hash of the settings `STEP_SETTINGS` lists for the step, the ones every
    step depends on (the ROI and the analysis scale), the ROI file's content, and
    the keys of the steps upstream of it. The config's name, description, export
    plumbing and metrics are in none of them, so two configs that differ only in
    name have the same keys.

    A stage that is not one of the pipeline's (a test's, say) has no entry in
    `STEP_SETTINGS`; its key then covers every block the legacy fingerprint
    covers, which can only over-invalidate.
    """
    dumped = config.model_dump(mode="json")
    return _step_key(config, dumped, step, {})


def _omit_step_defaults(settings: dict[str, Any]) -> dict[str, Any]:
    """`settings` without the fields `_STEP_OMITTED_AT_DEFAULT` lists, while each holds its default.

    A field is found inside its block, where a step's settings list the whole
    block ("masking"), or as a setting of its own ("masking.new_field").
    """
    out = dict(settings)
    for (block, field), default in _STEP_OMITTED_AT_DEFAULT.items():
        values = out.get(block)
        if isinstance(values, dict) and field in values and values[field] == default:
            out[block] = {k: v for k, v in values.items() if k != field}
        path = f"{block}.{field}"
        if path in out and out[path] == default:
            del out[path]
    return out


def _step_key(config: Any, dumped: dict[str, Any], step: str, memo: dict[str, str]) -> str:
    if step in memo:
        return memo[step]
    if step in STEP_SETTINGS:
        settings = _omit_step_defaults(
            {p: _setting(dumped, p) for p in (*_EVERY_STEP, *STEP_SETTINGS[step])}
        )
        upstream = {u: _step_key(config, dumped, u, memo) for u in step_upstream(config, step)}
    else:
        settings = {"legacy_fingerprint_payload": _legacy_payload(config)}
        upstream = {}
    payload: dict[str, Any] = {
        "layout": PER_STEP_LAYOUT,
        "version": STEP_KEY_VERSION,
        "step": step,
        "settings": settings,
        "roi_file_sha256": _roi_file_sha256(config),
        "upstream": upstream,
    }
    also = _REVISION_ALSO_FROM.get(step, ())
    if not also:
        if STEP_REVISION.get(step, 0):
            payload["revision"] = STEP_REVISION[step]
    elif any(STEP_REVISION.get(s, 0) for s in (step, *also)):
        payload["revision"] = {s: STEP_REVISION.get(s, 0) for s in (step, *also)}
    encoded = json.dumps(payload, sort_keys=True, default=str).encode()
    memo[step] = STEP_KEY_PREFIX + hashlib.sha256(encoded).hexdigest()[:10]
    return memo[step]


def _legacy_payload(config: Any) -> dict[str, Any]:
    dumped = config.model_dump(mode="json")
    payload: dict[str, Any] = {block: dumped.get(block) for block in sorted(_CACHE_RELEVANT_BLOCKS)}
    payload["export"] = {f: getattr(config.export, f) for f in _CACHE_RELEVANT_EXPORT_FIELDS}
    return payload


def step_keys(config: Any) -> dict[str, str]:
    """The per-step key of every cached step, for the manifest."""
    dumped = config.model_dump(mode="json")
    memo: dict[str, str] = {}
    return {step: _step_key(config, dumped, step, memo) for step in STEP_SETTINGS}


def cache_key(config: Any, stage_name: str, layout: str) -> str:
    """What follows `__` in the name of a stage's cached assets, under a layout."""
    if layout == LEGACY_LAYOUT:
        return config_fingerprint(config)
    if layout == PER_STEP_LAYOUT:
        return step_key(config, stage_name)
    raise ValueError(f"cache layout must be one of {CACHE_LAYOUTS}, got {layout!r}")


# The layout each pipeline run is using, while it runs, so that a stage that
# names cached assets itself (the export stage's inventory, the metrics stage's
# reference) names the ones the run reads. Keyed by config name and legacy
# fingerprint; set and cleared by fmu.pipeline.Pipeline.run.
_active_layouts: dict[tuple[str, str], str] = {}


@contextmanager
def layout_in_use(config: Any, layout: str) -> Iterator[None]:
    """Record `layout` as the one a run of `config` uses, for the length of the block."""
    if layout not in CACHE_LAYOUTS:
        raise ValueError(f"cache layout must be one of {CACHE_LAYOUTS}, got {layout!r}")
    key = (config.name, config_fingerprint(config))
    before = _active_layouts.get(key)
    _active_layouts[key] = layout
    try:
        yield
    finally:
        if before is None:
            _active_layouts.pop(key, None)
        else:
            _active_layouts[key] = before


def active_layout(config: Any) -> str | None:
    """The layout a pipeline run of this config is using now, or None outside a run."""
    return _active_layouts.get((config.name, config_fingerprint(config)))


def input_images_record(ids_by_collection: dict[str, list[str]], *, list_up_to: int) -> dict[str, Any]:
    """Count, SHA-256 and (if short enough) the list of image ids, per input collection.

    The SHA-256 is of the sorted ids joined by newlines, so it does not depend on
    the order Earth Engine returns them in. Pure Python.
    """
    out: dict[str, Any] = {}
    for name, ids in sorted(ids_by_collection.items()):
        ordered = sorted(str(i) for i in ids)
        out[name] = {
            "count": len(ordered),
            "sha256": hashlib.sha256("\n".join(ordered).encode()).hexdigest(),
            "ids": ordered if len(ordered) <= list_up_to else None,
        }
    return out

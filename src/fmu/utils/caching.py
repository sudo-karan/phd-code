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
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

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
_CACHE_IRRELEVANT_BLOCKS: frozenset[str] = frozenset(
    {"name", "description", "metrics"}
)

# `export` is split: analysis_scale_m governs every reduction and every export
# resolution, so it belongs in the fingerprint. The rest is output plumbing
# (Drive folder, formats, which layers to emit) and changing it should not throw
# away an expensive raster.
_CACHE_RELEVANT_EXPORT_FIELDS: tuple[str, ...] = ("analysis_scale_m",)


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
    payload: dict[str, Any] = {
        block: config.model_dump(mode="json").get(block)
        for block in sorted(_CACHE_RELEVANT_BLOCKS)
    }
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
    max_pixels: float = 1e9,
    description: str | None = None,
) -> ExportTaskInfo:
    """Submit an async export-to-asset task. Returns immediately.

    The task runs in the GEE backend queue; check status at
    https://code.earthengine.google.com/tasks. The asset becomes available
    when the task completes.
    """
    if description is None:
        # Asset path may exceed GEE's 100-char task description limit; use
        # the last two segments only.
        parts = asset_path.split("/")
        description = "_".join(parts[-2:])[:100]

    # A new config's cache folders don't exist yet; toAsset won't create them
    # and would fail every export. Create the parent hierarchy first.
    ensure_parent_folders(asset_path)

    task = ee.batch.Export.image.toAsset(
        image=image,
        description=description,
        assetId=asset_path,
        region=roi,
        scale=scale,
        maxPixels=max_pixels,
    )
    task.start()

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

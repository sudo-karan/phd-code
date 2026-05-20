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

import re
from dataclasses import dataclass

import ee

from fmu.utils.gee import asset_path
from fmu.utils.logging import get_logger

log = get_logger(__name__)


def cached_asset_path(config_name: str, stage_name: str, key: str) -> str:
    """Build a stable cache asset path.

    Layout:
      {asset_root}/{config_name}/{stage_name}/{key}

    `config_name` and `stage_name` may not contain slashes or whitespace;
    they're already constrained by config validation. We re-check `key`
    here because it comes from a stage's `produces` set and is otherwise
    unvalidated.
    """
    if not re.match(r"^[a-zA-Z0-9_]+$", key):
        raise ValueError(
            f"cached_asset_path: key must be alphanumeric/underscore. Got: {key!r}"
        )
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

"""
Google Earth Engine utilities.

This module is the single point of contact between the pipeline and the
GEE Python API. Three responsibilities:

1. Authentication and initialization (`init_gee`).
2. Safe materialization (`safe_get_info`) — wraps `.getInfo()` calls so when
   they fail (which they will, deep in a pipeline run), we get a useful error
   pointing at the operation that built the bad request.
3. Shared helpers stages will use (ROI loading, asset path resolution).

Why these live in one file:
   These are the "stages depend on this" foundations. Putting them together
   means a stage author imports one module and gets everything GEE-related.

Why explicit init (not auto-init on import):
   We do NOT call ee.Initialize() at import time. Tests that don't need GEE
   should be able to import any module without authenticating, and the user
   should control when network calls happen. See decisions.md DEC-008.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from functools import wraps
from pathlib import Path
from typing import Any, TypeVar

import ee

from fmu.settings import get_settings
from fmu.utils.logging import get_logger

log = get_logger(__name__)

# Track whether ee.Initialize() has been called successfully this session.
_initialized: bool = False


# ---------- Initialization ----------


def init_gee(project_id: str | None = None) -> None:
    """
    Initialize the Earth Engine API.

    Args:
        project_id: Override the GEE_PROJECT_ID from .env. Useful for tests
            or scripts that want to target a specific project.

    Raises:
        RuntimeError: If GEE_PROJECT_ID is missing and no override is given.
        ee.EEException: If authentication has not been done locally
            (see error message for the fix).

    Calling this more than once is a no-op after the first successful call.
    """
    global _initialized
    if _initialized:
        return

    settings = get_settings()
    pid = project_id or settings.gee_project_id
    if not pid:
        raise RuntimeError(
            "GEE project ID is not set. Either set GEE_PROJECT_ID in .env "
            "or pass project_id explicitly to init_gee()."
        )

    log.info("Initializing GEE with project: %s", pid)
    try:
        ee.Initialize(project=pid)
    except ee.EEException as e:
        msg = str(e)
        # Detect the "not authenticated" case and provide a useful hint.
        if "not authenticated" in msg.lower() or "no credentials" in msg.lower():
            raise ee.EEException(
                f"{msg}\n\n"
                "Fix: run `earthengine authenticate` in your terminal to set up "
                "credentials for this Google account. You only need to do this "
                "once per machine."
            ) from e
        raise

    _initialized = True
    log.info("GEE initialized")


def is_initialized() -> bool:
    """Return True if init_gee() has been called successfully."""
    return _initialized


# ---------- Safe materialization ----------


T = TypeVar("T")


def safe_get_info(ee_object: Any, *, context: str = "") -> Any:
    """
    Call .getInfo() on a GEE object with a useful error message if it fails.

    The whole point: GEE errors fire when you materialize, not when you build.
    So a `.getInfo()` deep in stage code can fail in a way whose traceback
    points at line that says `.getInfo()` — not the offending operation 50
    lines above it. This wrapper lets you label each materialization call
    with what it was trying to do.

    Args:
        ee_object: Any GEE object with a .getInfo() method.
        context: A short human-readable label for what this call was doing,
            e.g. "computing per-stand area" or "checking S2 image count".
            This shows up in the error if the call fails.

    Returns:
        The result of .getInfo().

    Raises:
        ee.EEException: With the original error AND the context label.
    """
    if not hasattr(ee_object, "getInfo"):
        raise TypeError(
            f"safe_get_info: expected a GEE object with .getInfo(), got "
            f"{type(ee_object).__name__}"
        )

    try:
        return ee_object.getInfo()
    except ee.EEException as e:
        ctx = f" [context: {context}]" if context else ""
        # Re-raise with the same exception type so callers can catch normally,
        # but with our context appended.
        raise ee.EEException(f"{e}{ctx}") from e


def safe_call(context: str) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator that adds GEE error context to a function.

    Usage:
        @safe_call("computing SNIC segmentation")
        def run_snic(image, params):
            return ee.Algorithms.Image.Segmentation.SNIC(...)

    If anything inside the function raises ee.EEException, it gets re-raised
    with the context label appended.
    """

    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            try:
                return fn(*args, **kwargs)
            except ee.EEException as e:
                raise ee.EEException(f"{e} [context: {context}]") from e

        return wrapper

    return decorator


# ---------- ROI loading ----------


def load_roi_geometry(roi_file: Path) -> ee.Geometry:
    """
    Load a local GeoJSON file and return an ee.Geometry.

    Supports:
      - A single Feature with a Polygon/MultiPolygon geometry
      - A FeatureCollection containing one or more Features
      - A bare Geometry object

    Args:
        roi_file: Path to a .geojson file.

    Returns:
        ee.Geometry suitable for filterBounds() / clip() / etc.

    Raises:
        FileNotFoundError: If the file doesn't exist.
        ValueError: If the GeoJSON structure is unrecognized.
    """
    roi_file = Path(roi_file)
    if not roi_file.exists():
        raise FileNotFoundError(f"ROI file not found: {roi_file}")

    with roi_file.open() as f:
        gj = json.load(f)

    gtype = gj.get("type")
    if gtype == "FeatureCollection":
        feats = gj.get("features", [])
        if not feats:
            raise ValueError(f"ROI file {roi_file} has no features.")
        # Union the geometries of all features.
        geoms = [ee.Geometry(feat["geometry"]) for feat in feats]
        if len(geoms) == 1:
            return geoms[0]
        return ee.Geometry.MultiPolygon(
            [g.coordinates() for g in geoms],
            proj="EPSG:4326",
            evenOdd=False,
        )
    elif gtype == "Feature":
        return ee.Geometry(gj["geometry"])
    elif gtype in ("Polygon", "MultiPolygon", "Point", "LineString"):
        return ee.Geometry(gj)
    else:
        raise ValueError(
            f"ROI file {roi_file}: unrecognized GeoJSON type {gtype!r}. "
            "Expected FeatureCollection, Feature, or a Geometry object."
        )


# ---------- Asset path helpers ----------


def asset_path(name: str, subdir: str | None = None) -> str:
    """
    Build a fully-qualified GEE asset path under this project's asset root.

    Args:
        name: Asset name (no slashes, no spaces).
        subdir: Optional subdirectory under the asset root.

    Returns:
        Full asset path, e.g. "projects/replicating-paper/assets/fmu/sanjay_van/cluster_map".

    Raises:
        ValueError: If name contains invalid characters or GEE_PROJECT_ID is unset.
    """
    if "/" in name or " " in name or "\\" in name:
        raise ValueError(
            f"asset_path: name must not contain slashes or spaces. Got: {name!r}"
        )

    settings = get_settings()
    root = settings.resolved_asset_root()
    parts = [root]
    if subdir:
        parts.append(subdir)
    parts.append(name)
    return "/".join(parts)

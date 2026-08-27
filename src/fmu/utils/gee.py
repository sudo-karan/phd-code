"""GEE helpers: init, materialization wrapper, ROI loader, asset paths."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from functools import wraps
from pathlib import Path
from typing import Any, TypeVar

import ee

from fmu.settings import get_settings
from fmu.utils.logging import get_logger

log = get_logger(__name__)

# The name every synthesised label band uses.
#
# Several places bolt a label band onto a feature stack so a grouped reduction,
# `reduceConnectedComponents` or `stratifiedSample` has something to group by.
# Each had invented its own name, and two of them picked a leading underscore --
# which EE rejects, and only says so at getInfo time:
#
#     Image.rename: Invalid band name: '_label'
#     Image.rename: Invalid band name: '_unit_label'
#
# Both got as far as a live run. One name, checked once, is the fix.
LABEL_BAND = "fmu_label"

# Deliberately narrower than EE's real rule: this only ever guards names *we*
# synthesise, so refusing a legal-but-odd name costs nothing and refusing an
# illegal one client-side saves a round trip and a mid-run failure.
_BAND_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def check_band_name(name: str, *, context: str = "") -> str:
    """Reject a band name EE would reject, here rather than at getInfo time."""
    if not _BAND_NAME_RE.fullmatch(name):
        ctx = f"{context}: " if context else ""
        raise ValueError(
            f"{ctx}{name!r} is not a band name Earth Engine will accept. It must "
            f"start with a letter and hold only letters, digits and underscores. "
            f"EE reports this as 'Image.rename: Invalid band name', and only when "
            f"the graph is evaluated -- so an unchecked name fails mid-run."
        )
    return name

_initialized: bool = False


def init_gee(project_id: str | None = None) -> None:
    """Explicit GEE init. See docs/design_notes.md."""
    global _initialized
    if _initialized:
        return

    pid = project_id or get_settings().gee_project_id
    if not pid:
        raise RuntimeError("GEE project ID is not set. Set GEE_PROJECT_ID in .env.")

    log.info("Initializing GEE with project: %s", pid)
    try:
        ee.Initialize(project=pid)
    except ee.EEException as e:
        msg = str(e).lower()
        if "not authenticated" in msg or "no credentials" in msg:
            # surface the fix in the error
            raise ee.EEException(
                f"{e}\nFix: run `earthengine authenticate` once on this machine."
            ) from e
        raise

    _initialized = True
    log.info("GEE initialized")


def is_initialized() -> bool:
    return _initialized


T = TypeVar("T")


def safe_get_info(ee_object: Any, *, context: str = "") -> Any:
    """Wrap .getInfo() with a context label, so errors say what failed."""
    if not hasattr(ee_object, "getInfo"):
        raise TypeError(f"safe_get_info: expected GEE object, got {type(ee_object).__name__}")

    try:
        return ee_object.getInfo()
    except ee.EEException as e:
        ctx = f" [context: {context}]" if context else ""
        raise ee.EEException(f"{e}{ctx}") from e


def safe_call(context: str) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator version of safe_get_info; adds context to ee.EEExceptions."""

    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            try:
                return fn(*args, **kwargs)
            except ee.EEException as e:
                raise ee.EEException(f"{e} [context: {context}]") from e

        return wrapper

    return decorator


def load_roi_geometry(roi_file: Path) -> ee.Geometry:
    """Load a local GeoJSON into an ee.Geometry."""
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
        # All coords come from the local JSON file; pass them directly as
        # Python lists. GEE constructs the geometry from them server-side.
        if len(feats) == 1:
            return ee.Geometry(feats[0]["geometry"])
        polys = [feat["geometry"]["coordinates"] for feat in feats]
        return ee.Geometry.MultiPolygon(polys, proj="EPSG:4326", evenOdd=False)
    if gtype == "Feature":
        return ee.Geometry(gj["geometry"])
    if gtype in ("Polygon", "MultiPolygon", "Point", "LineString"):
        return ee.Geometry(gj)
    raise ValueError(
        f"ROI file {roi_file}: unrecognized GeoJSON type {gtype!r}. "
        "Expected FeatureCollection, Feature, or a Geometry object."
    )


def asset_path(name: str, subdir: str | None = None) -> str:
    """Build an asset path under the configured asset root."""
    if "/" in name or " " in name or "\\" in name:
        raise ValueError(f"asset_path: name must not contain slashes or spaces. Got: {name!r}")

    root = get_settings().resolved_asset_root()
    parts = [root]
    if subdir:
        parts.append(subdir)
    parts.append(name)
    return "/".join(parts)

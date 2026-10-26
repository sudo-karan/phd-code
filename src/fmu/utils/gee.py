"""GEE helpers: init, materialization wrapper, ROI loader, asset paths."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from functools import wraps
from pathlib import Path
from typing import Any, TypeVar

import ee
from shapely.geometry import mapping, shape
from shapely.geometry.polygon import orient

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


def checkout_root() -> Path:
    """The root of the checkout the `fmu` package was imported from: the folder holding `src/`.

    Read from `fmu.__file__` (<root>/src/fmu/__init__.py) at every call: the root
    `fmu.utils.provenance` names as this package's checkout. In a batch run tree the package
    is imported from the run tree (PYTHONPATH=<run tree>/src), so the root is the run tree.
    The working directory plays no part.
    """
    import fmu

    return Path(fmu.__file__).resolve().parents[2]


def resolve_roi_file(roi_file: str | Path) -> Path:
    """Where a config's `roi.roi_file` is read from (round 14; round 13 question 41).

    An absolute path is used as it is; a relative one is taken under `checkout_root()`, never
    under the working directory. Until round 14 both the ROI loader and the per-step cache
    keys read a relative path from the working directory (review C40).
    """
    path = Path(roi_file)
    return path if path.is_absolute() else checkout_root() / path


def read_roi_file(roi_file: str | Path) -> bytes:
    """The bytes of a config's ROI file, read where `resolve_roi_file` puts it.

    The one reader of a ROI file: `load_roi_geometry` makes the run's geometry from these
    bytes and the per-step cache keys hash them (fmu.utils.caching), so the keys and the
    geometry are always of the same file, whatever folder the process stands in. The file
    is read at every call, not remembered.

    A file that cannot be read raises an OSError of the kind the read gave
    (FileNotFoundError for a missing file, IsADirectoryError for a folder, ...) whose
    message names the path as given, the path it resolved to and the checkout root.
    """
    path = resolve_roi_file(roi_file)
    try:
        return path.read_bytes()
    except OSError as e:
        message = (
            f"ROI file {str(roi_file)!r} cannot be read ({e.strerror or e}): read at {path}. "
            f"A relative roi_file is resolved against {checkout_root()}, the root of the "
            f"checkout the fmu package was imported from, not against the working directory; "
            f"an absolute one is used as it is."
        )
        raise (type(e)(e.errno, message) if e.errno is not None else type(e)(message)) from e


def load_roi_geometry(roi_file: str | Path) -> ee.Geometry:
    """Load a config's GeoJSON ROI file into an ee.Geometry.

    The file is read by `read_roi_file`, the reader the per-step cache keys hash it with:
    an absolute path as it is, a relative one from the checkout root, not the working
    directory (round 14). A file that cannot be read raises an OSError naming it.
    """
    gj = json.loads(read_roi_file(roi_file))

    gtype = gj.get("type")
    if gtype == "FeatureCollection":
        feats = gj.get("features", [])
        if not feats:
            raise ValueError(f"ROI file {roi_file} has no features.")
        # All coords come from the local JSON file; pass them directly as
        # Python lists. GEE constructs the geometry from them server-side.
        if len(feats) == 1:
            return ee.Geometry(feats[0]["geometry"])
        # Several features: one MultiPolygon under the left-inside rule
        # (evenOdd=False), where a clockwise shell is the rest of the globe. GEOS
        # buffers and GDAL's shapefile conversion write clockwise shells, so each
        # polygon is oriented first: shell counter-clockwise, holes clockwise.
        # Each part of a MultiPolygon feature is one polygon (B33, round 13).
        polys = []
        for feat in feats:
            geom = shape(feat["geometry"])
            for part in getattr(geom, "geoms", [geom]):
                if part.geom_type != "Polygon":
                    raise ValueError(
                        f"ROI file {roi_file}: a feature of a {geom.geom_type}; "
                        "a ROI of several features takes polygons only."
                    )
                coords = mapping(orient(part, sign=1.0))["coordinates"]
                polys.append([[list(pt) for pt in ring] for ring in coords])
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

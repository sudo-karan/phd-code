"""Round 14's live check (Task 4): two runs of one config, each from scratch, compared.

    python odisha_script/r14_live_check.py [--records docs/reproducibility/r14_runs/live_check]
        [--config-a configs/odisha_v120_3ha_squares_angul_keptland_s1desc_r14_check_a.yaml]
        [--config-b configs/odisha_v120_3ha_squares_angul_keptland_s1desc_r14_check_b.yaml]
        [--out <records>/r14_live_check.json] [--overwrite] [--offline]

The round 14 brief (docs/handoff/2026-10-26-round14.md), Task 4: "Run _r14_check_a and
_r14_check_b in full, both from scratch, in one wrapper batch, at the config's current k, with the
k_elbow pass included. It passes only if all of these hold: 1. The two runs give the same stands
(the same count, and the same stand layer by SHA-256 or polygon by polygon) and the same type for
every stand. 2. Their feature values agree to within 1e-9 relative, and their elbows are
identical. 3. distance_to_water is no longer exactly 10,000 m in every Angul stand, and it varies.
4. The manifests record 189 Sentinel-1 scenes over the Angul boxes. 5. Slope and aspect have
decimals. 6. The manifests record the four new settings on. Write the results to a results file
(no times; times go to the logs)."

Run it after the batch, once scripts/copy_run_results.py (export mode) has copied each run's files
into the records folder: per run, <run>_stands_merged.geojson, _stands_snic.geojson and
_stands_dissolved.geojson (a file over 5 MB is read from the "where" of its entry in
<run>_files_off_git.json, and must have the SHA-256 recorded there), every pass's manifest
<run>_manifest_<kind>[_n].json, the stages' files <run>_k_elbow.csv, _k_elbow_stand_table.csv,
_k_elbow_types.csv, _clustering_stand_table.csv and _clustering_fit_rows.csv, and the logs of the
passes that failed before writing a manifest, <run>_log_failed_<n>.txt. Run it from the repo root
(fmu reads .env from the working directory). It reads no Earth Engine with --offline, and then the
two Earth Engine parts, 2 iii and 5, are "not run". Otherwise it is READ-ONLY on Earth Engine: after
ee_read_only.forbid_writes() it reads assets, runs reductions and draws a sample, and submits no
task and writes no asset.

THE PASS RULES, declared on 26 Oct 2026, before the batch ran (round 14, Task 4)
------------------------------------------------------------------------------

Amended on 27 Oct 2026, still before the batch ran, after the gate's review (part 3) found that
two correct runs would fail two of the rules as first declared. Criterion 1 compared each pair of
geometries as read, but Earth Engine lists a polygon's holes, and a multipolygon's parts, in an
order that differs between two from-scratch runs of one config: round 9's two runs of the
Kendujhar 3 ha config (docs/reproducibility/round9_cache_test/), their labels the same pixel for
pixel, differ as read in 4 of 547 merged polygons and 9 of 111 dissolved, and in none in normal
form. So criterion 1 now compares, and hashes, each geometry in normal form. Criterion 5 counted
every whole aspect as one without decimals, but on a DEM of whole metres a correct aspect is a
whole number at a multiple of 45 degrees (below), about 15 % of Angul's pixels with slope above 0
if Earth Engine takes the gradient on the DEM's own grid and 68 % if on the 10 m grid (worked
offline on SRTM's 1-arcsecond tile N20E084, the grid NASADEM reprocesses, over the Angul boxes).
So criterion 5 now sets those aspects aside. An aspect rounded to whole degrees, as before round
13's A5, still fails it. Criterion 5 also fails now, naming it, when check_a's static_features is
not on Earth Engine, where it stopped the check (exit 4, nothing written). Nothing else changed.

Numbers agree. Two values a and b agree when |a - b| <= 1e-9 x max(|a|, |b|) (the brief's 1e-9
relative) or |a - b| <= 1e-12. The second clause is an absolute floor, for values at or near 0,
where the relative rule alone fails any difference at all (1e-15 against -1e-15 differ by twice
either). Two nulls agree, and two NaNs; a null and a number do not; a value that is not a number
(true and false among them) agrees only with an equal one of its kind. The relative difference
reported is |a - b| / max(|a|, |b|), taken as 0 where |a - b| <= 1e-12.

The passes of a run. The records name each manifest by its pass kind (features, segmentation,
k_elbow, clustering, export) and number the earlier ones of a kind that ran more than once:
<run>_manifest_<kind>_1.json, _2, ..., then <run>_manifest_<kind>.json, the last. The first
manifest of a kind is its _1 if there is one, else the one with no number.

0. Both runs from scratch. For each run:
   a. there is a manifest of each of the kinds features, segmentation, k_elbow and clustering;
   b. in the first manifest of each of these four kinds, taken in this order, every cacheable
      output (as fmu declares it for the stage: Pipeline._resolve_cacheable_outputs) of the
      stages the kind adds, the stages that no kind before it runs (features: every stage of the
      pass; segmentation: segmentation; k_elbow: the merge, which caches nothing, and k_elbow;
      clustering: clustering), has cache_status "miss-exported": its asset was not there when the
      pass started, and the pass computed it and exported it. A "hit" is accepted instead only for
      an output whose asset a pass of the same run exported before it failed without writing a
      manifest: the failed pass's log, <run>_log_failed_<n>.txt, has a line "Started cache export
      to <asset path>" (or "Started cache table export to") whose path ends in the output's asset
      name, <run>/<stage>/<key>__<cache key>. A pass exports only an output it did not find, and an
      export onto an asset that exists fails, so that asset was made by that pass; each such hit is
      listed. Any other status ("miss": computed and not exported; any other "hit"; none) fails,
      and so does a stage fmu does not have (its cacheable outputs unknown);
   c. every manifest of the run records the same cache layout, and each stage the same cache key
      in all of them, so that a hit in a later pass reads the asset that the first pass of the
      stage's kind exported.
   The export pass adds profiling and export, which cache nothing, and is not checked here. The
   rule takes the records to hold this batch's run folders only: the batch runs from a new run tree.

1. The same stands, and the same type for every stand. The two runs' stands_merged layers have
   the same number of polygons, more than 0, and the same number of distinct stand_lbl. Paired by
   (stand_lbl, stand_id), every polygon of either layer has a partner in the other (no pair key
   twice in a layer), and in each pair the geometry is exactly equal in normal form
   (shapely.normalize of the GeoJSON geometry, as WKB, little-endian, byte for byte: the same type
   and the same coordinates, number for number, whatever the order in which a polygon's rings and
   a multipolygon's parts are listed, the vertex a ring starts at and the way it turns; no
   coordinate is changed) and so are n_pixels and area_ha (stand_lbl and stand_id are the pair's
   key). The SHA-256 of each layer's canonical form are equal: the JSON text (sorted keys, no
   spaces) of the list of [stand_lbl, the geometry's normal form as hexadecimal WKB] of every
   polygon, the items sorted by their own JSON text. The same type: cluster_id is equal in every
   pair (null equal to null), and the two runs' <run>_clustering_fit_rows.csv hold the same unit
   labels (the first column; more than 0) with the same value in the "type" column each.
   Reported, not part of the pass: stands_snic, paired by (snic_label, stand_id), and
   stands_dissolved, paired by unit_id, compared the same way (their canonical forms with
   snic_label and cluster_id in place of stand_lbl); in each layer, the pairs whose geometries
   differ as read; and in the merged pairs, the merge provenance
   (fmu.utils.region_merge.PROVENANCE_FIELDS, exactly) and perim_m and the centroid (the largest
   relative difference).

2. The feature values agree within 1e-9 relative, and the elbows are identical. All of:
   i.  <run>_k_elbow_stand_table.csv and <run>_clustering_stand_table.csv, each against the
       other run's file of the same name: the same header (the unit label, in_fit, then the bands
       in the same order), the same labels (more than 0, none twice), and label by label the same
       in_fit and agreeing values in every band;
   ii. in the pairs of stands_merged (criterion 1), every feature mean: each property but
       stand_lbl, stand_id, cluster_id, n_pixels, area_ha, perim_m, centroid_lat, centroid_lon,
       the merge provenance and _sort_key (the export stage's bookkeeping, null where it is
       there). Both polygons of a pair have the same such properties, and each value agrees; more
       than 0 values compared;
   iii. read-only on Earth Engine, the two configs' cached assets, pixel by pixel on the assets'
       own grid: masking's habitat_mask, water_mask, mask_provenance and landcover_summary;
       data_load's s2_composite; optical_features, radar_features, structure_features and
       static_features; segmentation's snic_clusters and snic_means; clustering's cluster_labels
       and feature_stack. An asset's path is fmu's (fmu.utils.caching.cached_asset_path with the
       key fmu.utils.caching.cache_key gives the config in the layout
       fmu.pipeline.cache_layout_for finds), and must be the one its run recorded (the
       manifests' cache layout and the stage's cache key). Both assets must exist, with the same
       band names, on the same grid (crs and crsTransform). Then reduceRegion over the ROI (config
       a's) on that grid, unweighted, maxPixels 1e10, tileScale 4, as
       scripts/compare_cached_assets.py does. Per band: the pixels compared (unmasked in both) and
       the pixels whose mask differs, which must be 0; for the label-like assets (habitat_mask,
       water_mask, mask_provenance, landcover_summary, which is an image of class codes,
       snic_clusters and cluster_labels) the pixels whose values differ, which must be 0; for the
       others, read as doubles, the pixels whose values do not agree (|a - b| > 1e-12 and
       |a - b| > 1e-9 x max(|a|, |b|)), which must be 0, and the largest relative and absolute
       differences. Each asset needs more than 0 pixels compared;
   iv. the elbows: the two runs' <run>_k_elbow.csv identical (the same SHA-256 of their bytes),
       and their <run>_k_elbow_types.csv identical.

3. distance_to_water. In each run's stands_merged, over its polygons with a value (a stand in
   pieces counts once per piece): the number exactly 10000.0, the number of distinct values, the
   least and the greatest (and the number of polygons with no value). Passes for a run when some
   polygon has a value, not every value is exactly 10,000 m, and there is more than one distinct
   value; and the criterion when it passes for both runs.

4. 189 Sentinel-1 scenes. In each run, every manifest's record of the radar features' input images:
   stage features_radar, input_images["radar_features"]["collections"]["s1"]["count"]. Passes for
   a run when its first features manifest records that count and every count that any manifest of
   the run records is 189; and the criterion when it passes for both runs.

5. Slope and aspect have decimals. Read-only on Earth Engine, check_a's cached static_features (its
   path as in 2 iii): Image.sample of its slope and aspect over the ROI on the asset's own grid,
   10,000 pixels asked for, seed 42, a pixel with either band masked dropped; then 5,000 of them at
   random (randomColumn with seed 42, the 5,000 lowest), or as many as there are (their number is
   reported). Among the pixels with slope above 0: the number whose slope is not a whole number;
   and, of those whose aspect is not at a multiple of 45 degrees (0, 45, 90, ..., 315, which are
   counted and set aside), the number whose aspect is not a whole number. A whole number is a
   finite one with no fraction. Passes when there is a pixel with slope above 0 and one whose
   aspect is not at a multiple of 45 degrees, and both shares are at least 0.99. The multiples of
   45 are set aside because there a correct aspect is a whole number: NASADEM's elevations are
   whole metres, so the two components of the 4-neighbour gradient are whole-metre differences
   over the grid's spacings; where one is exactly 0 the aspect is exactly 0, 90, 180 or 270, and
   where the two spacings are equal and the two differences equal in size, exactly 45, 135, 225 or
   315. If check_a's static_features is not on Earth Engine, criterion 5 fails, naming it.

6. The four settings on. Every manifest of each run has config.clustering.fit_outside_earth_engine
   true, config.clustering.log_rule "right_skew", config.features_optical.mean_over_window true and
   config.k_elbow.in_fit_space true, and each run has a manifest.

The check passes only if 0 to 6 all pass. A criterion whose records are missing fails, naming
what is missing. Each criterion's "passes" is true, false or "not run" (an Earth Engine part, with
--offline), and so is the check's: false if any criterion is false, else "not run" if any is not
run, else true.

Output. The results file (default <records>/r14_live_check.json; refused, as is its run record, if
it is there already, unless --overwrite) holds each criterion's numbers and "passes", and the
check's "passes": results only, no times or dates, so that a second check of the same records
writes the same file. Beside it, <name>_run.json: the command, when it ran (UTC), the git block of
this script's checkout (fmu.utils.provenance.git_state, read at the start of main(), without its
root), the records folder, the SHA-256 of every file read, and the Earth Engine calls that
forbid_writes replaced. Times go to the log (what this script prints).

Exit 0 when the check passes; 1 when it fails; 2 when nothing failed but a part was not run
(--offline); 3, nothing written, when the output is there (without --overwrite), the records
folder is not, the two configs have one name, or a manifest cannot be read; 4, nothing written,
when Earth Engine cannot be set up or read.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib
import io
import json
import math
import re
import shlex
import sys
import time
from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, TypeGuard, cast

import shapely
from shapely.geometry import shape

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
# This checkout's fmu first, not an editable install of another; scripts/ (last) for ee_read_only
# and copy_run_results.
if str(REPO / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "src"))
if str(REPO / "scripts") not in sys.path:
    sys.path.append(str(REPO / "scripts"))

from copy_run_results import STAMP, time_keys  # noqa: E402

from fmu.utils.provenance import git_state  # noqa: E402
from fmu.utils.region_merge import PROVENANCE_FIELDS  # noqa: E402

RUN_A = "odisha_v120_3ha_squares_angul_keptland_s1desc_r14_check_a"
RUN_B = "odisha_v120_3ha_squares_angul_keptland_s1desc_r14_check_b"
CONFIG_A = REPO / "configs" / f"{RUN_A}.yaml"
CONFIG_B = REPO / "configs" / f"{RUN_B}.yaml"
RECORDS = REPO / "docs" / "reproducibility" / "r14_runs" / "live_check"
OUT_NAME = "r14_live_check.json"

RELATIVE = 1e-9
FLOOR = 1e-12
S1_SCENES = 189
DECIMALS_SHARE = 0.99
SAMPLE_PIXELS = 5000
SAMPLE_ASKED = 10_000
SAMPLE_SEED = 42
DISTANCE_CAP_M = 10000.0
NOT_RUN = "not run"
# A request deadline, so that a read issued during a network drop fails rather than hangs.
DEADLINE_MS = 7 * 60 * 1000

KINDS = ("features", "segmentation", "k_elbow", "clustering", "export")
CHECKED_KINDS = ("features", "segmentation", "k_elbow", "clustering")
MANIFEST = re.compile(r"_manifest_(features|segmentation|k_elbow|clustering|export)(?:_(\d+))?\.json")
FAILED_LOG = re.compile(r"_log_failed_(\d+)\.txt")
EXPORT_LINE = re.compile(r"Started cache (?:table )?export to (\S+) \(task ")
# fmu's stage modules, whose stage classes say what each stage caches.
STAGE_MODULES = ("masking", "data_load", "features_optical", "features_radar", "features_structure",
                 "features_static", "features_embedding", "segmentation", "merge", "k_elbow",
                 "clustering", "profiling", "export", "metrics")
# The four settings of round 14's Task 2, on in every R3 config: (block, field, value).
SETTINGS = (
    ("clustering", "fit_outside_earth_engine", True),
    ("clustering", "log_rule", "right_skew"),
    ("features_optical", "mean_over_window", True),
    ("k_elbow", "in_fit_space", True),
)
# 2 iii: the cached assets compared, in the pipeline's order: (stage, key, label-like).
ASSETS = (
    ("masking", "habitat_mask", True),
    ("masking", "landcover_summary", True),
    ("masking", "mask_provenance", True),
    ("masking", "water_mask", True),
    ("data_load", "s2_composite", False),
    ("features_optical", "optical_features", False),
    ("features_radar", "radar_features", False),
    ("features_structure", "structure_features", False),
    ("features_static", "static_features", False),
    ("segmentation", "snic_clusters", True),
    ("segmentation", "snic_means", False),
    ("clustering", "cluster_labels", True),
    ("clustering", "feature_stack", False),
)
STATIC = ("features_static", "static_features")
SLOPE_ASPECT = ("slope", "aspect")
# The properties of a stand layer that are not feature means (2 ii).
GEOMETRY_ATTRIBUTES = ("perim_m", "centroid_lat", "centroid_lon")
NOT_FEATURE_MEANS = frozenset({"stand_lbl", "stand_id", "snic_label", "unit_id", "cluster_id",
                               "n_pixels", "area_ha", *GEOMETRY_ATTRIBUTES, *PROVENANCE_FIELDS,
                               "_sort_key"})
# Layer -> (the pair key, the label of the canonical form, part of criterion 1).
LAYERS = {
    "stands_merged": (("stand_lbl", "stand_id"), "stand_lbl", True),
    "stands_snic": (("snic_label", "stand_id"), "snic_label", False),
    "stands_dissolved": (("unit_id",), "cluster_id", False),
}
TABLES = ("k_elbow_stand_table.csv", "clustering_stand_table.csv")


class MissingRecordError(Exception):
    """A file the check needs is not in the records, or not as its off-git record says."""


# ---------------------------------------------------------------------------
# Numbers agree (module docstring)
# ---------------------------------------------------------------------------


def is_number(v: Any) -> TypeGuard[int | float]:
    return isinstance(v, int | float) and not isinstance(v, bool)


def agree(a: Any, b: Any) -> bool:
    """Whether two values agree: |a - b| <= 1e-9 x max(|a|, |b|) or |a - b| <= 1e-12 for
    numbers; null with null; anything else only when equal."""
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if is_number(a) and is_number(b):
        x, y = float(a), float(b)
        if math.isnan(x) or math.isnan(y):
            return math.isnan(x) and math.isnan(y)
        if x == y:
            return True
        d = abs(x - y)
        return d <= FLOOR or d <= RELATIVE * max(abs(x), abs(y))
    return bool(a == b)


def relative_difference(a: float, b: float) -> float:
    """|a - b| / max(|a|, |b|), 0 where |a - b| <= 1e-12 (and for two NaNs); inf for a NaN
    against a number."""
    x, y = float(a), float(b)
    if math.isnan(x) or math.isnan(y):
        return 0.0 if (math.isnan(x) and math.isnan(y)) else math.inf
    if x == y:
        return 0.0
    d = abs(x - y)
    if d <= FLOOR:
        return 0.0
    return d / max(abs(x), abs(y))


class Largest:
    """The largest relative difference seen, and where (None while every one is 0)."""

    def __init__(self) -> None:
        self.value = 0.0
        self.where: str | None = None

    def see(self, a: Any, b: Any, where: str) -> None:
        if is_number(a) and is_number(b):
            r = relative_difference(a, b)
            if r > self.value:
                self.value, self.where = r, where


def combine(values: Iterable[bool | str]) -> bool | str:
    """False if any is False, else "not run" if any is not run, else True."""
    values = list(values)
    if any(v is False for v in values):
        return False
    if any(v == NOT_RUN for v in values):
        return NOT_RUN
    return True


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# The records
# ---------------------------------------------------------------------------


class Records:
    """The records folder: a file by name, from the folder, or from the "where" of its entry in a
    <run>_files_off_git.json, checked against the SHA-256 recorded there. Every file read is kept
    with its SHA-256, for the run record."""

    def __init__(self, folder: Path):
        self.folder = folder
        self.read: dict[str, str] = {}
        self._off_git: dict[str, dict[str, Any]] = {}
        for record in sorted(folder.glob("*_files_off_git.json")):
            for entry in json.loads(record.read_text()).get("files", []):
                self._off_git[str(entry["file"])] = entry
            self.read[record.name] = sha256(record.read_bytes())

    def names(self) -> set[str]:
        return {p.name for p in self.folder.iterdir() if p.is_file()} | set(self._off_git)

    def data(self, name: str) -> bytes:
        path = self.folder / name
        if path.is_file():
            data = path.read_bytes()
        elif name in self._off_git:
            entry = self._off_git[name]
            where = Path(str(entry.get("where", "")))
            if not where.is_file():
                raise MissingRecordError(f"{name}: off git, and not at {where}")
            data = where.read_bytes()
            if sha256(data) != entry.get("sha256"):
                raise MissingRecordError(f"{name}: the file at {where} is not the one its off-git record names")
        else:
            raise MissingRecordError(f"{name}: not in the records")
        self.read[name] = sha256(data)
        return data

    def text(self, name: str) -> str:
        return self.data(name).decode()

    def json(self, name: str) -> Any:
        return json.loads(self.data(name))


Manifests = dict[str, list[tuple[str, dict[str, Any]]]]


def run_manifests(records: Records, run: str) -> Manifests:
    """Every manifest of a run, by kind, each kind in the order its passes ran: _1, _2, ..., then
    the one with no number, the last (as scripts/copy_run_results.py names them)."""
    found: dict[str, list[tuple[float, str]]] = {}
    for name in records.names():
        if not name.startswith(f"{run}_manifest_"):
            continue
        m = MANIFEST.fullmatch(name[len(run):])
        if m:
            found.setdefault(m.group(1), []).append((int(m.group(2)) if m.group(2) else math.inf, name))
    return {kind: [(name, records.json(name)) for _, name in sorted(found[kind])]
            for kind in KINDS if kind in found}


def all_manifests(by_kind: Manifests) -> list[tuple[str, dict[str, Any]]]:
    return [item for kind in KINDS for item in by_kind.get(kind, [])]


def failed_exports(records: Records, run: str) -> dict[str, str]:
    """The asset names (<run>/<stage>/<key>__<cache key>) that the run's failed passes exported,
    each with the log that says so."""
    out: dict[str, str] = {}
    for name in sorted(records.names()):
        if not (name.startswith(f"{run}_log_failed_") and FAILED_LOG.fullmatch(name[len(run):])):
            continue
        for path in EXPORT_LINE.findall(records.text(name)):
            out.setdefault("/".join(path.split("/")[-3:]), name)
    return out


def recorded_keys(by_kind: Manifests) -> tuple[set[Any], dict[str, set[Any]]]:
    """The cache layouts the run's manifests record, and each stage's cache keys."""
    layouts: set[Any] = set()
    keys: dict[str, set[Any]] = {}
    for _, m in all_manifests(by_kind):
        layouts.add(m.get("cache_layout"))
        for s in m.get("stages") or []:
            if s.get("cache_key") is not None:
                keys.setdefault(s["name"], set()).add(s["cache_key"])
    return layouts, keys


_CACHEABLE: dict[str, set[str]] = {}


def stage_modules() -> list[Any]:
    """fmu's stage modules, imported (which registers their stages)."""
    return [importlib.import_module(f"fmu.stages.{name}") for name in STAGE_MODULES]


def cacheable_outputs(stage: str) -> set[str] | None:
    """What fmu declares the stage caches (Pipeline._resolve_cacheable_outputs), read from the
    stage classes of fmu's stage modules (not the registry, which a test may have cleared); None
    for a stage fmu does not have."""
    if not _CACHEABLE:
        from fmu.pipeline import Pipeline
        from fmu.stages.base import Stage

        for module in stage_modules():
            for obj in vars(module).values():
                if (isinstance(obj, type) and issubclass(obj, Stage) and obj is not Stage
                        and obj.__module__ == module.__name__):
                    stage_class = cast("type[Stage]", obj)
                    _CACHEABLE[stage_class.name] = set(Pipeline._resolve_cacheable_outputs(stage_class()))
    return _CACHEABLE.get(stage)


# ---------------------------------------------------------------------------
# 0. Both runs from scratch
# ---------------------------------------------------------------------------


def from_scratch_of_run(run: str, by_kind: Manifests, exported_by_failed: dict[str, str]) -> dict[str, Any]:
    owner: dict[str, str] = {}
    kinds: dict[str, Any] = {}
    accepted: list[dict[str, Any]] = []
    unknown: list[str] = []
    ok = True
    for kind in CHECKED_KINDS:
        if not by_kind.get(kind):
            kinds[kind] = {"manifest": None, "passes": False}
            ok = False
            continue
        name, manifest = by_kind[kind][0]
        adds: list[str] = []
        computed: list[str] = []
        not_computed: list[dict[str, Any]] = []
        for s in manifest.get("stages") or []:
            stage = s["name"]
            owner.setdefault(stage, kind)
            if owner[stage] != kind:
                continue
            adds.append(stage)
            status = s.get("cache_status") or {}
            declared = cacheable_outputs(stage)
            if declared is None:
                unknown.append(stage)
                declared = set()
            for key in sorted(declared | set(status)):
                output, state = f"{stage}/{key}", status.get(key)
                if state == "miss-exported":
                    computed.append(output)
                    continue
                log = exported_by_failed.get(f"{run}/{stage}/{key}__{s.get('cache_key')}")
                if state == "hit" and log:
                    accepted.append({"output": output, "manifest": name, "exported_by": log})
                    continue
                not_computed.append({"output": output, "cache_status": state})
        passes = not not_computed
        ok = ok and passes
        kinds[kind] = {"manifest": name, "stages_it_adds": adds, "computed_in_it": computed,
                       "not_computed_in_it": not_computed, "passes": passes}
    layouts, keys = recorded_keys(by_kind)
    several = [{"stage": stage, "cache_keys": sorted(map(str, k))}
               for stage, k in sorted(keys.items()) if len(k) > 1]
    one_layout_and_key = len(layouts) == 1 and not several
    return {
        "first_manifests": kinds,
        "hits_made_by_a_failed_pass": accepted,
        "cache_layouts": sorted(map(str, layouts)),
        "stages_with_more_than_one_cache_key": several,
        "one_layout_and_one_key_per_stage": one_layout_and_key,
        "stages_fmu_does_not_have": sorted(set(unknown)),
        "passes": ok and one_layout_and_key and not unknown,
    }


# ---------------------------------------------------------------------------
# 1. The same stands; 2 ii, the feature means
# ---------------------------------------------------------------------------


def _key(feature: dict[str, Any], fields: Sequence[str]) -> str:
    return json.dumps([(feature.get("properties") or {}).get(f) for f in fields])


def normal_form(geometry: dict[str, Any] | None) -> bytes | None:
    """A GeoJSON geometry in normal form: shapely.normalize, as WKB (little-endian). It puts the
    rings of a polygon and the parts of a multipolygon in one order, starts each ring at one vertex
    and turns it one way, and changes no coordinate: two geometries have one normal form only when
    they have the same type and the same coordinates, number for number, however they are listed."""
    if geometry is None:
        return None
    return cast(bytes, shapely.to_wkb(shapely.normalize(shape(geometry)), byte_order=1))


def canonical_sha256(features: list[dict[str, Any]], label: str) -> str:
    def item(f: dict[str, Any]) -> str:
        form = normal_form(f.get("geometry"))
        return json.dumps([(f.get("properties") or {}).get(label), None if form is None else form.hex()],
                          sort_keys=True, separators=(",", ":"))

    return sha256(("[" + ",".join(sorted(item(f) for f in features)) + "]").encode())


def compare_values(pairs: list[tuple[dict[str, Any], dict[str, Any], str]],
                   names: Callable[[dict[str, Any]], set[str]]) -> dict[str, Any]:
    """The properties `names` picks, pair by pair: whether a pair's two polygons have the same
    ones, and whether each value agrees."""
    names_differ = compared = outside = 0
    largest = Largest()
    for pa, pb, _key_of_the_pair in pairs:
        na, nb = names(pa), names(pb)
        if na != nb:
            names_differ += 1
        for n in sorted(na & nb):
            compared += 1
            if not agree(pa[n], pb[n]):
                outside += 1
            largest.see(pa[n], pb[n], n)
    return {"pairs_whose_properties_differ_in_name": names_differ, "values_compared": compared,
            "values_not_agreeing": outside, "largest_relative_difference": largest.value,
            "in_property": largest.where,
            "passes": compared > 0 and names_differ == 0 and outside == 0}


def compare_layer(a: dict[str, Any], b: dict[str, Any], layer: str) -> dict[str, Any]:
    key_fields, label, _ = LAYERS[layer]
    fa, fb = list(a.get("features") or []), list(b.get("features") or [])

    def index(features: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], int]:
        out: dict[str, dict[str, Any]] = {}
        repeated = 0
        for f in features:
            k = _key(f, key_fields)
            repeated += k in out
            out[k] = f
        return out, repeated

    ia, repeated_a = index(fa)
    ib, repeated_b = index(fb)
    common = sorted(set(ia) & set(ib))
    pairs = [(ia[k], ib[k]) for k in common]
    props = [((x.get("properties") or {}), (y.get("properties") or {}), k) for (x, y), k in
             zip(pairs, common, strict=True)]
    labels_a = {(f.get("properties") or {}).get(label) for f in fa}
    labels_b = {(f.get("properties") or {}).get(label) for f in fb}
    geometry_differs = sum(normal_form(x.get("geometry")) != normal_form(y.get("geometry")) for x, y in pairs)
    geometry_differs_as_read = sum(x.get("geometry") != y.get("geometry") for x, y in pairs)
    size_differs = {f: sum(pa.get(f) != pb.get(f) for pa, pb, _ in props) for f in ("n_pixels", "area_ha")}
    cluster_differs = sum(pa.get("cluster_id") != pb.get("cluster_id") for pa, pb, _ in props)
    sha = [canonical_sha256(fa, label), canonical_sha256(fb, label)]
    passes = (
        len(fa) == len(fb) > 0 and len(labels_a) == len(labels_b)
        and repeated_a == repeated_b == 0 and len(common) == len(ia) == len(ib)
        and geometry_differs == 0 and not any(size_differs.values()) and cluster_differs == 0
        and sha[0] == sha[1]
    )
    out: dict[str, Any] = {
        "polygons": [len(fa), len(fb)],
        f"distinct_{label}": [len(labels_a), len(labels_b)],
        "paired_by": list(key_fields),
        "pairs": len(common),
        "keys_twice_in_a_layer": [repeated_a, repeated_b],
        "only_in_a": len(set(ia) - set(ib)),
        "only_in_b": len(set(ib) - set(ia)),
        "geometry_differs": geometry_differs,
        "geometry_differs_as_read": geometry_differs_as_read,
        "n_pixels_differs": size_differs["n_pixels"],
        "area_ha_differs": size_differs["area_ha"],
        "cluster_id_differs": cluster_differs,
        "canonical_sha256": sha,
        "same_canonical_sha256": sha[0] == sha[1],
        "feature_means": compare_values(props, lambda p: {n for n in p if n not in NOT_FEATURE_MEANS}),
        "passes": passes,
    }
    if layer == "stands_merged":
        out["provenance_differs"] = {
            f: sum(pa.get(f) != pb.get(f) for pa, pb, _ in props) for f in PROVENANCE_FIELDS}
        geometry_attrs = Largest()
        for pa, pb, _ in props:
            for f in GEOMETRY_ATTRIBUTES:
                geometry_attrs.see(pa.get(f), pb.get(f), f)
        out["geometry_attributes_largest_relative_difference"] = {
            "value": geometry_attrs.value, "in_property": geometry_attrs.where}
    return out


def read_csv(text: str) -> tuple[list[str], list[list[str]]]:
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return [], []
    return rows[0], rows[1:]


def _cell(text: str) -> float | str | None:
    """A cell of a table of units: a number, None when empty, else the text itself."""
    if text == "":
        return None
    try:
        return float(text)
    except ValueError:
        return text


def types_in_fit_rows(text_a: str, text_b: str) -> dict[str, Any]:
    """The "type" column of the two runs' clustering_fit_rows.csv, by unit label (the first
    column)."""
    by_run: list[dict[str, str]] = []
    labels: list[str] = []
    for text in (text_a, text_b):
        header, rows = read_csv(text)
        if "type" not in header:
            return {"problem": "a clustering_fit_rows.csv has no type column", "passes": False}
        t = header.index("type")
        if any(len(r) != len(header) for r in rows):
            return {"problem": "a clustering_fit_rows.csv has a row of another length than its header",
                    "passes": False}
        by_run.append({r[0]: r[t] for r in rows})
        labels.append(header[0])
        if len(by_run[-1]) != len(rows):
            return {"problem": "a clustering_fit_rows.csv has a label twice", "passes": False}
    ta, tb = by_run
    common = set(ta) & set(tb)
    out: dict[str, Any] = {
        "unit_label": labels,
        "labels": [len(ta), len(tb)],
        "same_labels": set(ta) == set(tb) and labels[0] == labels[1],
        "type_differs": sum(ta[k] != tb[k] for k in common),
    }
    out["passes"] = bool(ta) and out["same_labels"] and out["type_differs"] == 0
    return out


def same_stands(records: Records, run_a: str, run_b: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for layer in LAYERS:
        try:
            out[layer] = compare_layer(records.json(f"{run_a}_{layer}.geojson"),
                                       records.json(f"{run_b}_{layer}.geojson"), layer)
        except MissingRecordError as e:
            out[layer] = {"missing": str(e), "passes": False}
        out[layer]["part_of_the_pass"] = LAYERS[layer][2]
    try:
        out["types_in_clustering_fit_rows"] = types_in_fit_rows(
            records.text(f"{run_a}_clustering_fit_rows.csv"), records.text(f"{run_b}_clustering_fit_rows.csv"))
    except MissingRecordError as e:
        out["types_in_clustering_fit_rows"] = {"missing": str(e), "passes": False}
    out["passes"] = bool(out["stands_merged"]["passes"] and out["types_in_clustering_fit_rows"]["passes"])
    return out


# ---------------------------------------------------------------------------
# 2. The feature values and the elbows (offline parts)
# ---------------------------------------------------------------------------


def compare_table(text_a: str, text_b: str) -> dict[str, Any]:
    """A table of units (label, in_fit, bands), each against the other run's, label by label."""
    ha, ra = read_csv(text_a)
    hb, rb = read_csv(text_b)
    malformed = sum(len(r) != len(ha) for r in ra) + sum(len(r) != len(hb) for r in rb)
    by_a, by_b = {r[0]: r for r in ra if r}, {r[0]: r for r in rb if r}
    same_header = ha == hb and len(ha) >= 2 and ha[1] == "in_fit"
    same_labels = set(by_a) == set(by_b) and len(by_a) == len(ra) and len(by_b) == len(rb)
    in_fit_differs = compared = outside = 0
    largest = Largest()
    if same_header and not malformed:
        bands = ha[2:]
        for label in sorted(set(by_a) & set(by_b)):
            x, y = by_a[label], by_b[label]
            in_fit_differs += x[1] != y[1]
            for j, band in enumerate(bands, start=2):
                va, vb = _cell(x[j]), _cell(y[j])
                compared += 1
                outside += not agree(va, vb)
                largest.see(va, vb, band)
    return {
        "rows": [len(ra), len(rb)],
        "bands": max(len(ha) - 2, 0),
        "same_header": same_header,
        "same_labels": same_labels,
        "rows_of_another_length_than_the_header": malformed,
        "identical_bytes": text_a == text_b,
        "in_fit_differs": in_fit_differs,
        "values_compared": compared,
        "values_not_agreeing": outside,
        "largest_relative_difference": largest.value,
        "in_band": largest.where,
        "passes": (same_header and same_labels and not malformed and bool(ra)
                   and in_fit_differs == 0 and outside == 0),
    }


def knee_of(text: str) -> int | None:
    """The k marked as the knee in a k_elbow.csv, or None (none, several, or unreadable)."""
    header, rows = read_csv(text)
    if "is_knee" not in header or "k" not in header:
        return None
    k, knee = header.index("k"), header.index("is_knee")
    knees = [r[k] for r in rows if len(r) == len(header) and r[knee] == "1"]
    return int(knees[0]) if len(knees) == 1 and knees[0].isdigit() else None


def elbows(records: Records, run_a: str, run_b: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name in ("k_elbow.csv", "k_elbow_types.csv"):
        try:
            da, db = records.data(f"{run_a}_{name}"), records.data(f"{run_b}_{name}")
        except MissingRecordError as e:
            out[name] = {"missing": str(e), "passes": False}
            continue
        out[name] = {"sha256": [sha256(da), sha256(db)], "passes": sha256(da) == sha256(db)}
        if name == "k_elbow.csv":
            out[name]["knee"] = [knee_of(da.decode()), knee_of(db.decode())]
    out["passes"] = all(out[n]["passes"] for n in ("k_elbow.csv", "k_elbow_types.csv"))
    return out


def feature_values_offline(records: Records, run_a: str, run_b: str,
                           stands: dict[str, Any]) -> dict[str, Any]:
    tables: dict[str, Any] = {}
    for name in TABLES:
        try:
            tables[name] = compare_table(records.text(f"{run_a}_{name}"), records.text(f"{run_b}_{name}"))
        except MissingRecordError as e:
            tables[name] = {"missing": str(e), "passes": False}
    tables["passes"] = all(tables[n]["passes"] for n in TABLES)
    merged = stands.get("stands_merged") or {}
    means = merged.get("feature_means") or {"missing": merged.get("missing", "no merged pairs"),
                                            "passes": False}
    # Reported beside the pass: the scaled rows, which the tables and the declared preprocessing
    # determine.
    fit_rows: dict[str, Any] = {}
    for name in ("k_elbow_fit_rows.csv", "clustering_fit_rows.csv"):
        try:
            da, db = records.data(f"{run_a}_{name}"), records.data(f"{run_b}_{name}")
            fit_rows[name] = {"identical_bytes": da == db}
        except MissingRecordError as e:
            fit_rows[name] = {"missing": str(e)}
    return {
        "i_tables_of_units": tables,
        "ii_feature_means_of_stands_merged": means,
        "elbows": elbows(records, run_a, run_b),
        "reported_fit_rows": fit_rows,
    }


# ---------------------------------------------------------------------------
# 3, 4, 6: per run, from its records
# ---------------------------------------------------------------------------


def distance_to_water(layer: dict[str, Any]) -> dict[str, Any]:
    values = [(f.get("properties") or {}).get("distance_to_water") for f in layer.get("features") or []]
    with_value = [float(v) for v in values if is_number(v)]
    at_cap = sum(v == DISTANCE_CAP_M for v in with_value)
    distinct = len(set(with_value))
    return {
        "polygons": len(values),
        "polygons_with_no_value": len(values) - len(with_value),
        "exactly_10000": at_cap,
        "distinct_values": distinct,
        "least": min(with_value) if with_value else None,
        "greatest": max(with_value) if with_value else None,
        "passes": bool(with_value) and at_cap < len(with_value) and distinct > 1,
    }


def s1_counts(by_kind: Manifests) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for name, m in all_manifests(by_kind):
        for s in m.get("stages") or []:
            if s.get("name") != "features_radar":
                continue
            record = (s.get("input_images") or {}).get("radar_features") or {}
            s1 = (record.get("collections") or {}).get("s1") or {}
            records.append({"manifest": name, "source": record.get("source"), "count": s1.get("count"),
                            "sha256": s1.get("sha256")})
    first = by_kind.get("features", [(None, {})])[0][0]
    counts = [r["count"] for r in records if r["count"] is not None]
    first_has = any(r["manifest"] == first and r["count"] is not None for r in records)
    return {
        "manifests": records,
        "first_features_manifest_records_a_count": first_has,
        "counts": sorted(set(counts)),
        "passes": first_has and all(c == S1_SCENES for c in counts),
    }


def settings_on(by_kind: Manifests) -> dict[str, Any]:
    manifests = all_manifests(by_kind)
    off: list[dict[str, Any]] = []
    for name, m in manifests:
        config = m.get("config") or {}
        for block, field, value in SETTINGS:
            got = (config.get(block) or {}).get(field)
            if got != value:
                off.append({"manifest": name, "setting": f"{block}.{field}", "value": got})
    return {"manifests": len(manifests), "settings_not_on": off, "passes": bool(manifests) and not off}


def per_run(fn: Callable[[str], dict[str, Any]], runs: Sequence[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for run in runs:
        try:
            out[run] = fn(run)
        except MissingRecordError as e:
            out[run] = {"missing": str(e), "passes": False}
    return {"runs": out, "passes": all(out[r]["passes"] for r in runs)}


# ---------------------------------------------------------------------------
# The Earth Engine parts (2 iii and 5): through a reader the tests replace
# ---------------------------------------------------------------------------


class NoSuchAssetError(LookupError):
    """An asset criterion 5 samples is not on Earth Engine (its path, the argument)."""


class AssetReader(Protocol):
    """What the Earth Engine parts ask of Earth Engine (EarthEngineReader; a stand-in in the tests).
    For an asset that is not there, compare answers {"missing": [...]} and sample raises
    NoSuchAssetError."""

    def cache_layout(self, config: Any) -> str: ...

    def compare(self, path_a: str, path_b: str, *, roi_file: str, label_like: bool) -> dict[str, Any]: ...

    def sample(self, path: str, *, roi_file: str, bands: Sequence[str], n: int, asked: int,
               seed: int) -> list[list[Any]]: ...


def asset_path(reader: AssetReader, config: Any, stage: str, key: str, by_kind: Manifests,
               layouts: dict[str, str]) -> tuple[str | None, str | None]:
    """(fmu's path of a config's cached asset, None) when it is the one its run recorded; else
    (None, why)."""
    from fmu.utils.caching import cache_key, cached_asset_path

    if config.name not in layouts:
        layouts[config.name] = reader.cache_layout(config)
    layout = layouts[config.name]
    recorded_layouts, keys = recorded_keys(by_kind)
    key_now = cache_key(config, stage, layout)
    if recorded_layouts != {layout}:
        return None, (f"{config.name}: fmu finds its cache in the {layout} layout, and its "
                      f"manifests record {sorted(map(str, recorded_layouts))}")
    if keys.get(stage) != {key_now}:
        return None, (f"{config.name}: fmu's {stage} key is {key_now}, and its manifests record "
                      f"{sorted(map(str, keys.get(stage, set())))}")
    return cached_asset_path(config.name, stage, key, key_now), None


def judge_asset(stage: str, key: str, label_like: bool, path_a: str, path_b: str,
                got: dict[str, Any]) -> dict[str, Any]:
    """One row of 2 iii from what the reader got (EarthEngineReader.compare)."""
    row: dict[str, Any] = {"stage": stage, "key": key, "label_like": label_like,
                           "asset_a": path_a, "asset_b": path_b}
    if got.get("missing"):
        row.update({"not_cached": got["missing"], "passes": False})
        return row
    same_bands = got["bands_a"] == got["bands_b"]
    same_grid = got["grid_a"] == got["grid_b"]
    row.update({"bands": got["bands_a"], "same_bands": same_bands, "same_grid": same_grid})
    if not (same_bands and same_grid):
        row.update({"bands_b": got["bands_b"], "grid_a": got["grid_a"], "grid_b": got["grid_b"],
                    "passes": False})
        return row
    per_band = got.get("per_band") or {}
    bands = list(got["bands_a"])

    def of(band: str, name: str) -> Any:
        return (per_band.get(band) or {}).get(name)

    def total(name: str) -> int:
        return int(sum(int(of(b, name) or 0) for b in bands))

    row["pixels_compared"] = total("n_compared")
    row["pixels_whose_mask_differs"] = total("n_mask_differs")
    if label_like:
        row["pixels_whose_values_differ"] = total("n_differ")
        bad = row["pixels_whose_values_differ"]
    else:
        row["pixels_whose_values_do_not_agree"] = total("n_not_agreeing")
        bad = row["pixels_whose_values_do_not_agree"]
        rel = {b: float(of(b, "largest_relative_difference") or 0.0) for b in bands}
        worst = max(bands, key=lambda b: rel[b]) if bands else None
        row["largest_relative_difference"] = rel[worst] if worst else None
        row["in_band"] = worst if worst and rel[worst] > 0 else None
        row["largest_abs_difference"] = max(
            (float(of(b, "largest_abs_difference") or 0.0) for b in bands), default=None)
    # A list, so that a band's name is never a key of the results file.
    row["per_band"] = [{"band": b, **(per_band.get(b) or {})} for b in bands]
    row["passes"] = (bool(bands) and row["pixels_compared"] > 0
                     and row["pixels_whose_mask_differs"] == 0 and bad == 0)
    return row


def cached_assets(reader: AssetReader, cfg_a: Any, cfg_b: Any, mans_a: Manifests,
                  mans_b: Manifests, layouts: dict[str, str]) -> dict[str, Any]:
    rows = []
    for stage, key, label_like in ASSETS:
        pa, why_a = asset_path(reader, cfg_a, stage, key, mans_a, layouts)
        pb, why_b = asset_path(reader, cfg_b, stage, key, mans_b, layouts)
        if pa is None or pb is None:
            rows.append({"stage": stage, "key": key, "label_like": label_like,
                         "not_the_recorded_asset": [w for w in (why_a, why_b) if w], "passes": False})
            continue
        t0 = time.monotonic()
        got = reader.compare(pa, pb, roi_file=cfg_a.roi.roi_file, label_like=label_like)
        rows.append(judge_asset(stage, key, label_like, pa, pb, got))
        print(f"  2 iii {stage}/{key}: passes {rows[-1]['passes']} ({time.monotonic() - t0:.0f} s)",
              flush=True)
    return {"assets": rows,
            "cache_layouts": [{"config": name, "layout": layout} for name, layout in sorted(layouts.items())],
            "passes": bool(rows) and all(r["passes"] for r in rows)}


def has_decimals(v: Any) -> bool:
    """A finite number that is not a whole number."""
    return is_number(v) and math.isfinite(v) and not float(v).is_integer()


def at_a_multiple_of_45(v: Any) -> bool:
    return is_number(v) and math.isfinite(v) and float(v) % 45 == 0


def decimals(values: Sequence[Sequence[Any]]) -> dict[str, Any]:
    """5: among the sampled pixels with slope above 0, the share whose slope is not a whole
    number; and, of those whose aspect is not at a multiple of 45 degrees (set aside: on a DEM of
    whole metres a correct aspect is a whole number there), the share whose aspect is not one."""
    sloped = [(float(s), a) for s, a in values if is_number(s) and s > 0]
    n = len(sloped)
    slope_decimal = sum(has_decimals(s) for s, _ in sloped)
    judged = [a for _, a in sloped if not at_a_multiple_of_45(a)]
    aspect_decimal = sum(has_decimals(a) for a in judged)
    share_slope = slope_decimal / n if n else None
    share_aspect = aspect_decimal / len(judged) if judged else None
    return {
        "pixels_sampled": len(values),
        "pixels_with_slope_above_0": n,
        "slope_not_a_whole_number": slope_decimal,
        "aspect_at_a_multiple_of_45": n - len(judged),
        "aspect_not_at_a_multiple_of_45": len(judged),
        "aspect_not_a_whole_number": aspect_decimal,
        "share_slope_not_whole": share_slope,
        "share_aspect_not_whole": share_aspect,
        "passes": share_slope is not None and share_aspect is not None
        and share_slope >= DECIMALS_SHARE and share_aspect >= DECIMALS_SHARE,
    }


def slope_and_aspect(reader: AssetReader, cfg_a: Any, mans_a: Manifests,
                     layouts: dict[str, str]) -> dict[str, Any]:
    stage, key = STATIC
    path, why = asset_path(reader, cfg_a, stage, key, mans_a, layouts)
    if path is None:
        return {"not_the_recorded_asset": why, "passes": False}
    try:
        values = reader.sample(path, roi_file=cfg_a.roi.roi_file, bands=SLOPE_ASPECT, n=SAMPLE_PIXELS,
                               asked=SAMPLE_ASKED, seed=SAMPLE_SEED)
    except NoSuchAssetError:
        return {"asset": path, "not_on_earth_engine": [path], "passes": False}
    return {"asset": path, "sample": {"asked": SAMPLE_ASKED, "limit": SAMPLE_PIXELS, "seed": SAMPLE_SEED},
            **decimals(values)}


def earth_engine_parts(reader: AssetReader, cfg_a: Any, cfg_b: Any,
                       mans: dict[str, Manifests]) -> dict[str, Any]:
    """2 iii and 5, read-only on Earth Engine through `reader`."""
    layouts: dict[str, str] = {}
    return {
        "iii": cached_assets(reader, cfg_a, cfg_b, mans[cfg_a.name], mans[cfg_b.name], layouts),
        "5": slope_and_aspect(reader, cfg_a, mans[cfg_a.name], layouts),
    }


class EarthEngineReader:
    """The Earth Engine side of 2 iii and 5, on a session that can submit or change nothing."""

    def __init__(self, ee: Any, forbidden: list[str]):
        self.ee = ee
        self.forbidden = forbidden
        self._rois: dict[str, Any] = {}

    def _roi(self, roi_file: str) -> Any:
        from fmu.utils.gee import load_roi_geometry

        if roi_file not in self._rois:
            self._rois[roi_file] = load_roi_geometry(roi_file)
        return self._rois[roi_file]

    def cache_layout(self, config: Any) -> str:
        from fmu.pipeline import cache_layout_for

        stage_modules()  # cache_layout_for looks only at the stages registered
        return cache_layout_for(config)[0]

    def compare(self, path_a: str, path_b: str, *, roi_file: str, label_like: bool) -> dict[str, Any]:
        from fmu.utils.caching import asset_exists
        from fmu.utils.gee import safe_get_info

        ee = self.ee
        missing = [p for p in (path_a, path_b) if not asset_exists(p)]
        if missing:
            return {"missing": missing}
        a, b = ee.Image(path_a), ee.Image(path_b)
        bands_a = safe_get_info(a.bandNames(), context=f"{path_a} bands")
        bands_b = safe_get_info(b.bandNames(), context=f"{path_b} bands")
        proj_a = safe_get_info(a.projection(), context=f"{path_a} projection")
        proj_b = safe_get_info(b.projection(), context=f"{path_b} projection")
        grid_a = {"crs": proj_a.get("crs"), "transform": proj_a.get("transform")}
        grid_b = {"crs": proj_b.get("crs"), "transform": proj_b.get("transform")}
        out: dict[str, Any] = {"bands_a": bands_a, "bands_b": bands_b, "grid_a": grid_a,
                               "grid_b": grid_b, "per_band": {}}
        if bands_a != bands_b or grid_a != grid_b:
            return out
        kw = {"geometry": self._roi(roi_file), "crs": grid_a["crs"], "crsTransform": grid_a["transform"],
              "maxPixels": int(1e10), "tileScale": 4}
        count = ee.Reducer.count().unweighted()
        total = ee.Reducer.sum().unweighted()
        # Unweighted throughout: a pixel counts once if its centre is in the ROI.
        mask_differs = a.mask().neq(b.mask()).unmask(0)
        if label_like:
            neq = a.neq(b)
            reductions = {
                "n_compared": neq.reduceRegion(reducer=count, **kw),
                "n_differ": neq.reduceRegion(reducer=total, **kw),
                "n_mask_differs": mask_differs.reduceRegion(reducer=total, **kw),
            }
        else:
            da, db = a.toDouble(), b.toDouble()
            diff = da.subtract(db).abs()
            top = da.abs().max(db.abs())
            not_agreeing = diff.gt(FLOOR).And(diff.gt(top.multiply(RELATIVE)))
            relative = diff.divide(top.where(top.eq(0), 1)).where(diff.lte(FLOOR), 0)
            reductions = {
                "n_compared": diff.reduceRegion(reducer=count, **kw),
                "n_not_agreeing": not_agreeing.reduceRegion(reducer=total, **kw),
                "largest_relative_difference": relative.reduceRegion(reducer=ee.Reducer.max(), **kw),
                "largest_abs_difference": diff.reduceRegion(reducer=ee.Reducer.max(), **kw),
                "n_mask_differs": mask_differs.reduceRegion(reducer=total, **kw),
            }
        got = safe_get_info(ee.Dictionary(reductions), context=f"{path_a} against {path_b}")
        out["per_band"] = {band: {name: (got.get(name) or {}).get(band) for name in reductions}
                           for band in bands_a}
        return out

    def sample(self, path: str, *, roi_file: str, bands: Sequence[str], n: int, asked: int,
               seed: int) -> list[list[Any]]:
        from fmu.utils.caching import asset_exists
        from fmu.utils.gee import safe_get_info

        ee = self.ee
        if not asset_exists(path):
            raise NoSuchAssetError(path)
        drawn = ee.Image(path).select(list(bands)).sample(
            region=self._roi(roi_file), numPixels=asked, seed=seed, dropNulls=True,
            geometries=False, tileScale=4)
        kept = drawn.randomColumn("live_check_order", seed).sort("live_check_order").limit(n)
        got = safe_get_info(kept.reduceColumns(reducer=ee.Reducer.toList(len(bands)),
                                               selectors=list(bands)), context=f"{path} sample")
        return [list(row) for row in ((got or {}).get("list") or [])]


def earth_engine_reader() -> AssetReader:
    """Earth Engine set up, its writing calls replaced (ee_read_only.forbid_writes), a deadline."""
    import ee
    import ee_read_only

    from fmu.utils.gee import init_gee

    init_gee()
    forbidden = ee_read_only.forbid_writes()
    ee.data.setDeadline(DEADLINE_MS)
    return EarthEngineReader(ee, forbidden)


# ---------------------------------------------------------------------------
# The check
# ---------------------------------------------------------------------------


def check(records: Records, cfg_a: Any, cfg_b: Any, mans: dict[str, Manifests],
          on_earth_engine: dict[str, Any] | None) -> dict[str, Any]:
    """Every criterion, from the records, with the Earth Engine parts as earth_engine_parts gave
    them (None: not run). Results only."""
    a, b = cfg_a.name, cfg_b.name
    criteria: dict[str, Any] = {}

    criteria["0_both_runs_from_scratch"] = per_run(
        lambda run: from_scratch_of_run(run, mans[run], failed_exports(records, run)), (a, b))

    stands = same_stands(records, a, b)
    criteria["1_same_stands_and_types"] = stands

    values = feature_values_offline(records, a, b, stands)
    values["iii_cached_assets"] = on_earth_engine["iii"] if on_earth_engine else {"passes": NOT_RUN}
    values["passes"] = combine(values[p]["passes"] for p in (
        "i_tables_of_units", "ii_feature_means_of_stands_merged", "iii_cached_assets", "elbows"))
    criteria["2_feature_values_and_elbows"] = values

    criteria["3_distance_to_water"] = per_run(
        lambda run: distance_to_water(records.json(f"{run}_stands_merged.geojson")), (a, b))
    criteria["4_sentinel1_scenes"] = {**per_run(lambda run: s1_counts(mans[run]), (a, b)),
                                      "expected": S1_SCENES}
    criteria["5_slope_and_aspect_decimals"] = (
        on_earth_engine["5"] if on_earth_engine else {"passes": NOT_RUN})
    criteria["6_four_settings_on"] = per_run(lambda run: settings_on(mans[run]), (a, b))

    return {
        "what": "Round 14's live check (Task 4): two runs of one config, each from scratch, compared "
                "by the rules declared in odisha_script/r14_live_check.py. Results only.",
        "runs": [a, b],
        "agreement_rule": {"relative": RELATIVE, "absolute_floor": FLOOR},
        "criteria": criteria,
        "passes": combine(c["passes"] for c in criteria.values()),
    }


def exit_code(passes: bool | str) -> int:
    return 0 if passes is True else (2 if passes == NOT_RUN else 1)


def results_only(result: dict[str, Any]) -> None:
    """Refuse a result holding a key that names a time or a value holding a date and time."""
    text = json.dumps(result)
    left = time_keys(result)
    if left or STAMP.search(text):
        raise SystemExit(f"the results would hold times: {left[:5] or STAMP.findall(text)[:5]}")


def main(argv: list[str] | None = None,
         reader: Callable[[], AssetReader] = earth_engine_reader) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--records", type=Path, default=RECORDS,
                    help="the folder scripts/copy_run_results.py copied both runs into")
    ap.add_argument("--config-a", type=Path, default=CONFIG_A)
    ap.add_argument("--config-b", type=Path, default=CONFIG_B)
    ap.add_argument("--out", type=Path, default=None, help=f"the results file (default <records>/{OUT_NAME})")
    ap.add_argument("--overwrite", action="store_true", help="write over an existing results file")
    ap.add_argument("--offline", action="store_true",
                    help="read no Earth Engine: 2 iii and 5 are not run")
    args = ap.parse_args(argv)
    given = sys.argv[1:] if argv is None else argv
    command_line = " ".join(["python", "odisha_script/r14_live_check.py", *map(shlex.quote, given)])

    # Which code: this script's checkout, as it is before anything is read or written.
    git = {k: v for k, v in git_state(HERE).items() if k != "root"}

    out: Path = args.out or args.records / OUT_NAME
    run_record = out.with_name(out.stem + "_run.json")
    there = [p for p in (out, run_record) if p.exists()]
    if there and not args.overwrite:
        print(f"REFUSED, nothing written: {', '.join(map(str, there))} is there already "
              f"(--overwrite writes over it)", file=sys.stderr)
        return 3
    if not args.records.is_dir():
        print(f"REFUSED, nothing written: no records folder {args.records}", file=sys.stderr)
        return 3

    from fmu.config import load_config

    cfg_a, cfg_b = load_config(args.config_a), load_config(args.config_b)
    if cfg_a.name == cfg_b.name:
        print(f"REFUSED, nothing written: both configs are {cfg_a.name}", file=sys.stderr)
        return 3
    records = Records(args.records)
    try:
        mans = {cfg.name: run_manifests(records, cfg.name) for cfg in (cfg_a, cfg_b)}
    except MissingRecordError as e:
        print(f"REFUSED, nothing written: a manifest cannot be read: {e}", file=sys.stderr)
        return 3
    t0 = time.monotonic()
    on_earth_engine: dict[str, Any] | None = None
    forbidden: list[str] | None = None
    if not args.offline:
        try:
            asset_reader = reader()
            forbidden = getattr(asset_reader, "forbidden", None)
            on_earth_engine = earth_engine_parts(asset_reader, cfg_a, cfg_b, mans)
        except Exception as e:  # noqa: BLE001 - a failure to read Earth Engine stops the run before it writes
            print(f"FAILED to read Earth Engine, nothing written: {e!r}", file=sys.stderr)
            return 4
    result = check(records, cfg_a, cfg_b, mans, on_earth_engine)
    results_only(result)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1) + "\n")
    run_record.write_text(json.dumps({
        "result_file": out.name,
        "command_line": command_line,
        "ran_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git": git,
        "offline": args.offline,
        "records": str(args.records),
        "configs": [str(args.config_a), str(args.config_b)],
        "earth_engine_writes_forbidden": forbidden,
        "files_read_sha256": dict(sorted(records.read.items())),
    }, indent=1) + "\n")
    for name, c in result["criteria"].items():
        print(f"  {name}: passes {c['passes']}")
    print(f"the check passes: {result['passes']} ({time.monotonic() - t0:.0f} s); wrote {out} and "
          f"{run_record.name}")
    return exit_code(result["passes"])


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

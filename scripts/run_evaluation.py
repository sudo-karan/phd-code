"""Apply the evaluation metrics of `fmu.evaluation` to one site's reference data.

**This script refuses to run without `--predeclared FILE`**: a written statement
of the analysis (which statistics, which null model, which distance bands, how
many relabellings, what will count as support), made before any result is seen.
Analyses are declared before they are run (CLAUDE.md, "Results"; the pattern is
`odisha_script/PHASE3_PREDECLARED.md`). The sha256 of that file goes into the
manifest and into the results, so a result can always be traced to the
declaration it was run under. What must be declared is listed in
`docs/evaluation_metrics.md`, "Before running on real data".

It is general: no site names and no fixed column names. Every column and every
property is named on the command line.

Inputs
    --plots FILE.csv          one row per field plot. Columns are named with
                              --stand-id-col, --stand-type-col, --x-col,
                              --y-col, --attribute-cols, --field-type-col,
                              --group-col (village forest), --super-group-col
                              (the unit stand types were fitted in: a district).
    --stand-polygons FILE     the stand map, GeoJSON, projected metres, the
                              same coordinate system as the plots.
    --regions FILE            GeoJSON of the area the plots of each group may
                              be moved in (the village forest); needed by the
                              rotation null.
    --reference-polygons FILE GeoJSON of reference polygons (a compartment
                              map), for the segmentation-accuracy measures.

What is computed
    The statistics named with --statistics (any of the twelve of
    `fmu.evaluation`), each with its descriptive tables, and each tested
    against ONE null model (--null) with --n-permutations relabellings and
    --seed. The rotation null needs --stand-polygons and --regions. The torus
    translation needs a gridded map and is not offered here. With
    --reference-polygons: over- and under-segmentation and, if
    --boundary-tolerance is given, the boundary match.

    The measures that need no reference data (explained variance, Global
    Score) work on rasters and are not run by this script: explained variance
    is reported by the pipeline's metrics stage, and the Global Score is
    `fmu.evaluation.unsupervised.global_score`.

Outputs, in --out-dir
    evaluation_results.json   results only: no run times, no dates, no paths.
                              The same inputs, arguments and seed give the same
                              file byte for byte.
    evaluation_manifest.json  what was run: the git commit and whether the tree
                              had uncommitted changes (`fmu.utils.provenance`),
                              the predeclaration and its sha256, the sha256 of
                              every input file, the arguments, library versions.

    An existing results file is never overwritten unless --overwrite is given.

Example (made-up names):

    .venv/bin/python scripts/run_evaluation.py \
        --predeclared path/to/PREDECLARED.md \
        --plots plots.csv --stand-id-col stand --stand-id-scope super-group \
        --stand-type-col type --x-col x --y-col y \
        --attribute-cols height cover basal_area count --field-type-col field_type \
        --group-col village --super-group-col district \
        --stand-polygons stands.geojson --stand-polygons-type-property type \
        --regions forests.geojson --regions-group-property village \
        --statistics pair_stand mantel_stand --null rotation \
        --band-edges 0 100 200 400 800 inf --n-permutations 1999 --seed 1 \
        --out-dir out/evaluation

Exit codes: 0 done; 2 refused (nothing was computed or written).
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import math
import os
import platform
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import shapely
from shapely.geometry import shape

from fmu.evaluation import agreement, pairs, permutation, spatial_null
from fmu.evaluation import segmentation_accuracy as segacc
from fmu.evaluation._common import (
    Statistic,
    check_one_type_per_stand,
    combine_labels,
    encode_labels,
)
from fmu.utils.provenance import git_state

RESULTS_NAME = "evaluation_results.json"
MANIFEST_NAME = "evaluation_manifest.json"

# The twelve statistics of the package, by their fixed names.
STATISTICS: tuple[str, ...] = (
    "ari_drawing",
    "ari_labelling",
    "pair_stand",
    "pair_type",
    "mantel_stand",
    "mantel_type",
    "partial_mantel_stand",
    "partial_mantel_type",
    "anosim_stand",
    "anosim_type",
    "permanova_stand",
    "permanova_type",
)
TYPE_STATISTICS = tuple(s for s in STATISTICS if s.endswith(("_type", "_labelling")))
NULLS: tuple[str, ...] = ("rotation", "within_group_permutation", "free_permutation")

# Written into the results whenever the null is a permutation of plots.
PERMUTATION_CAUTION = (
    "This null permutes plots. In the synthetic validation "
    "(docs/evaluation/synthetic_validation.md) permutation nulls gave false alarms far above "
    "5% for most statistics when the field data were spatially smooth. A small p-value under "
    "this null is not, on its own, evidence that the map agrees with the field."
)

# Numbers are written with this many significant digits. A sum of products can
# differ in its last binary digit from one run to the next (the linear-algebra
# library adds in a different order depending on where an array sits in
# memory), and a results file has to be the same byte for byte on a re-run.
SIGNIFICANT_DIGITS = 10

# Strings that mean "no value" in a table cell.
_EMPTY_CELLS = ("", "NA", "NaN", "nan", "None", "null")


class Refusal(Exception):  # noqa: N818 - it is a refusal, not an error in the code
    """The run is refused. Nothing is computed and nothing is written."""


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def to_plain(value: Any) -> Any:
    """Turn results into plain JSON values, the same way every time.

    `NaN` becomes `null` ("not estimable"), infinities become the strings
    `"inf"` and `"-inf"`, other numbers are rounded to `SIGNIFICANT_DIGITS`
    significant digits, tables become lists of rows, numpy numbers become
    Python numbers, and mapping keys become strings.
    """
    if isinstance(value, pd.DataFrame):
        return [to_plain(row) for row in value.to_dict(orient="records")]
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            f.name: to_plain(getattr(value, f.name))
            for f in dataclasses.fields(value)
            if not isinstance(getattr(value, f.name), pd.DataFrame | np.ndarray)
        }
    if isinstance(value, dict):
        return {str(k): to_plain(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [to_plain(v) for v in value]
    if isinstance(value, np.ndarray):
        return [to_plain(v) for v in value.tolist()]
    if isinstance(value, np.bool_ | bool):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, float | np.floating):
        number = float(value)
        if math.isnan(number):
            return None
        if math.isinf(number):
            return "inf" if number > 0 else "-inf"
        return float(f"{number:.{SIGNIFICANT_DIGITS}g}")
    return value


def write_json(path: Path, value: Any) -> None:
    text = json.dumps(to_plain(value), indent=1, sort_keys=True, allow_nan=False)
    path.write_text(text + "\n", encoding="utf-8")


def looks_like_degrees(xy: np.ndarray) -> bool:
    """True if every coordinate could be a longitude and latitude."""
    finite = xy[np.isfinite(xy).all(axis=1)]
    if finite.shape[0] == 0:
        return False
    return bool((np.abs(finite[:, 0]) <= 180).all() and (np.abs(finite[:, 1]) <= 90).all())


def predeclaration_git_status(path: Path) -> str:
    """Whether the predeclaration is committed: read-only, never raises.

    One of `committed_unmodified`, `tracked_modified`, `not_tracked`,
    `unknown`. A declaration that is not committed can be edited after the
    results are seen, so the manifest says which it was.
    """
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env["GIT_OPTIONAL_LOCKS"] = "0"
    folder = str(path.resolve().parent)
    name = path.name

    def git(*args: str) -> int:
        done = subprocess.run(  # noqa: S603 - fixed argv, no shell
            ["git", "-C", folder, *args], capture_output=True, timeout=10, env=env, check=False
        )
        return done.returncode

    try:
        if git("ls-files", "--error-unmatch", "--", name) != 0:
            return "not_tracked"
        if git("diff", "--quiet", "HEAD", "--", name) != 0:
            return "tracked_modified"
        return "committed_unmodified"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


# ---------------------------------------------------------------------------
# Reading the inputs
# ---------------------------------------------------------------------------


def read_table(path: Path) -> pd.DataFrame:
    """The plot table with every cell as text, so labels are never reinterpreted."""
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def _column(table: pd.DataFrame, name: str) -> list[str]:
    if name not in table.columns:
        raise Refusal(f"the plot table has no column {name!r}; it has {list(table.columns)}")
    return [str(cell).strip() for cell in table[name].tolist()]


def label_column(table: pd.DataFrame, name: str, missing: Sequence[str]) -> np.ndarray:
    """A label column as text, with `None` where the label is missing."""
    absent = {*_EMPTY_CELLS, *missing}
    cells = [None if cell in absent else cell for cell in _column(table, name)]
    return np.asarray(cells, dtype=object)


def number_column(table: pd.DataFrame, name: str) -> np.ndarray:
    """A numeric column; an empty cell is `NaN`, anything else must be a number."""
    out = np.full(table.shape[0], np.nan, dtype=np.float64)
    for k, cell in enumerate(_column(table, name)):
        if cell in _EMPTY_CELLS:
            continue
        try:
            out[k] = float(cell)
        except ValueError as exc:
            raise Refusal(f"column {name!r}, row {k + 1}: {cell!r} is not a number") from exc
    return out


def read_geojson(path: Path, properties: Sequence[str]) -> tuple[list[Any], dict[str, list[Any]]]:
    """Geometries and the named properties of a GeoJSON feature collection.

    Read with the `json` module and shapely. Features with no geometry or an
    empty one are left out. A property that is missing or `null` is `None`;
    any other value is turned into text, so `3` in the file and `"3"` in the
    plot table are the same label. A named property that no feature has is
    refused.
    """
    with path.open(encoding="utf-8") as handle:
        document = json.load(handle)
    if document.get("type") == "FeatureCollection":
        features = document.get("features", [])
    elif document.get("type") == "Feature":
        features = [document]
    else:
        raise Refusal(f"{path}: expected a GeoJSON FeatureCollection")
    geometries: list[Any] = []
    values: dict[str, list[Any]] = {name: [] for name in properties}
    for feature in features:
        if feature.get("geometry") is None:
            continue
        geometry = shape(feature["geometry"])
        if geometry.is_empty:
            continue
        geometries.append(geometry)
        props = feature.get("properties") or {}
        for name in properties:
            raw = props.get(name)
            values[name].append(None if raw is None else str(raw).strip())
    if not geometries:
        raise Refusal(f"{path}: no feature with a geometry")
    for name in properties:
        if all(v is None for v in values[name]):
            raise Refusal(f"{path}: no feature has the property {name!r}")
    bounds = shapely.total_bounds(np.asarray(geometries, dtype=object))
    if looks_like_degrees(np.array([[bounds[0], bounds[1]], [bounds[2], bounds[3]]])):
        raise Refusal(
            f"{path}: the coordinates look like degrees. Distances and areas are worked out "
            "in metres: give every file in one projected coordinate system."
        )
    return geometries, values


def codes_from(labels: np.ndarray, classes: np.ndarray, what: str) -> np.ndarray:
    """Codes of `labels` in an existing list of classes (`-1` for missing)."""
    position = {str(c): k for k, c in enumerate(classes.tolist())}
    out = np.full(labels.shape[0], -1, dtype=np.int64)
    for k, label in enumerate(labels.tolist()):
        if label is None:
            continue
        if label not in position:
            raise Refusal(f"{what}: the label {label!r} is in the plot table but not in the map")
        out[k] = position[label]
    return out


def same_partition(a: np.ndarray, b: np.ndarray) -> bool:
    """True if two codings put the same plots together and leave the same plots out."""
    if not np.array_equal(a < 0, b < 0):
        return False
    on = a >= 0
    if not on.any():
        return True
    both = np.unique(np.stack([a[on], b[on]]), axis=1).shape[1]
    return bool(both == np.unique(a[on]).shape[0] == np.unique(b[on]).shape[0])


# ---------------------------------------------------------------------------
# The site, as arrays
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class Site:
    """Everything the statistics need, in one fixed plot order."""

    n: int
    stand_id: np.ndarray
    stand_type: np.ndarray | None
    coords: np.ndarray | None
    attributes: np.ndarray | None
    field_type: np.ndarray | None
    groups: np.ndarray | None
    super_group: np.ndarray | None
    group_labels: list[str]
    super_group_labels: list[str]
    stand_map: spatial_null.PolygonStandMap | None
    stand_geometries: list[Any] | None
    regions: Any
    label_check: dict[str, Any]


def build_site(args: argparse.Namespace) -> Site:
    table = read_table(args.plots)
    n = int(table.shape[0])
    if n < 2:
        raise Refusal("the plot table needs at least two plots")
    missing = tuple(args.missing_label)

    groups = group_labels = None
    if args.group_col:
        groups, classes = encode_labels(label_column(table, args.group_col, missing))
        group_labels = [str(c) for c in classes.tolist()]
    super_group = super_labels = None
    if args.super_group_col:
        super_group, classes = encode_labels(label_column(table, args.super_group_col, missing))
        super_labels = [str(c) for c in classes.tolist()]
    if groups is not None and super_group is not None:
        both = (groups >= 0) & (super_group >= 0)
        pairs_seen = np.unique(np.stack([groups[both], super_group[both]]), axis=1)
        if pairs_seen.shape[1] != np.unique(groups[both]).shape[0]:
            raise Refusal(
                f"a group ({args.group_col}) has plots in more than one super-group "
                f"({args.super_group_col}); each group must lie in one"
            )

    coords = None
    if args.x_col or args.y_col:
        if not (args.x_col and args.y_col):
            raise Refusal("give both --x-col and --y-col, or neither")
        coords = np.column_stack(
            [number_column(table, args.x_col), number_column(table, args.y_col)]
        )
        if not np.isfinite(coords).all():
            raise Refusal("a plot has no coordinates; every plot needs x and y")
        if looks_like_degrees(coords):
            raise Refusal(
                "the plot coordinates look like degrees. Distances are worked out in metres: "
                "give x and y in a projected coordinate system, the same as the polygons."
            )

    attributes = None
    if args.attribute_cols:
        attributes = np.column_stack([number_column(table, c) for c in args.attribute_cols])
    field_type = None
    if args.field_type_col:
        field_type = encode_labels(label_column(table, args.field_type_col, missing))[0]

    # --- the map's labels of the plots -------------------------------------
    csv_id = csv_type_labels = None
    if args.stand_id_col:
        raw = label_column(table, args.stand_id_col, missing)
        if args.stand_id_scope is None:
            raise Refusal(
                "--stand-id-col needs --stand-id-scope: say whether a stand id is unique over "
                "the whole table (global), or restarts in each group or each super-group"
            )
        if args.stand_id_scope == "global":
            csv_id = encode_labels(raw)[0]
        else:
            flag, col = (
                ("--group-col", args.group_col)
                if args.stand_id_scope == "group"
                else ("--super-group-col", args.super_group_col)
            )
            if not col:
                raise Refusal(f"--stand-id-scope {args.stand_id_scope} needs {flag}")
            csv_id = combine_labels(label_column(table, col, missing), raw)
    if args.stand_type_col:
        csv_type_labels = label_column(table, args.stand_type_col, missing)

    stand_map = None
    stand_geometries = None
    label_check: dict[str, Any] = {"labels_from": "plot table"}
    if args.stand_polygons:
        wanted = [p for p in (args.stand_polygons_type_property,) if p]
        stand_geometries, props = read_geojson(args.stand_polygons, wanted)
        type_codes = type_classes = None
        if args.stand_polygons_type_property:
            type_codes, type_classes = encode_labels(
                np.asarray(props[args.stand_polygons_type_property], dtype=object)
            )
        stand_map = spatial_null.PolygonStandMap(stand_geometries, type_codes)

    if stand_map is not None and coords is not None:
        # The labels the tests use are read from the map, by the same lookup
        # as the relabellings. The plot table's labels are checked against them.
        map_id = stand_map.lookup(coords)
        map_type = None
        if stand_map.stand_type is not None:
            map_type = np.where(map_id >= 0, stand_map.stand_type[np.maximum(map_id, 0)], -1)
        label_check = {
            "labels_from": "stand polygons",
            "n_plots_on_a_stand_in_the_map": int((map_id >= 0).sum()),
        }
        problems: list[str] = []
        if csv_id is not None:
            agree = same_partition(csv_id, map_id)
            label_check["n_plots_on_a_stand_in_the_table"] = int((csv_id >= 0).sum())
            label_check["n_plots_on_a_stand_in_one_but_not_the_other"] = int(
                ((csv_id >= 0) != (map_id >= 0)).sum()
            )
            label_check["stand_ids_agree"] = agree
            if not agree:
                problems.append("the stand ids of the plot table and the stand polygons differ")
        if csv_type_labels is not None and map_type is not None and type_classes is not None:
            csv_type = codes_from(csv_type_labels, type_classes, "stand types")
            n_diff = int((csv_type != map_type).sum())
            label_check["n_plots_whose_type_differs"] = n_diff
            if n_diff:
                problems.append(f"{n_diff} plot(s) have a different stand type in table and map")
        if problems and args.on_label_mismatch == "refuse":
            raise Refusal(
                "; ".join(problems) + f". Details: {label_check}. A test on labels that are "
                "not the map's labels tests something else. Fix the join, or pass "
                "--on-label-mismatch use-map to take the labels from the polygons (recorded)."
            )
        stand_id, stand_type = map_id, map_type
        if stand_type is None and csv_type_labels is not None:
            stand_type = encode_labels(csv_type_labels)[0]
            label_check["stand_types_from"] = "plot table (the polygons carry no type)"
    else:
        if csv_id is None:
            raise Refusal(
                "no stand labels: give --stand-id-col, or --stand-polygons with --x-col/--y-col"
            )
        stand_id = csv_id
        stand_type = None if csv_type_labels is None else encode_labels(csv_type_labels)[0]

    if stand_type is not None:
        stand_type = np.where(stand_id >= 0, stand_type, -1)
        try:
            check_one_type_per_stand(stand_id, stand_type)
        except ValueError as exc:
            raise Refusal(str(exc)) from exc

    regions: Any = None
    if args.regions:
        wanted = [args.regions_group_property] if args.regions_group_property else []
        geoms, props = read_geojson(args.regions, wanted)
        if groups is None:
            regions = shapely.union_all(np.asarray(geoms, dtype=object))
        else:
            if not args.regions_group_property:
                raise Refusal("--regions with --group-col needs --regions-group-property")
            by_label: dict[str, list[Any]] = {}
            for geom, label in zip(geoms, props[args.regions_group_property], strict=True):
                if label is not None:
                    by_label.setdefault(label, []).append(geom)
            regions = {}
            assert group_labels is not None
            for code, label in enumerate(group_labels):
                if label not in by_label:
                    raise Refusal(f"--regions has no polygon for the group {label!r}")
                regions[code] = shapely.union_all(np.asarray(by_label[label], dtype=object))

    return Site(
        n=n,
        stand_id=np.asarray(stand_id, dtype=np.int64),
        stand_type=None if stand_type is None else np.asarray(stand_type, dtype=np.int64),
        coords=coords,
        attributes=attributes,
        field_type=field_type,
        groups=groups,
        super_group=super_group,
        group_labels=group_labels or [],
        super_group_labels=super_labels or [],
        stand_map=stand_map,
        stand_geometries=stand_geometries,
        regions=regions,
        label_check=label_check,
    )


# ---------------------------------------------------------------------------
# Statistics, their descriptive tables, and the null
# ---------------------------------------------------------------------------


def _need(value: Any, statistic: str, flag: str) -> Any:
    if value is None:
        raise Refusal(f"the statistic {statistic} needs {flag}")
    return value


def _strata(site: Site, by_type: bool) -> np.ndarray | None:
    """Strata of ANOSIM and PERMANOVA: the group; plots without measurements left out.

    Without groups, type comparisons are still kept inside one super-group.
    """
    assert site.attributes is not None
    base = site.groups
    if base is None and by_type:
        base = site.super_group
    measured = ~np.isnan(site.attributes).any(axis=1)
    if base is None:
        return None if measured.all() else np.where(measured, 0, -1)
    return np.where(measured, base, -1)


def build_statistics(
    names: Sequence[str], site: Site, args: argparse.Namespace
) -> tuple[list[Statistic], dict[str, Any]]:
    """The requested statistics, and the descriptive tables that go with each."""
    stats: list[Statistic] = []
    describe: dict[str, Any] = {}
    sid, typ = site.stand_id, site.stand_type
    field = geo = comparison = None
    if any(not s.startswith("ari_") for s in names):
        attributes = _need(site.attributes, "(any but the Rand indices)", "--attribute-cols")
        field = pairs.field_distance(attributes)
    if any(s.startswith(("pair_", "partial_mantel_")) for s in names):
        coords = _need(site.coords, "(pair comparison, partial Mantel)", "--x-col and --y-col")
        geo = pairs.geographic_distance(coords)
    if any(s.startswith("pair_") for s in names):
        if not args.band_edges:
            raise Refusal(
                "the pair comparison needs --band-edges: the distance bands have no default "
                "and must be the ones written in the predeclaration"
            )
        comparison = pairs.PairComparison(
            field, site.coords, args.band_edges, groups=site.groups, super_group=site.super_group
        )
        table = comparison.table(sid, typ)
        describe["pair_comparison"] = {
            "band_edges": list(args.band_edges),
            "pooled": table.pooled,
            "crude_without_strata": table.crude,
            "n_pairs_used": table.n_pairs_used,
            "n_strata_used": table.n_strata_used,
            "by_band": table.by_band,
            "by_group": table.by_group,
            "strata": table.strata,
        }

    for name in names:
        if name in TYPE_STATISTICS and typ is None:
            raise Refusal(f"the statistic {name} needs stand types (--stand-type-col)")
        if name == "ari_drawing":
            field_type = _need(site.field_type, name, "--field-type-col")
            stats.append(agreement.drawing_statistic(field_type))
            result = agreement.agreement(field_type, sid)
            # Over the plots the index scores, those with a stand and a field type
            # (review C24: these counts included plots with no field type).
            scored = (sid >= 0) & (np.asarray(field_type) >= 0)
            per_stand = np.bincount(sid[scored]) if scored.any() else np.zeros(0, int)
            describe[name] = {
                "rand": result.rand,
                "adjusted_rand": result.adjusted_rand,
                "adjusted_rand_ceiling": result.adjusted_rand_max,
                "pair_counts": result.counts,
                "same_stand_pairs": result.counts.both + result.counts.b_only,
                "stands_with_a_plot": int((per_stand >= 1).sum()),
                "stands_with_two_or_more_plots": int((per_stand >= 2).sum()),
                "n_field_types": result.n_groups_a,
            }
        elif name == "ari_labelling":
            field_type = _need(site.field_type, name, "--field-type-col")
            stats.append(agreement.labelling_statistic(field_type, site.super_group))
            strata = site.super_group if site.super_group is not None else np.zeros(site.n, int)
            pooled = agreement.stratified_agreement(field_type, typ, strata)
            describe[name] = {
                "pooled_over": "super-groups, by pair counts",
                "rand": pooled.rand,
                "adjusted_rand": pooled.adjusted_rand,
                "per_super_group": pooled.per_stratum,
            }
        elif name in ("pair_stand", "pair_type"):
            assert comparison is not None
            stats.append(comparison.statistic("stand" if name == "pair_stand" else "type"))
        elif name.startswith(("mantel_", "partial_mantel_")):
            kind = "stand" if name.endswith("_stand") else "type"
            stats.append(
                permutation.mantel_statistic(
                    field,
                    kind=kind,  # type: ignore[arg-type]
                    groups=site.groups,
                    super_group=site.super_group if kind == "type" else None,
                    geo_dist=geo if name.startswith("partial_") else None,
                    method=args.mantel_method,
                )
            )
            describe[name] = {
                "method": args.mantel_method,
                "pairs": "inside one group" if site.groups is not None else "all pairs",
            }
        elif name.startswith(("anosim_", "permanova_")):
            by = "stand" if name.endswith("_stand") else "type"
            strata = _strata(site, by == "type")
            grouping = sid if by == "stand" else typ
            if name.startswith("anosim_"):
                stats.append(
                    permutation.anosim_statistic(
                        field,
                        by=by,  # type: ignore[arg-type]
                        strata=strata,
                        stratum_weights=args.anosim_weights,
                    )
                )
                declared = permutation.anosim(
                    field, grouping, strata=strata, stratum_weights=args.anosim_weights
                )
                other = "equal" if args.anosim_weights == "pairs" else "pairs"
                beside = permutation.anosim(field, grouping, strata=strata, stratum_weights=other)
                describe[name] = {
                    "stratum_weights": args.anosim_weights,
                    "r": declared.r,
                    f"r_with_{other}_weights_for_comparison": beside.r,
                    "n_plots": declared.n,
                    "n_cells": declared.n_groups,
                    "per_stratum": declared.per_stratum,
                }
            else:
                stats.append(
                    permutation.permanova_statistic(field, by=by, strata=strata)  # type: ignore[arg-type]
                )
                describe[name] = permutation.permanova(field, grouping, strata=strata)
        else:  # argparse restricts the names, so this is a guard only
            raise Refusal(f"unknown statistic {name!r}")
    built = [s.name for s in stats]
    if built != list(names):
        raise RuntimeError(f"statistic names differ from the request: {built} against {names}")
    return stats, describe


def draw_null(site: Site, args: argparse.Namespace) -> permutation.NullDraws:
    """Relabellings of the plots from the one declared null model."""
    n_draws, seed = args.n_permutations, args.seed
    if args.null == "free_permutation":
        return permutation.free_permutation(site.stand_id, site.stand_type, n_draws, seed)
    if args.null == "within_group_permutation":
        if site.groups is None:
            raise Refusal("--null within_group_permutation needs --group-col")
        return permutation.within_group_permutation(
            site.stand_id, site.stand_type, site.groups, n_draws, seed
        )
    if site.stand_map is None or site.regions is None or site.coords is None:
        raise Refusal(
            "--null rotation needs --stand-polygons, --regions and the plot coordinates: it "
            "moves each group's plots over the map"
        )
    groups = site.groups if site.groups is not None else np.zeros(site.n, dtype=np.int64)
    try:
        draws = spatial_null.rotation_null(
            site.coords,
            groups,
            site.stand_map,
            site.regions,
            n_draws,
            seed,
            require_type=args.require_type,
        )
    except spatial_null.NullNotEstimable as exc:
        raise Refusal(f"the rotation null could not be drawn: {exc}") from exc
    types = draws.types if site.stand_map.stand_type is not None else None
    observed_type = draws.observed_type if types is not None else None
    if types is None and any(s in TYPE_STATISTICS for s in args.statistics):
        raise Refusal(
            "under the rotation null the stand types must come from the map: give "
            "--stand-polygons-type-property (a plot moved onto another stand needs its type)"
        )
    if not np.array_equal(draws.observed_id, site.stand_id):
        raise RuntimeError("the null does not start from the labels the statistics are read on")
    return permutation.NullDraws(
        name=draws.name,
        observed_id=draws.observed_id,
        observed_type=observed_type,
        ids=draws.ids,
        types=types,
        info=draws.info,
    )


def reference_measures(site_stands: list[Any], args: argparse.Namespace) -> dict[str, Any]:
    """Over- and under-segmentation, and the boundary match if a tolerance is declared."""
    references, _ = read_geojson(args.reference_polygons, [])
    accuracy = segacc.segmentation_accuracy(
        site_stands, references, min_overlap_fraction=args.min_overlap_fraction
    )
    out: dict[str, Any] = {
        "min_overlap_fraction": args.min_overlap_fraction,
        "summary": accuracy.summary,
        "per_reference": accuracy.per_reference,
    }
    if args.boundary_tolerance is not None:
        ignore = None
        if args.boundary_ignore:
            geoms, _ = read_geojson(args.boundary_ignore, [])
            ignore = shapely.union_all(np.asarray(geoms, dtype=object))
        out["boundary_match"] = segacc.boundary_match(
            site_stands, references, args.boundary_tolerance, ignore=ignore
        )
        out["boundary_ignore_given"] = ignore is not None
    return out


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def _band_edge(text: str) -> float:
    return math.inf if text.strip().lower() in ("inf", "infinity") else float(text)


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(__doc__ or "").split("\n\n")[0],
        epilog="See the top of this file and docs/evaluation_metrics.md.",
    )
    add = parser.add_argument
    add("--predeclared", type=Path, help="the written predeclaration of this analysis (required)")
    add("--out-dir", type=Path, help="folder for the results file and the manifest (required)")
    add("--overwrite", action="store_true", help="replace an existing results file")

    add("--plots", type=Path, help="plot table, CSV, one row per plot")
    add("--stand-id-col", help="column: the stand each plot is in")
    add(
        "--stand-id-scope",
        choices=("global", "group", "super-group"),
        help="whether a stand id is unique in the whole table or restarts in each "
        "group or super-group (no default)",
    )
    add("--stand-type-col", help="column: the type of the plot's stand")
    add("--x-col", help="column: x in metres, projected")
    add("--y-col", help="column: y in metres, projected")
    add("--attribute-cols", nargs="+", default=[], help="columns: the field measurements")
    add("--field-type-col", help="column: the category the field data give the plot")
    add("--group-col", help="column: the unit plots were laid out in (village forest)")
    add("--super-group-col", help="column: the unit stand types were fitted in (district)")
    add(
        "--missing-label",
        nargs="*",
        default=[],
        help="cell values that mean 'no label', besides an empty cell (for example -1)",
    )

    add("--stand-polygons", type=Path, help="stand map, GeoJSON, projected metres")
    add("--stand-polygons-type-property", help="property of a stand polygon: its type")
    add(
        "--on-label-mismatch",
        choices=("refuse", "use-map"),
        default="refuse",
        help="what to do if the table's stand labels differ from the polygons' (default: refuse)",
    )
    add("--regions", type=Path, help="GeoJSON: where each group's plots may be moved")
    add("--regions-group-property", help="property of a region polygon: its group")
    add("--reference-polygons", type=Path, help="GeoJSON of reference polygons")
    add("--boundary-tolerance", type=float, help="metres; the boundary match is run if given")
    add("--boundary-ignore", type=Path, help="GeoJSON left out of the boundary match")
    add("--min-overlap-fraction", type=float, default=0.0, help="sliver rule; default 0")

    add("--statistics", nargs="+", default=[], choices=STATISTICS, metavar="NAME")
    add("--null", choices=NULLS, help="the one null model (no default)")
    add("--band-edges", nargs="+", type=_band_edge, default=[], help="metres; last may be inf")
    add("--n-permutations", type=int, help="relabellings per test (no default)")
    add("--seed", type=int, help="seed of the relabellings (no default)")
    add("--mantel-method", choices=("pearson", "spearman"), default="pearson")
    add("--anosim-weights", choices=("pairs", "equal"), default="pairs")
    add(
        "--require-type",
        action="store_true",
        help="rotation null: a plot on a typed stand must land on a typed stand",
    )
    return parser


def check_request(args: argparse.Namespace) -> tuple[str, str]:
    """Refuse a request that may not be run. Returns the predeclaration's text and sha256."""
    if args.predeclared is None:
        raise Refusal(
            "no --predeclared file. Analyses are declared before they are run: write down the "
            "statistics, the null model, the distance bands, the number of relabellings and "
            "what will count as support, commit that file, and pass its path. See "
            "docs/evaluation_metrics.md, 'Before running on real data'."
        )
    if not args.predeclared.is_file():
        raise Refusal(f"the predeclaration {args.predeclared} is not a file")
    text = args.predeclared.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        raise Refusal(f"the predeclaration {args.predeclared} is empty")
    if args.out_dir is None:
        raise Refusal("--out-dir is required")
    if (args.out_dir / RESULTS_NAME).exists() and not args.overwrite:
        raise Refusal(
            f"{args.out_dir / RESULTS_NAME} exists. A result is never overwritten silently: "
            "choose another --out-dir, or compare first and then pass --overwrite."
        )
    if args.statistics:
        if len(set(args.statistics)) != len(args.statistics):
            raise Refusal("--statistics names a statistic twice")
        if args.plots is None:
            raise Refusal("--statistics needs --plots")
        missing = [
            flag
            for flag, value in (
                ("--null", args.null),
                ("--n-permutations", args.n_permutations),
                ("--seed", args.seed),
            )
            if value is None
        ]
        if missing:
            raise Refusal(
                f"{', '.join(missing)} must be given: they have no default, because they are "
                "part of the declared analysis"
            )
        if args.n_permutations < 1:
            raise Refusal("--n-permutations must be at least 1")
        if args.seed < 0:
            raise Refusal("--seed must not be negative")
    elif args.reference_polygons is None:
        raise Refusal("nothing to do: give --statistics, or --reference-polygons")
    if args.reference_polygons is not None and args.stand_polygons is None:
        raise Refusal("--reference-polygons needs --stand-polygons")
    for flag in ("plots", "stand_polygons", "regions", "reference_polygons", "boundary_ignore"):
        path = getattr(args, flag)
        if path is not None and not path.is_file():
            raise Refusal(f"--{flag.replace('_', '-')} {path} is not a file")
    return text, sha256_file(args.predeclared)


def run(args: argparse.Namespace, argv: Sequence[str]) -> tuple[Path, Path]:
    text, declared_sha = check_request(args)
    not_named = [
        name
        for name in [*args.statistics, *([args.null] if args.statistics else [])]
        if name not in text
    ]
    if not_named:
        print(
            "warning: the predeclaration does not contain the name(s) "
            f"{not_named}; this is recorded in the manifest",
            file=sys.stderr,
        )

    results: dict[str, Any] = {
        "about": (
            "Results of scripts/run_evaluation.py. Results only: no run times, no dates, no "
            "paths. The manifest beside this file says what was run. null means not estimable. "
            f"Numbers are written with {SIGNIFICANT_DIGITS} significant digits."
        ),
        "predeclared_sha256": declared_sha,
    }
    stand_geometries: list[Any] | None = None
    if args.statistics:
        try:
            site = build_site(args)
            stats, describe = build_statistics(args.statistics, site, args)
            draws = draw_null(site, args)
        except ValueError as exc:  # malformed input, reported by the package
            raise Refusal(f"the input was not accepted: {exc}") from exc
        stand_geometries = site.stand_geometries
        tests = permutation.run_tests(stats, draws)
        in_stand = site.stand_id >= 0
        results["inputs"] = {
            "n_plots": site.n,
            "n_plots_in_a_stand": int(in_stand.sum()),
            "n_stands_with_a_plot": int(np.unique(site.stand_id[in_stand]).shape[0]),
            "n_groups": len(site.group_labels),
            "n_super_groups": len(site.super_group_labels),
            "group_labels_by_code": site.group_labels,
            "super_group_labels_by_code": site.super_group_labels,
            "plots_per_group": (
                np.bincount(site.groups[site.groups >= 0], minlength=len(site.group_labels))
                if site.groups is not None
                else []
            ),
            "attribute_columns": list(args.attribute_cols),
            "n_plots_with_a_missing_measurement": (
                int(np.isnan(site.attributes).any(axis=1).sum())
                if site.attributes is not None
                else None
            ),
            "has_stand_types": site.stand_type is not None,
        }
        results["label_check"] = site.label_check
        results["null"] = {
            "name": draws.name,
            "n_permutations": args.n_permutations,
            "seed": args.seed,
            "how_drawn": draws.info,
            "is_a_metric": False,
            "caution": None if draws.name == "rotation" else PERMUTATION_CAUTION,
        }
        results["tests"] = {
            "p_value": "(b + 1) / (R + 1), one-sided: larger means the map agrees better",
            "p_holm": "Holm's correction over the rows of this table",
            "rows": tests,
        }
        results["descriptive"] = describe
    if args.reference_polygons is not None:
        if stand_geometries is None:
            stand_geometries, _ = read_geojson(args.stand_polygons, [])
        try:
            results["reference_polygons"] = reference_measures(stand_geometries, args)
        except ValueError as exc:
            raise Refusal(f"the polygons were not accepted: {exc}") from exc

    args.out_dir.mkdir(parents=True, exist_ok=True)
    results_path = args.out_dir / RESULTS_NAME
    manifest_path = args.out_dir / MANIFEST_NAME
    write_json(results_path, results)

    inputs = {
        flag: {"path": str(getattr(args, flag)), "sha256": sha256_file(getattr(args, flag))}
        for flag in ("plots", "stand_polygons", "regions", "reference_polygons", "boundary_ignore")
        if getattr(args, flag) is not None
    }
    manifest = {
        "script": "scripts/run_evaluation.py",
        "script_sha256": sha256_file(Path(__file__).resolve()),
        "git": git_state(),
        "predeclared": {
            "path": str(args.predeclared),
            "sha256": declared_sha,
            "git_status": predeclaration_git_status(args.predeclared),
            "names_not_found_in_it": not_named,
        },
        "command_line": list(argv),
        "arguments": {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items()},
        "inputs": inputs,
        "outputs": {RESULTS_NAME: {"sha256": sha256_file(results_path)}},
        "versions": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "shapely": shapely.__version__,
        },
    }
    write_json(manifest_path, manifest)
    return results_path, manifest_path


def main(argv: Sequence[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    args = make_parser().parse_args(argv)
    try:
        results_path, manifest_path = run(args, argv)
    except Refusal as refusal:
        print(f"refused: {refusal}", file=sys.stderr)
        return 2
    print(f"wrote {results_path} and {manifest_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

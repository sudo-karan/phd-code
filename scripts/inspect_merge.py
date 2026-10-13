"""Run the pipeline through the merge stage and print what the merge did.

Prints the stage's summary numbers, where the configured tolerances fall among
this area's neighbour differences, the distribution of stand sizes, a table of
every stand's provenance (how many superpixels it is made of, how many merges of
each kind, whether and why it ended below the minimum size), the stands left
below the minimum size, and where to look first. The table is also written to
the run directory as `merge_provenance.csv` and `merge_provenance.json`.

READ-ONLY BY DEFAULT, unlike the older inspect scripts: it runs
`Pipeline(..., use_cache=True, submit_exports=False)`, which reads cached
assets, computes anything missing live, and submits no Earth Engine task and
writes no asset. Pass `--submit-exports` for the older behaviour (export tasks
for upstream outputs that are not cached yet). Never do that while tasks from
an earlier run are still queued: it submits a second copy of each.

Run from the repo root (the pipeline reads `.env` from the working directory):

    python scripts/inspect_merge.py --config configs/sanjay_van_baseline.yaml
    python scripts/inspect_merge.py --config <config> --sort area --rows 50
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from fmu.config import load_config
from fmu.pipeline import Pipeline, default_stage_names
from fmu.stages.base import PipelineContext
from fmu.stages.data_load import DataLoadStage  # noqa: F401
from fmu.stages.features_embedding import FeaturesEmbeddingStage  # noqa: F401
from fmu.stages.features_optical import FeaturesOpticalStage  # noqa: F401
from fmu.stages.features_radar import FeaturesRadarStage  # noqa: F401
from fmu.stages.features_static import FeaturesStaticStage  # noqa: F401
from fmu.stages.features_structure import FeaturesStructureStage  # noqa: F401
from fmu.stages.masking import MaskingStage  # noqa: F401
from fmu.stages.merge import (
    _MERGE_KIND_LEGEND,
    MergeStage,
    merge_kind_code,
    summarise_merge_diagnostics,
)
from fmu.stages.segmentation import SegmentationStage  # noqa: F401
from fmu.utils.caching import config_fingerprint
from fmu.utils.gee import init_gee, load_roi_geometry
from fmu.utils.logging import init_logging
from fmu.utils.region_merge import PROVENANCE_FIELDS

# Columns of the per-stand table, in order. `stand_lbl` is the merge's own stand
# id: the pixel value of `stand_clusters` and the `stand_lbl` property of the
# exported stands_merged layer, so the table joins to both.
TABLE_COLUMNS: tuple[str, ...] = (
    "stand_lbl",
    "area_ha",
    "n_pixels",
    *PROVENANCE_FIELDS,
    "merge_kind",
)

SORT_CHOICES = ("fallback", "area", "id")


# ---------------------------------------------------------------------
# Pure helpers (tested in tests/test_inspect_merge.py)
# ---------------------------------------------------------------------


def provenance_rows(
    stand_attributes: dict[int, dict[str, Any]],
    stand_provenance: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    """One row per stand, in stand-id order, with the columns in TABLE_COLUMNS."""
    if set(stand_attributes) != set(stand_provenance):
        raise ValueError(
            "stand_attributes and stand_provenance do not describe the same "
            f"stands: {len(stand_attributes)} against {len(stand_provenance)} ids."
        )
    rows = []
    for sid in sorted(stand_attributes):
        attrs, prov = stand_attributes[sid], stand_provenance[sid]
        rows.append(
            {
                "stand_lbl": sid,
                "area_ha": attrs["area_ha"],
                "n_pixels": attrs["n_pixels"],
                **{name: prov[name] for name in PROVENANCE_FIELDS},
                "merge_kind": merge_kind_code(prov),
            }
        )
    return rows


def sort_rows(rows: list[dict[str, Any]], by: str) -> list[dict[str, Any]]:
    """Order the table. Ties always fall back to the stand id, so the order is
    the same on every run.

    "fallback": most shared-edge fallback merges first, then largest area.
    "area":     largest first.
    "id":       by stand id.
    """
    if by == "fallback":
        return sorted(
            rows, key=lambda r: (-r["n_fallback"], -r["area_ha"], r["stand_lbl"])
        )
    if by == "area":
        return sorted(rows, key=lambda r: (-r["area_ha"], r["stand_lbl"]))
    if by == "id":
        return sorted(rows, key=lambda r: r["stand_lbl"])
    raise ValueError(f"sort must be one of {SORT_CHOICES}, got {by!r}")


def size_distribution(
    areas_ha: list[float], min_area_ha: float, max_area_ha: float
) -> dict[str, Any]:
    """Quantiles of stand area and how the stands sit against the two bounds.

    Quantiles are the value at position int(q * n) of the sorted areas, the
    same rule `calibrate_thresholds` uses.
    """
    vals = sorted(areas_ha)
    if not vals:
        return {"n_stands": 0}

    def q(p: float) -> float:
        return vals[min(len(vals) - 1, int(p * len(vals)))]

    total = sum(vals)
    return {
        "n_stands": len(vals),
        "total_ha": round(total, 4),
        "mean_ha": round(total / len(vals), 4),
        "min_ha": vals[0],
        "p10_ha": q(0.10),
        "p25_ha": q(0.25),
        "median_ha": q(0.50),
        "p75_ha": q(0.75),
        "p90_ha": q(0.90),
        "max_ha": vals[-1],
        "n_below_min_area": sum(1 for v in vals if v < min_area_ha),
        "n_within_bounds": sum(1 for v in vals if min_area_ha <= v <= max_area_ha),
        "n_above_max_area": sum(1 for v in vals if v > max_area_ha),
    }


def by_merge_kind(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Stands and area under each `merge_kind` code, in legend order."""
    total_ha = sum(r["area_ha"] for r in rows)
    out = []
    for entry in _MERGE_KIND_LEGEND:
        mine = [r for r in rows if r["merge_kind"] == entry.value]
        area = sum(r["area_ha"] for r in mine)
        out.append(
            {
                "merge_kind": entry.value,
                "label": entry.label,
                "n_stands": len(mine),
                "area_ha": round(area, 4),
                "share_of_area": round(area / total_ha, 4) if total_ha else 0.0,
            }
        )
    return out


def format_table(rows: list[dict[str, Any]], limit: int | None = None) -> list[str]:
    """The table as fixed-width text lines. `limit` keeps the first rows only."""
    shown = rows if limit is None else rows[:limit]
    cells = [[str(r[c]) for c in TABLE_COLUMNS] for r in shown]
    widths = [
        max(len(c), *(len(row[i]) for row in cells)) if cells else len(c)
        for i, c in enumerate(TABLE_COLUMNS)
    ]
    lines = ["  ".join(c.rjust(w) for c, w in zip(TABLE_COLUMNS, widths, strict=True))]
    lines += ["  ".join(v.rjust(w) for v, w in zip(row, widths, strict=True)) for row in cells]
    if len(shown) < len(rows):
        lines.append(f"... {len(rows) - len(shown)} more stand(s); all are in the CSV")
    return lines


# What each cause of an undersized stand calls for. Same three causes as the
# stage's summary numbers.
_CAUSE_ADVICE = {
    "isolated": "touches no other stand, so nothing can be merged into it",
    "area_blocked": (
        "every neighbour is already too big to take it under merge.max_area_ha; "
        "this points at the area bounds, not at the forest"
    ),
    "iteration_cap": (
        "still had a neighbour it could have joined when the second pass "
        "stopped at merge.max_pass2_iterations"
    ),
}


def where_to_look_first(rows: list[dict[str, Any]], top: int = 5) -> list[str]:
    """Plain-language pointers, most weakly justified stands first."""
    if not rows:
        return ["No stands: the merge had nothing to work on."]
    lines = []
    total_ha = sum(r["area_ha"] for r in rows)
    with_fallback = [r for r in rows if r["n_fallback"]]
    if with_fallback:
        area = sum(r["area_ha"] for r in with_fallback)
        lines.append(
            f"{len(with_fallback)} of {len(rows)} stands "
            f"({100 * area / total_ha:.1f}% of the stand area) contain at least "
            f"one shared-edge fallback merge, which no merge criterion justified. "
            f"Their boundaries are the least well supported."
        )
        worst = sort_rows(with_fallback, "fallback")[:top]
        lines.append(
            "Most fallback merges: "
            + "; ".join(
                f"stand_lbl {r['stand_lbl']} ({r['n_fallback']} of "
                f"{r['n_superpx'] - 1} merges, {r['area_ha']:.2f} ha)"
                for r in worst
            )
            + "."
        )
    else:
        lines.append("No stand contains a shared-edge fallback merge.")
    below = [r for r in rows if r["below_min"]]
    if below:
        for cause, advice in _CAUSE_ADVICE.items():
            n = sum(1 for r in below if r["below_why"] == cause)
            if n:
                lines.append(f"{n} stand(s) below the minimum size, {cause}: {advice}.")
    else:
        lines.append("No stand is below the minimum size.")
    lines.append(
        "On a map: the display layer merge_provenance.merge_kind (declared in "
        "the manifest with its legend), or the exported stands_merged layer "
        "styled by n_fallback."
    )
    return lines


def write_table(
    rows: list[dict[str, Any]], run_dir: Path, header: dict[str, Any]
) -> tuple[Path, Path]:
    """Write the table as CSV and as JSON (with `header` on top) to `run_dir`.

    Results only, in stand-id order: no times or dates, so a re-run of the same
    config writes the same two files.
    """
    ordered = sort_rows(rows, "id")
    csv_path = run_dir / "merge_provenance.csv"
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(TABLE_COLUMNS))
        writer.writeheader()
        writer.writerows(ordered)
    json_path = run_dir / "merge_provenance.json"
    json_path.write_text(
        json.dumps({**header, "columns": list(TABLE_COLUMNS), "stands": ordered}, indent=1)
        + "\n"
    )
    return csv_path, json_path


# ---------------------------------------------------------------------
# The script
# ---------------------------------------------------------------------


def _heading(text: str) -> None:
    print()
    print("=" * 70)
    print(text)
    print("=" * 70)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--config",
        default="configs/sanjay_van_baseline.yaml",
        help="Path to the pipeline config YAML.",
    )
    parser.add_argument(
        "--sort",
        choices=SORT_CHOICES,
        default="fallback",
        help="Order of the printed table (the CSV and JSON are always by stand id).",
    )
    parser.add_argument(
        "--rows",
        type=int,
        default=25,
        help="How many stands to print; 0 prints all. The CSV always has all.",
    )
    parser.add_argument(
        "--submit-exports",
        action="store_true",
        help="Submit Earth Engine export tasks for upstream outputs that are "
        "not cached yet (the older inspect scripts' behaviour). Off by default: "
        "the run then submits nothing and writes no asset.",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    if not config.merge.enabled:
        raise SystemExit(f"{config.name}: merge.enabled is false, so there is no merge to inspect.")
    init_gee()

    ctx = PipelineContext()
    ctx.set("roi", load_roi_geometry(config.roi.roi_file))
    run_dir = init_logging(config_name=config.name)
    names = default_stage_names(config, through="clustering")
    names = names[: names.index("merge") + 1]
    result = Pipeline(
        stage_names=names, use_cache=True, submit_exports=args.submit_exports
    ).run(config=config, run_dir=run_dir, initial_context=ctx)
    ctx = result.context
    n_tasks = sum(len(s.export_tasks) for s in result.stages)

    diagnostics = ctx.get("merge_diagnostics")
    params = config.merge
    rows = provenance_rows(ctx.get("stand_attributes"), ctx.get("stand_provenance"))

    _heading(f"Merge: {config.name} (fingerprint {config_fingerprint(config)})")
    if args.submit_exports:
        print(
            f"MODE: --submit-exports. Pipeline(use_cache=True, submit_exports=True): "
            f"{n_tasks} Earth Engine export task(s) submitted for outputs that "
            f"were not cached."
        )
    else:
        print(
            "MODE: read-only. Pipeline(use_cache=True, submit_exports=False): "
            f"no Earth Engine task submitted ({n_tasks}), no asset written. "
            "Anything not cached was computed live for this run only."
        )
    print(f"Stages: {' -> '.join(names)}")
    print(
        f"Settings: min_area_ha {params.min_area_ha}, max_area_ha {params.max_area_ha}, "
        f"relax_factor {params.relax_factor}, min_defined_criteria "
        f"{params.min_defined_criteria}, max_pass2_iterations {params.max_pass2_iterations}, "
        f"pass2_skip_at_min_area {params.pass2_skip_at_min_area}"
    )

    _heading("Summary numbers")
    numbers = summarise_merge_diagnostics(diagnostics)
    for declared in MergeStage.summary_numbers:
        print(f"  {declared.name}: {numbers[declared.name]} {declared.unit}")
        print(f"      {declared.description}")

    _heading("Threshold calibration (a diagnostic, not a target)")
    calibration = diagnostics["threshold_calibration"]
    print(f"  adjacent superpixel pairs: {calibration['n_pairs']}")
    for band, row in calibration["per_band"].items():
        print(
            f"  {band}: tolerance {row['threshold']} admits "
            f"{row['percentile_of_threshold']}% of pair differences "
            f"(p25 {row['p25']}, p50 {row['p50']}, p75 {row['p75']}, p90 {row['p90']}; "
            f"defined on {row['n_pairs_defined']} pairs)"
        )
    print(
        f"  all criteria at once: {calibration['joint_admit_rate_pct']}% of "
        f"{calibration['n_pairs_with_any_defined_criterion']} pairs. The gate "
        f"needs every criterion, so this is none of the per-band figures."
    )

    _heading("Stand sizes")
    sizes = size_distribution(
        [r["area_ha"] for r in rows], params.min_area_ha, params.max_area_ha
    )
    for key, value in sizes.items():
        print(f"  {key}: {value}")
    print("  by how the stand was put together:")
    kinds = by_merge_kind(rows)
    for k in kinds:
        print(
            f"    {k['merge_kind']}  {k['n_stands']:>5} stands  {k['area_ha']:>10.2f} ha  "
            f"{100 * k['share_of_area']:5.1f}% of area  {k['label']}"
        )

    _heading(f"Per-stand provenance, sorted by {args.sort}")
    print(
        "  n_superpx superpixels in the stand; n_pass1 / n_relaxed / n_fallback "
        "merges of each kind\n  inside it; below_min 1 if it ended below the "
        "minimum size, below_why the cause;\n  merge_kind the display-layer code "
        "(0 single, 1 first pass only, 2 relaxed, 3 fallback)."
    )
    for line in format_table(sort_rows(rows, args.sort), args.rows or None):
        print("  " + line)

    _heading("Stands left below the minimum size")
    below = [r for r in sort_rows(rows, "area") if r["below_min"]]
    if below:
        for line in format_table(below):
            print("  " + line)
    else:
        print("  none")

    _heading("Where to look first")
    for line in where_to_look_first(rows):
        print("  - " + line)
    for warning in diagnostics.get("warnings", []):
        print("  - stage warning: " + warning)

    csv_path, json_path = write_table(
        rows,
        run_dir,
        {
            "config": config.name,
            "fingerprint": config_fingerprint(config),
            "summary_numbers": numbers,
            "stand_sizes": sizes,
            "by_merge_kind": kinds,
        },
    )
    print()
    print(f"Table (CSV):  {csv_path}")
    print(f"Table (JSON): {json_path}")
    print(f"Run dir:      {run_dir}")
    print(f"Manifest:     {run_dir / 'manifest.json'}")


if __name__ == "__main__":
    main()

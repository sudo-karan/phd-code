"""Does clustering.fit_excludes_stands_below_min_area leave out what it should? A read-only check.

    python scripts/check_fit_excludes_stands.py --config configs/<name>.yaml [--out <file.json>]

READ-ONLY on Earth Engine: it reads the config's cached assets and makes interactive requests.
It submits no task and writes no asset (scripts/ee_read_only.py makes any such call raise). Run
it from the repo root (fmu reads .env from there).

Why this exists. With the setting on (register entry
spec-clustering-fit-excludes-stands-below-min-area), the clustering stage leaves the stands the
merge left below merge.min_area_ha out of the k-means training rows. It does so with masks on
the integer stand-label image (remap) and two masked samples, not by filtering rows by label,
and checks only that the two samples add up, with a warning if they do not. That path has never
run on Earth Engine: its requests are checked offline only
(tests/test_clustering_fit_excludes_ee_graph.py). Jaskaran's answer to question 5 of
docs/handoff/2026-10-14-round3.md (15 Oct 2026) is a read-only check first, on a cached run.

What it does. `--config` names a config that has run with the setting off, with every stage up
to segmentation cached. The script reads those stages from the cache, runs the merge (it is
never cached, as in every run) and then the clustering stage in memory with the setting turned
on. It keeps what the stage's `_leave_out_of_fit` was given and returned, and asks Earth Engine,
in three requests of its own, for the stand labels of every training row, of the rows the fit
was trained on, and the types the run gave the stands left out. Then:

  1. rows_add_up: the fit's rows and the rows left out are the rows of every unit.
  2. fit_holds_no_stand_below_min: no row of the fit is of a stand below the minimum.
  3. left_out_are_the_stands_below_min_with_a_row: the rows left out are exactly those of the
     stands below the minimum that have a training row, and the stage counts as many.
  4. left_out_typed: every stand left out has a type, and one type: the trained clusterer,
     applied to every unit, types them too.
  5. summary_numbers_add_up: units_in_habitat = units_fitted + units_dropped_missing_band +
     units_left_out_of_fit, from the stage's own counts.
  6. stage_warnings: what the stage logged as a warning. Expected: none of the three warnings of
     the path with the setting on, which begin "k-means fit:" (no stand below the minimum had a
     row; the sample of them holds other units; the two samples do not add up). Others, such as
     units left out for missing band data, are recorded and do not count against it.

The cached superpixels are those of the config as it ran (the setting off, segmentation on the
whole area), which is all this needs: what is checked is how the clustering stage leaves stands
out, not which stands there are. `--out` writes the result, which holds results only, and
beside it `<name>_run.json` with the command, the date and the git commit it ran from.
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import shlex
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))  # this checkout's fmu, not an editable install of another
REQUEST_DEADLINE_MS = 7 * 60 * 1000  # as scripts/check_snic_on_kept_land.py
D3_WARNING = "k-means fit:"  # how each warning of _leave_out_of_fit begins


def run_record_path(out: Path) -> Path:
    return out.with_name(out.stem + "_run.json")


def compare_rows(all_rows: list[Any], fit_rows: list[Any], below_min: dict[int, float],
                 report: dict[str, Any]) -> dict[str, Any]:
    """Checks 1 to 3 from the stand labels of the rows. Pure Python."""
    every, fit = [int(float(v)) for v in all_rows], [int(float(v)) for v in fit_rows]
    below = set(below_min)
    left_out = sorted(set(every) - set(fit))
    with_a_row = sorted(set(every) & below)
    return {
        "rows": len(every),
        "distinct_units_in_rows": len(set(every)),
        "fit_rows": len(fit),
        "left_out_rows": len(left_out),
        "stands_below_min": len(below),
        "stands_below_min_with_a_row": len(with_a_row),
        "stage_counts_left_out": report.get("n_stands_left_out_of_fit"),
        "rows_add_up": len(fit) + len(left_out) == len(every) and len(set(every)) == len(every),
        "fit_holds_no_stand_below_min": not (set(fit) & below),
        "fit_rows_of_stands_below_min": sorted(set(fit) & below)[:20],
        "left_out_are_the_stands_below_min_with_a_row": (
            left_out == with_a_row and report.get("n_stands_left_out_of_fit") == len(with_a_row)),
        "left_out_not_below_min": sorted(set(left_out) - below)[:20],
        "fit_rows_not_in_every_row": sorted(set(fit) - set(every))[:20],
    }


def typed(groups: list[dict[str, Any]], left_out: list[int]) -> dict[str, Any]:
    """Check 4 from a histogram of types grouped by stand. Pure Python."""
    types = {int(float(g["unit"])): {k for k in g["histogram"] if k != "null"} for g in groups}
    untyped = sorted(s for s in left_out if not types.get(s))
    several = sorted(s for s in left_out if len(types.get(s, ())) > 1)
    return {"left_out": len(left_out), "untyped": untyped[:20], "n_untyped": len(untyped),
            "with_more_than_one_type": several[:20], "n_with_more_than_one_type": len(several),
            "left_out_typed": not untyped and not several}


def verdicts(result: dict[str, Any]) -> list[str]:
    """Plain lines for a result. Pure Python, so it is testable offline."""
    lines: list[str] = []
    if "error" in result:
        return [f"the check could not be run: {result['error']}",
                f"export tasks submitted: {result.get('export_tasks_submitted')}"]

    def says(ok: bool, yes: str, no: str) -> str:
        return ("as expected: " + yes) if ok else ("NOT as expected: " + no)

    r = result["rows"]
    if not r["stands_below_min_with_a_row"]:
        # With the setting on the stage always takes the path, so its lines would all hold with
        # nothing left out: say that this tested nothing (the final review of round 4).
        lines.append("NOT as expected: no stand below the minimum has a training row, so nothing "
                     "was left out of the fit and the lines below test nothing")
    lines.append(says(r["rows_add_up"],
                      f"the fit's {r['fit_rows']} rows and the {r['left_out_rows']} left out are "
                      f"the {r['rows']} rows of every unit",
                      f"{r['fit_rows']} rows in the fit and {r['left_out_rows']} left out against "
                      f"{r['rows']} rows of every unit ({r['distinct_units_in_rows']} distinct)"))
    lines.append(says(r["fit_holds_no_stand_below_min"],
                      "no row of the fit is of a stand below the minimum",
                      f"the fit holds rows of stands below the minimum: "
                      f"{r['fit_rows_of_stands_below_min']}"))
    lines.append(says(r["left_out_are_the_stands_below_min_with_a_row"],
                      f"the {r['left_out_rows']} rows left out are those of the stands below "
                      f"the minimum with a training row ({r['stands_below_min_with_a_row']} of "
                      f"{r['stands_below_min']}), as the stage counts",
                      f"left out {r['left_out_rows']}, stands below the minimum with a row "
                      f"{r['stands_below_min_with_a_row']}, the stage counts "
                      f"{r['stage_counts_left_out']}; left out but not below the minimum: "
                      f"{r['left_out_not_below_min']}"))
    t = result.get("types", {})
    if "error" in t:
        lines.append(f"the types of the stands left out could not be read: {t['error']}")
    elif t:
        lines.append(says(t["left_out_typed"],
                          f"each of the {t['left_out']} stands left out has one type",
                          f"of the {t['left_out']} stands left out, {t['n_untyped']} have no type "
                          f"and {t['n_with_more_than_one_type']} more than one"))
    n = result["summary_numbers"]
    total = n["units_fitted"] + n["units_dropped_missing_band"] + n["units_left_out_of_fit"]
    lines.append(says(total == n["units_in_habitat"],
                      f"units_in_habitat {n['units_in_habitat']} = units_fitted "
                      f"{n['units_fitted']} + units_dropped_missing_band "
                      f"{n['units_dropped_missing_band']} + units_left_out_of_fit "
                      f"{n['units_left_out_of_fit']}",
                      f"units_in_habitat {n['units_in_habitat']} against {total} fitted, dropped "
                      f"and left out"))
    w = [m for m in result.get("stage_warnings", []) if m.startswith(D3_WARNING)]
    lines.append(says(not w, "the clustering stage logged none of the warnings of the path with "
                      "the setting on",
                      f"the clustering stage logged {len(w)} warning(s) of the path with the "
                      "setting on: " + " | ".join(w)))
    lines.append(f"export tasks submitted: {result.get('export_tasks_submitted')}")
    return lines


def row_labels(ee: Any, get_info: Callable[..., Any], *, training_sample: Any, fit_sample: Any,
               label_band: str) -> dict[str, list[Any]]:
    """The stand label of every training row and of each row the fit was trained on."""
    got = get_info(
        ee.Dictionary({"every": training_sample.aggregate_array(label_band),
                       "fit": fit_sample.aggregate_array(label_band)}),
        context="stand labels of every training row and of the fit's rows",
    )
    return {"every": list(got.get("every") or []), "fit": list(got.get("fit") or [])}


def types_of(ee: Any, get_info: Callable[..., Any], *, cluster_labels: Any, unit_labels: Any,
             left_out: list[int], roi: Any, scale: int) -> list[dict[str, Any]]:
    """The types the run gave the stands left out, as a histogram per stand. The reduction
    takes `scale` as the stage's own counts of units do (clustering._count_units)."""
    if not left_out:
        return []
    mine = unit_labels.select([0]).remap(left_out, [1] * len(left_out), 0)
    got = get_info(
        cluster_labels.select([0]).rename("type")
        .addBands(unit_labels.select([0]).rename("unit"))
        .updateMask(mine)
        .reduceRegion(
            reducer=ee.Reducer.frequencyHistogram().unweighted().group(
                groupField=1, groupName="unit"),
            geometry=roi, scale=scale, maxPixels=int(1e10), tileScale=4),
        context="types of the stands left out",
    )
    return list(got.get("groups") or [])


class _Warnings(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(" ".join(record.getMessage().split()))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--config", type=Path, required=True,
                    help="a config that ran with the setting off, cached up to segmentation")
    ap.add_argument("--out", type=Path, default=None, help="write the result here as JSON")
    args = ap.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from check_snic_on_kept_land import check_fmu_is_this_checkouts

    check_fmu_is_this_checkouts()

    import ee

    import fmu.stages.clustering as clustering_module
    import fmu.stages.data_load  # noqa: F401  (importing registers the stages)
    import fmu.stages.features_embedding  # noqa: F401
    import fmu.stages.features_optical  # noqa: F401
    import fmu.stages.features_radar  # noqa: F401
    import fmu.stages.features_static  # noqa: F401
    import fmu.stages.features_structure  # noqa: F401
    import fmu.stages.masking  # noqa: F401
    import fmu.stages.merge  # noqa: F401
    import fmu.stages.segmentation  # noqa: F401
    from fmu.config import Config, load_config
    from fmu.pipeline import Pipeline, default_stage_names
    from fmu.stages.base import PipelineContext
    from fmu.utils.gee import LABEL_BAND, init_gee, load_roi_geometry, safe_get_info
    from fmu.utils.provenance import git_state

    cfg = load_config(args.config)
    if cfg.clustering.fit_excludes_stands_below_min_area:
        raise SystemExit(f"{cfg.name} already has the setting on; name a config that ran with it off")
    if not cfg.merge.enabled:
        raise SystemExit(f"{cfg.name} has no merge, and the setting needs one")
    raw_cfg = cfg.model_dump(mode="json")
    raw_cfg["clustering"]["fit_excludes_stands_below_min_area"] = True
    on = Config.model_validate(raw_cfg)

    init_gee()
    import ee_read_only  # scripts/: every task or asset write raises before it is sent

    ee_read_only.forbid_writes()
    ee.data.setDeadline(REQUEST_DEADLINE_MS)
    roi = load_roi_geometry(cfg.roi.roi_file)
    scale = cfg.export.analysis_scale_m
    stages = default_stage_names(cfg, through="clustering")
    assert stages[-2:] == ["merge", "clustering"], stages
    ctx = PipelineContext()
    ctx.set("roi", roi)
    run = Pipeline(stages[:-1], use_cache=True, submit_exports=False, summaries=False).run(
        config=cfg, run_dir=Path(tempfile.mkdtemp(prefix="check_fit_excludes_stands_")),
        initial_context=ctx,
    )
    status = {s.name: s.cache_status for s in run.stages}
    live = sorted(f"{st}/{k}" for st, keys in status.items() if st != "merge"
                  for k, v in keys.items() if v != "hit" and k != "mask_provenance")
    if live:
        raise SystemExit(f"{cfg.name}: not cached, so this would compute them live: {live}")
    context = run.context

    def get_info(obj: Any, context: str = "") -> Any:
        print(f"  ... {context}", file=sys.stderr, flush=True)
        return safe_get_info(obj, context=context)

    # The clustering stage itself, keeping what _leave_out_of_fit and _train_and_apply_kmeans
    # were given and returned.
    captured: dict[str, Any] = {}
    leave_out, train = clustering_module._leave_out_of_fit, clustering_module._train_and_apply_kmeans

    def keep_leave_out(**kwargs: Any) -> Any:
        captured["leave_out_args"] = kwargs
        captured["leave_out"] = leave_out(**kwargs)
        return captured["leave_out"]

    def keep_train(**kwargs: Any) -> Any:
        captured["train"] = train(**kwargs)
        return captured["train"]

    warnings = _Warnings()
    stage_log = logging.getLogger(clustering_module.__name__)
    result: dict[str, Any] = {
        "config": cfg.name,
        "with_the_setting_on": {"fit_excludes_stands_below_min_area": True},
        "upstream_cache_status": status,
        "merge": {k: context.get("merge_diagnostics").get(k)
                  for k in ("n_superpixels", "n_stands", "stands_below_min_area",
                            "orphans_isolated", "orphans_area_blocked")},
    }
    try:
        clustering_module._leave_out_of_fit = keep_leave_out
        clustering_module._train_and_apply_kmeans = keep_train
        stage_log.addHandler(warnings)
        stage = clustering_module.ClusteringStage()
        stage.validate(context, on)
        stage_result = stage.run(context, on)
    except Exception as exc:
        result["error"] = " ".join(str(exc).split())[:300]
        stage_result = None
    finally:
        clustering_module._leave_out_of_fit = leave_out
        clustering_module._train_and_apply_kmeans = train
        stage_log.removeHandler(warnings)

    if stage_result is not None and "leave_out" not in captured:
        result["error"] = "the stage did not take the path with the setting on"
    elif stage_result is not None:
        given = captured["leave_out_args"]
        fit_sample, n_fit, report = captured["leave_out"]
        _, coverage = captured["train"]
        labels = row_labels(ee, get_info, training_sample=given["training_sample"],
                            fit_sample=fit_sample, label_band=LABEL_BAND)
        rows = compare_rows(labels["every"], labels["fit"], given["below_min"], report)
        rows["stage_n_rows"], rows["stage_n_fit"] = given["n_rows"], n_fit
        result["rows"], result["fit_report"] = rows, report
        left_out = sorted({int(float(v)) for v in labels["every"]}
                          - {int(float(v)) for v in labels["fit"]})
        try:
            result["types"] = typed(types_of(
                ee, get_info, cluster_labels=stage_result.outputs["cluster_labels"],
                unit_labels=given["unit_labels"], left_out=left_out, roi=roi, scale=scale),
                left_out)
        except Exception as exc:
            result["types"] = {"error": " ".join(str(exc).split())[:300]}
        result["summary_numbers"] = clustering_module.tabulate_clustering_metadata(
            {**coverage, "k": on.clustering.k, "fit_excludes_stands_below_min_area": True})
    result["stage_warnings"] = warnings.messages
    result["export_tasks_submitted"] = sum(len(s.export_tasks) for s in run.stages)
    print("\n".join(verdicts(result)))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=1, default=str) + "\n")
        record = {
            "result_file": args.out.name,
            "command_line": "python " + " ".join(shlex.quote(a) for a in sys.argv),
            "date": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
            "git": {k: v for k, v in git_state().items() if k != "root"},
        }
        run_record_path(args.out).write_text(json.dumps(record, indent=1) + "\n")
        print(f"wrote {args.out} and {run_record_path(args.out).name}")


if __name__ == "__main__":
    main()

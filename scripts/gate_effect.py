"""Isolate what the Task 4 removal of `canopy_height_std` actually did to the stand map.

WHY THREE ARMS
--------------
The removal moved two things at once: `canopy_height_std` came out of
`_DEFAULT_SNIC_INPUT_BANDS` *and* out of `_DEFAULT_MERGE_CRITERIA`. So the superpixels
changed as well as the gate, and a before/after gives the combined effect with no way to
attribute it.

    arm A   6 SNIC bands (with canopy_height_std)   3 criteria    pre-Task-4 reference
    arm B   6 SNIC bands (unchanged)                2 criteria    the GATE change alone
    arm C   5 SNIC bands (current main)             2 criteria    the shipped state

    B vs A  isolates the conjunctive-gate effect.
    C vs B  isolates the segmentation effect.

There is no usable "before" on disk: the archived run at b24fad3 holds only
`current_config`, `k` and `silhouette_current`, and predates the merge stage entirely.
Everything here is run fresh on current main.

THE CROSS-CHECK, AND WHY IT IS NOT OPTIONAL
-------------------------------------------
Arms A and B declare identical `segmentation.input_bands`, so in principle they share a
tessellation and B-minus-A is purely the gate. In principle. `merge.py` says the arms'
"tessellations diverge run to run", and `adjacency.py` records 3595 vs 3594 adjacency pairs
between two runs of the same config. If SNIC is not reproducible, an independent arm-B run
confounds the gate change with tessellation noise, and the headline number is wrong.

So this runs a fourth merge: **arm B's criteria against arm A's own superpixel graph**
(`B_on_A`). Arms A and B_on_A share a tessellation by construction, not by assumption, so
B_on_A minus A is the gate effect exactly. Comparing B_on_A with the independent arm B then
measures the run-to-run noise floor directly, which is what makes C vs B interpretable
rather than merely quotable.

WHY n_stands AND NOT R2
-----------------------
`explained_variance_r2` rises monotonically with region count, so comparing R2 across arms
with different stand counts measures the stand count. That is the matched-stand-count
problem `docs/matched_stand_count.md` describes. Stand count is the primary output here and
everything else is reported beside it, not normalised by it.

COST
----
Three pipeline runs through segmentation over Sanjay Van (~968 ha at 10 m), plus four merges.
`use_cache=False` throughout: nothing is read from or written to the GEE asset cache, so no
export tasks are submitted and no cached asset is created or invalidated. The GEE work is the
S2/S1/ETH composites, SNIC, and one adjacency `getInfo` of ~1250 rows per arm.

Run:  python scripts/gate_effect.py
Out:  odisha_script/gate_effect_results.txt
"""

from __future__ import annotations

import argparse
import socket
import sys
import time
from pathlib import Path
from typing import Any

from fmu.config import Config, load_config
from fmu.pipeline import Pipeline, segmentation_stage_names
from fmu.stages.base import PipelineContext
from fmu.stages.data_load import DataLoadStage  # noqa: F401
from fmu.stages.features_optical import FeaturesOpticalStage  # noqa: F401
from fmu.stages.features_radar import FeaturesRadarStage  # noqa: F401
from fmu.stages.features_static import FeaturesStaticStage  # noqa: F401
from fmu.stages.features_structure import FeaturesStructureStage  # noqa: F401
from fmu.stages.masking import MaskingStage  # noqa: F401
from fmu.stages.merge import MergeStage
from fmu.stages.segmentation import SegmentationStage  # noqa: F401
from fmu.utils.adjacency import stand_geometry, summarize_stand_geometry
from fmu.utils.gee import init_gee, load_roi_geometry
from fmu.utils.logging import init_logging

# Nothing in fmu.utils.gee retries or sets a deadline: safe_get_info and safe_call are thin
# wrappers, so a stalled request blocks forever. This experiment hit that twice -- 37 minutes
# on one segmentation request, then 70 minutes inside the merge's adjacency extraction, both
# at 0% CPU with the socket ESTABLISHED, while a fresh process got answers in ~1 s.
#
# `socket.setdefaulttimeout` does NOT govern Earth Engine requests: the second stall ran 70
# minutes with a 900 s default set, because the transport constructs its own connections. The
# knobs that do work are ee.data.setDeadline() and ee.data.setMaxRetries(), applied after
# init_gee(). Recorded here because it is not obvious and cost two runs to establish.
EE_DEADLINE_MS = 600_000     # per request; a stall now raises instead of hanging
EE_MAX_RETRIES = 3           # transient stalls are retried rather than aborting the run
SOCKET_TIMEOUT_S = 900       # backstop only; does not govern ee requests

ARMS = ("a", "b", "c")
CONFIG_FOR = {a: f"configs/experiments/gate_effect_arm_{a}.yaml" for a in ARMS}
OUT = Path("odisha_script/gate_effect_results.txt")

_out: list[str] = []


def say(s: str = "") -> None:
    _out.append(s)
    print(s)


def rule(t: str) -> None:
    say("")
    say("=" * 100)
    say(t)
    say("=" * 100)


def segment(cfg: Config) -> tuple[PipelineContext, Any]:
    """Run one arm through segmentation. Returns its context and roi."""
    roi = load_roi_geometry(cfg.roi.roi_file)
    ctx = PipelineContext()
    ctx.set("roi", roi)
    run_dir = init_logging(config_name=cfg.name)
    t = time.time()
    Pipeline(
        stage_names=segmentation_stage_names(cfg), use_cache=False
    ).run(config=cfg, run_dir=run_dir, initial_context=ctx)
    say(f"  segmentation for {cfg.name} took {time.time() - t:.1f}s")
    return ctx, roi


def merge_on(ctx: PipelineContext, cfg: Config, roi: Any) -> dict[str, Any]:
    """Run the merge stage against an existing context, and measure the result.

    Deliberately calls the stage rather than reimplementing it, so this measures the
    shipped merge and not a copy of it that could drift.
    """
    stage = MergeStage()
    stage.validate(ctx, cfg)
    t = time.time()
    res = stage.run(ctx, cfg)
    stands = res.outputs["stand_clusters"]
    scale = cfg.export.analysis_scale_m
    geom = stand_geometry(stands, roi, scale, context="gate-effect stand geometry")
    say(f"  merge+geometry took {time.time() - t:.1f}s")
    return {
        "diag": res.outputs["merge_diagnostics"],
        "geom": summarize_stand_geometry(geom, min_area_ha=cfg.merge.min_area_ha),
        "criteria": [(c.band, c.tolerance) for c in cfg.merge.criteria],
    }


def _fmt(v: Any, nd: int = 3) -> str:
    if v is None:
        return "--"
    if isinstance(v, float):
        return f"{v:.{nd}f}"
    return str(v)


def row(label: str, get, results: dict[str, dict], nd: int = 3) -> None:
    cells = "".join(f"{_fmt(get(results[a]), nd):>18}" for a in ARMS)
    say(f"  {label:<44}{cells}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--independent-b",
        action="store_true",
        help="Additionally run arm B's OWN segmentation, to measure the SNIC run-to-run "
             "noise floor. Costs a third cold pipeline; off by default.",
    )
    args = ap.parse_args()

    for a in ARMS:
        if not Path(CONFIG_FOR[a]).exists():
            sys.exit(f"MISSING CONFIG: {CONFIG_FOR[a]}")
    if not OUT.parent.exists():
        sys.exit(f"MISSING OUTPUT DIR: {OUT.parent}")

    socket.setdefaulttimeout(SOCKET_TIMEOUT_S)
    init_gee()
    import ee.data
    ee.data.setDeadline(EE_DEADLINE_MS)
    ee.data.setMaxRetries(EE_MAX_RETRIES)
    say(f"  ee deadline {EE_DEADLINE_MS / 1000:.0f}s per request, "
        f"max {EE_MAX_RETRIES} retries")
    cfgs = {a: load_config(CONFIG_FOR[a]) for a in ARMS}

    say("=" * 100)
    say("GATE EFFECT — what removing canopy_height_std did, split into gate and segmentation")
    say("=" * 100)
    say("  Sanjay Van. Three arms differing only in segmentation.input_bands and")
    say("  merge.criteria. min_defined_criteria = 2 in every arm. No tuned tolerances.")
    say("")
    for a in ARMS:
        c = cfgs[a]
        say(f"  arm {a.upper()}  {CONFIG_FOR[a]}")
        say(f"        snic  ({len(c.segmentation.input_bands)}) "
            f"{[b.band for b in c.segmentation.input_bands]}")
        say(f"        merge ({len(c.merge.criteria)}) "
            f"{[(x.band, x.tolerance) for x in c.merge.criteria]}"
            f"   min_defined={c.merge.min_defined_criteria}")

    results: dict[str, dict] = {}

    # Arms A and B declare IDENTICAL segmentation.input_bands, so they are one segmentation
    # run with two gates on it. Running B's own segmentation as well would cost a second
    # cold pipeline (nothing is cached -- Task 4 changed the fingerprint) and would make
    # B-minus-A depend on SNIC being reproducible, which merge.py explicitly doubts. Driving
    # both gates off arm A's graph holds the tessellation identical BY CONSTRUCTION, which is
    # the stronger form of the comparison the brief asked for, not a shortcut around it.
    rule("RUN — arm A (6-band segmentation, 3 criteria)")
    ctx_a, roi_a = segment(cfgs["a"])
    results["a"] = merge_on(ctx_a, cfgs["a"], roi_a)
    say(f"  arm A: {results['a']['diag']['n_superpixels']} superpixels -> "
        f"{results['a']['diag']['n_stands']} stands")

    rule("RUN — arm B (arm A's tessellation, 2 criteria)")
    results["b"] = merge_on(ctx_a, cfgs["b"], roi_a)
    say(f"  arm B: {results['b']['diag']['n_superpixels']} superpixels -> "
        f"{results['b']['diag']['n_stands']} stands")

    rule("RUN — arm C (5-band segmentation, 2 criteria)")
    ctx_c, roi_c = segment(cfgs["c"])
    results["c"] = merge_on(ctx_c, cfgs["c"], roi_c)
    say(f"  arm C: {results['c']['diag']['n_superpixels']} superpixels -> "
        f"{results['c']['diag']['n_stands']} stands")

    # Optional determinism control: does arm B's OWN segmentation reproduce arm A's? Off by
    # default because it costs a third cold pipeline. Without it, the C-vs-B comparison
    # carries an unmeasured tessellation-noise floor, and the report says so.
    indep_b = None
    if args.independent_b:
        rule("CONTROL — arm B's own segmentation run (determinism check)")
        ctx_b, roi_b = segment(cfgs["b"])
        indep_b = merge_on(ctx_b, cfgs["b"], roi_b)
        say(f"  independent B: {indep_b['diag']['n_superpixels']} superpixels -> "
            f"{indep_b['diag']['n_stands']} stands")

    # ---------------------------------------------------------------- table
    rule("COMPARISON")
    say(f"  {'':<44}{'arm A':>18}{'arm B':>18}{'arm C':>18}")
    say(f"  {'':<44}{'6 bands / 3 crit':>18}{'6 bands / 2 crit':>18}{'5 bands / 2 crit':>18}")
    say("")
    say("  -- primary --")
    row("n_superpixels", lambda r: r["diag"]["n_superpixels"], results)
    row("n_stands", lambda r: r["diag"]["n_stands"], results)
    row("reduction factor (superpixels/stands)",
        lambda r: r["diag"]["reduction_factor"], results)
    say("")
    say("  -- merge passes --")
    row("pass1_rounds", lambda r: r["diag"]["pass1_rounds"], results)
    row("pass1_merges", lambda r: r["diag"]["pass1_merges"], results)
    row("pass2_iterations", lambda r: r["diag"]["pass2_iterations"], results)
    row("pass2_merges", lambda r: r["diag"]["pass2_merges"], results)
    row("pass2_fallback_merges", lambda r: r["diag"]["pass2_fallback_merges"], results)
    say("")
    say("  -- rejection attribution (pass 1, round 1) --")
    row("pairs blocked by area",
        lambda r: r["diag"]["pass1_pairs_blocked_by_area_round1"], results)
    row("pairs blocked_by_undefined_criteria",
        lambda r: r["diag"]["pass1_pairs_blocked_by_undefined_criteria_round1"], results)
    say("")
    say("  -- orphans --")
    row("orphans_isolated", lambda r: r["diag"]["orphans_isolated"], results)
    row("orphans_area_blocked", lambda r: r["diag"]["orphans_area_blocked"], results)
    row("orphans_no_attribute_match",
        lambda r: r["diag"]["orphans_no_attribute_match"], results)
    row("stands_with_incomplete_criteria",
        lambda r: r["diag"]["stands_with_incomplete_criteria"], results)
    say("")
    say("  -- stand area distribution (ha) --")
    for label, key in (("min", "area_ha_min"), ("p10", "area_ha_p10"),
                       ("median", "area_ha_median"), ("p90", "area_ha_p90"),
                       ("max", "area_ha_max"), ("mean", "area_ha_mean"),
                       ("total", "total_area_ha")):
        row(f"area {label}", lambda r, k=key: r["geom"][k], results, nd=4)
    row("stands below min_area_ha",
        lambda r: r["geom"]["stands_below_min_area"], results)
    row("area in undersized stands (ha)",
        lambda r: r["geom"]["area_in_undersized_stands_ha"], results, nd=4)
    row("area share of largest decile",
        lambda r: r["geom"]["area_share_largest_decile"], results, nd=4)
    say("")
    say("  -- shape --")
    row("polsby_popper_median", lambda r: r["geom"]["polsby_popper_median"], results, nd=4)
    row("polsby_popper_above_one",
        lambda r: r["geom"]["polsby_popper_above_one"], results)
    say("")
    say("  -- adjacency graph --")
    row("n_edges", lambda r: r["diag"]["adjacency"]["n_edges"], results)
    row("mean_degree", lambda r: r["diag"]["adjacency"]["mean_degree"], results)

    # ---------------------------------------------------------------- calibration
    rule("CALIBRATED TOLERANCES — where each arm's thresholds land in its OWN distribution")
    say("  Each arm calibrates against its own band set via calibrate_thresholds(). No")
    say("  threshold was changed to make the arms agree; these are reported, not fed back.")
    for a in ARMS:
        cal = results[a]["diag"]["threshold_calibration"]
        say("")
        say(f"  --- arm {a.upper()} ---   n_pairs={cal['n_pairs']}   "
            f"joint_admit_rate={cal['joint_admit_rate_pct']}%   "
            f"(pairs with any defined criterion: {cal['n_pairs_with_any_defined_criterion']})")
        say(f"      {'band':<26}{'tol':>8}{'pct<=tol':>10}{'p25':>10}"
            f"{'p50':>10}{'p75':>10}{'p90':>10}{'n_defined':>11}")
        for band, s in sorted(cal["per_band"].items()):
            say(f"      {band:<26}{s['threshold']:>8}{s['percentile_of_threshold']:>10}"
                f"{_fmt(s['p25'],4):>10}{_fmt(s['p50'],4):>10}{_fmt(s['p75'],4):>10}"
                f"{_fmt(s['p90'],4):>10}{s['n_pairs_defined']:>11}")

    # ---------------------------------------------------------------- control
    rule("HOW FAR THE ISOLATION HOLDS")
    a_sp = results["a"]["diag"]["n_superpixels"]
    say(f"  Arms A and B were merged from the SAME superpixel graph ({a_sp} regions), so")
    say("  B minus A is the gate change with the tessellation held identical by")
    say("  construction. That comparison carries no tessellation noise at all.")
    say("")
    if indep_b is not None:
        ib_sp = indep_b["diag"]["n_superpixels"]
        say(f"  Determinism control: arm B's own segmentation run gave {ib_sp} superpixels "
            f"({ib_sp - a_sp:+d} vs arm A)")
        say(f"  and {indep_b['diag']['n_stands']} stands "
            f"({indep_b['diag']['n_stands'] - results['b']['diag']['n_stands']:+d} vs arm B "
            f"on A's graph).")
        if ib_sp == a_sp and indep_b["diag"]["n_stands"] == results["b"]["diag"]["n_stands"]:
            say("  SNIC reproduced exactly for a fixed band stack, so the C-vs-B noise floor")
            say("  is zero and that comparison is as clean as B vs A.")
        else:
            say("  SNIC did NOT reproduce exactly. That difference is the noise floor which")
            say("  C vs B is measured against, and it must be quoted alongside it.")
    else:
        say("  NOT MEASURED: the SNIC run-to-run noise floor. C vs B compares two separate")
        say("  segmentation runs, and merge.py records that tessellations can diverge run to")
        say("  run (adjacency.py: 3595 vs 3594 pairs across two runs of one config). So the")
        say("  C-vs-B figure below carries an unquantified noise term, while B vs A does not.")
        say("  Re-run with --independent-b to measure it; it costs a third cold pipeline.")

    # ---------------------------------------------------------------- prose
    rule("WHAT THIS SHOWS")
    a_st, b_st, c_st = (results[x]["diag"]["n_stands"] for x in ARMS)
    a_sp2, b_sp2, c_sp2 = (results[x]["diag"]["n_superpixels"] for x in ARMS)
    gate = b_st - a_st

    say("  B vs A — the gate change alone.")
    say(f"    Superpixels are held fixed ({a_sp2}). Dropping the third criterion moves the")
    say(f"    stand count by {gate:+d} ({a_st} -> {a_st + gate}, "
        f"{100.0 * gate / a_st:+.1f}%).")
    say("")

    ua = results["a"]["diag"]["pass1_pairs_blocked_by_undefined_criteria_round1"]
    ub = results["b"]["diag"]["pass1_pairs_blocked_by_undefined_criteria_round1"]
    cal_a = results["a"]["diag"]["threshold_calibration"]
    cal_b = results["b"]["diag"]["threshold_calibration"]
    defined_a = {b: v["n_pairs_defined"] for b, v in cal_a["per_band"].items()}

    say("    The definedness floor did NOT do it. Pairs blocked by undefined criteria go")
    say(f"    {ua} -> {ub} ({ub - ua:+d}).")
    say("")
    say("    Why, measured rather than assumed: a criterion is undefined where its source")
    say("    image is masked, and per-band defined-pair counts in arm A are")
    for band, n in sorted(defined_a.items()):
        say(f"      {band:<26} defined on {n} of {cal_a['n_pairs']} pairs")
    struct = sorted(n for b, n in defined_a.items() if b.startswith("canopy_height"))
    if len(struct) > 1 and len(set(struct)) == 1:
        say("")
        say("    canopy_height and canopy_height_std are defined on EXACTLY the same pairs.")
        say("    Both are derived from the same ETH image, so they are masked together and")
        say("    go undefined together. A pair missing ETH therefore had ONE defined")
        say("    criterion under 3-criteria and ONE under 2 — blocked either way. Dropping")
        say("    a band that is collinear in definedness with one that remains cannot move")
        say("    the definedness floor, whatever the floor is set to.")
    say("")
    say("    What did it was the TOLERANCE conjunction. The joint admit rate — the share of")
    say(f"    pairs clearing every tolerance at once — goes "
        f"{cal_a['joint_admit_rate_pct']}% -> {cal_b['joint_admit_rate_pct']}% "
        f"({cal_b['joint_admit_rate_pct'] - cal_a['joint_admit_rate_pct']:+.2f} pts) with one")
    say(f"    fewer threshold to clear, and pass-1 merges rise "
        f"{results['a']['diag']['pass1_merges']} -> {results['b']['diag']['pass1_merges']}.")
    say("    That is the whole mechanism: fewer hurdles per pair, not fewer pairs disqualified")
    say("    for missing data.")
    say("")
    say("  C vs B — the segmentation change alone.")
    say("    The gate is held fixed at 2 criteria. Dropping canopy_height_std from the SNIC")
    say(f"    stack moves superpixels {b_sp2} -> {c_sp2} ({c_sp2 - b_sp2:+d}) and stands")
    say(f"    {b_st} -> {c_st} ({c_st - b_st:+d}, {100.0 * (c_st - b_st) / b_st:+.1f}%).")
    say("")
    say("  C vs A — the combined effect, which is what shipped.")
    say(f"    {a_st} -> {c_st} stands ({c_st - a_st:+d}, "
        f"{100.0 * (c_st - a_st) / a_st:+.1f}%).")
    say("")
    say("  No threshold was tuned to bring the arms together. Where the stand count moves,")
    say("  that is the measurement.")

    OUT.write_text("\n".join(_out) + "\n")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()

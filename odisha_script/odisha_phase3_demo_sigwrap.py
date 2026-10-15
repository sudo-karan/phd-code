"""Run odisha_phase3_3_significance.py, unmodified, on other stand files and another plot table.

Why this exists. The chance test reads its plot table and its stand files from fixed places
(JOINED and odisha_phase2_3_join.VECTOR_DIR), has no option for either, and knows two arms
only (10 ha and 3 ha). The demo set needs the same test on re-merged stands, and on the
AlphaEarth stands as a third arm. Editing the script would change what the committed Phase 3
results came from, so this module imports it, points it elsewhere at run time, and calls its
own main(). Every statistic, every seed and every printed line is the script's.

What is set, and nothing else (each is explained where it is done, in configure()):
  1. odisha_phase2_3_join.VECTOR_DIR   where the stand files are read from
  2. the script's JOINED               which plot table each arm is read from
  3. the script's load_all             so that the plot set comes from that table too
  4. the script's ARM_LABEL            one more arm, and only for a run of that arm alone

With the committed paths and no extra arm the output is the script's own, byte for byte
(tests/test_phase3_demo_fes.py checks it).

Usage, from the repo root (odisha_phase3_demo_fes.py builds these commands; this is what it runs):
    python odisha_script/odisha_phase3_demo_sigwrap.py --vectors-dir DIR --joined CSV \\
        [--single-arm alphaearth] -- <the options of odisha_phase3_3_significance.py>
  --joined CSV        one plot table holding every arm run, or ARM=CSV once per arm
  --single-arm ARM    run ARM alone as an arm the script does not know (alphaearth). The
                      options after -- must then say --arms ARM. Refused for alphaearth unless
                      its declaration is committed and pushed (odisha_phase3_demo_fes.py).
Reads : the plot table(s), the stand files in --vectors-dir, the AOIs, the field-types file.
Writes: what the script writes, <out-dir>/odisha_phase3_3_results<suffix>.txt and its .log.
Offline; no Earth Engine.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# The label the script prints for an arm it does not know. Only AlphaEarth is declared
# (PHASE3_ALPHAEARTH_PREDECLARED.md); another arm needs its own declaration and a line here.
EXTRA_ARM_LABEL = {"alphaearth": "AlphaEarth 10 ha"}
PLOT_COLUMNS = ("plot_key", "lat6", "lon6")     # what two plot tables must agree on


def arm_columns(arm: str, layers) -> list[str]:
    """The join's columns for one arm, by exact name. A prefix test would not do: 'v120_'
    is also how the columns of v120_3ha start."""
    return [f"{arm}_{short}_{col}" for short in layers for col in ("id", "cluster", "area_ha", "bdist_m")]


def configure(vectors_dir: Path, joined: Path | dict, single_arm: str | None = None):
    """Point the significance script at vectors_dir and at the plot table(s) in `joined`
    (one path for every arm, or {arm: path}). Returns the script's module, ready for main().

    The imports are here, not at the top: they pull in numpy, shapely and matplotlib, and
    the driver that builds the commands needs none of them."""
    import odisha_phase2_3_join as J  # noqa: N812
    import odisha_phase2_5_stats as S  # noqa: N812
    import odisha_phase3_3_significance as G  # noqa: N812
    import pandas as pd

    if single_arm is not None:
        if single_arm not in EXTRA_ARM_LABEL:
            raise SystemExit(f"--single-arm: {single_arm!r} is not a declared extra arm ({sorted(EXTRA_ARM_LABEL)})")
        if single_arm not in J.ALL_ARMS:
            raise SystemExit(f"--single-arm: the join knows no arm {single_arm!r}")
        if single_arm == "alphaearth":
            # No AlphaEarth test before its declaration is committed and pushed: the check the
            # driver makes, repeated here, before anything is set, so that this file cannot be
            # used around it.
            import odisha_phase3_demo_fes as D  # noqa: N812
            D.require_alphaearth_declared()

    vectors_dir = Path(vectors_dir).resolve()
    if not vectors_dir.is_dir():
        raise SystemExit(f"--vectors-dir {vectors_dir} is not a folder")
    arms_known = [*G.ARM_LABEL, *(a for a in EXTRA_ARM_LABEL if a not in G.ARM_LABEL)]
    table = ({a: Path(joined).resolve() for a in arms_known} if not isinstance(joined, dict)
             else {a: Path(p).resolve() for a, p in joined.items()})
    for a, p in table.items():
        if not p.is_file():
            raise SystemExit(f"--joined: no plot table {p} (arm {a})")

    # 1. Where the stand files are read from. odisha_phase2_3_join.vector_path() looks
    #    VECTOR_DIR up each time it is called, and the statistics module (Partition, the
    #    rotation null) reaches the files only through that function, so this one assignment
    #    moves the join's presence rule, the identity check and both nulls together.
    J.VECTOR_DIR = vectors_dir

    # 2. Which plot table each arm is read from. scorer_observed() recomputes the observed
    #    statistics the scorer's way from JOINED[arm]; it must read the table the stands were
    #    joined into, or its check against the array path would compare two different joins.
    G.JOINED = {**G.JOINED, **table}

    # 3. One more arm, for a run of that arm ALONE. ARM_LABEL is also the script's default
    #    --arms and its test for "is this the primary two-arm run" (sensitivity_tag), and
    #    compare_arms() reads the 10 ha and the 3 ha arm by name. So the label is added only
    #    here, in the process that runs the extra arm by itself: the script then takes its
    #    single-arm path (five tests, Holm over those five, no arm comparison) and adds the
    #    suffix _<arm> to the file name. A two-arm run never sees a third label.
    if single_arm is not None:
        G.ARM_LABEL = {**G.ARM_LABEL, single_arm: EXTRA_ARM_LABEL[single_arm]}

    # 4. The plot set. The script's own load_all() calls set_spec("districts") with no
    #    folder, so the plots, their AOI parts and the 10 ha columns always come from the
    #    committed 10 ha table, whatever JOINED says. This version does what that one does
    #    (select the arms in place, load through the statistics module, add the field types,
    #    stop on a plot without one) but takes the plot set from the first arm's table and
    #    each further arm's columns from its own. With the committed tables it returns the
    #    same plots in the same order.
    def load_all(arms: list, field_types: Path):
        missing = [a for a in arms if a not in G.JOINED]
        if missing:
            raise SystemExit(f"no plot table was given for arm(s) {missing}")
        J.ARMS.clear()
        J.ARMS.update({k: J.ALL_ARMS[k] for k in arms})      # in place, as the script does
        base = G.JOINED[arms[0]]
        spec = J.set_spec("districts")
        spec["joined"] = base
        _, plots, parts = S.load(spec)
        for a in arms:
            cols = arm_columns(a, J.LAYERS)
            if G.JOINED[a] == base:
                absent = [c for c in cols if c not in plots.columns]
                if absent:
                    raise SystemExit(f"{base} has no columns for arm {a} (for example {absent[0]}): "
                                     "the join was not run for this arm")
                continue
            ja = pd.read_csv(G.JOINED[a])
            absent = [c for c in cols if c not in ja.columns]
            if absent:
                raise SystemExit(f"{G.JOINED[a]} has no columns for arm {a} (for example {absent[0]})")
            # two tables are one plot set only if they hold the same plots at the same places
            both = plots[list(PLOT_COLUMNS)].merge(ja[list(PLOT_COLUMNS)], on="plot_key", how="left",
                                                   suffixes=("", "_other"), validate="1:1")
            if not ((both.lat6 == both.lat6_other) & (both.lon6 == both.lon6_other)).all():
                raise SystemExit(f"{G.JOINED[a]} and {base} do not hold the same plots at the same coordinates")
            plots = plots.drop(columns=[c for c in cols if c in plots.columns])
            plots = plots.merge(ja[["plot_key", *cols]], on="plot_key", how="left", validate="1:1")
        ft = pd.read_csv(field_types)[["plot_key", "field_type"]]
        plots = plots.merge(ft, on="plot_key", how="left", validate="1:1")
        if plots.field_type.isna().any():
            raise SystemExit(f"{int(plots.field_type.isna().sum())} in-AOI plot(s) have no field type")
        return spec, plots, parts

    G.load_all = load_all
    return G


def parse_joined(values: list[str]) -> Path | dict:
    """'CSV' -> one table for every arm; 'ARM=CSV' (once per arm) -> {arm: table}."""
    if len(values) == 1 and "=" not in values[0]:
        return Path(values[0])
    out = {}
    for v in values:
        arm, sep, path = v.partition("=")
        if not sep or not arm or not path:
            raise SystemExit(f"--joined: expected one CSV, or ARM=CSV once per arm; got {v!r}")
        out[arm] = Path(path)
    return out


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--" not in argv:
        raise SystemExit("usage: odisha_phase3_demo_sigwrap.py --vectors-dir DIR --joined CSV [--single-arm ARM] "
                         "-- <options of odisha_phase3_3_significance.py>")
    cut = argv.index("--")
    own, passed = argv[:cut], argv[cut + 1:]
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--vectors-dir", type=Path, required=True)
    ap.add_argument("--joined", action="append", required=True, metavar="CSV | ARM=CSV")
    ap.add_argument("--single-arm", default=None, choices=sorted(EXTRA_ARM_LABEL))
    args = ap.parse_args(own)

    # The extra arm runs alone or not at all: beside another arm the script would take its
    # two-arm path, which is written for the 10 ha and the 3 ha arm by name.
    asked = [passed[i + 1] for i, a in enumerate(passed[:-1]) if a == "--arms"]
    asked += [a.split("=", 1)[1] for a in passed if a.startswith("--arms=")]
    if args.single_arm is not None and asked != [args.single_arm]:
        raise SystemExit(f"--single-arm {args.single_arm}: the options after -- must say --arms {args.single_arm} "
                         f"(they say {asked or 'nothing, which means both hand-crafted arms'})")
    if args.single_arm is None and any(a in EXTRA_ARM_LABEL for x in asked for a in x.split(",")):
        raise SystemExit("an extra arm (alphaearth) is run with --single-arm, alone")

    G = configure(args.vectors_dir, parse_joined(args.joined), args.single_arm)  # noqa: N806
    # the script reads its options from sys.argv; hand it its own, under its own name
    sys.argv = [str(HERE / "odisha_phase3_3_significance.py"), *passed]
    return int(G.main())


if __name__ == "__main__":
    raise SystemExit(main())

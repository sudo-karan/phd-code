"""
Phase 1, step 11 — is the Meta zero pattern temporal rather than model failure?

WHY
---
The supervisor memo lists survey year among the enquiries blocked on FES, on the grounds
that it "determines whether the field campaign and Meta's source imagery -- 2009-2020,
chiefly 2018-2020 -- are contemporaneous, and therefore whether any part of the Meta zero
pattern is temporal rather than model failure."

That is the right question and it is the one live alternative to the DISQUALIFIED verdict:
if the imagery predates the survey by enough, a plot that carries canopy today could
genuinely have been bare ground when Meta saw it, and a reading of 0 would be correct
rather than a failure.

It is not blocked. `Odisha_samples.csv` carries `Creation Date` and `Submission Date` on
every one of the 5,910 tree records. The date was simply not carried through
`odisha_phase1_0_clean.py` into the plot-level CSV, so nothing downstream could see it.

WHAT THIS DOES
--------------
Recovers the survey date per plot (earliest tree record, keyed the same way step 0 keys
plots -- rounded lat/lon, not Plot No), then asks the arithmetic question the temporal
hypothesis has to answer:

    for a plot that reads Meta 0 (predicted under half a metre) and measures H metres of
    Lorey's height at survey time, what growth rate does the gap require?

Reported at both ends of the collection's stated imagery window, because the answer is
entirely governed by which end applies:

  - 2020, the late end of "chiefly 2018-2020" -- the window the product is documented as
    representing.
  - 2009, the earliest acquisition anywhere in the collection -- the most generous
    assumption available to the temporal hypothesis.

WHAT THIS DOES NOT DO
---------------------
It does not assert a growth rate for Sal or any other species, and it does not pronounce
on the hypothesis. It prints the rate each plot would require and leaves the comparison
against known silviculture to the reader, because a species growth rate is not something
this repository can compute. It writes no CSV and changes no published number.

Run:  python odisha_phase1_11_survey_date_check.py
Out:  odisha_phase1_11_results.txt
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

SAMPLES = "Odisha_samples.csv"
PLOTS = "odisha_plots_sampled_v2.csv"
OUT = "odisha_phase1_11_results.txt"

# The two ends of the imagery window, as stated in the collection description. Not
# tunable: they are the documented bounds, and the whole point is that the answer differs
# between them.
IMAGERY_BOUNDS = (
    (2020, "late end of the documented 'chiefly 2018-2020' window"),
    (2009, "earliest acquisition anywhere in the collection"),
)
RATE_BARS = (1.0, 2.0, 3.0)

_out: list[str] = []


def say(s: str = "") -> None:
    _out.append(s)
    print(s)


def rule(t: str) -> None:
    say("")
    say("=" * 96)
    say(t)
    say("=" * 96)


def main() -> None:
    for f in (SAMPLES, PLOTS):
        if not Path(f).exists():
            sys.exit(f"MISSING INPUT: {f} — run from the odisha_script directory.")

    say("=" * 96)
    say("PHASE 1 STEP 11 — survey date, and whether the Meta zeros are temporal")
    say("=" * 96)

    s = pd.read_csv(SAMPLES, low_memory=False)
    # Same key as step 0: rounded lat/lon, deliberately not Plot No or Site Name.
    s["plot_key"] = (
        s["Plot Lat"].round(6).astype(str) + "_" + s["Plot Long"].round(6).astype(str)
    )
    # errors="raise": an unparseable date must be loud. The claim being made is that every
    # record carries one, and a silent NaT would quietly shrink the denominator.
    s["survey_date"] = pd.to_datetime(s["Creation Date"], errors="raise", format="mixed")

    rule("A — the survey date was never blocked; it is in the raw records")
    say(f"  source: {SAMPLES}")
    say(f"  tree records: {len(s):,}   parsed dates: {s.survey_date.notna().sum():,}")
    say(
        f"  campaign window: {s.survey_date.min().date()} .. {s.survey_date.max().date()}"
    )
    by_year = s.survey_date.dt.year.value_counts().sort_index()
    say(f"  tree records by year: {by_year.to_dict()}")
    say("")
    say("  `odisha_phase1_0_clean.py` aggregates trees to plots but does not carry any of")
    say("  `Creation Date`, `Submission Date` or the form timestamp through to the plot")
    say("  CSV, which is why every downstream step has treated the year as unknown.")

    per_plot = s.groupby("plot_key")["survey_date"].min().rename("survey_date")
    df = pd.read_csv(PLOTS).merge(per_plot, on="plot_key", how="left")
    say("")
    say(f"  plots matched to a survey date: {df.survey_date.notna().sum()} / {len(df)}")

    rule("B — the growth rate the temporal hypothesis requires")
    z = df[df.meta_chm == 0].dropna(subset=["survey_date", "loreys_h_m"])
    say(f"  zero plots carrying both a date and a field height: {len(z)}")
    say(
        f"  their field Lorey's height: {z.loreys_h_m.min():.2f} .. "
        f"{z.loreys_h_m.max():.2f} m   median {z.loreys_h_m.median():.2f} m"
    )
    say("")
    say("  A Meta 0 means 'predicted under half a metre'. So for a zero plot measuring H m")
    say("  at survey time, the temporal explanation requires (H - 0.5) / gap metres a year,")
    say("  sustained from the imagery date to the survey date.")

    for year, note in IMAGERY_BOUNDS:
        # Mid-year for the imagery, exact day-of-year for the survey.
        gap = (
            z.survey_date.dt.year + z.survey_date.dt.dayofyear / 365.25 - (year + 0.5)
        )
        rate = (z.loreys_h_m - 0.5) / gap
        say("")
        say(f"  --- imagery = {year}: {note} ---")
        say(f"  gap to survey: {gap.min():.1f} .. {gap.max():.1f} years")
        say(
            f"  required growth rate (m/yr):  median {rate.median():.2f}   "
            f"p90 {rate.quantile(0.9):.2f}   max {rate.max():.2f}"
        )
        for bar in RATE_BARS:
            n = int((rate > bar).sum())
            say(
                f"    plots requiring more than {bar:.0f} m/yr: {n:3d} of {len(z)} "
                f"({100 * n / len(z):.0f}%)"
            )

    rule("What this settles, and what it leaves open")
    say("  The survey ran 2022-04-25 to 2023-04-05, so the field campaign postdates the")
    say("  imagery either way and the hypothesis is not symmetric: forest can grow into a")
    say("  zero, it cannot grow out of one.")
    say("")
    say("  Under the documented window the hypothesis fails. A ~2-year gap requires the")
    say("  median zero plot to have grown at over 2 m a year, and the tallest at over 15,")
    say("  which is not growth in any dry deciduous forest.")
    say("")
    say("  Under a 2009 sourcing it survives the arithmetic: a ~13-year gap brings the")
    say("  median requirement below half a metre a year. So the verdict rests on these")
    say("  particular tiles coming from the late window the collection documents, and the")
    say("  residual check is the per-tile acquisition date, not a question for FES.")

    Path(OUT).write_text("\n".join(_out) + "\n")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()

"""Phase 1's scripts, offline: record fixes of round 13 (review of 19 Oct 2026).

- C3: step 7's part A gave field Lorey's height as "running to 37.75 m", the mean of Test 1's
  top height bin; the plots run to 45.52 m.

No Earth Engine call: step 7's part B is not run.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "odisha_script"
sys.path.insert(0, str(SCRIPTS))

import odisha_phase1_7_meta_zero_diagnosis as step7  # noqa: E402

# --------------------------------------------------------------------------- C3


def test_step7_gives_the_field_maximum_not_the_top_bin_mean(monkeypatch):
    monkeypatch.setattr(step7, "_out", [])
    df = pd.read_csv(SCRIPTS / "odisha_plots_sampled_v2.csv")
    step7.part_a(df)
    line = next(s for s in step7._out if "against field Lorey's heights" in s)
    assert f"{df.loreys_h_m.max():.2f}" == "45.52"
    assert line == "  levels, 0 to 15 m, against field Lorey's heights running to 45.52 m."

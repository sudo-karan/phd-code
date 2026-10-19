"""Phase 1's scripts, offline: record fixes of round 13 (review of 19 Oct 2026).

- C3: step 7's part A gave field Lorey's height as "running to 37.75 m", the mean of Test 1's
  top height bin; the plots run to 45.52 m.
- C22: the close-out correlated site means rounded to 2 dp; it must correlate the unrounded
  means and round only when printing.

No Earth Engine call: step 7's part B is not run.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd
from scipy import stats

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


# --------------------------------------------------------------------------- C22


def test_closeout_correlates_unrounded_site_means(tmp_path):
    # One plot per site, so a site mean is the plot's value. The values are chosen so that
    # rounding the means to 2 dp moves Pearson's r in the third decimal.
    field = [1.004, 2.006, 2.996, 4.004, 4.995, 6.005]
    eth = [0.104, 0.196, 0.304, 0.196, 0.504, 0.396]
    pd.DataFrame({
        "plot_key": [f"p{i}" for i in range(6)],
        "loreys_h_m": field,
        "site_polygon": [f"S{i}" for i in range(6)],
        "eth_chm_3x3": eth,
    }).to_csv(tmp_path / "odisha_plots_sampled_v2.csv", index=False)
    exact = float(stats.pearsonr(field, eth)[0])
    rounded = float(stats.pearsonr([round(v, 2) for v in field], [round(v, 2) for v in eth])[0])
    assert f"{exact:+.3f}" != f"{rounded:+.3f}"  # a case where rounding first changes r

    subprocess.run([sys.executable, str(SCRIPTS / "odisha_phase1_6_closeout.py")], cwd=tmp_path,
                   check=True, capture_output=True, text=True)
    out = (tmp_path / "odisha_phase1_closeout.txt").read_text().splitlines()
    line = next(s for s in out if s.startswith("  site-level  eth_chm_3x3"))
    assert line.split("pearson r=")[1].split()[0] == f"{exact:+.3f}"
    # the table of site means is still printed to 2 dp
    s0 = next(s for s in out if s.startswith("S0 "))
    assert s0.split()[2] == "1.00" and float(s0.split()[3]) == 0.10

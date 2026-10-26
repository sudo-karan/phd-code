"""Phase 1's scripts, offline: record fixes of round 13 (review of 19 Oct 2026).

- C3: step 7's part A gave field Lorey's height as "running to 37.75 m", the mean of Test 1's
  top height bin; the plots run to 45.52 m.
- C22: the close-out correlated site means rounded to 2 dp; it must correlate the unrounded
  means and round only when printing.
- C26: step 12's --offline mode rewrote the run record, so the git block of the Earth Engine
  sampling run was lost; it must keep the sampling run's command, date and git block.

No Earth Engine call: step 7's part B is not run, and step 12's `sample` is replaced by the
committed sample.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
from scipy import stats

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "odisha_script"
sys.path.insert(0, str(SCRIPTS))

import odisha_phase1_7_meta_zero_diagnosis as step7  # noqa: E402
import odisha_phase1_12_radar_descending as step12  # noqa: E402

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


# --------------------------------------------------------------------------- C26


def _fake_git(commit: str, dirty: bool):
    def git_state(*_a, **_k):
        return {"commit": commit, "dirty": dirty, "modified": [], "modified_truncated": False,
                "untracked": [], "untracked_truncated": False, "root": "/x", "error": None}
    return git_state


def test_step12_offline_keeps_the_sampling_runs_git_block(tmp_path, monkeypatch):
    committed_run = json.loads((SCRIPTS / "odisha_phase1_12_radar_descending_run.json").read_text())
    committed_sample = pd.read_csv(SCRIPTS / "odisha_plots_sampled_s1desc.csv")
    monkeypatch.setattr(step12, "RESULTS", tmp_path / "results.txt")
    monkeypatch.setattr(step12, "RUN", tmp_path / "run.json")
    monkeypatch.setattr(step12, "SAMPLE", tmp_path / "sample.csv")
    monkeypatch.setattr(step12, "sample",
                        lambda: (committed_sample.copy(), dict(committed_run["images_per_district"])))
    import fmu.utils.provenance as prov

    # 1. the sampling run (Earth Engine replaced by the committed sample)
    monkeypatch.setattr(prov, "git_state", _fake_git("a" * 40, False))
    monkeypatch.setattr(sys, "argv", ["odisha_phase1_12_radar_descending.py"])
    assert step12.main() == 0
    sampled = json.loads((tmp_path / "run.json").read_text())

    # 2. an offline re-analysis, from another commit with a dirty tree
    monkeypatch.setattr(prov, "git_state", _fake_git("b" * 40, True))
    monkeypatch.setattr(sys, "argv", ["odisha_phase1_12_radar_descending.py", "--offline"])
    assert step12.main() == 0
    rec = json.loads((tmp_path / "run.json").read_text())

    assert rec["git"]["commit"] == "b" * 40          # this run's own block
    assert rec["sampled"] == sampled["date"]
    sampling = rec.get("sampling_run", {})
    assert sampling.get("git", {}).get("commit") == "a" * 40
    assert sampling.get("git", {}).get("dirty") is False
    assert sampling.get("command_line", "").endswith("odisha_phase1_12_radar_descending.py")
    assert sampling.get("date") == sampled["date"]
    # the offline run analyses the same sample into the committed result file
    assert (tmp_path / "results.txt").read_text() == \
        (SCRIPTS / "odisha_phase1_12_radar_descending_results.txt").read_text()

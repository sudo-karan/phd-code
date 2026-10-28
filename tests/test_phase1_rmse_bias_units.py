"""Phase 1, steps 2 and 6, offline: RMSE and bias only where both sides are heights in metres.

Round 13 question 18 (review C21 of 19 Oct 2026), answered (a) on 26 Oct 2026 by the round 14
brief's rule "Every other question: your recommendation": the rule round 10 applied to step 12
(round 9 question 3 (b)) applies to steps 2 and 6 too.

- Step 2 (`odisha_phase1_2_analyse.py`) printed RMSE and bias for Test 2, NDVI amplitude against a
  Sal fraction, and for Test 3, ETH roughness in metres against crown cover in per cent. Test 1,
  ETH height against field heights, both in metres, keeps them.
- The close-out (`odisha_phase1_6_closeout.py`) printed a bias for vh_iqr and vv_iqr, radar
  spreads in dB, against Lorey's height in metres. The eight height products keep theirs.

Nothing else changes: step 2's whole output is its committed file as first written but for the
eight Test 2 and Test 3 lines, and the close-out's section A/B is its committed file's but for the
two radar lines. The close-out's section C differs from its file as first written in four lines,
from round 13's C22 (docs/reproducibility.md), so it is checked against the `_r14` file only. Each
script's output is committed beside its old file under a `_r14` name, and is checked here.
Each script runs in a temporary folder on its committed input; no Earth Engine call.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "odisha_script"

# The close-out's candidates that are heights in metres, as field Lorey's height is, and the two
# that are radar spreads in dB.
METRES = ["eth_chm_3x3", "meta_chm_3x3", "meta_mean_15m", "meta_p95_15m", "meta_mean_30m",
          "meta_p95_30m", "glad_chm", "gedi_rh98_50m"]
RADAR_DB = ["vh_iqr", "vv_iqr"]


def _run(folder: Path, script: str, data: str, result: str) -> list[str]:
    """Run a Phase 1 script in `folder` on its committed input; the lines of the file it writes."""
    shutil.copy(SCRIPTS / data, folder / data)
    subprocess.run([sys.executable, str(SCRIPTS / script)], cwd=folder, check=True,
                   capture_output=True, text=True)
    return (folder / result).read_text().split("\n")


def _as_first_written(name: str) -> list[str]:
    """A committed result file's lines up to its first dated note (the notes are not output)."""
    return (SCRIPTS / name).read_text().split("\n\n  NOTE ADDED")[0].split("\n")


@pytest.fixture(scope="module")
def step2(tmp_path_factory: pytest.TempPathFactory) -> list[str]:
    return _run(tmp_path_factory.mktemp("step2"), "odisha_phase1_2_analyse.py",
                "odisha_plots_sampled.csv", "odisha_phase1_results.txt")


@pytest.fixture(scope="module")
def closeout(tmp_path_factory: pytest.TempPathFactory) -> list[str]:
    return _run(tmp_path_factory.mktemp("closeout"), "odisha_phase1_6_closeout.py",
                "odisha_plots_sampled_v2.csv", "odisha_phase1_closeout.txt")


# --------------------------------------------------------------------------- step 2


def _tests(lines: list[str]) -> dict[int, list[str]]:
    """Step 2's lines by test, each from its 'TEST n' heading to the next one."""
    starts = [i for i, s in enumerate(lines) if s.startswith("TEST ")]
    assert [lines[i][:6] for i in starts] == ["TEST 1", "TEST 2", "TEST 3"]
    ends = [*starts[1:], len(lines)]
    return {n: lines[a:b] for n, a, b in zip((1, 2, 3), starts, ends, strict=True)}


def _fits(lines: list[str]) -> list[str]:
    """The lines that print a fit (n, r, R2, slope); a skipped fit prints none of them."""
    return [s for s in lines if " r=" in s and " R2=" in s]


def test_step2_prints_rmse_and_bias_only_where_both_sides_are_heights_in_metres(step2):
    tests = _tests(step2)
    test1 = _fits(tests[1])
    assert len(test1) == 7  # Lorey's height (all plots and four districts), top-5, mean height
    assert [s for s in test1 if "RMSE=" not in s or "bias(pred-field)=" not in s] == []
    # Test 2 (amplitude against a Sal fraction) and Test 3 (roughness in m against cover in %)
    assert len(_fits(tests[2])) == 3 and len(_fits(tests[3])) == 5
    assert [s for s in tests[2] + tests[3] if "RMSE" in s or "bias" in s] == []


def test_step2_changes_no_other_line(step2):
    first = _as_first_written("odisha_phase1_results.txt")
    test2 = next(i for i, s in enumerate(first) if s.startswith("TEST 2"))
    expected = [s.split("  RMSE=")[0] if i > test2 else s for i, s in enumerate(first)]
    assert sum(a != b for a, b in zip(first, expected, strict=True)) == 8
    assert step2 == expected


def test_step2_writes_the_committed_r14_file(step2):
    # odisha_phase1_results_r14.txt is this script's output, saved under its round 14 name
    assert step2 == (SCRIPTS / "odisha_phase1_results_r14.txt").read_text().split("\n")


# --------------------------------------------------------------------------- step 6


def _ab(lines: list[str]) -> dict[str, str]:
    """Section A/B's fit lines (field Lorey's height against each candidate), by candidate."""
    return {s.split()[0]: s for s in lines
            if "pearson r=" in s and not s.startswith("  site-level")}


def test_closeout_prints_a_bias_only_where_both_sides_are_heights_in_metres(closeout):
    ab = _ab(closeout)
    assert sorted(ab) == sorted(METRES + RADAR_DB)
    assert [ab[c] for c in METRES if "   bias=" not in ab[c]] == []
    assert [ab[c] for c in RADAR_DB if "bias" in ab[c]] == []


def test_closeout_changes_no_other_line_of_section_ab(closeout):
    # The committed file as first written up to its round 11 note: section A/B, with the Read lines.
    first = _as_first_written("odisha_phase1_closeout.txt")
    assert _ab(first).keys() == _ab(closeout).keys()
    expected = [s.split("   bias=")[0] if s.split()[:1] in (["vh_iqr"], ["vv_iqr"]) else s
                for s in first]
    assert sum(a != b for a, b in zip(first, expected, strict=True)) == 2
    assert closeout[:len(first)] == expected
    # section C follows at once, as before (it calls no fit that prints a bias)
    assert closeout[len(first)] == "" and closeout[len(first) + 1] == "=" * 96


def test_closeout_writes_the_committed_r14_file(closeout):
    # odisha_phase1_closeout_r14.txt is this script's output, saved under its round 14 name
    assert closeout == (SCRIPTS / "odisha_phase1_closeout_r14.txt").read_text().split("\n")

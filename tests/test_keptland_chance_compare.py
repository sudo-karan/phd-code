"""odisha_script/odisha_keptland_chance_compare.py, offline: chance test results set beside set.

Two small result files in the chance script's shape are written to a temporary folder; the
comparison must give each set's observed value, chance median, percentile and Holm p per score,
count the passes, give C1 its own p, and never write over a file.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "odisha_script"))

import odisha_keptland_chance_compare as X  # noqa: E402, N812


def _row(obs, med, pct, p, holm=None, passes=None):
    r = {"observed": obs, "null_median": med, "null_p5": med - 0.01, "null_p95": med + 0.01, "pctile": pct,
         "p": p, "n_null": 1999}
    if holm is not None:
        r.update(holm_p=holm, passes=passes)
    return r


def _result(shift: float, rehearsal: bool, runs: list[str], seed: str) -> dict:
    def analysis():
        scores = {k: _row(0.01 + shift, 0.005, 90.0, 0.04, 0.2, False) for k, _ in X.STATS}
        scores["prec"] = _row(0.6 + shift, 0.5, 99.9, 0.001, 0.005, True)
        return {"what": "an analysis", "scores": scores, "plots_scored_observed": 264,
                "districts_in_labelling_mean": {"observed": 4, "realisations_by_count": {"3": 11, "4": 1988}}}

    return {"rehearsal": rehearsal, "runs": runs, "rotations": 1999, "arm_seed_name": seed, "null_built": True,
            "analyses": {a: analysis() for a in X.ANALYSES},
            "checks": {"C1": {**_row(0.03, 0.04, 30.0, 0.7), "plots_scored_observed": 257}}}


@pytest.fixture
def two_sets(tmp_path):
    (tmp_path / "hc.json").write_text(json.dumps(_result(0.0, False, ["hc_a", "hc_b"], "v120_arm")))
    (tmp_path / "ae.json").write_text(json.dumps(_result(0.1, False, ["ae_a", "ae_b"], "ae_arm")))
    args = ["--set", "hand-crafted=hc", "--set", "AlphaEarth=ae", "--scores-dir", str(tmp_path),
            "--out", str(tmp_path / "out.md")]
    return tmp_path, args


def test_each_score_side_by_side_with_its_holm_p(two_sets):
    tmp_path, args = two_sets
    assert X.main(args) == 0
    text = (tmp_path / "out.md").read_text()
    assert ("| 3 drawing: same-stand pair precision | +0.6000 | +0.5000 | 99.9 | 0.005 (passes) | "
            "+0.7000 | +0.5000 | 99.9 | 0.005 (passes) |") in text
    assert "| 1 drawing: ARI, all plots | +0.0100 | +0.0050 | 90.0 | 0.200 | +0.1100 | +0.0050 | 90.0 | 0.200 |" in text
    assert "Tests that pass after Holm: hand-crafted 1 of 5; AlphaEarth 1 of 5." in text
    assert text.count("## primary") == 1 and "## S1" in text and "## S2" in text


def test_c1_has_its_own_p_and_each_set_says_what_it_ran_on(two_sets):
    tmp_path, args = two_sets
    X.main(args)
    text = (tmp_path / "out.md").read_text()
    assert "| C1: labelling ARI, district mean, Kendujhar left out | +0.0300 | +0.0400 | 30.0 | 0.700 |" in text
    assert "| AlphaEarth | `ae_a`, `ae_b` | declared | 1999 | `ae_arm` | yes | 264, 257 | 11 |" in text


def test_it_never_writes_over_an_old_file_and_wants_label_and_stem(two_sets):
    tmp_path, args = two_sets
    (tmp_path / "out.md").write_text("old")
    with pytest.raises(SystemExit, match="exists"):
        X.main(args)
    assert (tmp_path / "out.md").read_text() == "old"
    with pytest.raises(SystemExit):
        X.main(["--set", "no-stem", "--out", str(tmp_path / "x.md")])

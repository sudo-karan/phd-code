"""odisha_script/odisha_keptland_compare.py, offline: old and new kept-land results side by side.

Two small scores files and run records are written to a temporary folder; the comparison must
give each score's old and new value and their difference, the stand counts from the records,
and refuse to write over a file that exists. No real run is read.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "odisha_script"))

import odisha_keptland_compare as C  # noqa: E402, N812

DISTRICTS = C.DISTRICTS


def _scores(shift: float, plots: int, runs: str) -> dict:
    def analysis(name: str) -> dict:
        return {"analysis": name, "delin_all": 0.10 + shift, "delin_multi": 0.20 + shift, "prec": 0.50,
                "lab_wmean": 0.04 + shift, "far_gap": float("nan") if name == "S2" else -0.01,
                "counts": {"plots": plots},
                "labelling_by_district": {d.upper(): {"n": 10, "ari": 0.1 + shift} for d in DISTRICTS}}

    join = {d: {"inside_the_boxes": 10, "on_a_stand": 9, "by_the_30_m_rule": 1, "left_out": 0}
            for d in (*DISTRICTS, "all")}
    return {"analyses": [analysis("primary"), analysis("S2")], "join": join,
            "inputs_sha256": {runs.format(district=d): f"{d}-sha" for d in DISTRICTS}}


def _record(folder: Path, run: str, stands: int) -> None:
    folder.mkdir(exist_ok=True)
    (folder / f"{run}_run.json").write_text(json.dumps({
        "merge_diagnostics": {"n_superpixels": 5 * stands, "n_stands": stands, "stands_below_min_area": 3},
        "export_vector_layers": {"stands_merged": {"n_features": stands + 1, "n_stands": stands},
                                 "stands_snic": {"n_features": 5 * stands + 2},
                                 "stands_dissolved": {"n_features": stands // 4}},
    }))


@pytest.fixture
def two_sets(tmp_path, monkeypatch):
    old_runs, new_runs = "run_{district}", "run_{district}_r9"
    monkeypatch.setattr(C, "SCORES", tmp_path)
    (tmp_path / "old_scores.json").write_text(json.dumps(_scores(0.0, 264, old_runs)))
    (tmp_path / "new_scores.json").write_text(json.dumps(_scores(0.05, 265, new_runs)))
    for d in DISTRICTS:
        _record(tmp_path / "old", old_runs.format(district=d), 100)
        _record(tmp_path / "new", new_runs.format(district=d), 120)
    args = ["--old-stem", "old", "--new-stem", "new", "--old-runs", old_runs, "--new-runs", new_runs,
            "--old-records", str(tmp_path / "old"), "--new-records", str(tmp_path / "new"),
            "--out", str(tmp_path / "out.md")]
    return tmp_path, args


def test_each_score_old_new_and_the_difference(two_sets):
    tmp_path, args = two_sets
    assert C.main(args) == 0
    text = (tmp_path / "out.md").read_text()
    assert "| primary | 1 drawing: ARI, all plots | +0.1000 | +0.1500 | +0.0500 |" in text
    assert "| primary | 3 drawing: same-stand pair precision | +0.5000 | +0.5000 | +0.0000 |" in text
    assert "| S2 | 5 labelling: far-apart gap | n/a | n/a | n/a |" in text
    assert "| primary | plots scored | 264 | 265 | +1 |" in text


def test_the_stand_counts_come_from_the_run_records(two_sets):
    tmp_path, args = two_sets
    C.main(args)
    text = (tmp_path / "out.md").read_text()
    assert "| angul | 500, 600 | 100, 120 | 101, 121 | 3, 3 | 502, 602 | 25, 30 |" in text
    assert "| `run_koraput_r9` | `koraput-sha` |" in text


def test_it_never_writes_over_an_old_file(two_sets):
    tmp_path, args = two_sets
    (tmp_path / "out.md").write_text("an old comparison")
    with pytest.raises(SystemExit, match="exists"):
        C.main(args)
    assert (tmp_path / "out.md").read_text() == "an old comparison"


def test_a_pair_adds_the_stand_counts_of_a_run_that_is_not_scored(two_sets):
    tmp_path, args = two_sets
    _record(tmp_path / "old", "sanjay", 40)
    _record(tmp_path / "new", "sanjay_r9", 44)
    C.main([*args, "--pair", "sanjay", "sanjay_r9"])
    text = (tmp_path / "out.md").read_text()
    assert "| sanjay | 200, 220 | 40, 44 | 41, 45 | 3, 3 | 202, 222 | 10, 11 |" in text


def test_the_difference_column_takes_a_label(two_sets):
    tmp_path, args = two_sets
    C.main([*args, "--diff-label", "AlphaEarth minus hand-crafted"])
    text = (tmp_path / "out.md").read_text()
    assert "| Analysis | Score | old | new | AlphaEarth minus hand-crafted |" in text
    assert "new minus old" not in text


def test_the_plots_one_side_scores_and_the_other_does_not_are_named(two_sets):
    tmp_path, args = two_sets
    header = "plot_key,district,how\n"
    (tmp_path / "old_joined.csv").write_text(header + "p1,ANGUL,covered\np2,ANGUL,within\np3,KORAPUT,none\n")
    (tmp_path / "new_joined.csv").write_text(header + "p1,ANGUL,covered\np2,ANGUL,none\np3,KORAPUT,covered\n")
    C.main([*args, "--plots"])
    text = (tmp_path / "out.md").read_text()
    assert "- scored (the join with the 30 m rule): 2 (old), 2 (new), 1 in both." in text
    assert "  - only old: ANGUL 1: p2" in text
    assert "  - only new: KORAPUT 1: p3" in text
    assert "- covered by a stand (no 30 m rule): 1 (old), 2 (new), 1 in both." in text


def test_without_the_plots_option_no_plot_is_read(two_sets):
    tmp_path, args = two_sets
    C.main(args)
    assert "The plots each side scores" not in (tmp_path / "out.md").read_text()

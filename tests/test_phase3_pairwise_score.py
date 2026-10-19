"""odisha_script/odisha_phase3_1_pairwise_score.py: what the score file says about chance.

Offline: the scorer is run on the committed plot table into a temporary folder; nothing
committed is written.

Review finding C1 (19 Oct 2026): the scorer printed a fixed chance band, "~0.005-0.022 on
delineation and ~0.04-0.06 on labelling", into every score file. The committed chance tests
(odisha_phase3_3_results*.txt) put the labelling null median at 0.0665-0.0682 for the 3 ha
stands and 0.0288-0.0368 for the 10 ha stands, and the delineation null medians at
0.0036-0.0097 (all plots) and 0.0168-0.0228 (multi-plot stands): the band is wrong for both
arms. The scorer runs no null, so it cannot know the chance level; the file says where it is
measured instead.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCORER = REPO / "odisha_script" / "odisha_phase3_1_pairwise_score.py"


def _score(tmp_path: Path, *args: str) -> str:
    got = subprocess.run([sys.executable, str(SCORER), *args, "--out-dir", str(tmp_path)],
                         cwd=REPO, capture_output=True, text=True, check=False)
    assert got.returncode == 0, got.stderr
    (out,) = tmp_path.glob("odisha_phase3_1_score_*.txt")
    return out.read_text()


def test_the_score_file_states_no_chance_level_it_did_not_measure(tmp_path: Path):
    text = _score(tmp_path, "--arm", "v120")
    head = text.split("A. DELINEATION")[0]
    assert "READ ARI AGAINST ITS CHANCE LEVEL, NOT AGAINST ZERO" in head
    assert "odisha_phase3_3_significance.py" in head          # where the chance level is measured
    assert not re.search(r"~\s*\d", head), head                # no fixed band of chance values

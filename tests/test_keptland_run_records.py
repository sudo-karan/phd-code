"""The run records of the kept-land scorer and chance test, offline: what each one says about the run.

odisha_script/odisha_keptland_score.py writes <stem>_scores_run.json and
odisha_script/odisha_keptland_chance.py writes <stem>_run.json beside their results (review of
19 Oct 2026, C37).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "odisha_script"))
sys.path.insert(0, str(REPO / "scripts"))

pytest.importorskip("shapely")
import odisha_keptland_chance as C  # noqa: E402, N812
import odisha_keptland_score as K  # noqa: E402, N812

ENVIRONMENT_KEYS = {"python", "earthengine_api", "pip_freeze_sha256", "pip_freeze_packages",
                    "pip_freeze_left_out", "error"}


def _record(script: str, out_dir: Path) -> dict:
    if script == "score":
        K.write_run_record(out_dir, ["--stem", "keptland_x"], "keptland_x")
        return json.loads((out_dir / "keptland_x_scores_run.json").read_text())
    C.write_run_record(out_dir, "keptland_x_chance", ["--declared"])
    return json.loads((out_dir / "keptland_x_chance_run.json").read_text())


@pytest.mark.parametrize("script", ["score", "chance"])
def test_the_run_record_names_the_python_environment(tmp_path, script):
    """Review C37: the records held the command, the date and the git state, but no pip-freeze
    hash: the rotation null draws from a seeded numpy Generator and places plots with shapely, so
    which versions ran is part of what the result rests on. They now carry the environment block
    of the pipeline's manifests (fmu.utils.provenance.environment_state)."""
    from fmu.utils.provenance import environment_state

    record = _record(script, tmp_path)
    assert set(record["environment"]) == ENVIRONMENT_KEYS
    assert record["environment"] == environment_state()

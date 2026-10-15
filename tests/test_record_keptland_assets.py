"""scripts/record_keptland_assets.py, offline: the record of the round-6 box kept-land runs' assets.

The record docs/reproducibility/keptland_boxes_assets.json is the source list of round 7's reuse
plan (scripts/reuse_upstream_assets.py). It is built from committed files only, so it is checked
here against them: the committed record is what the script builds today, every asset is at the
cache layout's path under its run's own fingerprint, and those fingerprints are the round-6 pins.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "record_keptland_assets.py"
RECORD = REPO / "docs" / "reproducibility" / "keptland_boxes_assets.json"


def _load():
    spec = importlib.util.spec_from_file_location("record_keptland_assets", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_committed_record_is_what_the_script_builds():
    assert json.loads(RECORD.read_text()) == _load().build()


def test_every_asset_is_at_its_runs_cache_path():
    from test_keptland_configs import PINNED

    rec = json.loads(RECORD.read_text())
    assert rec["n_assets"] == sum(len(r["assets"]) for r in rec["runs"]) == 52
    for run in rec["runs"]:
        name = run["run_id"]
        assert run["fingerprint"] == PINNED[name]
        assert len(run["assets"]) == 13, name  # masking 4, data_load 1, features 4, SNIC 2, k-means 2
        for a in run["assets"]:
            assert a["asset"] == (f"{rec['asset_root']}/{name}/{a['stage']}/{a['key']}__"
                                  f"{run['fingerprint']}")
        # Copied in round 6 from the box runs, or computed by the run itself.
        how = {a["stage"]: a["how"] for a in run["assets"]}
        assert how["features_static"].startswith("computed") and how["masking"].startswith("copied")

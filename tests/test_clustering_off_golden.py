"""With clustering.fit_excludes_stands_below_min_area off, clustering does what it always did.

Every run saved so far took the default path, so the setting must leave that path exactly
as it was. tests/data/clustering_off_calls.json holds, for three shipped configs (the
hand-crafted baseline, a 3 ha box config, and an AlphaEarth config), what
`ClusteringStage.run()` does on the stand-ins of tests/_clustering_stand_ins.py: every
Earth Engine call as recorded by tests/_ee_recorder.py (name, arguments and keyword
arguments, in order) and every request it sends with the context it names (and, until
review B14, its call of `assert_components_fit`); the clustering_metadata it writes on
cluster_labels; and its stage metadata. The file was written from the stage as it was
before the setting existed (commit 12d2a05):

    git show 12d2a05:src/fmu/stages/clustering.py > /tmp/clustering_12d2a05.py
    python tests/test_clustering_off_golden.py --write /tmp/clustering_12d2a05.py

and the stage of today must reproduce the calls and the clustering_metadata exactly. Its
stage metadata gains one key, fit_excludes_stands_below_min_area, false, and nothing else.
A deliberate change to the default path rewrites the file the same way, from the new
code, in the commit that makes it (`--write src/fmu/stages/clustering.py`), still without
that key in the stage metadata. Rewritten so in round 13 by review A5 (a flat cell's aspect
pair is (0, 0): the calls of the two hand-crafted configs changed), B13 (a phase's sin and
cos are not tested for skew: the same two configs ask two skews fewer), B14 (one mean per
unit label, with no reduceConnectedComponents, from grouped sums of the bands unmasked over
their pixels with data: the calls of all three configs changed, and their stage metadata lost
the five keys that described its maxSize) and B16 (each band's column is read back for exact
quartiles, in place of Earth Engine's percentiles: the calls of all three configs). Rewritten
in round 14 by round 13's question 35 (the units without a row counted by cause: each config
makes one more request, an unweighted histogram of the habitat-masked unit labels, eight
recorded calls inserted after the habitat histogram, and its clustering_metadata gains
n_units_no_pixel_centre_in_roi, 1 on the stand-ins, while n_units_dropped_null_band goes from
2 to 1; nothing else in the file changed).
"""

from __future__ import annotations

import functools
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
GOLDEN = HERE / "data" / "clustering_off_calls.json"
CONFIGS = (
    "configs/sanjay_van_baseline.yaml",
    "configs/odisha_v120_3ha_squares_koraput.yaml",
    "configs/odisha_alphaearth_angul_repro.yaml",
)

sys.path.insert(0, str(HERE))
from _clustering_stand_ins import run_stage  # noqa: E402
from _ee_recorder import call_log  # noqa: E402


def record(module: ModuleType, config_path: str) -> dict[str, Any]:
    """What `module.ClusteringStage().run()` does for a config, setting off."""
    from fmu.config import load_config

    config = load_config(REPO / config_path)
    assert not config.clustering.fit_excludes_stands_below_min_area
    result, log, _ = run_stage(module, config)
    (stamp,) = [c for c in log if c.attr == "set" and c.args[:1] == ("clustering_metadata",)]
    return {
        "calls": call_log(log),
        "clustering_metadata": json.loads(stamp.args[1]),
        "stage_metadata": result.metadata,
    }


@functools.cache
def _today(config_path: str) -> dict[str, Any]:
    import fmu.stages.clustering as clustering

    return record(clustering, config_path)


@functools.cache
def _golden() -> dict[str, Any]:
    return json.loads(GOLDEN.read_text())


def test_the_file_holds_the_three_configs():
    assert sorted(_golden()) == sorted(CONFIGS)


@pytest.mark.parametrize("config_path", CONFIGS)
def test_the_default_path_makes_the_calls_it_made_before(config_path: str):
    assert _today(config_path)["calls"] == _golden()[config_path]["calls"]


@pytest.mark.parametrize("config_path", CONFIGS)
def test_the_default_path_writes_the_clustering_metadata_it_wrote_before(config_path: str):
    """Key for key and value for value: the summary numbers are read from it on cached
    assets."""
    assert _today(config_path)["clustering_metadata"] == _golden()[config_path]["clustering_metadata"]


@pytest.mark.parametrize("config_path", CONFIGS)
def test_the_stage_metadata_gains_the_setting_and_nothing_else(config_path: str):
    assert _today(config_path)["stage_metadata"] == {
        **_golden()[config_path]["stage_metadata"],
        "fit_excludes_stands_below_min_area": False,
    }


def test_the_recording_reaches_the_branches_of_the_default_path():
    """A recording that skipped a branch would not guard it. Every config has skewed
    bands, a band with no spread and units in habitat without a row, and takes the unit
    means; the hand-crafted ones drop bands and decompose cyclic ones."""
    for config_path in CONFIGS:
        meta = _golden()[config_path]["clustering_metadata"]
        assert meta["log_transformed_bands"] and meta["log_offsets"], config_path
        assert meta["dropped_constant_bands"], config_path
        assert meta["n_units_dropped_null_band"] > 0, config_path
        names = [name for name, _, _ in _golden()[config_path]["calls"]]
        assert names.count("getInfo") > 10, config_path
        assert "ee.Reducer.sum().unweighted().forEachBand().group" in names, config_path
    for config_path in CONFIGS[:2]:
        meta = _golden()[config_path]["clustering_metadata"]
        assert meta["cyclic_decomposition_log"] == ["ndvi_phase_annual", "aspect"], config_path
        assert len(meta["raw_band_names"]) == 20, config_path


def _load_other(path: Path) -> ModuleType:
    """Load another copy of the clustering module without registering its stage twice."""
    import fmu.stages.base as base

    real = base.register_stage
    base.register_stage = lambda name: (lambda cls: cls)  # type: ignore[assignment]
    try:
        spec = importlib.util.spec_from_file_location("clustering_other", path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        base.register_stage = real  # type: ignore[assignment]
    return module


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "--write":
        raise SystemExit(__doc__)
    sys.path.insert(0, str(REPO / "src"))
    other = _load_other(Path(sys.argv[2]))
    recorded = {c: record(other, c) for c in CONFIGS}
    # As the file was first written, before the setting existed: the test adds the key.
    for entry in recorded.values():
        entry["stage_metadata"].pop("fit_excludes_stands_below_min_area", None)
    GOLDEN.write_text(json.dumps(recorded, indent=0, sort_keys=True) + "\n")
    print(f"wrote {GOLDEN}")

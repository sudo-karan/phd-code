"""scripts/alphaearth_stand_means.py, offline: what it reduces, and the file it writes.

Earth Engine is replaced by a stand-in reduction; the plan is built from the committed records.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "alphaearth_stand_means.py"


@pytest.fixture(scope="module")
def mod():
    spec = importlib.util.spec_from_file_location("alphaearth_stand_means", SCRIPT)
    assert spec is not None and spec.loader is not None
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_the_plan_takes_four_images_by_path_from_the_copy_record(mod):
    p = mod.plan()
    got = [(i["run"], i["stage"]) for i in p["images"]]
    assert got == [("sanjay_van_alphaearth_keptland", "features_optical"),
                   ("sanjay_van_alphaearth_keptland", "features_structure"),
                   ("sanjay_van_baseline_keptland", "features_radar"),
                   ("sanjay_van_baseline_keptland", "features_static")]
    for i in p["images"]:
        assert i["asset"].startswith(f"projects/replicating-paper/assets/fmu/{i['run']}/{i['stage']}/")
    assert p["n_polygons"] == 559 and p["scale_m"] == 10


def _fake(p, drop=None):
    layer = json.loads((REPO / p["stand_layer"]).read_text())["features"]
    bands = {p["images"][0]["asset"]: ["ndvi_mean"], p["images"][1]["asset"]: ["canopy_height"],
             p["images"][2]["asset"]: ["vv_minus_vh_median"], p["images"][3]["asset"]: ["elevation"]}
    feats = [{"properties": {"stand_id": f["properties"]["stand_id"],
                             "stand_lbl": f["properties"]["stand_lbl"], "ndvi_mean": 0.5,
                             "canopy_height": 7.0, "vv_minus_vh_median": 6.0, "elevation": 220.0}}
             for f in layer if f["properties"]["stand_id"] != drop]
    return bands, feats


def test_the_result_says_whose_means_and_keeps_the_layers_order(mod, tmp_path, monkeypatch):
    out = tmp_path / "means.json"
    monkeypatch.setattr(mod, "write_run_record", lambda *a, **k: None)
    assert mod.main(["--out", str(out)], reducer=_fake) == 0
    res = json.loads(out.read_text())
    assert "baseline kept-land run's (sanjay_van_baseline_keptland)" in res["note"]
    assert res["bands"]["vv_minus_vh_median"]["run"] == "sanjay_van_baseline_keptland"
    assert res["bands"]["canopy_height"]["run"] == "sanjay_van_alphaearth_keptland"
    layer = json.loads((REPO / mod.plan()["stand_layer"]).read_text())["features"]
    assert [s["stand_id"] for s in res["stands"]] == [f["properties"]["stand_id"] for f in layer]
    assert res["stands"][0]["elevation"] == 220.0 and res["n_polygons"] == 559
    assert "date" not in json.dumps(res)  # results only


def test_it_refuses_a_read_back_without_every_polygon(mod, tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "write_run_record", lambda *a, **k: None)
    first = json.loads((REPO / mod.plan()["stand_layer"]).read_text())["features"][0]
    with pytest.raises(SystemExit, match="not the stand layer's"):
        mod.main(["--out", str(tmp_path / "m.json")],
                 reducer=lambda p: _fake(p, drop=first["properties"]["stand_id"]))


def test_the_plan_alone_makes_no_earth_engine_call(mod, capsys):
    def boom(p):
        raise AssertionError("Earth Engine called")

    assert mod.main(["--plan"], reducer=boom) == 0
    assert "plan only: no Earth Engine call" in capsys.readouterr().out

"""odisha_script/odisha_keptland_chance.py, offline: the rehearsal of the kept-land chance test.

The null's join (vectorised) is checked against the declared join of odisha_keptland_score on the
scorer test's own edge cases; the polyline decoder against the explorer's encoder; Holm against
hand-worked values; the draws (every plot inside its box, no plot forced onto a stand, seeded, an
unplaceable box reported); and one short run end to end on the committed inputs, whose identity
checks must pass.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "odisha_script"))
sys.path.insert(0, str(REPO / "scripts"))

pytest.importorskip("shapely")
import odisha_keptland_chance as C  # noqa: E402, N812
import odisha_keptland_score as K  # noqa: E402, N812
import shapely  # noqa: E402
from shapely.geometry import box, shape  # noqa: E402

EPSG = 32645


def sq(x0, x1, y0=21.0, y1=21.001):
    return {"type": "Polygon", "coordinates": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]}


def write_layer(tmp_path: Path, feats: list[tuple[int, float, dict]]) -> Path:
    fc = {"type": "FeatureCollection",
          "features": [{"type": "Feature", "geometry": g, "properties": {"stand_lbl": s, "cluster_id": c, "area_ha": 1.0}}
                       for s, c, g in feats]}
    path = tmp_path / "layer.geojson"
    path.write_text(json.dumps(fc))
    return path


def as_layer(path: Path) -> C.Layer:
    rows = [{"sid": int(f["properties"]["stand_lbl"]), "cluster": float(np.rint(f["properties"]["cluster_id"])),
             "geom_ll": shape(f["geometry"])} for f in json.loads(path.read_text())["features"]]
    st = pd.DataFrame(rows)
    code = {("d", s): float(s) for s in st.sid}          # key = stand id, so the lowest key is the lowest id
    return C.Layer(st, "d", EPSG, code, typed_only=False)


LAYERS = {
    "overlap": [(2, 1.0, sq(85.0, 85.001)), (1, 4.0, sq(85.0008, 85.002)), (7, 2.0, sq(85.0030, 85.004))],
    "tie": [(2, 1.0, sq(85.0, 85.001)), (1, 4.0, sq(85.0008, 85.002)), (7, 2.0, sq(85.00219, 85.003))],
    "pieces": [(5, 1.0, sq(85.0, 85.001)), (5, 3.0, sq(85.003, 85.004))],
}
POINTS = [(85.0005, 21.0005), (85.0009, 21.0005), (85.0021, 21.0005), (85.0025, 21.0005), (85.0100, 21.0005),
          ((85.002 + 85.00219) / 2, 21.0005), (85.0041, 21.0005), (85.0020, 21.0010), (85.0015, 21.00125)]


@pytest.mark.parametrize("name", list(LAYERS))
def test_the_nulls_join_is_the_declared_join(tmp_path, name):
    path = write_layer(tmp_path, LAYERS[name])
    plots = pd.DataFrame([{"plot_key": f"p{i}", "lon6": lo, "lat6": la, "epsg": EPSG}
                          for i, (lo, la) in enumerate(POINTS)])
    ref = K.join(plots, path, K.REACH_M).set_index("plot_key").loc[plots.plot_key]
    fwd = C.utm_transformers_epsg(EPSG)
    xy = np.column_stack(fwd(plots.lon6.to_numpy(), plots.lat6.to_numpy()))
    key, cl, dist = C.assign(xy, as_layer(path))
    assert np.array_equal(key, ref.sid.to_numpy(float), equal_nan=True)
    assert np.array_equal(cl, ref.cluster.to_numpy(float), equal_nan=True)
    how = np.where(~np.isfinite(key), "none", np.where(dist == 0, "covered", "within"))
    assert list(how) == list(ref.how)
    within = ref.how.to_numpy() != "none"
    assert np.allclose(dist[within], ref.dist_m.to_numpy()[within], atol=1e-9)


def test_reach_is_inclusive_and_beyond_it_a_plot_is_left_out(tmp_path):
    lay = as_layer(write_layer(tmp_path, [(3, 2.0, sq(85.0, 85.001))]))
    # The easternmost vertex: no point of the polygon lies further east, so a point due east of it
    # at 30 m - 1 um is within reach (its distance to that vertex) and one at 30 m + 1 mm is not.
    c = shapely.get_coordinates(lay.geoms[0])
    ex, ey = c[np.argmax(c[:, 0])]
    xy = np.array([[ex + 30.0 - 1e-6, ey], [ex + 30.0 + 1e-3, ey]])
    key, _, dist = C.assign(xy, lay)
    assert key[0] == 3 and dist[0] <= 30.0
    assert math.isnan(key[1]) and math.isinf(dist[1])


def test_polyline6_round_trip():
    import build_ui_early_data as B  # noqa: N812
    ring = [[85.123456, 21.654321], [85.123999, 21.654321], [85.124, 21.655], [85.123456, 21.654321]]
    assert C.decode_polyline6(B.polyline6(ring)) == ring
    neg = [[-0.000001, -12.5], [179.999999, 89.0]]
    assert C.decode_polyline6(B.polyline6(neg)) == neg


def test_holm():
    assert C.holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])
    assert C.holm([0.5, 0.001, 0.2, 0.2, 0.9]) == pytest.approx([1.0, 0.005, 0.8, 0.8, 1.0])
    assert C.holm([0.3]) == [0.3]


def _toy(tmp_path: Path, n_plots: int = 6, stand_cover: float = 0.5):
    """One 2 km box in metres (UTM 45N near 85 E), stands covering its west part only."""
    x0, y0 = 500_000.0, 2_320_000.0
    part = {"district": "d", "k": 0, "epsg": EPSG, "name": "toy:BOX", "geom": box(x0, y0, x0 + 2000, y0 + 2000)}
    shapely.prepare(part["geom"])
    rng = np.random.default_rng(0)
    xy = np.column_stack([x0 + 800 + rng.uniform(0, 400, n_plots), y0 + 800 + rng.uniform(0, 400, n_plots)])
    plots = pd.DataFrame({"x": xy[:, 0], "y": xy[:, 1], "aoi_part": 0})
    stand = box(x0, y0, x0 + 2000 * stand_cover, y0 + 2000)

    class L:
        geoms = np.array([stand])
        tree = shapely.STRtree(geoms)
        key = np.array([0.0])
        cluster = np.array([1.0])
    shapely.prepare(L.geoms)
    return plots, [part], {0: L}


def test_draws_keep_every_plot_in_its_box_and_force_none_onto_a_stand(tmp_path):
    plots, parts, layers = _toy(tmp_path)
    out = C.draw_null(plots, parts, layers, 200, np.random.default_rng(1), "toy")
    assert not out["failures"]
    landed = np.isfinite(out["key"])
    # the stand covers half the box: many realisations leave some plots off it, which the rule allows
    assert 0.1 < landed.mean() < 0.9
    assert (~landed).any(axis=1).sum() > 20
    assert np.isfinite(out["moved"]).all() and (out["moved"] > 0).all()
    # seeded: the same stream gives the same realisations
    again = C.draw_null(plots, parts, layers, 200, np.random.default_rng(1), "toy")
    assert np.array_equal(out["key"], again["key"], equal_nan=True)


def test_an_unplaceable_box_makes_the_null_unbuilt(tmp_path):
    plots, parts, layers = _toy(tmp_path)
    plots.loc[0, "x"] = parts[0]["geom"].bounds[0] - 5000.0   # cloud wider than the box: fits at no angle
    out = C.draw_null(plots, parts, layers, 50, np.random.default_rng(1), "toy", cap_scale=0.001)
    assert out["failures"] and out["failures"][0]["part"] == "toy:BOX"


def test_the_array_scores_are_the_scorers():
    rng = np.random.default_rng(3)
    n = 60
    plots = pd.DataFrame({"plot_key": [f"p{i}" for i in range(n)],
                          "box_district": rng.choice(["a", "b"], n),
                          "lon6": 85.0 + rng.uniform(0, 0.05, n), "lat6": 21.0 + rng.uniform(0, 0.05, n),
                          "field_type": rng.integers(0, 4, n)})
    sid = rng.integers(0, 15, n).astype(float)
    sid[rng.random(n) < 0.1] = np.nan
    cl = np.where(np.isfinite(sid), sid % 3, np.nan)
    key = np.array([s + (100 if d == "b" else 0) for s, d in zip(sid, plots.box_district, strict=True)])
    sc = C.Scoring(plots, plots.field_type.to_numpy(), np.isfinite(key))
    mine = sc.all(key, cl)
    theirs = K.five_scores(plots.rename(columns={"box_district": "district"}).assign(sid=sid, cluster=cl))
    for k, _ in K.STATS:
        assert math.isclose(mine[k], theirs[k], rel_tol=0, abs_tol=1e-12), k


def test_a_short_run_on_the_committed_inputs_passes_its_identity_checks(tmp_path):
    if not (C.UI_DATA / K.run_id("koraput") / "stands.json").exists():
        pytest.skip("ui_data not present")
    res = C.run(12, tmp_path)
    assert res["identity_checks"]["join_at_real_positions"] == "PASS"
    assert res["null_built"]
    txt = (tmp_path / "keptland_s1desc_chance_rehearsal_rot12.txt").read_text()
    assert "REHEARSAL" in txt and "NOT THE DECLARED TEST'S RESULT" in txt
    # with 12 realisations every test is below the 100 usable the percentile needs
    assert all(r["p"] is None for r in res["analyses"]["primary"]["scores"].values())
    assert not any("holm_p" in r for r in res["analyses"]["primary"]["scores"].values())
    assert res["rehearsal"] and all(k.startswith("stands:") for k in list(res["inputs_sha256"])[:4])
    # C1: the observed value is the plot-weighted mean of the three other districts' committed ARIs
    by = json.loads((C.SCORES_DIR / "keptland_s1desc_scores.json").read_text())["analyses"][0]["labelling_by_district"]
    rest = {d: v for d, v in by.items() if d != "KENDUJHAR"}
    want = sum(v["n"] * v["ari"] for v in rest.values()) / sum(v["n"] for v in rest.values())
    c1 = res["checks"]["C1"]
    assert math.isclose(c1["observed"], want, abs_tol=1e-12)
    assert c1["plots_scored_observed"] == sum(v["n"] for v in rest.values())
    assert "Check C1" in txt
    assert not (tmp_path / "keptland_s1desc_chance_rehearsal.txt").exists()


def test_the_geojson_route_gives_the_ui_data_stands():
    """Angul's merged layer is in git: read both ways, the same stands, types and shapes (to the
    1e-6 degree the explorer rounds to)."""
    run = K.run_id("angul")
    path = K.STANDS_DIR / f"{run}_stands_merged.geojson"
    if not path.exists() or not (C.UI_DATA / run / "stands.json").exists():
        pytest.skip("inputs not present")
    a = C.geojson_stands(path).sort_values("sid", kind="stable").reset_index(drop=True)
    b = C.ui_stands(C.UI_DATA / run / "stands.json").sort_values("sid", kind="stable").reset_index(drop=True)
    assert list(a.sid) == list(b.sid)
    assert np.array_equal(a.cluster.to_numpy(), b.cluster.to_numpy(), equal_nan=True)
    for ga, gb in zip(a.geom_ll, b.geom_ll, strict=True):
        assert ga.hausdorff_distance(gb) <= 1e-6        # each vertex moved by at most 0.5e-6 deg per axis


def test_re_run_stands_cannot_be_read_from_ui_data(tmp_path):
    with pytest.raises(SystemExit, match="geojson"):
        C.run(12, tmp_path, stands_from="ui_data", run_suffix="_r9")
    with pytest.raises(SystemExit, match="geojson"):
        C.run(12, tmp_path, declared=True)


def test_the_pre_fix_files_are_known_and_a_declared_run_refuses_them():
    pre = C.pre_fix_sha256()
    angul = K.STANDS_DIR / f"{K.run_id('angul')}_stands_merged.geojson"
    koraput_rec = K.STANDS_DIR / f"{K.run_id('koraput')}_files_off_git.json"
    if not angul.exists() or not koraput_rec.exists():
        pytest.skip("inputs not present")
    assert C.sha256(angul) in pre
    assert C.sha256(C.UI_DATA / K.run_id("koraput") / "stands.json") in pre
    off = {e["sha256"] for e in json.loads(koraput_rec.read_text())["files"] if e["file"].endswith("_merged.geojson")}
    assert off <= pre


def test_boxes_are_named_as_the_village_test_names_its_parts():
    parts = C.box_parts()
    C.load_plots(parts)
    names = {p["name"] for p in parts}
    # the habitation of the box would be dhenkanal:BALIKUMA; stats.load names it by the plots' site polygon
    assert "dhenkanal:Balikurma" in names and "dhenkanal:BALIKUMA" not in names
    assert len(names) == len(parts)


def test_output_stems():
    assert C.out_stem("keptland_s1desc", True, C.N_ROT) == "keptland_s1desc_chance_rehearsal"
    assert C.out_stem("keptland_s1desc_r9", False, C.N_ROT) == "keptland_s1desc_r9_chance"
    assert C.out_stem("keptland_s1desc", True, 120) == "keptland_s1desc_chance_rehearsal_rot120"

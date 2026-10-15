"""Offline checks of scripts/build_ui_early_data.py: the stand means it keeps, and the layers it
draws pixel by pixel for Sanjay Van (round 3's step 3, done in round 4)."""

from __future__ import annotations

import importlib
import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("rasterio")
pytest.importorskip("PIL")

import rasterio  # noqa: E402
from PIL import Image  # noqa: E402
from rasterio.transform import from_origin  # noqa: E402

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def builder(monkeypatch, tmp_path):
    """The script as a module, with its output and per-pixel folders under tmp_path. It reads
    its folders from sys.argv when imported, so the import sees no arguments."""
    monkeypatch.syspath_prepend(str(SCRIPTS))
    monkeypatch.setattr(sys, "argv", ["build_ui_early_data.py"])
    module = importlib.import_module("build_ui_early_data")
    monkeypatch.setattr(module, "OUT", tmp_path / "ui_data")
    monkeypatch.setattr(module, "PIXELS", tmp_path / "ui_data_full")
    return module


def _geotiff(path: Path, bands: dict[str, np.ndarray]) -> None:
    """A small EPSG:4326 GeoTIFF with named float32 bands, as scripts/fetch_ui_layers.py writes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    first = next(iter(bands.values()))
    with rasterio.open(path, "w", driver="GTiff", width=first.shape[1], height=first.shape[0],
                       count=len(bands), dtype="float32", crs="EPSG:4326", nodata=float("nan"),
                       transform=from_origin(77.0, 28.6, 0.0001, 0.0001)) as dst:
        for i, (name, data) in enumerate(bands.items(), 1):
            dst.write(data.astype("float32"), i)
            dst.set_band_description(i, name)


def _js_ramp(palette: list[str], t: float) -> list[int]:
    """`ramp` of ui/explorer.html, line for line."""
    x = min(1.0, max(0.0, t)) * (len(palette) - 1)
    i = min(len(palette) - 2, math.floor(x))
    f = x - i
    a = [int(palette[i][k:k + 2], 16) for k in (1, 3, 5)]
    b = [int(palette[i + 1][k:k + 2], 16) for k in (1, 3, 5)]
    return [math.floor(v + (w - v) * f + 0.5) for v, w in zip(a, b, strict=True)]


def test_every_feature_mean_is_kept_and_ids_and_provenance_are_not(builder):
    props = {"stand_id": 3, "stand_lbl": 3, "area_ha": 1.2, "cluster_id": 2, "n_pixels": 120,
             "centroid_lat": 28.5, "centroid_lon": 77.2, "perim_m": 500.0,
             "n_superpx": 2, "n_pass1": 1, "n_relaxed": 0, "n_fallback": 0, "below_min": 0,
             "below_why": "", "canopy_height": 7.25, "ndvi_trend": 0.000123456,
             "vh_p50": -19.87654}
    assert builder.feature_names(props) == ["canopy_height", "ndvi_trend", "vh_p50"]


def test_the_seven_first_kept_keep_their_decimals_and_the_rest_four_figures(builder):
    assert builder.feature_value("canopy_height", 7.25) == round(7.25, 1)
    assert builder.feature_value("elevation", 215.6) == 216.0
    assert builder.feature_value("ndvi_trend", 0.000123456) == 0.0001235
    assert builder.feature_value("vh_p50", -19.87654) == -19.88
    assert builder.feature_value("A07", 0.0412345) == 0.04123
    assert builder.feature_value("slope", None) is None
    assert builder.feature_value("vh_p50", float("nan")) is None


def test_the_colour_ramp_is_the_explorers(builder):
    palette = ["#f7fcf5", "#c7e9c0", "#74c476", "#238b45", "#00441b"]
    ts = np.array([-1.0, 0.0, 0.1, 0.25, 0.5, 0.6, 0.999, 1.0, 2.0])
    got = builder.ramp_rgb(palette, ts)
    assert got.tolist() == [_js_ramp(palette, float(t)) for t in ts]


def test_a_hand_crafted_run_gets_three_layers_pixel_by_pixel(builder, tmp_path):
    rng = np.random.default_rng(0)
    shape = (6, 5)
    bands = {name: rng.normal(size=shape) for name in
             ("B4_median", "B8_median", "canopy_height", "ndvi_amplitude_annual",
              "vv_minus_vh_median")}
    bands["canopy_height"][0, 0] = np.nan
    _geotiff(tmp_path / "ui_data_full" / "run_a" / "features_part01.tif", bands)

    layers = builder.pixel_feature_layers("run_a", "feature_vector")

    assert [layer["layer_id"] for layer in layers] == [
        "feature_canopy_height", "feature_ndvi_amplitude_annual", "feature_vv_minus_vh_median"]
    first = layers[0]
    assert first["kind"] == "raster" and first["smooth"] is False
    # No description: the explorer marks a colour-ramp layer with one as a stand average.
    assert "description" not in first
    valid = bands["canopy_height"][np.isfinite(bands["canopy_height"])]
    lo, hi = np.percentile(valid, [2, 98])
    assert first["colormap"]["min"] == round(float(lo), 3)
    assert first["colormap"]["max"] == round(float(hi), 3)
    (part,) = first["parts"]
    assert part["file"] == "by_run/run_a/feature_canopy_height_part01.png"
    assert part["bounds"] == [77.0, 28.5994, 77.0005, 28.6]
    rgba = np.asarray(Image.open(tmp_path / "ui_data" / part["file"]))
    assert rgba.shape == (*shape, 4)
    assert rgba[0, 0, 3] == 0 and (rgba[..., 3].ravel()[1:] == 255).all()


def test_an_alphaearth_run_gets_its_embedding_as_colour_pixel_by_pixel(builder, tmp_path):
    rng = np.random.default_rng(1)
    shape = (8, 7)
    bands = {f"A{i:02d}": rng.normal(size=shape) for i in range(64)}
    bands["A05"][3, 4] = np.nan
    _geotiff(tmp_path / "ui_data_full" / "run_b" / "embedding_part01.tif", bands)

    (layer,) = builder.pixel_feature_layers("run_b", "alphaearth")

    assert layer["layer_id"] == "embedding_rgb" and layer["kind"] == "raster"
    assert layer["color_is_value"] is True and "pixel" in layer["description"]
    path = tmp_path / "ui_data" / layer["parts"][0]["file"]
    first = path.read_bytes()
    rgba = np.asarray(Image.open(path))
    assert rgba.shape == (*shape, 4)
    assert rgba[3, 4, 3] == 0 and int((rgba[..., 3] == 255).sum()) == shape[0] * shape[1] - 1
    # The same data gives the same picture.
    builder.pixel_feature_layers("run_b", "alphaearth")
    assert path.read_bytes() == first


def test_a_run_without_geotiffs_gets_none(builder):
    assert builder.pixel_feature_layers("run_c", "feature_vector") is None


def test_the_committed_ui_data_draws_sanjay_van_pixel_by_pixel():
    index = json.loads((SCRIPTS.parent / "ui_data" / "index.json").read_text())
    by_id = {r["run_id"]: r for r in index["runs"]}
    for run_id in ("sanjay_van_baseline_repro", "sanjay_van_alphaearth_repro"):
        (step,) = [s for s in by_id[run_id]["steps"] if s["step"] == "features"]
        assert step["layers"] and all(layer["kind"] == "raster" for layer in step["layers"])
        for layer in step["layers"]:
            for part in layer["parts"]:
                assert (SCRIPTS.parent / "ui_data" / part["file"]).is_file()


# ---------------------------------------------------------------- the kept-land runs (round 5)

FILL = math.sqrt(2**31 - 1) * 10  # distance_to_water where no water lies within 10 km


def test_far_water_is_over_10_km_for_a_kept_land_run_only(builder):
    assert builder.feature_value("distance_to_water", FILL, far_water=True) == "over 10 km"
    assert builder.feature_value("distance_to_water", 9_999.0, far_water=True) == 9999.0
    assert builder.feature_value("distance_to_water", FILL) == float(f"{FILL:.4g}")
    assert builder.feature_value("elevation", FILL, far_water=True) == round(FILL, 0)
    assert builder.profile_value("distance_to_water", FILL) == "over 10 km"
    assert builder.profile_value("canopy_height", 7.123456) == 7.123


def _stands(tmp_path, run_id: str) -> Path:
    square = [[[77.0, 28.0], [77.001, 28.0], [77.001, 28.001], [77.0, 28.001], [77.0, 28.0]]]
    feats = []
    for sid, (below, dist) in enumerate([(0, 1234.5), (1, FILL)]):
        props = {"stand_id": sid, "stand_lbl": sid, "area_ha": 1.5 + sid, "cluster_id": sid,
                 "n_pixels": 150, "centroid_lat": 28.0, "centroid_lon": 77.0, "perim_m": 400.0,
                 "n_superpx": 2, "n_pass1": 1, "n_relaxed": 0, "n_fallback": 0,
                 "below_min": below, "below_why": "isolated" if below else "",
                 "canopy_height": 6.0, "distance_to_water": dist}
        feats.append({"type": "Feature", "properties": props,
                      "geometry": {"type": "Polygon", "coordinates": square}})
    path = tmp_path / f"{run_id}_stands_merged.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    return tmp_path


def test_a_kept_land_runs_stands_carry_the_below_min_flag_and_far_water(builder, tmp_path):
    vec = _stands(tmp_path, "k_run")
    fc, st = builder.run_stands("k_run", "feature_vector", vec, keptland=True)
    first, second = (f["properties"] for f in fc["features"])
    assert (first["below_min"], second["below_min"]) == (False, True)
    assert (first["distance_to_water"], second["distance_to_water"]) == (1234.0, "over 10 km")
    assert "n_superpx" not in first and "below_why" not in first
    assert st["n_bands"] == 2
    # Another run's stands are as before: no flag, the number as it is.
    fc, _ = builder.run_stands("k_run", "feature_vector", vec)
    other = fc["features"][1]["properties"]
    assert "below_min" not in other and other["distance_to_water"] == float(f"{FILL:.4g}")


def test_a_kept_land_runs_profiles_diagnostics_and_metadata_are_written(builder, tmp_path):
    manifest = {"stages": [
        {"name": "profiling", "metadata": {"k": 2, "feature_bands": ["canopy_height",
                                                                     "distance_to_water"],
         "profiles": [{"cluster_id": 0, "pixel_count": 10, "area_ha": 0.1,
                       "canopy_height_mean": 6.123456, "canopy_height_p25": 5.0,
                       "canopy_height_p50": 6.0, "canopy_height_p75": 7.0,
                       "distance_to_water_mean": FILL, "distance_to_water_p25": 800.0,
                       "distance_to_water_p50": FILL, "distance_to_water_p75": FILL}]}},
        {"name": "export", "metadata": {"manifest": {"clustering": {
            "k": 2, "n_stands_left_out_of_fit": 3, "area_ha_in_stands_left_out_of_fit": 0.9}}}}]}
    (tmp_path / "k_run_manifest_export.json").write_text(json.dumps(manifest))
    run = {"merge_diagnostics": {"n_stands": 5, "kept_land": {"kept_land_ha": 12.3}}}
    names, clustering = builder.keptland_files("k_run", tmp_path, run)
    assert clustering["n_stands_left_out_of_fit"] == 3
    out = tmp_path / "ui_data"
    prof = json.loads((out / names["profiles"]).read_text())
    assert "1/cos(latitude)" in prof["area_note"]
    (t0,) = prof["types"]
    assert t0["bands"]["canopy_height"] == {"mean": 6.123, "p25": 5.0, "p50": 6.0, "p75": 7.0}
    assert t0["bands"]["distance_to_water"] == {"mean": "over 10 km", "p25": 800.0,
                                                "p50": "over 10 km", "p75": "over 10 km"}
    assert json.loads((out / names["merge_diagnostics"]).read_text()) == run["merge_diagnostics"]
    assert json.loads((out / names["clustering_metadata"]).read_text())["k"] == 2


def test_the_kept_land_layer_holds_kept_land_only(builder, tmp_path, monkeypatch):
    mask_dir = tmp_path / "mask"
    band = np.array([[1, 1, 0, 0], [1, 1, 0, 0], [0, 0, 0, 1], [0, 0, 0, 1]], dtype="float64")
    _geotiff(mask_dir / "part01_x_habitat_mask.tif", {"habitat_mask": band})
    monkeypatch.setitem(builder.AREAS, "test_area", {"mask_dir": mask_dir})
    name = builder.kept_land_layer("test_area")
    data = json.loads((tmp_path / "ui_data" / name).read_text())
    assert [c["value"] for c in data["classes"]] == [1]
    assert len(data["classes"][0]["polygons"]) == 2  # the two patches

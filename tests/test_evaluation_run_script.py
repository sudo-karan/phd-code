"""`scripts/run_evaluation.py`, end to end, on a small generated site.

All data are generated inside the tests with `fmu.evaluation.synthetic` and
written to a temporary folder. Nothing is read from a real site. The layout
and the column names are made up.
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest
from shapely.geometry import mapping

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import run_evaluation as rev  # noqa: E402

from fmu.evaluation import agreement, pairs  # noqa: E402
from fmu.evaluation import synthetic as sy  # noqa: E402

LAYOUT = {0: (9, 7), 1: (10,)}  # 26 plots, 3 groups, 2 super-groups
# Coarse pixels and large stands keep the polygons few and simple (test cost only).
PARAMS = sy.SyntheticParams(pixel_size=40.0, stand_spacing=240.0, stand_jitter=60.0)
ATTRIBUTES = ("m0", "m1", "m2", "m3")
BANDS = ("0", "200", "400", "inf")
STATISTICS = ("ari_drawing", "ari_labelling", "pair_stand", "pair_type", "mantel_stand",
              "partial_mantel_type", "anosim_stand", "permanova_type")  # fmt: skip


def _feature_collection(geometries: list, properties: list[dict]) -> dict:
    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "geometry": mapping(g), "properties": p}
            for g, p in zip(geometries, properties, strict=True)
        ],
    }


@pytest.fixture(scope="module")
def site(tmp_path_factory: pytest.TempPathFactory) -> dict:
    """A generated site written as the files the script reads."""
    folder = tmp_path_factory.mktemp("site")
    ds = sy.make_dataset(5, 2.0, LAYOUT, PARAMS)
    group_names = {g: f"forest_{chr(97 + g)}" for g in sorted(ds.planted)}

    # Stand polygons, in the order that makes position == the generator's stand code.
    stands, stand_props, first_group_stands = [], [], []
    offset = 0
    for g in sorted(ds.planted):
        raster = ds.planted[g]
        for code, polygon in enumerate(sy.raster_to_polygons(raster)):
            # An empty polygon keeps its place so that positions stay the stand codes.
            stands.append(polygon)
            stand_props.append({"stand": offset + code, "kind": int(raster.stand_type[code])})
            if g == 0 and not polygon.is_empty:
                first_group_stands.append(polygon)
        offset += raster.n_stands
    assert all(not p.is_empty for p in stands)  # so the file keeps every position

    plots = folder / "plots.csv"
    with plots.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["plot", "forest", "region", "stand", "kind", "east", "north",
                         *ATTRIBUTES, "field_kind"])  # fmt: skip
        for i in range(ds.n_plots):
            writer.writerow(
                [
                    f"p{i:03d}",
                    group_names[int(ds.groups[i])],
                    f"region_{int(ds.super_group[i])}",
                    int(ds.stand_id[i]),
                    int(ds.stand_type[i]),
                    repr(float(ds.coords[i, 0])),
                    repr(float(ds.coords[i, 1])),
                    *[repr(float(v)) for v in ds.attributes[i]],
                    f"ft{int(ds.field_type[i])}",
                ]
            )

    files = {"plots": plots}
    for name, payload in {
        "stands": _feature_collection(stands, stand_props),
        "regions": _feature_collection(
            [ds.regions[g] for g in sorted(ds.regions)],
            [{"forest": group_names[g]} for g in sorted(ds.regions)],
        ),
        # The reference is the map itself in the first group: a perfect match there.
        "reference": _feature_collection(first_group_stands, [{}] * len(first_group_stands)),
    }.items():
        files[name] = folder / f"{name}.geojson"
        files[name].write_text(json.dumps(payload), encoding="utf-8")

    declared = folder / "PREDECLARED.md"
    declared.write_text(
        "# Declared before the run (test)\n\nStatistics: "
        + ", ".join(STATISTICS)
        + ". Null: rotation. Bands 0, 200, 400 m and beyond. 19 relabellings, seed 3.\n",
        encoding="utf-8",
    )
    files["predeclared"] = declared
    return {"ds": ds, "files": files, "folder": folder}


def _plot_arguments(files: dict) -> list[str]:
    return [
        "--plots", str(files["plots"]),
        "--stand-id-col", "stand", "--stand-id-scope", "global", "--stand-type-col", "kind",
        "--x-col", "east", "--y-col", "north",
        "--attribute-cols", *ATTRIBUTES,
        "--field-type-col", "field_kind",
        "--group-col", "forest", "--super-group-col", "region",
    ]  # fmt: skip


def _full_arguments(files: dict, out_dir: Path) -> list[str]:
    return [
        "--predeclared", str(files["predeclared"]),
        *_plot_arguments(files),
        "--stand-polygons", str(files["stands"]), "--stand-polygons-type-property", "kind",
        "--regions", str(files["regions"]), "--regions-group-property", "forest",
        "--reference-polygons", str(files["reference"]), "--boundary-tolerance", "40",
        "--statistics", *STATISTICS,
        "--null", "rotation", "--band-edges", *BANDS,
        "--n-permutations", "19", "--seed", "3",
        "--out-dir", str(out_dir),
    ]  # fmt: skip


@pytest.fixture(scope="module")
def full_run(site: dict) -> dict:
    out_dir = site["folder"] / "out"
    code = rev.main(_full_arguments(site["files"], out_dir))
    assert code == 0
    return {
        "out_dir": out_dir,
        "results": json.loads((out_dir / rev.RESULTS_NAME).read_text(encoding="utf-8")),
        "manifest": json.loads((out_dir / rev.MANIFEST_NAME).read_text(encoding="utf-8")),
    }


# ---------------------------------------------------------------------------
# It refuses
# ---------------------------------------------------------------------------


def test_refuses_without_predeclaration(site: dict, capsys: pytest.CaptureFixture) -> None:
    out_dir = site["folder"] / "never"
    arguments = _full_arguments(site["files"], out_dir)
    position = arguments.index("--predeclared")
    del arguments[position : position + 2]
    assert rev.main(arguments) == 2
    assert "declared before they are run" in capsys.readouterr().err
    assert not out_dir.exists()  # nothing computed, nothing written


def test_refuses_missing_or_empty_predeclaration(site: dict, tmp_path: Path) -> None:
    arguments = _full_arguments(site["files"], tmp_path / "out")
    position = arguments.index("--predeclared") + 1
    arguments[position] = str(tmp_path / "no_such_file.md")
    assert rev.main(arguments) == 2
    empty = tmp_path / "empty.md"
    empty.write_text("  \n", encoding="utf-8")
    arguments[position] = str(empty)
    assert rev.main(arguments) == 2
    assert not (tmp_path / "out").exists()


def test_refuses_to_overwrite_and_undeclared_settings(
    site: dict, full_run: dict, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    # An existing result is never replaced silently.
    before = (full_run["out_dir"] / rev.RESULTS_NAME).read_bytes()
    assert rev.main(_full_arguments(site["files"], full_run["out_dir"])) == 2
    assert "never overwritten silently" in capsys.readouterr().err
    assert (full_run["out_dir"] / rev.RESULTS_NAME).read_bytes() == before

    # The null, the number of relabellings, the seed and the bands have no default.
    base = ["--predeclared", str(site["files"]["predeclared"]), *_plot_arguments(site["files"]),
            "--out-dir", str(tmp_path / "out")]  # fmt: skip
    assert rev.main([*base, "--statistics", "mantel_stand"]) == 2
    assert "--null" in capsys.readouterr().err
    permuted = ["--null", "within_group_permutation", "--n-permutations", "9", "--seed", "1"]
    assert rev.main([*base, "--statistics", "pair_stand", *permuted]) == 2
    assert "--band-edges" in capsys.readouterr().err
    # The rotation null cannot be had from a plot table alone.
    rotation = ["--null", "rotation", "--n-permutations", "9", "--seed", "1"]
    assert rev.main([*base, "--statistics", "mantel_stand", *rotation]) == 2
    assert not (tmp_path / "out").exists()


def test_refuses_labels_that_are_not_the_maps(site: dict, tmp_path: Path) -> None:
    """A plot table whose stand ids disagree with the polygons is not tested."""
    ds = site["ds"]
    other = int(np.flatnonzero(ds.stand_id != ds.stand_id[0])[0])  # a plot in another stand
    with site["files"]["plots"].open(encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    stand = rows[0].index("stand")
    rows[1][stand] = rows[1 + other][stand] = "9001"  # two stands forced into one made-up stand
    wrong = tmp_path / "plots_wrong.csv"
    with wrong.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows(rows)
    arguments = _full_arguments(site["files"], tmp_path / "out")
    arguments[arguments.index("--plots") + 1] = str(wrong)
    assert rev.main(arguments) == 2
    assert not (tmp_path / "out").exists()


# ---------------------------------------------------------------------------
# It runs, and the numbers are the package's numbers
# ---------------------------------------------------------------------------


def test_manifest_records_declaration_and_git_state(site: dict, full_run: dict) -> None:
    manifest = full_run["manifest"]
    digest = hashlib.sha256(site["files"]["predeclared"].read_bytes()).hexdigest()
    assert manifest["predeclared"]["sha256"] == digest
    assert full_run["results"]["predeclared_sha256"] == digest
    assert manifest["predeclared"]["names_not_found_in_it"] == []
    assert manifest["predeclared"]["git_status"] in (
        "not_tracked", "unknown", "committed_unmodified", "tracked_modified",
    )  # fmt: skip
    for key in ("commit", "dirty", "modified", "untracked", "error"):
        assert key in manifest["git"]
    for name in ("plots", "stands", "regions", "reference"):
        flag = {"stands": "stand_polygons", "reference": "reference_polygons"}.get(name, name)
        expected = hashlib.sha256(site["files"][name].read_bytes()).hexdigest()
        assert manifest["inputs"][flag]["sha256"] == expected
    results_bytes = (full_run["out_dir"] / rev.RESULTS_NAME).read_bytes()
    assert (
        manifest["outputs"][rev.RESULTS_NAME]["sha256"] == hashlib.sha256(results_bytes).hexdigest()
    )
    assert manifest["arguments"]["seed"] == 3
    assert manifest["arguments"]["null"] == "rotation"


def test_results_match_the_package(site: dict, full_run: dict) -> None:
    ds, results = site["ds"], full_run["results"]
    assert results["inputs"]["n_plots"] == ds.n_plots
    assert results["inputs"]["plots_per_group"] == [9, 7, 10]
    assert results["label_check"]["labels_from"] == "stand polygons"
    assert results["label_check"]["stand_ids_agree"] is True
    assert results["label_check"]["n_plots_whose_type_differs"] == 0

    rows = {row["statistic"]: row for row in results["tests"]["rows"]}
    assert tuple(rows) == STATISTICS
    assert {row["null"] for row in rows.values()} == {"rotation"}
    assert results["null"]["is_a_metric"] is False and results["null"]["caution"] is None

    def close(a: float | None, b: float) -> bool:
        return (a is None and np.isnan(b)) or (
            a is not None and np.isclose(a, b, rtol=1e-8, atol=1e-10)
        )

    # Observed values, recomputed here straight from the generated arrays.
    drawing = agreement.agreement(ds.field_type, ds.stand_id)
    assert close(rows["ari_drawing"]["observed"], drawing.adjusted_rand)
    assert close(results["descriptive"]["ari_drawing"]["adjusted_rand_ceiling"],
                 drawing.adjusted_rand_max)  # fmt: skip
    labelling = agreement.stratified_agreement(ds.field_type, ds.stand_type, ds.super_group)
    assert close(rows["ari_labelling"]["observed"], labelling.adjusted_rand)
    table = pairs.pair_comparison(
        ds.attributes, ds.coords, ds.stand_id, ds.stand_type, (0.0, 200.0, 400.0, np.inf),
        groups=ds.groups, super_group=ds.super_group,
    )  # fmt: skip
    assert close(rows["pair_stand"]["observed"], table.pooled["stand"])
    assert close(rows["pair_type"]["observed"], table.pooled["type"])
    assert close(
        results["descriptive"]["pair_comparison"]["pooled"]["stand"], table.pooled["stand"]
    )
    assert results["descriptive"]["pair_comparison"]["band_edges"][-1] == "inf"

    for row in rows.values():
        assert row["n_draws"] == 19
        if row["p_value"] is not None:
            assert 1 / 20 - 1e-12 <= row["p_value"] <= 1.0
            assert row["p_holm"] >= row["p_value"] - 1e-12


def test_reference_polygons_known_answer(full_run: dict) -> None:
    """The reference is the map itself in one group: a perfect match there."""
    reference = full_run["results"]["reference_polygons"]
    summary = reference["summary"]
    assert summary["n_unmatched_references"] == 0
    for key in ("over", "under", "d"):
        assert abs(summary[key]) < 1e-9
    assert all(abs(row["d"]) < 1e-9 for row in reference["per_reference"])
    # Every reference boundary is a stand boundary; the map has more boundaries elsewhere.
    assert reference["boundary_match"]["recall"] == pytest.approx(1.0, abs=1e-9)
    assert 0.0 < reference["boundary_match"]["precision"] < 1.0


def test_results_hold_results_only_and_reproduce(site: dict, full_run: dict) -> None:
    text = (full_run["out_dir"] / rev.RESULTS_NAME).read_text(encoding="utf-8")
    assert str(site["folder"]) not in text  # no paths
    for word in ("time", "date", "elapsed", "seconds", "hostname", "commit"):
        assert f'"{word}' not in text
    assert "NaN" not in text and "Infinity" not in text  # strict JSON

    again = site["folder"] / "out_again"
    assert rev.main(_full_arguments(site["files"], again)) == 0
    assert (again / rev.RESULTS_NAME).read_bytes() == (
        full_run["out_dir"] / rev.RESULTS_NAME
    ).read_bytes()


def test_plot_table_alone_with_permutation_null(site: dict, tmp_path: Path) -> None:
    """Without polygons only a permutation null is possible, and the results say what that is worth."""
    out_dir = tmp_path / "out"
    code = rev.main(
        [
            "--predeclared",
            str(site["files"]["predeclared"]),
            *_plot_arguments(site["files"]),
            "--statistics",
            "pair_type",
            "anosim_stand",
            "--null",
            "within_group_permutation",
            "--band-edges",
            *BANDS,
            "--n-permutations",
            "19",
            "--seed",
            "3",
            "--out-dir",
            str(out_dir),
        ]  # fmt: skip
    )
    assert code == 0
    results = json.loads((out_dir / rev.RESULTS_NAME).read_text(encoding="utf-8"))
    assert results["null"]["name"] == "within_group_permutation"
    assert "false alarms" in results["null"]["caution"]
    assert results["label_check"]["labels_from"] == "plot table"
    assert "reference_polygons" not in results
    manifest = json.loads((out_dir / rev.MANIFEST_NAME).read_text(encoding="utf-8"))
    # The declaration names the rotation null, not this one: the manifest says so.
    assert manifest["predeclared"]["names_not_found_in_it"] == ["within_group_permutation"]
    anosim = results["descriptive"]["anosim_stand"]
    assert "r_with_equal_weights_for_comparison" in anosim and anosim["per_stratum"]

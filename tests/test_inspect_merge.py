"""Fast tests for the parts of scripts/inspect_merge.py that need no Earth
Engine: building the per-stand table, ordering it, the size distribution, the
pointers it prints, and the files it writes. Also that the script is read-only
unless asked otherwise: `main()` is run with a stand-in Pipeline, with and without
the flag.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import inspect_merge as im  # noqa: E402

from fmu.utils.region_merge import PROVENANCE_FIELDS  # noqa: E402


def _prov(n, pass1=0, relaxed=0, fallback=0, why=""):
    return {
        "n_superpx": n,
        "n_pass1": pass1,
        "n_relaxed": relaxed,
        "n_fallback": fallback,
        "below_min": int(bool(why)),
        "below_why": why,
    }


# Five stands: one of each merge kind, and two left below a 1 ha minimum.
ATTRS = {
    0: {"n_pixels": 400, "area_ha": 4.0, "ch": 10.0, "frac_valid_ch": 1.0},
    1: {"n_pixels": 250, "area_ha": 2.5, "ch": 12.0, "frac_valid_ch": 1.0},
    2: {"n_pixels": 300, "area_ha": 3.0, "ch": None, "frac_valid_ch": 0.2},
    3: {"n_pixels": 40, "area_ha": 0.4, "ch": 9.0, "frac_valid_ch": 1.0},
    4: {"n_pixels": 10, "area_ha": 0.1, "ch": 30.0, "frac_valid_ch": 1.0},
}
PROV = {
    0: _prov(6, pass1=3, relaxed=1, fallback=1),
    1: _prov(4, pass1=1, fallback=2),
    2: _prov(3, pass1=1, relaxed=1),
    3: _prov(2, pass1=1, why="isolated"),
    4: _prov(1, why="area_blocked"),
}


@pytest.fixture
def rows():
    return im.provenance_rows(ATTRS, PROV)


def test_one_row_per_stand_with_the_documented_columns(rows):
    assert [r["stand_lbl"] for r in rows] == [0, 1, 2, 3, 4]
    assert all(tuple(r) == im.TABLE_COLUMNS for r in rows)
    assert set(PROVENANCE_FIELDS) < set(im.TABLE_COLUMNS)
    assert rows[1] == {
        "stand_lbl": 1,
        "area_ha": 2.5,
        "n_pixels": 250,
        "n_superpx": 4,
        "n_pass1": 1,
        "n_relaxed": 0,
        "n_fallback": 2,
        "below_min": 0,
        "below_why": "",
        "merge_kind": 3,
    }
    assert [r["merge_kind"] for r in rows] == [3, 3, 2, 1, 0]


def test_the_two_dicts_must_describe_the_same_stands():
    with pytest.raises(ValueError, match="same stands"):
        im.provenance_rows(ATTRS, {0: PROV[0]})


def test_sorting_by_fallback_merges_by_area_and_by_id(rows):
    # Most fallback merges first; among the stands with none, largest first.
    assert [r["stand_lbl"] for r in im.sort_rows(rows, "fallback")] == [1, 0, 2, 3, 4]
    assert [r["stand_lbl"] for r in im.sort_rows(rows, "area")] == [0, 2, 1, 3, 4]
    assert im.sort_rows(list(reversed(rows)), "id") == rows
    with pytest.raises(ValueError, match="sort must be one of"):
        im.sort_rows(rows, "n_pass1")


def test_size_distribution_against_the_two_bounds(rows):
    d = im.size_distribution([r["area_ha"] for r in rows], 1.0, 3.0)
    assert d["n_stands"] == 5
    assert d["total_ha"] == 10.0 and d["mean_ha"] == 2.0
    assert (d["min_ha"], d["median_ha"], d["max_ha"]) == (0.1, 2.5, 4.0)
    assert (d["n_below_min_area"], d["n_within_bounds"], d["n_above_max_area"]) == (2, 2, 1)
    assert im.size_distribution([], 1.0, 3.0) == {"n_stands": 0}


def test_stands_and_area_by_merge_kind(rows):
    kinds = im.by_merge_kind(rows)
    assert [k["merge_kind"] for k in kinds] == [0, 1, 2, 3]
    assert [k["n_stands"] for k in kinds] == [1, 1, 1, 2]
    assert [k["area_ha"] for k in kinds] == [0.1, 0.4, 3.0, 6.5]
    assert sum(k["share_of_area"] for k in kinds) == pytest.approx(1.0)


def test_the_printed_table_can_be_cut_short_and_says_so(rows):
    full = im.format_table(rows)
    assert full[0].split() == list(im.TABLE_COLUMNS)
    assert len(full) == 1 + len(rows)
    assert full[2].split() == ["1", "2.5", "250", "4", "1", "0", "2", "0", "3"]  # below_why ""
    cut = im.format_table(rows, limit=2)
    assert len(cut) == 4 and "3 more stand(s)" in cut[-1]
    assert im.format_table([]) == ["  ".join(im.TABLE_COLUMNS)]


def test_where_to_look_first_names_the_fallback_stands_and_the_causes(rows):
    text = "\n".join(im.where_to_look_first(rows))
    assert "2 of 5 stands (65.0% of the stand area)" in text
    assert "no merge criterion justified" in text
    # Stand 1 before stand 0: two fallback merges against one.
    assert text.index("stand_lbl 1 (2 of 3 merges") < text.index("stand_lbl 0 (1 of 5 merges")
    assert "1 stand(s) below the minimum size, isolated" in text
    assert "1 stand(s) below the minimum size, area_blocked" in text
    assert "iteration_cap" not in text
    assert "merge_provenance.merge_kind" in text


def test_the_advice_on_an_isolated_stand_says_no_4_connected_neighbour(rows):
    """Review C16: `isolated` means no 4-connected neighbour in the merge's graph, so a
    stand that meets another only at a corner is isolated too; the printed advice must not
    say it touches no other stand."""
    line = next(t for t in im.where_to_look_first(rows) if "minimum size, isolated" in t)
    assert "touches no other stand" not in line
    assert "4-connected" in line and "corner" in line


def test_where_to_look_first_on_a_clean_merge_and_on_none():
    clean = im.provenance_rows({0: ATTRS[0]}, {0: _prov(3, pass1=2)})
    text = "\n".join(im.where_to_look_first(clean))
    assert "No stand contains a shared-edge fallback merge." in text
    assert "No stand is below the minimum size." in text
    assert im.where_to_look_first([]) == ["No stands: the merge had nothing to work on."]


def test_the_table_is_written_as_csv_and_json_in_stand_order(rows, tmp_path):
    header = {"config": "a_config", "summary_numbers": {"stands_out": 5}}
    csv_path, json_path = im.write_table(im.sort_rows(rows, "fallback"), tmp_path, header)

    assert (csv_path.name, json_path.name) == ("merge_provenance.csv", "merge_provenance.json")
    with csv_path.open() as f:
        read = list(csv.DictReader(f))
    assert list(read[0]) == list(im.TABLE_COLUMNS)
    assert [int(r["stand_lbl"]) for r in read] == [0, 1, 2, 3, 4]
    assert read[3]["below_why"] == "isolated" and read[0]["below_why"] == ""
    saved = json.loads(json_path.read_text())
    assert saved["config"] == "a_config"
    assert saved["columns"] == list(im.TABLE_COLUMNS)
    assert saved["stands"] == rows
    # Results only: the same table gives the same bytes.
    first = (csv_path.read_bytes(), json_path.read_bytes())
    im.write_table(rows, tmp_path, header)
    assert (csv_path.read_bytes(), json_path.read_bytes()) == first


def _merge_context():
    """A context as the merge stage leaves it, from a real merge of a small
    hand-built graph (no Earth Engine)."""
    from fmu.stages.base import PipelineContext
    from fmu.utils.adjacency import SuperpixelGraph
    from fmu.utils.region_merge import calibrate_thresholds, merge_superpixels

    px = [30, 30, 300, 40, 200, 200]
    graph = SuperpixelGraph(
        raw_labels=list(range(len(px))),
        n_pixels=px,
        edges={(0, 1): 5, (2, 3): 5, (1, 2): 4, (4, 5): 5, (2, 4): 3},
        scale_m=10,
    )
    height = [10.0, 11.0, 50.0, 53.0, 100.0, 101.0]
    means = {i: {"ch": v, "std": 0.5} for i, v in enumerate(height)}
    counts = {i: {"ch": n, "std": n} for i, n in enumerate(px)}
    criteria = {"ch": 2.0, "std": 0.45}
    result = merge_superpixels(
        graph,
        means,
        counts,
        criteria=criteria,
        relax_factor=1.75,
        min_area_ha=1.0,
        max_area_ha=10.0,
        min_defined_criteria=2,
        min_frac_valid=0.5,
        max_pass2_iterations=60,
    )
    ctx = PipelineContext()
    ctx.set("stand_attributes", result.stand_attributes)
    ctx.set("stand_provenance", result.stand_provenance)
    ctx.set(
        "merge_diagnostics",
        {
            **result.diagnostics,
            "adjacency": graph.summary(),
            "threshold_calibration": calibrate_thresholds(graph, means, criteria),
            "warnings": [],
        },
    )
    return ctx


@pytest.fixture
def fake_run(monkeypatch, tmp_path):
    """Run `main()` with everything that would reach Earth Engine replaced.
    Returns a function taking the command-line arguments and giving back the
    keyword arguments each `Pipeline(...)` was built with."""
    from types import SimpleNamespace

    built: list[dict] = []

    class _FakePipeline:
        def __init__(self, **kwargs):
            built.append(kwargs)

        def run(self, *, config, run_dir, initial_context):
            return SimpleNamespace(context=_merge_context(), stages=[])

    monkeypatch.setattr(im, "Pipeline", _FakePipeline)
    monkeypatch.setattr(im, "init_gee", lambda: None)
    monkeypatch.setattr(im, "load_roi_geometry", lambda roi_file: "<roi>")
    monkeypatch.setattr(im, "init_logging", lambda config_name: tmp_path)

    def run(*argv):
        config = Path(__file__).parent.parent / "configs" / "sanjay_van_baseline.yaml"
        monkeypatch.setattr(sys, "argv", ["inspect_merge.py", "--config", str(config), *argv])
        im.main()
        return built

    return run


def test_a_plain_run_is_read_only_and_stops_at_merge(fake_run, capsys, tmp_path):
    """Run for real, with a stand-in Pipeline: with no flag the one pipeline the
    script builds has exports off, so it can submit no Earth Engine task."""
    (kwargs,) = fake_run()
    assert kwargs["use_cache"] is True
    assert kwargs["submit_exports"] is False
    # It stops at merge: no stage after it, so no clustering and no export.
    assert kwargs["stage_names"][-1] == "merge"
    assert not {"clustering", "export", "metrics"} & set(kwargs["stage_names"])
    out = capsys.readouterr().out
    assert "MODE: read-only" in out and "MODE: --submit-exports" not in out
    saved = json.loads((tmp_path / "merge_provenance.json").read_text())
    assert [r["n_superpx"] for r in saved["stands"]] == [4, 2]
    assert [r["merge_kind"] for r in saved["stands"]] == [3, 1]
    assert (tmp_path / "merge_provenance.csv").exists()


def test_exports_are_submitted_only_when_the_flag_is_given(fake_run, capsys):
    (kwargs,) = fake_run("--submit-exports")
    assert kwargs["submit_exports"] is True
    out = capsys.readouterr().out
    assert "MODE: --submit-exports" in out and "MODE: read-only" not in out

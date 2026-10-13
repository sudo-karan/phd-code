"""scripts/snic_cached_vs_live.py must stay read-only: it is run while batch jobs are queued.

The comparison itself needs Earth Engine and is not run here.
"""

from __future__ import annotations

from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "scripts" / "snic_cached_vs_live.py"


def test_the_script_cannot_submit_a_task_or_write_an_asset():
    src = SCRIPT.read_text()
    for forbidden in ("ee.batch", "Export.", "start_export", "copyAsset", "deleteAsset",
                      "createFolder", "createAsset"):
        assert forbidden not in src, forbidden


def test_every_pipeline_it_builds_is_read_only():
    code = SCRIPT.read_text().split('"""', 2)[2]  # the code after the module docstring
    calls = [line for line in code.splitlines() if "Pipeline(" in line]
    assert calls, "expected the script to build a Pipeline"
    assert all("submit_exports=False" in line for line in calls), calls


def _load():
    import importlib.util

    spec = importlib.util.spec_from_file_location("snic_cached_vs_live", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _result(**kw):
    result = {
        "config": "site_repro",
        "inputs": {"cached": {"distance_scale": 1.2}},
        "comparisons": [
            {"inputs": "cached", "against": "site_repro", "asset": "a",
             "pixels_compared": 1000, "pixels_with_another_label": 264},
        ],
        "between_inputs": [],
        "export_tasks_submitted": 0,
    }
    result.update(kw)
    return result


def test_the_three_inputs_are_the_documented_ones_and_cached_is_the_default():
    mod = _load()
    assert mod.INPUTS == ("cached", "live", "live-on-cache-grid")
    src = SCRIPT.read_text()
    assert 'choices=INPUTS, default=["cached"]' in src
    for kind in mod.INPUTS:
        assert f"       {kind} " in src.split('"""', 2)[1], kind  # each is explained in the docstring


def test_describe_gives_the_share_of_pixels_and_what_was_compared():
    line, last = _load().describe(_result())
    assert "cached features of site_repro" in line and "asset of site_repro" in line
    assert "264 of 1000 pixels carry another label (26.4%)" in line
    assert last == "export tasks submitted: 0"


def test_describe_reports_an_input_that_failed_and_an_asset_that_is_missing():
    lines = _load().describe(_result(
        inputs={"cached": {"distance_scale": 1.2}, "live": {"error": "User memory limit exceeded."}},
        comparisons=[{"inputs": "cached", "against": "site", "asset": "b",
                      "outcome": "its snic_clusters asset is not cached"}],
    ))
    assert any("live features" in ln and "could not be run" in ln and "memory limit" in ln for ln in lines)
    assert any("asset of site: its snic_clusters asset is not cached" in ln for ln in lines)


def test_describe_compares_the_inputs_with_each_other():
    lines = _load().describe(_result(between_inputs=[
        {"a": "cached", "b": "live-on-cache-grid", "pixels_compared": 2000, "pixels_with_another_label": 1},
    ]))
    assert any("cached features of site_repro, against SNIC from its live-on-cache-grid features" in ln
               and "1 of 2000" in ln for ln in lines)


def test_the_run_record_sits_beside_the_result():
    mod = _load()
    assert mod.run_record_path(Path("docs/x/snic_cached_vs_live_site.json")) == Path(
        "docs/x/snic_cached_vs_live_site_run.json")


def test_the_result_file_holds_no_date_and_the_run_record_holds_the_commit():
    code = SCRIPT.read_text().split('"""', 2)[2]
    result_part, record_part = code.split("record = {", 1)
    assert "datetime.datetime.now" not in result_part and "git_state()" not in result_part.split("import")[-1]
    assert '"date"' in record_part and "git_state()" in record_part and '"command_line"' in record_part

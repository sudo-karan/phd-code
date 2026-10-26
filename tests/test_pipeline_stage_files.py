"""A stage's result files: written into the run folder by the orchestrator (round 14).

`StageResult.files` maps a file name to its text. The orchestrator writes each into the run
folder as soon as the stage returns, beside manifest.json, and the manifest names each with its
size and SHA-256. A stage that hands over no file leaves its manifest entry as it was. Round 14
uses it for the k-means rows of the clustering stage and the elbow step, tables too large for
the manifest (round 14 brief, Task 2, item 4: "save each run's fit rows ... as a result file").
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from fmu.pipeline import Pipeline
from fmu.stages.base import (
    Stage,
    StageResult,
    _clear_registry_for_testing,
    _stage_registry,
    register_stage,
)


@pytest.fixture(autouse=True)
def reset_registry():
    found = dict(_stage_registry)
    _clear_registry_for_testing()
    try:
        yield
    finally:
        _clear_registry_for_testing()
        _stage_registry.update(found)


def _config(name: str = "files_test"):
    from fmu.config import Config, DateRange, DatesConfig, ROIConfig

    return Config(
        name=name,
        roi=ROIConfig(name="t", roi_file=Path("aois/sanjay_van.geojson")),
        dates=DatesConfig(
            phenology=DateRange(start="2020-01-01", end="2024-12-31"),
            radar=DateRange(start="2020-01-01", end="2024-12-31"),
            optical_composite=DateRange(start="2023-01-01", end="2023-12-31"),
        ),
    )


def _stage(stage_name: str, files: dict[str, str] | None = None, fail: bool = False):
    @register_stage(stage_name)
    class _S(Stage):
        name = stage_name
        required_inputs: set[str] = set()
        produces: set[str] = set()

        def run(self, ctx, config):
            if fail:
                raise RuntimeError("this stage fails")
            return StageResult(files=dict(files or {}))

    return _S


def test_a_stage_s_files_are_written_into_the_run_folder_and_named_in_the_manifest(tmp_path):
    text = "stand_lbl,in_fit,b0\n1,1,0.5\n"
    _stage("rows", {"rows_fit_rows.csv": text})
    Pipeline(stage_names=["rows"]).run(config=_config(), run_dir=tmp_path)
    assert (tmp_path / "rows_fit_rows.csv").read_text() == text
    entry = json.loads((tmp_path / "manifest.json").read_text())["stages"][0]
    data = text.encode()
    assert entry["files"] == {
        "rows_fit_rows.csv": {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    }


def test_a_stage_with_no_file_keeps_its_manifest_entry_as_it_was(tmp_path):
    _stage("plain")
    Pipeline(stage_names=["plain"]).run(config=_config(), run_dir=tmp_path)
    entry = json.loads((tmp_path / "manifest.json").read_text())["stages"][0]
    assert "files" not in entry
    assert sorted(p.name for p in tmp_path.iterdir()) == ["manifest.json"]


@pytest.mark.parametrize("bad", ["../escape.csv", "sub/inner.csv", "", ".", "..", "manifest.json"])
def test_a_file_name_that_is_not_a_plain_new_name_in_the_folder_is_refused(tmp_path, bad):
    _stage("bad", {bad: "x\n"})
    with pytest.raises(ValueError, match="file name"):
        Pipeline(stage_names=["bad"]).run(config=_config(), run_dir=tmp_path)


def test_two_stages_cannot_write_the_same_file(tmp_path):
    _stage("one", {"same.csv": "a\n"})
    _stage("two", {"same.csv": "b\n"})
    with pytest.raises(ValueError, match="already"):
        Pipeline(stage_names=["one", "two"]).run(config=_config(), run_dir=tmp_path)
    assert (tmp_path / "same.csv").read_text() == "a\n"


def test_the_files_are_written_as_the_stage_returns_even_if_a_later_stage_fails(tmp_path):
    _stage("first", {"first_rows.csv": "a\n"})
    _stage("second", fail=True)
    with pytest.raises(RuntimeError):
        Pipeline(stage_names=["first", "second"]).run(config=_config(), run_dir=tmp_path)
    assert (tmp_path / "first_rows.csv").read_text() == "a\n"

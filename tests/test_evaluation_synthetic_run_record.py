"""scripts/evaluation_synthetic_validation.py writes a run record beside its two result files.

The validation itself is stood in for here (tests/test_evaluation_synthetic.py runs it); this file
checks only the record of which code and which environment wrote the results.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "evaluation_synthetic_validation.py"


def _load():
    spec = importlib.util.spec_from_file_location("evaluation_synthetic_validation_record", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclasses look their module up while a class is built
    try:
        spec.loader.exec_module(mod)
    finally:
        del sys.modules[spec.name]
    return mod


def test_the_results_get_a_run_record_beside_them(tmp_path, monkeypatch):
    """Review C37: the builder of docs/evaluation/synthetic_validation.{csv,md} wrote no record of
    its own: which commit, whether the tree was dirty, and which packages made the files were
    nowhere. The two result files still hold results only."""
    from fmu.utils.provenance import environment_state, git_state

    esv = _load()
    asked: list[str] = []

    def run_validation(design, **kwargs):
        asked.append("run")
        return {"design": "stood in for"}

    def write_outputs(results, out_dir, command):
        out_dir.mkdir(parents=True, exist_ok=True)
        paths = (out_dir / "synthetic_validation.csv", out_dir / "synthetic_validation.md")
        for p in paths:
            p.write_text("results\n")
        return paths

    monkeypatch.setattr(esv, "run_validation", run_validation)
    monkeypatch.setattr(esv, "write_outputs", write_outputs)
    assert esv.main(["--quick", "--out-dir", str(tmp_path), "--jobs", "2"]) == 0
    assert asked == ["run"]
    record = json.loads((tmp_path / "synthetic_validation_run.json").read_text())
    assert record["result_files"] == ["synthetic_validation.csv", "synthetic_validation.md"]
    assert record["command_line"].endswith(
        f"scripts/evaluation_synthetic_validation.py --quick --out-dir {tmp_path} --jobs 2")
    assert record["git"] == {k: v for k, v in git_state().items() if k != "root"}
    assert record["environment"] == environment_state()
    assert "date" in record
    for name in record["result_files"]:
        assert (tmp_path / name).read_text() == "results\n"

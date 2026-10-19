"""Run records name the code as it was when the run started, and say how the tree stood at the end.

Review of 19 Oct 2026, C32: fmu.utils.provenance.git_state remembers its first answer, and nothing
asked it when a run started. The pipeline first asked when it wrote the manifest, after the
stages, so a commit made during a run was recorded as the run's commit; and three scripts wrote
their results before they asked, so a script that rewrote a tracked result recorded its own output
as a dirty tree. Each test below fails on the code before round 13's fix.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

import fmu.utils.provenance as prov

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "odisha_script"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(REPO / "scripts"))

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.org",
                           "-c", "commit.gpgsign=false", *args],
                          capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q")
    (r / "tracked.txt").write_text("one\n")
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "first")
    return r


@needs_git
def test_the_state_now_is_read_again_and_not_remembered(repo: Path):
    assert prov.git_state(repo, refresh=True)["dirty"] is False
    (repo / "tracked.txt").write_text("two\n")
    assert prov.git_state_now(repo)["dirty"] is True
    assert prov.git_state(repo)["dirty"] is False  # what the process started with is kept


# ---------------------------------------------------------------------------
# The pipeline's manifest
# ---------------------------------------------------------------------------


@needs_git
def test_the_manifest_names_the_commit_the_run_started_from_and_the_one_it_ended_on(repo, tmp_path,
                                                                                     monkeypatch):
    import fmu.pipeline
    from fmu.pipeline import Pipeline
    from fmu.stages.base import (
        Stage,
        StageResult,
        _clear_registry_for_testing,
        _stage_registry,
        register_stage,
    )
    from test_pipeline import _make_config

    found = dict(_stage_registry)
    start = _git(repo, "rev-parse", "HEAD")

    @register_stage("commits_while_it_runs")
    class CommitsWhileItRuns(Stage):
        name = "commits_while_it_runs"
        required_inputs: set[str] = set()
        produces: set[str] = set()

        def run(self, ctx, config):
            (repo / "tracked.txt").write_text("changed while the run ran\n")
            _git(repo, "commit", "-qam", "during the run")
            return StageResult()

    monkeypatch.setattr(prov, "_cache", {})
    monkeypatch.setattr(fmu.pipeline, "git_state", lambda: prov.git_state(repo))
    monkeypatch.setattr(fmu.pipeline, "git_state_now", lambda: prov.git_state_now(repo), raising=False)
    (tmp_path / "run").mkdir()
    try:
        Pipeline(stage_names=["commits_while_it_runs"]).run(config=_make_config(name="git_test"),
                                                           run_dir=tmp_path / "run")
    finally:
        _clear_registry_for_testing()
        _stage_registry.update(found)
    manifest = json.loads((tmp_path / "run" / "manifest.json").read_text())
    assert manifest["git"]["commit"] == start
    assert manifest["git_at_end"]["commit"] == _git(repo, "rev-parse", "HEAD") != start


# ---------------------------------------------------------------------------
# Scripts that write their results and then their record
# ---------------------------------------------------------------------------


def _git_reads_see(paths: list[Path], monkeypatch) -> None:
    """Every read of the git state answers as git would for a tree whose only change is that some of
    `paths` exist (the script's results, tracked here): dirty once one has been written."""
    def read(start):
        written = sorted(str(p) for p in paths if p.exists())
        return {"commit": "c" * 40, "dirty": bool(written), "modified": written, "modified_truncated": False,
                "untracked": [], "untracked_truncated": False, "root": "/repo", "error": None}

    monkeypatch.setattr(prov, "_cache", {})
    monkeypatch.setattr(prov, "_read_git_state", read)


def test_the_scorers_record_names_the_tree_as_it_was_before_the_scores_were_written(tmp_path, monkeypatch):
    import odisha_keptland_score as K  # noqa: N812

    out = tmp_path / "scores"
    stem = "keptland_x"
    _git_reads_see([out / f"{stem}_joined.csv", out / f"{stem}_scores.json", out / f"{stem}_scores.txt"],
                   monkeypatch)
    # The declared join and scores are tested in tests/test_keptland_score.py; stood in for here.
    plots = pd.DataFrame({"plot_key": ["p1"], "box_district": [K.DISTRICTS[0]], "epsg": [32645]})

    def join(sub, layer, reach):
        n = len(sub)
        return pd.DataFrame({"plot_key": list(sub.plot_key), "sid": [1] * n, "cluster": [0] * n,
                             "how": ["covered"] * n})

    monkeypatch.setattr(K, "plots_in_boxes", lambda: plots)
    monkeypatch.setattr(K, "stand_layer", lambda run, stands_dir: tmp_path / f"{run}.geojson")
    monkeypatch.setattr(K, "sha256", lambda path: "0" * 64)
    monkeypatch.setattr(K, "join", join)
    monkeypatch.setattr(K, "join_counts", lambda plots, joined: {})
    monkeypatch.setattr(K, "analyses", lambda *a: [])
    monkeypatch.setattr(K, "text", lambda result, runs: "scores\n")
    assert K.main(["--out-dir", str(out), "--stem", stem]) == 0
    record = json.loads((out / f"{stem}_scores_run.json").read_text())
    assert record["git"]["dirty"] is False  # read before the scores were written
    assert record["git_at_end"]["modified"] == sorted(
        str(out / n) for n in (f"{stem}_joined.csv", f"{stem}_scores.json", f"{stem}_scores.txt"))


def test_the_chance_tests_record_names_the_tree_as_it_was_before_the_result_was_written(tmp_path,
                                                                                        monkeypatch):
    import odisha_keptland_chance as C  # noqa: N812

    out = tmp_path / "chance"
    stem = C.out_stem("keptland_s1desc", False, 12)
    _git_reads_see([out / f"{stem}.json", out / f"{stem}.txt"], monkeypatch)

    def run(n_rot, out_dir, **kwargs):  # the 12 rotations stood in for: the result files only
        out_dir.mkdir(parents=True, exist_ok=True)
        for ext in (".json", ".txt"):
            (out_dir / f"{stem}{ext}").write_text("result\n")
        return {"rehearsal": False}

    monkeypatch.setattr(C, "run", run)
    assert C.main(["--rotations", "12", "--out-dir", str(out)]) == 0
    record = json.loads((out / f"{stem}_run.json").read_text())
    assert record["git"]["dirty"] is False
    assert record["git_at_end"]["dirty"] is True


def test_step12s_record_names_the_tree_as_it_was_before_the_sample_was_written(tmp_path, monkeypatch):
    import odisha_phase1_12_radar_descending as step12

    committed_run = json.loads((SCRIPTS / "odisha_phase1_12_radar_descending_run.json").read_text())
    committed_sample = pd.read_csv(SCRIPTS / "odisha_plots_sampled_s1desc.csv")
    for name, path in (("RESULTS", tmp_path / "results.txt"), ("RUN", tmp_path / "run.json"),
                       ("SAMPLE", tmp_path / "sample.csv")):
        monkeypatch.setattr(step12, name, path)
    monkeypatch.setattr(step12, "sample",
                        lambda: (committed_sample.copy(), dict(committed_run["images_per_district"])))
    _git_reads_see([tmp_path / "results.txt", tmp_path / "sample.csv"], monkeypatch)
    monkeypatch.setattr(sys, "argv", ["odisha_phase1_12_radar_descending.py"])  # the sampling run
    assert step12.main() == 0
    record = json.loads((tmp_path / "run.json").read_text())
    assert record["git"]["dirty"] is False and record["sampling_run"]["git"]["dirty"] is False
    assert record["git_at_end"]["modified"] == [str(tmp_path / "results.txt"), str(tmp_path / "sample.csv")]

"""The batch wrapper reads the run tree's git state before and after each pass (review C32).

Since round 14 (round 13 question 30 (c)) the state counts untracked code under src/, scripts/,
odisha_script/ and configs/ as well as modified tracked files, by the run tree's own
fmu.utils.provenance.untracked_code (the harness's run tree links src/fmu to this checkout's).

Run against the modelled Earth Engine of tests/_wrapper_harness.py, as tests/test_run_passes_safely.py
is: the real wrapper and the real run_config_passes.sh, nothing reaching Earth Engine.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from _wrapper_harness import Harness, wait_for

pytestmark = pytest.mark.skipif(shutil.which("bash") is None or shutil.which("git") is None,
                                reason="needs bash and git")

A = "cfg_a"


@pytest.fixture
def h(tmp_path: Path):
    harness = Harness(tmp_path)
    yield harness
    harness.cleanup()


def _git(rt: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.name=harness", "-c", "user.email=harness@example.org",
                           "-c", "commit.gpgsign=false", "-C", str(rt), *args],
                          check=True, capture_output=True, text=True).stdout.strip()


@pytest.mark.parametrize("change", ["a commit", "an uncommitted edit"])
def test_a_run_tree_changed_during_a_pass_starts_no_further_pass_and_is_recorded(h, change):
    """Review C32: the wrapper read the run tree's commit once, at the start, and its state file
    always said "dirty": false. A commit or an edit made while a batch ran was not seen: the next
    pass ran other code than the passes before it, and the record named the start commit as
    clean. A batch is run from a run tree pinned to one commit (CLAUDE.md), so the wrapper now
    reads the tree before and after each pass and starts no pass on a tree that has changed."""
    a = h.config(A)
    (h.rt / "notes.txt").write_text("one\n")
    h.commit()
    start = _git(h.rt, "rev-parse", "HEAD")
    # Pass 1 is held at its features call, then fails at clustering, so a pass 2 is needed.
    h.scenario(hold=[f"{A}:features"], fail_once=[f"{A}:clustering"])
    w = h.start(a)
    assert wait_for(h.holding), h.log()
    (h.rt / "notes.txt").write_text("two\n")
    if change == "a commit":
        _git(h.rt, "commit", "-qam", "moved while the batch ran")
    h.release()
    rc, out = h.finish(w)
    state = h.state()
    assert rc == 95, out
    assert [s for _, _, _, s in h.runners()] == ["features", "segmentation", "clustering"]
    # untracked_code since round 14 (round 13 question 30 (c)): none here
    assert state["git"] == {"commit": start, "dirty": False, "modified": [], "untracked_code": [],
                            "error": None}
    (only,) = state["passes"]
    assert only["git_before"] == state["git"]
    now = {"commit": _git(h.rt, "rev-parse", "HEAD"), "dirty": change != "a commit",
           "modified": [] if change == "a commit" else ["notes.txt"], "untracked_code": [],
           "error": None}
    assert only["git_after"] == now and state["run_tree_changed"] == {"before_pass": 2, "git": now}
    assert state["not_finished"] == [A]
    log = h.log()
    assert "REFUSING pass 2: the run tree changed since the batch started" in log
    assert log.splitlines()[-1].endswith("batch batch ended: NOT ALL COMPLETE (the run tree changed)")


def test_a_run_tree_changed_during_the_last_pass_is_recorded_and_the_batch_is_not_called_complete(h):
    """The config finishes in its one pass, but the tree moved while it ran: the later calls of the
    pass may have run other code, so the batch says so and exits 95, with the config done."""
    a = h.config(A)
    (h.rt / "notes.txt").write_text("one\n")
    h.commit()
    h.scenario(hold=[f"{A}:segmentation"])
    w = h.start(a)
    assert wait_for(h.holding), h.log()
    (h.rt / "notes.txt").write_text("two\n")
    _git(h.rt, "commit", "-qam", "moved while the batch ran")
    h.release()
    rc, out = h.finish(w)
    state = h.state()
    assert rc == 95, out
    now = {"commit": _git(h.rt, "rev-parse", "HEAD"), "dirty": False, "modified": [],
           "untracked_code": [], "error": None}
    assert state["run_tree_changed"] == {"after_pass": 1, "git": now}
    assert state["done"] == [A] and state["passes"][0]["git_after"] == now
    assert "the run tree changed during pass 1" in h.log()


def test_a_batch_on_a_run_tree_that_stays_as_it_was_records_it_before_and_after_each_pass(h):
    """On a pinned run tree a batch runs as before, and the state file now says, for each pass,
    how the tree stood before and after it: as the batch started."""
    a = h.config(A)
    h.commit()
    h.scenario(fail_once=[f"{A}:clustering"])
    rc, out = h.finish(h.start(a))
    state = h.state()
    assert rc == 0, out
    assert [p["git_before"] for p in state["passes"]] == [state["git"]] * 2
    assert [p["git_after"] for p in state["passes"]] == [state["git"]] * 2
    assert state["run_tree_changed"] is None and state["done"] == [A]


# ---------- Round 14 (round 13 question 30 (c)): untracked code makes the run tree dirty ----------


def test_a_run_tree_with_untracked_code_is_refused_before_anything_runs(h):
    """Round 13 question 30, answer (c): the wrapper refuses a run tree with untracked code under
    src/, scripts/, odisha_script/ or configs/ (exit 92), as it refuses one with modified tracked
    files. An untracked module would run in every pass, and no record would call the tree dirty.
    Until round 14 the wrapper read tracked files only (git status --untracked-files=no) and ran
    the batch."""
    a = h.config(A)
    h.commit()
    (h.rt / "odisha_script" / "new.py").write_text("x = 1\n")
    w = h.start(a)
    rc, out = h.finish(w)
    assert rc == 92, out
    assert "REFUSING" in out and "odisha_script/new.py" in out
    assert h.runners() == [] and h.tasks() == [] and h.ee_calls(w.pid) == []


def test_a_run_tree_with_a_modified_tracked_file_is_still_refused(h):
    a = h.config(A)
    (h.rt / "notes.txt").write_text("one\n")
    h.commit()
    (h.rt / "notes.txt").write_text("two\n")
    rc, out = h.finish(h.start(a))
    assert rc == 92, out
    assert "REFUSING" in out and "notes.txt" in out and h.runners() == []


def test_untracked_code_written_during_a_pass_starts_no_further_pass(h):
    """The check before each pass (review C32) reads the tree by the same rule, so a module dropped
    into src/ while a pass runs stops the batch before the next pass, and the record names it."""
    a = h.config(A)
    h.commit()
    start = _git(h.rt, "rev-parse", "HEAD")
    h.scenario(hold=[f"{A}:features"], fail_once=[f"{A}:clustering"])
    w = h.start(a)
    assert wait_for(h.holding), h.log()
    (h.rt / "src" / "new_module.py").write_text("x = 1\n")
    h.release()
    rc, out = h.finish(w)
    state = h.state()
    assert rc == 95, out
    now = {"commit": start, "dirty": True, "modified": [], "untracked_code": ["src/new_module.py"],
           "error": None}
    assert state["passes"][0]["git_after"] == now
    assert state["run_tree_changed"] == {"before_pass": 2, "git": now}
    assert "untracked code: ['src/new_module.py']" in h.log()


def test_run_outputs_pycache_folders_and_code_outside_the_four_folders_leave_a_batch_alone(h):
    """Run outputs and __pycache__ folders under the four folders hold no code, and the answer
    scopes the rule to the four folders, so none of these stops a batch or makes its record dirty.
    The harness's run tree has no .gitignore, so git lists every one of them."""
    a = h.config(A)
    h.commit()
    (h.rt / "odisha_script" / "phase2_vectors").mkdir()
    (h.rt / "odisha_script" / "phase2_vectors" / f"{A}_stands_merged.geojson").write_text("{}")
    (h.rt / "scripts" / "__pycache__").mkdir(parents=True)
    (h.rt / "scripts" / "__pycache__" / "tool.cpython-313.pyc").write_bytes(b"\x00")
    (h.rt / "notes.py").write_text("")
    (h.rt / "tests").mkdir()
    (h.rt / "tests" / "test_new.py").write_text("")
    h.scenario(fail_once=[f"{A}:clustering"])
    rc, out = h.finish(h.start(a))
    state = h.state()
    assert rc == 0, out
    assert state["git"]["dirty"] is False and state["git"]["untracked_code"] == []
    assert len(state["passes"]) == 2 and state["run_tree_changed"] is None


def test_a_run_tree_whose_fmu_has_no_untracked_code_rule_is_refused(h):
    """The wrapper takes the rule from the run tree's own fmu.utils.provenance, the one its runs'
    records follow. A run tree from before round 14 has none, so its untracked code cannot be
    checked by that rule: refused (exit 92) before a config is read, not run on another rule."""
    a = h.config(A)
    fmu = h.rt / "src" / "fmu"
    fmu.unlink()  # the link to this checkout's package
    (fmu / "utils").mkdir(parents=True)
    (fmu / "__init__.py").write_text("")
    (fmu / "utils" / "__init__.py").write_text("")
    old = '"""A provenance module from before round 14, with git_state only."""\n'
    (fmu / "utils" / "provenance.py").write_text(old)
    h.commit()
    rc, out = h.finish(h.start(a))
    assert rc == 92, out
    assert "REFUSING" in out and "untracked_code" in out and h.runners() == []

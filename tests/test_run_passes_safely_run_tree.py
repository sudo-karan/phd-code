"""The batch wrapper reads the run tree's git state before and after each pass (review C32).

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
    assert state["git"] == {"commit": start, "dirty": False, "modified": [], "error": None}
    (only,) = state["passes"]
    assert only["git_before"] == state["git"]
    now = {"commit": _git(h.rt, "rev-parse", "HEAD"), "dirty": change != "a commit",
           "modified": [] if change == "a commit" else ["notes.txt"], "error": None}
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
    now = {"commit": _git(h.rt, "rev-parse", "HEAD"), "dirty": False, "modified": [], "error": None}
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

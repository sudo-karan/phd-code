"""fmu.utils.provenance.git_state counts untracked code under four code folders as dirty (round 14).

Round 13's question 30, answer (c) (Jaskaran, 26 Oct 2026, by the round 14 brief's rule "Every
other question: your recommendation"): count as dirty only untracked code files, by suffix (.py,
.sh, .yaml and the like), and untracked folders under src/, scripts/, odisha_script/ and configs/.
Until round 14 the flag counted tracked files only, so an untracked module or config that changed
what ran left a record that said the tree was clean. A folder counts by what it holds: a folder of
run outputs or a __pycache__ folder holds no code, so neither sets the flag. Code outside the four
folders does not set it either: the answer names those four. The batch wrapper refuses a run tree
by the same rule (tests/test_run_passes_safely_run_tree.py).

The repositories are throwaway ones under tmp_path, with no .gitignore, as the wrapper's test run
trees have none: git lists a __pycache__ folder there as untracked.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from fmu.utils.provenance import git_state

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")

OUTPUTS = "odisha_script/phase2_vectors"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.org",
                    "-c", "commit.gpgsign=false", *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A checkout whose folders are tracked, as this repository's are, each holding a .keep only."""
    r = tmp_path / "repo"
    for folder in ("configs", "scripts", "src/fmu", "odisha_script", OUTPUTS, "tests", "docs"):
        (r / folder).mkdir(parents=True)
        (r / folder / ".keep").write_text("")
    _git(r, "init", "-q")
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "first")
    return r


def test_an_untracked_module_in_src_makes_the_tree_dirty(repo: Path):
    (repo / "src" / "x.py").write_text("x = 1\n")
    s = git_state(repo, refresh=True)
    assert s["dirty"] is True
    assert s["modified"] == [] and s["untracked_code"] == ["src/x.py"]
    assert s["untracked_code_truncated"] is False


def test_an_untracked_folder_holding_code_makes_the_tree_dirty(repo: Path):
    """git names an untracked folder ("scripts/newdir/") without its files; the files decide."""
    (repo / "scripts" / "newdir" / "deeper").mkdir(parents=True)
    (repo / "scripts" / "newdir" / "deeper" / "tool.py").write_text("")
    (repo / "scripts" / "newdir" / "notes.txt").write_text("")
    s = git_state(repo, refresh=True)
    assert s["untracked"] == ["scripts/newdir/"]
    assert s["dirty"] is True and s["untracked_code"] == ["scripts/newdir/deeper/tool.py"]


def test_an_untracked_config_or_shell_script_makes_the_tree_dirty(repo: Path):
    (repo / "configs" / "new_site_r14.yaml").write_text("name: new_site_r14\n")
    (repo / "odisha_script" / "Run Batch.SH").write_text("")  # the suffix in any case; a space
    s = git_state(repo, refresh=True)
    assert s["dirty"] is True
    assert s["untracked_code"] == ["configs/new_site_r14.yaml", "odisha_script/Run Batch.SH"]


def test_untracked_run_outputs_do_not_make_the_tree_dirty(repo: Path):
    """A finished run leaves its outputs in odisha_script/phase2_vectors/: they are not code."""
    for name in ("a.geojson", "a_raster_at_plots.csv", "a_run.json", "results.txt"):
        (repo / OUTPUTS / name).write_text("{}")
    (repo / "odisha_script" / "new_outputs").mkdir()  # an untracked folder of outputs
    (repo / "odisha_script" / "new_outputs" / "b.geojson").write_text("{}")
    s = git_state(repo, refresh=True)
    assert s["dirty"] is False and s["untracked_code"] == []
    assert {f"{OUTPUTS}/a.geojson", "odisha_script/new_outputs/"} <= set(s["untracked"])


def test_an_untracked_pycache_folder_does_not_make_the_tree_dirty(repo: Path):
    """Python writes __pycache__ beside a module it imports; with no .gitignore git lists it."""
    for folder in ("scripts/__pycache__", "odisha_script/__pycache__", "src/fmu/__pycache__"):
        (repo / folder).mkdir()
        (repo / folder / "mod.cpython-313.pyc").write_bytes(b"\x00")
    s = git_state(repo, refresh=True)
    assert s["untracked"] == ["odisha_script/__pycache__/", "scripts/__pycache__/",
                              "src/fmu/__pycache__/"]
    assert s["dirty"] is False and s["untracked_code"] == []


def test_untracked_code_outside_the_four_folders_does_not_make_the_tree_dirty(repo: Path):
    """The answer scopes the rule to src/, scripts/, odisha_script/ and configs/: a new test, a
    script at the top level or in docs/ is listed among the untracked paths, not counted."""
    (repo / "tests" / "test_new.py").write_text("")
    (repo / "top.py").write_text("")
    (repo / "docs" / "build.sh").write_text("")
    (repo / "newpkg").mkdir()
    (repo / "newpkg" / "mod.py").write_text("")
    s = git_state(repo, refresh=True)
    assert s["dirty"] is False and s["untracked_code"] == []
    assert set(s["untracked"]) == {"docs/build.sh", "newpkg/", "tests/test_new.py", "top.py"}


def test_a_repository_inside_a_code_folder_counts_as_untracked_code(repo: Path):
    """git does not list the files of a repository inside the checkout, so a folder that is one
    cannot be shown to hold no code; it counts, under its own name."""
    nested = repo / "src" / "vendored"
    nested.mkdir()
    _git(nested, "init", "-q")
    (nested / "lib.txt").write_text("")
    s = git_state(repo, refresh=True)
    assert s["dirty"] is True and s["untracked_code"] == ["src/vendored/"]


def test_the_untracked_code_list_is_cut_at_fifty_and_says_so(repo: Path):
    for i in range(60):
        (repo / "scripts" / f"tool_{i:02d}.py").write_text("")
    s = git_state(repo, refresh=True)
    assert s["dirty"] is True and s["untracked_code_truncated"] is True
    assert s["untracked_code"] == [f"scripts/tool_{i:02d}.py" for i in range(50)]


def test_a_tracked_change_and_untracked_code_are_listed_apart(repo: Path):
    (repo / "configs" / ".keep").write_text("changed\n")
    (repo / "src" / "fmu" / "new_stage.py").write_text("")
    s = git_state(repo, refresh=True)
    assert s["dirty"] is True
    assert s["modified"] == ["configs/.keep"] and s["untracked_code"] == ["src/fmu/new_stage.py"]

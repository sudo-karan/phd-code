"""fmu.utils.provenance.git_state lists untracked code before untracked outputs (review C34).

The list of untracked paths is the record's safeguard for a source file that is not in git: it does
not make the tree dirty, but it can change what ran. The list is cut at 50 paths, and run outputs
(odisha_script/phase2_vectors/...) sort before scripts/, src/ and tests/, so 50 of them pushed an
untracked module off it, with nothing else to flag it.
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
    """A checkout whose folders are tracked, as this repository's are: git then lists a new file in
    them one by one (a folder git does not track at all is listed as the folder)."""
    r = tmp_path / "repo"
    for folder in ("configs", "scripts", "src/fmu", OUTPUTS):
        (r / folder).mkdir(parents=True)
        (r / folder / ".keep").write_text("")
    _git(r, "init", "-q")
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "first")
    return r


def _outputs(repo: Path, n: int) -> list[str]:
    names = [f"{OUTPUTS}/run_{i:03d}_stands_merged.geojson" for i in range(n)]
    for name in names:
        (repo / name).write_text("{}")
    return names


def test_an_untracked_module_stays_on_the_list_past_fifty_untracked_outputs(repo: Path):
    _outputs(repo, 50)
    (repo / "src" / "fmu" / "new_stage.py").write_text("x = 1\n")
    s = git_state(repo, refresh=True)
    assert "src/fmu/new_stage.py" in s["untracked"]
    assert s["untracked"][0] == "src/fmu/new_stage.py" and len(s["untracked"]) == 50
    assert s["untracked_truncated"] is True and s["dirty"] is False


def test_code_and_untracked_folders_come_first_then_the_rest_each_sorted(repo: Path):
    outputs = _outputs(repo, 3)
    (repo / "configs" / "b.yaml").write_text("name: b\n")
    (repo / "scripts" / "a.py").write_text("")
    (repo / "scripts" / "run.sh").write_text("")
    (repo / "newpkg").mkdir()  # an untracked folder: git names the folder, not its files
    (repo / "newpkg" / "mod.py").write_text("")
    (repo / "notes.txt").write_text("")
    s = git_state(repo, refresh=True)
    assert s["untracked"] == ["configs/b.yaml", "newpkg/", "scripts/a.py", "scripts/run.sh",
                              "notes.txt", *outputs]
    assert s["untracked_truncated"] is False


def test_with_few_untracked_paths_the_list_holds_them_all(repo: Path):
    """The set listed does not change when it fits: only its order."""
    outputs = _outputs(repo, 2)
    (repo / "scripts" / "a.py").write_text("")
    s = git_state(repo, refresh=True)
    assert sorted(s["untracked"]) == sorted([*outputs, "scripts/a.py"])

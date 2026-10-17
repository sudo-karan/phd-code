"""`fmu.utils.provenance.git_state`: the record of which code ran.

Every run manifest carries it (CLAUDE.md, "Results"). These tests build small
throwaway repositories under tmp_path; nothing here touches the repository the
tests live in, apart from one test that only reads it.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from fmu.utils.provenance import git_state

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")

KEYS = {
    "commit",
    "dirty",
    "modified",
    "modified_truncated",
    "untracked",
    "untracked_truncated",
    "root",
    "error",
}


def _git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=test", "-c", "user.email=test@example.com",
         "-c", "commit.gpgsign=false", *args],
        capture_output=True, text=True, check=True,
    )
    return done.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q")
    (r / "tracked.txt").write_text("one\n")
    (r / ".gitignore").write_text("ignored.txt\n")
    _git(r, "add", "tracked.txt", ".gitignore")
    _git(r, "commit", "-q", "-m", "first")
    return r


def test_clean_tree(repo: Path):
    s = git_state(repo, refresh=True)
    assert set(s) == KEYS
    assert s["commit"] == _git(repo, "rev-parse", "HEAD") and len(s["commit"]) == 40
    assert s["dirty"] is False
    assert s["modified"] == [] and s["untracked"] == []
    assert Path(s["root"]).resolve() == repo.resolve()
    assert s["error"] is None


def test_a_modified_tracked_file_makes_it_dirty(repo: Path):
    (repo / "tracked.txt").write_text("two\n")
    s = git_state(repo, refresh=True)
    assert s["dirty"] is True and s["modified"] == ["tracked.txt"]


def test_a_staged_change_makes_it_dirty(repo: Path):
    (repo / "tracked.txt").write_text("two\n")
    _git(repo, "add", "tracked.txt")
    s = git_state(repo, refresh=True)
    assert s["dirty"] is True and s["modified"] == ["tracked.txt"]


def test_a_deleted_tracked_file_makes_it_dirty(repo: Path):
    (repo / "tracked.txt").unlink()
    s = git_state(repo, refresh=True)
    assert s["dirty"] is True and s["modified"] == ["tracked.txt"]


def test_a_rename_is_one_entry_under_its_new_name(repo: Path):
    _git(repo, "mv", "tracked.txt", "renamed file.txt")
    s = git_state(repo, refresh=True)
    assert s["dirty"] is True and s["modified"] == ["renamed file.txt"]


def test_untracked_files_are_listed_but_do_not_make_it_dirty(repo: Path):
    """A finished run leaves untracked outputs behind; they are not code."""
    (repo / "output.geojson").write_text("{}")
    s = git_state(repo, refresh=True)
    assert s["dirty"] is False
    assert s["untracked"] == ["output.geojson"]


def test_ignored_files_appear_nowhere(repo: Path):
    (repo / "ignored.txt").write_text("x")
    s = git_state(repo, refresh=True)
    assert s["dirty"] is False and s["untracked"] == [] and s["modified"] == []


def test_long_lists_are_cut_at_fifty_and_say_so(repo: Path):
    for i in range(60):
        (repo / f"new_{i:02d}.txt").write_text("x")
    s = git_state(repo, refresh=True)
    assert len(s["untracked"]) == 50 and s["untracked_truncated"] is True
    assert s["modified_truncated"] is False


def test_start_may_be_a_file_or_a_subdirectory(repo: Path):
    sub = repo / "pkg"
    sub.mkdir()
    (sub / "mod.py").write_text("")
    head = _git(repo, "rev-parse", "HEAD")
    assert git_state(sub, refresh=True)["commit"] == head
    assert git_state(sub / "mod.py", refresh=True)["commit"] == head


def test_outside_a_repository_it_reports_and_does_not_raise(tmp_path: Path):
    plain = tmp_path / "plain"
    plain.mkdir()
    s = git_state(plain, refresh=True)
    assert set(s) == KEYS
    assert s["commit"] is None and s["dirty"] is None
    assert "not in a git checkout" in s["error"]


def test_a_repository_with_no_commit_yet(tmp_path: Path):
    r = tmp_path / "empty"
    r.mkdir()
    _git(r, "init", "-q")
    s = git_state(r, refresh=True)
    assert s["commit"] is None and "no commit" in s["error"]


def test_without_git_it_reports_and_does_not_raise(repo: Path, monkeypatch):
    monkeypatch.setenv("PATH", "")
    s = git_state(repo, refresh=True)
    assert s["commit"] is None and s["dirty"] is None
    assert "git is not installed" in s["error"]


def test_git_dir_in_the_environment_does_not_redirect_it(repo: Path, tmp_path: Path, monkeypatch):
    """GIT_DIR pointing elsewhere must not make it describe another repository."""
    other = tmp_path / "other"
    other.mkdir()
    _git(other, "init", "-q")
    monkeypatch.setenv("GIT_DIR", str(other / ".git"))
    assert git_state(repo, refresh=True)["commit"] == _git_plain_head(repo)


def _git_plain_head(repo: Path) -> str:
    import os

    env = {k: v for k, v in os.environ.items() if k != "GIT_DIR"}
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True, env=env).stdout.strip()


def test_the_answer_is_remembered_until_refreshed(repo: Path):
    assert git_state(repo, refresh=True)["dirty"] is False
    (repo / "tracked.txt").write_text("two\n")
    assert git_state(repo)["dirty"] is False  # the state the process started with
    assert git_state(repo, refresh=True)["dirty"] is True


def test_the_returned_dict_is_a_copy(repo: Path):
    s = git_state(repo, refresh=True)
    s["modified"].append("tampered")
    assert git_state(repo)["modified"] == []


def test_default_describes_the_checkout_holding_the_imported_package():
    """With no argument it looks at where `fmu` was imported from, not at the
    working directory. Here that is this repository; the commit is whatever CI
    checked out, so only the shape is asserted."""
    import fmu

    s = git_state()
    assert set(s) == KEYS
    if s["root"] is not None:
        assert Path(fmu.__file__).resolve().is_relative_to(Path(s["root"]).resolve())
        assert s["commit"] is None or len(s["commit"]) == 40


# ---------------------------------------------------------------------
# environment_state (round 9)
# ---------------------------------------------------------------------


def test_environment_names_python_earthengine_and_a_freeze_hash():
    from fmu.utils import provenance

    env = provenance.environment_state(refresh=True)
    assert set(env) == {
        "python", "earthengine_api", "pip_freeze_sha256", "pip_freeze_packages",
        "pip_freeze_left_out", "error",
    }
    assert env["python"].count(".") == 2
    assert env["earthengine_api"]
    if env["error"] is None:
        assert len(env["pip_freeze_sha256"]) == 64 and env["pip_freeze_packages"] > 10
    # this package's own line names a commit or a path, so it is not in the hash
    assert all(provenance._is_this_package(ln, provenance._checkout_root())
               for ln in env["pip_freeze_left_out"])


def test_environment_is_remembered_and_copied():
    from fmu.utils import provenance

    a = provenance.environment_state()
    a["python"] = "changed"
    assert provenance.environment_state()["python"] != "changed"


def test_the_package_lines_left_out_of_the_freeze_hash():
    from fmu.utils.provenance import _is_this_package

    root = "/somewhere/phd-code"
    assert _is_this_package("-e git+https://github.com/x/phd-code.git@abc#egg=fmu", root)
    assert _is_this_package("fmu==1.3.0", root)
    assert _is_this_package("-e /somewhere/phd-code", root)
    assert not _is_this_package("-e /elsewhere/other", root)
    assert not _is_this_package("numpy==2.5.1", root)


def test_a_failing_pip_freeze_is_reported_not_raised(monkeypatch):
    import subprocess

    from fmu.utils import provenance

    def boom(*a, **k):
        raise subprocess.TimeoutExpired("pip", 1)

    monkeypatch.setattr(provenance.subprocess, "run", boom)
    env = provenance.environment_state(refresh=True)
    assert env["pip_freeze_sha256"] is None and "could not run" in env["error"]
    monkeypatch.undo()
    provenance.environment_state(refresh=True)

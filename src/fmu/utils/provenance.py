"""Which code ran: the git commit, and whether the checkout had uncommitted changes.

Every run manifest records this (CLAUDE.md, "Results"), so that a result can be
traced to the code that produced it and a run made from a half-edited tree says
so. Result files do not carry it: they hold results only, so that `git diff`
after a re-run shows whether the numbers reproduced, and a hash in them would
make every re-run differ.
"""

from __future__ import annotations

import contextlib
import copy
import os
import subprocess
from pathlib import Path
from typing import Any

# A manifest is not the place for a thousand paths. The lists say what kind of
# change there was; the flags beside them say when they were cut short.
_MAX_LISTED = 50
_TIMEOUT_S = 10

# Untracked paths listed first, before the others, so that run outputs cannot push
# them off the list (review C34, round 13): source and config files, by suffix, and
# untracked folders, which git names as the folder ("dir/") without listing their
# files. Before round 13 the list was sorted as a whole, and 50 untracked outputs in
# odisha_script/phase2_vectors/ sorted before an untracked module in src/ or scripts/.
_CODE_SUFFIXES = (".py", ".pyi", ".pyx", ".sh", ".bash", ".yaml", ".yml", ".toml", ".cfg",
                  ".ini", ".js", ".mjs", ".cjs", ".ts", ".ipynb", ".r", ".sql")


def _code_first(path: str) -> tuple[bool, str]:
    """Sort key: untracked code and untracked folders before everything else, each in path order."""
    is_code = path.endswith("/") or path.lower().endswith(_CODE_SUFFIXES)
    return (not is_code, path)

# One answer per checkout per process. The code a process runs is the code it
# imported when it started, so the state at first asking describes the run only
# if the run asks before it does anything: the pipeline asks when Pipeline.run
# starts, and each script that writes a run record asks at the start of main(),
# before it writes a result (review C32, round 13; until then the first asking
# came after the stages, or after the results were written). It also keeps a
# test suite that writes hundreds of manifests from starting hundreds of git
# processes. `git_state_now` reads the state again, for a record of how the
# tree stood at the end, and remembers nothing.
_cache: dict[str, dict[str, Any]] = {}


def git_state(start: Path | None = None, *, refresh: bool = False) -> dict[str, Any]:
    """Describe the git checkout holding the code that is running.

    `start` is any path inside the checkout. By default it is the imported
    `fmu` package, NOT the working directory: a run can be started in one
    checkout with PYTHONPATH pointing at another, and the manifest must name
    the code that ran.

    Returns a dict that always has these keys:

      commit               full hash of HEAD, or None
      dirty                True if any TRACKED file is modified, staged, deleted
                           or renamed relative to HEAD; False if none; None if
                           it could not be determined
      modified             sorted tracked paths behind `dirty` (at most 50)
      modified_truncated   True if there were more than 50
      untracked            untracked, non-ignored paths (at most 50): first the
                           code (source and config files, by suffix) and the
                           untracked folders, then the rest, each sorted, so
                           that run outputs do not push an untracked source
                           file off the list
      untracked_truncated  True if there were more than 50
      root                 the checkout's root directory, or None
      error                None, or why the state could not be read (git not
                           installed, the code is not in a git checkout, a git
                           command failed)

    Untracked files do not make the tree dirty: a finished run leaves untracked
    outputs behind, and they are not code. They are listed all the same, because
    an untracked source file can change what ran.

    Never raises, never waits more than a few seconds per git call, changes
    nothing in the checkout, and does not depend on the user's git settings.
    The answer is remembered for the life of the process; `refresh=True` asks
    git again.
    """
    if start is None:
        import fmu

        start = Path(fmu.__file__).resolve().parent
    key = str(Path(start).resolve())
    if refresh or key not in _cache:
        _cache[key] = _read_git_state(Path(key))
    return copy.deepcopy(_cache[key])


def git_state_now(start: Path | None = None) -> dict[str, Any]:
    """The state of the same checkout as `git_state`, read again now and not remembered.

    For a record of how the tree stood when a run ended, beside `git_state()`,
    how it stood when the run started: a commit made, or a file edited, while the
    run ran shows as a difference between the two. The keys are those of
    `git_state`. Never raises.
    """
    if start is None:
        import fmu

        start = Path(fmu.__file__).resolve().parent
    return _read_git_state(Path(start).resolve())


def _read_git_state(start: Path) -> dict[str, Any]:
    state: dict[str, Any] = {
        "commit": None,
        "dirty": None,
        "modified": [],
        "modified_truncated": False,
        "untracked": [],
        "untracked_truncated": False,
        "root": None,
        "error": None,
    }
    cwd = start if start.is_dir() else start.parent

    # GIT_DIR and friends would point git at some other repository than the one
    # the code sits in. GIT_OPTIONAL_LOCKS=0 keeps `status` from rewriting the
    # index, so reading the state never touches the checkout.
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_PREFIX")
    }
    env["GIT_OPTIONAL_LOCKS"] = "0"

    def git(*args: str, at: Path) -> tuple[int, str, str]:
        done = subprocess.run(  # noqa: S603 - fixed argv, no shell
            ["git", "-C", str(at), *args],
            capture_output=True,
            timeout=_TIMEOUT_S,
            env=env,
            check=False,
        )
        return (
            done.returncode,
            done.stdout.decode("utf-8", "replace"),
            done.stderr.decode("utf-8", "replace").strip(),
        )

    try:
        rc, out, err = git("rev-parse", "--show-toplevel", at=cwd)
        if rc != 0:
            state["error"] = f"not in a git checkout: {err or 'git rev-parse failed'}"
            return state
        root = Path(out.strip())
        state["root"] = str(root)

        rc, out, err = git("rev-parse", "--verify", "HEAD", at=root)
        if rc == 0:
            state["commit"] = out.strip()
        else:
            state["error"] = f"no commit to name: {err or 'git rev-parse HEAD failed'}"

        rc, out, err = git(
            "status", "--porcelain=v1", "-z", "--untracked-files=normal", at=root
        )
        if rc != 0:
            state["error"] = f"git status failed: {err}"
            return state
    except FileNotFoundError:
        state["error"] = "git is not installed or not on PATH"
        return state
    except subprocess.TimeoutExpired:
        state["error"] = f"git did not answer within {_TIMEOUT_S} s"
        return state
    except (OSError, subprocess.SubprocessError) as e:
        state["error"] = f"could not run git: {type(e).__name__}: {e}"
        return state

    modified: list[str] = []
    untracked: list[str] = []
    entries = out.split("\0")
    i = 0
    while i < len(entries):
        entry = entries[i]
        i += 1
        if len(entry) < 4:
            continue
        code, path = entry[:2], entry[3:]
        if code[0] in "RC":
            i += 1  # a rename or copy is followed by the path it came from
        if code == "??":
            untracked.append(path)
        elif code != "!!":
            modified.append(path)
    modified.sort()
    untracked.sort(key=_code_first)
    state["dirty"] = bool(modified)
    state["modified"] = modified[:_MAX_LISTED]
    state["modified_truncated"] = len(modified) > _MAX_LISTED
    state["untracked"] = untracked[:_MAX_LISTED]
    state["untracked_truncated"] = len(untracked) > _MAX_LISTED
    return state


# ---------------------------------------------------------------------
# Which Python environment ran (round 9): manifests record it beside `git`
# ---------------------------------------------------------------------

_PIP_TIMEOUT_S = 120
_environment: dict[str, Any] | None = None


def environment_state(*, refresh: bool = False) -> dict[str, Any]:
    """The Python environment a run ran in, for its manifest.

    Returns a dict that always has these keys:

      python               the interpreter's version, e.g. "3.13.14"
      earthengine_api      the installed earthengine-api version, or None
      pip_freeze_sha256    SHA-256 of the sorted lines of `python -m pip freeze`,
                           without comment lines and without the line of this
                           package itself, or None
      pip_freeze_packages  how many lines the hash is over
      pip_freeze_left_out  the lines left out of the hash: this package's own,
                           `-e git+...@<commit>#egg=fmu` (or `-e <path>`), which
                           would make two checkouts of one commit differ. Its
                           commit is that of the checkout the venv's editable
                           install points at, when the environment is first
                           read, not always the one the git block records: in a
                           run-tree batch the package is imported from the run
                           tree (PYTHONPATH=<run tree>/src) while the shared
                           venv's editable install is the live checkout, so the
                           two differ (review C33; in 92 of the 108 committed
                           records with both blocks, counted 20 Oct 2026).
                           Nothing reads the line.
      error                None, or why pip freeze could not be read

    Two runs with the same hash ran on the same third-party packages, version for
    version. Never raises; asked once per process (`refresh=True` asks again).
    """
    global _environment
    if _environment is None or refresh:
        _environment = _read_environment()
    return copy.deepcopy(_environment)


def _is_this_package(line: str, checkout: str | None = None) -> bool:
    """A pip freeze line that names this package: `fmu==...`, `...#egg=fmu`, or an
    editable install of the checkout the package sits in (`-e <its root>`)."""
    text = line.strip()
    lower = text.lower()
    if lower.startswith("fmu==") or lower.endswith("#egg=fmu"):
        return True
    if checkout and lower.startswith("-e "):
        target = text[3:].strip()
        return target.rstrip("/") == checkout.rstrip("/")
    return False


def _checkout_root() -> str | None:
    import fmu

    # src/fmu/__init__.py -> the checkout holding src/
    return str(Path(fmu.__file__).resolve().parents[2])


def _read_environment() -> dict[str, Any]:
    import platform
    import sys
    from importlib import metadata

    state: dict[str, Any] = {
        "python": platform.python_version(),
        "earthengine_api": None,
        "pip_freeze_sha256": None,
        "pip_freeze_packages": None,
        "pip_freeze_left_out": [],
        "error": None,
    }
    with contextlib.suppress(metadata.PackageNotFoundError):
        state["earthengine_api"] = metadata.version("earthengine-api")
    try:
        done = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [sys.executable, "-m", "pip", "freeze"],
            capture_output=True,
            timeout=_PIP_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as e:
        state["error"] = f"pip freeze could not run: {type(e).__name__}: {e}"
        return state
    if done.returncode != 0:
        err = done.stderr.decode("utf-8", "replace").strip()[:300]
        state["error"] = f"pip freeze failed: {err}"
        return state
    import hashlib

    lines = [ln.strip() for ln in done.stdout.decode("utf-8", "replace").splitlines()]
    lines = [ln for ln in lines if ln and not ln.startswith("#")]
    checkout = _checkout_root()
    kept = sorted(ln for ln in lines if not _is_this_package(ln, checkout))
    state["pip_freeze_left_out"] = sorted(ln for ln in lines if _is_this_package(ln, checkout))
    state["pip_freeze_sha256"] = hashlib.sha256("\n".join(kept).encode()).hexdigest()
    state["pip_freeze_packages"] = len(kept)
    return state

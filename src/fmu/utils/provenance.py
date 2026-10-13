"""Which code ran: the git commit, and whether the checkout had uncommitted changes.

Every run manifest records this (CLAUDE.md, "Results"), so that a result can be
traced to the code that produced it and a run made from a half-edited tree says
so. Result files do not carry it: they hold results only, so that `git diff`
after a re-run shows whether the numbers reproduced, and a hash in them would
make every re-run differ.
"""

from __future__ import annotations

import copy
import os
import subprocess
from pathlib import Path
from typing import Any

# A manifest is not the place for a thousand paths. The lists say what kind of
# change there was; the flags beside them say when they were cut short.
_MAX_LISTED = 50
_TIMEOUT_S = 10

# One answer per checkout per process. The code a process runs is the code it
# imported when it started, so the state at first asking is the state that
# describes the run; it also keeps a test suite that writes hundreds of
# manifests from starting hundreds of git processes.
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
      untracked            sorted untracked, non-ignored paths (at most 50)
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
    untracked.sort()
    state["dirty"] = bool(modified)
    state["modified"] = modified[:_MAX_LISTED]
    state["modified_truncated"] = len(modified) > _MAX_LISTED
    state["untracked"] = untracked[:_MAX_LISTED]
    state["untracked_truncated"] = len(untracked) > _MAX_LISTED
    return state

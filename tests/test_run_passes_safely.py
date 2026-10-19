"""The batch wrapper, odisha_script/run_passes_safely.py, run against a modelled Earth Engine.

Each test runs the real wrapper and the real run_config_passes.sh in a run tree of its own, with
stand-ins for Earth Engine and for the runner (tests/_wrapper_harness.py); nothing reaches Earth
Engine. The findings are those of the review of 19 Oct 2026 (docs/reviews/2026-10-19-review.md):
B4 to B8 are ways for the wrapper to submit a second copy of a task, B9 a way for it to hang.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from _wrapper_harness import Harness, wait_for

pytestmark = pytest.mark.skipif(shutil.which("bash") is None or shutil.which("git") is None,
                                reason="needs bash and git")

A, B = "cfg_a", "cfg_b"


@pytest.fixture
def h(tmp_path: Path):
    harness = Harness(tmp_path)
    yield harness
    harness.cleanup()


# ---------- B4: a batch started again skips what an earlier batch of its label finished ----------


def test_a_batch_cut_short_records_what_it_finished_and_its_command_does_not_run_that_again(h):
    """Review B4: a batch of A and B stopped with Ctrl-C while B runs, after A's export exit=0.
    Before round 13 its state file read "done": [], and the same command again sent all nine of
    A's Drive exports a second time."""
    a, b = h.config(A), h.config(B)
    h.commit()
    h.scenario(hold=[f"{B}:features"])
    first = h.start(a, b)
    assert wait_for(h.holding), h.log()
    assert f"--- PASS1 {A} export exit=0 ---" in h.log()
    os.killpg(first.pid, signal.SIGINT)  # Ctrl-C: the terminal signals the wrapper's process group
    h.finish(first)
    state = h.state()
    assert (state["done"], state["not_finished"]) == ([A], [B])

    h.scenario()
    rc, out = h.finish(h.start(a, b))
    assert (h.drive_exports(A), h.drive_exports(B)) == ([1] * 9, [1] * 9)
    assert rc == 0, out
    assert [n for _, _, n, _ in h.runners()].count(A) == 4  # A's four passes, in the first batch
    assert f"{A}: skipped, an earlier batch of label batch finished it" in h.log()
    state = h.state()
    assert (state["done"], state["not_finished"]) == ([B], [])
    assert list(state["skipped"]) == [A] and state["earlier_batches"][0]["done"] == [A]


def test_a_batch_started_again_skips_what_an_earlier_one_finished_or_left_for_a_person(h):
    """A config whose export stage failed is left for a person to read the log (needs attention);
    a batch started again under the label leaves it alone too, and does not call itself complete."""
    a, b = h.config(A), h.config(B)
    h.commit()
    h.scenario(fail=[f"{A}:export"])
    rc, out = h.finish(h.start(a, b))
    assert rc == 1, out
    first = h.state()
    assert (first["done"], list(first["needs_attention"])) == ([B], [A])

    h.scenario()
    rc, out = h.finish(h.start(a, b))
    assert (h.drive_exports(A), h.drive_exports(B)) == ([1] * 9, [1] * 9)
    assert (rc, len(h.runners())) == (1, 8), out  # no runner started by the second batch
    second = h.state()
    first.pop("earlier_batches")  # the earlier batches are kept in one list, oldest first
    assert list(second["skipped"]) == [A, B] and second["earlier_batches"] == [first]
    assert (second["done"], second["needs_attention"], second["not_finished"]) == ([], {}, [])
    assert h.log().splitlines()[-1].endswith("batch batch ended: NOT ALL COMPLETE")


# ---------- B6, B7: one lock per machine, taken first ----------


def test_two_starts_a_moment_apart_run_one_batch(h):
    """Review B6: the lock was checked first but written only after `import ee` and
    ee.Initialize (about 8 s on the Mac), so two starts 0.3 s apart both ran every task."""
    a = h.config(A)
    h.commit()
    h.scenario(hold=[f"{A}:features"])
    first = h.start(a, import_s=2.0)
    time.sleep(0.3)
    second = h.start(a, import_s=2.0)
    wait_for(lambda: first.poll() is not None or second.poll() is not None or len(h.holding()) == 2)
    h.release()
    results = [h.finish(p) for p in (first, second)]
    assert sorted(rc for rc, _ in results) == [0, 90], results
    assert any("REFUSING: a batch with pid" in out for _, out in results)
    assert (h.drive_exports(A), h.second_copies_while_running()) == ([1] * 9, [])


def test_a_second_batch_with_another_log_folder_is_refused(h):
    """Review B7: the lock lived in the log folder, so a batch with another --log-dir (or another
    run tree's logs/) did not see it."""
    a = h.config(A)
    h.commit()
    h.scenario(hold=[f"{A}:features"])
    first = h.start(a, "--log-dir", str(h.root / "logs_a"))
    assert wait_for(h.holding)
    second = h.start(a, "--log-dir", str(h.root / "logs_b"))
    wait_for(lambda: second.poll() is not None or len(h.holding()) == 2)
    h.release()
    (rc1, out1), (rc2, out2) = h.finish(first), h.finish(second)
    assert (rc1, rc2) == (0, 90), out1 + out2
    assert f"REFUSING: a batch with pid {first.pid} is still running" in out2
    assert h.drive_exports(A) == [1] * 9
    assert (h.home / ".fmu" / "run_passes_safely.lock").exists()


def test_the_label_names_the_log_and_the_state_file_not_the_lock():
    wrapper = Path(__file__).resolve().parent.parent / "odisha_script" / "run_passes_safely.py"
    out = subprocess.run([sys.executable, str(wrapper), "--help"], capture_output=True, text=True,
                         timeout=60).stdout
    label = " ".join(out.split("--label LABEL")[-1].split())
    assert label.startswith("names the log and the state file"), label
    assert "lock" not in label.split("--run-tree")[0]

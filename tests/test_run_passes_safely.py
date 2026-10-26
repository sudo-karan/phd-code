"""The batch wrapper, odisha_script/run_passes_safely.py, run against a modelled Earth Engine.

Each test runs the real wrapper and the real run_config_passes.sh in a run tree of its own, with
stand-ins for Earth Engine and for the runner (tests/_wrapper_harness.py); nothing reaches Earth
Engine. The findings are those of the review of 19 Oct 2026 (docs/reviews/2026-10-19-review.md):
B4 to B8 are ways for the wrapper to submit a second copy of a task, B9 a way for it to hang.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from _wrapper_harness import FEATURE_OUTPUTS, Harness, alive, wait_for

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


@pytest.mark.parametrize("sig", [signal.SIGTERM, signal.SIGHUP, signal.SIGINT],
                         ids=["SIGTERM", "SIGHUP", "SIGINT"])
def test_a_stop_during_the_export_stage_leaves_the_config_for_a_person(h, sig):
    """A check of the B4 fix (round 13): a signal while the export stage ran, after it had sent its
    Drive exports, left no exit line for the stage, so the config was recorded as not finished and
    the same command again sent all nine Drive exports a second time. Now it needs attention, as a
    config whose export stage failed does."""
    a = h.config(A)
    h.commit()
    h.scenario(hold_after_submit=[f"{A}:export"])
    w = h.start(a)
    assert wait_for(h.holding), h.log()
    assert h.drive_exports(A) == [1] * 9
    os.kill(w.pid, sig)
    rc, out = h.finish(w)
    assert rc == 128 + sig, out
    state = h.state()
    assert (state["done"], state["not_finished"], list(state["needs_attention"])) == ([], [], [A])

    h.scenario()
    rc, out = h.finish(h.start(a))
    assert h.drive_exports(A) == [1] * 9
    assert rc == 1, out
    assert f"{A}: skipped, an earlier batch of label batch put it under needs attention" in h.log()


def test_a_save_cut_short_leaves_the_earlier_state_whole(h):
    """A check of the B4 fix (round 13): the state file, which a batch started again reads first,
    was rewritten in place, so a save cut short (here every write of it stops halfway, as on a
    full disk) left it half written, and every later start of the label stopped on it. Now the
    earlier batch's record is left as it was."""
    a, b = h.config(A), h.config(B)
    h.commit()
    rc, out = h.finish(h.start(a))
    assert rc == 0, out
    before = h.state()
    rc, out = h.finish(h.start(a, b, save_fails=True))
    assert rc == 1 and "No space left on device (the harness)" in out, out
    assert h.state() == before
    assert not list((h.rt / "logs").glob("*.tmp"))


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


# ---------- B9: a request deadline on the queue poll ----------


def test_the_queue_poll_has_a_request_deadline(h):
    """Review B9: the client's default deadline is none, so a poll caught by a network drop (the
    laptop asleep) never returned and the batch stalled with no log line. The runner sets one."""
    a = h.config(A)
    h.commit()
    w = h.start(a)
    rc, out = h.finish(w)
    assert rc == 0, out
    assert h.ee_calls(w.pid)[:3] == ["Initialize", "setDeadline 120000", "listOperations"]


# ---------- B5: a signal to the wrapper reaches the shell script and the runner ----------


@pytest.mark.parametrize("sig", [signal.SIGTERM, signal.SIGHUP, signal.SIGINT],
                         ids=["SIGTERM", "SIGHUP", "SIGINT"])
def test_a_signal_to_the_wrapper_ends_the_shell_script_and_the_runner_first(h, sig):
    """Review B5: SIGTERM, SIGHUP or SIGINT to the wrapper's pid left run_config_passes.sh and the
    runner running (SIGINT killed the shell only), and the next start ran beside them."""
    a = h.config(A)
    h.commit()
    h.scenario(hold=[f"{A}:features"])
    w = h.start(a)
    assert wait_for(h.holding)
    ((runner, shell, _, _),) = h.runners()
    os.kill(w.pid, sig)
    rc, out = h.finish(w)
    assert [alive(shell), alive(runner)] == [False, False]
    assert rc == 128 + sig, out
    assert h.log().splitlines()[-1].endswith(
        f"batch batch ended: NOT ALL COMPLETE (stopped by {signal.Signals(sig).name})")
    assert h.state()["not_finished"] == [A]


def test_a_start_while_the_runner_of_a_stopped_batch_still_ends_is_refused(h):
    """SIGTERM reaches the runner, which takes a while to end (here 5 s); the wrapper waits for it
    before it lets go of the lock, so a start in the meantime is refused."""
    a = h.config(A)
    h.commit()
    h.scenario(hold=[f"{A}:features"], linger_on_term_s=5.0)
    w = h.start(a)
    assert wait_for(h.holding)
    ((runner, shell, _, _),) = h.runners()
    os.kill(w.pid, signal.SIGTERM)
    wait_for(lambda: h.ended(w) or list(h.ee.glob("terminating_*")), timeout=10)
    second = h.start(a)
    wait_for(lambda: second.poll() is not None or len(h.holding()) == 2)
    h.release()
    rc2, out2 = h.finish(second)
    assert rc2 == 90, out2
    h.finish(w)
    assert [alive(shell), alive(runner)] == [False, False]
    assert (h.drive_exports(A), h.second_copies_while_running()) == ([0] * 9, [])


def test_the_lock_is_held_while_the_children_of_a_killed_wrapper_run(h):
    """SIGKILL cannot be caught: the shell script and the runner run on, and hold the lock (they
    were given its descriptor), so a new start is refused until they have ended."""
    a = h.config(A)
    h.commit()
    h.scenario(hold=[f"{A}:features"])
    w = h.start(a)
    assert wait_for(h.holding)
    ((runner, shell, _, _),) = h.runners()
    os.kill(w.pid, signal.SIGKILL)
    h.finish(w)
    second = h.start(a)
    wait_for(lambda: second.poll() is not None or len(h.holding()) == 2)
    for pid in (runner, shell):  # the killed batch's children end
        os.kill(pid, signal.SIGKILL)
    h.release()
    rc2, out2 = h.finish(second)
    assert rc2 == 90, out2
    assert wait_for(lambda: not alive(runner) and not alive(shell))
    rc3, out3 = h.finish(h.start(a))  # the children have ended, so the lock is free
    assert rc3 == 0, out3


def test_a_signal_while_the_wrapper_waits_on_the_queue_is_acted_on(h):
    """A check of the B5 fix (round 13): the handler set a threading.Event, whose lock
    Event.wait holds for a moment on each call, and a signal that came in that moment left the
    handler waiting for the lock forever, the wrapper hung and holding the batch lock. The harness
    widens the moment to the whole wait, so the signal comes in it every time."""
    a = h.config(A)
    h.commit()
    now = time.time()
    (h.ee / "tasks.json").write_text(json.dumps([{
        "id": "T0001", "description": f"{A}_features_static_static_features", "submitted": now,
        "done_at": now + 3600, "pid": 0}]))
    w = h.start(a, poll_s=5.0, wide_event_wait=True)
    assert wait_for(lambda: "before pass 1: 1 task(s) of these configs still queued" in h.log())
    time.sleep(0.5)  # into the wait after the poll
    os.kill(w.pid, signal.SIGTERM)
    assert wait_for(lambda: h.ended(w), timeout=10), "the wrapper is stuck in its signal handler"
    rc, out = h.finish(w)
    assert rc == 128 + signal.SIGTERM, out
    assert h.runners() == []


def test_a_signal_ignored_when_the_batch_started_stays_ignored(h):
    """A batch started under nohup ignores SIGHUP, as before: closing the terminal it was started
    from does not stop it. A guard, for the handlers B5 adds."""
    a = h.config(A)
    h.commit()
    h.scenario(hold=[f"{A}:features"])
    w = h.start(a, nohup=True)
    assert wait_for(h.holding)
    os.kill(w.pid, signal.SIGHUP)
    time.sleep(1.0)
    h.release()
    rc, out = h.finish(w)
    assert rc == 0, out
    assert h.drive_exports(A) == [1] * 9


# ---------- B8: a config is its name:, which names its tasks ----------


def test_a_config_path_that_does_not_end_in_yaml_is_refused(h):
    """Review B8: a .yml copy was never recognised as finished, so its export pass, and its
    Drive exports, ran again in every pass."""
    yml = h.config(A, path=f"configs/{A}.yml")
    h.commit()
    rc, out = h.finish(h.start(yml))
    assert (rc, len(h.tasks())) == (93, 0), out
    assert f"REFUSING: {yml} is not a .yaml file" in out


def test_a_config_whose_name_is_not_its_file_stem_is_refused(h):
    """Review B8: a copy whose name: was not edited names its tasks after A, while the wrapper
    waited on its file stem: after a failed features pass the next pass started at once and sent
    a second copy of every export still running."""
    copy = h.config(A, path=f"configs/{A}_copy.yaml")
    h.commit()
    h.scenario(fail_once=[f"{A}:features"], task_s=6.0)
    rc, out = h.finish(h.start(copy))
    assert (rc, len(h.second_copies_while_running())) == (93, 0), out
    assert f"REFUSING: {copy} has name: {A}, not its file stem {A}_copy" in out
    assert h.tasks() == []


@pytest.mark.parametrize("again", [None, f"configs/again/{A}.yaml"], ids=["same path", "same name"])
def test_a_config_listed_twice_is_refused(h, again):
    """Review B8: a config listed twice ran twice in every pass and sent its Drive exports twice."""
    a = h.config(A)
    other = a if again is None else h.config(A, path=again)
    h.commit()
    rc, out = h.finish(h.start(a, other))
    assert (rc, len(h.tasks())) == (93, 0), out
    assert f"REFUSING: {A} is listed twice" in out


def test_the_wait_before_a_pass_matches_the_tasks_named_after_the_config(h):
    """The features pass fails once with its exports still running; the next pass waits for them
    (they are named after the config's name:), and then finds every one in the cache. A guard:
    this held before round 13 too, for a config whose name: is its file stem."""
    a = h.config(A)
    h.commit()
    h.scenario(fail_once=[f"{A}:features"], task_s=5.0)
    rc, out = h.finish(h.start(a))
    assert rc == 0, out
    assert h.second_copies_while_running() == []
    assert [h.submitted(f"{A}_{o}") for o in FEATURE_OUTPUTS] == [1] * 9
    assert "before pass 2: 9 task(s) of these configs still queued or running" in h.log()

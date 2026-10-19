"""A modelled Earth Engine for the batch wrapper, for tests/test_run_passes_safely.py.

`Harness` builds a run tree in a temporary folder: a git repository holding copies of the real
odisha_script/run_passes_safely.py and odisha_script/run_config_passes.sh, a few configs (copies of a
real config with only `name:` changed), a stand-in for the runner at
odisha_script/odisha_phase2_2_run_pipeline.py, and a stand-in `ee` package in its src/, which the
wrapper finds first (it puts <run tree>/src at the front of sys.path, then imports ee). src/fmu is a
link to this checkout's package, so the wrapper reads the configs with the real fmu.config.

`start()` runs the real wrapper's main() in a process of its own, with POLL_S made small by setting
the module attribute before main() runs, and with a `sleep` on PATH that sleeps 0.05 s whatever it
is asked, for the shell script's `sleep 60`. Neither script is changed. HOME is a temporary folder.

The stand-ins share one folder (`self.ee`, $FAKE_EE_DIR):

  - tasks.json      every task "submitted", in order: description, submitted, done_at. A task is
                    RUNNING until done_at, then SUCCEEDED; a cached asset exists once a task that
                    exports it has succeeded.
  - ee_calls.txt    the calls the wrapper made of the stand-in ee, in order.
  - runners.txt     one line per runner started: pid, the shell script's pid, config name, pass.
  - scenario.json   what the runner does (`scenario()`): how long a task runs, a pass that fails
                    once (as on a cold cache, after submitting its exports), an export pass that
                    fails, a pass that holds until `release()`, a runner slow to end on SIGTERM.

The runner names every task after the config's `name:`, as the pipeline does
(`f"{config.name}_{stage.name}_{key}"`), and does what the real runner does that matters here: each
pass after the first refuses (exit 3) while an upstream asset is missing, a pass submits an export of
every asset of its own that does not exist yet (so a second copy of one still running), the passes
before export wait for their own tasks (--wait), and the export pass submits the nine Drive exports
and does not wait.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REAL_CONFIG = REPO / "configs" / "sanjay_van_baseline_keptland.yaml"

FEATURE_OUTPUTS = (
    "masking_habitat_mask", "masking_water_mask", "masking_landcover_summary",
    "masking_mask_provenance", "data_load_s2_composite", "features_optical_optical_features",
    "features_radar_radar_features", "features_structure_structure_features",
    "features_static_static_features",
)
DRIVE_FILES = ("cluster_labels", "features_raw", "features_scaled") + tuple(
    f"stands_{layer}_{fmt}" for layer in ("merged", "snic", "dissolved") for fmt in ("shp", "geojson"))

FAKE_EE = '''"""A stand-in for the earthengine-api package (tests/_wrapper_harness.py): no network."""
import json
import os
import time

_DIR = os.environ["FAKE_EE_DIR"]
time.sleep(float(os.environ.get("FAKE_EE_IMPORT_S", "0")))  # the real import takes seconds


def _record(what):
    with open(os.path.join(_DIR, "ee_calls.txt"), "a") as f:
        f.write(f"{os.getpid()} {what}\\n")


def Initialize(*args, **kwargs):
    _record("Initialize")


class data:
    @staticmethod
    def setDeadline(milliseconds):
        _record(f"setDeadline {milliseconds}")

    @staticmethod
    def listOperations(*args, **kwargs):
        _record("listOperations")
        path = os.path.join(_DIR, "tasks.json")
        tasks = json.load(open(path)) if os.path.exists(path) else []
        now = time.time()
        return [{"name": "projects/p/operations/" + t["id"],
                 "metadata": {"description": t["description"],
                              "state": "RUNNING" if now < t["done_at"] else "SUCCEEDED"}}
                for t in tasks]
'''

FAKE_RUNNER = '''"""A stand-in for odisha_phase2_2_run_pipeline.py (tests/_wrapper_harness.py): no Earth Engine."""
import argparse
import fcntl
import json
import os
import re
import signal
import sys
import time
from pathlib import Path

D = Path(os.environ["FAKE_EE_DIR"])
SCENARIO = json.loads((D / "scenario.json").read_text()) if (D / "scenario.json").exists() else {}
#: the harness's FEATURE_OUTPUTS and DRIVE_FILES
CACHED = {
    "features": FEATURE_OUTPUTS,
    "segmentation": ("segmentation_snic_clusters", "segmentation_snic_means"),
    "clustering": ("clustering_cluster_labels", "clustering_feature_stack"),
}
UPSTREAM = {"features": (), "segmentation": ("features",), "clustering": ("features", "segmentation"),
            "export": ("features", "segmentation", "clustering")}
DRIVE = DRIVE_FILES


def read_tasks():
    path = D / "tasks.json"
    return json.loads(path.read_text()) if path.exists() else []


def exists(description):
    now = time.time()
    return any(t["description"] == description and now >= t["done_at"] for t in read_tasks())


def submit(descriptions):
    with open(D / "tasks.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        tasks, now, ids = read_tasks(), time.time(), []
        for d in descriptions:
            ids.append(f"T{len(tasks) + 1:04d}")
            tasks.append({"id": ids[-1], "description": d, "submitted": now,
                          "done_at": now + SCENARIO.get("task_s", 0.2), "pid": os.getpid()})
        tmp = D / f"tasks.{os.getpid()}.tmp"
        tmp.write_text(json.dumps(tasks, indent=1))
        os.replace(tmp, D / "tasks.json")
    return ids


def linger(signum, frame):
    (D / f"terminating_{os.getpid()}").write_text("")
    time.sleep(SCENARIO["linger_on_term_s"])
    sys.exit(128 + signum)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--through", required=True)
    ap.add_argument("--wait", action="store_true")
    a = ap.parse_args()
    name = re.search(r"^name:[ ]*(\\S+)", Path(a.config).read_text(), re.M).group(1)
    with open(D / "runners.txt", "a") as f:
        f.write(f"{os.getpid()} {os.getppid()} {name} {a.through}\\n")
    print(f"{name} fingerprint=0123456789 through={a.through}", flush=True)
    print("  cache layout: per_step (its cache holds no asset of the legacy layout)", flush=True)
    me = f"{name}:{a.through}"
    if me in SCENARIO.get("hold", []):
        if SCENARIO.get("linger_on_term_s"):
            signal.signal(signal.SIGTERM, linger)
        (D / f"holding_{name}_{a.through}_{os.getpid()}").write_text("")
        while not (D / "release").exists():
            time.sleep(0.05)
    gaps = [f"{name}_{o}" for s in UPSTREAM[a.through] for o in CACHED[s] if not exists(f"{name}_{o}")]
    if gaps:
        print(f"  REFUSING: {len(gaps)} upstream cache asset(s) missing; run the earlier pass first:")
        for g in gaps:
            print(f"    {g}")
        return 3
    if a.through == "export":
        for tid, f in zip(submit([f"{name}_{f}" for f in DRIVE]), DRIVE):
            print(f"  submitted Drive export: task_id={tid}, file='{name}_{f}'")
        if me in SCENARIO.get("fail", []):
            print("ee.ee_exception.EEException: Computation timed out.")
            return 1
        print(f"  wrote {name}_run.json")
        return 0  # the export pass does not wait for its Drive exports
    todo = [f"{name}_{o}" for o in CACHED[a.through] if not exists(f"{name}_{o}")]
    ids = submit(todo)
    for tid, d in zip(ids, todo):
        print(f"Started cache export to .../{d} (task {tid}).")
    failed_once = D / f"failed_{name}_{a.through}"
    if me in SCENARIO.get("fail_once", []) and not failed_once.exists():
        failed_once.write_text("")
        print("ee.ee_exception.EEException: User memory limit exceeded.")
        return 1
    if a.wait:
        if not ids:
            print("  no export tasks submitted by this pass")
        else:
            print(f"  waiting on {len(ids)} task(s)")
            while any(t["id"] in ids and time.time() < t["done_at"] for t in read_tasks()):
                time.sleep(0.05)
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''.replace("#: the harness's FEATURE_OUTPUTS and DRIVE_FILES\n",
           f"FEATURE_OUTPUTS = {FEATURE_OUTPUTS!r}\nDRIVE_FILES = {DRIVE_FILES!r}\n")
assert "FEATURE_OUTPUTS = (" in FAKE_RUNNER and "DRIVE_FILES = (" in FAKE_RUNNER

# Runs the real wrapper's main(), with POLL_S set first. argv: the wrapper's path, then its arguments.
DRIVER = '''
import importlib.util
import os
import sys

path = sys.argv[1]
spec = importlib.util.spec_from_file_location("run_passes_safely", path)
wrapper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wrapper)
wrapper.POLL_S = float(os.environ["HARNESS_POLL_S"])
sys.argv = [path, *sys.argv[2:]]
sys.exit(wrapper.main())
'''


def alive(pid: int) -> bool:
    """Whether the process is running (a zombie is not)."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    stat = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)],
                          capture_output=True, text=True).stdout.strip()
    return bool(stat) and not stat.startswith("Z")


def wait_for(what: Callable[[], object], timeout: float = 60.0, step: float = 0.05) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if what():
            return True
        time.sleep(step)
    return bool(what())


class Harness:
    def __init__(self, root: Path):
        self.root = root
        self.rt = root / "run_tree"
        self.ee = root / "ee"
        self.home = root / "home"
        self.bin = root / "bin"
        self.wrappers: list[subprocess.Popen] = []
        self.outputs: dict[int, Path] = {}
        for d in (self.rt / "odisha_script", self.rt / "src" / "ee", self.rt / "configs", self.ee,
                  self.home, self.bin):
            d.mkdir(parents=True)
        for script in ("run_passes_safely.py", "run_config_passes.sh"):
            shutil.copy2(REPO / "odisha_script" / script, self.rt / "odisha_script" / script)
        (self.rt / "odisha_script" / "odisha_phase2_2_run_pipeline.py").write_text(FAKE_RUNNER)
        (self.rt / "src" / "ee" / "__init__.py").write_text(FAKE_EE)
        (self.rt / "src" / "fmu").symlink_to(REPO / "src" / "fmu", target_is_directory=True)
        sleep = self.bin / "sleep"
        sleep.write_text("#!/bin/sh\nexec /bin/sleep 0.05\n")
        sleep.chmod(0o755)
        self.scenario()

    # ---------- the run tree ----------

    def config(self, name: str, path: str | None = None) -> str:
        """A copy of a real config with `name:` set; its path relative to the run tree."""
        rel = path or f"configs/{name}.yaml"
        text, n = re.subn(r"(?m)^name:.*$", f"name: {name}", REAL_CONFIG.read_text(), count=1)
        assert n == 1
        (self.rt / rel).parent.mkdir(parents=True, exist_ok=True)
        (self.rt / rel).write_text(text)
        return rel

    def commit(self) -> None:
        def git(*args: str) -> None:
            subprocess.run(["git", "-c", "user.name=harness", "-c", "user.email=harness@example.org",
                            "-c", "commit.gpgsign=false", "-C", str(self.rt), *args],
                           check=True, capture_output=True)
        git("init", "-q")
        git("add", "-A")
        git("commit", "-q", "-m", "run tree")

    def scenario(self, **kw: object) -> None:
        (self.ee / "scenario.json").write_text(json.dumps(kw))

    # ---------- the wrapper ----------

    def start(self, *args: str, label: str = "batch", import_s: float = 0.0) -> subprocess.Popen:
        """The real wrapper's main() in a process group of its own, as a terminal starts it."""
        env = {**os.environ, "HOME": str(self.home), "FAKE_EE_DIR": str(self.ee),
               "FAKE_EE_IMPORT_S": str(import_s), "HARNESS_POLL_S": "0.1",
               "PATH": f"{self.bin}{os.pathsep}{os.environ.get('PATH', '')}"}
        # Its output goes to a file, not a pipe: the shell script and the runner inherit it, and a
        # pipe would stay open for as long as they run.
        out = self.root / f"wrapper_{len(self.wrappers) + 1}.out"
        with out.open("w") as f:
            p = subprocess.Popen(
                [sys.executable, "-c", DRIVER, str(self.rt / "odisha_script" / "run_passes_safely.py"),
                 "--label", label, *args],
                cwd=self.root, env=env, stdout=f, stderr=subprocess.STDOUT, start_new_session=True)
        self.wrappers.append(p)
        self.outputs[p.pid] = out
        return p

    def finish(self, p: subprocess.Popen, timeout: float = 120.0) -> tuple[int, str]:
        """Its exit code and output, once it has ended."""
        p.wait(timeout=timeout)
        return p.returncode, self.outputs[p.pid].read_text()

    def ended(self, p: subprocess.Popen) -> bool:
        """Whether it has ended; reaps it if so (a process not yet reaped looks alive to os.kill)."""
        return p.poll() is not None

    def release(self) -> None:
        (self.ee / "release").write_text("")

    # ---------- what happened ----------

    def log(self, label: str = "batch", log_dir: Path | None = None) -> str:
        path = (log_dir or self.rt / "logs") / f"{label}.log"
        return path.read_text() if path.exists() else ""

    def state(self, label: str = "batch", log_dir: Path | None = None) -> dict:
        return json.loads(((log_dir or self.rt / "logs") / f"{label}.state.json").read_text())

    def tasks(self) -> list[dict]:
        path = self.ee / "tasks.json"
        return json.loads(path.read_text()) if path.exists() else []

    def submitted(self, description: str) -> int:
        return sum(t["description"] == description for t in self.tasks())

    def drive_exports(self, name: str) -> list[int]:
        """How many times each of the config's nine Drive exports was submitted."""
        return [self.submitted(f"{name}_{f}") for f in DRIVE_FILES]

    def second_copies_while_running(self) -> list[str]:
        """Tasks submitted while an earlier copy of the same task was still queued or running."""
        tasks = self.tasks()
        return [t["description"] for i, t in enumerate(tasks)
                if any(e["description"] == t["description"] and e["submitted"] <= t["submitted"]
                       < e["done_at"] for e in tasks[:i])]

    def runners(self) -> list[tuple[int, int, str, str]]:
        """(pid, the shell script's pid, config name, pass) of every runner started, in order."""
        path = self.ee / "runners.txt"
        lines = path.read_text().splitlines() if path.exists() else []
        return [(int(p), int(g), n, s) for p, g, n, s in (line.split() for line in lines)]

    def holding(self) -> list[Path]:
        return sorted(self.ee.glob("holding_*"))

    def ee_calls(self, pid: int) -> list[str]:
        path = self.ee / "ee_calls.txt"
        lines = path.read_text().splitlines() if path.exists() else []
        return [line.split(" ", 1)[1] for line in lines if line.split(" ", 1)[0] == str(pid)]

    # ---------- clean up ----------

    def cleanup(self) -> None:
        """Ends everything the tests started: the wrappers' groups, the runners and the shells."""
        self.release()
        for p in self.wrappers:
            if p.poll() is None:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(p.pid, signal.SIGKILL)
            try:
                p.wait(timeout=30)
            except subprocess.TimeoutExpired:
                p.kill()
        for pid, shell, _, _ in self.runners():
            for target in (pid, shell):
                command = subprocess.run(["ps", "-o", "command=", "-p", str(target)],
                                         capture_output=True, text=True).stdout
                if alive(target) and ("odisha_phase2_2_run_pipeline" in command
                                      or "run_config_passes" in command):
                    os.kill(target, signal.SIGKILL)

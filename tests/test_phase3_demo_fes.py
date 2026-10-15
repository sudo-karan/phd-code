"""odisha_script/odisha_phase3_demo_fes.py and odisha_phase3_demo_sigwrap.py: the FES comparison on new stands.

Offline: no Earth Engine, no network. The fast tests use hand-built stand files, temporary
git repositories and the committed HAND-CRAFTED Phase 3 result files. The tests marked slow
run the real scripts on the committed hand-crafted stands at 120 rotations: about 15 minutes
of processor time over eight processes, measured as 27 minutes on a heavily shared machine.
They are skipped by default: `pytest -m slow tests/test_phase3_demo_fes.py`.

No AlphaEarth score is computed or read anywhere in this file. The AlphaEarth analysis has
to be declared first (CLAUDE.md, "Results"), so its path is tested through what it shares
with the hand-crafted arms: the same wrapper run on one hand-crafted arm alone, the arm
bookkeeping with no data, and an invented arm name for the parser.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
ODISHA = REPO / "odisha_script"
sys.path.insert(0, str(ODISHA))

import odisha_phase3_demo_fes as D  # noqa: E402, N812
import odisha_phase3_demo_sigwrap as W  # noqa: E402, N812

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
RULE = "a merge rule that no declaration names (test)"
SQUARE = {"type": "Polygon",
          "coordinates": [[[85.0, 20.0], [85.001, 20.0], [85.001, 20.001], [85.0, 20.001], [85.0, 20.0]]]}


def write_stand_file(path: Path, layer: str) -> None:
    """One square stand with the properties the join reads from that layer."""
    props = {D.LAYER_ID[layer]: 1, "cluster_id": 2.0, "area_ha": 1.2}
    path.write_text(json.dumps({"type": "FeatureCollection",
                                "features": [{"type": "Feature", "properties": props, "geometry": SQUARE}]}))


def make_stands(folder: Path, arms: list[str], suffix: str, layers: list[str]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for arm in arms:
        for d in D.DISTRICTS:
            for layer in layers:
                write_stand_file(folder / f"{D.ARMS[arm]['config']}_{d}{suffix}_{layer}.geojson", layer)


def git(repo: Path, *args: str) -> str:
    got = subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.org",
                          "-c", "commit.gpgsign=false", *args], capture_output=True, text=True, check=True)
    return got.stdout.strip()


# --------------------------------------------------------------------------- staging
def test_the_twelve_configs_are_the_ones_the_join_knows():
    import odisha_phase2_3_join as J  # noqa: N812

    assert {a: D.ARMS[a]["config"] for a in D.ARMS} == {a: J.ALL_ARMS[a] for a in D.ARMS}
    assert J.DISTRICTS == D.DISTRICTS
    assert {name: field for name, field in J.LAYERS.values()} == D.LAYER_ID


def test_staging_names_and_fallbacks(tmp_path: Path):
    stands, fallback, staged = tmp_path / "new", tmp_path / "old", tmp_path / "staged"
    # the re-merge folder: every merged layer, and the snic layer of one arm only
    make_stands(stands, list(D.ARMS), "_repro", ["stands_merged"])
    make_stands(stands, ["v120"], "_repro", ["stands_snic"])
    make_stands(fallback, list(D.ARMS), "_repro", ["stands_merged", "stands_snic", "stands_dissolved"])
    # files that must never sit beside new stands
    for tail in ("run.json", "raster_at_plots.csv"):
        (stands / f"odisha_v120_handcrafted_angul_repro_{tail}").write_text("{}")
        (fallback / f"odisha_v120_handcrafted_angul_repro_{tail}").write_text("{}")

    plan = D.plan_staging(stands, "_repro", fallback, list(D.ARMS))
    assert len(plan) == 3 * 4 * 3
    by_name = {i["staged_as"]: i for i in plan}
    assert "odisha_v120_3ha_koraput_stands_merged.geojson" in by_name          # the suffix is gone
    assert all("_repro" not in n for n in by_name)
    assert all(i["from"] == "stands-dir" for i in plan if i["layer"] == "stands_merged")
    assert by_name["odisha_v120_handcrafted_angul_stands_snic.geojson"]["from"] == "stands-dir"
    assert by_name["odisha_alphaearth_angul_stands_snic.geojson"]["from"] == "fallback-vectors"
    assert all(i["from"] == "fallback-vectors" for i in plan if i["layer"] == "stands_dissolved")
    for i in plan:
        D.check_stand_file(i["source"], i["layer"])

    staged.mkdir()
    D.stage(plan, staged)
    assert sorted(p.name for p in staged.iterdir()) == sorted(by_name)
    assert not [p.name for p in staged.iterdir() if p.name.endswith(("run.json", "raster_at_plots.csv"))]
    assert (staged / "odisha_alphaearth_angul_stands_snic.geojson").resolve().parent == fallback.resolve()
    record = D.staged_record(plan)
    one = record["odisha_alphaearth_angul_stands_snic.geojson"]
    assert one["from"] == "fallback-vectors" and one["sha256"] == D.sha256(by_name[
        "odisha_alphaearth_angul_stands_snic.geojson"]["source"])


def test_a_merged_layer_is_never_taken_from_the_fallback(tmp_path: Path, capsys):
    stands, fallback = tmp_path / "new", tmp_path / "old"
    make_stands(stands, ["v120"], "_repro", ["stands_snic", "stands_dissolved"])
    make_stands(fallback, ["v120"], "_repro", ["stands_merged", "stands_snic", "stands_dissolved"])
    with pytest.raises(D.Refused) as e:
        D.plan_staging(stands, "_repro", fallback, ["v120"])
    assert e.value.code == 2
    assert "4 stand file(s) not found" in e.value.why
    assert "odisha_v120_handcrafted_koraput_repro_stands_merged.geojson" in e.value.why


def test_a_stand_file_written_for_the_ui_is_refused(tmp_path: Path):
    ui = tmp_path / "odisha_v120_3ha_angul_repro_stands_merged.geojson"
    ui.write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"stand_id": 1, "stand_type": 2, "area_ha": 1.0}, "geometry": SQUARE}]}))
    with pytest.raises(D.Refused) as e:
        D.check_stand_file(ui, "stands_merged")
    assert "stand_lbl" in e.value.why
    untyped = tmp_path / "untyped.geojson"
    untyped.write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"stand_lbl": 1}, "geometry": SQUARE}]}))
    with pytest.raises(D.Refused):
        D.check_stand_file(untyped, "stands_merged")
    with pytest.raises(D.Refused):
        D.check_stand_file(tmp_path / "absent.geojson", "stands_merged")


@pytest.mark.parametrize("out", [ODISHA, REPO, ODISHA / "phase2_vectors", ODISHA / "phase3_3ha",
                                 ODISHA / "phase3_before_regroup", ODISHA / "phase3_3ha" / "new"])
def test_protected_folders_are_refused(out: Path, tmp_path: Path):
    with pytest.raises(D.Refused):
        D.check_out_dir(out, [tmp_path])


def test_the_stands_folder_is_refused_as_out_dir(tmp_path: Path):
    stands = tmp_path / "stands"
    stands.mkdir()
    for out in (stands, stands / "results", tmp_path):
        with pytest.raises(D.Refused):
            D.check_out_dir(out, [stands])
    D.check_out_dir(tmp_path / "results", [stands])        # a folder of its own: accepted, and not created
    assert not (tmp_path / "results").exists()


@needs_git
def test_a_folder_holding_another_analysis_is_refused(tmp_path: Path):
    repo = tmp_path / "repo"
    (repo / "theirs").mkdir(parents=True)
    (repo / "ours").mkdir()
    git(repo, "init", "-q")
    (repo / "theirs" / "some_other_results.txt").write_text("x\n")
    (repo / "ours" / "README.md").write_text("x\n")
    (repo / "ours" / "odisha_phase3_3_results.txt").write_text("x\n")
    (repo / "ours" / D.MANIFEST_NAME).write_text("{}\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "results")
    with pytest.raises(D.Refused) as e:
        D.check_out_dir(repo / "theirs", [tmp_path / "stands"])
    assert "another analysis" in e.value.why
    D.check_out_dir(repo / "ours", [tmp_path / "stands"])   # its own files and a README: accepted here


# --------------------------------------------------------------------------- the commands
def test_commands_follow_the_reproducing_section(tmp_path: Path):
    staged, out = tmp_path / "staged", tmp_path / "out"
    jobs = D.build_jobs(list(D.ARMS), D.STEPS, staged, out, D.N_ROT, D.N_BOOT, skip_guarded=False)
    assert [j["step"] for j in jobs].count("join") == 1
    join = jobs[0]["argv"]
    assert join[join.index("--arms") + 1] == "v120,v120_3ha,alphaearth"
    assert join[join.index("--vectors-dir") + 1] == str(staged)

    scores = [j for j in jobs if j["step"] == "score"]
    assert len(scores) == 3 * 4
    tail = ["--joined", str(out / D.JOINED_NAME), "--out-dir", str(out)]
    k4 = str(ODISHA / "odisha_phase3_0_field_types_k4.csv")
    old = str(ODISHA / "odisha_phase3_0_field_types_allrows.csv")
    assert [j["argv"][2:] for j in scores[:4]] == [
        ["--arm", "v120", *tail], ["--arm", "v120", "--exclude-types", "0", *tail],
        ["--arm", "v120", "--field-types", k4, *tail], ["--arm", "v120", "--field-types", old, *tail]]
    assert scores[4]["argv"][2:6] == ["--arm", "v120_3ha", "--tag", "_3ha"]
    assert [j["writes"][0] for j in scores[4:8]] == [
        f"odisha_phase3_1_score_v120_3ha_merged_districts_3ha{s}.txt" for s in ("", "_excl0", "_ft-k4", "_ft-allrows")]

    sig = [j for j in jobs if j["step"] == "significance"]
    assert [j["writes"][0] for j in sig] == [
        *(f"odisha_phase3_3_results{s}.txt" for s in ("", "_excl0", "_ft-k4", "_ft-allrows")),
        *(f"odisha_phase3_3_results{s}_alphaearth.txt" for s in ("", "_excl0", "_ft-k4", "_ft-allrows"))]
    for j in sig[:4]:      # hand-crafted: both stand sizes in one run, and no extra arm
        own, passed = j["argv"][2:j["argv"].index("--")], j["argv"][j["argv"].index("--") + 1:]
        assert "--single-arm" not in own
        assert passed[:6] == ["--arms", "v120,v120_3ha", "--rotations", "1999", "--boot", "4000"]
    for j in sig[4:]:      # AlphaEarth: alone
        own, passed = j["argv"][2:j["argv"].index("--")], j["argv"][j["argv"].index("--") + 1:]
        assert own[-2:] == ["--single-arm", "alphaearth"] and passed[:2] == ["--arms", "alphaearth"]
    assert len({j["log"] for j in jobs}) == len(jobs)

    # an undeclared AlphaEarth arm is joined (the join scores nothing) and then left alone
    skipped = D.build_jobs(list(D.ARMS), D.STEPS, staged, out, D.N_ROT, D.N_BOOT, skip_guarded=True)
    assert "alphaearth" in skipped[0]["argv"][skipped[0]["argv"].index("--arms") + 1]
    assert len(skipped) == 1 + 8 + 4
    assert not [j for j in skipped[1:] if "alphaearth" in j["name"] or "alphaearth" in j["argv"]]


def test_results_file_names_are_the_significance_scripts_own():
    import odisha_phase3_3_significance as G  # noqa: N812

    for _, extra, _ in D.ANALYSES:
        ft = Path(extra[1]) if "--field-types" in extra else G.FIELD_TYPES
        excluded = (0,) if "--exclude-types" in extra else ()
        sens = G.sensitivity_tag(ft, excluded, ["v120", "v120_3ha"])
        for arms in (["v120", "v120_3ha"], ["v120"], ["v120_3ha"]):
            for rot, boot in ((1999, 4000), (120, 200), (1999, 200)):
                want = f"{G.OUT_STEM}{G.sensitivity_tag(ft, excluded, arms, rot, boot)}.txt"
                assert D.significance_name(sens, arms, rot, boot) == want
    assert (D.N_ROT, D.N_BOOT) == (G.N_ROT, G.N_BOOT)
    assert [label for label, _, _ in D.TESTS.values()] == [label for _, label in G.STATS]


def test_dry_run_checks_and_prints_but_writes_nothing(tmp_path: Path, capsys):
    stands, out = tmp_path / "new", tmp_path / "out"
    make_stands(stands, ["v120", "v120_3ha", "alphaearth"], "_repro", list(D.LAYER_ID))
    rc = D.main(["--stands-dir", str(stands), "--merge-rule", RULE, "--out-dir", str(out),
                 "--fallback-vectors", str(tmp_path / "none"), "--dry-run"])
    said = capsys.readouterr().out
    # the declaration does not name this test's merge rule, so AlphaEarth is refused: status 3
    assert rc == 3
    assert "THE ALPHAEARTH ARM WILL NOT BE SCORED OR TESTED" in said
    assert "--arm alphaearth" not in said and "--single-arm" not in said
    assert "--arms v120,v120_3ha,alphaearth --vectors-dir" in said           # the join still covers it
    assert said.count("odisha_phase3_1_pairwise_score.py") == 8
    assert said.count("odisha_phase3_demo_sigwrap.py") == 4
    assert "--dry-run: every input was found and checked" in said
    assert not out.exists()

    rc = D.main(["--stands-dir", str(stands), "--merge-rule", RULE, "--out-dir", str(out),
                 "--fallback-vectors", str(tmp_path / "none"), "--arms", "v120,v120_3ha", "--dry-run"])
    assert rc == 0 and not out.exists()
    # the join alone needs no declaration: it relates no field measurement to a stand
    rc = D.main(["--stands-dir", str(stands), "--merge-rule", RULE, "--out-dir", str(out),
                 "--fallback-vectors", str(tmp_path / "none"), "--arms", "alphaearth", "--steps", "join", "--dry-run"])
    assert rc == 0 and "WILL NOT BE SCORED" not in capsys.readouterr().out and not out.exists()


def test_runs_that_cannot_be_right_are_refused(tmp_path: Path):
    stands, out = tmp_path / "new", tmp_path / "out"
    make_stands(stands, ["v120"], "_repro", list(D.LAYER_ID))
    base = ["--stands-dir", str(stands), "--out-dir", str(out), "--fallback-vectors", str(tmp_path / "none"),
            "--arms", "v120", "--dry-run"]
    with pytest.raises(D.Refused):                       # no merge rule
        D.main(base)
    with pytest.raises(D.Refused):                       # an arm nobody knows
        D.main([*base, "--merge-rule", RULE, "--arms", "v120,current"])
    with pytest.raises(D.Refused) as e:                  # scores without a plot table
        D.main([*base, "--merge-rule", RULE, "--steps", "score"])
    assert "Run the join first" in e.value.why
    with pytest.raises(D.Refused):                       # stands missing for an arm asked for
        D.main([*base, "--merge-rule", RULE, "--arms", "v120,v120_3ha"])

    # a plot table in the folder that holds more arms than this run would join
    out.mkdir()
    (out / D.JOINED_NAME).write_text("plot_key,v120_merged_id,v120_3ha_merged_id\n")
    with pytest.raises(D.Refused) as e:
        D.main([*base, "--merge-rule", RULE])
    assert "v120_3ha" in e.value.why and "--steps score,significance" in e.value.why

    # scoring on a table joined to other stands, or under another merge rule
    plan = D.plan_staging(stands, "_repro", tmp_path / "none", ["v120"])
    (out / D.JOINED_NAME).write_text("plot_key,v120_merged_id\n")
    (out / D.MANIFEST_NAME).write_text(json.dumps({"merge_rule": RULE, "staged": D.staged_record(plan)}))
    with pytest.raises(D.Refused) as e:                  # a plot table the manifest does not record
        D.main([*base, "--merge-rule", RULE, "--steps", "score"])
    assert "not the plot table" in e.value.why
    (out / D.MANIFEST_NAME).write_text(json.dumps({"merge_rule": RULE, "staged": D.staged_record(plan),
                                                   "result_files": {D.JOINED_NAME: D.sha256(out / D.JOINED_NAME)}}))
    assert D.main([*base, "--merge-rule", RULE, "--steps", "score"]) == 0
    with pytest.raises(D.Refused) as e:
        D.main([*base, "--merge-rule", "another rule", "--steps", "score"])
    assert "merge rule" in e.value.why
    extra = stands / "odisha_v120_handcrafted_angul_repro_stands_merged.geojson"
    extra.write_text(extra.read_text() + "\n")
    with pytest.raises(D.Refused) as e:
        D.main([*base, "--merge-rule", RULE, "--steps", "score"])
    assert "not the ones the plot table" in e.value.why


@needs_git
def test_a_committed_result_is_not_replaced_silently(tmp_path: Path, capsys):
    stands, repo = tmp_path / "new", tmp_path / "repo"
    make_stands(stands, ["v120"], "_repro", list(D.LAYER_ID))
    out = repo / "phase3_demo"
    out.mkdir(parents=True)
    git(repo, "init", "-q")
    (out / "odisha_phase3_1_score_v120_merged_districts.txt").write_text("a committed score\n")
    (out / "README.md").write_text("x\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "results")
    base = ["--stands-dir", str(stands), "--merge-rule", RULE, "--out-dir", str(out),
            "--fallback-vectors", str(tmp_path / "none"), "--arms", "v120", "--dry-run"]
    with pytest.raises(D.Refused) as e:
        D.main(base)
    assert "--replace-committed" in e.value.why
    assert D.main([*base, "--replace-committed"]) == 0
    assert (out / "odisha_phase3_1_score_v120_merged_districts.txt").read_text() == "a committed score\n"


# --------------------------------------------------------------------------- the run, with stand-in scripts
STAND_IN = '''"""A stand-in for the join, the scorer and the chance test: writes the files the real
script would, under the right names, with no number in them. FES_FAIL names the kind to fail."""
import os, sys
from pathlib import Path
a, kind = sys.argv[1:], Path(sys.argv[0]).stem
def opt(name, default=None):
    return a[a.index(name) + 1] if name in a else default
out = Path(opt("--out-dir"))
sens = "_excl0" if "--exclude-types" in a else ""
if opt("--field-types"):
    sens = "_ft-" + Path(opt("--field-types")).stem.rsplit("_", 1)[1]
if kind == "join":
    (out / "phase2_plots_joined_districts.csv").write_text(
        "plot_key," + ",".join(f"{x}_merged_id" for x in opt("--arms").split(",")) + "\\n")
    (out / "odisha_phase2_3_results_districts.txt").write_text("the join of " + os.environ.get("FES_ROUND", "") + "\\n")
if os.environ.get("FES_FAIL") == kind:
    sys.exit(7)                       # a join that fails has already written half of its files
if kind == "score":
    (out / f"odisha_phase3_1_score_{opt('--arm')}_merged_districts{opt('--tag', '')}{sens}.txt").write_text("a score\\n")
if kind == "chance":
    sys.path.insert(0, os.environ["FES_ODISHA"])
    import odisha_phase3_demo_fes as D
    name = D.significance_name(sens, opt("--arms").split(","), int(opt("--rotations")), int(opt("--boot")))
    (out / name).write_text("a chance test\\n")
    (out / name).with_suffix(".log").write_text("took 1 s\\n")
'''


@pytest.fixture
def stand_ins(tmp_path: Path, monkeypatch):
    """The driver with the three scripts it runs replaced by STAND_IN, new stands for the two
    hand-crafted arms, and the options of a run on them. No real script runs and no score exists."""
    for kind, attr in (("join", "JOIN_SCRIPT"), ("score", "SCORE_SCRIPT"), ("chance", "SIGNIFICANCE_WRAPPER")):
        (tmp_path / f"{kind}.py").write_text(STAND_IN)
        monkeypatch.setattr(D, attr, tmp_path / f"{kind}.py")
    monkeypatch.setenv("FES_ODISHA", str(ODISHA))
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join([str(REPO / "src"), os.environ.get("PYTHONPATH", "")]))
    monkeypatch.delenv("FES_FAIL", raising=False)
    stands, out = tmp_path / "new", tmp_path / "out"
    make_stands(stands, D.HANDCRAFTED, "_repro", list(D.LAYER_ID))
    base = ["--stands-dir", str(stands), "--merge-rule", RULE, "--out-dir", str(out),
            "--fallback-vectors", str(tmp_path / "none"), "--arms", "v120,v120_3ha"]
    return base, out, monkeypatch


def results_in(out: Path) -> list[str]:
    return sorted(p.name for p in out.iterdir() if p.suffix != ".log" and p.name != D.MANIFEST_NAME)


def test_the_manifest_lists_what_the_folder_holds_after_a_failed_rerun(stand_ins, capsys):
    base, out, monkeypatch = stand_ins
    assert D.main(base) == 0
    manifest = json.loads((out / D.MANIFEST_NAME).read_text())
    assert len(manifest["result_files"]) == 2 + 8 + 4 and sorted(manifest["result_files"]) == results_in(out)

    # the scores of one arm again, and the scorer fails: its four files are gone, and so are their names
    monkeypatch.setenv("FES_FAIL", "score")
    assert D.main([*base[:-1], "v120", "--steps", "score"]) == 1
    manifest = json.loads((out / D.MANIFEST_NAME).read_text())
    lost = [D.score_name("v120", sens) for _, _, sens in D.ANALYSES]
    assert not [n for n in lost if (out / n).exists() or n in manifest["result_files"]]
    assert len(manifest["result_files"]) == 10 and sorted(manifest["result_files"]) == results_in(out)
    assert all(h == D.sha256(out / n) for n, h in manifest["result_files"].items())
    assert manifest["runs"][1]["written"] == {} and len(manifest["runs"][1]["failed"]) == 4

    # run again and it works: the names are back
    monkeypatch.delenv("FES_FAIL")
    assert D.main([*base[:-1], "v120", "--steps", "score"]) == 0
    manifest = json.loads((out / D.MANIFEST_NAME).read_text())
    assert len(manifest["result_files"]) == 14 and sorted(manifest["result_files"]) == results_in(out)


def test_a_failed_join_leaves_the_earlier_results_as_they_were(stand_ins, capsys):
    base, out, monkeypatch = stand_ins
    monkeypatch.setenv("FES_ROUND", "first")
    assert D.main(base) == 0
    before = {p.name: p.read_bytes() for p in out.iterdir() if p.name != D.MANIFEST_NAME and p.name != "fes_join.log"}
    manifest = json.loads((out / D.MANIFEST_NAME).read_text())
    assert len(before) > 14                                  # the results and the logs beside them

    monkeypatch.setenv("FES_ROUND", "second")
    monkeypatch.setenv("FES_FAIL", "join")
    assert D.main(base) == 1
    said = capsys.readouterr().out
    assert "set aside" in said and "put back" in said
    after = {p.name: p.read_bytes() for p in out.iterdir() if p.name != D.MANIFEST_NAME and p.name != "fes_join.log"}
    assert after == before and not (out / D.HELD_NAME).exists()
    assert (out / D.JOIN_RESULTS_NAME).read_text() == "the join of first\n"      # not the half-written second one
    again = json.loads((out / D.MANIFEST_NAME).read_text())
    assert {k: v for k, v in again.items() if k != "runs"} == {k: v for k, v in manifest.items() if k != "runs"}
    assert again["runs"][0] == manifest["runs"][0] and again["runs"][1]["failed"] == ["join"]
    assert again["runs"][1]["written"] == {} and len(again["runs"][1]["not_run"]) == 12
    # the earlier results can still be scored on: the plot table is the one the manifest records
    monkeypatch.delenv("FES_FAIL")
    assert D.main([*base, "--steps", "score"]) == 0

    # a join that succeeds replaces them all, and nothing stays set aside
    assert D.main(base) == 0
    assert (out / D.JOIN_RESULTS_NAME).read_text() == "the join of second\n"
    assert not (out / D.HELD_NAME).exists()
    assert len(json.loads((out / D.MANIFEST_NAME).read_text())["runs"]) == 1

    # a failed first join in an empty folder leaves no result behind and says so in the manifest
    fresh = out.parent / "fresh"
    monkeypatch.setenv("FES_FAIL", "join")
    assert D.main([*base[:5], str(fresh), *base[6:]]) == 1
    assert results_in(fresh) == [] and json.loads((fresh / D.MANIFEST_NAME).read_text())["result_files"] == {}

    # results an interrupted run left set aside are not run over
    (out / D.HELD_NAME).mkdir()
    monkeypatch.delenv("FES_FAIL")
    with pytest.raises(D.Refused) as e:
        D.main(base)
    assert "interrupted" in e.value.why


# --------------------------------------------------------------------------- the AlphaEarth guard
@pytest.fixture
def declared(tmp_path: Path):
    """A checkout on the branch `work` with a remote, and the path of its declaration file."""
    origin, repo = tmp_path / "origin.git", tmp_path / "checkout"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "work", str(origin)], check=True)
    subprocess.run(["git", "init", "-q", "-b", "work", str(repo)], check=True)
    git(repo, "remote", "add", "origin", str(origin))
    (repo / "odisha_script").mkdir()
    (repo / "odisha_script" / "other.txt").write_text("x\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "first")
    git(repo, "push", "-q", "origin", "work")
    return repo, repo / "odisha_script" / D.DECLARATION.name


@needs_git
def test_the_guard_wants_the_declaration_committed_unchanged_and_pushed(declared):
    repo, decl = declared
    state = D.alphaearth_declaration_state(repo)
    assert not state["ok"] and "does not exist" in state["why"]

    decl.write_text(f"# declared\n\n- Merge rule: {D.MERGE_RULE_PLACEHOLDER}\n")
    state = D.alphaearth_declaration_state(repo)
    assert not state["ok"] and "not committed" in state["why"]

    git(repo, "add", "-A")
    state = D.alphaearth_declaration_state(repo)          # staged is not committed
    assert not state["ok"] and "differs from its committed version" in state["why"]
    git(repo, "commit", "-q", "-m", "declaration, placeholder left in")
    git(repo, "push", "-q", "origin", "work")
    state = D.alphaearth_declaration_state(repo)
    assert not state["ok"] and "placeholder" in state["why"]

    decl.write_text("# declared\n\n- Merge rule: skip a region already at\n  the minimum size (register id x)\n")
    git(repo, "commit", "-q", "-am", "the stands are named")
    commit = git(repo, "rev-parse", "HEAD")
    state = D.alphaearth_declaration_state(repo)
    assert not state["ok"] and "is not on origin/work" in state["why"]     # committed, not pushed
    with pytest.raises(D.Refused):
        D.require_alphaearth_declared(repo)

    git(repo, "push", "-q", "origin", "work")
    state = D.require_alphaearth_declared(repo)
    assert state["ok"] and state["commit"] == commit and state["branch"] == "work"
    assert state["sha256"] == D.sha256(decl)
    # the merge rule given on the command line must be the one declared; line breaks do not matter
    assert D.alphaearth_declaration_state(repo, "skip a region already at the minimum size (register id x)")["ok"]
    state = D.alphaearth_declaration_state(repo, "before the merge fix")
    assert not state["ok"] and "--merge-rule" in state["why"]

    # later commits that do not touch the file change nothing, pushed or not
    (repo / "odisha_script" / "other.txt").write_text("y\n")
    git(repo, "commit", "-q", "-am", "something else")
    assert D.alphaearth_declaration_state(repo)["ok"]

    decl.write_text(decl.read_text() + "\nand one more test, added after the scores\n")
    state = D.alphaearth_declaration_state(repo)
    assert not state["ok"] and "differs from its committed version" in state["why"]
    git(repo, "checkout", "-q", "--", ".")

    git(repo, "checkout", "-q", "-b", "elsewhere")        # a branch the remote does not have
    state = D.alphaearth_declaration_state(repo)
    assert not state["ok"] and "no origin/elsewhere" in state["why"]
    git(repo, "checkout", "-q", "--detach", "work")
    state = D.alphaearth_declaration_state(repo)
    assert not state["ok"] and "not on a branch" in state["why"]


@needs_git
def test_the_merge_rule_is_the_one_line_that_declares_it(declared):
    """The real draft with its placeholder filled in: only the text of "- Merge rule:" passes."""
    repo, decl = declared
    rule = "D-031 (skip a region already at the minimum size)"
    draft = D.DECLARATION.read_text()
    # its one "- Merge rule:" item (the placeholder, or what the engineer wrote there) becomes this test's rule
    filled, n = re.subn(r"(?m)^- Merge rule:.*(\n[ \t]+(?![-*]\s)\S.*)*$", f"- Merge rule: {rule}", draft)
    assert n == 1
    decl.write_text(filled)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "declaration")
    git(repo, "push", "-q", "origin", "work")
    state = D.alphaearth_declaration_state(repo, rule)
    assert state["ok"] and state["merge_rule"] == rule
    assert D.alphaearth_declaration_state(repo, "  D-031 (skip a region\n already at the minimum size) ")["ok"]
    # text that stands elsewhere in the file, a part of the rule, and the words of the command block
    for other in ("10", "the", "k = 6", "unchanged", "Merge rule", "D-031", "$RULE", rule + " and more",
                  "<the merge rule, exactly as written above>"):
        state = D.alphaearth_declaration_state(repo, other)
        assert not state["ok"] and "is not the merge rule" in state["why"], other
    # nothing in the commands the draft gives can be passed as a rule
    assert "merge rule, exactly" not in draft and '--merge-rule "$RULE"' in draft

    # a second line that declares a rule, and no line at all
    text = decl.read_text()
    for changed, said in ((text + "\n- Merge rule: before the merge fix\n", "2 list items"),
                          (text.replace("- Merge rule:", "- The merge rule is"), "0 list items"),
                          (text.replace(f"- Merge rule: {rule}", "- Merge rule:"), "names no rule")):
        decl.write_text(changed)
        git(repo, "commit", "-q", "-am", "changed")
        git(repo, "push", "-q", "origin", "work")
        for given in (None, rule, "before the merge fix"):
            state = D.alphaearth_declaration_state(repo, given)
            assert not state["ok"] and said in state["why"], (said, given)


def test_the_declared_merge_rule_is_read_from_its_list_item():
    assert D.declared_merge_rule("# x\n\n- Merge rule: a rule\n  over two lines\n- another item\n") == (
        "a rule over two lines", "")
    assert D.declared_merge_rule("- Merge rule: one\n\n  not part of it\n")[0] == "one"
    assert D.declared_merge_rule("- Merge rule: one\nThe driver is given the merge rule.\n")[0] == "one"
    assert D.declared_merge_rule("The merge rule: none is declared in a list item\n")[0] is None


@needs_git
def test_a_file_git_was_told_to_assume_unchanged_does_not_pass(declared):
    repo, decl = declared
    decl.write_text("# declared\n\n- Merge rule: a rule\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "declaration")
    git(repo, "push", "-q", "origin", "work")
    assert D.alphaearth_declaration_state(repo, "a rule")["ok"]
    for flag in ("--assume-unchanged", "--skip-worktree"):
        git(repo, "update-index", flag, "--", f"odisha_script/{decl.name}")
        decl.write_text("# declared\n\n- Merge rule: a rule\n\nA sixth test, added later.\n")
        assert git(repo, "status", "--porcelain") == ""                    # git status sees nothing
        state = D.alphaearth_declaration_state(repo, "a rule")
        assert not state["ok"] and "differs from its committed version" in state["why"], flag
        decl.write_text("# declared\n\n- Merge rule: a rule\n")
        assert D.alphaearth_declaration_state(repo, "a rule")["ok"]
        git(repo, "update-index", flag.replace("--", "--no-", 1), "--", f"odisha_script/{decl.name}")


def test_the_guard_refuses_outside_a_checkout(tmp_path: Path):
    (tmp_path / "odisha_script").mkdir()
    (tmp_path / "odisha_script" / D.DECLARATION.name).write_text("declared, but in no repository\n")
    state = D.alphaearth_declaration_state(tmp_path)
    assert not state["ok"] and "not committed" in state["why"]


def test_the_draft_declaration_cannot_pass_the_guard_as_it_is():
    """The file in this checkout is a draft until the engineer names the stands in it."""
    text = D.DECLARATION.read_text()
    if D.MERGE_RULE_PLACEHOLDER in text:
        assert text.count(D.MERGE_RULE_PLACEHOLDER) == 1
        assert not D.alphaearth_declaration_state(REPO)["ok"]


# --------------------------------------------------------------------------- the wrapper's bookkeeping
@pytest.fixture
def significance_modules():
    """The three Phase 2/3 modules, put back as they were after a test has pointed them elsewhere."""
    import odisha_phase2_3_join as J  # noqa: N812
    import odisha_phase3_3_significance as G  # noqa: N812

    saved = (J.VECTOR_DIR, dict(J.ARMS), G.JOINED, G.ARM_LABEL, G.load_all)
    yield J, G
    J.VECTOR_DIR, G.JOINED, G.ARM_LABEL, G.load_all = saved[0], saved[2], saved[3], saved[4]
    J.ARMS.clear()
    J.ARMS.update(saved[1])


def test_the_wrapper_moves_the_paths_and_nothing_else(significance_modules, tmp_path: Path):
    J, G = significance_modules  # noqa: N806
    labels, joined = dict(G.ARM_LABEL), tmp_path / "joined.csv"
    joined.write_text("plot_key\n")
    assert W.configure(tmp_path, joined) is G
    assert tmp_path.resolve() == J.VECTOR_DIR
    assert J.vector_path("cfg", "stands_merged") == tmp_path.resolve() / "cfg_stands_merged.geojson"
    assert G.JOINED["v120"] == G.JOINED["v120_3ha"] == joined.resolve()
    # the two-arm run is still the primary run: no third label, no file suffix
    assert labels == G.ARM_LABEL
    assert G.parse_arms("v120,v120_3ha") == ["v120", "v120_3ha"]
    assert G.sensitivity_tag(G.FIELD_TYPES, (), ["v120", "v120_3ha"]) == ""
    with pytest.raises(SystemExit):
        G.parse_arms("alphaearth")
    with pytest.raises(SystemExit):
        W.configure(tmp_path / "absent", joined)
    with pytest.raises(SystemExit):
        W.configure(tmp_path, tmp_path / "absent.csv")


def test_the_extra_arm_runs_alone_and_only_when_declared(significance_modules, tmp_path: Path, monkeypatch):
    """Arm bookkeeping only: no stand file, no plot table and no score is read."""
    J, G = significance_modules  # noqa: N806
    labels, joined = dict(G.ARM_LABEL), tmp_path / "joined.csv"
    joined.write_text("plot_key\n")

    monkeypatch.setattr(D, "alphaearth_declaration_state", lambda *a, **k: {"ok": False, "why": "not declared (test)"})
    with pytest.raises(D.Refused):
        W.configure(tmp_path, joined, single_arm="alphaearth")
    assert labels == G.ARM_LABEL
    with pytest.raises(SystemExit):
        W.configure(tmp_path, joined, single_arm="current")       # no other arm is declared

    monkeypatch.setattr(D, "alphaearth_declaration_state", lambda *a, **k: {"ok": True, "why": ""})
    W.configure(tmp_path, joined, single_arm="alphaearth")
    assert {**labels, "alphaearth": "AlphaEarth 10 ha"} == G.ARM_LABEL
    assert G.parse_arms("alphaearth") == ["alphaearth"]
    # a single-arm run: the script adds _alphaearth to the file name, as the driver expects
    assert G.sensitivity_tag(G.FIELD_TYPES, (), ["alphaearth"]) == "_alphaearth"
    assert D.significance_name("", ["alphaearth"], G.N_ROT, G.N_BOOT) == f"{G.OUT_STEM}_alphaearth.txt"
    assert G.JOINED["alphaearth"] == joined.resolve()
    # its seed strings, as PHASE3_ALPHAEARTH_PREDECLARED.md writes them
    assert G.SEED_UNCOND.format(arm="alphaearth") == "alphaearth/stands_merged/phase3_ari"
    assert G.SEED_LABELLED.format(arm="alphaearth") == "alphaearth/stands_merged/phase3_ari_labelled"


def test_the_wrapper_refuses_the_extra_arm_beside_another(tmp_path: Path):
    base = ["--vectors-dir", str(tmp_path), "--joined", str(tmp_path / "j.csv")]
    for own, passed in ((["--single-arm", "alphaearth"], ["--arms", "v120"]),
                        (["--single-arm", "alphaearth"], ["--arms", "v120,alphaearth"]),
                        (["--single-arm", "alphaearth"], []),
                        ([], ["--arms", "alphaearth"]),
                        ([], ["--arms=v120,alphaearth"])):
        with pytest.raises(SystemExit) as e:
            W.main([*base, *own, "--", *passed])
        assert e.value.code not in (0, None)
    with pytest.raises(SystemExit):
        W.main(base)                                              # no "--": nothing to hand on


def test_arm_columns_are_exact():
    cols = W.arm_columns("v120", ["merged", "snic", "dissolved"])
    assert len(cols) == 12 and "v120_merged_id" in cols and "v120_dissolved_bdist_m" in cols
    assert not [c for c in cols if c.startswith("v120_3ha")]
    assert W.parse_joined(["a.csv"]) == Path("a.csv")
    assert W.parse_joined(["v120=a.csv", "v120_3ha=b.csv"]) == {"v120": Path("a.csv"), "v120_3ha": Path("b.csv")}


def test_the_wrapper_loads_the_plots_the_script_loads(significance_modules):
    """On the committed hand-crafted tables the replaced load_all returns the script's own plots."""
    J, G = significance_modules  # noqa: N806
    original = G.load_all
    _, want, parts_want = original(["v120", "v120_3ha"], G.FIELD_TYPES)
    committed = dict(G.JOINED)
    W.configure(J.VECTOR_DIR, committed)
    spec, got, parts = G.load_all(["v120", "v120_3ha"], G.FIELD_TYPES)
    pd.testing.assert_frame_equal(got, want)
    assert [p["name"] for p in parts] == [p["name"] for p in parts_want]
    assert spec["joined"] == committed["v120"]
    # one arm alone: the same plots in the same order, from that arm's own table
    _, one, _ = G.load_all(["v120_3ha"], G.FIELD_TYPES)
    cols = ["plot_key", "aoi_part", "district_set", "x", "y", "field_type", *W.arm_columns("v120_3ha", J.LAYERS)]
    pd.testing.assert_frame_equal(one[cols], want[cols])


# --------------------------------------------------------------------------- the parser
PRIMARY = ODISHA / "odisha_phase3_3_results.txt"
CHECKS = {"S1": ODISHA / "odisha_phase3_3_results_excl0.txt", "S2": ODISHA / "odisha_phase3_3_results_ft-k4.txt",
          "S3": ODISHA / "odisha_phase3_3_results_ft-allrows.txt"}
ROW_KEYS = ["arm", "stand_ceiling_ha", "analysis", "test", "title", "score", "chance_percentile", "p", "p_holm",
            "holm_family", "holm_tests_corrected", "n_plots"]


def pick(rows: list[dict], ceiling: int, test: str) -> dict:
    (row,) = [r for r in rows if r["stand_ceiling_ha"] == ceiling and r["test"] == test]
    return row


def test_parser_reads_the_committed_primary_file():
    rows = D.parse_significance(PRIMARY)
    assert len(rows) == 10 and all(list(r) == ROW_KEYS for r in rows)
    assert {(r["arm"], r["analysis"], r["holm_family"]) for r in rows} == {("feature_vector", "primary", 10)}
    assert {r["holm_tests_corrected"] for r in rows} == {10}
    # 10 ha, drawing on all plots: the numbers of odisha_phase3_3_results.txt (and PHASE3_STATUS.md)
    row = pick(rows, 10, "drawing_all_plots")
    assert (row["score"], row["chance_percentile"], row["p"], row["p_holm"]) == (0.0121, 93.7, 0.063, 0.630)
    assert row["n_plots"] == 267
    row = pick(rows, 3, "labelling_far_apart")
    assert (row["score"], row["chance_percentile"], row["p"], row["p_holm"]) == (0.0143, 64.0, 0.360, 1.0)
    assert pick(rows, 10, "labelling_far_apart")["score"] == -0.0118
    # the number of plots that enter each measure, from the "[10 ha] plots with a stand ..." lines
    assert [pick(rows, 10, t)["n_plots"] for t in D.TESTS] == [267, 184, 184, 266, 266]
    assert [pick(rows, 3, t)["n_plots"] for t in D.TESTS] == [267, 113, 113, 267, 267]


def test_parser_reads_the_three_checks():
    for analysis, path in CHECKS.items():
        rows = D.parse_significance(path)
        assert len(rows) == 10 and {r["analysis"] for r in rows} == {analysis}
    s1 = D.parse_significance(CHECKS["S1"])
    # after field type 0 is left out: 251 scored plots, 250 of them typed at 10 ha
    assert [pick(s1, 10, t)["n_plots"] for t in D.TESTS] == [251, 168, 168, 250, 250]
    assert [pick(s1, 3, t)["n_plots"] for t in D.TESTS] == [251, 100, 100, 251, 251]


@pytest.mark.parametrize("path", [PRIMARY, *CHECKS.values()], ids=["primary", "S1", "S2", "S3"])
def test_every_row_of_the_committed_holm_tables_is_recovered(path: Path):
    """Read the Holm table a second, simpler way and find each of its rows among the parsed ones."""
    lines = path.read_text().splitlines()
    at = next(i for i, ln in enumerate(lines) if ln.startswith("MULTIPLE COMPARISONS"))
    table = []
    for ln in lines[at + 3:]:
        if not ln.strip():
            break
        name, p, holm = ln[4:62].strip(), ln[62:70], ln[70:79]
        table.append((name, float(p), float(holm)))
    assert len(table) == 10
    rows = D.parse_significance(path)
    label_of = {test: label for test, (label, _, _) in D.TESTS.items()}
    parsed = {(f"{r['stand_ceiling_ha']} ha: {label_of[r['test']]}"): (r["p"], r["p_holm"]) for r in rows}
    assert parsed == {name: (p, holm) for name, p, holm in table}


def test_not_estimable_gives_nulls(tmp_path: Path):
    text = PRIMARY.read_text()
    row = "    delineation ARI, multi-plot stands           +0.0244 | +0.0223 [+0.0143, +0.0321]    65.7   0.344   1999\n"
    holm = "    3 ha: delineation ARI, multi-plot stands                     0.344    1.000\n"
    assert text.count(row) == 1 and text.count(holm) == 1
    # what null_row() prints, and what the Holm table then holds: no row for that test
    text = text.replace(row, "    delineation ARI, multi-plot stands           +0.0244 | NOT ESTIMABLE "
                             "(usable realisations 5 < 100)\n").replace(holm, "")
    path = tmp_path / "odisha_phase3_3_results.txt"
    path.write_text(text)
    rows = D.parse_significance(path)
    row = pick(rows, 3, "drawing_shared_stands")
    assert row["score"] == 0.0244
    assert (row["chance_percentile"], row["p"], row["p_holm"]) == (None, None, None)
    assert row["holm_family"] == 10 and row["n_plots"] == 113
    assert pick(rows, 10, "drawing_shared_stands")["p"] == 0.230         # the other arm's row is untouched
    # the file declares 10 tests and its Holm table holds 9: every row says so, and so does the table
    assert {(r["holm_family"], r["holm_tests_corrected"]) for r in rows} == {(10, 9)}
    md = D.markdown_tables(rows)
    assert "| primary | Drawing, shared stands | 0.0244 | not estimable | not estimable | not estimable | 113 |" in md
    assert "p after Holm (over 10 tests, or over the number in the cell)" in md
    assert "| 0.630 (over 9 tests) | 267 |" in md and md.count("(over 9 tests)") == 9
    assert "holm_tests_corrected" in D.ROW_NOTES and "not over holm_family" in D.ROW_NOTES["holm_tests_corrected"]


def test_a_whole_arm_not_estimable_is_not_called_a_family_of_ten(tmp_path: Path):
    """The five 10 ha tests cannot be made: the 3 ha Holm values in the file are then over 5 tests."""
    lines = PRIMARY.read_text().splitlines()
    labels = [label for label, _, _ in D.TESTS.values()]
    out, arm = [], ""
    for ln in lines:
        if ln.endswith("-- observed vs rotation null"):
            arm = ln.split(" ARM ")[0]
        elif ln.startswith(("ARM COMPARISON", "MULTIPLE COMPARISONS")):
            arm = ""
        head = re.match(r"    (\S.*?\S)\s+([+-]\d+\.\d+) \| ", ln)
        if arm == "10 HA" and head and head[1] in labels:
            ln = ln.split(" | ")[0] + " | NOT ESTIMABLE (usable realisations 5 < 100)"
        if ln.startswith("    10 ha: "):
            continue                                      # its row of the Holm table
        out.append(ln)
    path = tmp_path / "odisha_phase3_3_results.txt"
    path.write_text("\n".join(out) + "\n")
    rows = D.parse_significance(path)
    assert {(r["holm_family"], r["holm_tests_corrected"]) for r in rows} == {(10, 5)}
    assert {r["p_holm"] for r in rows if r["stand_ceiling_ha"] == 10} == {None}
    assert all(r["p_holm"] is not None for r in rows if r["stand_ceiling_ha"] == 3)
    md = D.markdown_tables(rows)
    assert md.count("(over 5 tests)") == 5 and "(over 10 tests)" not in md

    # a Holm table with a row no headline test accounts for, or without the row of one, is refused
    text = PRIMARY.read_text()
    holm = "    3 ha: delineation ARI, multi-plot stands                     0.344    1.000\n"
    assert text.count(holm) == 1
    path.write_text(text.replace(holm, ""))
    with pytest.raises(D.Refused):
        D.parse_significance(path)


def test_a_score_that_is_not_defined_is_not_called_not_estimable():
    rows = [dict(r) for r in D.parse_significance(PRIMARY)]
    rows[0].update(score=None, chance_percentile=None, p=None, p_holm=None)
    md = D.markdown_tables(rows)
    assert "| primary | Drawing, all plots | not defined | not estimable | not estimable | not estimable | 267 |" in md


def test_parser_reads_a_one_arm_file_whatever_the_arm_is_called(tmp_path: Path, monkeypatch):
    """The layout of a single-arm results file, with an invented arm and invented numbers."""
    monkeypatch.setitem(D.ARMS, "invented", {"ui_arm": "invented_arm", "ceiling_ha": 7})
    labels = [label for label, _, _ in D.TESTS.values()]
    obs = ["+0.1000", "+0.2000", "+0.3000", "+0.4000", "-0.5000"]
    lines = ["  THIS RUN", "  * field types file: odisha_phase3_0_field_types.csv   (the primary typology)",
             "  * excluded field types: none", "",
             "  [Invented Arm 7 ha] plots with a stand 30, with a stand type 20; multi-plot stands 4 holding 10 plots; "
             "observed statistics match the scorer's definition (|diff| < 1e-12)", "",
             "INVENTED ARM 7 HA ARM (invented, merged layer) -- observed vs rotation null",
             "    statistic                                    observed |        null median [p5, p95]  pctile   p(>=)      n"]
    for k, (label, o) in enumerate(zip(labels, obs, strict=True)):
        lines.append(f"    {label:44} {o} | +0.0100 [+0.0050, +0.0200]  {90 + k:6.1f}  {0.01 * (k + 1):6.3f}   1999")
    lines += ["      angul                                      +0.9000 | +0.0100 [+0.0050, +0.0200]    99.0   0.001   1999",
              "", "ARM COMPARISON -- NOT RUN", "",
              "MULTIPLE COMPARISONS -- Holm over the 5 headline tests (one-sided p(>=), rotation null)",
              f"    {'test':58} {'p(>=)':>7}  {'Holm p':>7}"]
    for k, label in enumerate(labels):
        name = f"Invented Arm 7 ha: {label}"
        lines.append(f"    {name:58} {0.01 * (k + 1):7.3f}  {0.05:7.3f}" + ("  <- survives" if k == 0 else ""))
    lines += ["    (Holm here is over this arm's 5 tests only.)", "", "WHAT THIS SAYS"]
    path = tmp_path / "odisha_phase3_3_results_invented.txt"
    path.write_text("\n".join(lines) + "\n")
    rows = D.parse_significance(path)
    assert len(rows) == 5 and {(r["arm"], r["stand_ceiling_ha"], r["holm_family"]) for r in rows} == {("invented_arm", 7, 5)}
    assert {r["holm_tests_corrected"] for r in rows} == {5}
    assert [r["score"] for r in rows] == [0.1, 0.2, 0.3, 0.4, -0.5]
    assert [r["chance_percentile"] for r in rows] == [90.0, 91.0, 92.0, 93.0, 94.0]
    assert [r["p"] for r in rows] == [0.01, 0.02, 0.03, 0.04, 0.05] and {r["p_holm"] for r in rows} == {0.05}
    assert [r["n_plots"] for r in rows] == [30, 10, 10, 20, 20]


def test_parser_refuses_what_it_does_not_know(tmp_path: Path):
    cut = tmp_path / "odisha_phase3_3_results.txt"
    cut.write_text(PRIMARY.read_text().split("MULTIPLE COMPARISONS")[0])     # a run that did not finish
    with pytest.raises(D.Refused):
        D.parse_significance(cut)
    other = tmp_path / "other.txt"
    other.write_text(PRIMARY.read_text().replace("odisha_phase3_0_field_types.csv", "some_other_types.csv"))
    with pytest.raises(D.Refused):
        D.parse_significance(other)
    with pytest.raises(D.Refused):
        D.parse_significance(ODISHA / "odisha_phase3_1_score_v120_merged_districts.txt")


def test_score_parser_gives_the_same_five_measures():
    rows = D.parse_score(ODISHA / "odisha_phase3_1_score_v120_merged_districts.txt")
    assert [r["test"] for r in rows] == list(D.TESTS)
    assert {(r["arm"], r["stand_ceiling_ha"], r["analysis"]) for r in rows} == {("feature_vector", 10, "primary")}
    # the scorer prints three of the five; the other two follow from its pair counts
    # (133 of 247 same-stand pairs alike; 693/3677 - 1373/6857 far apart)
    assert [None if r["score"] is None else round(r["score"], 4) for r in rows] == [0.0121, 0.0257, 0.5385, 0.0389, -0.0118]
    assert rows[2]["score"] == 133 / 247
    assert [r["n_plots"] for r in rows] == [267, 184, 184, 266, 266]
    rows = D.parse_score(ODISHA / "odisha_phase3_1_score_v120_3ha_merged_districts_3ha_excl0.txt")
    assert {(r["stand_ceiling_ha"], r["analysis"]) for r in rows} == {(3, "S1")}
    assert rows[0]["n_plots"] == 251


def test_collect_writes_the_rows_and_the_tables(tmp_path: Path, capsys):
    folder = tmp_path / "phase3_demo"
    folder.mkdir()
    for p in [PRIMARY, *CHECKS.values(), *ODISHA.glob("odisha_phase3_1_score_v120_*merged_districts*.txt")]:
        shutil.copy(p, folder / p.name)
    # a short test run in the same folder is not a result
    shutil.copy(PRIMARY, folder / "odisha_phase3_3_results_rot120_boot200.txt")
    out_json, out_md = tmp_path / "ui" / "ui_data_fes.json", tmp_path / "fes_table.md"
    assert D.main(["--collect", "--out-dir", str(folder), "--json", str(out_json), "--markdown", str(out_md)]) == 0
    said = capsys.readouterr().out
    assert "40 score(s) agree with the scorer's own files" in said
    assert "left out (a test run, not the declared draws): odisha_phase3_3_results_rot120_boot200.txt" in said

    data = json.loads(out_json.read_text())
    assert list(data) == ["notes", "sources", "rows"] and "n_plots" in data["notes"]
    assert "holm_tests_corrected" in data["notes"]
    assert data["sources"] == sorted(p.name for p in [PRIMARY, *CHECKS.values()])
    rows = data["rows"]
    assert len(rows) == 40 and all(list(r) == ROW_KEYS for r in rows)
    assert {r["arm"] for r in rows} == {"feature_vector"}                 # no AlphaEarth file, no AlphaEarth row
    assert [(r["stand_ceiling_ha"], r["analysis"]) for r in rows[::5]] == [
        (c, a) for c in (10, 3) for a in ("primary", "S1", "S2", "S3")]
    assert rows[0] == {"arm": "feature_vector", "stand_ceiling_ha": 10, "analysis": "primary",
                       "test": "drawing_all_plots", "title": D.TESTS["drawing_all_plots"][2], "score": 0.0121,
                       "chance_percentile": 93.7, "p": 0.063, "p_holm": 0.63, "holm_family": 10,
                       "holm_tests_corrected": 10, "n_plots": 267}
    # results only: nothing in either file says when or where it was made
    for text in (out_json.read_text(), out_md.read_text()):
        assert not re.search(r"20\d\d-\d\d-\d\d|/Users/|took \d+ s", text)

    md = out_md.read_text()
    assert md.count("### ") == 2
    assert "### Hand-crafted features, stands of at most 10 hectares" in md
    assert "| primary | Drawing, all plots | 0.0121 | 93.7 | 0.063 | 0.630 | 267 |" in md
    assert "| primary | Far-apart labelling | −0.0118 | 46.6 | 0.534 | 1.000 | 266 |" in md
    assert "p after Holm (over 10 tests)" in md

    # a score file from another plot table: nothing is written
    scorer = folder / "odisha_phase3_1_score_v120_merged_districts.txt"
    scorer.write_text(scorer.read_text().replace(">>> ARI +0.0121", ">>> ARI +0.0321"))
    out_json.unlink()
    with pytest.raises(D.Refused) as e:
        D.main(["--collect", "--out-dir", str(folder), "--json", str(out_json)])
    assert "do not come from the same plot table" in e.value.why and not out_json.exists()
    with pytest.raises(D.Refused):
        D.main(["--collect", "--out-dir", str(tmp_path / "ui"), "--json", str(out_json)])


# --------------------------------------------------------------------------- the real scripts (slow)
SMOKE = ["--rotations", "120", "--boot", "200"]       # 120: the fewest realisations that give a percentile


def _env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(REPO / "src"), *filter(None, [env.get("PYTHONPATH")])])
    return env


@pytest.fixture(scope="module")
def real_runs(tmp_path_factory):
    """The significance script on the committed hand-crafted stands, plain and through the
    wrapper, both stand sizes together and the 10 ha arm alone; and the whole driver on the
    same stands, presented as if they were new. All at 120 rotations, side by side."""
    root = tmp_path_factory.mktemp("fes")
    py, plain, wrap = sys.executable, str(ODISHA / "odisha_phase3_3_significance.py"), str(D.SIGNIFICANCE_WRAPPER)
    committed = ["--vectors-dir", str(ODISHA / "phase2_vectors"),
                 "--joined", f"v120={ODISHA / 'phase2_plots_joined_districts.csv'}",
                 "--joined", f"v120_3ha={ODISHA / 'phase3_3ha' / 'phase2_plots_joined_districts.csv'}", "--"]
    commands = {
        "plain_both": [py, plain, *SMOKE, "--out-dir", str(root / "plain_both")],
        "wrap_both": [py, wrap, *committed, *SMOKE, "--out-dir", str(root / "wrap_both")],
        "plain_one": [py, plain, "--arms", "v120", *SMOKE, "--out-dir", str(root / "plain_one")],
        "wrap_one": [py, wrap, *committed, "--arms", "v120", *SMOKE, "--out-dir", str(root / "wrap_one")],
    }
    running = {}
    for name, argv in commands.items():
        log = (root / f"{name}.stdout").open("w")
        running[name] = (subprocess.Popen(argv, cwd=REPO, env=_env(), stdout=log, stderr=subprocess.STDOUT), log)
    demo = root / "demo"
    driver = subprocess.run(
        [py, str(ODISHA / "odisha_phase3_demo_fes.py"), "--stands-dir", str(ODISHA / "phase2_vectors"), "--suffix", "",
         "--merge-rule", "the committed stands (test)", "--out-dir", str(demo), "--arms", "v120,v120_3ha",
         "--fallback-vectors", str(root / "none"), "--jobs", "4", *SMOKE],
        cwd=REPO, env=_env(), capture_output=True, text=True, timeout=3600, check=False)
    codes = {}
    for name, (proc, log) in running.items():
        codes[name] = proc.wait(timeout=3600)
        log.close()
    assert codes == dict.fromkeys(commands, 0), {n: (root / f"{n}.stdout").read_text()[-2000:] for n in commands}
    return {"root": root, "demo": demo, "driver": driver}


@pytest.mark.slow
def test_wrapper_output_is_the_plain_scripts_byte_for_byte(real_runs):
    name = "odisha_phase3_3_results_rot120_boot200.txt"
    plain = (real_runs["root"] / "plain_both" / name).read_bytes()
    assert plain == (real_runs["root"] / "wrap_both" / name).read_bytes()
    assert b"this is the PRIMARY analysis" not in plain and b"_rot120_boot200" in plain      # a test run, and it says so


@pytest.mark.slow
def test_single_arm_path_through_the_wrapper(real_runs):
    """One arm alone, as AlphaEarth will be run: five tests, Holm over five, no arm comparison."""
    name = "odisha_phase3_3_results_v120_rot120.txt"
    plain = real_runs["root"] / "plain_one" / name
    assert plain.read_bytes() == (real_runs["root"] / "wrap_one" / name).read_bytes()
    text = plain.read_text()
    assert "10 ha arm ONLY" in text and "ARM COMPARISON -- NOT RUN" in text
    rows = D.parse_significance(plain)
    assert len(rows) == 5 and {(r["arm"], r["stand_ceiling_ha"], r["holm_family"]) for r in rows} == {("feature_vector", 10, 5)}
    assert [r["test"] for r in rows] == list(D.TESTS)
    # the same observed scores as the committed two-arm file: the stands and the plots are the same
    both = D.parse_significance(PRIMARY)
    assert [r["score"] for r in rows] == [pick(both, 10, t)["score"] for t in D.TESTS]
    assert [r["n_plots"] for r in rows] == [267, 184, 184, 266, 266]


@pytest.mark.slow
def test_driver_on_the_committed_stands_gives_the_committed_results(real_runs):
    demo, driver = real_runs["demo"], real_runs["driver"]
    assert driver.returncode == 0, driver.stdout[-3000:] + driver.stderr[-3000:]
    assert "NOT THE DECLARED DRAWS" in driver.stdout

    # the join: one table for both stand sizes, equal to the two committed tables
    joined = pd.read_csv(demo / D.JOINED_NAME)
    for arm, committed in (("v120", ODISHA / "phase2_plots_joined_districts.csv"),
                           ("v120_3ha", ODISHA / "phase3_3ha" / "phase2_plots_joined_districts.csv")):
        cols = ["plot_key", *W.arm_columns(arm, ["merged", "snic", "dissolved"])]
        pd.testing.assert_frame_equal(joined[cols], pd.read_csv(committed)[cols])
    # no run record or raster sample was staged, so the join printed no cross-check against one
    report = (demo / D.JOIN_RESULTS_NAME).read_text()
    assert "raster cross-check" not in report and report.count("_run.json missing") == 8

    # the scores: the committed score files, byte for byte, primary and three checks, both sizes
    for arm in ("v120", "v120_3ha"):
        for _, _, sens in D.ANALYSES:
            name = D.score_name(arm, sens)
            assert (demo / name).read_bytes() == (ODISHA / name).read_bytes(), name

    # the chance test, staged stands and one plot table: what the plain script gives on the committed files
    name = "odisha_phase3_3_results_rot120_boot200.txt"
    assert (demo / name).read_bytes() == (real_runs["root"] / "plain_both" / name).read_bytes()
    names = [D.significance_name(sens, ["v120", "v120_3ha"], 120, 200) for _, _, sens in D.ANALYSES]
    assert all((demo / n).is_file() for n in names)
    for n in names:                    # results only: run times are in the logs
        assert "took" not in (demo / n).read_text()
        assert "took" in (demo / n).with_suffix(".log").read_text()

    manifest = json.loads((demo / D.MANIFEST_NAME).read_text())
    assert manifest["merge_rule"] == "the committed stands (test)"
    assert len(manifest["staged"]) == 2 * 4 * 3 and {s["from"] for s in manifest["staged"].values()} == {"stands-dir"}
    one = manifest["staged"]["odisha_v120_3ha_koraput_stands_merged.geojson"]
    assert one["source"] == "odisha_script/phase2_vectors/odisha_v120_3ha_koraput_stands_merged.geojson"
    assert one["sha256"] == D.sha256(ODISHA / "phase2_vectors" / "odisha_v120_3ha_koraput_stands_merged.geojson")
    (run,) = manifest["runs"]
    assert run["git"]["commit"] and run["git"]["dirty"] in (True, False)
    assert run["failed"] == [] and run["not_run"] == [] and run["alphaearth_declaration"] is None
    assert "--merge-rule" in run["command"]
    wrote = sorted([D.JOINED_NAME, D.JOIN_RESULTS_NAME, *names,
                    *(D.score_name(a, s) for a in ("v120", "v120_3ha") for _, _, s in D.ANALYSES)])
    assert sorted(run["written"]) == wrote == sorted(manifest["result_files"])
    assert all(run["written"][n] == D.sha256(demo / n) for n in wrote)
    # everything the folder holds is a result file, the manifest or a git-ignored log
    assert sorted(p.name for p in demo.iterdir() if p.suffix != ".log") == sorted([*wrote, D.MANIFEST_NAME])

    # a test run is not collected
    with pytest.raises(D.Refused):
        D.collect(demo, demo / "rows.json", None)


@pytest.mark.slow
def test_a_second_run_scores_on_the_same_plot_table_or_not_at_all(real_runs):
    demo = real_runs["demo"]
    base = [sys.executable, str(ODISHA / "odisha_phase3_demo_fes.py"), "--stands-dir", str(ODISHA / "phase2_vectors"),
            "--suffix", "", "--out-dir", str(demo), "--fallback-vectors", str(real_runs["root"] / "none"), "--arms", "v120"]

    def go(*more: str) -> subprocess.CompletedProcess:
        return subprocess.run([*base, *more], cwd=REPO, env=_env(), capture_output=True, text=True, check=False)

    before = (demo / D.JOINED_NAME).read_bytes()
    got = go("--merge-rule", "the committed stands (test)")                 # a join for one arm would drop the other
    assert got.returncode == 2 and "v120_3ha" in got.stderr
    got = go("--merge-rule", "another rule", "--steps", "score")
    assert got.returncode == 2 and "merge rule" in got.stderr
    got = go("--merge-rule", "the committed stands (test)", "--steps", "score")
    assert got.returncode == 0, got.stdout[-2000:] + got.stderr[-2000:]
    assert (demo / D.JOINED_NAME).read_bytes() == before
    manifest = json.loads((demo / D.MANIFEST_NAME).read_text())
    assert [r["steps"] for r in manifest["runs"]] == [["join", "score", "significance"], ["score"]]
    assert len(manifest["runs"][1]["written"]) == 4 and len(manifest["result_files"]) == 14

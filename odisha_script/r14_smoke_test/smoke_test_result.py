"""Offline: the smoke test's verdict, rule by rule and run by run (the round 14 record, Done, the round
resumed again), from the files its declaration names. Rule 6 (within each run, the k elbow and the
fit are one fit, the types reach the layers, the angle means are unit-bounded and each centroid lies
in its polygon's box) is worked here; rules 1 to 5 are read from what
the wrapper, the one reading of the Drive states, the copy tool, the elbow's read-back and the live
check's script wrote. A file a rule needs that is missing or unreadable fails that rule, named.
Writes <records>/r14_smoke_test.json (results only, no times) and, beside it,
r14_smoke_test_run.json (how it was made: the command, when, the git block of the repo, and the
SHA-256 of every file read and of the round's judging scripts). Exit 0 if the smoke test passes,
1 if not.

    python smoke_test_result.py <records> <off-git folder> <wrapper state file> <run> <run>
"""
import csv
import hashlib
import importlib.util
import io
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

spec = importlib.util.spec_from_file_location("r14_live_check", "odisha_script/r14_live_check.py")
assert spec is not None and spec.loader is not None
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)

HERE = Path(__file__).resolve().parent
SCRIPTS = ("smoke_assets.py", "list_k_elbow_assets.py", "elbow_read_back.py", "smoke_vs_second_check.py",
           "smoke_test_result.py", "after_smoke.sh", "preflight_smoke.sh", "round_use.py")
ANGLE_PAIRS = (("aspect_sin", "aspect_cos"), ("ndvi_phase_annual_sin", "ndvi_phase_annual_cos"))
records, off_git, state_file = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
runs = sys.argv[4:]
K = 5
STAGE_FILES = ("k_elbow.csv", "k_elbow_stand_table.csv", "k_elbow_fit_rows.csv", "k_elbow_types.csv",
               "k_elbow_preprocessing.json", "clustering_stand_table.csv", "clustering_fit_rows.csv",
               "clustering_kmeans.json", "k_elbow_run.json")
# Not ended at the one reading: READY or RUNNING. CANCEL_REQUESTED fails: the round cancels only
# after the reading, so at it a cancellation can only be someone else's (the gate's review, part 11).
NOT_ENDED = ("READY", "RUNNING")
read: dict[str, str] = {}


def path_of(name: str) -> Path:
    """A record in the records folder, or, if the copy tool kept it off git, in the off-git folder."""
    for folder in (records, off_git):
        if (folder / name).exists():
            return folder / name
    raise FileNotFoundError(name)


def text_of(name: str) -> str:
    p = path_of(name)
    data = p.read_bytes()
    read[str(p)] = hashlib.sha256(data).hexdigest()
    return data.decode()


def rows_of(name: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text_of(name))))


def guarded(rule):
    """Run one rule; an error in it (a missing or unreadable file) fails it, named."""
    try:
        return rule()
    except Exception as e:  # noqa: BLE001 - the verdict names the failure
        return {"passes": False, "error": f"{type(e).__name__}: {e}"}


def rule1():
    """The batch completes: every config done in one of the label's batches through export (a batch
    resumed under the label skips what an earlier one finished)."""
    state = json.loads(state_file.read_text())
    read[str(state_file)] = hashlib.sha256(state_file.read_bytes()).hexdigest()
    batches = [*state.get("earlier_batches", []), state]
    done = sorted({c for b in batches if b.get("through", "export") == "export" for c in b.get("done", [])})
    attention = {c: why for b in batches for c, why in (b.get("needs_attention") or {}).items()}
    return {"batches_of_the_label": len(batches), "configs_done": done,
            "configs_needing_attention": attention, "configs_left": sorted(set(runs) - set(done)),
            "passes": set(runs) <= set(done)}


def rule2(r1):
    """Every task ends well: the cache exports by the stages' exits (a stage exits 0 only when every
    cache export it waited on completed); the Drive exports by the one reading of their states."""
    out: dict = {"runs": {}}
    for run in runs:
        states = json.loads(text_of(f"{run}_drive_exports.json"))
        files = states.get("files") or {}
        out["runs"][run] = {
            "drive_files": len(files), "states_at_the_reading": states.get("states"),
            "files_with_no_task_id": states.get("files_with_no_task_id"),
            "not_ended_at_the_reading": sorted(k for k, f in files.items() if f.get("state") in NOT_ENDED),
            "ended_badly": {k: f.get("state") for k, f in files.items()
                            if f.get("state") != "COMPLETED" and f.get("state") not in NOT_ENDED},
        }
    out["passes"] = r1["passes"] is True and all(
        r["drive_files"] > 0 and not r["files_with_no_task_id"] and r["ended_badly"] == {}
        for r in out["runs"].values())
    return out


def rule3():
    missing = {}
    for run in runs:
        gone = []
        for f in STAGE_FILES:
            try:
                path_of(f"{run}_{f}")
            except FileNotFoundError:
                gone.append(f)
        missing[run] = gone
    return {"missing": missing, "passes": all(not m for m in missing.values())}


def rule4():
    back = json.loads(text_of("r14_smoke_test_elbow_read_back.json"))
    return {"passes": back.get("passes") is True and sorted(back.get("runs", {})) == sorted(runs)}


def accepted(z: dict, kind: str) -> set:
    """The outputs of a kind's first manifest that criterion 0 credits to a failed pass."""
    name = z["first_manifests"][kind].get("manifest")
    return {h["output"] for h in z.get("hits_made_by_a_failed_pass", []) if h.get("manifest") == name}


def rule5():
    crit = json.loads(text_of("r14_smoke_test_live_check_rules.json"))["criteria"]
    others = {name: c["passes"] for name, c in crit.items() if name != "0_both_runs_from_scratch"}
    zero_ok = {}
    for run in runs:
        z = crit["0_both_runs_from_scratch"]["runs"][run]
        f = z["first_manifests"]
        zero_ok[run] = (
            f["features"]["passes"] is False and f["features"]["computed_in_it"] == []
            and {o["cache_status"] for o in f["features"]["not_computed_in_it"]} == {"hit"}
            and f["segmentation"]["passes"] is False and f["segmentation"]["computed_in_it"] == []
            and {o["cache_status"] for o in f["segmentation"]["not_computed_in_it"]} == {"hit"}
            # The k elbow and clustering parts pass as criterion 0 judges them: every output computed
            # in the first manifest of its kind, or a hit on an asset a failed pass of the run made
            # (criterion 0's own exception, listed in its results; the gate's review, part 11).
            and f["k_elbow"]["passes"] is True and f["clustering"]["passes"] is True
            and set(f["k_elbow"]["computed_in_it"]) | accepted(z, "k_elbow") == {"k_elbow/k_elbow"}
            and set(f["clustering"]["computed_in_it"]) | accepted(z, "clustering")
            == {"clustering/cluster_labels", "clustering/feature_stack"}
            and z["one_layout_and_one_key_per_stage"] is True and z["stages_fmu_does_not_have"] == [])
    return {"criteria_1_to_6": others, "criterion_0_fails_only_as_it_must": zero_ok,
            "passes": set(others.values()) == {True} and all(zero_ok.values())
            and crit["0_both_runs_from_scratch"]["passes"] is False}


def rule6_run(run: str) -> dict:
    r: dict = {}
    kmeans = json.loads(text_of(f"{run}_clustering_kmeans.json"))
    elbow = {int(row["k"]): row for row in rows_of(f"{run}_k_elbow.csv")}
    at_k = elbow.get(K)
    agreement = kmeans.get("starts_agreement") or {}
    a = {"k": kmeans.get("k"),
         "wcss": [float(at_k["wcss"]) if at_k else None, round(float(kmeans["wcss"]), 6)],
         "ari_median": [float(at_k["ari_median"]) if at_k else None, round(float(agreement["ari_median"]), 6)],
         "ari_min": [float(at_k["ari_min"]) if at_k else None, round(float(agreement["ari_min"]), 6)]}
    a["passes"] = kmeans.get("k") == K and at_k is not None and all(a[x][0] == a[x][1] for x in ("wcss", "ari_median", "ari_min"))
    r["a_the_elbow_at_k_is_the_fit"] = a
    types, fit = rows_of(f"{run}_k_elbow_types.csv"), rows_of(f"{run}_clustering_fit_rows.csv")
    label = next(iter(fit[0])) if fit else "stand_lbl"
    lt, lf = [t[label] for t in types], [f[label] for f in fit]
    b = {"labels": len(lf), "same_labels_in_order": lt == lf, "none_twice": len(set(lf)) == len(lf),
         "same_in_fit": [t["in_fit"] for t in types] == [f["in_fit"] for f in fit],
         "types_differing": sum(t[f"type_k{K}"] != f["type"] for t, f in zip(types, fit, strict=False))}
    b["passes"] = b["labels"] > 0 and b["same_labels_in_order"] and b["none_twice"] and b["same_in_fit"] and b["types_differing"] == 0
    r["b_the_types_at_k_are_the_fits"] = b
    tables = check.compare_table(text_of(f"{run}_k_elbow_stand_table.csv"), text_of(f"{run}_clustering_stand_table.csv"))
    fit_text = text_of(f"{run}_clustering_fit_rows.csv")
    at = list(fit[0]).index("type")
    without_type = "\n".join(",".join(c for j, c in enumerate(line.split(",")) if j != at)
                             for line in fit_text.splitlines()) + "\n"
    fit_rows = check.compare_table(text_of(f"{run}_k_elbow_fit_rows.csv"), without_type)
    r["c_the_two_tables_agree"] = {"tables_of_units": tables, "fit_rows": fit_rows,
                                   "passes": tables.get("passes") is True and fit_rows.get("passes") is True}
    layer = json.loads(text_of(f"{run}_stands_merged.geojson"))
    by_label = {f[label]: f["type"] for f in fit}
    polygons = [ft["properties"] for ft in layer["features"]]
    with_a_polygon = {str(int(p["stand_lbl"])) for p in polygons if p.get("stand_lbl") is not None}

    def wrong(p: dict) -> bool:
        lbl = str(int(p["stand_lbl"]))
        if lbl in by_label:
            return p.get("cluster_id") is None or str(int(p["cluster_id"])) != by_label[lbl]
        return p.get("cluster_id") is not None

    bad = [p.get("stand_id") for p in polygons if wrong(p)]
    d = {"polygons": len(polygons), "fit_labels_without_a_polygon": sorted(set(by_label) - with_a_polygon, key=int),
         "n_polygons_with_a_wrong_cluster_id": len(bad), "polygons_with_a_wrong_cluster_id": bad[:20]}
    d["passes"] = d["polygons"] > 0 and not d["fit_labels_without_a_polygon"] and not bad
    r["d_the_types_reach_the_layer"] = d
    # e. Q33's stand means of each angle's sine and cosine: the mean of unit vectors is no longer
    # than 1 (by 1e-12, for the rounding of one-pixel or uniform pieces).
    e: dict = {}
    for s_name, c_name in ANGLE_PAIRS:
        vals = [(p.get(s_name), p.get(c_name)) for p in polygons]
        finite = [(a, b) for a, b in vals if isinstance(a, (int, float)) and isinstance(b, (int, float))]
        over = [round(a * a + b * b, 17) for a, b in finite if a * a + b * b > 1 + 1e-12]
        e[s_name.rsplit("_", 1)[0]] = {"polygons_checked": len(finite), "over_1": over[:10], "n_over_1": len(over)}
    e["passes"] = all(v["polygons_checked"] > 0 and v["n_over_1"] == 0 for v in e.values() if isinstance(v, dict))
    r["e_the_angle_means_are_unit_bounded"] = e
    # f. Q21's centroid, the mean of the polygon's pixel centres, lies within the bounding box of
    # the polygon's own vertices (every ring of every part).
    outside = []
    for ft in layer["features"]:
        p, g = ft["properties"], ft.get("geometry") or {}
        parts = g.get("coordinates") or []
        if g.get("type") == "Polygon":
            parts = [parts]
        xs = [pt[0] for part in parts for ring in part for pt in ring]
        ys = [pt[1] for part in parts for ring in part for pt in ring]
        lon, lat = p.get("centroid_lon"), p.get("centroid_lat")
        if not xs or lon is None or lat is None or not (min(xs) <= lon <= max(xs) and min(ys) <= lat <= max(ys)):
            outside.append(p.get("stand_id"))
    r["f_each_centroid_lies_in_its_polygons_box"] = {"polygons": len(layer["features"]), "n_outside": len(outside),
                                                      "outside": outside[:20], "passes": bool(layer["features"]) and not outside}
    r["passes"] = all(r[x]["passes"] for x in r)
    return r


rules: dict = {}
rules["1_the_batch_completes"] = guarded(rule1)
rules["2_every_task_ends_well"] = guarded(lambda: rule2(rules["1_the_batch_completes"]))
rules["3_every_file_copied"] = guarded(rule3)
rules["4_the_elbow_tables_read_back"] = guarded(rule4)
rules["5_the_live_checks_rules"] = guarded(rule5)
six = {run: guarded(lambda run=run: rule6_run(run)) for run in runs}
rules["6_within_each_run"] = {"runs": six, "passes": bool(six) and all(r["passes"] is True for r in six.values())}
out = {"what": "The smoke test's verdict (the round 14 record, Done, the round resumed again): rules 1 to 6",
       "runs": runs, "rules": rules}
out["passes"] = len(runs) == 2 and all(v["passes"] is True for v in rules.values())
check.results_only(out)
(records / "r14_smoke_test.json").write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
sys.path.insert(0, "src")
from fmu.utils.provenance import git_state  # noqa: E402

run_record = {
    "command": " ".join(["python", *sys.argv]),
    "ran_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "git": git_state(),
    "files_read_sha256": dict(sorted(read.items())),
    "judging_scripts_sha256": {s: hashlib.sha256((HERE / s).read_bytes()).hexdigest()
                               for s in SCRIPTS if (HERE / s).exists()},
}
(records / "r14_smoke_test_run.json").write_text(json.dumps(run_record, indent=1, default=str) + "\n")
print(json.dumps({k: v["passes"] for k, v in rules.items()}, indent=1), "smoke test passes:", out["passes"])
sys.exit(0 if out["passes"] else 1)

"""odisha_script/r14_elbow_report.py, offline: the elbow report of R3's first half (round 14, Task 6).

The records are made up for the nineteen R3 runs and written as the k elbow step writes them
(fmu.utils.stand_table.table_csv, fmu.stages.k_elbow._elbow_csv, the preprocessing record), with
tables of 18 to 30 stands whose labels repeat across districts.

The sweep. The script calls fmu.stages.k_elbow.fit_space_sweep itself (the first test checks that
the names it calls are the pipeline's own functions). One sweep with its settings (k 2 to 12, 25
starts) takes 15 s or more whatever the table's size, and even with 3 starts about 4 s on a busy
Mac (each k enters threadpool_limits, and each of the 300 pairs of starts is one adjusted Rand
index; measured 26 Oct 2026), so the other tests replace it with a stand-in that records each call
and returns a sweep made from the rows by a closed form. They check the script's call (the pooled
rows, made here independently, every row, k 2 to 12, seed 42, 25 starts) and that the script writes
what the sweep returns. The test marked slow runs a pool, and the check of a run, with the real
sweep and the script's own settings. No Earth Engine, no network.

Each pool is also swept with the same rows in reverse order (Jaskaran's answer (b) to question 9,
27 Oct 2026). The stand-in's numbers depend on which row is first, as k-means++'s depend on the
order of the rows, so in these tests the two orders' elbows differ and each can be told apart.
"""

from __future__ import annotations

import csv
import dataclasses
import hashlib
import io
import json
import re
import shutil
import struct
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "odisha_script"))

import r14_elbow_report as R  # noqa: E402, N812

from fmu.stages import k_elbow  # noqa: E402
from fmu.utils import stand_table as st  # noqa: E402

DECOMPOSED = {"handcrafted": ["ndvi_phase_annual", "aspect"], "alphaearth": []}
BANDS = {
    "handcrafted": ["canopy_height", "vh_iqr", "slope", "ndvi_phase_annual_sin", "ndvi_phase_annual_cos",
                    "aspect_sin", "aspect_cos"],
    "alphaearth": ["A00", "A01", "A02", "A03"],
}
SKEWED = {"vh_iqr", "A01"}  # right-skewed in the made-up tables, so the rule logs them
RUNS = [(area, arm, run) for area in R.AREAS for arm, run in area.runs.items()]
TILE = "odisha_v120_3ha_tile10km_angul_keptland_s1desc_r14"
SCRIPTS_CALL = {"k_min": 2, "k_max": 12, "seed": 42, "n_starts": 25}


# ---------------------------------------------------------------------- made-up records
def made_up_table(seed: int, arm: str, n: int) -> st.StandTable:
    """A table of stands as the clustering stage reads it: labels 2, 4, ... in every district."""
    rng = np.random.default_rng(seed)
    cols: dict[str, np.ndarray] = {}
    for b in BANDS[arm]:
        if not b.endswith(("_sin", "_cos")):
            cols[b] = rng.lognormal(0.0, 0.9, n) if b in SKEWED else rng.normal(10.0, 2.0, n)
    for d in DECOMPOSED[arm]:
        angle = rng.uniform(0.0, 2 * np.pi, n)
        cols[f"{d}_sin"], cols[f"{d}_cos"] = np.sin(angle), np.cos(angle)
    in_fit = rng.random(n) > 0.2
    in_fit[:4] = True
    return st.StandTable(labels=np.arange(1, n + 1, dtype=np.int64) * 2, bands=list(BANDS[arm]),
                         values=np.column_stack([cols[b] for b in BANDS[arm]]), in_fit=in_fit)


def preprocessing_record(table: st.StandTable, arm: str) -> dict[str, Any]:
    """The record the k elbow step writes beside the table (fmu.stages.k_elbow._in_fit_space)."""
    pre = st.preprocess(table, rule="right_skew", threshold=1.0, decomposed=DECOMPOSED[arm])
    return {**pre.record, "cyclic_decomposition_log": DECOMPOSED[arm],
            "raw_band_names": [b for b in table.bands if not b.endswith(("_sin", "_cos"))]
            + DECOMPOSED[arm], "candidate_bands": list(table.bands), "n_table_rows": len(table.labels),
            "n_rows_fitted": int(table.in_fit.sum()), "unit_key": "stand_clusters"}


def made_up_elbow(seed: int) -> dict[str, Any]:
    """A run's elbow as the step's sweep gives it (k_elbow.fit_space_sweep), its numbers made up."""
    rng = np.random.default_rng(seed)
    ks = list(range(2, 13))
    wcss = [round(float(500.0 / k**0.8 + rng.uniform(0.0, 8.0)), 6) for k in ks]
    med = [round(float(rng.uniform(0.6, 1.0)), 6) for _ in ks]
    low = [round(float(m - rng.uniform(0.0, 0.4)), 6) for m in med]
    return {"ks": ks, "inertia": wcss, "ari_median": med, "ari_min": low, "elbow_k": k_elbow.knee(ks, wcss)}


def write_run(folder: Path, run: str, table: st.StandTable, record: dict, elbow: dict) -> None:
    """The run's three files, written as the step and scripts/copy_run_results.py write them."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{run}_k_elbow.csv").write_text(k_elbow._elbow_csv(elbow))
    (folder / f"{run}_k_elbow_stand_table.csv").write_text(st.table_csv(table))
    (folder / f"{run}_k_elbow_preprocessing.json").write_text(st.json_text(record))


def move_off_git(folder: Path, name: str, off_dir: Path) -> Path:
    """Move a file off git and write its <run>_files_off_git.json, as copy_run_results.py does."""
    off_dir.mkdir(parents=True, exist_ok=True)
    where = off_dir / name
    shutil.move(folder / name, where)
    data = where.read_bytes()
    run = name.split("_k_elbow")[0]
    (folder / f"{run}_files_off_git.json").write_text(json.dumps({
        "what": f"The files of {run} over 5 MB, kept off git: name, size, SHA-256, where.",
        "files": [{"file": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                   "where": str(where.resolve())}]}, indent=1) + "\n")
    return where


@pytest.fixture(scope="module")
def records(tmp_path_factory) -> SimpleNamespace:
    """Records of the nineteen runs, the tile's table of stands off git."""
    base = tmp_path_factory.mktemp("r14")
    folder, off_dir = base / "first_half", base / "off_git"
    tables, recs, elbows = {}, {}, {}
    for i, (_, arm, run) in enumerate(RUNS):
        tables[run] = made_up_table(100 + i, arm, 18 + (5 * i) % 13)
        recs[run] = preprocessing_record(tables[run], arm)
        elbows[run] = made_up_elbow(200 + i)
        write_run(folder, run, tables[run], recs[run], elbows[run])
    off = move_off_git(folder, f"{TILE}_k_elbow_stand_table.csv", off_dir)
    return SimpleNamespace(folder=folder, off_path=off, tables=tables, records=recs, elbows=elbows)


# ---------------------------------------------------------------------- the stand-in sweep
def stand_in_sweep(rows: np.ndarray, every_row: np.ndarray, *, k_min: int, k_max: int, seed: int,
                   n_starts: int) -> dict[str, Any]:
    """A sweep shaped as fit_space_sweep's, made from the rows by a closed form, in no time. Its
    numbers depend on the first row too, as k-means++'s depend on the order of the rows."""
    ks = [k for k in range(k_min, k_max + 1) if k < len(rows)]
    total = float(((rows - rows.mean(axis=0)) ** 2).sum())
    first = float(np.abs(rows[0]).sum())
    inertia = [round(total / k**0.9 + 0.37 * (k % 3) + 0.05 * first * (k % 2), 6) for k in ks]
    med = [round(1.0 - 0.031 * (k - k_min) - 0.001 * (seed % 7) - 0.001 * (round(first, 3) % 7), 6)
           for k in ks]
    low = [round(m - 0.12 - 0.001 * n_starts, 6) for m in med]
    return {"n_rows": len(rows), "ks": ks, "inertia": inertia, "ari_median": med, "ari_min": low,
            "elbow_k": k_elbow.knee(ks, inertia), "types": [[0] * len(every_row) for _ in ks]}


class Recorder:
    """The stand-in sweep, each call recorded: (rows, every row, the settings). The sweep is made
    from the copies recorded, so a test that sweeps a recorded call's rows gets the same numbers."""

    def __init__(self) -> None:
        self.calls: list[tuple[np.ndarray, np.ndarray, dict[str, Any]]] = []

    def __call__(self, rows: np.ndarray, every_row: np.ndarray, **kwargs: Any) -> dict[str, Any]:
        rows, every_row = np.array(rows), np.array(every_row)
        self.calls.append((rows, every_row, dict(kwargs)))
        return stand_in_sweep(rows, every_row, **kwargs)


@pytest.fixture
def sweeps(monkeypatch) -> Recorder:
    recorder = Recorder()
    monkeypatch.setattr(R, "fit_space_sweep", recorder)
    return recorder


def args(records: SimpleNamespace, out: Path, *more: str) -> list[str]:
    return ["--records", str(records.folder), "--out-dir", str(out), *more]


@pytest.fixture(scope="module")
def written(records, tmp_path_factory) -> SimpleNamespace:
    """One run of the script on the records, the runs' elbows taken as they are."""
    out = tmp_path_factory.mktemp("out")
    recorder = Recorder()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(R, "fit_space_sweep", recorder)
        assert R.main(args(records, out, "--no-run-check")) == 0
    return SimpleNamespace(out=out, calls=recorder.calls)


def read_csv(path: Path) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(path.read_text())))


def by_series(rows: list[dict[str, str]]) -> dict[tuple[str, str, str], list[dict[str, str]]]:
    """The csv's rows by area, arm and row order."""
    out: dict[tuple[str, str, str], list[dict[str, str]]] = {}
    for r in rows:
        out.setdefault((r["area"], r["arm"], r["row_order"]), []).append(r)
    return out


def pooled_rows(records: SimpleNamespace, size: str, arm: str) -> tuple[np.ndarray, np.ndarray]:
    """The pooled rows made here, from the made-up tables: the four districts in order, then the
    preprocessing over every row; (rows in the fit, every row)."""
    tables = [records.tables[R.district_run(d, size, arm)] for d in R.DISTRICTS]
    values = np.vstack([t.values for t in tables])
    in_fit = np.concatenate([t.in_fit for t in tables])
    table = st.StandTable(labels=np.arange(len(values), dtype=np.int64), bands=list(tables[0].bands),
                          values=values, in_fit=in_fit)
    pre = st.preprocess(table, rule="right_skew", threshold=1.0, decomposed=DECOMPOSED[arm])
    return pre.values[in_fit], pre.values


def loaded(records: SimpleNamespace, size: str, arm: str) -> dict[str, R.RunRecords]:
    out = {}
    for d in R.DISTRICTS:
        run = R.load_run(records.folder, R.district_run(d, size, arm), [])
        assert run is not None
        out[d] = run
    return out


def png_chunks(data: bytes) -> list[tuple[bytes, bytes]]:
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    chunks, i = [], 8
    while i < len(data):
        (n,) = struct.unpack(">I", data[i:i + 4])
        chunks.append((data[i + 4:i + 8], data[i + 8:i + 8 + n]))
        i += 12 + n
    return chunks


# ---------------------------------------------------------------------- the areas and the sweep
def test_the_script_sweeps_and_takes_the_knee_with_the_pipelines_own_functions():
    """Not copies: the names the script calls are fmu.stages.k_elbow's functions."""
    assert R.fit_space_sweep is k_elbow.fit_space_sweep
    assert R.knee is k_elbow.knee
    assert R.N_STARTS == st.KMEANS_STARTS == 25


def test_the_areas_are_the_nineteen_r3_configs_with_the_sweep_the_script_makes(monkeypatch):
    """Each run named is an R3 config of its arm and stand size, and every R3 config's k elbow is
    the sweep the pooled elbows make (k 2 to 12, seed 42, 25 starts, in the fit's space)."""
    from fmu.config import load_config

    monkeypatch.chdir(REPO)
    names = sorted(run for _, _, run in RUNS)
    assert names == sorted(p.stem for p in (REPO / "configs").glob("*_r14.yaml")) and len(names) == 19
    assert (R.K_MIN, R.K_MAX, R.SEED, R.N_STARTS) == (2, 12, 42, 25)
    for area, arm, run in RUNS:
        cfg = load_config(REPO / "configs" / f"{run}.yaml")
        assert (cfg.clustering.feature_source == "embedding") == (arm == "alphaearth"), run
        assert cfg.merge.enabled and cfg.merge.max_area_ha == {"3ha": 3.0, "10ha": 10.0}[area.stand_size], run
        assert cfg.clustering.fit_excludes_stands_below_min_area and cfg.merge.min_area_ha == 1.0, run
        assert (cfg.clustering.log_rule, cfg.clustering.skewness_threshold) == ("right_skew", 1.0), run
        e = cfg.k_elbow
        assert (e.in_fit_space, e.k_min, e.k_max, e.seed, e.n_init) == (True, 2, 12, 42, 25), run
    assert [a.key for a in R.AREAS] == [
        *(f"{d}_3ha" for d in R.DISTRICTS), *(f"{d}_10ha" for d in R.DISTRICTS),
        "sanjay_van", "tile_angul_10km", "pooled_3ha", "pooled_10ha"]
    assert R.AREAS[9].runs == {"handcrafted": TILE}  # the tile: one arm


# ---------------------------------------------------------------------- the csv
def test_the_csv_has_one_row_per_area_arm_row_order_and_k_with_each_runs_own_numbers(records, written):
    path = written.out / "r14_elbow.csv"
    assert R.CSV_COLUMNS == ["area", "arm", "stand_size", "row_order", "k", "wcss", "ari_median", "ari_min",
                             "is_knee", "n_rows_fitted"]
    assert path.read_text().splitlines()[0] == ",".join(R.CSV_COLUMNS)
    rows = read_csv(path)
    series = by_series(rows)
    # Each run's elbow in its one order; each pool's in the stated order, then in reverse order.
    assert list(series) == [(a.key, arm, order) for a in R.AREAS for arm in R.ARMS
                            if arm in a.runs or a.pooled
                            for order in (("stated", "reversed") if a.pooled else ("stated",))]
    assert len(series) == 27  # 9 areas x 2 arms, the tile 1, the 4 pools twice
    for area, arm, run in RUNS:
        mine, elbow = series[(area.key, arm, "stated")], records.elbows[run]
        assert [int(r["k"]) for r in mine] == elbow["ks"] == list(range(2, 13))
        assert [float(r["wcss"]) for r in mine] == elbow["inertia"]
        assert [float(r["ari_median"]) for r in mine] == elbow["ari_median"]
        assert [float(r["ari_min"]) for r in mine] == elbow["ari_min"]
        assert {r["stand_size"] for r in mine} == {area.stand_size}
        assert {int(r["n_rows_fitted"]) for r in mine} == {int(records.tables[run].in_fit.sum())}
    for size in R.SIZES:
        for arm in R.ARMS:
            fitted = sum(int(records.tables[R.district_run(d, size, arm)].in_fit.sum()) for d in R.DISTRICTS)
            for order in ("stated", "reversed"):
                mine = series[(f"pooled_{size}", arm, order)]
                assert [int(r["k"]) for r in mine] == list(range(2, 13))
                assert {r["stand_size"] for r in mine} == {size}
                assert {int(r["n_rows_fitted"]) for r in mine} == {fitted}


def test_each_series_flags_one_knee_the_knee_of_its_sums_of_squares(records, written):
    series = by_series(read_csv(written.out / "r14_elbow.csv"))
    for (area, arm, order), mine in series.items():
        ks, wcss = [int(r["k"]) for r in mine], [float(r["wcss"]) for r in mine]
        assert {r["is_knee"] for r in mine} <= {"0", "1"}
        assert [k for k, r in zip(ks, mine, strict=True) if r["is_knee"] == "1"] == [k_elbow.knee(ks, wcss)], (
            area, arm, order)
    for area, arm, run in RUNS:
        flagged = [int(r["k"]) for r in series[(area.key, arm, "stated")] if r["is_knee"] == "1"]
        assert flagged == [records.elbows[run]["elbow_k"]]


def test_a_knee_flag_that_is_not_the_knee_of_the_sums_of_squares_stops(records, tmp_path):
    run = R.district_run("dhenkanal", "3ha", "alphaearth")
    for p in records.folder.glob(f"{run}_*"):
        shutil.copy(p, tmp_path / p.name)
    elbow = records.elbows[run]
    wrong = next(k for k in elbow["ks"] if k != elbow["elbow_k"])
    (tmp_path / f"{run}_k_elbow.csv").write_text(k_elbow._elbow_csv({**elbow, "elbow_k": wrong}))
    with pytest.raises(SystemExit, match=f"the knee it flags \\({wrong}\\) is not the knee"):
        R.load_run(tmp_path, run, [])


def test_a_run_with_one_of_its_files_missing_stops(records, tmp_path):
    run = R.district_run("angul", "10ha", "handcrafted")
    for p in records.folder.glob(f"{run}_*"):
        if not p.name.endswith("_preprocessing.json"):
            shutil.copy(p, tmp_path / p.name)
    with pytest.raises(SystemExit, match="k_elbow_preprocessing.json is not in"):
        R.load_run(tmp_path, run, [])
    assert R.load_run(tmp_path, "a_run_with_no_files", []) is None


def test_a_table_whose_bands_or_counts_are_not_its_records_stops(records, tmp_path):
    run = R.district_run("kendujhar", "10ha", "handcrafted")
    table, record = records.tables[run], records.records[run]
    write_run(tmp_path, run, table, {**record, "n_rows_fitted": record["n_rows_fitted"] + 1},
              records.elbows[run])
    with pytest.raises(SystemExit, match="in the fit; .* says"):
        R.load_run(tmp_path, run, [])
    write_run(tmp_path, run, table, {**record, "candidate_bands": table.bands[::-1]}, records.elbows[run])
    with pytest.raises(SystemExit, match="not the candidate bands"):
        R.load_run(tmp_path, run, [])


# ---------------------------------------------------------------------- the pools
def test_the_pooled_sweep_is_fit_space_sweep_on_the_pooled_preprocessed_rows(records, written):
    """Each pool's call is the script's sweep (k 2 to 12, seed 42, 25 starts) on the four districts'
    rows pooled and preprocessed together, with every pooled row, and the csv holds what it
    returned: with the first test, the pooled numbers are fit_space_sweep's on those rows. Its
    second call is the same sweep on the same rows in reverse order, with every row reversed (the
    same preprocessing, made once), and the csv's reversed rows hold what that returned (Jaskaran's
    answer (b) to question 9, 27 Oct 2026)."""
    assert len(written.calls) == 8  # the four pools, each in two orders; --no-run-check
    series = by_series(read_csv(written.out / "r14_elbow.csv"))
    for size in R.SIZES:
        for arm in R.ARMS:
            rows, every = pooled_rows(records, size, arm)
            backwards = (np.ascontiguousarray(rows[::-1]), np.ascontiguousarray(every[::-1]))
            for order, (want_rows, want_every) in (("stated", (rows, every)), ("reversed", backwards)):
                calls = [c for c in written.calls if c[0].shape == want_rows.shape
                         and np.array_equal(c[0], want_rows)]
                assert len(calls) == 1, (size, arm, order)
                _, every_row, kwargs = calls[0]
                assert np.array_equal(every_row, want_every)
                assert kwargs == SCRIPTS_CALL
                sweep = stand_in_sweep(want_rows, want_every, **SCRIPTS_CALL)
                mine = series[(f"pooled_{size}", arm, order)]
                assert [int(r["k"]) for r in mine] == sweep["ks"]
                assert [float(r["wcss"]) for r in mine] == sweep["inertia"]
                assert [float(r["ari_median"]) for r in mine] == sweep["ari_median"]
                assert [float(r["ari_min"]) for r in mine] == sweep["ari_min"]
                assert [int(r["k"]) for r in mine if r["is_knee"] == "1"] == [
                    k_elbow.knee(sweep["ks"], sweep["inertia"])]
            # The two orders' elbows differ here (the stand-in depends on the first row), so the
            # reversed rows are not the stated ones written twice.
            assert ([r["wcss"] for r in series[(f"pooled_{size}", arm, "stated")]]
                    != [r["wcss"] for r in series[(f"pooled_{size}", arm, "reversed")]])


def test_the_pooled_rows_are_keyed_by_district_and_stand_label(records):
    runs = loaded(records, "3ha", "handcrafted")
    table, keys = R.pool_table("3ha", "handcrafted", runs)
    tables = [records.tables[R.district_run(d, "3ha", "handcrafted")] for d in R.DISTRICTS]
    assert keys == [(d, int(lbl)) for d, t in zip(R.DISTRICTS, tables, strict=True) for lbl in t.labels]
    assert len(set(keys)) == len(keys) and len({lbl for _, lbl in keys}) < len(keys)  # labels repeat
    assert np.array_equal(table.values, np.vstack([t.values for t in tables]))
    assert np.array_equal(table.in_fit, np.concatenate([t.in_fit for t in tables]))


def test_tables_with_other_bands_or_another_rule_stop_the_pool(records):
    runs = loaded(records, "3ha", "handcrafted")
    t = runs["kendujhar"].table
    more = st.StandTable(labels=t.labels, bands=[*t.bands, "elevation"],
                         values=np.column_stack([t.values, np.ones(len(t.labels))]), in_fit=t.in_fit)
    with pytest.raises(SystemExit, match="different candidate bands .*only in .*: \\['elevation'\\]"):
        R.pool_table("3ha", "handcrafted", {**runs, "kendujhar": dataclasses.replace(runs["kendujhar"], table=more)})
    order = [1, 0, *range(2, len(t.bands))]
    swapped = st.StandTable(labels=t.labels, bands=[t.bands[i] for i in order], values=t.values[:, order],
                            in_fit=t.in_fit)
    with pytest.raises(SystemExit, match="the same bands, in another order"):
        R.pool_table("3ha", "handcrafted", {**runs, "kendujhar": dataclasses.replace(runs["kendujhar"], table=swapped)})
    other = dataclasses.replace(runs["koraput"], record={**runs["koraput"].record, "log_rule": "abs_skew"})
    with pytest.raises(SystemExit, match="differs in log_rule"):
        R.pool_table("3ha", "handcrafted", {**runs, "koraput": other})
    # The other two keys of the records, and the label column (the gate's review, part 3).
    for key, value in (("skewness_threshold", 1.5), ("cyclic_decomposition_log", ["aspect"])):
        other = dataclasses.replace(runs["koraput"], record={**runs["koraput"].record, key: value})
        with pytest.raises(SystemExit, match=f"differs in {key}"):
            R.pool_table("3ha", "handcrafted", {**runs, "koraput": other})
    other = dataclasses.replace(runs["koraput"], label_name="snic_label")
    with pytest.raises(SystemExit, match="labels its rows stand_lbl, .* snic_label"):
        R.pool_table("3ha", "handcrafted", {**runs, "koraput": other})


# ---------------------------------------------------------------------- the off-git files
def test_an_off_git_file_is_read_from_where_its_record_says(records, written):
    record = json.loads((written.out / "r14_elbow_run.json").read_text())
    inputs = {i["file"]: i for i in record["inputs"]}
    entry = inputs[f"{TILE}_k_elbow_stand_table.csv"]
    assert entry["off_git"] is True and Path(entry["path"]) == records.off_path.resolve()
    assert entry["sha256"] == hashlib.sha256(records.off_path.read_bytes()).hexdigest()
    assert f"{TILE}_files_off_git.json" in inputs
    assert len(record["inputs"]) == 19 * 3 + 1
    assert all(not i["off_git"] for name, i in inputs.items() if name != f"{TILE}_k_elbow_stand_table.csv")


def test_an_off_git_file_that_is_not_the_one_its_record_names_stops(records, tmp_path):
    folder = tmp_path / "records"
    folder.mkdir()
    for p in records.folder.glob(f"{TILE}_*"):
        shutil.copy(p, folder / p.name)
    assert R.load_run(folder, TILE, []) is not None
    name = f"{TILE}_k_elbow_stand_table.csv"
    changed = tmp_path / "changed" / name
    changed.parent.mkdir()
    text = records.off_path.read_text()  # the last digit of the last value changed
    changed.write_text(text[:-2] + ("1" if text[-2] != "1" else "2") + "\n")
    off = json.loads((folder / f"{TILE}_files_off_git.json").read_text())
    off["files"][0]["where"] = str(changed)
    (folder / f"{TILE}_files_off_git.json").write_text(json.dumps(off))
    with pytest.raises(SystemExit, match="not the file its off-git record names: its SHA-256"):
        R.load_run(folder, TILE, [])
    off["files"][0]["where"] = str(tmp_path / "nowhere" / name)
    (folder / f"{TILE}_files_off_git.json").write_text(json.dumps(off))
    with pytest.raises(SystemExit, match="which is not here"):
        R.load_run(folder, TILE, [])
    off["files"][0]["where"] = str(records.off_path)
    (folder / f"{TILE}_files_off_git.json").write_text(json.dumps(off))
    (folder / name).write_text("stand_lbl,in_fit,a\n")  # a copy in the records that is another file
    with pytest.raises(SystemExit, match="differ"):
        R.load_run(folder, TILE, [])


# ---------------------------------------------------------------------- the check of each run
def test_the_run_check_passes_on_a_runs_own_elbow_and_stops_on_any_other(records, sweeps, tmp_path):
    """The elbow made again from the table by the pooled elbows' code is the run's own (the run's
    elbow is written here by the same sweep, the stand-in); a number changed, or a preprocessing
    record that is not its table's, stops the script."""
    run = R.district_run("angul", "3ha", "handcrafted")
    table, record = records.tables[run], records.records[run]
    pre = st.preprocess(table, rule="right_skew", threshold=1.0, decomposed=DECOMPOSED["handcrafted"])
    own = stand_in_sweep(pre.values[table.in_fit], pre.values, **SCRIPTS_CALL)
    write_run(tmp_path, run, table, record, own)
    loaded_run = R.load_run(tmp_path, run, [])
    assert loaded_run is not None
    R.check_run(loaded_run)
    rows, every_row, kwargs = sweeps.calls[-1]
    assert kwargs == SCRIPTS_CALL and np.array_equal(rows, pre.values[table.in_fit])
    assert np.array_equal(every_row, pre.values)
    inertia = [*own["inertia"][:4], round(own["inertia"][4] + 1e-6, 6), *own["inertia"][5:]]
    write_run(tmp_path, run, table, record, {**own, "inertia": inertia, "elbow_k": k_elbow.knee(own["ks"], inertia)})
    with pytest.raises(SystemExit, match="differs from its own in wcss"):
        R.check_run(R.load_run(tmp_path, run, []))
    bad = {**record, "skew_before": {**record["skew_before"], "slope": 9.0}}
    write_run(tmp_path, run, table, bad, own)
    with pytest.raises(SystemExit, match="preprocessing made again .* differs from its record in \\['skew_before'\\]"):
        R.check_run(R.load_run(tmp_path, run, []))


def test_by_default_every_runs_elbow_is_made_again(records, sweeps, tmp_path, monkeypatch):
    checked: list[str] = []
    monkeypatch.setattr(R, "check_run", lambda run: checked.append(run.run))
    monkeypatch.setattr(R, "draw_figure", lambda area, arms, path: path.write_bytes(b""))
    assert R.main(args(records, tmp_path)) == 0
    assert sorted(checked) == sorted(run for _, _, run in RUNS)
    report = (tmp_path / "r14_elbow_report.md").read_text()
    assert "is the run's own in every number (19 of 19 runs with a record)" in report
    assert json.loads((tmp_path / "r14_elbow_run.json").read_text())["run_check"] is True


@pytest.mark.slow
def test_with_the_real_sweep_a_pool_and_a_runs_check_are_fit_space_sweeps(records, tmp_path):
    """The real sweep and the script's own settings, 25 starts at each k from 2 to 12 (a minute or
    more); the pool's elbow in both orders."""
    pool = R.make_pool("10ha", "alphaearth", loaded(records, "10ha", "alphaearth"))
    rows, every = pooled_rows(records, "10ha", "alphaearth")
    for elbow, (r, e) in ((pool.elbow, (rows, every)), (pool.elbow_reversed, (rows[::-1], every[::-1]))):
        sweep = k_elbow.fit_space_sweep(np.ascontiguousarray(r), np.ascontiguousarray(e), **SCRIPTS_CALL)
        assert elbow.numbers() == (sweep["ks"], sweep["inertia"], sweep["ari_median"], sweep["ari_min"],
                                   k_elbow.knee(sweep["ks"], sweep["inertia"]))
    run = R.district_run("koraput", "3ha", "alphaearth")
    table = records.tables[run]
    pre = st.preprocess(table, rule="right_skew", threshold=1.0, decomposed=[])
    write_run(tmp_path, run, table, records.records[run],
              k_elbow.fit_space_sweep(pre.values[table.in_fit], pre.values, **SCRIPTS_CALL))
    R.check_run(R.load_run(tmp_path, run, []))


# ---------------------------------------------------------------------- what is written
def test_it_refuses_to_write_over_an_earlier_run(records, tmp_path):
    (tmp_path / "r14_elbow.csv").write_text("an earlier run\n")
    with pytest.raises(SystemExit, match="refusing to write over .*r14_elbow.csv"):
        R.main(args(records, tmp_path, "--no-run-check"))
    assert (tmp_path / "r14_elbow.csv").read_text() == "an earlier run\n"
    assert [p.name for p in tmp_path.iterdir()] == ["r14_elbow.csv"]
    figures = tmp_path / "b" / "r14_elbow"
    figures.mkdir(parents=True)
    (figures / "angul_3ha.png").write_bytes(b"an earlier figure")
    with pytest.raises(SystemExit, match="refusing to write over"):
        R.main(args(records, tmp_path / "b", "--no-run-check"))
    assert [p.name for p in (tmp_path / "b").iterdir()] == ["r14_elbow"]


def test_with_overwrite_a_second_run_writes_the_same_files_byte_for_byte(records, written, sweeps, tmp_path):
    again = tmp_path / "again"
    shutil.copytree(written.out, again)
    assert R.main(args(records, again, "--no-run-check", "--overwrite")) == 0
    names = ["r14_elbow.csv", "r14_elbow_report.md", *(f"r14_elbow/{a.key}.png" for a in R.AREAS)]
    for name in names:
        assert (again / name).read_bytes() == (written.out / name).read_bytes(), name


def test_a_crash_while_writing_leaves_nothing_and_the_next_run_writes_everything(records, sweeps, tmp_path,
                                                                                   monkeypatch):
    """The files are written in a folder of their own and put in place at the end: a failure that
    is not a stop (a full disk, Ctrl-C) leaves no part of the outputs (the gate's review, part 3)."""
    draw, calls = R.draw_figure, []

    def fails_on_the_fourth(area, arms, path):
        calls.append(area.key)
        if len(calls) == 4:
            raise OSError(28, "No space left on device")
        draw(area, arms, path)

    monkeypatch.setattr(R, "draw_figure", fails_on_the_fourth)
    with pytest.raises(OSError, match="No space left"):
        R.main(args(records, tmp_path, "--no-run-check"))
    assert list(tmp_path.iterdir()) == []
    monkeypatch.setattr(R, "draw_figure", draw)

    def interrupted(*a, **k):
        raise KeyboardInterrupt

    # The environment (pip freeze, seconds) is read before anything is put in place.
    monkeypatch.setattr(R, "environment", interrupted)
    with pytest.raises(KeyboardInterrupt):
        R.main(args(records, tmp_path, "--no-run-check"))
    assert list(tmp_path.iterdir()) == []
    monkeypatch.undo()
    monkeypatch.setattr(R, "fit_space_sweep", sweeps)
    # A kill no finally block sees (SIGKILL) leaves the work folder: the next run refuses it, and
    # --overwrite removes it (the gate's review, part 5).
    left = tmp_path / ".r14_elbow.abcd1234"
    (left / "r14_elbow").mkdir(parents=True)
    (left / "r14_elbow" / "angul_3ha.png").write_bytes(b"part of a run")
    with pytest.raises(SystemExit, match=r"refusing to write over .*\.r14_elbow\.abcd1234"):
        R.main(args(records, tmp_path, "--no-run-check"))
    assert R.main(args(records, tmp_path, "--no-run-check", "--overwrite")) == 0
    assert sorted(p.name for p in tmp_path.iterdir()) == ["r14_elbow", "r14_elbow.csv", "r14_elbow_report.md",
                                                          "r14_elbow_run.json"]
    assert len(list((tmp_path / "r14_elbow").iterdir())) == 12


def test_one_figure_per_area_1200_pixels_wide_with_no_date(written):
    folder = written.out / "r14_elbow"
    assert sorted(p.name for p in folder.iterdir()) == sorted(f"{a.key}.png" for a in R.AREAS)
    assert len(list(folder.iterdir())) == 12
    for path in folder.iterdir():
        chunks = png_chunks(path.read_bytes())
        assert chunks[0][0] == b"IHDR" and struct.unpack(">II", chunks[0][1][:8]) == (1200, 960)
        assert b"tIME" not in {kind for kind, _ in chunks}
        texts = b"".join(body for kind, body in chunks if kind in (b"tEXt", b"iTXt", b"zTXt"))
        assert b"Software" not in texts and not re.search(rb"20\d\d", texts), path.name


def test_the_knee_labels_name_their_arm_and_two_knees_at_one_point_share_one():
    assert [t for t, *_ in R.knee_labels({"handcrafted": (5, 0.48), "alphaearth": (5, 0.47)})] == [
        "both knees, k = 5"]
    assert [t for t, *_ in R.knee_labels({"handcrafted": (4, 0.4), "alphaearth": (9, 0.3)})] == [
        "Hand-crafted knee, k = 4", "AlphaEarth knee, k = 9"]
    near = R.knee_labels({"handcrafted": (5, 0.6), "alphaearth": (6, 0.3)})
    assert [(t, ha, va) for t, _, _, ha, va in near] == [  # above right; the lower below left
        ("Hand-crafted knee, k = 5", "left", "bottom"), ("AlphaEarth knee, k = 6", "right", "top")]
    near_the_left = R.knee_labels({"handcrafted": (3, 0.3), "alphaearth": (4, 0.6)})
    assert [(ha, va) for _, _, _, ha, va in near_the_left] == [("left", "top"), ("left", "bottom")]
    ((text, xy, _, ha, _),) = R.knee_labels({"handcrafted": (11, 0.2)})
    assert (text, xy, ha) == ("knee, k = 11", (11, 0.2), "right")  # one arm; near the right edge


def test_the_report_gives_every_areas_knees_and_a_section_with_its_figure(written):
    """One row of knees per area; for a pool, a second row, its knees with the same rows in reverse
    order, right below it."""
    report = (written.out / "r14_elbow_report.md").read_text()
    knees = {key: next(int(r["k"]) for r in mine if r["is_knee"] == "1")
             for key, mine in by_series(read_csv(written.out / "r14_elbow.csv")).items()}
    summary = report.split("## The knees\n", 1)[1].split("\n## ", 1)[0].splitlines()
    for area in R.AREAS:
        titles = [(area.title, "stated")] + ([(R.reversed_title(area), "reversed")] if area.pooled else [])
        for title, order in titles:
            (row,) = [line for line in summary if line.startswith(f"| {title} |")]
            cells = [c.strip() for c in row.strip().strip("|").split("|")]
            assert cells[1] == str(knees[(area.key, "handcrafted", order)]), (area.key, order)
            assert cells[2] == (str(knees[(area.key, "alphaearth", order)]) if (area.key, "alphaearth", order) in knees
                                else "no run (one arm)"), (area.key, order)
        if area.pooled:
            rows = [line for line in summary if line.startswith("| ")]
            i = rows.index(next(line for line in rows if line.startswith(f"| {area.title} |")))
            assert rows[i + 1].startswith(f"| {area.title}, the same rows in reverse order |")
        assert f"\n## {area.title}\n" in report
        assert f"](r14_elbow/{area.key}.png)" in report
    assert "reads no plot and computes no field score, and it recommends no k" in report
    assert "It was not made again here (`--no-run-check`)" in report


def test_each_pooled_section_gives_both_knees_and_both_tables(written):
    """A pool's section gives its knees and its table of k in the stated order, then in reverse
    order, each from the csv's rows of that order (Jaskaran's answer (b) to question 9)."""
    report = (written.out / "r14_elbow_report.md").read_text()
    series = by_series(read_csv(written.out / "r14_elbow.csv"))
    for area in (a for a in R.AREAS if a.pooled):
        section = report.split(f"\n## {area.title}\n", 1)[1].split("\n## ", 1)[0]
        parts = {}
        for order, head in (("stated", "**The rows in the stated order**"),
                            ("reversed", "**The same rows in reverse order**")):
            assert section.count(head) == 1, (area.key, order)
            parts[order] = section.split(head, 1)[1]
        parts["stated"] = parts["stated"].split("**The same rows in reverse order**", 1)[0]
        for order, text in parts.items():
            knees = {arm: next(int(r["k"]) for r in series[(area.key, arm, order)] if r["is_knee"] == "1")
                     for arm in R.ARMS}
            assert f"Knees: hand-crafted k = {knees['handcrafted']}, AlphaEarth k = {knees['alphaearth']}." in text
            table = [line for line in text.splitlines() if line.startswith("| ") and line[2].isdigit()]
            assert [int(line.split("|")[1]) for line in table] == list(range(2, 13)), (area.key, order)
            for line in table:
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                k = int(cells[0])
                for j, arm in enumerate(R.ARMS):
                    (row,) = [r for r in series[(area.key, arm, order)] if int(r["k"]) == k]
                    knee = " (knee)" if row["is_knee"] == "1" else ""
                    assert cells[1 + 3 * j] == R._num(float(row["wcss"])) + knee, (area.key, order, k, arm)
                    assert cells[2 + 3 * j] == R._ari(float(row["ari_median"]))
                    assert cells[3 + 3 * j] == R._ari(float(row["ari_min"]))
    # A run's section has one table, in its one order.
    section = report.split(f"\n## {R.AREAS[0].title}\n", 1)[1].split("\n## ", 1)[0]
    assert "reverse order" not in section and len([ln for ln in section.splitlines() if ln.startswith("| 2 |")]) == 1


def test_the_report_gives_each_pools_row_counts(records, written):
    report = (written.out / "r14_elbow_report.md").read_text()
    for size in R.SIZES:
        section = report.split(f"\n## The four districts pooled, {R.SIZE_TEXT[size]} stands\n", 1)[1].split("\n## ", 1)[0]
        tables = {arm: [records.tables[R.district_run(d, size, arm)] for d in R.DISTRICTS] for arm in R.ARMS}
        for i, d in enumerate(R.DISTRICTS):
            cells = [f"{len(tables[arm][i].labels):,} ({int(tables[arm][i].in_fit.sum()):,})" for arm in R.ARMS]
            assert f"| {d.capitalize()} | {cells[0]} | {cells[1]} |" in section
        total = [f"{sum(len(t.labels) for t in tables[arm]):,} ({sum(int(t.in_fit.sum()) for t in tables[arm]):,})"
                 for arm in R.ARMS]
        assert f"| Pooled | {total[0]} | {total[1]} |" in section
        assert "preprocessed together by the runs' rule (`right_skew`" in section


def test_the_caption_gives_the_ari_scale_the_figure_has(tmp_path, monkeypatch):
    """Two starts can agree less than chance would (an ARI below 0, as at k = 2 on three of the eight
    _r9 10 ha tables in the gate review's offline sweep of them, part 3): the bottom panel then goes
    below 0, and the caption gives the axis the figure draws (part 5)."""
    from matplotlib.figure import Figure

    area = R.AREAS[0]
    drawn: list[tuple[float, float]] = []
    monkeypatch.setattr(Figure, "savefig", lambda fig, *a, **k: drawn.append(fig.axes[1].get_ylim()))

    def arms(low: float) -> dict[str, R.Series]:
        e = R.Elbow(ks=[2, 3], wcss=[10.0, 5.0], ari_median=[0.9, 0.8], ari_min=[low, 0.5], knee=None)
        return {"handcrafted": R.Series(area=area, arm="handcrafted", elbow=e, n_rows_fitted=10,
                                        n_table_rows=12, source="x")}

    for low, said in ((0.2, "on a scale from 0 to 1."),
                      (-0.0986, "on a scale from 0 to 1 taken down to -0.1486, below the lowest, -0.0986,"),
                      (-4e-05, "on a scale from 0 to 1 taken down to -0.0500, below the lowest, -4.0e-05,")):
        R.draw_figure(area, arms(low), tmp_path / "figure.png")
        assert drawn[-1] == (R.ari_floor(arms(low)), 1.0)
        caption = " ".join(R._caption(arms(low)).split())
        assert said in caption, caption
        assert ("on a scale from 0 to 1." in caption) is (low >= 0)
    # An index that would print as -0.0000, or as 0 with a minus sign, does not.
    assert (R._ari(-4e-05), R._ari(-0.0), R._ari(0.0), R._ari(1.0), R._ari(0.12345)) == (
        "-4.0e-05", "0.0000", "0.0000", "1", "0.1235")


def _elbow(seed: int, low: float = 0.3) -> R.Elbow:
    e = made_up_elbow(seed)
    return R.Elbow(ks=e["ks"], wcss=e["inertia"], ari_median=e["ari_median"],
                   ari_min=[low, *e["ari_min"][1:]], knee=e["elbow_k"])


def test_a_pools_figure_has_the_same_rows_in_reverse_order_beside_the_stated_order(tmp_path, monkeypatch):
    """A pool's figure has two columns on the same axes: the rows in the stated order, and the same
    rows in reverse order, each arm in its own colour in both (Jaskaran's answer (b) to question 9);
    a run's figure has one. The caption says so, and its index scale covers both orders."""
    from matplotlib.colors import to_hex
    from matplotlib.figure import Figure

    figures: list[Any] = []
    monkeypatch.setattr(Figure, "savefig", lambda fig, *a, **k: figures.append(fig))
    pool = next(a for a in R.AREAS if a.key == "pooled_10ha")
    stated = {arm: _elbow(300 + i) for i, arm in enumerate(R.ARMS)}
    backwards = {arm: _elbow(310 + i, low=-0.12 if arm == "alphaearth" else 0.3) for i, arm in enumerate(R.ARMS)}
    arms = {arm: R.Series(area=pool, arm=arm, elbow=stated[arm], n_rows_fitted=50, n_table_rows=60,
                          source="pooled", elbow_reversed=backwards[arm]) for arm in R.ARMS}
    R.draw_figure(pool, arms, tmp_path / "pooled.png")
    (fig,) = figures
    top_left, top_right, bottom_left, bottom_right = fig.axes
    assert top_left.get_title(loc="left") == "The rows in the stated order"
    assert top_right.get_title(loc="left") == "The same rows in reverse order"
    for top, bottom, elbows in ((top_left, bottom_left, stated), (top_right, bottom_right, backwards)):
        for arm, e in elbows.items():
            colour = R.COLOUR[arm].lower()
            curves = [ln for ln in top.get_lines() if to_hex(ln.get_color()) == colour and len(ln.get_xdata()) > 1]
            assert len(curves) == 1, arm
            assert np.allclose(curves[0].get_ydata(), np.array(e.wcss) / e.wcss[0])
            lines = [list(ln.get_ydata()) for ln in bottom.get_lines() if to_hex(ln.get_color()) == colour]
            assert e.ari_median in lines and e.ari_min in lines, arm
            rings = [ln for ln in top.get_lines()
                     if len(ln.get_xdata()) == 1 and to_hex(ln.get_markeredgecolor()) == colour]
            assert [ln.get_xdata()[0] for ln in rings] == [e.knee], arm
        # Each panel's legend names its knees; no label on the curves, in panels half as wide.
        assert [t.get_text() for t in top.get_legend().get_texts()] == [
            f"{R.ARM_TEXT[arm]}: knee at k = {e.knee}" for arm, e in elbows.items()]
        assert list(top.texts) == []
    # One axis per row: the reverse order's lowest index, -0.12, takes both index panels below 0.
    assert bottom_left.get_ylim() == bottom_right.get_ylim() == (R.ari_floor(arms), 1.0)
    assert R.ari_floor(arms) == pytest.approx(-0.17)
    assert top_left.get_ylim() == top_right.get_ylim()
    caption = " ".join(R._caption(arms).split())
    assert caption.startswith("*Left: the rows in the stated order; right: the same rows in reverse order, on the "
                              "same axes.")
    assert "taken down to -0.1700, below the lowest, -0.1200," in caption
    # A run's figure: one column, as before.
    run_arms = {arm: dataclasses.replace(s, area=R.AREAS[0], source="x", elbow_reversed=None)
                for arm, s in arms.items()}
    R.draw_figure(R.AREAS[0], run_arms, tmp_path / "run.png")
    assert len(figures[-1].axes) == 2
    labels = [t.get_text() for t in figures[-1].axes[0].texts]  # its knees labelled on the curve, as before
    assert labels and all("knee" in text for text in labels), labels
    assert "reverse order" not in R._caption(run_arms)


def test_the_paragraph_on_how_the_numbers_are_made_says_the_runs_rule(records, written, sweeps, tmp_path):
    """The rule and threshold are the records', one for every run, and the paragraph says how each
    band is scaled and how the numbers are rounded (the gate's review, part 3)."""
    report = " ".join((written.out / "r14_elbow_report.md").read_text().split())
    assert "`clustering.log_rule` right_skew: a band whose IQR is at most 1e-9 is dropped, and an angle's " \
           "sine and cosine only together, when their shared spread is; only a band skewed to the right, " \
           "skew above 1.0, is logged" in report
    assert "each other band is centred by its median and divided by its IQR" in report
    assert "the sine and cosine of an angle by their medians and by their shared spread, the root mean square " \
           "of their two IQRs" in report
    assert "6 decimals in the csv" in report and "4 in the tables" in report
    # Each pooled elbow in two orders (Jaskaran's answer (b) to question 9, 27 Oct 2026).
    assert "k-means++ depends on the order of the rows, so each pooled elbow is also made with the same rows " \
           "in reverse order, with the same preprocessing and the same sweep, and given beside it (the " \
           "declaration's note of 27 Oct 2026); each run's elbow has one order, the run's." in report
    # Every run at another threshold: the paragraph gives it.
    folder = tmp_path / "records"
    shutil.copytree(records.folder, folder)
    for path in folder.glob("*_k_elbow_preprocessing.json"):
        path.write_text(json.dumps({**json.loads(path.read_text()), "skewness_threshold": 1.5}))
    off = records.off_path
    assert R.main(["--records", str(folder), "--out-dir", str(tmp_path / "out"), "--no-run-check"]) == 0, off
    report = " ".join((tmp_path / "out" / "r14_elbow_report.md").read_text().split())
    assert "skew above 1.5, is logged" in report and "skew above 1.0" not in report
    # One run with another threshold, or another rule: the paragraph could not say both; it stops.
    run = "sanjay_van_baseline_keptland_r14"
    for key, value in (("skewness_threshold", 1.0), ("log_rule", "abs_skew")):
        path = folder / f"{run}_k_elbow_preprocessing.json"
        path.write_text(json.dumps({**json.loads(path.read_text()), "skewness_threshold": 1.5, key: value}))
        with pytest.raises(SystemExit, match=f"preprocessing differs.*{run}"):
            R.main(["--records", str(folder), "--out-dir", str(tmp_path / f"out_{key}"), "--no-run-check"])
        path.write_text(json.dumps({**json.loads(path.read_text()), "skewness_threshold": 1.5,
                                    "log_rule": "right_skew"}))
    # Every run with a rule the paragraph does not describe: it stops.
    for path in folder.glob("*_k_elbow_preprocessing.json"):
        path.write_text(json.dumps({**json.loads(path.read_text()), "log_rule": "abs_skew"}))
    with pytest.raises(SystemExit, match="describes right_skew"):
        R.main(["--records", str(folder), "--out-dir", str(tmp_path / "out_abs"), "--no-run-check"])


def test_the_report_reads_what_the_copy_tool_copies(records, tmp_path):
    """A run's files as the k elbow step writes them, in a run tree, copied by
    scripts/copy_run_results.py --through k_elbow (in the repo and, over a lowered limit, off git),
    then read by the report: the records it reads are the step's own (the gate's review, part 3)."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("copy_run_results", REPO / "scripts" / "copy_run_results.py")
    assert spec is not None and spec.loader is not None
    copy_tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(copy_tool)
    run = "odisha_alphaearth_3ha_squares_angul_keptland_r14"
    tree = tmp_path / "tree"
    vec = tree / "odisha_script" / "phase2_vectors"
    write_run(vec, run, records.tables[run], records.records[run], records.elbows[run])
    for name in ("k_elbow_fit_rows.csv", "k_elbow_types.csv"):
        (vec / f"{run}_{name}").write_text("stand_lbl,in_fit\n2,1\n")
    (vec / f"{run}_k_elbow_run.json").write_text(json.dumps({"run_dir": f"runs/{run}_20261027_100002"}))
    for i, last in enumerate(["features_static", "segmentation", "k_elbow"]):
        d = tree / "runs" / f"{run}_20261027_1000{i:02d}"
        d.mkdir(parents=True)
        (d / "manifest.json").write_text(json.dumps({"stages": [{"name": last}], "config": {}}))
    want = R.load_run(vec, run, [])
    assert want is not None
    for limit in (copy_tool.LIMIT, 300):
        dest, off = tmp_path / f"dest_{limit}", tmp_path / f"off_{limit}"
        copy_tool.LIMIT = limit
        copy_tool.copy(tree, run, dest, off, through="k_elbow")
        reads: list[R.Read] = []
        got = R.load_run(dest, run, reads)
        assert got is not None and got.elbow == want.elbow and got.record == want.record
        assert np.array_equal(got.table.values, want.table.values) and got.table.bands == want.table.bands
        assert any(r.off_git for r in reads) is (limit == 300)


def test_the_results_hold_no_date_time_or_commit_and_the_record_does(written):
    record = json.loads((written.out / "r14_elbow_run.json").read_text())
    commit = record["git"]["commit"]
    for name in ("r14_elbow.csv", "r14_elbow_report.md"):
        text = (written.out / name).read_text()
        assert not R.STAMP.search(text) and not re.search(r"\b20\d\d-\d\d-\d\d\b", text), name
        assert commit is None or commit not in text, name  # the whole hash: a prefix can be all digits
    assert record["command_line"].startswith("python odisha_script/r14_elbow_report.py --records ")
    assert re.match(r"20\d\d-\d\d-\d\dT\d\d:\d\d:\d\d", record["date"])
    assert {"commit", "dirty", "modified", "untracked_code"} <= set(record["git"]) and "root" not in record["git"]
    assert record["result_files"][:2] == ["r14_elbow.csv", "r14_elbow_report.md"] and len(record["result_files"]) == 14
    assert record["run_check"] is False and record["missing_runs"] == []
    assert set(record["packages"]) == {"numpy", "scikit-learn", "matplotlib"}
    # The csv's row orders, said in the record: a pool's two, a run's one (question 9).
    assert record["row_orders"] == R.ROW_ORDERS and list(R.ROW_ORDERS) == ["stated", "reversed"]


def test_the_git_state_at_the_end_is_read_once_the_results_are_in_place(records, sweeps, tmp_path, monkeypatch):
    """git_at_end is read after the csv, the report and the figures are in place and before the run
    record is, so that a re-run that rewrites committed results shows them, and the work folder,
    empty by then, does not show (the gate's review, part 5)."""
    seen: list[list[str]] = []
    real = R.git_block

    def spy(now: bool = False) -> dict[str, Any]:
        if now:
            seen.append(sorted(p.name for p in tmp_path.iterdir() if not p.name.startswith(".")))
            seen.append([p.name for p in tmp_path.glob(".r14_elbow.*/**/*") if p.is_file()])
        return real(now)

    monkeypatch.setattr(R, "git_block", spy)
    assert R.main(args(records, tmp_path, "--no-run-check")) == 0
    assert seen == [["r14_elbow", "r14_elbow.csv", "r14_elbow_report.md"], []]


def test_a_run_with_no_record_stops_the_script_unless_it_is_allowed(records, sweeps, tmp_path, monkeypatch):
    folder = tmp_path / "records"
    shutil.copytree(records.folder, folder)
    gone = R.district_run("koraput", "10ha", "alphaearth")
    for p in folder.glob(f"{gone}_*"):
        p.unlink()
    with pytest.raises(SystemExit, match=f"no records of 1 run\\(s\\) in .*: {gone}"):
        R.main(["--records", str(folder), "--out-dir", str(tmp_path / "a"), "--no-run-check"])
    assert not (tmp_path / "a").exists()
    drawn: list[tuple[str, list[str]]] = []

    def draw(area: R.Area, arms: dict, path: Path) -> None:
        drawn.append((area.key, list(arms)))
        path.write_bytes(b"")

    monkeypatch.setattr(R, "draw_figure", draw)
    out = tmp_path / "b"
    assert R.main(["--records", str(folder), "--out-dir", str(out), "--no-run-check", "--allow-missing"]) == 0
    series = {(area, arm) for area, arm, _ in by_series(read_csv(out / "r14_elbow.csv"))}
    assert ("koraput_10ha", "alphaearth") not in series and ("pooled_10ha", "alphaearth") not in series
    assert ("koraput_10ha", "handcrafted") in series and ("pooled_10ha", "handcrafted") in series
    assert ("koraput_10ha", ["handcrafted"]) in drawn and ("pooled_10ha", ["handcrafted"]) in drawn
    report = (out / "r14_elbow_report.md").read_text()
    assert f"**No record of 1 of the 19 runs:** `{gone}`" in report
    assert f"AlphaEarth: `{gone}`, no record." in report
    assert f"AlphaEarth: not computed, no record of `{gone}`." in report
    assert json.loads((out / "r14_elbow_run.json").read_text())["missing_runs"] == [gone]

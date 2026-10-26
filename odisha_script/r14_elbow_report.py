"""The elbow report of R3's first half (round 14, Task 6), for Jaskaran to choose k from.

    python odisha_script/r14_elbow_report.py [--records docs/reproducibility/r14_runs/first_half]
        [--out-dir odisha_script/keptland_scores] [--stem r14_elbow] [--overwrite]
        [--no-run-check] [--allow-missing]

Offline: no Earth Engine and no network. It reads no plot and computes no field score, and it
recommends no k: for R3, k for each area is Jaskaran's choice, from this report alone, before any
R3 field score exists (odisha_script/PHASE_KEPTLAND_PREDECLARED.md, the change of 26 Oct 2026;
register entry field-r3-k-chosen-by-jaskaran-from-the-elbow-report).

THE AREAS AND ARMS, by config name (the nineteen R3 configs, configs/*_r14.yaml; not the two
_check copies, which are not R3 results): each Odisha district (angul, dhenkanal, kendujhar,
koraput) at 3 ha and at 10 ha, hand-crafted odisha_v120_<size>_squares_<district>_keptland_s1desc_r14
and AlphaEarth odisha_alphaearth_<size>_squares_<district>_keptland_r14; Sanjay Van (10 ha stands),
sanjay_van_baseline_keptland_r14 (hand-crafted) and sanjay_van_alphaearth_keptland_r14; the 10 km
tile in Angul (3 ha stands), odisha_v120_3ha_tile10km_angul_keptland_s1desc_r14, which has one arm:
hand-crafted, as R3 has no AlphaEarth run of the tile.

THE INPUTS, for each run, in --records (the first half's records, which
scripts/copy_run_results.py --through k_elbow writes), as the k elbow step wrote them
(fmu.stages.k_elbow with k_elbow.in_fit_space on):
  <run>_k_elbow.csv                 k, wcss, ari_median, ari_min, is_knee (k_elbow._elbow_csv)
  <run>_k_elbow_stand_table.csv     stand_lbl, in_fit, then each candidate band
                                    (fmu.utils.stand_table.table_csv)
  <run>_k_elbow_preprocessing.json  the preprocessing record, with log_rule, skewness_threshold,
                                    cyclic_decomposition_log, candidate_bands, n_table_rows and
                                    n_rows_fitted
A file over 5 MB is not in --records: <run>_files_off_git.json names it, with where it is and its
SHA-256. It is read from there, and a SHA-256 that differs from the record's stops the script, as
does a copy in --records that differs from it. The three files of a run are checked against each
other before anything is computed: the elbow's k run 2, 3, ... (to 12 at most), its one knee flag
is the knee of its sums of squares (fmu.stages.k_elbow.knee), the table's bands are the record's
candidate bands, and the table's rows and rows in the fit are the record's counts. A run with none
of its files stops the script, which names every such run; with --allow-missing the report is
written without them and says which they are, and a pool that needs one is not computed. A run
with some of its files and not others always stops it.

EACH RUN'S ELBOW is the run's own, as its <run>_k_elbow.csv gives it. Unless --no-run-check, each
is also made again here from the run's table of stands and preprocessing record by the code that
makes the pooled elbows (below), and the script stops if the preprocessing made again differs from
the run's record, or a number of the elbow from the run's own: so the pooled elbows are made as the
runs' are, number for number.

THE POOLED ELBOW, for each arm and stand size (four pools): the four districts' tables of stands
put together, each row keyed by its district and stand label (labels repeat across districts), in
the order angul, dhenkanal, kendujhar, koraput, and within a district in its table's order (by
stand label: k-means++ depends on the order of the rows); each row keeps its in_fit. The four
tables must have the same label column and the same candidate bands in the same order, and their
records the same log_rule, skewness_threshold and cyclic_decomposition_log, or the script stops.
The pooled table is preprocessed by fmu.utils.stand_table.preprocess with that rule, threshold and
angle pairs, over every row, and k is swept on its rows in the fit with the fit's own starts,
fmu.stages.k_elbow.fit_space_sweep(rows, every_row, k_min=2, k_max=12, seed=42, n_starts=25), the
knee by fmu.stages.k_elbow.knee. The pipeline never fits the pooled rows; the report gives their
elbow because the declaration asks for it.

WRITES, in --out-dir, and refuses to write over any of these unless --overwrite (a refusal writes
nothing; so does a stop):
  <stem>.csv          one row per area, arm and k: area, arm, stand_size, k, wcss, ari_median,
                      ari_min, is_knee, n_rows_fitted (the pools as the areas pooled_3ha and
                      pooled_10ha)
  <stem>/<area>.png   one figure per area: each arm's within-cluster sum of squares divided by its
                      own value at k = 2 (the arms' sums are in different spaces) with its knee,
                      and the starts' median and lowest pairwise adjusted Rand index
  <stem>_report.md    the report
  <stem>_run.json     the run's record: the command, when it ran, the git block of this checkout
                      (fmu.utils.provenance.git_state, read at the start of main(), and again at
                      the end), the environment, and every input read, with where it was, its
                      size and its SHA-256
stem is r14_elbow by default. The csv, the figures and the report hold results only (no date,
time or commit), so that `git diff` after a re-run shows whether it reproduced.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import hashlib
import io
import json
import re
import shlex
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
# The fmu of this checkout, whichever checkout the venv's editable install points at.
if str(REPO / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "src"))

from fmu.stages.k_elbow import fit_space_sweep, knee  # noqa: E402
from fmu.utils import stand_table as st  # noqa: E402

RECORDS = REPO / "docs" / "reproducibility" / "r14_runs" / "first_half"
OUT_DIR = HERE / "keptland_scores"
STEM = "r14_elbow"
DISTRICTS = ("angul", "dhenkanal", "kendujhar", "koraput")
SIZES = ("3ha", "10ha")
SIZE_TEXT = {"3ha": "3 ha", "10ha": "10 ha"}
ARMS = ("handcrafted", "alphaearth")
ARM_TEXT = {"handcrafted": "Hand-crafted", "alphaearth": "AlphaEarth"}  # at the start of a sentence
ARM_WORD = {"handcrafted": "hand-crafted", "alphaearth": "AlphaEarth"}  # inside one
# The sweep of every R3 run's elbow, their k_elbow block (tests/test_r14_elbow_report.py checks the
# configs): k 2 to 12, seed 42, the fit's 25 k-means++ starts.
K_MIN, K_MAX, SEED, N_STARTS = 2, 12, 42, st.KMEANS_STARTS
N_PAIRS = N_STARTS * (N_STARTS - 1) // 2
FILES = ("k_elbow.csv", "k_elbow_stand_table.csv", "k_elbow_preprocessing.json")
ELBOW_COLUMNS = ["k", "wcss", "ari_median", "ari_min", "is_knee"]
CSV_COLUMNS = ["area", "arm", "stand_size", "k", "wcss", "ari_median", "ari_min", "is_knee",
               "n_rows_fitted"]
LABEL_COLUMNS = ("stand_lbl", "snic_label")
RECORD_KEYS = ("log_rule", "skewness_threshold", "cyclic_decomposition_log", "candidate_bands",
               "n_table_rows", "n_rows_fitted")
POOL_KEYS = ("log_rule", "skewness_threshold", "cyclic_decomposition_log")
# A value holding a date and time, as scripts/copy_run_results.py looks for one.
STAMP = re.compile(r"20\d\d-\d\d-\d\dT\d\d:|20\d{6}_\d{6}")

# The figures. One colour per arm, the same in every figure: Okabe-Ito blue and vermillion, apart
# for colour-blind readers and each at least 3:1 against the white figure (Okabe-Ito's orange,
# #E69F00, is 2.3:1). Text is in grey ink, never in an arm's colour. 8 x 6.4 in at 150 dpi:
# 1200 x 960 pixels.
COLOUR = {"handcrafted": "#0072B2", "alphaearth": "#D55E00"}
INK, INK_2, GRID, AXIS = "#1a1a1a", "#4d4d4d", "#e8e8e8", "#b3b3b3"
FIG_SIZE_IN, FIG_DPI = (8.0, 6.4), 150


# ---------------------------------------------------------------------- the areas
@dataclass(frozen=True)
class Area:
    """An area of the report: its name in the files, its title, its stand size and its runs."""

    key: str
    title: str
    stand_size: str
    runs: dict[str, str]  # arm -> config name; empty for a pool
    pooled: bool = False


def district_run(district: str, size: str, arm: str) -> str:
    if arm == "handcrafted":
        return f"odisha_v120_{size}_squares_{district}_keptland_s1desc_r14"
    return f"odisha_alphaearth_{size}_squares_{district}_keptland_r14"


def make_areas() -> list[Area]:
    """The areas in the order of every file: the districts at 3 ha, at 10 ha, Sanjay Van, the
    tile, then the two pools."""
    out = [Area(f"{d}_{size}", f"{d.capitalize()}, {SIZE_TEXT[size]} stands", size,
                {arm: district_run(d, size, arm) for arm in ARMS})
           for size in SIZES for d in DISTRICTS]
    out.append(Area("sanjay_van", "Sanjay Van, 10 ha stands", "10ha",
                    {"handcrafted": "sanjay_van_baseline_keptland_r14",
                     "alphaearth": "sanjay_van_alphaearth_keptland_r14"}))
    out.append(Area("tile_angul_10km", "The 10 km tile in Angul, 3 ha stands (one arm, hand-crafted)",
                    "3ha", {"handcrafted": "odisha_v120_3ha_tile10km_angul_keptland_s1desc_r14"}))
    out += [Area(f"pooled_{size}", f"The four districts pooled, {SIZE_TEXT[size]} stands", size, {},
                 pooled=True) for size in SIZES]
    return out


AREAS = make_areas()


# ---------------------------------------------------------------------- reading the records
@dataclass
class Read:
    """One input as read: the run, the file's name, where it was read, whether off git, its size
    and its SHA-256."""

    run: str
    file: str
    path: Path
    off_git: bool
    n_bytes: int
    sha256: str


@dataclass
class Elbow:
    """An elbow: for each k, the best start's within-cluster sum of squares and the starts'
    median and lowest pairwise adjusted Rand index, and the knee."""

    ks: list[int]
    wcss: list[float]
    ari_median: list[float]
    ari_min: list[float]
    knee: int | None

    def numbers(self) -> tuple[Any, ...]:
        return self.ks, self.wcss, self.ari_median, self.ari_min, self.knee


@dataclass
class RunRecords:
    """A run's three records, read and checked against each other."""

    run: str
    elbow: Elbow
    label_name: str
    table: st.StandTable
    record: dict[str, Any]

    @property
    def n_table_rows(self) -> int:
        return len(self.table.labels)

    @property
    def n_rows_fitted(self) -> int:
        return int(self.table.in_fit.sum())


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def shown(path: Path) -> str:
    """A path as the report and the run record give it: from the repo's root when inside it."""
    try:
        return str(path.resolve().relative_to(REPO))
    except ValueError:
        return str(path)


def read_input(records: Path, run: str, name: str, reads: list[Read]) -> bytes | None:
    """The run's file `name`, from `records` or from where its off-git record says (its SHA-256
    checked); None if it is in neither. Every file read is added to `reads`."""
    here = records / name
    record = records / f"{run}_files_off_git.json"
    entry = None
    if record.exists():
        text = record.read_bytes()
        try:
            entry = {f["file"]: f for f in json.loads(text)["files"]}.get(name)
        except (ValueError, KeyError, TypeError) as e:
            raise SystemExit(f"{run}: {record} is not an off-git record ({e})") from None
        if entry is not None and not any(r.path == record for r in reads):
            reads.append(Read(run, record.name, record, False, len(text), sha256(text)))
    if entry is None:
        if not here.exists():
            return None
        data = here.read_bytes()
        reads.append(Read(run, name, here, False, len(data), sha256(data)))
        return data
    if not entry.get("where") or not entry.get("sha256"):
        raise SystemExit(f"{run}: {record.name} names {name} without where it is or its SHA-256")
    where = Path(str(entry["where"]))
    if not where.is_absolute():
        where = REPO / where  # a relative place is read from the repo's root
    if not where.is_file():
        raise SystemExit(f"{run}: {name} is off git at {where}, which is not here")
    data = where.read_bytes()
    digest = sha256(data)
    if digest != entry["sha256"]:
        raise SystemExit(f"{run}: {where} is not the file its off-git record names: its SHA-256 is "
                         f"{digest}, the record ({record.name}) says {entry['sha256']}")
    if here.exists() and sha256(here.read_bytes()) != digest:
        raise SystemExit(f"{run}: {here} and the off-git copy its record names ({where}) differ")
    reads.append(Read(run, name, where, True, len(data), digest))
    return data


def parse_elbow(text: str, where: str) -> Elbow:
    """A run's elbow table, its knee flag checked against the knee of its sums of squares."""
    rows = list(csv.reader(io.StringIO(text)))
    if not rows or rows[0] != ELBOW_COLUMNS:
        raise SystemExit(f"{where}: not a k elbow table (its columns are {rows[0] if rows else []}, "
                         f"not {ELBOW_COLUMNS})")
    try:
        if any(len(r) != len(ELBOW_COLUMNS) for r in rows[1:]):
            raise ValueError("a row of another length")
        ks = [int(r[0]) for r in rows[1:]]
        wcss, med, low = ([float(r[i]) for r in rows[1:]] for i in (1, 2, 3))
        flags = [int(r[4]) for r in rows[1:]]
    except ValueError as e:
        raise SystemExit(f"{where}: a row is not k, wcss, ari_median, ari_min, is_knee ({e})") from None
    if not ks or ks != list(range(K_MIN, K_MIN + len(ks))) or ks[-1] > K_MAX:
        raise SystemExit(f"{where}: its k are {ks}, not {K_MIN}, {K_MIN + 1}, ... to {K_MAX} at most")
    if not all(np.isfinite([*wcss, *med, *low])) or any(f not in (0, 1) for f in flags):
        raise SystemExit(f"{where}: a sum of squares or an ARI is not a number, or a knee flag is not 0 or 1")
    flagged = [k for k, f in zip(ks, flags, strict=True) if f == 1]
    expected = knee(ks, wcss)
    if flagged != ([] if expected is None else [expected]):
        raise SystemExit(f"{where}: the knee it flags ({', '.join(map(str, flagged)) or 'none'}) is not "
                         f"the knee of its sums of squares (k = {expected}; fmu.stages.k_elbow.knee)")
    return Elbow(ks=ks, wcss=wcss, ari_median=med, ari_min=low, knee=expected)


def parse_table(text: str, where: str) -> tuple[str, st.StandTable]:
    """A run's table of stands (fmu.utils.stand_table.table_csv): its label column and the table."""
    rows = list(csv.reader(io.StringIO(text)))
    header = rows[0] if rows else []
    if len(header) < 3 or header[0] not in LABEL_COLUMNS or header[1] != "in_fit":
        raise SystemExit(f"{where}: not a table of stands (its columns begin {header[:3]}, not a "
                         f"label column, in_fit and the bands)")
    bands, body = header[2:], rows[1:]
    try:
        if any(len(r) != len(header) for r in body):
            raise ValueError("a row of another length")
        labels = np.array([int(r[0]) for r in body], dtype=np.int64)
        flags = [int(r[1]) for r in body]
        values = np.array([[float(v) for v in r[2:]] for r in body], dtype=float)
    except ValueError as e:
        raise SystemExit(f"{where}: a row is not a label, in_fit and a number per band ({e})") from None
    if any(f not in (0, 1) for f in flags) or not np.all(np.isfinite(values)):
        raise SystemExit(f"{where}: an in_fit is not 0 or 1, or a value is not a number")
    try:
        table = st.StandTable(labels=labels, bands=list(bands),
                              values=values.reshape(len(body), len(bands)),
                              in_fit=np.array(flags, dtype=bool))
    except ValueError as e:
        raise SystemExit(f"{where}: {e}") from None
    return header[0], table


def load_run(records: Path, run: str, reads: list[Read]) -> RunRecords | None:
    """A run's three records, checked against each other; None if the run has none of them."""
    found = {name: read_input(records, run, f"{run}_{name}", reads) for name in FILES}
    if all(data is None for data in found.values()):
        return None
    missing = [f"{run}_{name}" for name, data in found.items() if data is None]
    if missing:
        raise SystemExit(f"{run}: {', '.join(missing)} is not in {records}, and no off-git record "
                         "names it; the run's other records are")
    data = {name: d.decode("utf-8") for name, d in found.items() if d is not None}
    elbow = parse_elbow(data["k_elbow.csv"], f"{run}_k_elbow.csv")
    label_name, table = parse_table(data["k_elbow_stand_table.csv"], f"{run}_k_elbow_stand_table.csv")
    where = f"{run}_k_elbow_preprocessing.json"
    try:
        record = json.loads(data["k_elbow_preprocessing.json"])
    except ValueError as e:
        raise SystemExit(f"{where}: not JSON ({e})") from None
    lacking = [k for k in RECORD_KEYS if k not in record] if isinstance(record, dict) else list(RECORD_KEYS)
    if lacking:
        raise SystemExit(f"{where}: not a preprocessing record of the k elbow (it lacks {lacking})")
    if table.bands != list(record["candidate_bands"]):
        raise SystemExit(f"{run}: the bands of its table of stands are not the candidate bands of {where}")
    if (len(table.labels), int(table.in_fit.sum())) != (record["n_table_rows"], record["n_rows_fitted"]):
        raise SystemExit(f"{run}: its table of stands has {len(table.labels)} rows, {int(table.in_fit.sum())} "
                         f"in the fit; {where} says {record['n_table_rows']} and {record['n_rows_fitted']}")
    return RunRecords(run=run, elbow=elbow, label_name=label_name, table=table, record=record)


# ---------------------------------------------------------------------- the sweeps
def sweep_table(table: st.StandTable, record: dict[str, Any]) -> tuple[st.Preprocessed, Elbow]:
    """The elbow of a table of stands, made as the k elbow step makes a run's: the table
    preprocessed over every row by the record's rule, threshold and angle pairs, then the fit's
    starts on its rows in the fit, for k 2 to 12 (fmu.stages.k_elbow.fit_space_sweep), and the knee
    of the sums of squares (fmu.stages.k_elbow.knee)."""
    pre = st.preprocess(table, rule=str(record["log_rule"]),
                        threshold=float(record["skewness_threshold"]),
                        decomposed=list(record["cyclic_decomposition_log"]))
    sweep = fit_space_sweep(pre.values[table.in_fit], pre.values, k_min=K_MIN, k_max=K_MAX,
                            seed=SEED, n_starts=N_STARTS)
    elbow = Elbow(ks=list(sweep["ks"]), wcss=list(sweep["inertia"]), ari_median=list(sweep["ari_median"]),
                  ari_min=list(sweep["ari_min"]), knee=knee(list(sweep["ks"]), list(sweep["inertia"])))
    return pre, elbow


def check_run(run: RunRecords) -> None:
    """The run's elbow made again from its table of stands and preprocessing record, by the code of
    the pooled elbows: it must be the run's own, and the preprocessing its record, or the script
    stops."""
    pre, elbow = sweep_table(run.table, run.record)
    differ = sorted(key for key, value in pre.record.items() if run.record.get(key) != value)
    if differ:
        raise SystemExit(f"{run.run}: the preprocessing made again from its table of stands differs "
                         f"from its record in {differ}")
    if elbow.numbers() != run.elbow.numbers():
        names = ("k", "wcss", "ari_median", "ari_min", "the knee")
        what = [n for n, a, b in zip(names, elbow.numbers(), run.elbow.numbers(), strict=True) if a != b]
        raise SystemExit(f"{run.run}: its elbow made again from its table of stands differs from its "
                         f"own in {', '.join(what)} (made again: {elbow.numbers()}; its own: "
                         f"{run.elbow.numbers()})")


@dataclass
class Pool:
    """The four districts of an arm and stand size pooled: their rows and their elbow."""

    size: str
    arm: str
    runs: dict[str, RunRecords]  # district -> run, in DISTRICTS order
    table: st.StandTable
    keys: list[tuple[str, int]]  # (district, stand label) of each pooled row
    pre: st.Preprocessed
    elbow: Elbow

    @property
    def n_table_rows(self) -> int:
        return len(self.table.labels)

    @property
    def n_rows_fitted(self) -> int:
        return int(self.table.in_fit.sum())


def pool_table(size: str, arm: str, runs: dict[str, RunRecords]) -> tuple[st.StandTable, list[tuple[str, int]]]:
    """The four districts' tables of stands put together (module docstring), after checking that
    they can be: the same label column and candidate bands, and the same rule in their records."""
    name = f"the pooled {ARM_WORD[arm]} {SIZE_TEXT[size]} table"
    ordered = [runs[d] for d in DISTRICTS]
    first = ordered[0]
    for other in ordered[1:]:
        if other.table.bands != first.table.bands:
            only_other = [b for b in other.table.bands if b not in first.table.bands]
            only_first = [b for b in first.table.bands if b not in other.table.bands]
            detail = (f"bands only in {other.run}: {only_other}; only in {first.run}: {only_first}"
                      if only_other or only_first else "the same bands, in another order")
            raise SystemExit(f"{name}: {first.run} and {other.run} have different candidate bands "
                             f"({detail}); the pool needs the same bands in the same order")
        if other.label_name != first.label_name:
            raise SystemExit(f"{name}: {first.run} labels its rows {first.label_name}, "
                             f"{other.run} {other.label_name}")
        for key in POOL_KEYS:
            if other.record[key] != first.record[key]:
                raise SystemExit(f"{name}: the runs' preprocessing differs in {key}: {first.run} "
                                 f"{first.record[key]!r}, {other.run} {other.record[key]!r}")
    keys = [(d, int(lbl)) for d in DISTRICTS for lbl in runs[d].table.labels]
    table = st.StandTable(labels=np.arange(len(keys), dtype=np.int64), bands=list(first.table.bands),
                          values=np.vstack([r.table.values for r in ordered]),
                          in_fit=np.concatenate([r.table.in_fit for r in ordered]))
    return table, keys


def make_pool(size: str, arm: str, runs: dict[str, RunRecords]) -> Pool:
    table, keys = pool_table(size, arm, runs)
    pre, elbow = sweep_table(table, runs[DISTRICTS[0]].record)
    return Pool(size=size, arm=arm, runs={d: runs[d] for d in DISTRICTS}, table=table, keys=keys,
                pre=pre, elbow=elbow)


# ---------------------------------------------------------------------- the series of each area
@dataclass
class Series:
    """One arm of one area: its elbow, where it came from and how many rows it fitted."""

    area: Area
    arm: str
    elbow: Elbow
    n_rows_fitted: int
    n_table_rows: int
    source: str  # the run's config name, or "pooled"


def area_series(runs: dict[str, RunRecords], pools: dict[tuple[str, str], Pool | None]) -> dict[str, dict[str, Series]]:
    """For each area, its arms that have an elbow, in ARMS order."""
    out: dict[str, dict[str, Series]] = {}
    for area in AREAS:
        arms: dict[str, Series] = {}
        for arm in ARMS:
            if area.pooled:
                pool = pools.get((area.stand_size, arm))
                if pool is not None:
                    arms[arm] = Series(area, arm, pool.elbow, pool.n_rows_fitted, pool.n_table_rows,
                                       "pooled")
            elif arm in area.runs and area.runs[arm] in runs:
                r = runs[area.runs[arm]]
                arms[arm] = Series(area, arm, r.elbow, r.n_rows_fitted, r.n_table_rows, r.run)
        out[area.key] = arms
    return out


def csv_text(series: dict[str, dict[str, Series]]) -> str:
    """<stem>.csv: one row per area, arm and k (results only)."""
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(CSV_COLUMNS)
    for area in AREAS:
        for arm, s in series[area.key].items():
            e = s.elbow
            for i, k in enumerate(e.ks):
                w.writerow([area.key, arm, area.stand_size, k, repr(e.wcss[i]), repr(e.ari_median[i]),
                            repr(e.ari_min[i]), int(k == e.knee), s.n_rows_fitted])
    return out.getvalue()


# ---------------------------------------------------------------------- the figures
# Two knees at one k whose heights (on the scale where k = 2 is 1) differ by less than this share
# one label.
SAME_HEIGHT = 0.05
# The panels' place in the figure, fixed (a constrained layout takes twice as long to draw).
PANELS = {"height_ratios": [1.15, 1.0], "hspace": 0.3, "left": 0.085, "right": 0.985, "top": 0.885,
          "bottom": 0.085}


def knee_labels(points: dict[str, tuple[int, float]]) -> list[tuple[str, tuple[int, float], tuple[int, int], str, str]]:
    """The knees' labels: (text, the knee, offset in points, ha, va). With two arms each label names
    its arm, and two knees at one k and nearly one height share one label. The curves fall from
    left to right, so the room is above them to the right of a knee and below them to its left: a
    label goes above and to the right of its knee (to the left near the right edge), and the lower
    of two knees one k or less apart has its label below and to the left (to the right near the
    left edge)."""
    items: list[tuple[str, tuple[int, float]]] = list(points.items())
    if len(items) == 2:
        (_, (k1, y1)), (_, (k2, y2)) = items
        if k1 == k2 and abs(y1 - y2) < SAME_HEIGHT:
            items = [("both", (k1, max(y1, y2)))]
    out = []
    for arm, (k, y) in items:
        if any(abs(ok - k) <= 1 and y < oy for a, (ok, oy) in items if a != arm):
            dx, ha = (10, "left") if k <= K_MIN + 2 else (-10, "right")
            dy, va = -14, "top"
        else:
            dx, ha = (-10, "right") if k >= K_MAX - 1 else (10, "left")
            dy, va = 12, "bottom"
        if arm == "both":
            text = f"both knees, k = {k}"
        elif len(points) == 2:
            text = f"{ARM_TEXT[arm]} knee, k = {k}"
        else:
            text = f"knee, k = {k}"
        out.append((text, (k, y), (dx, dy), ha, va))
    return out


def draw_figure(area: Area, arms: dict[str, Series], path: Path) -> None:
    """One area's figure (module docstring), with the Agg backend; no date, no software name."""
    import matplotlib as mpl
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    from matplotlib.lines import Line2D

    with mpl.rc_context({"font.size": 11, "axes.titlesize": 11, "axes.labelsize": 11,
                         "xtick.labelsize": 10, "ytick.labelsize": 10, "legend.fontsize": 10,
                         "axes.edgecolor": AXIS, "axes.labelcolor": INK_2, "xtick.color": INK_2,
                         "ytick.color": INK_2, "text.color": INK, "axes.titlecolor": INK_2}):
        fig = Figure(figsize=FIG_SIZE_IN, dpi=FIG_DPI, facecolor="white")
        FigureCanvasAgg(fig)
        top, bottom = fig.subplots(2, 1, sharex=True, gridspec_kw=PANELS)
        fig.text(0.015, 0.975, area.title, ha="left", va="top", fontsize=13.5, fontweight="bold", color=INK)
        knees: dict[str, tuple[int, float]] = {}
        low_ari, high_rel = 0.0, 1.0
        for arm, s in arms.items():
            e, colour = s.elbow, COLOUR[arm]
            ks = np.array(e.ks, dtype=float)
            wcss = np.array(e.wcss, dtype=float)
            rel = wcss / wcss[0] if wcss[0] > 0 else wcss
            name = f"{ARM_TEXT[arm]}: knee at k = {e.knee}" if e.knee is not None else f"{ARM_TEXT[arm]}: no knee"
            top.plot(ks, rel, color=colour, lw=1.8, marker="o", ms=6, mfc=colour, mec="white",
                     mew=1.0, zorder=3, label=name, solid_capstyle="round", solid_joinstyle="round")
            if e.knee is not None:
                y = float(rel[e.ks.index(e.knee)])
                knees[arm] = (e.knee, y)
                top.plot([e.knee], [y], ls="none", marker="o", ms=14, mfc="none", mec=colour, mew=1.8,
                         zorder=4)
            bottom.plot(ks, e.ari_median, color=colour, lw=1.8, marker="o", ms=6, mfc=colour,
                        mec="white", mew=1.0, zorder=3, clip_on=False, solid_capstyle="round")
            bottom.plot(ks, e.ari_min, color=colour, lw=1.1, ls=(0, (4, 2.5)), zorder=2, clip_on=False)
            low_ari = min(low_ari, *e.ari_min, *e.ari_median)
            high_rel = max(high_rel, float(rel.max()))
        for text, xy, offset, ha, va in knee_labels(knees):
            top.annotate(text, xy=xy, xytext=offset, textcoords="offset points", ha=ha, va=va,
                         fontsize=10, color=INK, zorder=5,
                         bbox={"boxstyle": "round,pad=0.15", "fc": "white", "ec": "none", "alpha": 0.85})
        whose = "each arm relative to its own k = 2" if len(arms) > 1 else "relative to its k = 2"
        top.set_title(f"Within-cluster sum of squares of the best of {N_STARTS} starts, {whose}", loc="left")
        top.set_ylabel("Sum of squares (k = 2 is 1)")
        top.set_ylim(0.0, high_rel * 1.04)
        top.legend(loc="upper right", frameon=False)
        bottom.set_title(f"How much the {N_STARTS} starts agree: adjusted Rand index of the {N_PAIRS} "
                         "pairs of starts", loc="left")
        bottom.set_ylabel("Adjusted Rand index")
        bottom.set_xlabel("k, the number of stand types")
        bottom.set_ylim(low_ari - 0.05 if low_ari < 0 else 0.0, 1.0)
        bottom.legend(handles=[Line2D([], [], color=INK_2, lw=1.8, marker="o", ms=6, mec="white",
                                      label=f"median of the {N_PAIRS} pairs"),
                               Line2D([], [], color=INK_2, lw=1.1, ls=(0, (4, 2.5)), label="lowest pair")],
                      loc="best", frameon=False)
        for ax in (top, bottom):
            ax.grid(True, color=GRID, lw=0.8)
            ax.set_axisbelow(True)
            for side in ("top", "right"):
                ax.spines[side].set_visible(False)
            ax.tick_params(length=0)
        bottom.set_xlim(K_MIN - 0.5, K_MAX + 0.5)
        bottom.set_xticks(range(K_MIN, K_MAX + 1))
        fig.savefig(path, format="png", dpi=FIG_DPI, facecolor="white", metadata={"Software": None})


# ---------------------------------------------------------------------- the report
def _num(v: float) -> str:
    return f"{v:,.2f}"


def _ari(v: float) -> str:
    return "1" if v == 1.0 else f"{v:.4f}"


def _knee_cell(area: Area, arm: str, arms: dict[str, Series]) -> str:
    if arm in arms:
        k = arms[arm].elbow.knee
        return str(k) if k is not None else "none (the sums of squares do not change)"
    if not area.pooled and arm not in area.runs:
        return "no run (one arm)"
    return "not computed" if area.pooled else "no record"


def _fitted_cell(arms: dict[str, Series]) -> str:
    return "; ".join(f"{ARM_TEXT[a]} {s.n_rows_fitted:,} of {s.n_table_rows:,}"
                     for a, s in arms.items()) or "none"


def _bands(names: Sequence[str]) -> str:
    return ", ".join(f"`{b}`" for b in names) if names else "none"


def report_text(*, stem: str, records: Path, series: dict[str, dict[str, Series]],
                pools: dict[tuple[str, str], Pool | None], runs: dict[str, RunRecords],
                missing: list[str], run_check: bool) -> str:
    """<stem>_report.md (results only: no date, time or commit)."""
    n_runs = sum(len(a.runs) for a in AREAS)
    lines = [
        "# The elbow report of R3's first half (round 14, Task 6)",
        "",
        "For Jaskaran to choose k from. For R3, k for each area is his choice, from this report alone, "
        "before any R3 field score exists (`odisha_script/PHASE_KEPTLAND_PREDECLARED.md`, the change of "
        "26 Oct 2026; register entry `field-r3-k-chosen-by-jaskaran-from-the-elbow-report`). The report "
        "reads no plot and computes no field score, and it recommends no k.",
        "",
        f"Written by `odisha_script/r14_elbow_report.py` from the records of R3's first half, the runs "
        f"through the k elbow (`{shown(records)}`). The numbers behind the figures are in `{stem}.csv`, "
        f"one figure per area is in `{stem}/`, and the record of the run that wrote them (the command, "
        f"when it ran, the git commit, and every input with its SHA-256) is `{stem}_run.json`. The areas "
        "are each Odisha district at 3 ha and at 10 ha, Sanjay Van (10 ha stands) and the 10 km tile in "
        "Angul (3 ha stands), each with its two arms, hand-crafted and AlphaEarth, side by side, and the "
        "four districts pooled, for each arm and stand size. The tile has one arm, hand-crafted: R3 has "
        "no AlphaEarth run of the tile.",
        "",
    ]
    if run_check:
        lines += [f"Each run's elbow is the run's own (its `_k_elbow.csv`). Each was also made again here "
                  "from the run's table of stands and preprocessing record, by the code that makes the "
                  f"pooled elbows, and is the run's own in every number ({len(runs)} of {len(runs)} "
                  "runs with a record), its preprocessing its record.", ""]
    else:
        lines += ["Each run's elbow is the run's own (its `_k_elbow.csv`). It was not made again here "
                  "(`--no-run-check`).", ""]
    if missing:
        lines += [f"**No record of {len(missing)} of the {n_runs} runs:** "
                  + ", ".join(f"`{m}`" for m in missing)
                  + ". Their areas show the other arm only, and a pool that needs one is not computed.", ""]
    lines += [
        "## How the numbers are made",
        "",
        "Each run's elbow is the k elbow step's (`k_elbow.in_fit_space` on; `fmu.stages.k_elbow`). It "
        "takes the run's table of stands (one row per stand, its mean in every candidate band) and "
        "preprocesses it over every stand by the declared rule (`clustering.log_rule` right_skew: a band "
        "whose IQR is 0 is dropped; only a band skewed to the right, skew above 1.0, is logged, as "
        "log1p((x - min) / IQR); the sine and cosine of an angle are never logged, and each such pair is "
        "scaled by one shared spread; every band is centred by its median and divided by its IQR, exact "
        "quartiles). It then fits k-means on the fit's own rows in that space (the stands under 1 ha "
        f"left out), for each k from {K_MIN} to {K_MAX}: {N_STARTS} k-means++ starts from seed {SEED}, "
        "each refined by Lloyd's algorithm (scikit-learn, one thread), the start with the lowest "
        "within-cluster sum of squares kept. That sum, rounded to 6 decimals, is the curve, and the knee "
        "is the k farthest from the chord between the curve's first and last points "
        "(`fmu.stages.k_elbow.knee`). At each k the adjusted Rand index of every pair of the "
        f"{N_STARTS} starts ({N_PAIRS} pairs) says how much the starts agree with each other: a "
        "diagnostic of the clustering, not a field score. Its median and lowest are given, rounded to 6 "
        "decimals. The pooled elbow of an arm and stand size puts the four districts' tables of stands "
        "together, each row keyed by its district and stand label (labels repeat across districts), in "
        "the order Angul, Dhenkanal, Kendujhar, Koraput and within each by stand label, each row keeping "
        "whether it is in its run's fit. It preprocesses them together by the runs' own rule, threshold "
        "and angle pairs, and sweeps k on the rows in the fit with the same code and the same starts "
        "(`fmu.stages.k_elbow.fit_space_sweep`). The two arms' sums of squares are in different spaces "
        "(different bands), so the figures show each relative to its own value at k = 2, and the tables "
        "give them as they are.",
        "",
        "## The knees",
        "",
        "| Area | Hand-crafted knee | AlphaEarth knee | Stands in the fit, of those in the table |",
        "|---|---:|---:|---|",
    ]
    for area in AREAS:
        arms = series[area.key]
        lines.append(f"| {area.title} | {_knee_cell(area, 'handcrafted', arms)} | "
                     f"{_knee_cell(area, 'alphaearth', arms)} | {_fitted_cell(arms)} |")
    lines.append("")
    for area in AREAS:
        lines += _area_section(area, series[area.key], pools, stem, missing)
    return "\n".join(lines).rstrip("\n") + "\n"


def _area_section(area: Area, arms: dict[str, Series], pools: dict[tuple[str, str], Pool | None],
                  stem: str, missing: list[str]) -> list[str]:
    lines = [f"## {area.title}", ""]
    if area.pooled:
        lines += _pool_lines(area, pools, missing)
    else:
        said = []
        for arm, run in area.runs.items():
            if arm in arms:
                s = arms[arm]
                said.append(f"{ARM_TEXT[arm]}: `{run}`, {s.n_rows_fitted:,} stands in the fit of "
                            f"{s.n_table_rows:,} in its table of stands.")
            else:
                said.append(f"{ARM_TEXT[arm]}: `{run}`, no record.")
        if len(area.runs) == 1:
            said.append("The tile has one arm: R3 has no AlphaEarth run of the tile.")
        lines += [" ".join(said), ""]
    if not arms:
        return [*lines, "No figure and no table: no arm of this area has an elbow.", ""]
    shown_arms = " and ".join(ARM_WORD[a] for a in arms)
    lines += [f"![{area.title}: the k elbow, {shown_arms}]({stem}/{area.key}.png)", "", _caption(arms), ""]
    head = ["k"]
    for arm in arms:
        head += [f"{ARM_TEXT[arm]}: sum of squares", "median ARI", "lowest ARI"]
    lines += ["| " + " | ".join(head) + " |", "|" + "---:|" * len(head)]
    ks = sorted({k for s in arms.values() for k in s.elbow.ks})
    for k in ks:
        cells = [str(k)]
        for s in arms.values():
            e = s.elbow
            if k in e.ks:
                i = e.ks.index(k)
                cells += [_num(e.wcss[i]) + (" (knee)" if k == e.knee else ""), _ari(e.ari_median[i]),
                          _ari(e.ari_min[i])]
            else:
                cells += ["", "", ""]
        lines.append("| " + " | ".join(cells) + " |")
    return [*lines, ""]


def _caption(arms: dict[str, Series]) -> str:
    """A figure's caption: how its sums of squares are scaled, and its colours."""
    bottom = (f"Bottom: the adjusted Rand index of the {N_PAIRS} pairs of the {N_STARTS} starts, the "
              "median (solid, with points) and the lowest (dashed), on a scale from 0 to 1.")
    if len(arms) > 1:
        return ("*Top: each arm's within-cluster sum of squares (the best of the starts) divided by its "
                "own value at k = 2, as the two arms' sums are in different spaces, on a scale from 0; "
                f"each arm's knee is ringed and labelled. {bottom} Blue: hand-crafted; vermillion: "
                "AlphaEarth.*")
    (arm,) = arms
    colour = {"handcrafted": "blue", "alphaearth": "vermillion"}[arm]
    return ("*Top: the within-cluster sum of squares (the best of the starts) divided by its value at "
            f"k = 2, on a scale from 0; the knee is ringed and labelled. {bottom} One arm, "
            f"{ARM_WORD[arm]} ({colour}).*")


def _pool_lines(area: Area, pools: dict[tuple[str, str], Pool | None], missing: list[str]) -> list[str]:
    size = area.stand_size
    lines = ["The four districts' tables of stands put together, each row keyed by its district and stand "
             "label: the stands of each table, and in brackets those in the fit.", ""]
    head = ["District", *(f"{ARM_TEXT[arm]}: stands (in the fit)" for arm in ARMS)]
    lines += ["| " + " | ".join(head) + " |", "|---|" + "---:|" * len(ARMS)]
    for d in DISTRICTS:
        cells = [d.capitalize()]
        for arm in ARMS:
            pool = pools.get((size, arm))
            if pool is None:
                cells.append("no record" if district_run(d, size, arm) in missing else "")
            else:
                r = pool.runs[d]
                cells.append(f"{r.n_table_rows:,} ({r.n_rows_fitted:,})")
        lines.append("| " + " | ".join(cells) + " |")
    totals = ["Pooled"]
    for arm in ARMS:
        pool = pools.get((size, arm))
        totals.append(f"{pool.n_table_rows:,} ({pool.n_rows_fitted:,})" if pool is not None else "not computed")
    lines += ["| " + " | ".join(totals) + " |", ""]
    for arm in ARMS:
        pool = pools.get((size, arm))
        if pool is None:
            need = [district_run(d, size, arm) for d in DISTRICTS if district_run(d, size, arm) in missing]
            lines += [f"{ARM_TEXT[arm]}: not computed, no record of {_bands(need)}.", ""]
            continue
        rec = pool.pre.record
        first = pool.runs[DISTRICTS[0]].record
        logged = list(rec["log_transformed_bands"])
        lines += [f"{ARM_TEXT[arm]}: preprocessed together by the runs' rule (`{first['log_rule']}`, skew "
                  f"threshold {first['skewness_threshold']}; the angles taken as sine and cosine: "
                  f"{_bands(list(first['cyclic_decomposition_log']))}): {len(rec['active_bands'])} of "
                  f"{len(pool.table.bands)} candidate bands kept, {len(logged)} logged"
                  + (f" ({_bands(logged)})" if logged else "")
                  + f", dropped as constant: {_bands(rec['dropped_constant_bands'])}.", ""]
    return lines


# ---------------------------------------------------------------------- the run record
def git_block(now: bool = False) -> dict[str, Any]:
    """This checkout's git state as a run record holds it: as the process found it first, or read
    again now (`now`). main() asks first, before it reads or writes anything (review C32)."""
    from fmu.utils.provenance import git_state, git_state_now

    state = git_state_now(HERE) if now else git_state(HERE)
    return {k: v for k, v in state.items() if k != "root"}


def packages() -> dict[str, str | None]:
    """The versions of the packages the numbers and figures depend on."""
    from importlib import metadata

    out: dict[str, str | None] = {}
    for name in ("numpy", "scikit-learn", "matplotlib"):
        try:
            out[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            out[name] = None
    return out


def run_record(*, argv: list[str], started: dict[str, Any], result_files: list[str],
               reads: list[Read], run_check: bool, missing: list[str]) -> dict[str, Any]:
    from fmu.utils.provenance import environment_state

    return {
        "result_files": result_files,
        "command_line": "python " + " ".join(shlex.quote(a) for a in
                                             ["odisha_script/r14_elbow_report.py", *argv]),
        "date": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "git": started,
        "git_at_end": git_block(now=True),
        "environment": environment_state(),
        "packages": packages(),
        "run_check": run_check,
        "missing_runs": missing,
        "inputs": [{"run": r.run, "file": r.file, "path": shown(r.path), "off_git": r.off_git,
                    "bytes": r.n_bytes, "sha256": r.sha256} for r in reads],
    }


# ---------------------------------------------------------------------- main
def outputs(out_dir: Path, stem: str) -> tuple[Path, Path, Path, Path]:
    """<stem>.csv, <stem>_report.md, <stem>_run.json and the figures' folder <stem>/."""
    return (out_dir / f"{stem}.csv", out_dir / f"{stem}_report.md", out_dir / f"{stem}_run.json",
            out_dir / stem)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--records", type=Path, default=RECORDS,
                    help="the first half's records (scripts/copy_run_results.py --through k_elbow)")
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    ap.add_argument("--stem", default=STEM, help="the result files' names begin with this")
    ap.add_argument("--overwrite", action="store_true", help="write over the result files of an earlier run")
    ap.add_argument("--no-run-check", action="store_true",
                    help="do not make each run's elbow again from its table of stands")
    ap.add_argument("--allow-missing", action="store_true",
                    help="write the report without the runs that have no record, and say which")
    args = ap.parse_args(argv)
    argv_given = list(sys.argv[1:] if argv is None else argv)
    started = git_block()  # before anything is read or written (review C32)

    csv_path, report_path, record_path, fig_dir = outputs(args.out_dir, args.stem)
    there = [p for p in (csv_path, report_path, record_path) if p.exists()]
    if fig_dir.exists() and any(fig_dir.iterdir()):
        there.append(fig_dir)
    if there and not args.overwrite:
        raise SystemExit("refusing to write over " + ", ".join(shown(p) for p in there)
                         + " (--overwrite replaces them)")
    if not args.records.is_dir():
        raise SystemExit(f"{args.records}: no such folder of records")

    reads: list[Read] = []
    runs: dict[str, RunRecords] = {}
    missing: list[str] = []
    for area in AREAS:
        for run in area.runs.values():
            loaded = load_run(args.records, run, reads)
            if loaded is None:
                missing.append(run)
            else:
                runs[run] = loaded
    if missing and not args.allow_missing:
        raise SystemExit(f"no records of {len(missing)} run(s) in {args.records}: {', '.join(missing)} "
                         "(--allow-missing writes the report without them)")
    if not args.no_run_check:
        for run, records in runs.items():
            print(f"  {run}: its elbow made again from its table of stands", flush=True)
            check_run(records)
    pools: dict[tuple[str, str], Pool | None] = {}
    for size in SIZES:
        for arm in ARMS:
            names = {d: district_run(d, size, arm) for d in DISTRICTS}
            if all(n in runs for n in names.values()):
                print(f"  the pooled elbow, {ARM_WORD[arm]}, {SIZE_TEXT[size]}", flush=True)
                pools[(size, arm)] = make_pool(size, arm, {d: runs[n] for d, n in names.items()})
            else:
                pools[(size, arm)] = None
    series = area_series(runs, pools)
    table = csv_text(series)
    report = report_text(stem=args.stem, records=args.records, series=series, pools=pools, runs=runs,
                         missing=missing, run_check=not args.no_run_check)
    for name, text in ((csv_path.name, table), (report_path.name, report)):
        if STAMP.search(text):
            raise SystemExit(f"{name}: a value holding a date and time; results only")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    fig_dir.mkdir(parents=True, exist_ok=True)
    figures = []
    for area in AREAS:
        if series[area.key]:
            draw_figure(area, series[area.key], fig_dir / f"{area.key}.png")
            figures.append(f"{args.stem}/{area.key}.png")
        else:  # no arm has an elbow: an earlier run's figure of the area (--overwrite) is not left
            (fig_dir / f"{area.key}.png").unlink(missing_ok=True)
    csv_path.write_text(table, encoding="utf-8")
    report_path.write_text(report, encoding="utf-8")
    record = run_record(argv=argv_given, started=started,
                        result_files=[csv_path.name, report_path.name, *figures], reads=reads,
                        run_check=not args.no_run_check, missing=missing)
    record_path.write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")

    print(f"wrote {shown(csv_path)}, {shown(report_path)}, {len(figures)} figures in {shown(fig_dir)}, "
          f"and {shown(record_path)}")
    print("the knees:")
    for area in AREAS:
        arms = series[area.key]
        print(f"  {area.title}: " + ", ".join(f"{ARM_WORD[a]} {_knee_cell(area, a, arms)}" for a in ARMS
                                              if a in arms or area.pooled or a in area.runs))
    return 0


if __name__ == "__main__":
    sys.exit(main())

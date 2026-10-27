"""The elbow report of R3's first half (round 14, Task 6), for Jaskaran to choose k from.

    python odisha_script/r14_elbow_report.py [--records docs/reproducibility/r14_runs/first_half]
        [--out-dir odisha_script/keptland_scores] [--stem r14_elbow] [--overwrite]
        [--no-run-check] [--allow-missing]

Offline: no Earth Engine and no network. It reads no plot and computes no field score, and it
recommends no k: for R3, k for each area is Jaskaran's choice, from this report alone, before any
R3 field score exists (odisha_script/PHASE_KEPTLAND_PREDECLARED.md, the change of 26 Oct 2026;
register entry field-r3-k-chosen-by-jaskaran-from-the-elbow-report).

THE AREAS AND ARMS, by config name (the nineteen R3 configs, configs/*_r14.yaml; not the six
_check copies, a to f, which are not R3 results): each Odisha district (angul, dhenkanal, kendujhar,
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
Every run's record, the pools' and the others', must have one log_rule, right_skew (the rule the
report's paragraph on how the numbers are made describes), and one skewness_threshold, which the
paragraph gives, or the script stops.
The pooled table is preprocessed by fmu.utils.stand_table.preprocess with that rule, threshold and
angle pairs, over every row, and k is swept on its rows in the fit with the fit's own starts,
fmu.stages.k_elbow.fit_space_sweep(rows, every_row, k_min=2, k_max=12, seed=42, n_starts=25), the
knee by fmu.stages.k_elbow.knee. The pipeline never fits the pooled rows; the report gives their
elbow because the declaration asks for it.

THE SAME ROWS IN REVERSE ORDER. k-means++ depends on the order of the rows, so each pooled elbow is
also made with the same rows in reverse order and given beside it, as round 13's A7 script gave its
elbows (odisha_script/odisha_phase3_2_stand_k_elbow.py, elbow_of(x[::-1])): the pooled rows after
the same preprocessing (made once), reversed, the rows in the fit and every row alike, then the same
fit_space_sweep call and the same knee. Jaskaran's answer (b) to question 9 of the round 14 record,
27 Oct 2026, before any R3 result existed (odisha_script/PHASE_KEPTLAND_PREDECLARED.md, the note of
27 Oct 2026 in the change of 26 Oct 2026). Each run's own elbow has one order, the run's.

WRITES, in --out-dir, and refuses to write over any of these unless --overwrite (a refusal writes
nothing; so does a stop). They are written into a folder of their own beside them, the work folder
(named by tempfile.mkdtemp: .<stem>. and 8 characters from a to z, 0 to 9 and "_"; removed after),
and put in place once all are written, one file at a time: the figures, the csv and the report,
then, once the git state is read again, the run record. So a failure that is not a stop (a full
disk, Ctrl-C) while they are made leaves none of them. One in the last second, while they are put
in place or the git state is read, can leave part of the results in place (some or all of the
figures; the figures and the csv; or all the results without their run record) and, with
--overwrite, the rest of an earlier run's outputs beside them, its run record among them. A kill
that no finally block sees (SIGKILL) leaves the work folder, which the next run refuses to write
over, as it does the outputs, and --overwrite removes. Only a work folder this script makes is
taken for one (a folder, not a link, named as above, holding nothing but the names the script
writes there); anything else of a like name in --out-dir is left alone, neither refused nor
removed. The outputs:
  <stem>.csv          one row per area, arm, row order and k: area, arm, stand_size, row_order, k,
                      wcss, ari_median, ari_min, is_knee, n_rows_fitted (the pools as the areas
                      pooled_3ha and pooled_10ha); row_order is "stated" (a run's rows in its
                      table's order, a pool's in the order above) or "reversed" (a pool's same
                      rows in reverse order), as ROW_ORDERS says
  <stem>/<area>.png   one figure per area: each arm's within-cluster sum of squares divided by its
                      own value at k = 2 (the arms' sums are in different spaces) with its knee,
                      and the starts' median and lowest pairwise adjusted Rand index; a pool's
                      figure has two columns on the same axes, the rows in the stated order on
                      the left and the same rows in reverse order on the right
  <stem>_report.md    the report; for a pool, the knees and the table of k in both orders
  <stem>_run.json     the run's record: the command, when it ran, the git block of this checkout
                      (fmu.utils.provenance.git_state, read at the start of main(), and again once
                      the csv, the report and the figures are in place), the environment, the
                      csv's row orders (ROW_ORDERS), and every input read, with where it was, its
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
import os
import re
import shlex
import shutil
import sys
import tempfile
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
CSV_COLUMNS = ["area", "arm", "stand_size", "row_order", "k", "wcss", "ari_median", "ari_min",
               "is_knee", "n_rows_fitted"]
# The csv's row orders, as the run record gives them: each run's elbow in one, a pool's in both
# (Jaskaran's answer (b) to question 9 of the round 14 record, 27 Oct 2026).
ROW_ORDERS = {
    "stated": "a run's rows in its table's order (by stand label); a pool's, the districts in the "
              "order angul, dhenkanal, kendujhar, koraput, each in its table's order",
    "reversed": "a pool's same rows in reverse order, with the same preprocessing and the same sweep",
}
LABEL_COLUMNS = ("stand_lbl", "snic_label")
RECORD_KEYS = ("log_rule", "skewness_threshold", "cyclic_decomposition_log", "candidate_bands",
               "n_table_rows", "n_rows_fitted")
POOL_KEYS = ("log_rule", "skewness_threshold", "cyclic_decomposition_log")
# The rule the report's paragraph on how the numbers are made describes (one_rule).
RULE_DESCRIBED = "right_skew"
# A value holding a date and time, as scripts/copy_run_results.py looks for one: the date and the
# time joined by "T" or by a space, or a run folder's <date>_<time>.
STAMP = re.compile(r"20\d\d-\d\d-\d\d[T ]\d\d:|20\d{6}_\d{6}")

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


def one_rule(runs: dict[str, RunRecords]) -> tuple[str, float]:
    """The log rule and skewness threshold of every run's preprocessing record, which the report's
    paragraph on how the numbers are made gives once: the script stops if the runs have two, or a
    rule the paragraph does not describe. With no run, the R3 configs' own, right_skew above 1.0."""
    found: dict[tuple[str, float], list[str]] = {}
    for r in runs.values():
        found.setdefault((str(r.record["log_rule"]), float(r.record["skewness_threshold"])), []).append(r.run)
    if len(found) > 1:
        raise SystemExit("the runs' preprocessing differs in its rule or threshold, which the report "
                         "gives once: " + "; ".join(f"{rule} above {t!r} in {', '.join(names)}"
                                                    for (rule, t), names in sorted(found.items())))
    ((rule, threshold),) = found or {(RULE_DESCRIBED, 1.0): []}
    if rule != RULE_DESCRIBED:
        raise SystemExit(f"the runs' preprocessing rule is {rule}; the report's paragraph on how the "
                         f"numbers are made describes {RULE_DESCRIBED} only")
    return rule, threshold


# ---------------------------------------------------------------------- the sweeps
def elbow_of(values: np.ndarray, in_fit: np.ndarray) -> Elbow:
    """The elbow of preprocessed rows: the fit's starts on the rows in the fit, for k 2 to 12
    (fmu.stages.k_elbow.fit_space_sweep, with every row), and the knee of the sums of squares
    (fmu.stages.k_elbow.knee)."""
    sweep = fit_space_sweep(values[in_fit], values, k_min=K_MIN, k_max=K_MAX, seed=SEED,
                            n_starts=N_STARTS)
    return Elbow(ks=list(sweep["ks"]), wcss=list(sweep["inertia"]), ari_median=list(sweep["ari_median"]),
                 ari_min=list(sweep["ari_min"]), knee=knee(list(sweep["ks"]), list(sweep["inertia"])))


def sweep_table(table: st.StandTable, record: dict[str, Any]) -> tuple[st.Preprocessed, Elbow]:
    """The elbow of a table of stands, made as the k elbow step makes a run's: the table
    preprocessed over every row by the record's rule, threshold and angle pairs, then elbow_of its
    rows."""
    pre = st.preprocess(table, rule=str(record["log_rule"]),
                        threshold=float(record["skewness_threshold"]),
                        decomposed=list(record["cyclic_decomposition_log"]))
    return pre, elbow_of(pre.values, table.in_fit)


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
    """The four districts of an arm and stand size pooled: their rows and their elbow, in the
    stated order and with the same rows in reverse order."""

    size: str
    arm: str
    runs: dict[str, RunRecords]  # district -> run, in DISTRICTS order
    table: st.StandTable
    keys: list[tuple[str, int]]  # (district, stand label) of each pooled row
    pre: st.Preprocessed
    elbow: Elbow
    elbow_reversed: Elbow

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
    """The pool's elbow, then the same rows' in reverse order: the preprocessing made once, its rows
    reversed, the same sweep (module docstring)."""
    table, keys = pool_table(size, arm, runs)
    pre, elbow = sweep_table(table, runs[DISTRICTS[0]].record)
    elbow_reversed = elbow_of(pre.values[::-1], table.in_fit[::-1])
    return Pool(size=size, arm=arm, runs={d: runs[d] for d in DISTRICTS}, table=table, keys=keys,
                pre=pre, elbow=elbow, elbow_reversed=elbow_reversed)


# ---------------------------------------------------------------------- the series of each area
@dataclass
class Series:
    """One arm of one area: its elbow, where it came from and how many rows it fitted; for a pool,
    also its elbow with the same rows in reverse order."""

    area: Area
    arm: str
    elbow: Elbow
    n_rows_fitted: int
    n_table_rows: int
    source: str  # the run's config name, or "pooled"
    elbow_reversed: Elbow | None = None

    def orders(self) -> list[tuple[str, Elbow]]:
        """Its elbow in each row order it was made in (ROW_ORDERS): a pool's two, a run's one."""
        both = [("reversed", self.elbow_reversed)] if self.elbow_reversed is not None else []
        return [("stated", self.elbow), *both]


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
                                       "pooled", elbow_reversed=pool.elbow_reversed)
            elif arm in area.runs and area.runs[arm] in runs:
                r = runs[area.runs[arm]]
                arms[arm] = Series(area, arm, r.elbow, r.n_rows_fitted, r.n_table_rows, r.run)
        out[area.key] = arms
    return out


def csv_text(series: dict[str, dict[str, Series]]) -> str:
    """<stem>.csv: one row per area, arm, row order and k (results only)."""
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(CSV_COLUMNS)
    for area in AREAS:
        for arm, s in series[area.key].items():
            for order, e in s.orders():
                for i, k in enumerate(e.ks):
                    w.writerow([area.key, arm, area.stand_size, order, k, repr(e.wcss[i]),
                                repr(e.ari_median[i]), repr(e.ari_min[i]), int(k == e.knee),
                                s.n_rows_fitted])
    return out.getvalue()


# ---------------------------------------------------------------------- the figures
# Two knees at one k whose heights (on the scale where k = 2 is 1) differ by less than this share
# one label.
SAME_HEIGHT = 0.05
# The panels' place in the figure, fixed (a constrained layout takes twice as long to draw). A
# pool's figure has two columns, and room above them for the top row's heading.
PANELS = {"height_ratios": [1.15, 1.0], "hspace": 0.3, "left": 0.085, "right": 0.985, "top": 0.885,
          "bottom": 0.085}
PANELS_TWO = {**PANELS, "wspace": 0.08, "top": 0.835}
COLUMN_TITLES = ("The rows in the stated order", "The same rows in reverse order")


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
    """One area's figure (module docstring), with the Agg backend; no date, no software name. A
    pool's has two columns on the same axes: the rows in the stated order on the left, the same
    rows in reverse order on the right."""
    import matplotlib as mpl
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    from matplotlib.lines import Line2D

    two = any(s.elbow_reversed is not None for s in arms.values())
    whose = "each arm relative to its own k = 2" if len(arms) > 1 else "relative to its k = 2"
    sums_title = f"Within-cluster sum of squares of the best of {N_STARTS} starts, {whose}"
    ari_title = f"How much the {N_STARTS} starts agree: adjusted Rand index of the {N_PAIRS} pairs of starts"
    with mpl.rc_context({"font.size": 11, "axes.titlesize": 11, "axes.labelsize": 11,
                         "xtick.labelsize": 10, "ytick.labelsize": 10, "legend.fontsize": 10,
                         "axes.edgecolor": AXIS, "axes.labelcolor": INK_2, "xtick.color": INK_2,
                         "ytick.color": INK_2, "text.color": INK, "axes.titlecolor": INK_2}):
        fig = Figure(figsize=FIG_SIZE_IN, dpi=FIG_DPI, facecolor="white")
        FigureCanvasAgg(fig)
        fig.text(0.015, 0.975, area.title, ha="left", va="top", fontsize=13.5, fontweight="bold", color=INK)
        if two:
            (tl, tr), (bl, br) = fig.subplots(2, 2, sharex=True, sharey="row", gridspec_kw=PANELS_TWO)
            columns = [(tl, bl, {a: s.elbow for a, s in arms.items()}),
                       (tr, br, {a: s.elbow_reversed for a, s in arms.items() if s.elbow_reversed is not None})]
            # The top row's heading above the columns' titles; the bottom row's, over both panels.
            fig.text(PANELS_TWO["left"], 0.93, sums_title, ha="left", va="top", fontsize=11, color=INK_2)
            for (top, _, _), title in zip(columns, COLUMN_TITLES, strict=True):
                top.set_title(title, loc="left", fontweight="bold", color=INK)
            bl.set_title(ari_title, loc="left")
        else:
            top, bottom = fig.subplots(2, 1, sharex=True, gridspec_kw=PANELS)
            columns = [(top, bottom, {a: s.elbow for a, s in arms.items()})]
            top.set_title(sums_title, loc="left")
            bottom.set_title(ari_title, loc="left")
        # A pool's panels are half as wide: its knees are named in each panel's legend only, as a
        # label on the curve would run into the legend or out of the panel.
        high_rel = max(_draw_column(top, bottom, elbows, label_knees=not two) for top, bottom, elbows in columns)
        for top, bottom, _ in columns:
            top.set_ylim(0.0, high_rel * 1.04)
            bottom.set_ylim(ari_floor(arms), 1.0)
            bottom.set_xlabel("k, the number of stand types")
            for ax in (top, bottom):
                ax.grid(True, color=GRID, lw=0.8)
                ax.set_axisbelow(True)
                for side in ("top", "right"):
                    ax.spines[side].set_visible(False)
                ax.tick_params(length=0)
            bottom.set_xlim(K_MIN - 0.5, K_MAX + 0.5)
            bottom.set_xticks(range(K_MIN, K_MAX + 1))
        top, bottom, _ = columns[0]
        top.set_ylabel("Sum of squares (k = 2 is 1)")
        bottom.set_ylabel("Adjusted Rand index")
        bottom.legend(handles=[Line2D([], [], color=INK_2, lw=1.8, marker="o", ms=6, mec="white",
                                      label=f"median of the {N_PAIRS} pairs"),
                               Line2D([], [], color=INK_2, lw=1.1, ls=(0, (4, 2.5)), label="lowest pair")],
                      loc="best", frameon=False)
        fig.savefig(path, format="png", dpi=FIG_DPI, facecolor="white", metadata={"Software": None})


def _draw_column(top: Any, bottom: Any, elbows: dict[str, Elbow], *, label_knees: bool) -> float:
    """One column of a figure: in `top` each arm's sums of squares divided by its own value at
    k = 2, its knee ringed (and labelled, with `label_knees`) and named in the legend, in `bottom`
    the starts' median and lowest index; each arm in its own colour. Returns the highest relative
    sum drawn."""
    knees: dict[str, tuple[int, float]] = {}
    high_rel = 1.0
    for arm, e in elbows.items():
        colour = COLOUR[arm]
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
        high_rel = max(high_rel, float(rel.max()))
    for text, xy, offset, ha, va in knee_labels(knees) if label_knees else []:
        top.annotate(text, xy=xy, xytext=offset, textcoords="offset points", ha=ha, va=va,
                     fontsize=10, color=INK, zorder=5,
                     bbox={"boxstyle": "round,pad=0.15", "fc": "white", "ec": "none", "alpha": 0.85})
    top.legend(loc="upper right", frameon=False)
    return high_rel


def lowest_ari(arms: dict[str, Series]) -> float:
    """The lowest median or lowest pairwise index of an area's arms, in every row order drawn."""
    return min(min(e.ari_min + e.ari_median) for s in arms.values() for _, e in s.orders())


def ari_floor(arms: dict[str, Series]) -> float:
    """The bottom of a figure's index panel: 0, or 0.05 below the lowest index where one is below
    0 (two starts that agree less than chance would). The figure and its caption both use it."""
    low = lowest_ari(arms)
    return low - 0.05 if low < 0 else 0.0


# ---------------------------------------------------------------------- the report
def _num(v: float) -> str:
    return f"{v:,.2f}"


def _ari(v: float) -> str:
    """An index for the tables and captions: 4 decimals; 1 as 1; 0 without a sign; one between
    -0.00005 and 0.00005 but not 0 with two significant figures, so that it shows its sign."""
    if v == 1.0:
        return "1"
    if v == 0:
        return "0.0000"
    return f"{v:.1e}" if abs(v) < 5e-5 else f"{v:.4f}"


def reversed_title(area: Area) -> str:
    """The title of a pool's knees with the same rows in reverse order, in the table of knees."""
    return f"{area.title}, the same rows in reverse order"


def _knee_text(e: Elbow) -> str:
    return str(e.knee) if e.knee is not None else "none (the sums of squares do not change)"


def _knee_cell(area: Area, arm: str, arms: dict[str, Series], reverse: bool = False) -> str:
    if arm in arms:
        e = arms[arm].elbow_reversed if reverse else arms[arm].elbow
        return _knee_text(e) if e is not None else "not computed"
    if not area.pooled and arm not in area.runs:
        return "no run (one arm)"
    return "not computed" if area.pooled else "no record"


def _knees_sentence(elbows: dict[str, Elbow]) -> str:
    """Each arm's knee in one sentence: "Knees: hand-crafted k = 5, AlphaEarth k = 6."."""
    return "Knees: " + ", ".join(f"{ARM_WORD[a]} k = {e.knee}" if e.knee is not None
                                 else f"{ARM_WORD[a]} {_knee_text(e)}" for a, e in elbows.items()) + "."


def _fitted_cell(arms: dict[str, Series]) -> str:
    return "; ".join(f"{ARM_TEXT[a]} {s.n_rows_fitted:,} of {s.n_table_rows:,}"
                     for a, s in arms.items()) or "none"


def _bands(names: Sequence[str]) -> str:
    return ", ".join(f"`{b}`" for b in names) if names else "none"


def report_text(*, stem: str, records: Path, series: dict[str, dict[str, Series]],
                pools: dict[tuple[str, str], Pool | None], runs: dict[str, RunRecords],
                missing: list[str], run_check: bool, rule: str = RULE_DESCRIBED,
                threshold: float = 1.0) -> str:
    """<stem>_report.md (results only: no date, time or commit); rule and threshold are the
    runs' (one_rule)."""
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
        "four districts pooled, for each arm and stand size, in the stated order and with the same rows "
        "in reverse order. The tile has one arm, hand-crafted: R3 has no AlphaEarth run of the tile.",
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
        f"preprocesses it over every stand by the runs' rule (`clustering.log_rule` {rule}: a band "
        "whose IQR is at most 1e-9 is dropped, and an angle's sine and cosine only together, when "
        f"their shared spread is; only a band skewed to the right, skew above {threshold!r}, is logged, "
        "as log1p((x - min) / IQR), and it is then dropped if its IQR after the log is at most 1e-9; "
        "the sine and cosine of an angle are never logged; each other band is centred by its median "
        "and divided by its IQR (a logged band's after the log), and the sine and cosine of an angle "
        "by their medians and by their shared spread, the root mean square of their two IQRs; exact "
        "quartiles). "
        "It then fits k-means on the fit's own rows in that space (the stands below the "
        "merge's minimum area, 1 ha in every R3 config, left out), for each k from "
        f"{K_MIN} to {K_MAX}: {N_STARTS} k-means++ starts from seed {SEED}, each refined by Lloyd's "
        "algorithm (scikit-learn, one thread), the start with the lowest within-cluster sum of squares "
        "kept. That sum, rounded to 6 decimals (as the csv gives it; the tables below, to 2), is the "
        "curve, and the knee is the k farthest from the chord between the curve's first and last points "
        "(`fmu.stages.k_elbow.knee`). At each k the adjusted Rand index of every pair of the "
        f"{N_STARTS} starts ({N_PAIRS} pairs) says how much the starts agree with each other: a "
        "diagnostic of the clustering, not a field score. Its median and lowest are given, rounded to 6 "
        "decimals in the csv and to 4 in the tables, where 1 is given as 1, and an index between "
        "-0.00005 and 0.00005 other than 0 with two significant figures, so that its sign shows. "
        "The pooled elbow of an arm and stand size puts the four districts' tables of stands "
        "together, each row keyed by its district and stand label (labels repeat across districts), in "
        "the order Angul, Dhenkanal, Kendujhar, Koraput and within each by stand label, each row keeping "
        "whether it is in its run's fit. It preprocesses them together by the runs' own rule, threshold "
        "and angle pairs, and sweeps k on the rows in the fit with the same code and the same starts "
        "(`fmu.stages.k_elbow.fit_space_sweep`). k-means++ depends on the order of the rows, so each "
        "pooled elbow is also made with the same rows in reverse order, with the same preprocessing and "
        "the same sweep, and given beside it (the declaration's note of 27 Oct 2026); each run's elbow "
        "has one order, the run's. The two arms' sums of squares are in different spaces "
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
        if area.pooled:
            lines.append(f"| {reversed_title(area)} | {_knee_cell(area, 'handcrafted', arms, reverse=True)} | "
                         f"{_knee_cell(area, 'alphaearth', arms, reverse=True)} | {_fitted_cell(arms)} |")
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
    two = any(s.elbow_reversed is not None for s in arms.values())
    orders = ", the rows in the stated order and in reverse order" if two else ""
    lines += [f"![{area.title}: the k elbow, {shown_arms}{orders}]({stem}/{area.key}.png)", "",
              _caption(arms), ""]
    if not two:
        return [*lines, *_k_table({a: s.elbow for a, s in arms.items()}), ""]
    stated = {a: s.elbow for a, s in arms.items()}
    backwards = {a: s.elbow_reversed for a, s in arms.items() if s.elbow_reversed is not None}
    return [*lines,
            "**The rows in the stated order** (Angul, Dhenkanal, Kendujhar, Koraput, each by stand "
            f"label). {_knees_sentence(stated)}", "", *_k_table(stated), "",
            "**The same rows in reverse order** (the same preprocessing and the same sweep). "
            f"{_knees_sentence(backwards)}", "", *_k_table(backwards), ""]


def _k_table(elbows: dict[str, Elbow]) -> list[str]:
    """A table of k against each arm's sum of squares, its knee marked, and the starts' median and
    lowest index."""
    head = ["k"]
    for arm in elbows:
        head += [f"{ARM_TEXT[arm]}: sum of squares", "median ARI", "lowest ARI"]
    lines = ["| " + " | ".join(head) + " |", "|" + "---:|" * len(head)]
    for k in sorted({k for e in elbows.values() for k in e.ks}):
        cells = [str(k)]
        for e in elbows.values():
            if k in e.ks:
                i = e.ks.index(k)
                cells += [_num(e.wcss[i]) + (" (knee)" if k == e.knee else ""), _ari(e.ari_median[i]),
                          _ari(e.ari_min[i])]
            else:
                cells += ["", "", ""]
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def _caption(arms: dict[str, Series]) -> str:
    """A figure's caption: a pool's two columns, how its sums of squares are scaled, its index's
    scale as draw_figure sets it (below 0 when an index is, in either order), and its colours."""
    low = lowest_ari(arms)
    scale = ("on a scale from 0 to 1." if low >= 0 else
             f"on a scale from 0 to 1 taken down to {_ari(ari_floor(arms))}, below the lowest, {_ari(low)}, "
             "where an index below 0 means two starts agree less than chance would.")
    bottom = (f"Bottom: the adjusted Rand index of the {N_PAIRS} pairs of the {N_STARTS} starts, the "
              f"median (solid, with points) and the lowest (dashed), {scale}")
    two = any(s.elbow_reversed is not None for s in arms.values())
    columns = ("Left: the rows in the stated order; right: the same rows in reverse order, on the same "
               "axes. " if two else "")
    in_order = " in that order" if two else ""
    marked = "ringed and named in each panel's legend" if two else "ringed and labelled"
    if len(arms) > 1:
        return (f"*{columns}Top: each arm's within-cluster sum of squares (the best of the starts) divided "
                f"by its own value at k = 2{in_order}, as the two arms' sums are in different spaces, on a "
                f"scale from 0; each arm's knee is {marked}. {bottom} Blue: hand-crafted; vermillion: "
                "AlphaEarth.*")
    (arm,) = arms
    colour = {"handcrafted": "blue", "alphaearth": "vermillion"}[arm]
    return (f"*{columns}Top: the within-cluster sum of squares (the best of the starts) divided by its "
            f"value at k = 2{in_order}, on a scale from 0; the knee is {marked}. {bottom} One arm, "
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


def environment() -> dict[str, Any]:
    """The environment and the package versions, for the run record: read before any result is put
    in place, as pip freeze takes seconds."""
    from fmu.utils.provenance import environment_state

    return {"environment": environment_state(), "packages": packages()}


def run_record(*, argv: list[str], started: dict[str, Any], result_files: list[str],
               reads: list[Read], run_check: bool, missing: list[str],
               env: dict[str, Any]) -> dict[str, Any]:
    """The run record; git_at_end is read now, once the results are in place."""
    return {
        "result_files": result_files,
        "command_line": "python " + " ".join(shlex.quote(a) for a in
                                             ["odisha_script/r14_elbow_report.py", *argv]),
        "date": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "git": started,
        "git_at_end": git_block(now=True),
        "environment": env["environment"],
        "packages": env["packages"],
        "run_check": run_check,
        "missing_runs": missing,
        "row_orders": ROW_ORDERS,
        "inputs": [{"run": r.run, "file": r.file, "path": shown(r.path), "off_git": r.off_git,
                    "bytes": r.n_bytes, "sha256": r.sha256} for r in reads],
    }


# ---------------------------------------------------------------------- main
def outputs(out_dir: Path, stem: str) -> tuple[Path, Path, Path, Path]:
    """<stem>.csv, <stem>_report.md, <stem>_run.json and the figures' folder <stem>/."""
    return (out_dir / f"{stem}.csv", out_dir / f"{stem}_report.md", out_dir / f"{stem}_run.json",
            out_dir / stem)


def work_folders(out_dir: Path, stem: str) -> list[Path]:
    """The work folders earlier runs left in out_dir when killed while they wrote (SIGKILL, or a
    signal no finally block sees). Only what main() makes is taken for one: a folder, not a link,
    named as tempfile.mkdtemp names main()'s (.<stem>. and 8 characters from a to z, 0 to 9 and
    "_", its alphabet), holding nothing but the names main() writes there: the figures' folder
    <stem>/ with figures <area>.png in it, <stem>.csv, <stem>_report.md and <stem>_run.json, each
    a plain file. Anything else is left alone (the gate's review, part 7)."""
    if not out_dir.is_dir():
        return []
    named = re.compile(re.escape(f".{stem}.") + "[a-z0-9_]{8}")
    files = {f"{stem}.csv", f"{stem}_report.md", f"{stem}_run.json"}
    figures = {f"{a.key}.png" for a in AREAS}

    def plain(p: Path, names: set[str]) -> bool:
        return p.name in names and p.is_file() and not p.is_symlink()

    def own(folder: Path) -> bool:
        try:
            for p in folder.iterdir():
                if p.name == stem and p.is_dir() and not p.is_symlink():
                    if not all(plain(f, figures) for f in p.iterdir()):
                        return False
                elif not plain(p, files):
                    return False
        except OSError:  # a folder that cannot be read is not one main() left
            return False
        return True

    return [p for p in sorted(out_dir.iterdir())
            if named.fullmatch(p.name) and p.is_dir() and not p.is_symlink() and own(p)]


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
    # The work folder of an earlier run that was killed while it wrote (SIGKILL, or a signal no
    # finally block sees): part of that run's outputs (the gate's review, part 5). Only a folder
    # this script makes is taken for one; anything else is left alone (part 7).
    leftover = work_folders(args.out_dir, args.stem)
    there += leftover
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
    rule, threshold = one_rule(runs)
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
                         missing=missing, run_check=not args.no_run_check, rule=rule, threshold=threshold)
    for name, text in ((csv_path.name, table), (report_path.name, report)):
        if STAMP.search(text):
            raise SystemExit(f"{name}: a value holding a date and time; results only")

    # Everything is written into a folder of its own beside the outputs, and put in place only once
    # it all is, so that a failure that is not a stop (a full disk, Ctrl-C) while the figures are
    # drawn or the environment read leaves no part of them (the gate's review, part 3). Then the
    # figures, the csv and the report are put in place, one file at a time, the git state is read
    # again, and the run record goes in last (part 5): a failure in that last second can leave part
    # of them, beside the rest of an earlier run's (the module docstring; part 7).
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for old in leftover:
        shutil.rmtree(old, ignore_errors=True)
    work = Path(tempfile.mkdtemp(prefix=f".{args.stem}.", dir=args.out_dir))
    try:
        (work / fig_dir.name).mkdir()
        figures = []
        for area in AREAS:
            if series[area.key]:
                draw_figure(area, series[area.key], work / fig_dir.name / f"{area.key}.png")
                figures.append(f"{args.stem}/{area.key}.png")
        (work / csv_path.name).write_text(table, encoding="utf-8")
        (work / report_path.name).write_text(report, encoding="utf-8")
        env = environment()
        fig_dir.mkdir(exist_ok=True)
        for area in AREAS:
            if series[area.key]:
                os.replace(work / fig_dir.name / f"{area.key}.png", fig_dir / f"{area.key}.png")
            else:  # no arm has an elbow: an earlier run's figure of the area (--overwrite) is not left
                (fig_dir / f"{area.key}.png").unlink(missing_ok=True)
        for path in (csv_path, report_path):
            os.replace(work / path.name, path)
        record = run_record(argv=argv_given, started=started,
                            result_files=[csv_path.name, report_path.name, *figures], reads=reads,
                            run_check=not args.no_run_check, missing=missing, env=env)
        (work / record_path.name).write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
        os.replace(work / record_path.name, record_path)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    print(f"wrote {shown(csv_path)}, {shown(report_path)}, {len(figures)} figures in {shown(fig_dir)}, "
          f"and {shown(record_path)}")
    print("the knees:")
    for area in AREAS:
        arms = series[area.key]
        print(f"  {area.title}: " + ", ".join(f"{ARM_WORD[a]} {_knee_cell(area, a, arms)}" for a in ARMS
                                              if a in arms or area.pooled or a in area.runs))
        if area.pooled:
            print(f"  {reversed_title(area)}: "
                  + ", ".join(f"{ARM_WORD[a]} {_knee_cell(area, a, arms, reverse=True)}" for a in ARMS))
    return 0


if __name__ == "__main__":
    sys.exit(main())

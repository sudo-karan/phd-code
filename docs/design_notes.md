# Design notes

Notes on why the code is the way it is. Companion to `decisions.md` in the
phd-notebook repo — `decisions.md` *locks* choices, this file *explains* them.
Keep entries short. If something needs more, write it up properly.

---

## Config: Pydantic v2 vs dataclasses / dicts

Pydantic gives clear error messages when a YAML field is wrong, type-checks at
load time, and supports `.env` integration via pydantic-settings. Plain
dataclasses would need a hand-rolled validator. Dicts lose all of this.

Cost: one more dependency. Worth it.

`extra="forbid"` on every model so a typo in YAML errors immediately instead
of silently using a default.

## Settings vs Config

Two separate Pydantic things on purpose:

- `Settings` (`settings.py`) — per-machine, from `.env`, gitignored. Project
  ID, output paths, log level. Different per user.
- `Config` (`config.py`) — per-experiment, from YAML, in git. ROI, dates,
  parameters. Same for everyone running the same experiment.

If two people run `python ... --config baseline.yaml` they should get the
same output. That only holds if scientific parameters are in the YAML, not
the env. See DEC-003.

## ROI: GeoJSON now, GEE asset path reserved

GeoJSON works for small ROIs and is version-controlled. GEE inline geometry
is capped around 5 MB. For complex / national-park-scale polygons we'd hit
that; the schema accepts `roi_asset` for that case but only `roi_file` is
implemented. See DEC-005.

## Logging: per-run folder, not single rolling log

`outputs/runs/<config>_<timestamp>/` per run, containing `fmu.log`,
`manifest.json`, and (later) GeoTIFFs and reports. Lets us tar/archive
individual runs and supports the longitudinal record of validation metrics.
See DEC-009.

## GEE: explicit init, not auto-on-import

`init_gee()` must be called explicitly. Auto-init on import would mean tests
that don't touch GEE can't import any module without authenticating, and
errors at import time are confusing. See DEC-008.

## `safe_get_info` wrapper

GEE errors fire at materialization (`.getInfo()`), not at construction.
Without context labels, error tracebacks point at the materialization line —
50+ lines away from the offending operation. The wrapper attaches a context
string so the error tells you which operation failed.

Pattern: any `.getInfo()` in stage code should go through `safe_get_info` or
the `safe_call` decorator. See DEC-010.

## Stage contract: context-dict + declared inputs/produces

Stages communicate through a shared `PipelineContext`, not via named
parameters. Each stage declares `required_inputs` and `produces` as class
attributes; the orchestrator validates these against the context before
running. This gets the flexibility of dict-passing (new keys don't break
existing signatures) with the readability of named params (the registry
can list what each stage needs without reading its body). See DEC-012.

## Stage failure: exceptions only, no soft-fail

A stage either succeeds or raises. `warnings` field on `StageResult` is
informational only. Research pipelines benefit from loud failures — silent
partial failures cause subtle wrong results that are hard to detect later.
See DEC-013.

## Two-tier testing

`pytest` runs fast mocked tests by default (~1 sec, no auth, runs in CI).
`pytest -m live_gee` runs real-API tests (~10-20 sec, needs auth, run before
locking a module). Both have to pass before locking. See DEC-011.

## Baseline matches the working notebook, not the aspirational design

`configs/sanjay_van_baseline.yaml` uses what the notebooks did:
S2_SR_HARMONIZED, k=6, zscore, single annual harmonic. HLS migration,
auto-K, robust scaling, and dual harmonic are deferred to separate config
files for comparison against the baseline.

The baseline is the reference, not the best version. New ideas become new
configs and have to beat it. This is the mechanism for stopping the
"going-in-circles" pattern. See DEC-006.

## Date windows differ by sensor

Three separate windows for three jobs:

- **phenology (long, 8y)**: harmonic regression needs many cycles for stable
  amplitude/phase. Year-to-year anomalies have to average out.
- **radar (5y)**: Sentinel-1B operational 2016 – Dec 2021 (mission ended Aug
  2022). From late 2021 through 2024 only S1A operated, so revisit dropped
  from 6 to 12 days. We cap at 2021 to keep per-month image counts
  consistent. S1C launched Dec 2024, S1D Nov 2025; constellation back to
  full multi-satellite operation in 2025.
- **optical composite (1y)**: one cloud-free median, recent year, for SNIC
  to draw boundaries on. Not a time series.

## Pydantic v1 vs v2

v2 throughout. Faster, better error messages, official pydantic-settings
companion, current standard. Don't accidentally install v1 — they're not
compatible.

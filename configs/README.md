# Configs

Each YAML file in this directory defines a complete pipeline run: ROI, dates, datasets, parameters, output paths.

**The baseline config is `sanjay_van_baseline.yaml`.** This is the locked reference configuration. Once a stable version exists, this file should not be modified — new ideas become new config files, compared against the baseline.

## How configs work

Configs are loaded by `fmu.config.load_config()`, which:
1. Reads the YAML file
2. Merges with environment variables (from `.env` — see `.env.example`)
3. Validates against the Pydantic schema in `src/fmu/config.py`
4. Returns a typed `Config` object the pipeline can use

If a field is missing, has the wrong type, or violates a constraint, you get a clear Pydantic error pointing at the offending field. No more "the pipeline silently used a wrong default."

## Adding a new config

1. Copy `sanjay_van_baseline.yaml` to a new filename describing the experiment
2. Modify only the fields that differ from baseline
3. Run: `python scripts/run_pipeline.py --config configs/your_new_config.yaml`
4. The new run produces its own outputs and report — the baseline is untouched

## Status

Module 2 (`config.py`) is not yet implemented, so this directory will be populated when that module lands.

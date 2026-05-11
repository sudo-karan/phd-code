# Configs

One YAML per pipeline run: ROI, dates, datasets, parameters, output settings.

`sanjay_van_baseline.yaml` is the locked baseline. New experiments become new
YAML files — don't edit the baseline in place. See `docs/design_notes.md`.

## How configs are loaded

`fmu.config.load_config(path)`:
1. Reads the YAML file
2. Validates against the Pydantic schema in `src/fmu/config.py`
3. Returns a typed `Config` object

Per-machine values (GEE project ID, output paths) come from `.env` via
`fmu.settings.get_settings()` — that's a separate layer, not part of
`load_config`.

## Adding a new config

Copy `sanjay_van_baseline.yaml`, change what you need, run it. The new
config's outputs go to their own folder under `outputs/runs/`.

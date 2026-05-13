# fmu — Forest Management Units

Multi-sensor pipeline for delineating forest stands from open satellite data,
running server-side on Google Earth Engine.

Pre-alpha. Scaffold + config + utils + orchestrator in place. Real stages
(data load, masking, features, segmentation, clustering) coming.

## Setup

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
earthengine authenticate            # one-time per machine
cp .env.example .env                # then set GEE_PROJECT_ID
pytest                              # fast tier
pytest -m live_gee                  # real-GEE tier (needs auth)
```

## Layout

```
src/fmu/              package
  config.py           pydantic YAML schema
  settings.py         .env / per-machine settings
  pipeline.py         orchestrator
  stages/             pipeline stages (base.py contract; concrete stages WIP)
  metrics/            validation metrics (WIP)
  utils/              gee.py, logging.py
configs/              YAML configs, one per experiment
aois/                 GeoJSON polygons
tests/                pytest tests (fast + live_gee tiers)
docs/design_notes.md  why the code is the way it is
legacy/               pre-package Colab notebooks (read-only)
```

## Tests

- `pytest` → fast tier only (~1s, no auth, runs in CI). Tests pure-Python infrastructure.
- `pytest -m live_gee` → real-API tier (~10-20s, needs `earthengine authenticate`). Tests GEE stages against real data.

**CI runs only the fast tier.** GEE stages must be verified locally with `pytest -m live_gee` before locking a module — CI cannot do this. See `docs/current_flow.md` for the testing policy.

## License

MIT — see `LICENSE`.

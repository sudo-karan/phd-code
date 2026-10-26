"""The date windows of data_load include their last day (review A4), offline.

A config gives each window by its first and last day, both inside it: the register
(dn-date-windows-one-shared-window), docs/datasets.md and docs/design_notes.md declare
2017-01-01 to 2022-12-31, and the stage records the window as the config gives it.
Earth Engine's filterDate takes an exclusive end, so the stage must pass the day after
the last day, as features_embedding does (`ee.Date(end).advance(1, "day")`). Before
round 13 it passed the last day itself, so the S2 phenology collection, the S1
collection and the S2 composite stopped a day early, on 30 Dec 2022, while the manifests
recorded 31 Dec. Earth Engine is replaced by the recorder of tests/_ee_recorder.py.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

import yaml

import fmu.stages.data_load as data_load_module
from _ee_recorder import Rec, made_by, owner_call
from fmu.config import Config
from fmu.stages.base import PipelineContext

REPO = Path(__file__).resolve().parent.parent
CONFIG = REPO / "configs" / "odisha_v120_3ha_squares_angul_keptland_s1desc_r9.yaml"

# Three different windows, so that each collection is seen to take its own.
WINDOWS = {
    "phenology": ("2017-01-01", "2022-12-31"),
    "radar": ("2018-03-01", "2021-06-30"),
    "optical_composite": ("2022-01-01", "2022-12-31"),
}


def _config() -> Config:
    raw = yaml.safe_load(CONFIG.read_text())
    for window, (start, end) in WINDOWS.items():
        raw["dates"][window] = {"start": start, "end": end}
    return Config.model_validate(raw)


def _record(monkeypatch) -> list:
    log: list = []
    monkeypatch.setattr(data_load_module, "ee", Rec("ee", log))
    # Each window holds images, so the stage does not stop on an empty one.
    monkeypatch.setattr(data_load_module, "safe_get_info", lambda obj, context="": 1)
    return log


def _collection(log: list, call: Any) -> str:
    """The dataset a filterDate call filters: ee.ImageCollection(id).filterBounds(roi).filterDate."""
    bounds = owner_call(log, call)
    assert bounds.attr == "filterBounds"
    return owner_call(log, bounds).args[0]


def _days_kept(log: list, call: Any) -> str:
    """The first and last day a filterDate call keeps, as the stage records a window.

    filterDate keeps an image from its start (included) to its end (excluded): an end
    given as a date string keeps the day before it last; `ee.Date(day).advance(1, "day")`
    keeps `day` last.
    """
    start, end = call.args
    if isinstance(end, Rec):
        advance = made_by(log, end)
        day = owner_call(log, advance)
        assert (day.name, advance.attr, advance.args) == ("ee.Date", "advance", (1, "day"))
        (last,) = day.args
    else:
        last = str(date.fromisoformat(end) - timedelta(days=1))
    return f"{start} to {last}"


def test_each_window_keeps_its_last_day_as_recorded(monkeypatch):
    config = _config()
    log = _record(monkeypatch)
    ctx = PipelineContext()
    ctx.set("roi", Rec("roi", log))
    result = data_load_module.DataLoadStage().run(ctx, config)

    filters = [c for c in log if c.attr == "filterDate"]
    # The S2 phenology collection, the S1 collection, then the S2 composite's.
    assert [_collection(log, c) for c in filters] == [
        config.datasets.phenology_collection,
        config.datasets.radar_collection,
        config.datasets.optical_composite_collection,
    ]
    kept = dict(zip(["s2_phenology_window", "s1_radar_window", "s2_composite_window"],
                    [_days_kept(log, c) for c in filters], strict=True))
    recorded = {k: result.metadata[k] for k in kept}
    assert kept == recorded
    assert recorded == {
        "s2_phenology_window": "2017-01-01 to 2022-12-31",
        "s1_radar_window": "2018-03-01 to 2021-06-30",
        "s2_composite_window": "2022-01-01 to 2022-12-31",
    }


def test_the_composite_named_in_the_record_is_filtered_as_the_one_computed(monkeypatch):
    """input_collections names the composite's images for the manifest: the same window."""
    config = _config()
    log = _record(monkeypatch)
    ctx = PipelineContext()
    ctx.set("roi", Rec("roi", log))
    data_load_module.DataLoadStage().run(ctx, config)
    computed = [c for c in log if c.attr == "filterDate"][-1]
    n_run = len(log)
    data_load_module.DataLoadStage().input_collections(ctx, config)
    (named,) = [c for c in log[n_run:] if c.attr == "filterDate"]
    assert _collection(log, named) == _collection(log, computed)
    assert _days_kept(log, named) == _days_kept(log, computed) == "2022-01-01 to 2022-12-31"
